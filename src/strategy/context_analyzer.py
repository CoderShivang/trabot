"""
Context analyzer for HTF context (VWAP, EMAs, ATR)
"""

import pandas as pd
import asyncio
from dataclasses import dataclass
from typing import Any
from utils.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class MarketContext:
    symbol: str
    current_price: float
    vwap: float
    ema20: float
    ema50: float
    ema200: float
    atr: float
    trend_strength: float

    # Regime detection indicators
    adx: float = 0.0
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    bb_width_pct: float = 0.0

    # Market regime classification
    regime: str = "unknown"  # "trending", "choppy", "ranging"
    range_high: float = 0.0  # Range boundary high (if in range mode)
    range_low: float = 0.0   # Range boundary low (if in range mode)

    # Trend direction (NEW)
    trend_direction: str = "neutral"  # "bullish", "bearish", "neutral"
    price_above_ema200: bool = False
    ema50_above_ema200: bool = False

class ContextAnalyzer:
    def __init__(self, config, binance_client):
        self.config = config
        self.client = binance_client

        # Backtest mode support
        self.backtest_mode = False
        self.backtest_klines_cache = None
        self.backtest_current_timestamp = None

    def set_backtest_data(self, klines_cache: dict, current_timestamp: int):
        """Set backtest mode and provide historical data"""
        self.backtest_mode = True
        self.backtest_klines_cache = klines_cache
        self.backtest_current_timestamp = current_timestamp

    def clear_backtest_mode(self):
        """Disable backtest mode"""
        self.backtest_mode = False
        self.backtest_klines_cache = None
        self.backtest_current_timestamp = None

    async def get_context(self, symbol: str, timeframe: str, current_price: float) -> MarketContext:
        # In backtest mode, use historical data up to current_timestamp
        if self.backtest_mode and self.backtest_klines_cache:
            klines = self._get_historical_klines(symbol, timeframe, self.backtest_current_timestamp)
        else:
            # Live mode: fetch from API
            klines = await self.client.get_klines(symbol, timeframe, 500)
        if not klines:
            return MarketContext(symbol, current_price, current_price, current_price, current_price, current_price, 0.0, 0.0)

        df = pd.DataFrame(klines, columns=[
            'open_time','open','high','low','close','volume','close_time','qav','num_trades','tb_base','tb_quote','ignore'
        ])
        for c in ['open','high','low','close','volume']:
            df[c] = df[c].astype(float)

        # Basic indicators
        vwap = self._vwap(df)
        ema20 = float(df['close'].ewm(span=20).mean().iloc[-1])
        ema50 = float(df['close'].ewm(span=50).mean().iloc[-1])
        ema200 = float(df['close'].ewm(span=200).mean().iloc[-1]) if len(df) >= 200 else ema50
        atr = self._atr(df)
        trend_strength = abs(ema50 - ema200) / ema200 if ema200 > 0 else 0

        # Regime detection indicators
        adx = self._adx(df)
        bb_upper, bb_middle, bb_lower, bb_width_pct = self._bollinger_bands(df, current_price)

        # Classify market regime
        regime, range_high, range_low = self._classify_regime(df, adx, bb_width_pct, current_price)

        # Determine trend direction (NEW)
        price_above_ema200 = current_price > ema200
        ema50_above_ema200 = ema50 > ema200

        # Strong bullish: price > EMA200 AND EMA50 > EMA200
        # Strong bearish: price < EMA200 AND EMA50 < EMA200
        # Neutral: mixed signals
        if price_above_ema200 and ema50_above_ema200:
            trend_direction = "bullish"
        elif not price_above_ema200 and not ema50_above_ema200:
            trend_direction = "bearish"
        else:
            trend_direction = "neutral"

        return MarketContext(
            symbol=symbol,
            current_price=current_price,
            vwap=vwap,
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            atr=atr,
            trend_strength=trend_strength,
            adx=adx,
            bb_upper=bb_upper,
            bb_middle=bb_middle,
            bb_lower=bb_lower,
            bb_width_pct=bb_width_pct,
            regime=regime,
            range_high=range_high,
            range_low=range_low,
            trend_direction=trend_direction,
            price_above_ema200=price_above_ema200,
            ema50_above_ema200=ema50_above_ema200
        )

    def _vwap(self, df: pd.DataFrame) -> float:
        tp = (df['high'] + df['low'] + df['close']) / 3
        return float((tp * df['volume']).sum() / df['volume'].sum())

    def _atr(self, df: pd.DataFrame, period: int = 14) -> float:
        high = df['high']
        low = df['low']
        prev_close = df['close'].shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return float(atr) if not pd.isna(atr) else 0.0

    def _adx(self, df: pd.DataFrame, period: int = None) -> float:
        """Calculate ADX (Average Directional Index) for trend strength"""
        if period is None:
            period = self.config.regime_detection.adx_period

        high = df['high']
        low = df['low']
        close = df['close']

        # Calculate +DM and -DM
        plus_dm = high.diff()
        minus_dm = -low.diff()

        # Zero out negative/invalid values
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        # True Range
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Smooth the TR, +DM, -DM using Wilder's smoothing (exponential moving average)
        atr = tr.ewm(alpha=1/period, adjust=False).mean()

        # Avoid division by zero - replace zero ATR values with small number
        atr_safe = atr.replace(0, 1e-10)

        plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr_safe)
        minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr_safe)

        # Calculate DX and ADX - avoid division by zero
        di_sum = plus_di + minus_di
        di_sum_safe = di_sum.replace(0, 1e-10)
        dx = 100 * (plus_di - minus_di).abs() / di_sum_safe
        adx = dx.ewm(alpha=1/period, adjust=False).mean().iloc[-1]

        return float(adx) if not pd.isna(adx) else 0.0

    def _bollinger_bands(self, df: pd.DataFrame, current_price: float) -> tuple:
        """Calculate Bollinger Bands"""
        period = self.config.regime_detection.bb_period
        std_dev = self.config.regime_detection.bb_std_dev

        # Calculate middle band (SMA)
        bb_middle = df['close'].rolling(period).mean().iloc[-1]

        # Calculate standard deviation
        bb_std = df['close'].rolling(period).std().iloc[-1]

        # Calculate upper and lower bands
        bb_upper = bb_middle + (std_dev * bb_std)
        bb_lower = bb_middle - (std_dev * bb_std)

        # Calculate BB width as percentage of price
        bb_width_pct = ((bb_upper - bb_lower) / bb_middle) if bb_middle > 0 else 0.0

        return float(bb_upper), float(bb_middle), float(bb_lower), float(bb_width_pct)

    def _classify_regime(self, df: pd.DataFrame, adx: float, bb_width_pct: float, current_price: float) -> tuple:
        """Classify market regime: trending, choppy, or ranging"""

        adx_trending = self.config.regime_detection.adx_trending_threshold
        adx_choppy = self.config.regime_detection.adx_choppy_threshold
        bb_squeeze = self.config.regime_detection.bb_squeeze_threshold
        lookback = self.config.regime_detection.range_detection_lookback
        consolidation_threshold = self.config.regime_detection.range_consolidation_threshold

        # Get recent price action for range detection
        recent_df = df.tail(lookback)
        recent_high = recent_df['high'].max()
        recent_low = recent_df['low'].min()
        price_range_pct = (recent_high - recent_low) / recent_low if recent_low > 0 else 1.0

        # Regime classification logic
        regime = "unknown"
        range_high = 0.0
        range_low = 0.0

        if adx >= adx_trending:
            # Strong trend detected
            regime = "trending"

        elif adx < adx_choppy and bb_width_pct < bb_squeeze:
            # Low ADX + tight Bollinger Bands = tight consolidation/squeeze
            regime = "ranging"
            range_high = recent_high
            range_low = recent_low

        elif price_range_pct < consolidation_threshold:
            # Price staying within narrow range = consolidation
            regime = "ranging"
            range_high = recent_high
            range_low = recent_low

        else:
            # Between trending and ranging = choppy
            regime = "choppy"

        logger.debug(f"[REGIME] ADX={adx:.1f}, BB_width={bb_width_pct:.3f}, Range={price_range_pct:.3f} → {regime.upper()}")

        return regime, range_high, range_low

    def _get_historical_klines(self, symbol: str, timeframe: str, current_timestamp: int) -> list:
        """
        Get historical klines from cache up to current_timestamp for backtest.

        This creates a sliding window of historical data that progresses with the backtest,
        ensuring indicators like ADX/ATR update as the backtest moves forward.
        """
        if not self.backtest_klines_cache:
            return []

        # Get the klines cache for this symbol
        symbol_cache = self.backtest_klines_cache.get(symbol, {})

        # Get klines for the requested timeframe
        all_klines = symbol_cache.get(timeframe, [])

        if not all_klines:
            return []

        # Filter klines up to current_timestamp (inclusive)
        # Take last 500 candles before current timestamp for context calculation
        historical_klines = [k for k in all_klines if int(k[0]) <= current_timestamp]

        # Return last 500 candles (enough for EMA200 and other indicators)
        return historical_klines[-500:] if len(historical_klines) > 500 else historical_klines

