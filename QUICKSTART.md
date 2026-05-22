# 🚀 QUICKSTART — Cómo ejecutar el bot mejorado

## 📋 Requisitos previos
- Python 3.8+
- Cuenta Binance (Testnet o Real)
- API Key + Secret Key de Binance

---

## ⚡ Setup Rápido (5 minutos)

### 1. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 2. Configurar credenciales
Crea un archivo `.env` en la carpeta raíz:
```
BINANCE_API_KEY=tu_api_key_aqui
BINANCE_SECRET_KEY=tu_secret_key_aqui
```

⚠️ **Nunca** comitees el `.env` a Git

### 3. Revisar config.py
```python
# Cambia estos valores según necesites:
CAPITAL_TOTAL_USDT = 100.0      # Capital a usar
RIESGO_POR_TRADE = 0.01         # 1% por trade
MAX_OPEN_POSITIONS = 2          # Máximo 2 trades abiertos
MAX_DAILY_LOSS_USDT = 5.0       # Si pierdes $5 al día → parar
TIMEFRAME = "1h"                # Usar 1H para entrada
SYMBOLS = ["BTCUSDT", "ETHUSDT"]  # Qué tradear
```

---

## 🧪 Paso 1: Backtest (MUY IMPORTANTE)

Antes de operar en real, **SIEMPRE** valida con backtest:

```bash
python backtest.py
```

### Qué buscar en los resultados:
```
Capital inicial : $100.00
Capital final   : $127.35  (ROI +27.35%)
Trades          : 12  (✅ 8 ganadores  ❌ 4 perdedores)
Win Rate        : 66.7%
Profit Factor   : 2.15   (>1.5 = BUENO ✅)
Max Drawdown    : -8.5%
```

**Criterios mínimos para operar:**
- ✅ Win Rate > 50%
- ✅ Profit Factor > 1.5
- ✅ Drawdown < 15%
- ✅ ROI positivo en últimos 60 días

Si no cumple → **Ajusta parámetros en config.py** y repite backtest

---

## 🎯 Paso 2: Paper Trading (Recomendado)

Si tienes Binance Testnet:
```python
# En config.py
BASE_URL = "https://testnet.binance.vision"  # Cambiar a testnet
```

Luego ejecuta:
```bash
python trading_bot.py
```

**Ventajas:**
- Sin dinero real en riesgo
- Validas la estrategia en "vivo"
- Detectas bugs antes de usar capital real

---

## 💰 Paso 3: Trading en Vivo

### Pre-requisitos
1. ✅ Backtest validado (ROI +, Win Rate > 50%)
2. ✅ Paper trading 1-2 semanas sin problemas
3. ✅ Revisor de logs (`trading_bot.log`) diariamente
4. ✅ Máximo $100-500 de capital inicial

### Ejecutar
```bash
python trading_bot.py
```

### Monitorear
```bash
# En otra terminal:
tail -f trading_bot.log

# O en Windows:
Get-Content trading_bot.log -Wait
```

---

## 📊 Entender los Logs

### Entrada (Entry)
```
============================================================
🟢  SEÑAL DE COMPRA: BTCUSDT
    Score       : 9/7
    Precio      : $45,234.50
    Stop Loss   : $44,200.00  (-2.27%)
    Take Profit : $47,300.00  (DESACTIVADO - Trailing Stop)
    Cantidad    : 0.00221  (notional $100.00)
    ATR         : $1,200.50
    ✅  Order Book OK para BTCUSDT | Imbalance: BULLISH
============================================================
✅  Compra ejecutada: BTCUSDT #42
```

**Significado:**
- `Score 9/7` = 9 puntos vs mínimo 7 requeridos ✅
- `Trailing Stop` activado (sin TP fijo)
- Order Book validó que hay liquidez

### Actualización de Trailing Stop
```
BTCUSDT | Trailing SL actualizado: $44,200.00 → $44,950.50 (+1.74%)
BTCUSDT | Trailing SL actualizado: $44,950.50 → $45,100.20 (+0.33%)
```

**Significado:** El SL está subiendo con el precio → capturando la onda

### Salida (Exit)
```
============================================================
✅  VENTA: BTCUSDT — Trailing Stop (SL $45,100.20)
    Entrada: $45,234.50 → Salida: $45,100.50
    P&L    : +$310.42  (+0.30%)
============================================================
```

**Significado:** Ganancia en la posición

---

## 🔧 Ajustar Parámetros

Si no es rentable, **experimenta con:**

### Más agresivo (más trades)
```python
EMA_CORTO = 15  # Más rápido (default: 20)
EMA_LARGO = 40  # Menos restrictivo (default: 50)
RSI_MIN = 45    # Menos restrictivo (default: 52)
ADX_MIN = 18    # Menos restrictivo (default: 22)
```

### Menos agresivo (menos trades, pero mejores)
```python
EMA_CORTO = 25  # Más lento
EMA_LARGO = 60  # Más restrictivo
RSI_MIN = 58    # Más restrictivo
ADX_MIN = 26    # Más restrictivo
```

### Más rentable (arriesga más)
```python
RIESGO_POR_TRADE = 0.02  # 2% por trade (default: 1%)
SL_ATR_MULT = 1.5        # SL más apretado (default: 2.0)
TP_ATR_MULT = 4.0        # TP más lejano (default: 3.0)
```

### Más seguro (arriesga menos)
```python
RIESGO_POR_TRADE = 0.005  # 0.5% por trade
SL_ATR_MULT = 2.5         # SL más ancho
MAX_OPEN_POSITIONS = 1    # Solo 1 trade abierto
MAX_DAILY_LOSS_USDT = 3.0  # Para si pierdes $3
```

---

## ❓ Troubleshooting

### Error: "Sin datos para BTCUSDT"
```
Causa: Problema de conectividad con Binance
Solución: Espera 30 segundos e intenta de nuevo
```

### Error: "API rate limit"
```
Causa: Demasiadas llamadas a la API
Solución: Aumenta POLLING_INTERVAL en config.py
POLLING_INTERVAL = 120  # Esperar 2 minutos entre ciclos
```

### Error: "Orden rechazada: Saldo insuficiente"
```
Causa: No hay capital suficiente
Solución: Aumenta CAPITAL_TOTAL_USDT o reduce MAX_OPEN_POSITIONS
```

### Error: "No hay trades en backtest"
```
Causa: Mercado sin tendencia o filtros muy restrictivos
Solución: Reduce ADX_MIN o EMA_LARGO en config.py
```

---

## 📈 Métrica Objetivo

Para declarar un bot como **"rentable"**, necesita:
- ✅ Profit Factor > 1.5
- ✅ Win Rate > 55%
- ✅ Sharpe Ratio > 1.0
- ✅ Max Drawdown < 20%
- ✅ ROI mensual 5-15%

Si logras esto → 🎉 ¡Escalas capital gradualmente!

---

## 🚨 Disclaimer

- No hay garantía de rentabilidad
- El trading es RIESGOSO
- Usa capital que PUEDAS PERDER
- El backtest NO garantiza resultados futuros
- Monitorea el bot diariamente
- No dejes corriendo sin supervisión

---

## 📚 Aprende Más

- Consulta `IMPROVEMENTS.md` para entender las 3 mejoras
- Lee `strategy.py` para entender la lógica de compra
- Lee `microstructure.py` para entender validación de Order Book
- Lee `mtf_analyzer.py` para entender multi-timeframe

---

**¡Buena suerte! 🚀**
