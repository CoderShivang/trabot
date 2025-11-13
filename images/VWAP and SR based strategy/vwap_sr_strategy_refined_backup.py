"""
REFINED VWAP + S/R STRATEGY
Based on your trading charts and description

Key Improvements:
1. ADVANCED S/R zone detection (matches your manual zones!)
2. Pullback detection for trend continuation trades
3. Price action confirmation before order placement
4. Session-based VWAP (resets daily)
5. Proper confluence scoring system

Now uses AdvancedSRDetector to find zones like your purple boxes
and avoid choppy areas like your red ellipses!
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio
import time

# Import the advanced S/R detector
from sr_zone_detector import AdvancedSRDetector, SRZone


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class VWAPBands:
    """VWAP with standard deviation bands"""
    vwap: float
    std: float
    upper_1std: float
    lower_1std: float
    upper_2std: float
    lower_2std: float
    
    def get_position(self, price: float) -> str:
        """Get price position relative to bands"""
        if price > self.upper_2std:
            return 'above_2std'
        elif price > self.upper_1std:
            return 'above_1std'
        elif price > self.vwap:
            return 'above_vwap'
        elif price > self.lower_1std:
            return 'below_vwap'
        elif price > self.lower_2std:
            return 'below_1std'
        else:
            return 'below_2std'
    
    def is_near_band(self, price: float, band_name: str, threshold: float = 50) -> bool:
        """Check if price is near a specific band"""
        bands = {
            'upper_1std': self.upper_1std,
            'lower_1std': self.lower_1std,
            'upper_2std': self.upper_2std,
            'lower_2std': self.lower_2std,
            'vwap': self.vwap
        }
        return abs(price - bands[band_name]) <= threshold


# NOTE: SRZone is now imported from sr_zone_detector.py
# We're using the advanced detection that matches your manual zones!


@dataclass
class MarketStructure:
    """Market structure analysis"""
    bias: str  # 'strongly_bullish', 'bullish', 'neutral', 'bearish', 'strongly_bearish'
    confidence: float
    all_bands_below: bool  # All VWAP bands below price (firmly bullish)
    all_bands_above: bool  # All VWAP bands above price (firmly bearish)
    is_trending: bool
    trend_direction: Optional[str]  # 'up', 'down', or None


@dataclass
class PriceAction:
    """Recent price action analysis"""
    is_pullback: bool
    pullback_size: float  # In points
    direction: Optional[str]  # 'up' or 'down'
    momentum: float  # -1 to 1
    recent_high: float
    recent_low: float
    consolidating: bool


@dataclass
class TradeSetup:
    """Complete trade setup with confluence"""
    direction: str  # 'LONG' or 'SHORT'
    setup_type: str  # 'mean_reversion' or 'trend_continuation'
    limit_price: float
    stop_price: float
    target_price: float
    confidence: float
    confluence_factors: List[str]
    vwap_band_aligned: bool
    sr_zone: Optional[SRZone]
    market_structure: MarketStructure
    timeout_seconds: int


# ============================================================================
# S/R ZONE DETECTION (IMPROVED)
# ============================================================================

class SRZoneDetector:
    """
    Improved S/R detection focusing on horizontal levels
    Similar to the white rectangles in your charts
    """
    
    def __init__(self, zone_thickness_pct: float = 0.003, min_touches: int = 2):
        self.zone_thickness_pct = zone_thickness_pct
        self.min_touches = min_touches
    
    def detect_zones(self, df: pd.DataFrame, lookback: int = 100) -> List[SRZone]:
        """
        Detect S/R zones from price data
        
        Method:
        1. Find swing highs and lows
        2. Cluster nearby levels
        3. Count touches and validate
        """
        recent_df = df.tail(lookback).copy()
        
        # Find swing points
        swing_highs = self._find_swing_highs(recent_df)
        swing_lows = self._find_swing_lows(recent_df)
        
        # Cluster levels
        resistance_zones = self._cluster_levels(swing_highs, recent_df, 'resistance')
        support_zones = self._cluster_levels(swing_lows, recent_df, 'support')
        
        all_zones = resistance_zones + support_zones
        
        # Filter by strength
        all_zones = [z for z in all_zones if z.strength >= self.min_touches]
        
        # Check recent tests
        current_price = df['close'].iloc[-1]
        for zone in all_zones:
            zone.validated = self._check_zone_validation(zone, recent_df)
        
        # Sort by strength and recency
        all_zones.sort(key=lambda z: (z.strength, -z.last_test_time), reverse=True)
        
        return all_zones[:15]  # Keep top 15
    
    def _find_swing_highs(self, df: pd.DataFrame, window: int = 5) -> List[Tuple[int, float]]:
        """Find swing high points"""
        swings = []
        for i in range(window, len(df) - window):
            high = df['high'].iloc[i]
            is_swing = True
            
            # Check if highest in window
            for j in range(i - window, i + window + 1):
                if j != i and df['high'].iloc[j] >= high:
                    is_swing = False
                    break
            
            if is_swing:
                swings.append((int(df['timestamp'].iloc[i]), high))
        
        return swings
    
    def _find_swing_lows(self, df: pd.DataFrame, window: int = 5) -> List[Tuple[int, float]]:
        """Find swing low points"""
        swings = []
        for i in range(window, len(df) - window):
            low = df['low'].iloc[i]
            is_swing = True
            
            # Check if lowest in window
            for j in range(i - window, i + window + 1):
                if j != i and df['low'].iloc[j] <= low:
                    is_swing = False
                    break
            
            if is_swing:
                swings.append((int(df['timestamp'].iloc[i]), low))
        
        return swings
    
    def _cluster_levels(self, swing_points: List[Tuple[int, float]], 
                       df: pd.DataFrame, zone_type: str) -> List[SRZone]:
        """Cluster nearby swing points into zones"""
        if not swing_points:
            return []
        
        # Sort by price
        swing_points.sort(key=lambda x: x[1])
        
        clusters = []
        current_cluster = [swing_points[0]]
        
        avg_price = df['close'].mean()
        cluster_threshold = avg_price * self.zone_thickness_pct
        
        for i in range(1, len(swing_points)):
            if swing_points[i][1] - current_cluster[-1][1] <= cluster_threshold:
                current_cluster.append(swing_points[i])
            else:
                if len(current_cluster) >= self.min_touches:
                    clusters.append(current_cluster)
                current_cluster = [swing_points[i]]
        
        if len(current_cluster) >= self.min_touches:
            clusters.append(current_cluster)
        
        # Convert clusters to zones
        zones = []
        for cluster in clusters:
            prices = [p[1] for p in cluster]
            level = np.mean(prices)
            upper = level + (avg_price * self.zone_thickness_pct / 2)
            lower = level - (avg_price * self.zone_thickness_pct / 2)
            
            # Last test
            last_test = max(cluster, key=lambda x: x[0])
            
            zones.append(SRZone(
                level=level,
                upper=upper,
                lower=lower,
                zone_type=zone_type,
                strength=len(cluster),
                last_test_time=last_test[0],
                last_test_result='untested',
                validated=False
            ))
        
        return zones
    
    def _check_zone_validation(self, zone: SRZone, df: pd.DataFrame) -> bool:
        """Check if zone has been validated by holding"""
        # Look for tests after formation
        tests_held = 0
        tests_broken = 0
        
        for i in range(len(df)):
            price_high = df['high'].iloc[i]
            price_low = df['low'].iloc[i]
            
            # Check if zone was tested
            if zone.lower <= price_low <= zone.upper or zone.lower <= price_high <= zone.upper:
                # Check if it held (didn't break through significantly)
                if zone.zone_type == 'support':
                    if price_low >= zone.lower - 50:  # Held with small tolerance
                        tests_held += 1
                    else:
                        tests_broken += 1
                elif zone.zone_type == 'resistance':
                    if price_high <= zone.upper + 50:
                        tests_held += 1
                    else:
                        tests_broken += 1
        
        return tests_held >= 2 and tests_broken == 0


# ============================================================================
# VWAP CALCULATOR (SESSION-BASED)
# ============================================================================

class VWAPCalculator:
    """Calculate session-based VWAP (resets daily)"""
    
    def __init__(self):
        self.session_start = None
        self.reset_hour = 0  # Reset at midnight UTC
    
    def calculate(self, df: pd.DataFrame) -> VWAPBands:
        """
        Calculate VWAP bands for current session
        """
        # Get today's data only
        df = df.copy()
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Filter to current session (today)
        today = df['datetime'].iloc[-1].date()
        session_df = df[df['datetime'].dt.date == today]
        
        if len(session_df) < 10:
            # Not enough data, use last 100 bars
            session_df = df.tail(100)
        
        # Typical price
        typical_price = (session_df['high'] + session_df['low'] + session_df['close']) / 3
        
        # VWAP = sum(typical_price * volume) / sum(volume)
        vwap = (typical_price * session_df['volume']).sum() / session_df['volume'].sum()
        
        # Standard deviation
        squared_diff = (typical_price - vwap) ** 2
        variance = (squared_diff * session_df['volume']).sum() / session_df['volume'].sum()
        std = np.sqrt(variance)
        
        return VWAPBands(
            vwap=vwap,
            std=std,
            upper_1std=vwap + std,
            lower_1std=vwap - std,
            upper_2std=vwap + (std * 2),
            lower_2std=vwap - (std * 2)
        )


# ============================================================================
# MARKET STRUCTURE ANALYZER
# ============================================================================

class MarketStructureAnalyzer:
    """Analyze market structure and bias"""
    
    def analyze(self, current_price: float, vwap_bands: VWAPBands, 
                df: pd.DataFrame) -> MarketStructure:
        """
        Determine market structure and bias
        
        Key conditions from your strategy:
        - "Price firmly bullish": all 3 bands below price
        - "Price firmly bearish": all 3 bands above price
        """
        
        # Check if all bands below price (firmly bullish)
        all_bands_below = (
            current_price > vwap_bands.upper_1std and
            current_price > vwap_bands.vwap
        )
        
        # Check if all bands above price (firmly bearish)
        all_bands_above = (
            current_price < vwap_bands.lower_1std and
            current_price < vwap_bands.vwap
        )
        
        # Determine bias
        if all_bands_below:
            bias = 'strongly_bullish'
            confidence = 0.85
            is_trending = True
            trend_direction = 'up'
        elif all_bands_above:
            bias = 'strongly_bearish'
            confidence = 0.85
            is_trending = True
            trend_direction = 'down'
        elif vwap_bands.lower_1std <= current_price <= vwap_bands.vwap:
            bias = 'bullish_mean_reversion'
            confidence = 0.70
            is_trending = False
            trend_direction = None
        elif vwap_bands.vwap <= current_price <= vwap_bands.upper_1std:
            bias = 'bearish_mean_reversion'
            confidence = 0.70
            is_trending = False
            trend_direction = None
        else:
            bias = 'neutral'
            confidence = 0.50
            is_trending = False
            trend_direction = None
        
        return MarketStructure(
            bias=bias,
            confidence=confidence,
            all_bands_below=all_bands_below,
            all_bands_above=all_bands_above,
            is_trending=is_trending,
            trend_direction=trend_direction
        )


# ============================================================================
# PRICE ACTION ANALYZER
# ============================================================================

class PriceActionAnalyzer:
    """Analyze recent price action for confirmation signals"""
    
    def analyze(self, df: pd.DataFrame, lookback: int = 20) -> PriceAction:
        """Analyze recent price action"""
        recent = df.tail(lookback)
        
        # Recent high/low
        recent_high = recent['high'].max()
        recent_low = recent['low'].min()
        current_price = recent['close'].iloc[-1]
        
        # Check for pullback
        # Pullback = price moved away from extreme then came back
        high_idx = recent['high'].idxmax()
        low_idx = recent['low'].idxmin()
        
        is_pullback = False
        pullback_size = 0
        direction = None
        
        # Check if we had a high, then pulled back
        if high_idx < len(recent) - 5:  # High was at least 5 bars ago
            pullback_size = recent_high - current_price
            if pullback_size >= 100:  # At least 100 points
                is_pullback = True
                direction = 'down'  # Pulled back down
        
        # Check if we had a low, then pulled back up
        if low_idx < len(recent) - 5:
            pullback_up = current_price - recent_low
            if pullback_up >= 100:
                is_pullback = True
                direction = 'up'  # Pulled back up
                pullback_size = pullback_up
        
        # Calculate momentum (simple)
        returns = recent['close'].pct_change().dropna()
        momentum = returns.mean() / (returns.std() + 1e-10)
        momentum = np.clip(momentum, -1, 1)
        
        # Check if consolidating
        price_range = recent_high - recent_low
        avg_price = recent['close'].mean()
        range_pct = price_range / avg_price
        consolidating = range_pct < 0.01  # Less than 1% range
        
        return PriceAction(
            is_pullback=is_pullback,
            pullback_size=pullback_size,
            direction=direction,
            momentum=momentum,
            recent_high=recent_high,
            recent_low=recent_low,
            consolidating=consolidating
        )


# ============================================================================
# STRATEGY CORE (REFINED)
# ============================================================================

class RefinedVWAPSRStrategy:
    """
    Refined VWAP + S/R strategy with proper confluence detection
    """
    
    def __init__(self, config):
        self.config = config
        
        # Components
        self.sr_detector = SRZoneDetector(zone_thickness_pct=0.003, min_touches=2)
        self.vwap_calc = VWAPCalculator()
        self.structure_analyzer = MarketStructureAnalyzer()
        self.pa_analyzer = PriceActionAnalyzer()
        
        # Parameters
        self.target_points = 270
        self.stop_points = 190
        self.band_proximity = 75  # Must be within 75 points of band
        self.zone_proximity = 150  # Must be within 150 points of S/R zone
        
        # Timeouts
        self.mean_reversion_timeout = 180  # 3 minutes
        self.trend_continuation_timeout = 300  # 5 minutes
        
        # State
        self.sr_zones: List[SRZone] = []
        self.pending_orders: Dict = {}
        self.last_setup_time = 0
        self.min_setup_interval = 60  # Don't spam setups
    
    def find_trade_setups(self, df: pd.DataFrame, current_price: float) -> List[TradeSetup]:
        """
        Find valid trade setups with proper confluence
        
        Returns list of setups sorted by confidence
        """
        # Prevent setup spam
        if time.time() - self.last_setup_time < self.min_setup_interval:
            return []
        
        # Calculate all indicators
        vwap_bands = self.vwap_calc.calculate(df)
        self.sr_zones = self.sr_detector.detect_zones(df)
        market_structure = self.structure_analyzer.analyze(current_price, vwap_bands, df)
        price_action = self.pa_analyzer.analyze(df)
        
        setups = []
        
        # ========================================
        # LONG SETUPS
        # ========================================
        
        # 1. MEAN REVERSION LONG: Price at -1σ + support zone
        if market_structure.bias in ['bullish_mean_reversion', 'neutral']:
            if vwap_bands.is_near_band(current_price, 'lower_1std', self.band_proximity):
                # Find support zones nearby
                for zone in self.sr_zones:
                    if zone.zone_type == 'support' and zone.is_near(current_price, self.zone_proximity):
                        if zone.validated:
                            confluence_factors = [
                                f"Price at -1σ (${vwap_bands.lower_1std:,.0f})",
                                f"Validated support zone at ${zone.level:,.0f} ({zone.strength} touches)",
                                "Mean reversion setup"
                            ]
                            
                            # Better entry: slightly inside the zone
                            limit_price = max(zone.level - 30, current_price - 50)
                            
                            setups.append(TradeSetup(
                                direction='LONG',
                                setup_type='mean_reversion',
                                limit_price=limit_price,
                                stop_price=limit_price - self.stop_points,
                                target_price=limit_price + self.target_points,
                                confidence=0.80,
                                confluence_factors=confluence_factors,
                                vwap_band_aligned=True,
                                sr_zone=zone,
                                market_structure=market_structure,
                                timeout_seconds=self.mean_reversion_timeout
                            ))
        
        # 2. TREND CONTINUATION LONG: Firmly bullish + pullback to +1σ + structure
        if market_structure.all_bands_below and price_action.is_pullback:
            if vwap_bands.is_near_band(current_price, 'upper_1std', self.band_proximity):
                # Find any nearby S/R (could be old resistance flipped to support)
                for zone in self.sr_zones:
                    if zone.is_near(current_price, self.zone_proximity):
                        confluence_factors = [
                            f"Strongly bullish (price above all bands)",
                            f"Pullback to +1σ (${vwap_bands.upper_1std:,.0f})",
                            f"Structure confluence at ${zone.level:,.0f}",
                            "Trend continuation setup"
                        ]
                        
                        # Wait for price to start bouncing (limit order slightly below)
                        limit_price = min(vwap_bands.upper_1std, zone.level) - 30
                        
                        setups.append(TradeSetup(
                            direction='LONG',
                            setup_type='trend_continuation',
                            limit_price=limit_price,
                            stop_price=limit_price - self.stop_points,
                            target_price=limit_price + self.target_points,
                            confidence=0.75,
                            confluence_factors=confluence_factors,
                            vwap_band_aligned=True,
                            sr_zone=zone,
                            market_structure=market_structure,
                            timeout_seconds=self.trend_continuation_timeout
                        ))
        
        # ========================================
        # SHORT SETUPS
        # ========================================
        
        # 3. MEAN REVERSION SHORT: Price at +1σ + resistance zone
        if market_structure.bias in ['bearish_mean_reversion', 'neutral']:
            if vwap_bands.is_near_band(current_price, 'upper_1std', self.band_proximity):
                for zone in self.sr_zones:
                    if zone.zone_type == 'resistance' and zone.is_near(current_price, self.zone_proximity):
                        if zone.validated:
                            confluence_factors = [
                                f"Price at +1σ (${vwap_bands.upper_1std:,.0f})",
                                f"Validated resistance zone at ${zone.level:,.0f} ({zone.strength} touches)",
                                "Mean reversion setup"
                            ]
                            
                            limit_price = min(zone.level + 30, current_price + 50)
                            
                            setups.append(TradeSetup(
                                direction='SHORT',
                                setup_type='mean_reversion',
                                limit_price=limit_price,
                                stop_price=limit_price + self.stop_points,
                                target_price=limit_price - self.target_points,
                                confidence=0.80,
                                confluence_factors=confluence_factors,
                                vwap_band_aligned=True,
                                sr_zone=zone,
                                market_structure=market_structure,
                                timeout_seconds=self.mean_reversion_timeout
                            ))
        
        # 4. TREND CONTINUATION SHORT: Firmly bearish + pullback to -1σ + structure
        if market_structure.all_bands_above and price_action.is_pullback:
            if vwap_bands.is_near_band(current_price, 'lower_1std', self.band_proximity):
                for zone in self.sr_zones:
                    if zone.is_near(current_price, self.zone_proximity):
                        confluence_factors = [
                            f"Strongly bearish (price below all bands)",
                            f"Pullback to -1σ (${vwap_bands.lower_1std:,.0f})",
                            f"Structure confluence at ${zone.level:,.0f}",
                            "Trend continuation setup"
                        ]
                        
                        limit_price = max(vwap_bands.lower_1std, zone.level) + 30
                        
                        setups.append(TradeSetup(
                            direction='SHORT',
                            setup_type='trend_continuation',
                            limit_price=limit_price,
                            stop_price=limit_price + self.stop_points,
                            target_price=limit_price - self.target_points,
                            confidence=0.75,
                            confluence_factors=confluence_factors,
                            vwap_band_aligned=True,
                            sr_zone=zone,
                            market_structure=market_structure,
                            timeout_seconds=self.trend_continuation_timeout
                        ))
        
        # Sort by confidence
        setups.sort(key=lambda s: s.confidence, reverse=True)
        
        if setups:
            self.last_setup_time = time.time()
        
        return setups


# ============================================================================
# ORDER MANAGER
# ============================================================================

class LimitOrderManager:
    """Manage limit orders with timeout"""
    
    def __init__(self):
        self.pending_orders: Dict[str, Dict] = {}
    
    async def place_order(self, symbol: str, setup: TradeSetup, binance_client):
        """Place limit order"""
        try:
            # Calculate quantity (risk $20 per trade)
            risk_usd = 20
            quantity = risk_usd / setup.stop_points
            quantity = round(quantity, 3)
            
            # Place limit order
            side = 'BUY' if setup.direction == 'LONG' else 'SELL'
            
            order = await binance_client.futures_create_order(
                symbol=symbol,
                side=side,
                type='LIMIT',
                timeInForce='GTC',
                quantity=quantity,
                price=round(setup.limit_price, 2)
            )
            
            order_id = order['orderId']
            
            # Store order info
            self.pending_orders[order_id] = {
                'symbol': symbol,
                'setup': setup,
                'quantity': quantity,
                'placed_at': time.time(),
                'status': 'pending'
            }
            
            print(f"\n{'='*70}")
            print(f"🎯 LIMIT ORDER PLACED")
            print(f"{'='*70}")
            print(f"Direction: {setup.direction}")
            print(f"Type: {setup.setup_type.upper()}")
            print(f"Limit Price: ${setup.limit_price:,.2f}")
            print(f"Stop Loss: ${setup.stop_price:,.2f} (-${setup.stop_points})")
            print(f"Take Profit: ${setup.target_price:,.2f} (+${setup.target_points})")
            print(f"Confidence: {setup.confidence:.0%}")
            print(f"\nConfluence Factors:")
            for factor in setup.confluence_factors:
                print(f"  ✓ {factor}")
            print(f"\nTimeout: {setup.timeout_seconds}s")
            print(f"{'='*70}\n")
            
            return order_id
        
        except Exception as e:
            print(f"❌ Error placing order: {e}")
            return None
    
    async def monitor_orders(self, binance_client):
        """Monitor and manage pending orders"""
        for order_id in list(self.pending_orders.keys()):
            order_info = self.pending_orders[order_id]
            
            # Check timeout
            elapsed = time.time() - order_info['placed_at']
            if elapsed > order_info['setup'].timeout_seconds:
                # Cancel order
                try:
                    await binance_client.futures_cancel_order(
                        symbol=order_info['symbol'],
                        orderId=order_id
                    )
                    print(f"\n⏰ Order {order_id} timed out - cancelled")
                    del self.pending_orders[order_id]
                except:
                    pass
                continue
            
            # Check if filled
            try:
                status = await binance_client.futures_get_order(
                    symbol=order_info['symbol'],
                    orderId=order_id
                )
                
                if status['status'] == 'FILLED':
                    await self._handle_fill(order_id, status, binance_client)
            except Exception as e:
                print(f"Error checking order {order_id}: {e}")
    
    async def _handle_fill(self, order_id: str, order_status: dict, binance_client):
        """Handle filled order - place TP/SL"""
        order_info = self.pending_orders[order_id]
        setup = order_info['setup']
        
        print(f"\n{'='*70}")
        print(f"✅ ORDER FILLED!")
        print(f"{'='*70}")
        print(f"{setup.direction} {order_info['symbol']}")
        print(f"Fill Price: ${float(order_status['avgPrice']):,.2f}")
        print(f"Quantity: {order_info['quantity']}")
        print(f"{'='*70}\n")
        
        try:
            # Place TP
            tp_side = 'SELL' if setup.direction == 'LONG' else 'BUY'
            await binance_client.futures_create_order(
                symbol=order_info['symbol'],
                side=tp_side,
                type='TAKE_PROFIT_MARKET',
                stopPrice=round(setup.target_price, 2),
                closePosition=False,
                quantity=order_info['quantity']
            )
            
            # Place SL
            await binance_client.futures_create_order(
                symbol=order_info['symbol'],
                side=tp_side,
                type='STOP_MARKET',
                stopPrice=round(setup.stop_price, 2),
                closePosition=False,
                quantity=order_info['quantity']
            )
            
            print("✓ TP/SL orders placed\n")
        
        except Exception as e:
            print(f"❌ Error placing TP/SL: {e}")
        
        del self.pending_orders[order_id]


# ============================================================================
# MAIN BOT
# ============================================================================

class VWAPSRBot:
    """Main trading bot"""
    
    def __init__(self, config, binance_client):
        self.config = config
        self.binance = binance_client
        self.strategy = RefinedVWAPSRStrategy(config)
        self.order_manager = LimitOrderManager()
        self.running = False
    
    async def start(self):
        """Start the bot"""
        self.running = True
        print("\n" + "="*70)
        print("VWAP + S/R STRATEGY BOT STARTED")
        print("="*70 + "\n")
        
        await self.main_loop()
    
    async def stop(self):
        """Stop the bot"""
        self.running = False
        print("\n" + "="*70)
        print("BOT STOPPED")
        print("="*70 + "\n")
    
    async def main_loop(self):
        """Main trading loop"""
        while self.running:
            try:
                for symbol in self.config.symbols:
                    await self.process_symbol(symbol)
                
                # Monitor existing orders
                await self.order_manager.monitor_orders(self.binance)
                
                # Wait before next iteration
                await asyncio.sleep(60)  # Check every minute
            
            except Exception as e:
                print(f"❌ Error in main loop: {e}")
                await asyncio.sleep(5)
    
    async def process_symbol(self, symbol: str):
        """Process a single symbol"""
        try:
            # Get data
            klines = await self.binance.futures_klines(
                symbol=symbol,
                interval='1m',
                limit=200
            )
            
            # Convert to DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            current_price = df['close'].iloc[-1]
            
            # Find trade setups
            setups = self.strategy.find_trade_setups(df, current_price)
            
            # Display current status
            vwap_bands = self.strategy.vwap_calc.calculate(df)
            market_structure = self.strategy.structure_analyzer.analyze(
                current_price, vwap_bands, df
            )
            
            print(f"\n[{symbol}] Price: ${current_price:,.2f}")
            print(f"  VWAP: ${vwap_bands.vwap:,.2f}")
            print(f"  +1σ: ${vwap_bands.upper_1std:,.2f} | -1σ: ${vwap_bands.lower_1std:,.2f}")
            print(f"  Bias: {market_structure.bias} ({market_structure.confidence:.0%})")
            print(f"  S/R Zones: {len(self.strategy.sr_zones)}")
            print(f"  Pending Orders: {len(self.order_manager.pending_orders)}")
            
            # Place orders if we have setups and room for more orders
            if setups and len(self.order_manager.pending_orders) < 3:
                best_setup = setups[0]
                order_id = await self.order_manager.place_order(
                    symbol, best_setup, self.binance
                )
        
        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class BotConfig:
    """Bot configuration"""
    symbols: List[str] = field(default_factory=lambda: ['BTCUSDT'])
    risk_per_trade: float = 20.0
    max_concurrent_orders: int = 3


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                   VWAP + S/R STRATEGY - REFINED                           ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║  ✓ Session-based VWAP with ±1σ, ±2σ bands                               ║
║  ✓ Improved S/R zone detection (horizontal levels)                       ║
║  ✓ Mean reversion at bands + S/R confluence                              ║
║  ✓ Trend continuation on pullbacks (firmly bullish/bearish)              ║
║  ✓ Price action confirmation before entries                              ║
║  ✓ Limit orders with timeout management                                  ║
║  ✓ Proper confluence scoring                                             ║
║                                                                           ║
║  KEY IMPROVEMENTS:                                                        ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ║
║  1. S/R zones detected from swing highs/lows (like your white boxes)     ║
║  2. Pullback detection for trend continuation trades                     ║
║  3. Zone validation (must hold after formation)                          ║
║  4. Session VWAP (resets daily)                                          ║
║  5. Confluence scoring with multiple factors                             ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
    """)
