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

# ─── Universo de Trading (59 monedas — eliminado KASUSDT que no existe en Spot) ──
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "SHIBUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT",
    "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
    "FILUSDT", "AAVEUSDT", "INJUSDT", "RENDERUSDT", "FETUSDT",
    "PEPEUSDT", "WIFUSDT", "FLOKIUSDT", "TRXUSDT", "ICPUSDT",
    "BCHUSDT", "ETCUSDT", "STXUSDT", "IMXUSDT", "VETUSDT",
    "THETAUSDT", "FTMUSDT", "ALGOUSDT", "SANDUSDT", "MANAUSDT",
    "GALAUSDT", "EGLDUSDT", "AXSUSDT", "TONUSDT",
    "SEIUSDT", "TIAUSDT", "TAOUSDT", "ORDIUSDT", "RUNEUSDT",
    "ASTRUSDT", "AGIXUSDT", "OCEANUSDT", "ROSEUSDT", "CHZUSDT",
    "QNTUSDT", "MKRUSDT", "SNXUSDT", "CRVUSDT", "LDOUSDT"
]
ENTRY_SYMBOLS = SYMBOLS.copy()
RELAXED_MACRO_SYMBOLS = SYMBOLS.copy()

# Reset estadístico — fecha de inicio de la estrategia Momentum Dip Buyer
STRATEGY_START_TIME = "2026-05-29T23:00:00"

# ─── Capital y Riesgo ────────────────────────────────────────────────────────
CAPITAL_TOTAL_USDT   = 500.0
RIESGO_POR_TRADE     = 0.02    # 2% del capital por trade
MAX_OPEN_POSITIONS   = 3       # Máximo de posiciones simultáneas
MIN_ORDER_NOTIONAL   = 5.0     # Mínimo de Binance

# ─── Protección diaria ───────────────────────────────────────────────────────
MAX_DAILY_LOSS_USDT  = 10.0    # $10 máximo de pérdida diaria (2% del capital)
MAX_DAILY_TRADES     = 15      # Máximo 15 trades/día (subido de 10 para más oportunidades)

# ─── Cooldown entre entradas ─────────────────────────────────────────────────
MIN_BUY_COOLDOWN_H   = 1       # 1h mínimo entre entradas del mismo par (bajado de 2h)
MIN_BUY_COOLDOWN_S   = MIN_BUY_COOLDOWN_H * 3600
SL_COOLDOWN_S        = 2 * 3600    # 2h de cooldown después de un Stop Loss (bajado de 4h)
CONSECUTIVE_LOSS_MAX = 3            # Tras 3 pérdidas consecutivas → pausa de 4h

# ─── Indicadores técnicos ────────────────────────────────────────────────────
TIMEFRAME       = "1h"    # Temporalidad principal: 1 Hora
KLINES_LIMIT    = 500     # 500 velas × 1h = ~20 días
EMA_CORTO       = 20      # EMA rápida (soporte dinámico del pullback)
EMA_LARGO       = 50      # EMA lenta (confirmación de tendencia)
RSI_PERIOD      = 14
ATR_PERIOD      = 14
ADX_PERIOD      = 14
ADX_MIN         = 20      # Mínimo ADX para confirmar tendencia real

# ─── Stop Loss / Take Profit ────────────────────────────────────────────────
# Multiplicadores ATR para Scalping de Reversión
SL_ATR_MULT = 3.0
TP_ATR_MULT = 1.0

# Máximo Stop Loss en porcentaje (protección contra monedas muy volátiles)
MAX_SL_PCT = 4.5  # Modificado para permitir 3x ATR

# Mueve el SL a precio de entrada cuando el precio alcance este multiplicador ATR
# DESACTIVADO (9.9) para scalping: el breakeven prematuro ahorca los trades antes del TP.
BREAKEVEN_ATR_MULT = 9.9

# Límite máximo para retener un trade abierto antes de forzar cierre
MAX_HOLD_HOURS = 8      # Si no toca TP ni SL en 12h → cerrar al mercado

# ─── Comisiones ──────────────────────────────────────────────────────────────
TRADING_FEE_RATE = 0.001   # 0.1% por operación (Binance Spot estándar)
MIN_HOLD_HOURS   = 0.5     # 30 min mínimo antes de permitir salida (bajado de 1h)

# ─── Sistema ─────────────────────────────────────────────────────────────────
LOG_FILE         = "trading_bot.log"
DB_FILE          = "trades.db"
POLLING_INTERVAL = 60      # 60s entre ciclos
PAUSE_SIGNAL_FILE = ".bot_pause_signal"

# ─── Proxy ───────────────────────────────────────────────────────────────────
PROXY_URL = os.getenv("PROXY_URL")
