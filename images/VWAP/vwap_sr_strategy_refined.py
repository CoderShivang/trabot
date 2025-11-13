"""
VWAP + S/R STRATEGY WITH ADVANCED ZONE DETECTION
Now uses your manual zone detection logic!

Key Features:
1. ✅ Advanced S/R detection (matches your purple boxes)
2. ✅ Filters choppy areas (avoids your red ellipses)
3. ✅ Session-based VWAP with bands
4. ✅ Pullback detection for trend continuation
5. ✅ Confluence-based entry system
6. ✅ Limit orders with timeout
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Dict
from dataclasses import dataclass
import asyncio
import time

# Import the advanced S/R detector!
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
    
    def is_near_band(self, price: float, band_name: str, threshold: float = 75) -> bool:
        """Check if price is near a specific band"""
        bands = {
            'upper_1std': self.upper_1std,
            'lower_1std': self.lower_1std,
            'upper_2std': self.upper_2std,
            'lower_2std': self.lower_2std,
            'vwap': self.vwap
        }
        return abs(price - bands[band_name]) <= threshold


@dataclass
class MarketStructure:
    """Market structure analysis"""
    bias: str
    confidence: float
    all_bands_below: bool
    all_bands_above: bool


@dataclass
class TradeSetup:
    """Complete trade setup"""
    direction: str
    setup_type: str
    limit_price: float
    stop_price: float
    target_price: float
    confidence: int
    reason: str
    sr_zone: SRZone
    vwap_band: float
    timeout: int


# ============================================================================
# VWAP CALCULATOR
# ============================================================================

class VWAPCalculator:
    """Session-based VWAP calculator"""
    
    def calculate(self, df: pd.DataFrame) -> VWAPBands:
        """Calculate VWAP bands for current session"""
        # Use today's data
        df = df.copy()
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        today = df['datetime'].iloc[-1].date()
        session_df = df[df['datetime'].dt.date == today]
        
        if len(session_df) < 10:
            session_df = df.tail(100)
        
        # Typical price
        typical_price = (session_df['high'] + session_df['low'] + session_df['close']) / 3
        
        # VWAP
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
# MARKET ANALYZER
# ============================================================================

class MarketAnalyzer:
    """Analyze market structure and bias"""
    
    def analyze(self, price: float, vwap: VWAPBands) -> MarketStructure:
        """Determine market structure"""
        # All bands below = strongly bullish
        all_bands_below = price > vwap.upper_1std
        
        # All bands above = strongly bearish
        all_bands_above = price < vwap.lower_1std
        
        if all_bands_below:
            return MarketStructure(
                bias='strongly_bullish',
                confidence=0.85,
                all_bands_below=True,
                all_bands_above=False
            )
        elif all_bands_above:
            return MarketStructure(
                bias='strongly_bearish',
                confidence=0.85,
                all_bands_below=False,
                all_bands_above=True
            )
        elif vwap.lower_1std <= price <= vwap.vwap:
            return MarketStructure(
                bias='bullish_mean_reversion',
                confidence=0.70,
                all_bands_below=False,
                all_bands_above=False
            )
        elif vwap.vwap <= price <= vwap.upper_1std:
            return MarketStructure(
                bias='bearish_mean_reversion',
                confidence=0.70,
                all_bands_below=False,
                all_bands_above=False
            )
        else:
            return MarketStructure(
                bias='neutral',
                confidence=0.50,
                all_bands_below=False,
                all_bands_above=False
            )


# ============================================================================
# STRATEGY CORE
# ============================================================================

class VWAPSRStrategy:
    """
    VWAP + S/R Strategy with Advanced Zone Detection
    
    NOW USES: AdvancedSRDetector - finds zones like your purple boxes!
    """
    
    def __init__(self, config):
        self.config = config
        
        # 🎯 ADVANCED S/R DETECTOR (the new hotness!)
        self.sr_detector = AdvancedSRDetector()
        
        # Other components
        self.vwap_calc = VWAPCalculator()
        self.market_analyzer = MarketAnalyzer()
        
        # Parameters
        self.target_points = 270
        self.stop_points = 190
        self.band_proximity = 75
        self.zone_proximity = 150
        self.min_zone_strength = 50  # Only trade strong zones
        
        # Timeouts
        self.mean_reversion_timeout = 180
        self.trend_continuation_timeout = 300
        
        # State
        self.sr_zones: List[SRZone] = []
        self.last_zone_update = 0
        self.zone_update_interval = 300  # Update every 5 minutes
        self.pending_orders = {}
    
    def update_zones(self, df: pd.DataFrame, force: bool = False):
        """
        Update S/R zones using ADVANCED DETECTOR
        """
        current_time = time.time()
        
        if force or (current_time - self.last_zone_update > self.zone_update_interval):
            print("\n🔍 Updating S/R zones with ADVANCED DETECTOR...")
            
            # 🎯 THIS IS WHERE THE MAGIC HAPPENS
            # Using your manual zone detection logic!
            self.sr_zones = self.sr_detector.detect_zones(df, lookback=200)
            
            self.last_zone_update = current_time
            
            # Show strong zones
            strong_zones = [z for z in self.sr_zones if z.strength >= self.min_zone_strength]
            
            print(f"✅ Found {len(strong_zones)} STRONG S/R zones (strength ≥{self.min_zone_strength})")
            
            for zone in strong_zones[:5]:
                print(f"  • {zone.zone_type.upper():11} at ${zone.level:9,.2f} "
                      f"(strength: {zone.strength:2}, touches: {zone.touches}, "
                      f"rejections: {zone.rejections})")
    
    def find_setups(self, df: pd.DataFrame, current_price: float) -> List[TradeSetup]:
        """
        Find trade setups with VWAP + Advanced S/R confluence
        """
        # Update zones
        self.update_zones(df)
        
        # Calculate VWAP
        vwap = self.vwap_calc.calculate(df)
        
        # Analyze market
        structure = self.market_analyzer.analyze(current_price, vwap)
        
        # Filter to strong zones only
        strong_zones = [z for z in self.sr_zones if z.strength >= self.min_zone_strength]
        
        setups = []
        
        # ==========================================
        # LONG SETUPS
        # ==========================================
        
        # 1. Mean Reversion Long: -1σ + Support
        if structure.bias in ['bullish_mean_reversion', 'neutral']:
            if vwap.is_near_band(current_price, 'lower_1std', self.band_proximity):
                
                for zone in strong_zones:
                    if zone.zone_type == 'support' and zone.is_near(current_price, self.zone_proximity):
                        
                        # Calculate confluence score
                        confluence_score = self._calculate_confluence(
                            zone=zone,
                            bias_confidence=structure.confidence,
                            distance=abs(current_price - zone.level)
                        )
                        
                        if confluence_score >= 70:
                            limit_price = max(zone.level - 30, current_price - 50)
                            
                            setups.append(TradeSetup(
                                direction='LONG',
                                setup_type='mean_reversion',
                                limit_price=limit_price,
                                stop_price=limit_price - self.stop_points,
                                target_price=limit_price + self.target_points,
                                confidence=confluence_score,
                                reason=(
                                    f"LONG: -1σ (${vwap.lower_1std:,.0f}) + "
                                    f"Support ${zone.level:,.0f} "
                                    f"(str:{zone.strength}, t:{zone.touches}, r:{zone.rejections})"
                                ),
                                sr_zone=zone,
                                vwap_band=vwap.lower_1std,
                                timeout=self.mean_reversion_timeout
                            ))
        
        # 2. Trend Continuation Long
        if structure.all_bands_below:
            if vwap.is_near_band(current_price, 'upper_1std', self.band_proximity):
                
                for zone in strong_zones:
                    if zone.is_near(current_price, self.zone_proximity):
                        
                        confluence_score = self._calculate_confluence(
                            zone=zone,
                            bias_confidence=structure.confidence,
                            distance=abs(current_price - zone.level)
                        )
                        
                        if confluence_score >= 65:
                            limit_price = min(vwap.upper_1std, zone.level) - 30
                            
                            setups.append(TradeSetup(
                                direction='LONG',
                                setup_type='trend_continuation',
                                limit_price=limit_price,
                                stop_price=limit_price - self.stop_points,
                                target_price=limit_price + self.target_points,
                                confidence=confluence_score,
                                reason=(
                                    f"LONG: Pullback to +1σ (${vwap.upper_1std:,.0f}) "
                                    f"in uptrend + structure ${zone.level:,.0f} "
                                    f"(str:{zone.strength})"
                                ),
                                sr_zone=zone,
                                vwap_band=vwap.upper_1std,
                                timeout=self.trend_continuation_timeout
                            ))
        
        # ==========================================
        # SHORT SETUPS
        # ==========================================
        
        # 3. Mean Reversion Short: +1σ + Resistance
        if structure.bias in ['bearish_mean_reversion', 'neutral']:
            if vwap.is_near_band(current_price, 'upper_1std', self.band_proximity):
                
                for zone in strong_zones:
                    if zone.zone_type == 'resistance' and zone.is_near(current_price, self.zone_proximity):
                        
                        confluence_score = self._calculate_confluence(
                            zone=zone,
                            bias_confidence=structure.confidence,
                            distance=abs(current_price - zone.level)
                        )
                        
                        if confluence_score >= 70:
                            limit_price = min(zone.level + 30, current_price + 50)
                            
                            setups.append(TradeSetup(
                                direction='SHORT',
                                setup_type='mean_reversion',
                                limit_price=limit_price,
                                stop_price=limit_price + self.stop_points,
                                target_price=limit_price - self.target_points,
                                confidence=confluence_score,
                                reason=(
                                    f"SHORT: +1σ (${vwap.upper_1std:,.0f}) + "
                                    f"Resistance ${zone.level:,.0f} "
                                    f"(str:{zone.strength}, t:{zone.touches}, r:{zone.rejections})"
                                ),
                                sr_zone=zone,
                                vwap_band=vwap.upper_1std,
                                timeout=self.mean_reversion_timeout
                            ))
        
        # 4. Trend Continuation Short
        if structure.all_bands_above:
            if vwap.is_near_band(current_price, 'lower_1std', self.band_proximity):
                
                for zone in strong_zones:
                    if zone.is_near(current_price, self.zone_proximity):
                        
                        confluence_score = self._calculate_confluence(
                            zone=zone,
                            bias_confidence=structure.confidence,
                            distance=abs(current_price - zone.level)
                        )
                        
                        if confluence_score >= 65:
                            limit_price = max(vwap.lower_1std, zone.level) + 30
                            
                            setups.append(TradeSetup(
                                direction='SHORT',
                                setup_type='trend_continuation',
                                limit_price=limit_price,
                                stop_price=limit_price + self.stop_points,
                                target_price=limit_price - self.target_points,
                                confidence=confluence_score,
                                reason=(
                                    f"SHORT: Pullback to -1σ (${vwap.lower_1std:,.0f}) "
                                    f"in downtrend + structure ${zone.level:,.0f} "
                                    f"(str:{zone.strength})"
                                ),
                                sr_zone=zone,
                                vwap_band=vwap.lower_1std,
                                timeout=self.trend_continuation_timeout
                            ))
        
        # Sort by confidence
        setups.sort(key=lambda s: s.confidence, reverse=True)
        
        return setups
    
    def _calculate_confluence(self, zone: SRZone, bias_confidence: float, 
                             distance: float) -> int:
        """
        Calculate confluence score (0-100)
        
        Now uses ADVANCED zone metrics!
        """
        score = 0
        
        # Zone strength (up to 40 points) - from advanced detector!
        score += min(zone.strength * 0.4, 40)
        
        # Bias confidence (up to 30 points)
        score += bias_confidence * 30
        
        # Zone touches (up to 15 points)
        score += min(zone.touches * 3, 15)
        
        # Zone rejections (up to 10 points) - from advanced detector!
        score += min(zone.rejections * 3, 10)
        
        # Proximity (up to 5 points)
        if distance <= 50:
            score += 5
        elif distance <= 100:
            score += 3
        elif distance <= 150:
            score += 1
        
        return int(min(score, 100))


# ============================================================================
# ORDER MANAGER
# ============================================================================

class OrderManager:
    """Manage limit orders"""
    
    def __init__(self):
        self.pending_orders = {}
    
    async def place_order(self, symbol: str, setup: TradeSetup, binance_client):
        """Place limit order"""
        try:
            risk_usd = 20
            quantity = risk_usd / (setup.stop_price - setup.limit_price if setup.direction == 'LONG' 
                                  else setup.limit_price - setup.stop_price)
            quantity = round(quantity, 3)
            
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
            
            self.pending_orders[order_id] = {
                'symbol': symbol,
                'setup': setup,
                'quantity': quantity,
                'placed_at': time.time()
            }
            
            print(f"\n{'='*80}")
            print(f"🎯 LIMIT ORDER PLACED: {order_id}")
            print(f"{'='*80}")
            print(f"  Direction: {setup.direction}")
            print(f"  Type: {setup.setup_type.upper()}")
            print(f"  Limit: ${setup.limit_price:,.2f}")
            print(f"  Stop: ${setup.stop_price:,.2f} | Target: ${setup.target_price:,.2f}")
            print(f"  Confidence: {setup.confidence}%")
            print(f"\n  Setup: {setup.reason}")
            print(f"  Zone Quality: Strength {setup.sr_zone.strength}/100")
            print(f"  Timeout: {setup.timeout}s")
            print(f"{'='*80}\n")
            
            return order_id
        
        except Exception as e:
            print(f"❌ Error placing order: {e}")
            return None
    
    async def monitor_orders(self, binance_client):
        """Monitor pending orders"""
        for order_id in list(self.pending_orders.keys()):
            order_info = self.pending_orders[order_id]
            
            # Check timeout
            elapsed = time.time() - order_info['placed_at']
            if elapsed > order_info['setup'].timeout:
                try:
                    await binance_client.futures_cancel_order(
                        symbol=order_info['symbol'],
                        orderId=order_id
                    )
                    print(f"⏰ Order {order_id} timeout - cancelled")
                    del self.pending_orders[order_id]
                except:
                    pass
                continue
            
            # Check fill
            try:
                status = await binance_client.futures_get_order(
                    symbol=order_info['symbol'],
                    orderId=order_id
                )
                
                if status['status'] == 'FILLED':
                    print(f"✅ Order {order_id} FILLED @ ${float(status['avgPrice']):,.2f}")
                    # Place TP/SL
                    await self._place_tp_sl(order_info, binance_client)
                    del self.pending_orders[order_id]
            except:
                pass
    
    async def _place_tp_sl(self, order_info, binance_client):
        """Place TP/SL after fill"""
        setup = order_info['setup']
        side = 'SELL' if setup.direction == 'LONG' else 'BUY'
        
        try:
            # TP
            await binance_client.futures_create_order(
                symbol=order_info['symbol'],
                side=side,
                type='TAKE_PROFIT_MARKET',
                stopPrice=round(setup.target_price, 2),
                closePosition=False,
                quantity=order_info['quantity']
            )
            
            # SL
            await binance_client.futures_create_order(
                symbol=order_info['symbol'],
                side=side,
                type='STOP_MARKET',
                stopPrice=round(setup.stop_price, 2),
                closePosition=False,
                quantity=order_info['quantity']
            )
            
            print("  ✓ TP/SL orders placed\n")
        except Exception as e:
            print(f"  ❌ Error placing TP/SL: {e}\n")


# ============================================================================
# MAIN BOT
# ============================================================================

class VWAPSRBot:
    """
    Complete VWAP + S/R bot with ADVANCED zone detection
    """
    
    def __init__(self, config, binance_client):
        self.config = config
        self.binance = binance_client
        self.strategy = VWAPSRStrategy(config)
        self.order_manager = OrderManager()
        self.running = False
    
    async def start(self):
        """Start the bot"""
        self.running = True
        
        print("\n" + "="*80)
        print("VWAP + S/R BOT WITH ADVANCED ZONE DETECTION")
        print("="*80)
        print("\n✨ NOW USING ADVANCED S/R DETECTOR!")
        print("  ✓ Finds zones like your purple boxes")
        print("  ✓ Avoids choppy areas like your red ellipses")
        print("  ✓ Validates zones with touches + rejections")
        print("  ✓ Only trades zones with strength ≥50")
        print("\n" + "="*80 + "\n")
        
        await self.main_loop()
    
    async def main_loop(self):
        """Main trading loop"""
        while self.running:
            try:
                for symbol in self.config.symbols:
                    await self.process_symbol(symbol)
                
                # Monitor orders
                await self.order_manager.monitor_orders(self.binance)
                
                # Wait 60 seconds
                await asyncio.sleep(60)
            
            except Exception as e:
                print(f"❌ Error in main loop: {e}")
                import traceback
                traceback.print_exc()
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
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            current_price = df['close'].iloc[-1]
            
            # Find setups
            setups = self.strategy.find_setups(df, current_price)
            
            # Display status
            vwap = self.strategy.vwap_calc.calculate(df)
            structure = self.strategy.market_analyzer.analyze(current_price, vwap)
            strong_zones = len([z for z in self.strategy.sr_zones 
                              if z.strength >= self.strategy.min_zone_strength])
            
            print(f"\n[{symbol}] ${current_price:,.2f}")
            print(f"  VWAP: ${vwap.vwap:,.2f} | +1σ: ${vwap.upper_1std:,.2f} | -1σ: ${vwap.lower_1std:,.2f}")
            print(f"  Bias: {structure.bias} ({structure.confidence:.0%})")
            print(f"  Strong S/R Zones: {strong_zones}")
            print(f"  Pending Orders: {len(self.order_manager.pending_orders)}")
            
            # Place orders
            if setups and len(self.order_manager.pending_orders) < 3:
                best_setup = setups[0]
                
                print(f"\n🎯 SETUP FOUND:")
                print(f"  {best_setup.direction} {best_setup.setup_type}")
                print(f"  Confidence: {best_setup.confidence}%")
                print(f"  {best_setup.reason}")
                
                await self.order_manager.place_order(symbol, best_setup, self.binance)
        
        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class BotConfig:
    """Bot configuration"""
    symbols: List[str]
    risk_per_trade: float = 20.0


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║     VWAP + S/R STRATEGY WITH ADVANCED ZONE DETECTION                      ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║  ✨ NOW USING ADVANCED S/R DETECTOR! ✨                                   ║
║                                                                           ║
║  The bot now finds S/R zones EXACTLY like you do manually:               ║
║                                                                           ║
║  ✓ Detects consolidation zones (your purple boxes)                       ║
║  ✓ Filters out choppy/trending areas (your red ellipses)                 ║
║  ✓ Validates zones with touches and rejections                           ║
║  ✓ Scores zones 0-100 for quality                                        ║
║  ✓ Only trades zones with strength ≥50                                   ║
║                                                                           ║
║  Combined with:                                                           ║
║  • Session-based VWAP with ±1σ bands                                     ║
║  • Market structure analysis                                             ║
║  • Confluence-based entries                                              ║
║  • Limit orders with timeout                                             ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
    """)
