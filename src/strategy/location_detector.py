"""
Location detector (algorithmic S/R + manual zones via feedback system)
"""

import asyncio
from typing import List, Dict
import pandas as pd
from utils.logger import setup_logger

logger = setup_logger(__name__)

class LocationDetector:
    def __init__(self, config, binance_client, feedback_system=None):
        self.config = config
        self.client = binance_client
        self.feedback_system = feedback_system

    async def get_all_locations(self, symbol: str, current_price: float) -> Dict:
        locations = {}
        klines = await self.client.get_klines(symbol, '15m', 500)
        if klines:
            df = self._klines_to_df(klines)
            # naive S/R detector: local highs/lows frequency
            sr_zones = self._detect_sr_zones(df)
            locations['sr_zones'] = sr_zones
            vwap = self._vwap(df)
            vwap_std = df['close'].std()
            locations['vwap_15m'] = vwap
            locations['vwap_bands'] = {
                'vwap': vwap,
                'upper_1std': vwap + vwap_std,
                'lower_1std': vwap - vwap_std
            }
            locations['emas_15m'] = {
                20: float(df['close'].ewm(span=20).mean().iloc[-1]),
                50: float(df['close'].ewm(span=50).mean().iloc[-1])
            }
        else:
            locations['sr_zones'] = []

        # incorporate manual zones
        if self.feedback_system:
            manual = []
            for z in self.feedback_system.manual_zones.values():
                manual.append({
                    'level': z.price_level,
                    'upper_bound': z.upper_bound,
                    'lower_bound': z.lower_bound,
                    'strength': z.hits + 1,
                    'zone_type': z.zone_type,
                    'weight': z.adjusted_weight,
                    'is_manual': True
                })
            combined = locations.get('sr_zones', []) + manual
            combined.sort(key=lambda x: x.get('strength',0)*x.get('weight',1.0), reverse=True)
            locations['sr_zones'] = combined
            locations['manual_zone_count'] = len(manual)
        return locations

    def _klines_to_df(self, klines):
        df = pd.DataFrame(klines, columns=['open_time','open','high','low','close','volume','close_time','qav','num_trades','tb_base','tb_quote','ignore'])
        for c in ['open','high','low','close','volume']:
            df[c] = df[c].astype(float)
        return df

    def _vwap(self, df):
        tp = (df['high'] + df['low'] + df['close']) / 3
        return float((tp * df['volume']).sum() / df['volume'].sum())

    def _detect_sr_zones(self, df):
        # simple frequency-based zones: cluster local minima/maxima
        highs = df['high']
        lows = df['low']
        closes = df['close']
        zones = []
        window = 20
        for i in range(window, len(df)-window):
            cur = df.iloc[i]
            if cur['high'] == max(df['high'].iloc[i-window:i+window]):
                zones.append({'level': float(cur['high']), 'upper_bound': float(cur['high']*1.001), 'lower_bound': float(cur['high']*0.999), 'strength': 2, 'zone_type': 'resistance', 'weight':1.0})
            if cur['low'] == min(df['low'].iloc[i-window:i+window]):
                zones.append({'level': float(cur['low']), 'upper_bound': float(cur['low']*1.001), 'lower_bound': float(cur['low']*0.999), 'strength': 2, 'zone_type': 'support', 'weight':1.0})
        # dedupe by level proximity
        merged = []
        zones = sorted(zones, key=lambda z: z['level'])
        for z in zones:
            if not merged:
                merged.append(z)
            else:
                if abs(merged[-1]['level'] - z['level']) / z['level'] < 0.0015:
                    merged[-1]['strength'] += z['strength']
                else:
                    merged.append(z)
        return merged

