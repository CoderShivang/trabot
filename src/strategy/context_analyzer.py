"""
Context analyzer for HTF context (VWAP, EMAs, ATR)
"""

import pandas as pd
import asyncio
from dataclasses import dataclass
from typing import Any
from src.utils.logger import setup_logger

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
        vwap = self._vwap(df)
        ema20 = float(df['close'].ewm(span=20).mean().iloc[-1])
        ema50 = float(df['close'].ewm(span=50).mean().iloc[-1])
        ema200 = float(df['close'].ewm(span=200).mean().iloc[-1]) if len(df) >= 200 else ema50
        atr = self._atr(df)
        trend_strength = abs(ema50 - ema200) / ema200 if ema200 > 0 else 0
        return MarketContext(symbol, current_price, vwap, ema20, ema50, ema200, atr, trend_strength)

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

