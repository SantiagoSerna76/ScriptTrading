# 🏗️ Arquitectura del Bot Trading — Estructura del Proyecto

## 📁 Estructura de Archivos

```
tradingV2/
│
├── 🆕 mtf_analyzer.py          ← Análisis Multi-Timeframe (4H + 1H)
├── 🆕 microstructure.py        ← Order Book Analyzer (detecta muros)
├── 🆕 IMPROVEMENTS.md          ← Documentación de las 3 mejoras
├── 🆕 QUICKSTART.md            ← Guía rápida de uso
├── 🆕 ARCHITECTURE.md          ← Este archivo
│
├── ✏️ strategy.py              ← Modificado: Agregada clase TrailingStopManager
├── ✏️ trading_bot.py           ← Modificado: Integración de MTF, OB, Trailing Stop
├── ✏️ backtest.py              ← Modificado: Usa trailing stop dinámico
├── ✏️ requirements.txt          ← Modificado: Añadidas dependencias
│
├── config.py                   ← Configuración (NO MODIFICADO)
├── binance_api.py              ← API de Binance (NO MODIFICADO)
├── database.py                 ← Base de datos de trades (NO MODIFICADO)
├── check_keys.py               ← Validador de credenciales (NO MODIFICADO)
├── analyzer.py                 ← Análisis técnico (NO MODIFICADO)
│
├── .env                        ← Credenciales Binance (crear manualmente)
├── trading_bot.log             ← Logs de ejecución (generado automáticamente)
└── trades.db                   ← Base de datos SQLite (generado automáticamente)
```

---

## 🔄 Flujo de Datos

### 1️⃣ **Obtención de Datos (Binance)**
```
Binance API
    ↓
binance_api.py (get_klines, get_order_book)
    ↓
    ├── klines 1H  → parse_klines_to_dataframe()
    └── klines 4H  → parse_klines_to_dataframe()
```

### 2️⃣ **Análisis Técnico**
```
DataFrame 1H + 4H
    ↓
strategy.py (calculate_indicators)
    ├── EMA (short/long)
    ├── RSI (Wilder)
    ├── ATR
    ├── ADX
    ├── MACD
    ├── Stochastic
    └── Bollinger Bands
    ↓
mtf_analyzer.py (MultiTimeframeAnalyzer)
    ├── analyze_macro_trend() → validación 4H
    └── validate_entry_with_macro() → combinado 1H + 4H
```

### 3️⃣ **Validación de Microestructura**
```
Señal de Compra (1H + 4H)
    ↓
microstructure.py (OrderBookAnalyzer)
    ├── pre_order_check()
    ├── detect_sell_wall()
    ├── calculate_imbalance()
    └── validate_order_liquidity()
    ↓
¿Proceder? (SÍ / NO)
```

### 4️⃣ **Ejecución de Orden**
```
Validaciones OK
    ↓
trading_bot.py (_open_trade)
    ├── Calcula Position Size (strategy.RiskManager)
    ├── Coloca orden MARKET BUY (binance_api)
    └── Guarda en BD (database.py)
```

### 5️⃣ **Gestión de Posición Abierta**
```
Posición Abierta
    ↓
trading_bot.py (_check_exit)
    ├── update_trailing_stop() → Sube SL dinámicamente
    ├── Verifica exit_score() → Señales de salida
    └── ¿Cierre? SÍ/NO
    ↓
Si cierre:
    └── trading_bot.py (_close_trade) → Venta + registro en BD
```

---

## 📊 Clases Principales

### 🔹 `strategy.py`

#### **StrategySignals**
- Método: `calculate_indicators()` → Calcula 9+ indicadores
- Método: `check_buy_signal()` → Genera señal de compra (score-based)
- Método: `exit_score()` → Genera señal de salida
- Método: `calculate_sl_tp()` → SL y TP iniciales basados en ATR

#### **RiskManager** (Gestión de Riesgo)
- `position_size()` → Cantidad a comprar basado en riesgo %
- `validate_trade()` → Valida notional mínimo

#### **🆕 TrailingStopManager** (NUEVO)
- `update_trailing_stop()` → Recalcula SL dinámico cada vela
- `should_close_trailing()` → Verifica si toca SL
- `calculate_partial_exit()` → Cierre parcial (opcional)

---

### 🔹 `mtf_analyzer.py` (NUEVO)

#### **MultiTimeframeAnalyzer**
- `analyze_macro_trend(df_4h)` → Valida tendencia en 4H
  - ✅ Precio > EMA200
  - ✅ EMA20 > EMA50
  - ✅ MACD bullish
  - ✅ ADX > 20 (tendencia)

- `validate_entry_with_macro(df_1h, macro, signal_1h, conds)` → Combina 4H + 1H
  - Devuelve: (señal_combinada, detalles)

---

### 🔹 `microstructure.py` (NUEVO)

#### **OrderBookAnalyzer**
- `get_order_book(symbol, limit)` → Obtiene order book de Binance
- `detect_sell_wall(symbol, price)` → Detecta muros de venta
  - Severity: LOW / MEDIUM / HIGH
- `detect_buy_wall(symbol, price)` → Detecta soportes
- `calculate_imbalance(symbol)` → Ratio buy/sell
  - Sentiment: BULLISH / NEUTRAL / BEARISH
- `pre_order_check(symbol, price, qty)` → Validación final
  - Devuelve: (puede_ejecutar, detalles)

---

### 🔹 `trading_bot.py` (Principal)

#### **TradingBot**
- `__init__()` → Inicializa todos los analizadores + API
- `run()` → Loop principal (infinito con sleep)
- `_cycle()` → Un ciclo completo
- `_analyze(symbol)` → Analiza 1 símbolo
  - ✅ Obtiene datos 1H + 4H
  - ✅ Valida MTF
  - ✅ Genera señal combinada
