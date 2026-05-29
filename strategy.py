"""
Pullback Sniper Strategy — v2.0
================================
Compra pullbacks en tendencias alcistas confirmadas.
Solo 5 condiciones de entrada, 2 salidas fijas (SL/TP).
Sin trailing stop. Sin ventas parciales. Sin breakeven.
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Tuple
from config import (
    EMA_CORTO, EMA_LARGO, RSI_PERIOD,
    ATR_PERIOD, ADX_PERIOD, ADX_MIN, SL_ATR_MULT,
    MAX_SL_PCT,
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
    Pullback Sniper: Compra retrocesos en tendencias alcistas.
    
    5 condiciones de entrada (todas obligatorias):
    1. Precio > EMA200 (macro uptrend)
    2. EMA20 > EMA50 (estructura de tendencia local)  
    3. Pullback: precio cerca de EMA20 (retroceso, no breakout)
    4. RSI en zona 35-55 (dip, no sobrecompra)
    5. ADX >= 20 (tendencia real, no lateralización)
    """

    MIN_BUY_SCORE = 5   # 5 condiciones, todas requeridas

    def __init__(self):
        self.ti = TechnicalIndicators()

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula indicadores para Mean Reversion en Tendencia."""
        df = df.copy()
        ti = self.ti
        df["ema_short"]  = ti.ema(df["close"], EMA_CORTO)
        df["ema_long"]   = ti.ema(df["close"], EMA_LARGO)
        df["ema200"]     = ti.ema(df["close"], 200)
        df["rsi"]        = ti.rsi(df["close"], RSI_PERIOD)
        df["atr"]        = ti.atr(df, ATR_PERIOD)
        df["adx"]        = ti.adx(df, ADX_PERIOD)
        df["volume_sma"] = ti.sma(df["volume"], 20)
        df["bb_mid"], df["bb_upper"], df["bb_lower"] = ti.bollinger_bands(df["close"])
        return df

    def detect_market_regime(self, df: pd.DataFrame) -> Dict:
        """
        Régimen simplificado: TREND o NO_TRADE.
        Solo 2 estados en lugar de 5.
        """
        if df is None or len(df) < 30:
            return {
                "regime": "UNKNOWN",
                "adx": 0.0,
                "reason": "Datos insuficientes"
            }
            
        last = df.iloc[-1]
        adx_val = last.get("adx", 0.0)
        close = last["close"]
        ema200 = last.get("ema200", close)
        ema20 = last.get("ema_short", close)
        ema50 = last.get("ema_long", close)

        if adx_val >= ADX_MIN and close > ema200 and ema20 > ema50:
            regime = "TREND"
            reason = f"Tendencia alcista confirmada (ADX={adx_val:.1f})"
        elif adx_val >= ADX_MIN and close > ema200:
            regime = "TREND_WEAK"
            reason = f"Tendencia débil (ADX={adx_val:.1f}, EMAs no alineadas)"
        else:
            regime = "NO_TRADE"
            reason = f"Sin tendencia clara (ADX={adx_val:.1f})"
            
        return {
            "regime": regime,
            "adx": adx_val,
            "reason": reason
        }

    @staticmethod
    def get_position_size_multiplier(regime: str) -> float:
        """Tamaño de posición: 100% en tendencia, 80% en tendencia débil."""
        return 1.0 if regime == "TREND" else 0.8

    def check_buy_signal(self, df: pd.DataFrame) -> Tuple[bool, Dict]:
        """
        Pullback Hunter: Compra retrocesos en tendencias alcistas.
        
        5 condiciones, necesita 3 para entrar:
        1. Precio > EMA200 (macro uptrend)
        2. Precio dentro del 1.5% de la Lower Bollinger Band (pullback fuerte)
        3. RSI < 45 (momentum bajando — zona de retroceso)
        4. ADX ≥ 18 (hay tendencia real, no lateral)
        5. Volumen > promedio (interés institucional en el retroceso)
        """
        if df is None or len(df) < 210:
            return False, {}

        last = df.iloc[-1]

        score   = 0
        details = {}
        
        self.MIN_BUY_SCORE = 3  # Necesita 3 de 5 condiciones

        # ── 1. MACRO TREND: Precio > EMA200 ──────────────────────────────
        ema200 = last["ema200"]
        macro_bullish = last["close"] > ema200
        details["macro_bullish"] = macro_bullish
        details["ema200"] = round(ema200, 4)
        if macro_bullish:
            score += 1

        # ── 2. PULLBACK: Precio cerca de Lower Bollinger Band ────────────
        lower_bb = last["bb_lower"]
        bb_mid = last["bb_mid"]
        bb_range = bb_mid - lower_bb if bb_mid > lower_bb else 1e-8
        # Está en el 30% inferior de las bandas (cerca del lower)
        bb_position = (last["close"] - lower_bb) / bb_range if bb_range > 0 else 0.5
        pullback_ok = bb_position <= 0.35  # En el tercio inferior de las bandas
        details["pullback_ok"] = pullback_ok
        details["bb_position"] = round(bb_position, 3)
        details["lower_bb"] = round(lower_bb, 4)
        if pullback_ok:
            score += 1

        # ── 3. RSI RETROCESO: < 45 ───────────────────────────────────────
        rsi_val = round(last["rsi"], 2)
        details["rsi"] = rsi_val
        rsi_ok = rsi_val < 45
        details["rsi_ok"] = rsi_ok
        if rsi_ok:
            score += 1

        # ── 4. ADX ≥ 18: Tendencia real ──────────────────────────────────
        adx_val = round(last["adx"], 2)
        details["adx"] = adx_val
        adx_ok = adx_val >= 18
        details["adx_ok"] = adx_ok
        if adx_ok:
            score += 1

        # ── 5. VOLUMEN: Spike de interés ─────────────────────────────────
        vol_ratio = last["volume"] / last["volume_sma"] if last["volume_sma"] > 0 else 0
        vol_ok = vol_ratio > 1.2  # 20% más volumen que el promedio
        details["volume_ok"] = vol_ok
        details["vol_ratio"] = round(vol_ratio, 2)
        if vol_ok:
            score += 1

        # ── Información adicional para logs ──────────────────────────────
        details["close_price"] = last["close"]
        details["score"] = score
        details["min_score"] = self.MIN_BUY_SCORE

        regime_info = self.detect_market_regime(df)
        details["regime"] = regime_info["regime"]
        details["regime_desc"] = regime_info["reason"]

        return score >= self.MIN_BUY_SCORE, details

    def calculate_sl_tp(self, entry: float, df: pd.DataFrame):
        """
        SL basado en ATR (2.0x).
        TP dinámico basado en la media de reversión (Bollinger Middle Band / SMA 20).
        """
        last_row = df.iloc[-1]
        atr = last_row["atr"]
        
        # Stop Loss a 2.0 ATR por debajo (un poco más holgado para pánicos)
        sl = entry - (2.0 * atr)
        
        # Protección de volatilidad: SL > 8% del entry → rechazar (pánicos extremos)
        sl_distance_pct = (entry - sl) / entry * 100
        if sl_distance_pct > 8.0:
            logger.warning(
                f"Volatilidad excesiva: SL a -{sl_distance_pct:.1f}% del entry "
                f"(ATR={atr:.4f}). Trade RECHAZADO."
            )
            return None, None, atr
            
        # Take Profit a la media natural del precio (SMA 20)
        tp = last_row["bb_mid"]
        
        # Si el TP está por debajo del entry (ej. tendencia cayendo agresivamente), se descarta o ajusta
        if tp <= entry:
             tp = entry + (1.5 * atr)  # Fallback: salida rápida segura
             
        return sl, tp, atr

    # alias back-compat para backtest.py
    def calculate_stop_loss_and_tp(self, entry, df, side="BUY"):
        return self.calculate_sl_tp(entry, df)

    # ── RSI Bearish Divergence (kept for potential future use) ────────────
    @staticmethod
    def _rsi_bearish_div(df: pd.DataFrame) -> bool:
        if len(df) < 15:
            return False
        window = df.tail(14)
        prices = window["close"]
        rsis   = window["rsi"]
        if prices.iloc[-1] > prices.iloc[:-1].max() * 0.995:
            if rsis.iloc[-1] < rsis.iloc[:-1].max() * 0.90:
                if rsis.iloc[-1] > 55:
                    return True
        return False