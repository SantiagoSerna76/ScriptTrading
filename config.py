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
PAPER_TRADING = True    # True = simula trades sin ejecutar órdenes reales (RECOMENDADO para pruebas)
USE_TESTNET   = False   # False = usa Mainnet para datos reales de mercado

# ─── Universo de Trading ─────────────────────────────────────────────────────
# Seleccionados por scanner (30 pares, 60 días): solo símbolos con PF > 1.0 y P&L positivo
# Universo monitoreado. NEAR se conserva para gestionar una posición abierta existente.
SYMBOLS = ['INJUSDT', 'ICPUSDT', 'UNIUSDT', 'APTUSDT', 'FILUSDT', 'NEARUSDT']

# Monitorear todos los SYMBOLS, pero abrir nuevas entradas solo en los aprobados.
# Nuevas entradas: seleccionados por scanner MTF real (PF >= 1.5, WR >= 55%, trades >= 8).
ENTRY_SYMBOLS = [
    "SOLUSDT",
    "UNIUSDT",
    "RENDERUSDT",
    "ARBUSDT",
    "NEARUSDT",
    "INJUSDT",
]

# Reset estadístico tras auditoría cuantitativa. No borra la DB; solo evita mezclar
# resultados de configuraciones antiguas con la estrategia activa.
STRATEGY_START_TIME = "2026-05-24T00:58:00"

# ─── Capital y Riesgo ────────────────────────────────────────────────────────
CAPITAL_TOTAL_USDT   = 500.0   # Capital total que el bot puede usar
RIESGO_POR_TRADE     = 0.02    # 2% del capital por trade (base — Kelly lo ajusta dinámicamente)
MAX_OPEN_POSITIONS   = 2      # Bajado a 2 ($250 por posición) para concentrar el capital
MIN_ORDER_NOTIONAL   = 5.0     # Mínimo real de Binance para estos altcoins (verificado por get_symbol_rules)

# ─── Ajuste por Régimen de Mercado ───────────────────────────────────────────
POSITION_SIZE_TRENDING  = 1.0    # 100% en tendencia
POSITION_SIZE_RANGING   = 0.8    # 80% en rango (subido de 0.5 para no reducir tanto las ganancias)
POSITION_SIZE_VOLATILE  = 0.9    # 90% en volatilidad (subido de 0.7)
POSITION_SIZE_UNCERTAIN = 0.8    # 80% en normal/incertidumbre (subido de 0.6)


# ─── Relajación de filtros para acelerar acumulación de datos ─────────────────
# Símbolos donde se permite entrada aunque macro 4H sea neutral (no bajista).
# Útil en paper trading para generar más trades de entrenamiento ML.
RELAXED_MACRO_SYMBOLS = []

# ─── Protección diaria ───────────────────────────────────────────────────────
MAX_DAILY_LOSS_USDT  = 8.0     # Si perdemos $8 en el día → circuit breaker (ajustado a 3 posiciones × $167)
MAX_DAILY_TRADES     = 10      # Subido de 6→10 en paper trading para acelerar recolección de datos ML

# ─── Cooldown entre entradas ─────────────────────────────────────────
MIN_BUY_COOLDOWN_H   = 4      # 4h mínimo entre entradas del mismo par (evita señales falsas consecutivas)
MIN_BUY_COOLDOWN_S = MIN_BUY_COOLDOWN_H * 3600   # 4h de cooldown en segundos
SL_COOLDOWN_S        = 4 * 3600     # 4h de cooldown extra después de un Stop Loss (mercado en contra)
CONSECUTIVE_LOSS_MAX = 2            # Tras 2 pérdidas consecutivas en un símbolo → pausa de 12h

# ─── Indicadores técnicos ────────────────────────────────────────────────────
TIMEFRAME       = "1h"
KLINES_LIMIT    = 500   # Datos suficientes para EMA200 + margen (estabilización)
EMA_CORTO       = 20
EMA_LARGO       = 50
RSI_PERIOD      = 14
RSI_MIN         = 55    # Optimizado cuantitativamente (55): balance entre WR y PF
RSI_MAX         = 72
ATR_PERIOD      = 14
ATR_MULTIPLIER  = 2.0
ADX_PERIOD      = 14
ADX_MIN         = 25    # Relajado de 27: tendencia clara sin exigir extremos

# ─── Fibonacci ──────────────────────────────────────────────────────────────────
FIBONACCI_PERIOD = 50   # Velas para encontrar swing high/low y calcular retrazos
FIBONACCI_BOUNCE_PCT = 0.8  # % de tolerancia para considerar un "bounce" en soporte Fibonacci (bajado de 1.0→0.8: más preciso)
FIBONACCI_EXT_TP = 1.272    # Extensión Fibonacci para take profit parcial (127.2%)
FIBONACCI_REQUIRE_IN_WEAK = True  # True = exige soporte Fibonacci para entrar en regímenes CHOPPY/RANGE

# ─── Stop Loss / Take Profit ─────────────────────────────────────────────────
SL_ATR_MULT = 1.8   # Stop Loss = entry - (SL_ATR_MULT * ATR) [Optimizado de 2.0 a 1.8]
TP_ATR_MULT = 2.3   # Take Profit = entry + (TP_ATR_MULT * ATR) [Optimizado de 2.5 a 2.3]
PARTIAL_TP_PCT = 1.5  # % de ganancia para activar Venta Parcial [Optimizado cuantitativamente a 1.5% para asegurar ganancias rapido]

# ─── Comisiones y Retención ──────────────────────────────────────────────────
TRADING_FEE_RATE = 0.001   # 0.1% por operación (Binance Spot estándar)
MIN_HOLD_HOURS   = 1.0    # Mínimo 1h antes de permitir salida por señal (evita ruido intra-vela)

# ─── Sistema ─────────────────────────────────────────────────────────────────
LOG_FILE         = "trading_bot.log"
DB_FILE          = "trades.db"
POLLING_INTERVAL = 60   # 1 min entre ciclos

# ─── Proxy (para evitar bloqueos IP en Render/nube) ──────────────────────────
PROXY_URL = os.getenv("PROXY_URL")  # Formato: http://user:pass@ip:port