- `_open_trade(symbol, df, conds)` → Abre posición
  - ✅ Valida Order Book
  - ✅ Calcula tamaño
  - ✅ Ejecuta orden
- `_check_exit(symbol, price, df)` → Verifica salida
  - ✅ Actualiza trailing stop
  - ✅ Verifica señales de salida
- `_close_trade(symbol, price, trade_id, reason)` → Cierra posición

---

## 🔌 Conexiones Internas

```python
# En __init__ de TradingBot:
self.api = BinanceAPI(API_KEY, SECRET_KEY)          # Conexión Binance
self.strategy = StrategySignals()                   # Indicadores técnicos
self.risk = RiskManager()                           # Sizing
self.mtf = MultiTimeframeAnalyzer()                 # Análisis 4H+1H
self.ob = OrderBookAnalyzer(API_KEY, SECRET_KEY)    # Order Book
self.trailing = TrailingStopManager()               # Trailing stop
self.db = TradeDatabase()                           # Guardado de trades
```

---

## 🎯 Flujo Completo de 1 Iteración

```
┌─────────────────────────────────────────┐
│ run() → _cycle() cada POLLING_INTERVAL  │
└──────────────┬──────────────────────────┘
               ↓
      ┌────────────────────┐
      │ Para cada símbolo: │
      │ _analyze(symbol)   │
      └────────┬───────────┘
               ↓
    ┌──────────────────────────┐
    │ Obtiene datos 1H y 4H    │
    │ de Binance API           │
    └────────┬─────────────────┘
             ↓
    ┌──────────────────────────────────┐
    │ strategy.calculate_indicators()  │
    │ Calcula 9+ indicadores técnicos  │
    └────────┬─────────────────────────┘
             ↓
    ┌──────────────────────────────────┐
    │ ¿Ya hay posición abierta?        │
    └──┬──────────────────────────┬────┘
       │ SÍ                       │ NO
       ↓                          ↓
  _check_exit()          ┌─────────────────────────┐
    • Actualiza          │ mtf.analyze_macro_trend │
      trailing stop      │ (validar 4H)            │
    • Verifica salida    └────────┬────────────────┘
    • Cierra si toca SL           ↓
       o señal de salida  ┌─────────────────────────┐
                          │ strategy.check_buy_signal
                          │ (validar 1H)            │
                          └────────┬────────────────┘
                                   ↓
                   ┌───────────────────────────────────┐
                   │ mtf.validate_entry_with_macro()  │
                   │ Combina 4H + 1H                  │
                   └────────┬──────────────────────────┘
                            ↓
                   ┌────────────────────────┐
                   │ ¿Señal MTF válida?     │
                   └──┬──────────┬──────────┘
                      │ NO       │ SÍ
                      ↓          ↓
                    Skip    ┌──────────────────────────┐
                            │ ob.pre_order_check()     │
                            │ Valida Order Book        │
                            └────────┬─────────────────┘
                                     ↓
                            ┌────────────────────┐
                            │ ¿Order Book OK?    │
                            └──┬─────────┬──────┘
                               │ NO      │ SÍ
                               ↓         ↓
                             Skip    _open_trade()
                                   • Calcula tamaño
                                   • Ejecuta orden
                                   • Guarda en BD
```

---

## 🔐 Protecciones (Circuit Breakers)

```
┌─────────────────────────────────────────────┐
│ Cada ciclo verifica:                        │
├─────────────────────────────────────────────┤
│ 1. Pérdida diaria > MAX_DAILY_LOSS_USDT     │
│    → CIRCUIT BREAKER: Para trading por hoy  │
│                                             │
│ 2. Trades hoy > MAX_DAILY_TRADES            │
│    → CIRCUIT BREAKER: Limita entrada        │
│                                             │
│ 3. Cooldown por símbolo                     │
│    → No re-entrar en mismo par              │
│       antes de X horas                      │
│                                             │
│ 4. Máx posiciones abiertas                  │
│    → No abrir si ya hay X posiciones        │
│                                             │
│ 5. Validación Order Book                    │
│    → No operar si hay muros gigantes        │
└─────────────────────────────────────────────┘
```

---

## 📈 Base de Datos (SQLite)

```sql
-- trades.db contendrá:

-- Tabla: trades (entradas)
trades (
  id INTEGER PRIMARY KEY,
  symbol TEXT,
  entry_price FLOAT,
  quantity FLOAT,
  stop_loss FLOAT,
  take_profit FLOAT,
  timestamp DATETIME,
  reason TEXT
)

-- Tabla: exits (salidas)
exits (
  id INTEGER PRIMARY KEY,
  trade_id INTEGER,
  exit_price FLOAT,
  quantity FLOAT,
  pnl FLOAT,
  exit_reason TEXT,
  timestamp DATETIME
)

-- Tabla: indicators (log de indicadores)
indicators (
  id INTEGER PRIMARY KEY,
  symbol TEXT,
  ema_short FLOAT,
  ema_long FLOAT,
  rsi FLOAT,
  atr FLOAT,
  adx FLOAT,
  volume FLOAT,
  timestamp DATETIME
)
```

---

## 🚀 Escalabilidad Futura

### Mejoras Potenciales
- ✅ **WebSocket**: Datos en tiempo real en lugar de REST
- ✅ **ML**: Optimización automática de parámetros
- ✅ **Futuros**: Agregar trading de derivados
- ✅ **Liquidación**: Múltiples exchanges
- ✅ **Alertas**: Telegram/Discord notifications
- ✅ **Dashboard**: Web UI para monitoreo

---

**¡Tu bot está LISTO para operar en serio! 🚀**
