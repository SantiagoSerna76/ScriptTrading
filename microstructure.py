#!/usr/bin/env python3
"""
Análisis de Microestructura de Mercado (Order Book)
- Detecta muros de venta/compra (sell/buy walls)
- Valida que hay liquidez suficiente antes de ejecutar orden
- Usa WebSocket para datos en tiempo real (opcional) o REST fallback
"""

import logging
import json
import asyncio
from typing import Dict, Optional, List, Tuple
import requests
from collections import defaultdict

logger = logging.getLogger(__name__)


class OrderBookAnalyzer:
    """
    Analiza el Order Book para detectar:
    1. Muros de venta (sell walls) justo arriba del precio
    2. Liquidez disponible para nuestra orden
    3. Imbalance (ratio buy/sell)
    """

    BASE_URL = "https://api.binance.com/api/v3"

    def __init__(self, api_key: str = "", secret_key: str = ""):
        """Order Book es público, pero pasamos credenciales por si acaso."""
        self.api_key = api_key
        self.secret_key = secret_key

    def get_order_book(
        self, symbol: str, limit: int = 20
    ) -> Optional[Dict]:
        """
        Obtiene el Order Book actual.
        limit: 5, 10, 20, 50, 100, 500, 1000
        """
        try:
            url = f"{self.BASE_URL}/depth"
            params = {"symbol": symbol, "limit": limit}
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error obteniendo Order Book para {symbol}: {e}")
            return None

    def detect_sell_wall(
        self, symbol: str, current_price: float, levels_to_check: int = 5, ob: Optional[Dict] = None
    ) -> Dict:
        """
        Detecta si hay un "muro de venta" (sell wall) significativo
        justo por encima del precio actual.

        Devuelve: {
            'has_wall': bool,
            'wall_price': float,
            'wall_size': float,
            'distance_pct': float,  # % del precio actual
            'severity': str,  # 'LOW', 'MEDIUM', 'HIGH'
            'recommendation': str,  # 'OK', 'CAUTION', 'REJECT'
        }
        """
        if ob is None:
            ob = self.get_order_book(symbol, limit=50)
        if not ob:
            return {
                "has_wall": False,
                "reason": "No data",
                "recommendation": "PROCEED_WITH_CAUTION"
            }

        asks = ob.get("asks", [])  # [price, quantity]
        if not asks:
            return {
                "has_wall": False,
                "reason": "Empty order book",
                "recommendation": "PROCEED_WITH_CAUTION"
            }

        # Convierte a float
        asks_parsed = [(float(p), float(q)) for p, q in asks]

        # Promedio de tamaño de órdenes
        avg_size = sum(q for _, q in asks_parsed[:levels_to_check]) / len(asks_parsed[:levels_to_check])

        # Busca un nivel anormalmente grande en los primeros niveles
        for i, (price, quantity) in enumerate(asks_parsed[:levels_to_check]):
            distance_pct = (price / current_price - 1) * 100

            # Si la cantidad es > 2x el promedio, es un wall
            if quantity > avg_size * 2 and distance_pct < 2:
                severity = "HIGH" if quantity > avg_size * 5 else "MEDIUM"

                return {
                    "has_wall": True,
                    "wall_price": price,
                    "wall_size": quantity,
                    "distance_pct": distance_pct,
                    "severity": severity,
                    "avg_level_size": avg_size,
                    "recommendation": "REJECT" if severity == "HIGH" else "CAUTION",
                }

        return {
            "has_wall": False,
            "reason": "No sell wall detected",
            "recommendation": "OK",
            "avg_level_size": avg_size,
        }

    def detect_buy_wall(
        self, symbol: str, current_price: float, levels_to_check: int = 5, ob: Optional[Dict] = None
    ) -> Dict:
        """
        Detecta "muros de compra" (buy walls) justo debajo del precio.
        Estos FAVORECEN la compra (soporte).
        """
        if ob is None:
            ob = self.get_order_book(symbol, limit=50)
        if not ob:
            return {"has_wall": False, "reason": "No data"}

        bids = ob.get("bids", [])  # [price, quantity]
        if not bids:
            return {"has_wall": False, "reason": "Empty order book"}

        bids_parsed = [(float(p), float(q)) for p, q in bids]
        avg_size = sum(q for _, q in bids_parsed[:levels_to_check]) / len(bids_parsed[:levels_to_check])

        for price, quantity in bids_parsed[:levels_to_check]:
            distance_pct = (1 - price / current_price) * 100

            if quantity > avg_size * 3 and distance_pct < 2:
                return {
                    "has_wall": True,
                    "wall_price": price,
                    "wall_size": quantity,
                    "distance_below_pct": distance_pct,
                    "strength": "STRONG",
                }

        return {"has_wall": False, "reason": "No buy wall detected"}

    def calculate_imbalance(self, symbol: str, levels: int = 10, ob: Optional[Dict] = None) -> Dict:
        """
        Calcula el ratio de volumen Buy/Sell en el order book.
        - Ratio > 1.2 = más presión de compra
        - Ratio < 0.8 = más presión de venta
        """
        if ob is None:
            ob = self.get_order_book(symbol, limit=levels)
        if not ob:
            return {"imbalance_ratio": 1.0, "reason": "No data"}

        bids = sum(float(q) for _, q in ob.get("bids", [])[:levels])
        asks = sum(float(q) for _, q in ob.get("asks", [])[:levels])

        ratio = bids / asks if asks > 0 else 1.0

        return {
            "imbalance_ratio": round(ratio, 3),
            "buy_volume": round(bids, 2),
            "sell_volume": round(asks, 2),
            "sentiment": "BULLISH" if ratio > 1.2 else "BEARISH" if ratio < 0.8 else "NEUTRAL",
        }

    def validate_order_liquidity(
        self, symbol: str, order_quantity: float, side: str = "BUY", ob: Optional[Dict] = None
    ) -> Tuple[bool, Dict]:
        """
        Valida que haya suficiente liquidez para ejecutar una orden.

        Devuelve (puede_ejecutar, detalles)
        """
        if ob is None:
            ob = self.get_order_book(symbol, limit=50)
        if not ob:
            return False, {"reason": "No order book data"}

        side_book = ob.get("bids" if side == "BUY" else "asks", [])
        cumulative = 0.0

        for price_str, qty_str in side_book:
            qty = float(qty_str)
            cumulative += qty
            if cumulative >= order_quantity * 0.95:  # Necesita el 95% de la cantidad
                return True, {
                    "reason": "Sufficient liquidity",
                    "cumulative_qty": round(cumulative, 4),
                    "required_qty": round(order_quantity, 4),
                }

        return False, {
            "reason": f"Insufficient liquidity for {order_quantity}",
            "available": round(cumulative, 4),
            "required": round(order_quantity, 4),
        }

    def pre_order_check(
        self,
        symbol: str,
        entry_price: float,
        quantity: float,
        side: str = "BUY",
        sell_wall_threshold: str = "MEDIUM"
    ) -> Tuple[bool, Dict]:
        """
        Valida ANTES de ejecutar una orden:
        1. ¿Hay liquidez suficiente?
        2. ¿Hay un muro de venta inaceptable?

        Devuelve (proceed, detalles)
        """
        check_results = {}

        # 1. Descargamos el Order Book una sola vez
        ob = self.get_order_book(symbol, limit=50)
        if not ob:
            return False, {"reason": "No order book data"}

        # 2. Liquidity check
        liquidity_ok, liquidity_detail = self.validate_order_liquidity(
            symbol, quantity, side, ob
        )
        check_results["liquidity"] = liquidity_detail
        check_results["liquidity_ok"] = liquidity_ok

        # 3. Sell wall check (solo si es BUY)
        if side == "BUY":
            wall_detail = self.detect_sell_wall(symbol, entry_price, levels_to_check=10, ob=ob)
            check_results["sell_wall"] = wall_detail

            # Rechaza si el wall es del nivel especificado o peor
            severity_map = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
            threshold_level = severity_map.get(sell_wall_threshold, 1)
            wall_severity_level = severity_map.get(wall_detail.get("severity", "LOW"), 0)

            if wall_detail.get("has_wall") and wall_severity_level >= threshold_level:
                check_results["wall_rejection"] = True
                return False, check_results

        # 4. Imbalance (informativo)
        imbalance = self.calculate_imbalance(symbol, levels=10, ob=ob)
        check_results["imbalance"] = imbalance

        # Decision final
        if liquidity_ok and not check_results.get("wall_rejection", False):
            return True, check_results
        else:
            return False, check_results
