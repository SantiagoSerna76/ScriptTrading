"""
CONFIG PARA PRODUCCIÓN REAL CON $200

OBJETIVO:
  • Ejecutar bot con dinero REAL ($200)
  • Después de validar en paper trading
  
INSTRUCCIONES:
  1. Solo usar SI el paper trading pasó validación:
     - Win Rate >= 55%
     - Profit Factor >= 1.5
     - ML model entrenado
  
  2. Hacer backup de config.py actual
  3. Reemplazar config.py con este archivo
  4. Ejecutar: python trading_bot.py
  
⚠️ CRÍTICO: DINERO REAL - NO USAR SIN VALIDACIÓN PREVIA
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
# 🔴 PRODUCCIÓN REAL - DINERO REAL
# ─────────────────────────────────────────────────────────────────────────────
PAPER_TRADING = False   # ❌ PRODUCCIÓN REAL
USE_TESTNET = False     # ❌ MAINNET (dinero real)

# ─── Capital Real ─────────────────────────────────────────────────────────────
# ⚠️ ESTO ES DINERO REAL - SER CUIDADOSO
CAPITAL_TOTAL_USDT = 200.0  # $200 reales

# ─── Universo de Trading ─────────────────────────────────────────────────────
# Solo 2 pares para $200 - Menos riesgo
SYMBOLS = ['INJUSDT', 'ICPUSDT']

# ─── Riesgo y Posiciones - OPTIMIZADO PARA $200 ──────────────────────────────
RIESGO_POR_TRADE = 0.015        # 1.5% (bajado de 2%)
                                 # Cálculo: $200 × 1.5% = $3 riesgo/trade

MAX_OPEN_POSITIONS = 2          # Máximo 2 posiciones (bajado de 3)
                                 # Máximo en riesgo: $200 × 1.5% × 2 = $6

MIN_ORDER_NOTIONAL = 5.0        # Mínimo de Binance

# ─── Ajuste por Régimen ──────────────────────────────────────────────────────
POSITION_SIZE_TRENDING = 1.0
POSITION_SIZE_RANGING = 0.5
POSITION_SIZE_VOLATILE = 0.7
POSITION_SIZE_UNCERTAIN = 0.3

# ─── Protecciones Diarias - ESTRICTAS PARA $200 ──────────────────────────────
MAX_DAILY_LOSS_USDT = 3.0       # -3/200 = -1.5% max/día (circuit breaker)
                                 # Si pierdes $3, bot se detiene automáticamente

MAX_DAILY_TRADES = 4            # 4 trades máximo/día (menos es más con $200)

# ─── Cooldown entre Entradas ─────────────────────────────────────────────────
MIN_BUY_COOLDOWN_H = 2          # 2h entre entradas (más flexible)
MIN_BUY_COOLDOWN_S = MIN_BUY_COOLDOWN_H * 3600
SL_COOLDOWN_S = 3 * 3600        # 3h extra después de SL hit
CONSECUTIVE_LOSS_MAX = 2        # Pausa 12h tras 2 pérdidas

# ─── Indicadores Técnicos - MENOS RESTRICTIVOS ─────────────────────────────
TIMEFRAME = "1h"
KLINES_LIMIT = 500
EMA_CORTO = 20
EMA_LARGO = 50
RSI_PERIOD = 14
RSI_MIN = 50                    # Bajado de 55 (más oportunidades)
RSI_MAX = 72
ATR_PERIOD = 14
ATR_MULTIPLIER = 2.0
ADX_PERIOD = 14
ADX_MIN = 20                    # Bajado de 25 (menos restrictivo)

# ─── Fibonacci ────────────────────────────────────────────────────────────────
FIBONACCI_PERIOD = 50
FIBONACCI_BOUNCE_PCT = 0.8
FIBONACCI_EXT_TP = 1.272
FIBONACCI_REQUIRE_IN_WEAK = False  # Desactivado para más oportunidades

# ─── Stop Loss / Take Profit - MÁS AJUSTADO ────────────────────────────────
SL_ATR_MULT = 1.5               # Más ajustado (1.5 vs 2.0)
TP_ATR_MULT = 2.0               # TP más conservador (2.0 vs 2.5)
PARTIAL_TP_PCT = 1.5            # Cierre parcial al +1.5%

# ─── ML Filter ─────────────────────────────────────────────────────────────
# Usando modelo entrenado REAL
ML_THRESHOLD = 0.55             # Menos restrictivo (0.55 vs 0.60)

# ─── Trading ──────────────────────────────────────────────────────────────────
TRADING_FEE_RATE = 0.001
MIN_HOLD_HOURS = 1.0

# ─── Sistema ──────────────────────────────────────────────────────────────────
LOG_FILE = "trading_bot_production.log"  # Log separado para producción
DB_FILE = "trades.db"
POLLING_INTERVAL = 60  # 1 min entre ciclos

# ─────────────────────────────────────────────────────────────────────────────
# RESUMEN DE CONFIGURACIÓN PARA $200:
# ─────────────────────────────────────────────────────────────────────────────
"""
CAPITAL: $200

TAMAÑO POR TRADE:
  • Riesgo: $200 × 1.5% = $3/trade
  • Posición típica: $25-50
  • Máximo 2 abiertas: $50-100 en riesgo simultáneamente

PROTECCIONES:
  • Circuit breaker: -$3/día → bot se detiene
  • Máximo 4 trades/día
  • Cooldown 2h entre entradas
  • Pausa 12h tras 2 pérdidas consecutivas

FILTROS:
  • Win rate esperado: >= 55%
  • Profit factor: >= 1.5
  • ML threshold: 0.55

PRIMERA SEMANA:
  • Monitoreo diario de logs
  • Valida win rate real
  • Si < 45%: revisar estrategia
  • Si >= 55%: dejar crecer

ESCALADO:
  • Después 1 mes con P&L > 0:
    → Aumentar capital a $300-400
    → Agregar símbolos
    → Aumentar riesgo a 2%

ABANDONO:
  • Si P&L < -$20 en mes 1: pausar bot
  • Revisar modelo y parámetros
  • No perder más capital
"""
