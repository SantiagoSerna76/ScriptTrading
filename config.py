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
MAX_OPEN_POSITIONS   = 2       # REDUCIDO de 3→2: Más concentración
MIN_ORDER_NOTIONAL   = 5.0

# ─── Protección diaria ───────────────────────────────────────────────────────
MAX_DAILY_LOSS_USDT  = 10.0
MAX_DAILY_TRADES     = 10       # Permitir más trades para 60 monedas

# ─── Cooldown entre entradas ─────────────────────────────────────────────────
MIN_BUY_COOLDOWN_H   = 2       # Se mantiene: 2h entre mismo par
MIN_BUY_COOLDOWN_S   = MIN_BUY_COOLDOWN_H * 3600
SL_COOLDOWN_S        = 4 * 3600    # Se mantiene: 4h después de un SL
CONSECUTIVE_LOSS_MAX = 2            # Se mantiene: pausa tras 2 pérdidas

# ─── Indicadores técnicos ────────────────────────────────────────────────────
TIMEFRAME       = "1h"     # Trend Following en 1H
KLINES_LIMIT    = 500      # 500 velas × 1h = ~20 días
EMA_CORTO       = 20       # EMA rápida
EMA_LARGO       = 50       # EMA lenta (confirmación de tendencia)
RSI_PERIOD      = 14
ATR_PERIOD      = 14
ADX_PERIOD      = 14
ADX_MIN         = 22       # AUMENTADO de 20→22: tendencia más definida

# ─── Señales de entrada (Momentum Dip Buyer) ─────────────────────────────────
RSI_PULLBACK_MIN    = 38     # AUMENTADO de 35→38: evitar trampas en dips profundos
RSI_PULLBACK_MAX    = 52     # Zona de pullback normal
EMA_PULLBACK_PCT    = 1.5    # REDUCIDO de 1.8→1.5%: más pegado al EMA20
MIN_BUY_SCORE       = 3      # Se mantiene: 3 de 4 condiciones

# ─── Stop Loss / Take Profit ─────────────────────────────────────────────────
# R:R optimizado matemáticamente para Estrategia de Tendencia en 1H
SL_ATR_MULT = 2.0
TP_ATR_MULT = 3.0
# R:R efectivo = 3.0/2.0 = 1.5:1
# Con WR=50%: 0.5*3.6 - 0.5*2.2 = 0.7% > 0 ✓ (vs antes 0.43%)

# Máximo Stop Loss en porcentaje (protección contra volátiles)
MAX_SL_PCT = 6.0  # Se mantiene

# Breakeven cuando el precio avanza 1.5× ATR a favor
BREAKEVEN_ATR_MULT = 1.5

# Trailing Stop Dinámico
# Se activa después de 2.5 ATR de ganancia (protege tendencias fuertes en 15m)
TRAILING_ACTIVATE_ATR = 2.5
TRAILING_STEP_ATR     = 0.8
TRAILING_SL_OFFSET_ATR = 1.0  # SL a 1.0 ATR debajo del máximo

# Límite máximo de retención: 24h es suficiente para 15m (96 velas)
MAX_HOLD_HOURS = 24

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