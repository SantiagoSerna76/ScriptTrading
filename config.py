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

# ─── Universo de Trading (60 monedas) ─────────────────────────────────────────
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "SHIBUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT",
    "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
    "FILUSDT", "AAVEUSDT", "INJUSDT", "RENDERUSDT", "FETUSDT",
    "PEPEUSDT", "WIFUSDT", "FLOKIUSDT", "TRXUSDT", "ICPUSDT",
    "BCHUSDT", "ETCUSDT", "STXUSDT", "IMXUSDT", "VETUSDT",
    "THETAUSDT", "FTMUSDT", "ALGOUSDT", "SANDUSDT", "MANAUSDT",
    "GALAUSDT", "EGLDUSDT", "AXSUSDT", "KASUSDT", "TONUSDT",
    "SEIUSDT", "TIAUSDT", "TAOUSDT", "ORDIUSDT", "RUNEUSDT",
    "ASTRUSDT", "AGIXUSDT", "OCEANUSDT", "ROSEUSDT", "CHZUSDT",
    "QNTUSDT", "MKRUSDT", "SNXUSDT", "CRVUSDT", "LDOUSDT"
]
ENTRY_SYMBOLS = SYMBOLS.copy()
RELAXED_MACRO_SYMBOLS = SYMBOLS.copy()

# Reset estadístico — fecha de inicio de la estrategia Pullback Sniper
STRATEGY_START_TIME = "2026-05-28T23:00:00"

# ─── Capital y Riesgo ────────────────────────────────────────────────────────
CAPITAL_TOTAL_USDT   = 500.0
RIESGO_POR_TRADE     = 0.02    # 2% del capital por trade (conservador)
MAX_OPEN_POSITIONS   = 3       # Máximo de posiciones simultáneas
MIN_ORDER_NOTIONAL   = 5.0     # Mínimo de Binance

# ─── Protección diaria ───────────────────────────────────────────────────────
MAX_DAILY_LOSS_USDT  = 10.0    # $10 máximo de pérdida diaria (2% del capital)
MAX_DAILY_TRADES     = 10      # Máximo 10 trades/día en 1H

# ─── Cooldown entre entradas ─────────────────────────────────────────────────
MIN_BUY_COOLDOWN_H   = 2       # 2h mínimo entre entradas del mismo par
MIN_BUY_COOLDOWN_S   = MIN_BUY_COOLDOWN_H * 3600
SL_COOLDOWN_S        = 4 * 3600    # 4h de cooldown después de un Stop Loss
CONSECUTIVE_LOSS_MAX = 3            # Tras 3 pérdidas consecutivas → pausa de 6h

# ─── Indicadores técnicos ────────────────────────────────────────────────────
TIMEFRAME       = "1h"    # Temporalidad principal: 1 Hora
KLINES_LIMIT    = 500     # 500 velas × 1h = 20.8 días (suficiente para EMA200)
EMA_CORTO       = 20      # EMA rápida
EMA_LARGO       = 50      # EMA lenta
RSI_PERIOD      = 14
ATR_PERIOD      = 14
ADX_PERIOD      = 14
ADX_MIN         = 20      # Mínimo para confirmar que hay tendencia

# ─── Stop Loss / Take Profit ────────────────────────────────────────────────
SL_ATR_MULT     = 2.0     # SL = entry - (2.0 × ATR) para soportar el pánico
MAX_SL_PCT      = 8.0     # Si SL natural > 8% del entry → rechazar trade (Pánico extremo)

# ─── Comisiones y Retención ──────────────────────────────────────────────────
TRADING_FEE_RATE = 0.001   # 0.1% por operación (Binance Spot estándar)
MIN_HOLD_HOURS   = 1.0     # Mínimo 1 hora antes de permitir salida

# ─── Sistema ─────────────────────────────────────────────────────────────────
LOG_FILE         = "trading_bot.log"
DB_FILE          = "trades.db"
POLLING_INTERVAL = 60      # 60s entre ciclos (1H no necesita menos)

# ─── Proxy ───────────────────────────────────────────────────────────────────
PROXY_URL = os.getenv("PROXY_URL")
