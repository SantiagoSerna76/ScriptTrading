#!/usr/bin/env python3
"""
GUÍA DE EJECUCIÓN - TRADING BOT PRODUCCIÓN ROADMAP

Este archivo documenta el flujo completo para:
1. Paper trading validation (2 semanas)
2. ML model training (con datos reales)
3. Production deployment ($200)
4. Continuous monitoring & circuit breaker
"""

# ─────────────────────────────────────────────────────────────────────────────
# FASE 1: PAPER TRADING VALIDATION (Semanas 1-2)
# ─────────────────────────────────────────────────────────────────────────────

"""
OBJETIVO: Generar 30-50 trades para entrenar modelo ML real

PASOS:
  1. Backup de config.py:
     $ cp config.py config_backup_original.py
  
  2. Usar config de paper trading:
     $ cp config_paper_training.py config.py
  
  3. Ejecutar bot en papel:
     $ python trading_bot.py
     
     El bot correrá sin ejecutar órdenes reales. Verás:
     - [PAPER] tags en los logs
     - Trades simulados escribiéndose en trades.db
     - Filtros activos rechazando entradas no válidas
  
  4. Ejecutar diariamente:
     $ python monitor_daily.py
     
     Verás resumen de:
     - P&L acumulado
     - Win rate actual
     - Últimos 5 trades
     - Alertas (si las hay)
  
  5. Después de 30+ trades:
     • Verificar win rate >= 55%
     • Verificar profit factor >= 1.5
     • Si falla: ajustar config.py y repetir
"""

# ─────────────────────────────────────────────────────────────────────────────
# FASE 2: ML MODEL TRAINING (Después de 30+ trades)
# ─────────────────────────────────────────────────────────────────────────────

"""
OBJETIVO: Entrenar modelo ML REAL con datos de paper trading

PASOS:
  1. Entrenar modelo:
     $ python train_real_ml_model.py
     
     Esto:
     - Carga 30+ trades cerrados de trades.db
     - Extrae features (SL distance, TP distance, risk/reward)
     - Entrena Random Forest o Gradient Boosting
     - Reemplaza ml_model.pkl con modelo real
     
     Verás output:
     ✅ Cargados N trades cerrados
     📊 Labels creadas: X ganancias, Y pérdidas
     🤖 Entrenando modelo...
     📊 Evaluando modelo...
     💾 Guardando modelo...
  
  2. Archivos generados:
     • ml_model_real.pkl (modelo entrenado)
     • ml_scaler_real.pkl (normalizador)
     • ml_feature_names.pkl (nombres de features)
     • ml_feature_list.json (información legible)
"""

# ─────────────────────────────────────────────────────────────────────────────
# FASE 3: PARAMETER OPTIMIZATION (Opcional, recomendado)
# ─────────────────────────────────────────────────────────────────────────────

"""
OBJETIVO: Encontrar RSI_MIN, ADX_MIN, ML_THRESHOLD óptimos

PASOS:
  1. Ejecutar grid search:
     $ python backtest_grid_search.py
     
     Esto:
     - Prueba todas las combinaciones de parámetros
     - Para cada combo, simula cuántos trades pasarían
     - Calcula win rate y profit factor
     - Retorna parámetros óptimos
     
     Verás output:
     🔍 Iniciando grid search... (48 combinaciones)
     📊 TOP 5 COMBINACIONES:
     1. RSI=50, ADX=20, ML=0.55 | WR: 58.2% | PF: 1.68x
     ...
     
  2. Archivos generados:
     • backtest_results.json (todas las combinaciones)
     • backtest_best_params.json (parámetros óptimos)
  
  3. Actualizar config.py:
     RSI_MIN = [valor del reporte]
     ADX_MIN = [valor del reporte]
     ML_THRESHOLD = [valor del reporte]
"""

# ─────────────────────────────────────────────────────────────────────────────
# FASE 4: PRODUCCIÓN REAL CON $200 (Después de validación)
# ─────────────────────────────────────────────────────────────────────────────

