import logging
import pandas as pd
import numpy as np
from typing import Dict, Tuple
from config import (
    EMA_CORTO, EMA_LARGO, RSI_PERIOD, RSI_MIN, RSI_MAX,
    ATR_PERIOD, ADX_PERIOD, ADX_MIN, SL_ATR_MULT, TP_ATR_MULT,
    FIBONACCI_PERIOD, FIBONACCI_BOUNCE_PCT, FIBONACCI_EXT_TP, FIBONACCI_REQUIRE_IN_WEAK,
    POSITION_SIZE_TRENDING, POSITION_SIZE_RANGING,
    POSITION_SIZE_VOLATILE, POSITION_SIZE_UNCERTAIN,
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
    def stochastic(df: pd.DataFrame, period: int = 14):
        lo = df["low"].rolling(period).min()
        hi = df["high"].rolling(period).max()
        k  = 100 * (df["close"] - lo) / (hi - lo).replace(0, np.nan)
        return k, k.rolling(3).mean()

    @staticmethod
    def bollinger(series: pd.Series, period: int = 20, std: float = 2.0):
        mid   = series.rolling(period).mean()
        sigma = series.rolling(period).std()
        return mid + std * sigma, mid, mid - std * sigma


class StrategySignals:
    """
    Señales basadas en puntuación + filtro macro EMA200.
    """

    MIN_BUY_SCORE  = 6  # Bajado a 6 para permitir mayor frecuencia de trades (3-6 al día)
    MIN_SELL_SCORE = 3  # Bajado a 3 para cierres oportunos

    def __init__(self):
        self.ti = TechnicalIndicators()

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        ti = self.ti
        df["ema_short"]  = ti.ema(df["close"], EMA_CORTO)
        df["ema_long"]   = ti.ema(df["close"], EMA_LARGO)
        df["ema200"]     = ti.ema(df["close"], 200)          # Filtro macro
        df["rsi"]        = ti.rsi(df["close"], RSI_PERIOD)
        df["atr"]        = ti.atr(df, ATR_PERIOD)
        df["adx"]        = ti.adx(df, ADX_PERIOD)
        df["macd"], df["macd_signal"], df["macd_hist"] = ti.macd(df["close"])
        df["stoch_k"], df["stoch_d"] = ti.stochastic(df)
        df["volume_sma"] = ti.sma(df["volume"], 20)
        df["bb_upper"], df["bb_mid"], df["bb_lower"] = ti.bollinger(df["close"])
        df["atr_sma_20"] = df["atr"].rolling(20).mean()      # Precalculado para optimizar rendimiento
        return df

    def detect_market_regime(self, df: pd.DataFrame) -> Dict:
        """
        Detecta el régimen del mercado (1H) analizando ADX, ATR y Volumen.
        Devuelve un diccionario con el tipo de régimen y sugerencia de score mínimo.
        """
        if df is None or len(df) < 30:
            return {
                "regime": "UNKNOWN",
                "min_score": self.MIN_BUY_SCORE,
                "adx": 0.0,
                "reason": "Insuficientes datos"
            }
            
        last = df.iloc[-1]
        adx_val = last.get("adx", 0.0)
        close = last["close"]
        ema200 = last.get("ema200", close)
        ema20 = last.get("ema_short", close)
        ema50 = last.get("ema_long", close)
        volume = last.get("volume", 0.0)
        volume_sma = last.get("volume_sma", volume)
        atr = last.get("atr", 0.0)
        
        # Calcular ATR promedio reciente (usar precalculado si existe)
        atr_sma = last.get("atr_sma_20", atr)
        if pd.isna(atr_sma):
            atr_sma = atr
        
        # Clasificación de régimen
        if adx_val >= 25 and close > ema200 and ema20 > ema50:
            regime = "TREND_STRONG_BULL"
            min_score = 6  # Excelente tendencia, entradas muy fluidas
            reason = f"Tendencia alcista fuerte (ADX={adx_val:.1f})"
        elif adx_val >= 20 and (close > ema200 or ema20 > ema50):
            regime = "TREND_WEAK"
            min_score = 7  # Tendencia en desarrollo, buena frecuencia
            reason = f"Tendencia alcista moderada/débil (ADX={adx_val:.1f})"
        elif adx_val < 20:
            if volume > volume_sma and atr > atr_sma:
                regime = "RANGE_VOLATILE"
                min_score = 7  # Rango volátil
                reason = "Mercado en rango con volatilidad alta"
            else:
                regime = "CHOPPY"
                min_score = 8  # Lateral picado, exige buena señal pero no imposible
                reason = "Mercado lateral / consolidación de bajo volumen (Chop)"
        else:
            regime = "NORMAL"
            min_score = 7
            reason = "Condiciones normales de mercado"
            
        return {
            "regime": regime,
            "min_score": min_score,
            "adx": adx_val,
            "reason": reason
        }

    @staticmethod
    def get_position_size_multiplier(regime: str) -> float:
        mapping = {
            "TREND_STRONG_BULL": POSITION_SIZE_TRENDING,
            "TREND_BULL":        POSITION_SIZE_TRENDING,
            "TREND_WEAK":        POSITION_SIZE_TRENDING * 0.8,
            "RANGE_VOLATILE":    POSITION_SIZE_VOLATILE,
            "CHOPPY":            POSITION_SIZE_RANGING,
            "NORMAL":            POSITION_SIZE_UNCERTAIN,
            "UNKNOWN":           POSITION_SIZE_UNCERTAIN,
        }
        return mapping.get(regime, POSITION_SIZE_UNCERTAIN)

    @staticmethod
    def calcular_niveles_fibonacci(df: pd.DataFrame, period: int = FIBONACCI_PERIOD) -> dict:
        if df is None or df.empty or len(df) < period:
            logger.warning("DataFrame vacío o insuficiente para calcular Fibonacci.")
            return {}
        if not all(col in df.columns for col in ["high", "low"]):
            logger.warning("Faltan las columnas 'high' o 'low' en el DataFrame.")
            return {}
        bloque_reciente = df.tail(period)
        maximo = bloque_reciente["high"].max()
        minimo = bloque_reciente["low"].min()
        distancia = maximo - minimo
        if distancia == 0:
            return {}
        return {
            "swing_high": maximo,
            "swing_low": minimo,
            "fib_236": maximo - (distancia * 0.236),
            "fib_382": maximo - (distancia * 0.382),
            "fib_500": maximo - (distancia * 0.500),
            "fib_618": maximo - (distancia * 0.618),
            "fib_786": maximo - (distancia * 0.786),
            "fib_ext_1272": maximo + (distancia * 0.272),
            "fib_ext_1618": maximo + (distancia * 0.618),
        }

    def check_buy_signal(self, df: pd.DataFrame) -> Tuple[bool, Dict]:
        if df is None or len(df) < 60:
            return False, {}

        last = df.iloc[-1]
        prev = df.iloc[-2]

        score   = 0
        details = {}

        # ── FILTRO MACRO (hard block) ──────────────────────────────────────
        macro_bullish = last["close"] > last["ema200"]
        details["macro_bullish"] = macro_bullish
        details["ema200"] = round(last["ema200"], 2)

        # Margen significativo sobre EMA200 (evita entradas marginales)
        ema200_margin_pct = (last["close"] / last["ema200"] - 1) * 100 if last["ema200"] > 0 else 0
        details["ema200_margin_pct"] = round(ema200_margin_pct, 2)
        macro_margin_ok = ema200_margin_pct >= 0.5  # Al menos 0.5% arriba de EMA200 (relajado de 1%)

        # ── Puntuación ────────────────────────────────────────────────────
        # 1. EMA20 > EMA50 (+2 pts)
        ema_trend = last["ema_short"] > last["ema_long"]
        details["ema_trend"] = ema_trend
        if ema_trend:
            score += 2

        # 2. Precio sobre EMA20 (+1 pt)
        price_ok = last["close"] > last["ema_short"]
        details["price_above_ema"] = price_ok
        if price_ok:
            score += 1

        # 3. RSI momentum sin sobrecompra (+2 pts)
        rsi_val = round(last["rsi"], 2)
        details["rsi"] = rsi_val
        rsi_ok = RSI_MIN <= rsi_val <= RSI_MAX
        details["rsi_ok"] = rsi_ok
        if rsi_ok:
            score += 2

        # 4. Volumen elevado (+1 pt)
        vol_ok = last["volume"] > last["volume_sma"]
        details["volume_ok"] = vol_ok
        if vol_ok:
            score += 1

        # 5. ADX — tendencia fuerte (+1 pt)
        adx_val = round(last["adx"], 2)
        details["adx"] = adx_val
        adx_ok = adx_val >= ADX_MIN
        details["adx_ok"] = adx_ok
        if adx_ok:
            score += 1

        # 6. MACD por encima de señal (+1 pt)
        macd_ok = last["macd"] > last["macd_signal"]
        details["macd_bullish"] = macd_ok
        if macd_ok:
            score += 1

        # 7. Histograma MACD creciendo (+1 pt)
        hist_ok = last["macd_hist"] > prev["macd_hist"]
        details["macd_hist_growing"] = hist_ok
        if hist_ok:
            score += 1

        # 8. Estocástico no sobrecomprado (+1 pt)
        stoch_ok = last["stoch_k"] < 80
        details["stoch_ok"] = stoch_ok
        details["stoch_k"] = round(last["stoch_k"], 2)
        if stoch_ok:
            score += 1

        # 9. Rebote local / Buy the dip (+2 pts)
        bb_bounce = last["close"] <= last["bb_lower"] * 1.01
        details["bb_bounce"] = bb_bounce
        if bb_bounce:
            score += 2

        # 10. ATR en expansión — momentum acelerando (+1 pt)
        atr_expanding = last["atr"] > prev["atr"]
        details["atr_expanding"] = atr_expanding
        if atr_expanding:
            score += 1

        # 11. Fibonacci — soporte en retroceso 0.5 o 0.618 (+2 pts)
        fib_levels = self.calcular_niveles_fibonacci(df, FIBONACCI_PERIOD)
        fib_bounce = False
        fib_near_618 = False
        if fib_levels:
            close = last["close"]
            fib_618 = fib_levels["fib_618"]
            fib_500 = fib_levels["fib_500"]
            swing_low = fib_levels["swing_low"]
            swing_high = fib_levels["swing_high"]
            details["fib_618"] = round(fib_618, 4)
            details["fib_500"] = round(fib_500, 4)
            details["fib_swing_high"] = round(swing_high, 4)
            details["fib_swing_low"] = round(swing_low, 4)
            bounce_pct = FIBONACCI_BOUNCE_PCT / 100
            fib_near_618 = abs(close - fib_618) / fib_618 < bounce_pct
            fib_near_500 = abs(close - fib_500) / fib_500 < bounce_pct
            fib_bounce = fib_near_618 or fib_near_500
            details["fib_bounce"] = fib_bounce
            if fib_bounce:
                score += 2
                logger.debug(f"Fibonacci support bounce detectado (cerca de {'0.618' if fib_near_618 else '0.5'})")

        # 12. Fibonacci — precio entre 0.382 y 0.5 (zona neutral-bullish, +1 pt)
        fib_mid_zone = False
        if fib_levels and not fib_bounce:
            close = last["close"]
            fib_382 = fib_levels["fib_382"]
            fib_500 = fib_levels["fib_500"]
            fib_mid_zone = fib_382 <= close <= fib_500
            details["fib_mid_zone"] = fib_mid_zone
            if fib_mid_zone:
                score += 1

        regime_info = self.detect_market_regime(df)
        min_score = regime_info["min_score"]

        details["score"]     = score
        details["min_score"] = min_score
        details["regime"]    = regime_info["regime"]
        details["regime_desc"] = regime_info["reason"]

        # Hard blocks: cualquiera cancela la señal aunque el score sea suficiente
        hard_block = (
            not macro_bullish       # precio bajo EMA200 → downtrend macro (CRÍTICO)
            or not ema_trend        # sin tendencia local (CRÍTICO)
            or not macro_margin_ok  # precio apenas por encima de EMA200 (margen <1%)
        )

        # Hard block adicional: en CHOPPY o RANGE_VOLATILE, exigir soporte Fibonacci
        if not hard_block and FIBONACCI_REQUIRE_IN_WEAK:
            regime = regime_info.get("regime", "NORMAL")
            if regime in ("CHOPPY", "RANGE_VOLATILE") and fib_levels and not fib_bounce:
                hard_block = True
                details["fib_block"] = True

        return (score >= min_score and not hard_block), details

    def calculate_sl_tp(self, entry: float, df: pd.DataFrame):
        atr = df.iloc[-1]["atr"]
        sl = entry - SL_ATR_MULT * atr
        
        # PROTECCIÓN DE VOLATILIDAD: Si el SL natural (ATR) es > 4% del precio de entrada,
        # la moneda está demasiado volátil. Retornamos None en sl para que el llamante rechace el trade.
        # NO usamos un cap artificial (eso rompe el R:R). Mejor no entrar.
        sl_distance_pct = (entry - sl) / entry * 100
        if sl_distance_pct > 4.0:
            logger.warning(
                f"Volatilidad excesiva detectada: SL natural a -{sl_distance_pct:.1f}% del entry "
                f"(ATR={atr:.4f}). Trade RECHAZADO para proteger el R:R."
            )
            return None, None, atr
            
        tp_atr = entry + TP_ATR_MULT * atr
        fib_levels = self.calcular_niveles_fibonacci(df, FIBONACCI_PERIOD)
        tp_fib = fib_levels.get("fib_ext_1272", tp_atr) if fib_levels else tp_atr
        tp = max(tp_atr, tp_fib)
        return sl, tp, atr

    # alias back-compat para backtest.py
    def calculate_stop_loss_and_tp(self, entry, df, side="BUY"):
        return self.calculate_sl_tp(entry, df)

    def exit_score(self, df: pd.DataFrame) -> Tuple[int, str]:
        if len(df) < 3:
            return 0, ""
        last, prev = df.iloc[-1], df.iloc[-2]
        score, reason = 0, []

        if self._rsi_bearish_div(df):
            score += 2; reason.append("RSI Divergence")
        if prev["macd"] > prev["macd_signal"] and last["macd"] < last["macd_signal"]:
            score += 2; reason.append("MACD Bear Cross")
        if prev["stoch_k"] > 75 and last["stoch_k"] < last["stoch_d"]:
            score += 1; reason.append("Stoch Exit")
        if last["rsi"] > 78:
            score += 1; reason.append("RSI Overbought")
        if last["adx"] < 15:
            score += 1; reason.append("Trend Collapse")
        if last["close"] >= last["bb_upper"]:
            score += 1; reason.append("BB Upper")

        # ── Fibonacci Resistance ───────────────────────────────────────────
        fib_levels = self.calcular_niveles_fibonacci(df, FIBONACCI_PERIOD)
        if fib_levels:
            close = last["close"]
            swing_high = fib_levels["swing_high"]
            fib_236 = fib_levels["fib_236"]
            # Precio cerca del swing high o fib 0.236 (zona de resistencia)
            if close >= swing_high * 0.99:
                score += 1; reason.append("Fibonacci Swing High")
            elif close >= fib_236 * 0.995 and close <= fib_236 * 1.005:
                score += 1; reason.append("Fibonacci 0.236 Resistance")

        # ── AJUSTE DEL ESCUDO ADX (MEJORADO) ────────────────────────────────
        # Solo aplica el escudo si:
        # 1. La tendencia es fuerte (ADX > 35)
        # 2. El momentum está intacto (RSI > 55)
        # 3. PERO SOLO si ya hay señales de salida (score > 0)
        # 
        # Lógica: En uptrends fuertes con RSI alto, los "ruidos" de salida (pequeños
        # pullbacks) no son razón para cerrar. El escudo reduce el score de salida.
        if last["adx"] > 35 and last["rsi"] > 55 and score > 1:  # score > 1 (no puntos aislados)
            score -= 2
            reason.append("ADX Shield (Ignoring Noise)")

        return score, " + ".join(reason)

    def _rsi_bearish_div(self, df, window=14):
        """
        Detecta divergencia bearish del RSI:
        - Precio hace un nuevo high (o MUY cercano: 0.5%)
        - RSI no confirma → hace un lower high significativo (10%+)
        - RSI > 60 → confirmación de momentum fuerte (pero debilitándose)
        
        Window = 14 candles (típico)
        NOTA: Sensibilidad REDUCIDA para evitar falsas señales en uptrends.
        """
        if len(df) < window + 5:
            return False
        
        recent = df.iloc[-window:]
        last = df.iloc[-1]
        
        # Precio en máximo o MUY cerca (últimas 14 velas) — endurecido de 2% a 0.5%
        price_high = recent["close"].max()
        price_is_high = last["close"] > price_high * 0.995  # Dentro del 0.5% del máximo
        
        # RSI no confirma el nuevo high — endurecido de 5% a 10%
        rsi_high = recent["rsi"].max()
        rsi_is_lower = last["rsi"] < rsi_high * 0.90  # RSI 10% debajo del máximo
        
        # RSI sigue siendo fuerte (momentum todavía existe)
        rsi_strong = last["rsi"] > 55
        
        # Divergencia confirmada
        return price_is_high and rsi_is_lower and rsi_strong


class RiskManager:

    @staticmethod
    def position_size(capital, entry, stop_loss, risk_pct=0.01):
        diff = abs(entry - stop_loss)
        return 0.0 if diff == 0 else (capital * risk_pct) / diff

    # aliases
    @staticmethod
    def calculate_position_size(capital, entry_price, stop_loss, risk_percent=0.01):
        return RiskManager.position_size(capital, entry_price, stop_loss, risk_percent)

    @staticmethod
    def validate_trade(qty, entry, available, min_notional=11.0):
        notional = qty * entry
        if notional < min_notional:
            return False, f"Notional ${notional:.2f} < mínimo ${min_notional}"
        if notional > available * 0.95:
            return False, f"Saldo insuficiente"
        return True, "OK"

    @staticmethod
    def calculate_kelly_risk(symbol_stats: Dict, default_risk: float = 0.02) -> float:
        """
        Calcula el riesgo sugerido por trade usando el Criterio de Kelly Fraccionario (20% Kelly).
        Estadísticas requeridas:
          - win_rate: float (de 0.0 a 1.0)
          - win_loss_ratio: float (promedio ganancia / promedio pérdida)
          - total_trades: int
        Clampa el riesgo resultante entre 1.0% (0.01) y 4.0% (0.04) por seguridad.
        Si hay menos de 5 trades históricos para el símbolo, se usa default_risk.
        """
        total_trades = symbol_stats.get("total_trades", 0)
        if total_trades < 5:
            return default_risk
            
        win_rate = symbol_stats.get("win_rate", 0.0)
        win_loss_ratio = symbol_stats.get("win_loss_ratio", 0.0)
        
        if win_loss_ratio <= 0:
            return 0.01
            
        # Fórmula de Kelly: f* = p - (1 - p) / b
        kelly_f = win_rate - (1.0 - win_rate) / win_loss_ratio
        
        # Kelly Fraccionario (20% de Kelly para no sobre-apalancar y mantener baja volatilidad)
        fractional_kelly = kelly_f * 0.20
        
        # Clampar entre 1.0% y 4.0%
        final_risk = max(0.01, min(0.04, fractional_kelly))
        return final_risk


class TrailingStopManager:
    """
    Gestiona Stop Loss dinámico que se ajusta automáticamente:
    - El SL sube a medida que el precio sube (siguiendo el ATR)
    - El TP estático se ELIMINA → el SL es lo único que cierra la posición
    - Si el precio cae por debajo del trailing SL, se vende
    - Si la tendencia se quiebra (divergencia/señal de salida), también se cierra
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
    ) -> Dict:
        """
        Actualiza el trailing stop basado en:
        1. Precio máximo alcanzado (running high)
        2. ATR actual (volatilidad dinámica)
        3. Break-even: si ganancia >= breakeven_pct%, SL sube al precio de entrada

        El SL nunca baja (only moves up / close position).

        Args:
            entry_price: precio de entrada
            current_price: precio actual
            current_atr: ATR calculado ahora
            max_price: máximo histórico de esta posición
            initial_sl: SL inicial (de entrada)
            trailing_atr_mult: multiplicador ATR para el trailing (ej. 2.0)
            breakeven_pct: % de ganancia para activar break-even (default 1.0%)

        Returns:
            {
                'new_sl': float,  # Nuevo SL (nunca menor a initial_sl)
                'trailing_active': bool,
                'moved_sl': bool,
                'sl_movement_pct': float,
                'max_possible_sl': float,
                'breakeven_active': bool,
            }
        """
        # SL mínimo es el inicial (nunca retrocede)
        min_sl = initial_sl

        # Break-even: si el precio alcanzó +breakeven_pct%, el SL mínimo sube al entry
        breakeven_active = False
        if max_price >= entry_price * (1 + breakeven_pct / 100):
            min_sl = max(min_sl, entry_price)
            breakeven_active = True

        # Si el precio subió desde entrada, calcula un trailing SL
        if current_price > entry_price:
            # Trailing SL = max_price - (trailing_atr_mult * ATR)
            potential_sl = max_price - trailing_atr_mult * current_atr

            # Pero nunca por debajo del SL mínimo (que puede ser entry si break-even)
            new_sl = max(potential_sl, min_sl)
        else:
            # Si el precio está por debajo de entrada, usa el SL mínimo
            new_sl = min_sl

        # ¿Se movió el SL?
        moved = new_sl > initial_sl
        movement_pct = (new_sl / initial_sl - 1) * 100 if moved else 0.0

        return {
            "new_sl": new_sl,
            "trailing_active": current_price > entry_price,
            "moved_sl": moved,
            "sl_movement_pct": movement_pct,
            "max_possible_sl": current_price - trailing_atr_mult * current_atr,
            "breakeven_active": breakeven_active,
            "reason": (
                f"Break-even activo: SL=${new_sl:.4f}"
                if breakeven_active and not (new_sl > entry_price * 1.001)
                else f"Trailing: ${new_sl:.4f} (arriba {movement_pct:.2f}%)"
                if moved
                else f"Esperando entrada a tomar ganancias"
            ),
        }

    @staticmethod
    def should_close_trailing(
        current_price: float, current_sl: float, entry_price: float
    ) -> Tuple[bool, str]:
        """
        Decide si cerrar la posición basado en si toca el trailing SL.

        Returns: (should_close, reason)
        """
        if current_price <= current_sl:
            return True, f"Trailing Stop Hit: ${current_price:.4f} <= ${current_sl:.4f}"

        if current_price < entry_price and current_sl <= current_price * 0.98:
            return True, f"Initial SL Hit: ${current_price:.4f} <= ${current_sl:.4f}"

        return False, ""

    @staticmethod
    def calculate_partial_exit(
        entry_price: float,
        current_price: float,
        total_quantity: float,
        profit_target_pct: float = 2.5,
    ) -> Dict:
        """
        OPCIONAL: Cierre parcial de ganancias.
        Ej. cuando ganas 2.5%, vende el 50% de la posición y mueve SL al entrada.

        Returns:
            {
                'should_exit_partial': bool,
                'exit_quantity': float,
                'remaining_quantity': float,
                'reason': str,
            }
        """
        gain_pct = (current_price / entry_price - 1) * 100

        if gain_pct >= profit_target_pct:
            exit_qty = total_quantity * 0.5  # 50% de la posición

            return {
                "should_exit_partial": True,
                "exit_quantity": exit_qty,
                "remaining_quantity": total_quantity - exit_qty,
                "profit_pct": gain_pct,
                "reason": f"Cierre parcial al {gain_pct:.2f}% de ganancia",
            }

        return {
            "should_exit_partial": False,
            "reason": f"Ganancia actual {gain_pct:.2f}% < objetivo {profit_target_pct}%",
        }


logger.info("Módulo de estrategia cargado")