"""
Momentum Dip Buyer Strategy — v4.1
====================================
Compra pullbacks a EMA20 en tendencias alcistas confirmadas.
4 condiciones de entrada, necesita MIN_BUY_SCORE (default 3).
Salidas con SL/TP dinámicos según volatilidad + breakeven + trailing.
RiskManager con Kelly fraccional + position sizing por ATR.
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, List
import config
from config import (
    EMA_CORTO, EMA_LARGO, RSI_PERIOD,
    ATR_PERIOD, ADX_PERIOD, ADX_MIN,
    MAX_SL_PCT, TRAILING_ACTIVATE_ATR,
    TRAILING_STEP_ATR, TRAILING_SL_OFFSET_ATR,
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
    def bollinger(series: pd.Series, period: int = 20, std_dev: float = 2.0):
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return upper, sma, lower

    @staticmethod
    def stochastic(df: pd.DataFrame, period: int = 14, smooth_k: int = 3, smooth_d: int = 3):
        """Stochastic Oscillator (%K y %D)."""
        h = df["high"].rolling(period).max()
        l = df["low"].rolling(period).min()
        k = 100 * (df["close"] - l) / (h - l).replace(0, np.nan)
        k = k.rolling(smooth_k).mean()
        d = k.rolling(smooth_d).mean()
        return k, d


class StrategySignals:
    """
    Momentum Dip Buyer: compra retrocesos a EMA20 en tendencias alcistas.

    4 condiciones (MIN_BUY_SCORE requeridas, default 3):
    1. Precio > EMA50 (tendencia alcista)
    2. Precio cerca de EMA20 (pullback al soporte dinámico)
    3. RSI en zona de retroceso (35–52)
    4. ADX >= ADX_MIN (tendencia real, no lateral)
    """

    def __init__(self):
        self.ti = TechnicalIndicators()

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula todos los indicadores necesarios (incluyendo MACD, BB, Stoch, ATR_SMA)."""
        df = df.copy()
        ti = self.ti
        df["ema_short"]  = ti.ema(df["close"], EMA_CORTO)
        df["ema_long"]   = ti.ema(df["close"], EMA_LARGO)
        df["ema200"]     = ti.ema(df["close"], 200)
        df["ema9"]       = ti.ema(df["close"], 9)
        df["ema21"]      = ti.ema(df["close"], 21)
        df["rsi"]        = ti.rsi(df["close"], RSI_PERIOD)
        df["atr"]        = ti.atr(df, ATR_PERIOD)
        df["adx"]        = ti.adx(df, ADX_PERIOD)
        df["volume_sma"] = ti.sma(df["volume"], 20)

        # MACD
        df["macd"], df["macd_signal"], df["macd_hist"] = ti.macd(df["close"])

        # Bollinger Bands
        df["bb_upper"], df["bb_mid"], df["bb_lower"] = ti.bollinger(df["close"])

        # Stochastic
        df["stoch_k"], df["stoch_d"] = ti.stochastic(df)

        # ATR SMA 20 (para medir volatilidad relativa)
        df["atr_sma_20"] = ti.sma(df["atr"], 20)

        return df

    def detect_market_regime(self, df: pd.DataFrame) -> Dict:
        """
        Régimen de mercado mejorado con scoring.
        Retorna dict con regime, min_score, adx, reason.
        """
        if df is None or len(df) < 30:
            return {"regime": "UNKNOWN", "adx": 0.0, "min_score": 9, "reason": "Datos insuficientes"}

        last = df.iloc[-1]
        close = last["close"]
        ema20 = last.get("ema_short", close)
        ema50 = last.get("ema_long", close)
        ema200 = last.get("ema200", close)
        adx_val = last.get("adx", 0.0)
        rsi_val = last.get("rsi", 50)
        macd_hist = last.get("macd_hist", 0)
        volume = last.get("volume", 0)
        vol_sma = last.get("volume_sma", volume)

        # Condiciones
        above_ema50 = close > ema50
        above_ema200 = close > ema200
        ema_bullish = ema20 > ema50
        macd_positive = macd_hist > 0
        volume_confirm = volume > vol_sma * 0.8
        rsi_mid = 30 <= rsi_val <= 70

        score = sum([above_ema50, above_ema200, ema_bullish, macd_positive, volume_confirm, rsi_mid])

        if adx_val >= ADX_MIN and above_ema50 and above_ema200:
            if score >= 5:
                regime = "TREND_STRONG_BULL"
                min_score = 7
                reason = f"🔥 Tendencia alcista FUERTE (score={score}/6, ADX={adx_val:.1f})"
            elif score >= 4:
                regime = "TREND_BULL"
                min_score = 7
                reason = f"✓ Tendencia alcista (score={score}/6, ADX={adx_val:.1f})"
            else:
                regime = "TREND_WEAK"
                min_score = 8
                reason = f"⚠️ Tendencia débil (score={score}/6, ADX={adx_val:.1f})"
        elif adx_val >= ADX_MIN and not above_ema50:
            regime = "TREND_WEAK"
            min_score = 9
            reason = f"⚠️ Tendencia bajista con ADX alto (score={score}/6, ADX={adx_val:.1f})"
        elif adx_val < ADX_MIN and rsi_val > 40 and rsi_val < 60:
            regime = "CHOPPY"
            min_score = 9
            reason = f"🌀 Mercado lateral sin tendencia (ADX={adx_val:.1f}, RSI={rsi_val:.1f})"
        elif adx_val < ADX_MIN:
            regime = "RANGE_VOLATILE"
            min_score = 9
            reason = f"🌀 Sin tendencia definida (ADX={adx_val:.1f})"
        else:
            regime = "NORMAL"
            min_score = 8
            reason = f"Régimen normal (score={score}/6)"

        return {"regime": regime, "adx": adx_val, "min_score": min_score, "reason": reason}

    @staticmethod
    def get_position_size_multiplier(regime: str) -> float:
        """Tamaño de posición según régimen."""
        multipliers = {
            "TREND_STRONG_BULL": 1.0,
            "TREND_BULL": 1.0,
            "TREND_WEAK": 0.7,
            "CHOPPY": 0.5,
            "RANGE_VOLATILE": 0.0,  # No operar en mercados erráticos
            "NORMAL": 0.8,
            "UNKNOWN": 0.0,
        }
        return multipliers.get(regime, 0.5)

    def check_buy_signal(self, df: pd.DataFrame) -> Tuple[bool, Dict]:
        """Estrategia de Tendencia: Cruce EMA9 > EMA21 + MACD + Price > EMA200"""
        if df is None or len(df) < 60:
            return False, {}

        last = df.iloc[-1]
        prev = df.iloc[-2]
        close_price = last["close"]
        ema200 = last.get("ema200", close_price)
        ema9 = last.get("ema9", close_price)
        ema21 = last.get("ema21", close_price)
        prev_ema9 = prev.get("ema9", prev["close"])
        prev_ema21 = prev.get("ema21", prev["close"])
        
        macd = last.get("macd", 0)
        macd_signal = last.get("macd_signal", 0)
        
        rsi_val = last.get("rsi", 50)
        adx_val = last.get("adx", 0)

        # Condiciones de la estrategia optimizada
        above_ema200 = bool(close_price > ema200)
        cruce_emas = bool(ema9 > ema21 and prev_ema9 <= prev_ema21)
        macd_bullish = bool(macd > macd_signal)
        
        # Filtro opcional: ADX para confirmar tendencia
        trend_strength = bool(adx_val >= ADX_MIN)

        # Se requiere cruce y macd alcista por encima de EMA200
        is_buy = above_ema200 and cruce_emas and macd_bullish

        score = sum([above_ema200, cruce_emas, macd_bullish, trend_strength])

        details = {
            "close_price": close_price,
            "ema9": round(ema9, 4),
            "ema21": round(ema21, 4),
            "ema200": round(ema200, 4),
            "rsi": round(rsi_val, 2),
            "adx": round(adx_val, 2),
            "above_ema200": above_ema200,
            "cruce_emas": cruce_emas,
            "macd_bullish": macd_bullish,
            "trend_strength": trend_strength,
            "score": score,
            "min_score": 3, # Se requieren 3 condiciones base (EMA200, Cruce, MACD)
        }

        regime_info = self.detect_market_regime(df)
        details["regime"] = regime_info["regime"]
        details["regime_desc"] = regime_info["reason"]
        details["macro_bullish"] = above_ema200

        return is_buy, details

    def exit_score(self, df: pd.DataFrame) -> Tuple[int, str]:
        """
        Evalúa si hay razones para salir (scoring de salida).
        Retorna (score, razón).
        Score bajo = debe salir.
        """
        if df is None or len(df) < 20:
            return 0, "Datos insuficientes"

        last = df.iloc[-1]
        close = last["close"]
        ema20 = last.get("ema_short", close)
        ema50 = last.get("ema_long", close)
        rsi = last.get("rsi", 50)
        adx = last.get("adx", 0)

        # Condiciones de salida (invertidas: True = malo)
        below_ema20 = close < ema20
        rsi_overbought = rsi > 75
        rsi_div_neg = self._rsi_bearish_div(df)
        adx_falling = adx < 20

        exit_score = sum([below_ema20, rsi_overbought, rsi_div_neg, adx_falling])

        if exit_score >= 3:
            return -2, f"🚨 Señal de salida fuerte (score={exit_score}/4)"
        elif exit_score >= 2:
            return -1, f"⚠️ Señal de salida moderada (score={exit_score}/4)"
        else:
            return 0, f"Sin señal de salida (score={exit_score}/4)"

    def _rsi_bearish_div(self, df: pd.DataFrame, window: int = 14) -> bool:
        """
        Detecta divergencia bajista RSI: precio hace nuevo máximo pero RSI no.
        Retorna bool (True = hay divergencia bajista).
        """
        if len(df) < window * 2:
            return False
        recent = df.tail(window * 2)
        price_high_idx = recent["close"].idxmax()
        rsi_high_idx = recent["rsi"].idxmax()
        # Divergencia: precio máximo en posición más reciente que RSI máximo
        return bool(price_high_idx > rsi_high_idx)

    def calcular_niveles_fibonacci(self, df: pd.DataFrame, lookback: int = 50) -> Dict:
        """Calcula niveles de Fibonacci para el rango reciente."""
        if df is None or len(df) < lookback:
            return {}
        segment = df.tail(lookback)
        swing_high = segment["high"].max()
        swing_low = segment["low"].min()
        diff = swing_high - swing_low
        if diff == 0:
            return {}
        return {
            "swing_high": swing_high,
            "swing_low": swing_low,
            "fib_236": swing_high - 0.236 * diff,
            "fib_382": swing_high - 0.382 * diff,
            "fib_500": swing_high - 0.5 * diff,
            "fib_618": swing_high - 0.618 * diff,
            "fib_786": swing_high - 0.786 * diff,
            "fib_ext_1272": swing_high + 0.272 * diff,
            "fib_ext_1618": swing_high + 0.618 * diff,
        }

    def calculate_sl_tp(self, entry: float, df: pd.DataFrame):
        """
        SL y TP DINÁMICOS según volatilidad (ATR percentil).
        R:R se adapta automáticamente.
        """
        last_row = df.iloc[-1]
        atr = last_row["atr"]
        atr_sma_20 = last_row.get("atr_sma_20", atr)

        # Determinar volatilidad relativa
        if atr_sma_20 > 0:
            atr_ratio = atr / atr_sma_20
        else:
            atr_ratio = 1.0

        # ATR percentil estimado basado en ratio vs SMA20
        # < 0.7 = baja volatilidad, > 1.3 = alta volatilidad
        if atr_ratio < 0.7:
            # Baja volatilidad: SL más tight, TP ajustado
            sl_mult = 1.5
            tp_mult = 3.5
            rr = tp_mult / sl_mult  # 2.33
        elif atr_ratio > 1.3:
            # Alta volatilidad: SL más amplio para no ser sacado por ruido
            sl_mult = 3.0
            tp_mult = 6.0
            rr = tp_mult / sl_mult  # 2.0
        else:
            # Volatilidad normal
            sl_mult = config.SL_ATR_MULT
            tp_mult = config.TP_ATR_MULT
            rr = tp_mult / sl_mult  # ~1.82

        sl = entry - (sl_mult * atr)
        sl_distance_pct = (entry - sl) / entry * 100

        if sl_distance_pct > MAX_SL_PCT:
            logger.warning(
                f"Volatilidad excesiva: SL a -{sl_distance_pct:.1f}% del entry "
                f"(ATR={atr:.4f}, atr_ratio={atr_ratio:.2f}, max={MAX_SL_PCT}%). Trade RECHAZADO."
            )
            return None, None, atr, sl_mult, tp_mult, rr

        tp = entry + (tp_mult * atr)

        logger.debug(
            f"SL/TP dinámico: atr_ratio={atr_ratio:.2f}, "
            f"SL={sl_mult:.1f}×ATR, TP={tp_mult:.1f}×ATR, R:R={rr:.2f}"
        )

        return sl, tp, atr, sl_mult, tp_mult, rr

    def calculate_stop_loss_and_tp(self, entry, df, side="BUY"):
        return self.calculate_sl_tp(entry, df)