"""
⚠️ SOLO SI:
  • Win rate >= 55%
  • Profit factor >= 1.5
  • ML model entrenado
  • Grid search completado (opcional)

PASOS:
  1. Preparar config de producción:
     $ cp config_production_200.py config.py
     
     (O actualizar config.py con:
     - PAPER_TRADING = False
     - USE_TESTNET = False
     - CAPITAL_TOTAL_USDT = 200.0
     - RIESGO_POR_TRADE = 0.015
     - Parámetros optimizados del grid search)
  
  2. Ejecutar bot en producción:
     $ python trading_bot.py
     
     Verás:
     - [LIVE] tags (sin "PAPER")
     - Órdenes REALES ejecutadas en mainnet
     - Cada trade cuesta dinero real
  
  3. MONITOREO CRÍTICO - EJECUTAR CADA HORA:
     $ python monitor_daily.py
     
     Genera resumen de P&L, win rate, alertas
     
  4. HEALTH CHECK - EJECUTAR CADA 2 HORAS:
     $ python health_check.py
     
     Si detecta:
     • Win rate < 45%
     • Profit factor < 1.0
     • P&L < -$15
     • 3 pérdidas consecutivas
     
     PAUSA el bot automáticamente (crea .bot_pause_signal)
"""

# ─────────────────────────────────────────────────────────────────────────────
# PRIMER SEMANA EN PRODUCCIÓN - PROTOCOLO ESTRICTO
# ─────────────────────────────────────────────────────────────────────────────

"""
SCHEDULE:
  • 09:00 - Revisar monitor_daily.py
  • 10:00 - Revisar logs: tail -f trading_bot_production.log
  • 12:00 - Ejecutar monitor_daily.py + health_check.py
  • 15:00 - Revisar logs
  • 18:00 - Ejecutar monitor_daily.py + health_check.py
  • 21:00 - Ejecutar monitor_daily.py
  
QJECUTAR ANTES DE DORMIR:
  $ python health_check.py
  $ python monitor_daily.py
  
  Verificar en archivo monitor_daily.log:
  • ¿Win rate >= 55%?
  • ¿Profit factor >= 1.5?
  • ¿P&L positivo o apenas negativo?
  
  SI TODO ESTÁ BIEN:
    Dormir tranquilo, bot puede seguir 24/7
  
  SI ALGO ESTÁ MAL:
    Revisar health_check.log
    Si .bot_pause_signal existe: bot está pausado (revisar qué pasó)
    Considerar pause manual: $ touch .bot_pause_signal
"""

# ─────────────────────────────────────────────────────────────────────────────
# SCRIPTS DISPONIBLES - REFERENCIA RÁPIDA
# ─────────────────────────────────────────────────────────────────────────────

"""
1. train_real_ml_model.py
   Entrena modelo ML con datos reales
   $ python train_real_ml_model.py
   
   Entrada: trades.db (30+ trades)
   Salida: ml_model_real.pkl, ml_scaler_real.pkl

2. backtest_grid_search.py
   Optimiza parámetros
   $ python backtest_grid_search.py
   
   Entrada: trades.db
   Salida: backtest_best_params.json

3. monitor_daily.py
   Resumen diario del performance
   $ python monitor_daily.py
   
   Salida: monitor_daily.log + reporte en terminal

4. health_check.py
   Detecta problemas y pausa bot si es necesario
   $ python health_check.py
   
   Salida: health_check.log + archivo .bot_pause_signal (si hay problema)

5. config_paper_training.py
   Configuración para paper trading (2 semanas)
   $ cp config_paper_training.py config.py

6. config_production_200.py
   Configuración para producción con $200
   $ cp config_production_200.py config.py
"""

# ─────────────────────────────────────────────────────────────────────────────
# TROUBLESHOOTING
# ─────────────────────────────────────────────────────────────────────────────

