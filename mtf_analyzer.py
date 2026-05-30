#!/usr/bin/env python3
"""
Análisis Multi-Timeframe (MTF) — v3.0 Simplificado
Solo proporciona contexto macro (4H) para logs y decisiones informativas.
NO bloquea trades. NO combina scores.
"""

import logging
import pandas as pd
from typing import Dict, Tuple
from strategy import TechnicalIndicators

logger = logging.getLogger(__name__)


class MultiTimeframeAnalyzer:
    """
    Analiza la tendencia macro en 4H para enriquecer los logs.
    NO bloquea entradas — la decisión de entrada es 100% del motor 1H.
    """

    def __init__(self):
        self.ti = TechnicalIndicators()

    def analyze_macro_trend(self, df_4h: pd.DataFrame) -> Dict:
        """
        Análisis de tendencia en timeframe 4H.
        Devuelve diccionario con información macro para logs.
        """
        if df_4h is None or len(df_4h) < 210:
            return {"valid": False, "reason": "No hay suficientes datos 4H"}

        df = df_4h.copy()
        df["ema_short"]  = self.ti.ema(df["close"], 20)
        df["ema_long"]   = self.ti.ema(df["close"], 50)
        df["ema200"]     = self.ti.ema(df["close"], 200)
        df["macd"], df["macd_signal"], _ = self.ti.macd(df["close"])
        df["adx"]        = self.ti.adx(df)

        last = df.iloc[-1]

        conditions = {
            "price_above_ema200": last["close"] > last["ema200"],
            "ema_bullish": last["ema_short"] > last["ema_long"],
            "adx_strong": last["adx"] >= 20,
            "macd_bullish": last["macd"] > last["macd_signal"],
            "ema200": round(last["ema200"], 2),
            "adx": round(last["adx"], 2),
        }

        # Tendencia macro: informativa solamente
        all_valid = conditions["price_above_ema200"] and conditions["adx_strong"]
        conditions["valid"] = all_valid

        if all_valid:
            conditions["reason"] = "Macro 4H ALCISTA"
        else:
            conditions["reason"] = "Macro 4H neutral/bajista"

        return conditions

    def get_macro_context(self, df_4h: pd.DataFrame) -> str:
        """Retorna un string descriptivo del contexto macro para logs."""
        macro = self.analyze_macro_trend(df_4h)
        return (
            f"{macro.get('reason', 'N/A')} | "
            f"ADX={macro.get('adx', 0):.1f} | "
            f"EMA200=${macro.get('ema200', 0):.2f}"
        )


class HigherTimeframeFilter:
    """Deprecated. Usar MultiTimeframeAnalyzer en su lugar."""
    pass