class RiskManager:
    """
    Gestión de riesgo avanzada:
    - Position sizing basado en ATR (riesgo por trade)
    - Kelly Criterion fraccional
    - Protección de capital
    """

    @staticmethod
    def position_size(capital: float, entry: float, stop_loss: float,
                      risk_per_trade: float = 0.02) -> float:
        """
        Calcula cantidad de unidades basado en riesgo fijo.
        risk_per_trade = fracción del capital a arriesgar (ej: 0.02 = 2%).
        """
        if stop_loss >= entry:
            return 0.0
        risk_per_unit = entry - stop_loss
        if risk_per_unit <= 0:
            return 0.0
        risk_amount = capital * risk_per_trade
        return risk_amount / risk_per_unit

    @staticmethod
    def calculate_kelly_risk(symbol_stats: Dict, default_risk: float = 0.02) -> float:
        """
        Calcula el riesgo óptimo según Kelly Criterion fraccional.
        Retorna fracción de capital a arriesgar (ej: 0.02 = 2%).
        Clampeada entre 1% y 4%.
        """
        total = symbol_stats.get("total_trades", 0)
        if total < 5:
            return default_risk

        wr = symbol_stats.get("win_rate", 0.5)
        wl_ratio = symbol_stats.get("win_loss_ratio", 1.0)

        if wl_ratio <= 0:
            return default_risk

        # Kelly completo: f* = (p * (b+1) - 1) / b
        # donde p = win_rate, b = win_loss_ratio (avg_win/avg_loss)
        kelly = (wr * (wl_ratio + 1) - 1) / wl_ratio

        # Kelly fraccional (25% para ser conservador)
        kelly_fractional = kelly * 0.25

        # Clampear entre 1% y 4%
        return max(0.01, min(0.04, kelly_fractional))

    @staticmethod
    def max_daily_loss(capital: float, max_loss_pct: float = 0.02) -> float:
        """Pérdida máxima diaria en USD."""
        return capital * max_loss_pct


