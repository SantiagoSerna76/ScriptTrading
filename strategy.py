"""
Momentum Dip Buyer Strategy — v3.0
====================================
Compra pullbacks (retrocesos) a la EMA20 en tendencias alcistas confirmadas.
4 condiciones de entrada, necesita 3.
Salidas con SL/TP fijos basados en ATR + breakeven automático.
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Tuple
from config import (
    EMA_CORTO, EMA_LARGO, RSI_PERIOD,
    ATR_PERIOD, ADX_PERIOD, ADX_MIN,
    SL_ATR_MULT, TP_ATR_MULT, MAX_SL_PCT,
)

logger = logging.getLogger(__name__)


class TechnicalIndicators:

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        return series.rolling(period).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """RSI con suavizado de Wilder (correcto — igual a TradingView/Binance)."""
        delta    = series.diff()
        gain     = delta.clip(lower=0)
        loss     = (-delta).clip(lower=0)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        rs  = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        h, l, c = df["high"], df["low"], df["close"]
        tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        return tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    @staticmethod
    def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        h, l, c = df["high"], df["low"], df["close"]
        up, down = h.diff(), -l.diff()
        pos_dm = up.where((up > down) & (up > 0), 0.0)
        neg_dm = down.where((down > up) & (down > 0), 0.0)
        tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        alpha  = 1 / period
        atr_w  = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
        di_pos = 100 * pos_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_w
        di_neg = 100 * neg_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_w
        dx  = 100 * (di_pos - di_neg).abs() / (di_pos + di_neg).replace(0, np.nan)
        return dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    @staticmethod
    def macd(series: pd.Series, fast=12, slow=26, signal=9):
        ema_f  = series.ewm(span=fast, adjust=False).mean()
        ema_s  = series.ewm(span=slow, adjust=False).mean()
        line   = ema_f - ema_s
        sig    = line.ewm(span=signal, adjust=False).mean()
        return line, sig, line - sig

    @staticmethod
    def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return sma, upper, lower


class StrategySignals:
    """
    Momentum Dip Buyer: Compra retrocesos a la EMA20 en tendencias alcistas.

    4 condiciones de entrada (necesita 3):
    1. Precio > EMA50 (tendencia alcista confirmada)
    2. Precio cerca de EMA20 (pullback al soporte dinámico)
    3. RSI entre 35-50 (retroceso, no pánico ni sobrecompra)
    4. ADX >= 20 (tendencia real, no lateral)
    """

    MIN_BUY_SCORE = 3   # 3 de 4 condiciones requeridas

    def __init__(self):
        self.ti = TechnicalIndicators()

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula todos los indicadores necesarios."""
        df = df.copy()
        ti = self.ti
        df["ema_short"]  = ti.ema(df["close"], EMA_CORTO)     # EMA 20
        df["ema_long"]   = ti.ema(df["close"], EMA_LARGO)      # EMA 50
        df["ema200"]     = ti.ema(df["close"], 200)             # EMA 200 (solo para logs/macro)
        df["rsi"]        = ti.rsi(df["close"], RSI_PERIOD)
        df["atr"]        = ti.atr(df, ATR_PERIOD)
        df["adx"]        = ti.adx(df, ADX_PERIOD)
        df["volume_sma"] = ti.sma(df["volume"], 20)
        df["bb_mid"], df["bb_upper"], df["bb_lower"] = ti.bollinger_bands(df["close"], std_dev=2.5)
        return df

    def detect_market_regime(self, df: pd.DataFrame) -> Dict:
        """Régimen simplificado: TREND o NO_TRADE."""
        if df is None or len(df) < 30:
            return {"regime": "UNKNOWN", "adx": 0.0, "reason": "Datos insuficientes"}

        last = df.iloc[-1]
        adx_val = last.get("adx", 0.0)
        close = last["close"]
        ema50 = last.get("ema_long", close)

        if adx_val >= ADX_MIN and close > ema50:
            return {"regime": "TREND", "adx": adx_val,
                    "reason": f"Tendencia alcista (ADX={adx_val:.1f})"}
        elif adx_val >= ADX_MIN:
            return {"regime": "TREND_WEAK", "adx": adx_val,
                    "reason": f"Tendencia sin dirección clara (ADX={adx_val:.1f})"}
        else:
            return {"regime": "NO_TRADE", "adx": adx_val,
                    "reason": f"Sin tendencia (ADX={adx_val:.1f})"}

    @staticmethod
    def get_position_size_multiplier(regime: str) -> float:
        """Tamaño de posición: 100% en tendencia, 80% en tendencia débil."""
        return 1.0 if regime == "TREND" else 0.8

    def check_buy_signal(self, df: pd.DataFrame) -> Tuple[bool, Dict]:
        """
        Mean Reversion Scalper: Compra en Pánico Extremo
        Condiciones:
        1. Precio cruza por debajo de la Banda de Bollinger Inferior
        2. RSI < 35 (Sobreventa Extrema)
        """
        if df is None or len(df) < 60:
            return False, {}

        last = df.iloc[-1]
        details = {}

        close_price = last["close"]
        lower_bb = last.get("bb_lower", 0)
        rsi_val = last.get("rsi", 50)
        
        # Condición 1: Pánico (Precio < Lower BB)
        panic_drop = close_price < lower_bb
        
        # Condición 2: Sobreventa (RSI < 35)
        oversold = rsi_val < 35
        
        # Condición 3: Volumen de Capitulación (Volumen > 1.5x SMA)
        vol = last.get("volume", 0)
        vol_sma = last.get("volume_sma", 0)
        vol_climax = vol > (vol_sma * 1.5) if vol_sma > 0 else False
        
        score = sum([panic_drop, oversold, vol_climax])
        
        details["close_price"] = close_price
        details["lower_bb"] = round(lower_bb, 4)
        details["rsi"] = round(rsi_val, 2)
        details["panic_drop"] = panic_drop
        details["oversold"] = oversold
        details["vol_climax"] = vol_climax
        details["score"] = score
        details["min_score"] = 3
        
        regime_info = self.detect_market_regime(df)
        details["regime"] = regime_info["regime"]
        details["regime_desc"] = regime_info["reason"]

        return score >= 3, details

    def calculate_sl_tp(self, entry: float, df: pd.DataFrame):
        """
        SL y TP basados en ATR (configurables desde config.py).
        - SL = entry - SL_ATR_MULT × ATR
        - TP = entry + TP_ATR_MULT × ATR
        - R:R = TP_ATR_MULT / SL_ATR_MULT = 2.0/1.5 = 1.33
        """
        last_row = df.iloc[-1]
        atr = last_row["atr"]

        # Stop Loss
        sl = entry - (SL_ATR_MULT * atr)

        # Protección de volatilidad: SL > MAX_SL_PCT% del entry → rechazar
        sl_distance_pct = (entry - sl) / entry * 100
        if sl_distance_pct > MAX_SL_PCT:
            logger.warning(
                f"Volatilidad excesiva: SL a -{sl_distance_pct:.1f}% del entry "
                f"(ATR={atr:.4f}, max={MAX_SL_PCT}%). Trade RECHAZADO."
            )
            return None, None, atr

        # Take Profit
        tp = entry + (TP_ATR_MULT * atr)

        return sl, tp, atr

    # Alias para compatibilidad con backtest.py
    def calculate_stop_loss_and_tp(self, entry, df, side="BUY"):
        return self.calculate_sl_tp(entry, df)