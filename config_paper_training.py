"""
CONFIG PARA PAPER TRADING - VALIDACIÓN (Próximas 2 semanas)

OBJETIVO:
  • Ejecutar bot sin dinero real
  • Generar 30-50 trades de datos
  • Validar Win Rate >= 55%
  • Entrenar ML model REAL
  
INSTRUCCIONES:
  1. Hacer backup de config.py actual
  2. Reemplazar config.py con este archivo
  3. Ejecutar: python trading_bot.py
  4. Dejar corriendo 1-2 semanas
  5. Al finalizar: python train_real_ml_model.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Credenciales Binance ────────────────────────────────────────────────────
API_KEY    = os.getenv("BINANCE_API_KEY")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# ─── Telegram Notifier ───────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

# ─────────────────────────────────────────────────────────────────────────────
# 🔴 CRÍTICO: MODO PAPER TRADING (SIN DINERO REAL)
# ─────────────────────────────────────────────────────────────────────────────
PAPER_TRADING = True    # ✅ PAPEL, sin ejecutar órdenes reales
USE_TESTNET   = False   # ✅ MAINNET data (precios reales), pero sin ejecutar

# ─── Capital para Simulación ─────────────────────────────────────────────────
# Solo para simulación — NO afecta dinero real
CAPITAL_TOTAL_USDT = 500.0  # Simular con $500 virtual

# ─── Universo de Trading ─────────────────────────────────────────────────────
# Pares para validación (máximo 2-3 para debugging)
SYMBOLS = ['INJUSDT', 'ICPUSDT']

# ─── Riesgo y Posiciones ─────────────────────────────────────────────────────
RIESGO_POR_TRADE = 0.02         # 2% por trade
MAX_OPEN_POSITIONS = 3          # Máximo 3 posiciones
MIN_ORDER_NOTIONAL = 5.0        # Mínimo de Binance

# ─── Ajuste por Régimen ──────────────────────────────────────────────────────
POSITION_SIZE_TRENDING = 1.0
POSITION_SIZE_RANGING = 0.5
POSITION_SIZE_VOLATILE = 0.7
POSITION_SIZE_UNCERTAIN = 0.3

# ─── Protecciones Diarias ────────────────────────────────────────────────────
MAX_DAILY_LOSS_USDT = 10.0      # -10% de protección
MAX_DAILY_TRADES = 6            # 6 trades máximo/día

# ─── Cooldown entre Entradas ─────────────────────────────────────────────────
MIN_BUY_COOLDOWN_H = 4          # 4h entre entradas
MIN_BUY_COOLDOWN_S = MIN_BUY_COOLDOWN_H * 3600
SL_COOLDOWN_S = 4 * 3600        # 4h extra después de SL
CONSECUTIVE_LOSS_MAX = 2        # Pausa 12h tras 2 pérdidas

# ─── Indicadores Técnicos ────────────────────────────────────────────────────
TIMEFRAME = "1h"
KLINES_LIMIT = 500
EMA_CORTO = 20
EMA_LARGO = 50
RSI_PERIOD = 14
RSI_MIN = 55        # Conservador: momentum real
RSI_MAX = 72
ATR_PERIOD = 14
ATR_MULTIPLIER = 2.0
ADX_PERIOD = 14
ADX_MIN = 25        # Tendencia clara

# ─── Fibonacci ────────────────────────────────────────────────────────────────
FIBONACCI_PERIOD = 50
FIBONACCI_BOUNCE_PCT = 0.8     # Precisión
FIBONACCI_EXT_TP = 1.272
FIBONACCI_REQUIRE_IN_WEAK = True

# ─── Stop Loss / Take Profit ─────────────────────────────────────────────────
SL_ATR_MULT = 2.0
TP_ATR_MULT = 2.5
PARTIAL_TP_PCT = 2.0

# ─── Trading ──────────────────────────────────────────────────────────────────
TRADING_FEE_RATE = 0.001
MIN_HOLD_HOURS = 1.0

# ─── Sistema ──────────────────────────────────────────────────────────────────
LOG_FILE = "trading_bot_paper.log"  # Log separado para paper trading
DB_FILE = "trades.db"
POLLING_INTERVAL = 60  # 1 min entre ciclos
