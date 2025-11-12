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

class ContextAnalyzer:
    def __init__(self, config, binance_client):
        self.config = config
        self.client = binance_client

    async def get_context(self, symbol: str, timeframe: str, current_price: float) -> MarketContext:
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
            range_low=range_low
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
        plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)

        # Calculate DX and ADX
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
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

