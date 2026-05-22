import time
import hmac
import hashlib
import requests
import logging
from typing import Optional, Dict, List
import pandas as pd
from config import API_KEY, SECRET_KEY

logger = logging.getLogger(__name__)

# ─── Constantes ──────────────────────────────────────────────────────────────
MAX_RETRIES   = 3
RETRY_DELAY_S = 2.0      # segundos entre reintentos (se duplica cada vez)
REQUEST_TIMEOUT = 12


class BinanceAPI:
    """Wrapper para la API de Binance con reintentos y manejo robusto de errores."""

    def __init__(self, api_key: str, secret_key: str, use_testnet: bool = True):
        self.api_key    = api_key
        self.secret_key = secret_key
        self.use_testnet = use_testnet
        self.BASE_URL   = "https://testnet.binance.vision" if use_testnet else "https://api.binance.com"
        self.session    = requests.Session()
        if api_key:
            self.session.headers.update({"X-MBX-APIKEY": api_key})

    def get_symbol_rules(self, symbol: str) -> Optional[Dict]:
        """Devuelve filtros de trading dinámicos (stepSize, tickSize, minNotional) para el símbolo."""
        info = self.get_exchange_info(symbol)
        if not info:
            return None

        rules = {
            "step_size": 0.01,
            "tick_size": 0.01,
            "min_notional": 11.0,
        }

        for f in info.get("filters", []):
            f_type = f.get("filterType")
            if f_type == "LOT_SIZE":
                rules["step_size"] = float(f.get("stepSize"))
            elif f_type == "PRICE_FILTER":
                rules["tick_size"] = float(f.get("tickSize"))
            elif f_type == "NOTIONAL" or f_type == "MIN_NOTIONAL":
                rules["min_notional"] = float(f.get("minNotional", 10.0))

        return rules

    # ── Firma ─────────────────────────────────────────────────────────────────
    def _sign(self, query_string: str) -> str:
        return hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    # ── Request con reintentos ────────────────────────────────────────────────
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict = None,
        signed: bool = False,
    ) -> Optional[Dict]:
        if params is None:
            params = {}

        # Limpia None values antes de firmar
        params = {k: v for k, v in params.items() if v is not None}

        url = f"{self.BASE_URL}{endpoint}"
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                p = dict(params)  # copia para no mutar en reintentos

                if signed:
                    p["timestamp"] = int(time.time() * 1000)
                    qs = "&".join(f"{k}={v}" for k, v in p.items())
                    p["signature"] = self._sign(qs)

                resp = self.session.request(method, url, params=p, timeout=REQUEST_TIMEOUT)

                # Respuestas de rate-limit → espera y reintenta
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 5))
                    logger.warning(f"Rate limit 429. Esperando {wait}s …")
                    time.sleep(wait)
                    continue

                # Error de IP ban
                if resp.status_code == 418:
                    logger.error("IP baneada por Binance (418). Detener el bot.")
                    return None

                resp.raise_for_status()
                return resp.json()

            except requests.exceptions.Timeout:
                last_error = "Timeout"
            except requests.exceptions.ConnectionError:
                last_error = "ConnectionError"
            except requests.exceptions.HTTPError as e:
                last_error = f"HTTPError {e.response.status_code}: {e.response.text[:200]}"
                # No reintentar errores 4xx (parámetros incorrectos)
                if e.response.status_code < 500:
                    logger.error(f"Error cliente Binance: {last_error}")
                    return None

            delay = RETRY_DELAY_S * (2 ** (attempt - 1))
            logger.warning(f"Intento {attempt}/{MAX_RETRIES} falló ({last_error}). Reintentando en {delay:.1f}s …")
            time.sleep(delay)

        logger.error(f"Todos los reintentos fallaron para {method} {endpoint}: {last_error}")
        return None

    # ── Endpoints públicos ────────────────────────────────────────────────────
    def get_klines(self, symbol: str, interval: str, limit: int = 200) -> Optional[List]:
        data = self._request("GET", "/api/v3/klines", {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000),
        })
        if data:
            logger.debug(f"Obtenidas {len(data)} velas para {symbol}")
        return data

    def get_ticker_price(self, symbol: str) -> Optional[float]:
        data = self._request("GET", "/api/v3/ticker/price", {"symbol": symbol})
        return float(data["price"]) if data else None

    def get_exchange_info(self, symbol: str) -> Optional[Dict]:
        """Devuelve filtros del símbolo (mínimos, step size, etc.)"""
        data = self._request("GET", "/api/v3/exchangeInfo", {"symbol": symbol})
        if data:
            return data["symbols"][0] if data.get("symbols") else None
        return None

    # ── Endpoints privados ────────────────────────────────────────────────────
    def place_order(
        self,
        symbol: str,
        side: str,
        type_: str,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Optional[Dict]:
        params: Dict = {
            "symbol":   symbol,
            "side":     side,
            "type":     type_,
            "quantity": quantity,
        }
        if type_ == "LIMIT":
            params["timeInForce"] = "GTC"
            params["price"] = price
        if stop_price:
            params["stopPrice"] = stop_price

        resp = self._request("POST", "/api/v3/order", params, signed=True)
        if resp:
            logger.info(f"Orden {side} {type_} ejecutada: {quantity} {symbol}")
        return resp

    def get_account_balance(self) -> Optional[Dict]:
        return self._request("GET", "/api/v3/account", signed=True)

    def get_open_orders(self, symbol: str = None) -> Optional[List]:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/api/v3/openOrders", params, signed=True)

    def cancel_order(self, symbol: str, order_id: int) -> Optional[Dict]:
        return self._request("DELETE", "/api/v3/order",
                             {"symbol": symbol, "orderId": order_id}, signed=True)

    def get_usdt_balance(self) -> float:
        """Shortcut: devuelve saldo libre USDT."""
        account = self.get_account_balance()
        if account:
            for b in account.get("balances", []):
                if b["asset"] == "USDT":
                    return float(b["free"])
        return 0.0


# ── Helpers ──────────────────────────────────────────────────────────────────

def parse_klines_to_dataframe(klines: List) -> pd.DataFrame:
    """Convierte raw klines de Binance a DataFrame OHLCV."""
    df = pd.DataFrame(klines, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ])
    df[["open", "high", "low", "close", "volume"]] = (
        df[["open", "high", "low", "close", "volume"]].astype(float)
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
