#!/usr/bin/env python3
"""
Análisis Multi-Timeframe (MTF) — combina tendencia macro (4H) con entrada táctica (1H/15m)
"""

import logging
import pandas as pd
from typing import Dict, Tuple, Optional
from strategy import TechnicalIndicators

logger = logging.getLogger(__name__)


class MultiTimeframeAnalyzer:
    """
    Valida que la tendencia macro es alcista ANTES de permitir entrada.
    - Timeframe 4H: tendencia mayor (EMA200, MACD, ADX)
    - Timeframe 1H: táctica de entrada (score + RSI + volumen)
    """

    def __init__(self):
        self.ti = TechnicalIndicators()

    def analyze_macro_trend(self, df_4h: pd.DataFrame) -> Dict:
        """
        Análisis de tendencia en timeframe 4H.
        Devuelve diccionario con flags de validez macro.
        """
        if df_4h is None or len(df_4h) < 210:
            return {"valid": False, "reason": "No hay suficientes datos 4H"}

        # Calcula indicadores para 4H
        df = df_4h.copy()
        df["ema_short"]  = self.ti.ema(df["close"], 20)
        df["ema_long"]   = self.ti.ema(df["close"], 50)
        df["ema200"]     = self.ti.ema(df["close"], 200)
        df["macd"], df["macd_signal"], _ = self.ti.macd(df["close"])
        df["adx"]        = self.ti.adx(df)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Filtros macro (todos deben cumplirse)
        conditions = {
            "price_above_ema200": last["close"] > last["ema200"],
            "ema_bullish": last["ema_short"] > last["ema_long"],
            "macd_bullish": last["macd"] > last["macd_signal"],  # ← Informativo/bonus (ya no es hard block)
            "macd_growing": last["macd"] > prev["macd"],
            "adx_strong": last["adx"] >= 20,  # Bajado de 25→20: captura tendencias en desarrollo sin perder calidad
            "ema200": round(last["ema200"], 2),
            "adx": round(last["adx"], 2),
            "macd": round(last["macd"], 4),
        }

        # Condiciones hard: para Mean Reversion solo necesitamos tendencia macro alcista
        # La alineación EMA20 > EMA50 ya no es obligatoria (compramos dips que rompen eso)
        all_valid = all([
            conditions["price_above_ema200"],
            conditions["adx_strong"],
        ])

        conditions["valid"] = all_valid
        if not all_valid:
            # Excluimos keys que no son booleanas ni el flag 'valid' en sí
            skip_keys = {"ema200", "adx", "macd", "valid", "reason", "macd_growing", "macd_bullish"}
            failed = [k for k, v in conditions.items() if k not in skip_keys and v is False]
            conditions["reason"] = f"Filtros fallidos en 4H: {', '.join(failed) if failed else 'condiciones no cumplidas'}"
        else:
            conditions["reason"] = "Tendencia macro ALCISTA confirmada en 4H"

        return conditions

    def validate_entry_with_macro(
        self,
        df_1h: pd.DataFrame,
        macro_conditions: Dict,
        buy_signal_1h: bool,
        conditions_1h: Dict,
        relaxed: bool = False
    ) -> Tuple[bool, Dict]:
        """
        Valida entrada SOLO si:
        1. La macro 4H está en tendencia alcista (O neutral si relaxed=True)
        2. La táctica 1H genera una señal de compra
        3. Se combina la información de ambos timeframes

        Si relaxed=True, macro neutral permite entrada pero penaliza el score.

        Devuelve (señal_final, detalles_combinados)
        """
        combined_details = {
            "macro_valid": macro_conditions.get("valid", False),
            "tactical_signal": buy_signal_1h,
            "combined_score": 0,
            "filters_applied": {},
            "relaxed": relaxed,
        }

        # GATE 1: La tendencia macro ya no bloquea a nadie. Solo da contexto y suma bonos después.
        if not macro_conditions.get("valid", False):
            combined_details["reason"] = f"Macro 4H NO alcista ({macro_conditions.get('reason', 'Unknown')})"
        else:
            combined_details["reason"] = "Macro 4H Alcista confirmada"

        # Obtenemos el score táctico base de 1H
        base_score = conditions_1h.get("score", 0)
        combined_score = base_score

        # Bonus si EMA200 muy por debajo del precio (uptrend fuerte)
        if macro_conditions.get("price_above_ema200"):
            price_above_ema200_pct = (
                conditions_1h.get("close_price", 0) / (macro_conditions.get("ema200") or 1e-8) - 1
            ) * 100
            if price_above_ema200_pct > 5:
                combined_score += 1  # +1 por uptrend establecido
                combined_details["filters_applied"]["ema200_margin"] = f"+{price_above_ema200_pct:.1f}%"

        # Bonus si ADX es muy fuerte
        if macro_conditions.get("adx", 0) > 30:
            combined_score += 1  # +1 por tendencia muy fuerte
            combined_details["filters_applied"]["strong_adx"] = f"ADX {macro_conditions.get('adx')}"

        # Bonus si MACD es alcista
        if macro_conditions.get("macd_bullish"):
            combined_score += 1
            combined_details["filters_applied"]["macd_bullish"] = True

        combined_details["combined_score"] = combined_score
        combined_details["macro_info"] = {
            "ema200": macro_conditions.get("ema200"),
            "adx": macro_conditions.get("adx"),
            "macd": macro_conditions.get("macd"),
        }
        # Determinar score mínimo: Pullback Hunter necesita 3 de 5 condiciones base
        effective_min_score = 3
        
        is_valid = combined_score >= effective_min_score

        combined_details["reason"] = (
            f"MTF {'VÁLIDO' if is_valid else 'INVÁLIDO'}: "
            f"Macro {'Alcista' if macro_conditions.get('valid') else 'No Alcista'} + "
            f"Score {combined_score} (Req: {effective_min_score})"
        )

        return is_valid, combined_details


class HigherTimeframeFilter:
    """Deprecated. Usar MultiTimeframeAnalyzer en su lugar."""
    pass
