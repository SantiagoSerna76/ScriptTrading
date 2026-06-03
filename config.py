import os
from dotenv import load_dotenv

load_dotenv()

# ─── Credenciales Binance ────────────────────────────────────────────────────
API_KEY    = os.getenv("BINANCE_API_KEY")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# ─── Telegram Notifier ───────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

# ─── Modo de Operación ───────────────────────────────────────────────────────
PAPER_TRADING = True    # True = simula trades sin ejecutar órdenes reales
USE_TESTNET   = False   # False = usa Mainnet para datos reales de mercado

# ─── Universo de Trading ─────────────────────────────────────────────────────
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "LTCUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT", "APTUSDT",
    "ARBUSDT", "OPUSDT", "SUIUSDT", "FILUSDT", "AAVEUSDT",
    "INJUSDT", "RENDERUSDT", "FETUSDT", "PEPEUSDT", "WIFUSDT",
    "TRXUSDT", "ICPUSDT", "BCHUSDT", "ETCUSDT", "STXUSDT",
    "IMXUSDT", "THETAUSDT", "ALGOUSDT", "SANDUSDT", "MANAUSDT",
    "GALAUSDT", "EGLDUSDT", "AXSUSDT", "TONUSDT", "SEIUSDT",
    "TIAUSDT", "ORDIUSDT", "RUNEUSDT", "ROSEUSDT", "CHZUSDT",
    "QNTUSDT", "MKRUSDT", "SNXUSDT", "CRVUSDT", "LDOUSDT",
]
ENTRY_SYMBOLS = SYMBOLS
RELAXED_MACRO_SYMBOLS = SYMBOLS

STRATEGY_START_TIME = "2026-05-29T23:00:00"

# ─── Capital y Riesgo ────────────────────────────────────────────────────────
CAPITAL_TOTAL_USDT   = 500.0
RIESGO_POR_TRADE     = 0.02    # 2% del capital por trade (se mantiene)
MAX_OPEN_POSITIONS   = 5       # Permitir hasta 5 posiciones simultáneas ($100 c/u)
MIN_ORDER_NOTIONAL   = 5.0

# ─── Protección diaria ───────────────────────────────────────────────────────
MAX_DAILY_LOSS_USDT  = 10.0
MAX_DAILY_TRADES     = 10       # Permitir más trades para 60 monedas

# ─── Cooldown entre entradas ─────────────────────────────────────────────────
MIN_BUY_COOLDOWN_H   = 2       # 2h entre mismo par
MIN_BUY_COOLDOWN_S   = MIN_BUY_COOLDOWN_H * 3600
SL_COOLDOWN_S        = 8 * 3600    # 8h después de un SL (antes 4h)
CONSECUTIVE_LOSS_MAX = 2           # Pausa tras 2 pérdidas consecutivas
CONSECUTIVE_LOSS_COOLDOWN_S = 24 * 3600  # 24h de cooldown tras 2 pérdidas seguidas

# ─── Indicadores técnicos ────────────────────────────────────────────────────
TIMEFRAME       = "1h"     # Trend Following en 1H
KLINES_LIMIT    = 500      # 500 velas × 1h = ~20 días
EMA_CORTO       = 20       # EMA rápida
EMA_LARGO       = 50       # EMA lenta (confirmación de tendencia)
RSI_PERIOD      = 14
ATR_PERIOD      = 14
ADX_PERIOD      = 14
ADX_MIN         = 22       # AUMENTADO de 20→22: tendencia más definida

# ─── Filtros de entrada (Trend Following 1H) ─────────────────────────────────
RSI_BUY_MIN         = 40     # No comprar con RSI < 40 (momentum débil)
RSI_BUY_MAX         = 65     # No comprar con RSI > 65 (sobrecomprado, tarde para entrar)

# ─── Stop Loss / Take Profit ─────────────────────────────────────────────────
# R:R optimizado matemáticamente para Estrategia Institucional en 1H
SL_ATR_MULT = 1.0
TP_ATR_MULT = 2.0
# R:R efectivo = 2.0/1.0 = 2.0:1

# Máximo Stop Loss en porcentaje (protección contra volátiles)
MAX_SL_PCT = 3.0  # REDUCIDO de 6→3%: ningún trade pierde más del 3%

# Breakeven cuando el precio avanza 1.0× ATR a favor
BREAKEVEN_ATR_MULT = 1.0

# Trailing Stop Dinámico
# Se activa después de 1.5 ATR de ganancia
TRAILING_ACTIVATE_ATR = 1.5
TRAILING_STEP_ATR     = 0.5
TRAILING_SL_OFFSET_ATR = 0.8  # SL a 0.8 ATR debajo del máximo

# Límite máximo de retención: 48h para tendencias en 1H
MAX_HOLD_HOURS = 48

# ─── Comisiones ──────────────────────────────────────────────────────────────
TRADING_FEE_RATE = 0.001   # 0.1% Binance Spot
MIN_HOLD_HOURS   = 0.5     # 30 min mínimo (2 velas de 15m)

# ─── Sistema ─────────────────────────────────────────────────────────────────
LOG_FILE         = "trading_bot.log"
DB_FILE          = "trades.db"
POLLING_INTERVAL = 60      # 60s: en 15m revisamos cada minuto
PAUSE_SIGNAL_FILE = ".bot_pause_signal"

# ─── Proxy ───────────────────────────────────────────────────────────────────
PROXY_URL = os.getenv("PROXY_URL")