"""
ADVANCED S/R ZONE DETECTION
Based on your manual zone marking criteria

Key Principles from Your Charts:
1. Zones form in CONSOLIDATION (sideways price action)
2. Zones are HORIZONTAL (not in trends)
3. Zones have MULTIPLE touches at similar levels
4. Zones show clear REJECTION when retested
5. AVOID choppy/noisy areas (red ellipse zones)
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional
from dataclasses import dataclass
from scipy.signal import find_peaks, argrelextrema
from sklearn.cluster import DBSCAN


@dataclass
class SRZone:
    """Support/Resistance Zone"""
    level: float          # Center price
    upper: float          # Upper boundary
    lower: float          # Lower boundary
    zone_type: str        # 'support', 'resistance', 'both'
    strength: int         # Quality score (0-100)
    touches: int          # Number of price touches
    first_touch_idx: int  # First touch bar index
    last_touch_idx: int   # Most recent touch bar index
    rejections: int       # Number of clear rejections
    volatility: float     # Zone volatility (lower = better)
    is_consolidation: bool  # Formed during consolidation?


# ============================================================================
# STEP 1: IDENTIFY CONSOLIDATION ZONES (Where S/R forms)
# ============================================================================

class ConsolidationDetector:
    """
    Detect consolidation/ranging periods
    This is WHERE we look for S/R zones
    """
    
    def __init__(self, min_bars: int = 15, max_range_pct: float = 0.02):
        self.min_bars = min_bars  # Minimum bars for consolidation
        self.max_range_pct = max_range_pct  # Max 2% range = consolidation
    
    def find_consolidation_zones(self, df: pd.DataFrame) -> List[Tuple[int, int]]:
        """
        Find consolidation zones (sideways price action)
        Returns: List of (start_idx, end_idx) tuples
        """
        consolidations = []
        window_size = self.min_bars
        
        i = 0
        while i < len(df) - window_size:
            # Get window
            window = df.iloc[i:i+window_size]
            
            # Calculate range
            high = window['high'].max()
            low = window['low'].min()
            mid = (high + low) / 2
            range_pct = (high - low) / mid
            
            # Check if consolidating
            if range_pct <= self.max_range_pct:
                # Extend consolidation zone forward
                end_idx = i + window_size
                
                while end_idx < len(df):
                    extended_window = df.iloc[i:end_idx+1]
                    ext_high = extended_window['high'].max()
                    ext_low = extended_window['low'].min()
                    ext_mid = (ext_high + ext_low) / 2
                    ext_range_pct = (ext_high - ext_low) / ext_mid
                    
                    if ext_range_pct <= self.max_range_pct * 1.5:  # Allow slight expansion
                        end_idx += 1
                    else:
                        break
                
                # Valid consolidation if long enough
                if end_idx - i >= self.min_bars:
                    consolidations.append((i, end_idx))
                    i = end_idx  # Skip past this zone
                    continue
            
            i += 1
        
        return consolidations
    
    def is_choppy_trend(self, df: pd.DataFrame, start: int, end: int) -> bool:
        """
        Check if zone is choppy/noisy (like your red ellipse)
        
        Choppy characteristics:
        - High volatility
        - No clear horizontal level
        - Overlapping wicks
        - Part of trending move
        """
        window = df.iloc[start:end]
        
        # 1. Check trend strength
        closes = window['close'].values
        if len(closes) < 5:
            return True
        
        # Linear regression to detect trend
        x = np.arange(len(closes))
        slope, _ = np.polyfit(x, closes, 1)
        avg_price = closes.mean()
        slope_pct = (slope * len(closes)) / avg_price
        
        # Strong trend = not consolidation
        if abs(slope_pct) > 0.03:  # More than 3% slope
            return True
        
        # 2. Check volatility (choppy = high volatility)
        returns = np.diff(closes) / closes[:-1]
        volatility = returns.std()
        
        # High volatility = choppy
        if volatility > 0.008:  # More than 0.8% std
            return True
        
        # 3. Check wick overlap (choppy has lots of overlapping wicks)
        overlaps = 0
        for i in range(len(window) - 1):
            bar1_high = window['high'].iloc[i]
            bar1_low = window['low'].iloc[i]
            bar2_high = window['high'].iloc[i+1]
            bar2_low = window['low'].iloc[i+1]
            
            # Check if ranges overlap significantly
            overlap_high = min(bar1_high, bar2_high)
            overlap_low = max(bar1_low, bar2_low)
            
            if overlap_high > overlap_low:
                overlap_size = overlap_high - overlap_low
                bar1_size = bar1_high - bar1_low
                if bar1_size > 0 and overlap_size / bar1_size > 0.7:
                    overlaps += 1
        
        overlap_ratio = overlaps / max(len(window) - 1, 1)
        
        # Too many overlaps = choppy
        if overlap_ratio > 0.6:
            return True
        
        return False


# ============================================================================
# STEP 2: FIND HORIZONTAL LEVELS (The actual S/R levels)
# ============================================================================

class HorizontalLevelDetector:
    """
    Find horizontal price levels within consolidation zones
    These become S/R zones
    """
    
    def __init__(self, tolerance_pct: float = 0.003):
        self.tolerance_pct = tolerance_pct  # 0.3% tolerance for "same level"
    
    def find_levels(self, df: pd.DataFrame, start_idx: int, end_idx: int) -> List[float]:
        """
        Find horizontal levels in consolidation zone
        
        Method:
        1. Extract all swing highs and lows
        2. Cluster them by price level
        3. Return cluster centers as S/R levels
        """
        window = df.iloc[start_idx:end_idx]
        
        # Get swing points
        swing_highs = self._find_swing_highs(window)
        swing_lows = self._find_swing_lows(window)
        
        # Combine all levels
        all_levels = swing_highs + swing_lows
        
        if len(all_levels) < 2:
            return []
        
        # Cluster levels using DBSCAN
        levels_array = np.array(all_levels).reshape(-1, 1)
        avg_price = window['close'].mean()
        eps = avg_price * self.tolerance_pct
        
        clustering = DBSCAN(eps=eps, min_samples=2).fit(levels_array)
        labels = clustering.labels_
        
        # Get cluster centers
        unique_labels = set(labels)
        cluster_centers = []
        
        for label in unique_labels:
            if label == -1:  # Noise
                continue
            
            cluster_points = levels_array[labels == label]
            center = cluster_points.mean()
            cluster_centers.append(center)
        
        return sorted(cluster_centers)
    
    def _find_swing_highs(self, df: pd.DataFrame, order: int = 3) -> List[float]:
        """Find swing high points"""
        highs = df['high'].values
        peaks, _ = find_peaks(highs, distance=order)
        return [highs[i] for i in peaks]
    
    def _find_swing_lows(self, df: pd.DataFrame, order: int = 3) -> List[float]:
        """Find swing low points"""
        lows = df['low'].values
        inverted = -lows
        peaks, _ = find_peaks(inverted, distance=order)
        return [lows[i] for i in peaks]


# ============================================================================
# STEP 3: VALIDATE ZONES (Check quality and rejections)
# ============================================================================

class ZoneValidator:
    """
    Validate S/R zones by checking:
    1. Number of touches
    2. Clear rejections
    3. Consistency
    """
    
    def __init__(self, touch_tolerance_pct: float = 0.004):
        self.touch_tolerance_pct = touch_tolerance_pct
    
    def validate_zone(self, df: pd.DataFrame, level: float, 
                     zone_start_idx: int) -> Optional[SRZone]:
        """
        Validate an S/R level
        
        Returns SRZone if valid, None if invalid
        """
        avg_price = df['close'].mean()
        tolerance = avg_price * self.touch_tolerance_pct
        
        # Create zone boundaries
        upper = level + tolerance
        lower = level - tolerance
        
        # Find all touches
        touches = []
        rejections = 0
        
        for i in range(zone_start_idx, len(df)):
            bar_high = df['high'].iloc[i]
            bar_low = df['low'].iloc[i]
            bar_close = df['close'].iloc[i]
            
            # Check if price touched zone
            if bar_low <= upper and bar_high >= lower:
                touches.append(i)
                
                # Check for rejection (wick through zone but close outside)
                if bar_high >= upper and bar_close < upper:
                    rejections += 1  # Rejection from resistance
                elif bar_low <= lower and bar_close > lower:
                    rejections += 1  # Rejection from support
        
        # Need at least 2 touches
        if len(touches) < 2:
            return None
        
        # Determine zone type
        supports = 0
        resistances = 0
        
        for touch_idx in touches:
            bar_close = df['close'].iloc[touch_idx]
            if bar_close < level:
                supports += 1
            else:
                resistances += 1
        
        if supports > resistances * 1.5:
            zone_type = 'support'
        elif resistances > supports * 1.5:
            zone_type = 'resistance'
        else:
            zone_type = 'both'
        
        # Calculate volatility at zone
        zone_bars = df.iloc[touches[0]:touches[-1]+1]
        if len(zone_bars) > 2:
            returns = zone_bars['close'].pct_change().dropna()
            volatility = returns.std()
        else:
            volatility = 0
        
        # Calculate strength (0-100)
        strength = self._calculate_strength(
            touches=len(touches),
            rejections=rejections,
            volatility=volatility,
            zone_type=zone_type
        )
        
        return SRZone(
            level=level,
            upper=upper,
            lower=lower,
            zone_type=zone_type,
            strength=strength,
            touches=len(touches),
            first_touch_idx=touches[0],
            last_touch_idx=touches[-1],
            rejections=rejections,
            volatility=volatility,
            is_consolidation=True
        )
    
    def _calculate_strength(self, touches: int, rejections: int, 
                          volatility: float, zone_type: str) -> int:
        """
        Calculate zone strength score (0-100)
        
        Higher score = better zone
        """
        score = 0
        
        # More touches = stronger (up to 40 points)
        score += min(touches * 8, 40)
        
        # Rejections = very strong (up to 30 points)
        score += min(rejections * 10, 30)
        
        # Low volatility = more consistent (up to 20 points)
        vol_score = max(0, 20 - (volatility * 1000))
        score += vol_score
        
        # Clear zone type = stronger (10 points)
        if zone_type in ['support', 'resistance']:
            score += 10
        
        return int(min(score, 100))


# ============================================================================
# MAIN S/R DETECTOR
# ============================================================================

class AdvancedSRDetector:
    """
    Complete S/R detection system
    
    Pipeline:
    1. Find consolidation zones (WHERE to look)
    2. Find horizontal levels (WHAT the levels are)
    3. Validate zones (QUALITY check)
    4. Filter out choppy areas (AVOID red ellipse zones)
    """
    
    def __init__(self):
        self.consolidation_detector = ConsolidationDetector(
            min_bars=15,
            max_range_pct=0.02
        )
        self.level_detector = HorizontalLevelDetector(
            tolerance_pct=0.003
        )
        self.validator = ZoneValidator(
            touch_tolerance_pct=0.004
        )
    
    def detect_zones(self, df: pd.DataFrame, lookback: int = 200) -> List[SRZone]:
        """
        Main detection method
        
        Returns list of high-quality S/R zones
        """
        # Use recent data
        recent_df = df.tail(lookback).reset_index(drop=True)
        
        # Step 1: Find consolidation zones
        consolidations = self.consolidation_detector.find_consolidation_zones(recent_df)
        
        print(f"\n📊 Found {len(consolidations)} consolidation zones")
        
        all_zones = []
        
        # Step 2-3: For each consolidation, find and validate levels
        for start_idx, end_idx in consolidations:
            # Check if choppy (skip if true)
            if self.consolidation_detector.is_choppy_trend(recent_df, start_idx, end_idx):
                print(f"  ⚠️  Skipping choppy zone at bars {start_idx}-{end_idx}")
                continue
            
            print(f"  ✓ Processing consolidation at bars {start_idx}-{end_idx}")
            
            # Find horizontal levels
            levels = self.level_detector.find_levels(recent_df, start_idx, end_idx)
            
            print(f"    Found {len(levels)} horizontal levels")
            
            # Validate each level
            for level in levels:
                zone = self.validator.validate_zone(recent_df, level, start_idx)
                
                if zone and zone.strength >= 40:  # Minimum strength threshold
                    all_zones.append(zone)
                    print(f"    ✓ Valid {zone.zone_type} zone at ${zone.level:,.2f} "
                          f"(strength: {zone.strength}, touches: {zone.touches})")
        
        # Sort by strength
        all_zones.sort(key=lambda z: z.strength, reverse=True)
        
        # Remove overlapping zones (keep strongest)
        final_zones = self._remove_overlapping(all_zones)
        
        print(f"\n✅ Final: {len(final_zones)} high-quality S/R zones\n")
        
        return final_zones
    
    def _remove_overlapping(self, zones: List[SRZone]) -> List[SRZone]:
        """Remove overlapping zones, keep strongest"""
        if not zones:
            return []
        
        final = [zones[0]]
        
        for zone in zones[1:]:
            overlaps = False
            
            for existing in final:
                # Check overlap
                if not (zone.upper < existing.lower or zone.lower > existing.upper):
                    overlaps = True
                    break
            
            if not overlaps:
                final.append(zone)
        
        return final
    
    def find_nearest_zone(self, zones: List[SRZone], price: float, 
                         max_distance_pct: float = 0.01) -> Optional[SRZone]:
        """Find nearest S/R zone to current price"""
        nearest = None
        min_distance = float('inf')
        
        max_distance = price * max_distance_pct
        
        for zone in zones:
            distance = abs(price - zone.level)
            
            if distance < min_distance and distance <= max_distance:
                min_distance = distance
                nearest = zone
        
        return nearest


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

def example_usage():
    """Example of how to use the detector"""
    
    # Assuming you have a DataFrame with OHLCV data
    # df = pd.DataFrame(...)
    
    # Initialize detector
    detector = AdvancedSRDetector()
    
    # Detect zones
    zones = detector.detect_zones(df, lookback=200)
    
    # Print zones
    print("\n" + "="*70)
    print("DETECTED S/R ZONES")
    print("="*70)
    
    for i, zone in enumerate(zones[:10], 1):
        print(f"\n#{i} {zone.zone_type.upper()} Zone:")
        print(f"  Level: ${zone.level:,.2f}")
        print(f"  Range: ${zone.lower:,.2f} - ${zone.upper:,.2f}")
        print(f"  Strength: {zone.strength}/100")
        print(f"  Touches: {zone.touches}")
        print(f"  Rejections: {zone.rejections}")
        print(f"  Formed in consolidation: {zone.is_consolidation}")
    
    # Find zone near current price
    current_price = df['close'].iloc[-1]
    nearest_zone = detector.find_nearest_zone(zones, current_price, max_distance_pct=0.01)
    
    if nearest_zone:
        print(f"\n📍 Nearest zone to current price (${current_price:,.2f}):")
        print(f"  {nearest_zone.zone_type.upper()} at ${nearest_zone.level:,.2f}")
        print(f"  Distance: ${abs(current_price - nearest_zone.level):,.2f}")
        print(f"  Strength: {nearest_zone.strength}/100")


# ============================================================================
# PSEUDO-CODE SUMMARY
# ============================================================================

"""
PSEUDO-CODE FOR S/R DETECTION:

1. FIND CONSOLIDATION ZONES:
   - Scan chart for areas where price range is tight (< 2% range)
   - Must be at least 15 bars long
   - This is WHERE S/R zones form
   
2. FILTER OUT CHOPPY AREAS (Your Red Ellipse):
   - Check trend strength (strong trend = skip)
   - Check volatility (high volatility = skip)
   - Check wick overlap (too much overlap = skip)
   
3. FIND HORIZONTAL LEVELS:
   - Within valid consolidation zones:
     * Extract swing highs and swing lows
     * Cluster nearby levels (within 0.3%)
     * These clusters = potential S/R zones
   
4. VALIDATE ZONES:
   - Count touches (need at least 2)
   - Count rejections (wick through zone but close outside)
   - Check consistency (low volatility at zone)
   - Calculate strength score (0-100)
   
5. QUALITY FILTER:
   - Keep zones with strength >= 40
   - Remove overlapping zones (keep strongest)
   - Sort by strength
   
6. USE IN TRADING:
   - Check if current price near any zone
   - Wait for retest + rejection
   - Enter trade on confirmation
"""

print(__doc__)
