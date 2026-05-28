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
SYMBOLS = ["INJUSDT", "RENDERUSDT", "SOLUSDT", "NEARUSDT", "ARBUSDT", "MATICUSDT"]

# Monitorear todos los SYMBOLS, pero abrir nuevas entradas solo en los aprobados.
# Nuevas entradas: seleccionados por scanner MTF real (PF >= 1.5, WR >= 55%, trades >= 8).
ENTRY_SYMBOLS = [
    "INJUSDT",
    "RENDERUSDT",
    "SOLUSDT",
    "NEARUSDT",
    "ARBUSDT",
    "MATICUSDT",
]

# Reset estadístico tras auditoría cuantitativa. No borra la DB; solo evita mezclar
# resultados de configuraciones antiguas con la estrategia activa.
STRATEGY_START_TIME = "2026-05-24T00:58:00"

# ─── Capital y Riesgo ────────────────────────────────────────────────────────
CAPITAL_TOTAL_USDT   = 500.0   # Capital total que el bot puede usar
RIESGO_POR_TRADE     = 0.03    # 3% del capital por trade (subido de 2% — con 75% WR y SL dinámico es seguro)
MAX_OPEN_POSITIONS   = 3      # Máximo de posiciones simultáneas ($167 por posición con 5 símbolos)
MIN_ORDER_NOTIONAL   = 5.0     # Mínimo real de Binance para estos altcoins (verificado por get_symbol_rules)

# ─── Ajuste por Régimen de Mercado ───────────────────────────────────────────
POSITION_SIZE_TRENDING  = 1.0    # 100% en tendencia
POSITION_SIZE_RANGING   = 0.8    # 80% en rango (subido de 0.5 para no reducir tanto las ganancias)
POSITION_SIZE_VOLATILE  = 0.9    # 90% en volatilidad (subido de 0.7)
POSITION_SIZE_UNCERTAIN = 0.8    # 80% en normal/incertidumbre (subido de 0.6)


# ─── Relajación de filtros para acelerar acumulación de datos ─────────────────
# Símbolos donde se permite entrada aunque macro 4H sea neutral (no bajista).
# Útil en paper trading para generar más trades de entrenamiento ML.
RELAXED_MACRO_SYMBOLS = ["INJUSDT", "RENDERUSDT", "SOLUSDT"]

# ─── Protección diaria ───────────────────────────────────────────────────────
MAX_DAILY_LOSS_USDT  = 8.0     # Si perdemos $8 en el día → circuit breaker (ajustado a 3 posiciones × $167)
MAX_DAILY_TRADES     = 20      # 15MIN genera más señales → permitir más trades para alimentar ML

# ─── Cooldown entre entradas ─────────────────────────────────────────
MIN_BUY_COOLDOWN_H   = 1      # 1h mínimo entre entradas del mismo par (reducido para 15min)
MIN_BUY_COOLDOWN_S = MIN_BUY_COOLDOWN_H * 3600   # 1h de cooldown en segundos
SL_COOLDOWN_S        = 2 * 3600     # 2h de cooldown extra después de un Stop Loss
CONSECUTIVE_LOSS_MAX = 2            # Tras 2 pérdidas consecutivas en un símbolo → pausa de 4h

# ─── Indicadores técnicos ────────────────────────────────────────────────────
TIMEFRAME       = "15m"  # Migrado de 1H a 15MIN para más trades y menor volatilidad
KLINES_LIMIT    = 1000   # 1000 velas × 15min = 10.4 días (suficiente para EMA200 + warmup)
EMA_CORTO       = 20
EMA_LARGO       = 50
RSI_PERIOD      = 14
RSI_MIN         = 56    # Optimizado cuantitativamente (56): balance solicitado por el usuario
RSI_MAX         = 72
ATR_PERIOD      = 14
ATR_MULTIPLIER  = 2.0
ADX_PERIOD      = 14
ADX_MIN         = 20    # Reducido a 20 para 15min (ADX es naturalmente más bajo en timeframes cortos)

# ─── Fibonacci ──────────────────────────────────────────────────────────────────
FIBONACCI_PERIOD = 200  # 200×15min = 50h (equivalente a 50×1H para misma cobertura temporal)
FIBONACCI_BOUNCE_PCT = 0.8  # % de tolerancia para considerar un "bounce" en soporte Fibonacci (bajado de 1.0→0.8: más preciso)
FIBONACCI_EXT_TP = 1.272    # Extensión Fibonacci para take profit parcial (127.2%)
FIBONACCI_REQUIRE_IN_WEAK = True  # True = exige soporte Fibonacci para entrar en regímenes CHOPPY/RANGE

# ─── Stop Loss / Take Profit ─────────────────────────────────────────────────
SL_ATR_MULT = 1.8   # Stop Loss = entry - (SL_ATR_MULT * ATR) [Optimizado de 2.0 a 1.8]
TP_ATR_MULT = 2.3   # Take Profit = entry + (TP_ATR_MULT * ATR) [Optimizado de 2.5 a 2.3]
PARTIAL_TP_PCT = 1.0  # % de ganancia para activar Venta Parcial [Ajustado para 15min: tomas de ganancia rápidas]

# ─── Comisiones y Retención ──────────────────────────────────────────────────
TRADING_FEE_RATE = 0.001   # 0.1% por operación (Binance Spot estándar)
MIN_HOLD_HOURS   = 0.25   # Mínimo 15min (1 vela) antes de permitir salida por señal

# ─── Sistema ─────────────────────────────────────────────────────────────────
LOG_FILE         = "trading_bot.log"
DB_FILE          = "trades.db"
POLLING_INTERVAL = 45   # 45s entre ciclos (más frecuente para capturar señales de 15min)

# ─── Proxy (para evitar bloqueos IP en Render/nube) ──────────────────────────
PROXY_URL = os.getenv("PROXY_URL")  # Formato: http://user:pass@ip:port