"""
Q: ¿Cómo veo los logs del bot?
A: tail -f trading_bot_production.log (para seguir en vivo)
   or: less trading_bot_production.log (para revisar completo)

Q: ¿Cómo pausó el bot?
A: Revisa si existe .bot_pause_signal
   Si sí, ejecuta: python health_check.py (verás por qué pausó)

Q: ¿Cómo reanudo el bot?
A: Elimina .bot_pause_signal: rm .bot_pause_signal
   Luego: python trading_bot.py

Q: ¿Cómo veo el reporte de hoy?
A: python monitor_daily.py
   O: tail -50 monitor_daily.log

Q: ¿Cómo accedo a los datos de trades?
A: sqlite3 trades.db
   SELECT * FROM trades ORDER BY exit_time DESC LIMIT 10;

Q: ¿Cómo reentro el modelo ML?
A: python train_real_ml_model.py (carga trades nuevos automáticamente)

Q: ¿Cuándo debo retrain ML model?
A: Cada semana (domingos) después de ~20-30 trades nuevos
   O si win rate cae < 50%

Q: ¿Cuándo debo ejecutar grid search?
A: Después de cada reentrenamiento ML (opcional pero recomendado)
   O si notas que win rate no mejora
"""

# ─────────────────────────────────────────────────────────────────────────────
# ESCALADO - DESPUÉS DE 4 SEMANAS EXITOSAS
# ─────────────────────────────────────────────────────────────────────────────

"""
SI P&L > 0 Y WIN RATE >= 55% POR 4 SEMANAS:

1. Aumentar capital de $200 a $300-500
   (Modificar CAPITAL_TOTAL_USDT en config.py)

2. Agregar símbolo #3 (ahora: 3 pares en lugar de 2)
   (Agregar a SYMBOLS list)

3. Aumentar riesgo a 2% (de 1.5%)
   (RIESGO_POR_TRADE = 0.02)

4. Aumentar posiciones máximas a 3 (de 2)
   (MAX_OPEN_POSITIONS = 3)

5. Ejecutar grid search nuevamente con nueva capital
   (Parámetros pueden cambiar con capital mayor)

CRECIMIENTO ESPERADO:
• Semanas 1-4: $200 → $220-250 (10-25% ROI)
• Semanas 5-8: $250-300 → $350-450 (40-80% total)
• Mes 3: $400-500 → $700-1000+ (posible exponencial si win rate > 60%)
"""

# ─────────────────────────────────────────────────────────────────────────────
# RESUMEN DE COMANDOS
# ─────────────────────────────────────────────────────────────────────────────

"""
PAPEL TRADING (Semanas 1-2):
  $ cp config_paper_training.py config.py
  $ python trading_bot.py
  $ python monitor_daily.py  # Ejecutar diariamente

DESPUÉS DE 30+ TRADES:
  $ python train_real_ml_model.py
  $ python backtest_grid_search.py  # Opcional

ANTES DE PRODUCCIÓN:
  $ cp config_production_200.py config.py
  $ # Actualizar parámetros si necesario
  
PRODUCCIÓN ($200):
  $ python trading_bot.py
  $ python monitor_daily.py  # Cada 3 horas
  $ python health_check.py   # Cada 2 horas

SEMANAL (Domingos):
  $ python train_real_ml_model.py  # Retrain ML
  $ python backtest_grid_search.py  # Reoptimize parámetros
"""

# ─────────────────────────────────────────────────────────────────────────────
print("""
╔════════════════════════════════════════════════════════════════════════════════╗
║                   TRADING BOT - PLAN DE EJECUCIÓN 4 SEMANAS                   ║
╚════════════════════════════════════════════════════════════════════════════════╝

FASE 1: PAPER TRADING (Semanas 1-2)
  1. cp config_paper_training.py config.py
  2. python trading_bot.py
  3. python monitor_daily.py (cada día)
  Objetivo: 30+ trades, WR >= 55%, PF >= 1.5

FASE 2: ML TRAINING
  1. python train_real_ml_model.py
  2. python backtest_grid_search.py (opcional)
  Objetivo: Modelo real entrenado, parámetros optimizados

FASE 3: PRODUCCIÓN (Semana 4+)
  1. cp config_production_200.py config.py
  2. python trading_bot.py (DINERO REAL)
  3. python monitor_daily.py + health_check.py (24/7)
  Objetivo: Mantener WR >= 55%, crecimiento lento y estable

DOCUMENTACIÓN COMPLETA: Ver comentarios al inicio de este archivo
""")
