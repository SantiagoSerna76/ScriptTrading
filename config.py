import os
from dotenv import load_dotenv

load_dotenv()

# ─── Credenciales Binance ────────────────────────────────────────────────────
API_KEY    = os.getenv("BINANCE_API_KEY")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# ─── Modo de Operación ───────────────────────────────────────────────────────
PAPER_TRADING = True    # True = simula trades sin ejecutar órdenes reales (RECOMENDADO para pruebas)
USE_TESTNET   = False   # False = usa Mainnet para datos reales de mercado

# ─── Universo de Trading ─────────────────────────────────────────────────────
# Seleccionados por scanner.py: PF ≥ 1.3 y P&L positivo tras comisiones (60 días)
SYMBOLS = ["INJUSDT", "ICPUSDT", "MATICUSDT", "SUIUSDT", "TRXUSDT", "NEARUSDT"]

# ─── Capital y Riesgo ────────────────────────────────────────────────────────
CAPITAL_TOTAL_USDT   = 100.0   # Capital total que el bot puede usar
RIESGO_POR_TRADE     = 0.02    # 2% del capital por trade (ajustado para $100 de capital)
MAX_OPEN_POSITIONS   = 3       # Máximo de posiciones simultáneas (subido de 2→3 para más diversificación)
MIN_ORDER_NOTIONAL   = 5.0     # Mínimo real de Binance para estos altcoins (verificado por get_symbol_rules)

# ─── Protección diaria ───────────────────────────────────────────────────────
MAX_DAILY_LOSS_USDT  = 5.0     # Si perdemos $5 en el día → circuit breaker
MAX_DAILY_TRADES     = 10      # No más de 10 trades por día

# ─── Cooldown entre entradas ─────────────────────────────────────────────────
MIN_BUY_COOLDOWN_S   = 4 * 3600   # 4 horas mínimo entre entradas del mismo par

# ─── Indicadores técnicos ────────────────────────────────────────────────────
TIMEFRAME       = "1h"
KLINES_LIMIT    = 500   # Datos suficientes para EMA200 + margen (estabilización)
EMA_CORTO       = 20
EMA_LARGO       = 50
RSI_PERIOD      = 14
RSI_MIN         = 58    # Más restrictivo: momentum fuerte (era 56)
RSI_MAX         = 72
ATR_PERIOD      = 14
ATR_MULTIPLIER  = 2.0
ADX_PERIOD      = 14
ADX_MIN         = 27    # Más restrictivo: tendencia muy clara (era 25)

# ─── Stop Loss / Take Profit ─────────────────────────────────────────────────
SL_ATR_MULT = 3.0   # Stop Loss = entry - (SL_ATR_MULT * ATR) — Aumentado para máximo respaldo
TP_ATR_MULT = 3.0   # Take Profit = entry + (TP_ATR_MULT * ATR)  ← ratio 1:1

# ─── Comisiones y Retención ──────────────────────────────────────────────────
TRADING_FEE_RATE = 0.001   # 0.1% por operación (Binance Spot estándar)
MIN_HOLD_HOURS   = 3       # Mínimo 3 horas antes de permitir salida por señal

# ─── Sistema ─────────────────────────────────────────────────────────────────
LOG_FILE         = "trading_bot.log"
DB_FILE          = "trades.db"
POLLING_INTERVAL = 60   # segundos entre ciclos