class TrailingStopManager:
    """
    Gestión de trailing stops y salidas parciales.
    """

    @staticmethod
    def update_trailing_stop(
        entry_price: float,
        current_price: float,
        current_atr: float,
        max_price: float,
        initial_sl: float,
        trailing_atr_mult: float = 2.0,
        breakeven_pct: float = 1.0,
        trailing_step_atr: float = 0.8,
        trailing_sl_offset_atr: float = 1.0,
    ) -> Dict:
        """
        Actualiza trailing stop dinámico.
        Retorna dict con new_sl, breakeven_active, trailing_active.
        """
        result = {
            "new_sl": initial_sl,
            "breakeven_active": False,
            "trailing_active": False,
        }

        # 1. Breakeven
        if current_price >= entry_price * (1 + breakeven_pct / 100):
            result["new_sl"] = max(result["new_sl"], entry_price)
            result["breakeven_active"] = True

        # 2. Trailing
        if current_atr > 0:
            activate_level = entry_price + (trailing_atr_mult * current_atr)
            if current_price >= activate_level:
                result["trailing_active"] = True
                target_sl = max_price - (trailing_sl_offset_atr * current_atr)
                # Solo mover hacia arriba
                if target_sl > result["new_sl"]:
                    result["new_sl"] = target_sl

        return result

    @staticmethod
    def calculate_partial_exit(
        entry_price: float,
        current_price: float,
        total_quantity: float,
        profit_target_pct: float = 2.5,
    ) -> Dict:
        """
        Calcula si se debe hacer un cierre parcial (50%).
        Retorna dict con should_exit_partial y exit_quantity.
        """
        gain_pct = (current_price / entry_price - 1) * 100
        if gain_pct >= profit_target_pct:
            return {
                "should_exit_partial": True,
                "exit_quantity": total_quantity * 0.5,
                "reason": f"Partial exit at +{gain_pct:.2f}%",
            }
        return {
            "should_exit_partial": False,
            "exit_quantity": 0,
            "reason": f"Gain {gain_pct:.2f}% < target {profit_target_pct}%",
        }