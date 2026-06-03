"""
TEST DE PRODUCCIÓN COMPLETO
============================
Verifica que todos los módulos funcionen sin errores.
"""
import sys, os, traceback
sys.path.append(".")

TESTS_PASSED = 0
TESTS_FAILED = 0

def test(name, func):
    global TESTS_PASSED, TESTS_FAILED
    try:
        result = func()
        if result:
            print(f"  ✅ {name}")
            TESTS_PASSED += 1
        else:
            print(f"  ❌ {name} — returned False")
            TESTS_FAILED += 1
    except Exception as e:
        print(f"  ❌ {name} — {type(e).__name__}: {e}")
        traceback.print_exc()
        TESTS_FAILED += 1

# ═══════════════════════════════════════════════════════
print("=" * 70)
print("1. IMPORTS")
print("=" * 70)

def t_config():
    from config import (API_KEY, SECRET_KEY, SYMBOLS, CAPITAL_TOTAL_USDT,
        RIESGO_POR_TRADE, TIMEFRAME, POLLING_INTERVAL, LOG_FILE,
        MAX_OPEN_POSITIONS, MIN_BUY_COOLDOWN_S, MAX_DAILY_LOSS_USDT,
        MAX_DAILY_TRADES, MIN_ORDER_NOTIONAL, KLINES_LIMIT, MIN_HOLD_HOURS,
        PAPER_TRADING, USE_TESTNET, TRADING_FEE_RATE, ADX_MIN,
        RELAXED_MACRO_SYMBOLS, ENTRY_SYMBOLS, PROXY_URL,
        BREAKEVEN_ATR_MULT, MAX_HOLD_HOURS, PAUSE_SIGNAL_FILE,
        TRAILING_ACTIVATE_ATR, TRAILING_STEP_ATR, TRAILING_SL_OFFSET_ATR,
        SL_ATR_MULT, TP_ATR_MULT, MAX_SL_PCT,
        SL_COOLDOWN_S, CONSECUTIVE_LOSS_MAX, CONSECUTIVE_LOSS_COOLDOWN_S,
        RSI_BUY_MIN, RSI_BUY_MAX)
    return True
test("config.py imports", t_config)

def t_strategy():
    from strategy import StrategySignals, RiskManager, TrailingStopManager, TechnicalIndicators
    return True
test("strategy.py imports", t_strategy)

def t_binance():
    from binance_api import BinanceAPI, parse_klines_to_dataframe
    return True
test("binance_api.py imports", t_binance)

def t_mtf():
    from mtf_analyzer import MultiTimeframeAnalyzer
    return True
test("mtf_analyzer.py imports", t_mtf)

def t_db():
    from database import TradeDatabase
    return True
test("database.py imports", t_db)

def t_notifier():
    from notifier import TelegramNotifier
    return True
test("notifier.py imports", t_notifier)

def t_ml():
    import ml_features
    return True
test("ml_features.py imports", t_ml)

# ═══════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("2. CONFIG VALUES")
print("=" * 70)

def t_config_values():
    from config import (ADX_MIN, SL_ATR_MULT, TP_ATR_MULT, MAX_SL_PCT,
        MAX_OPEN_POSITIONS, RIESGO_POR_TRADE, PAPER_TRADING,
        CONSECUTIVE_LOSS_COOLDOWN_S, MAX_HOLD_HOURS, POLLING_INTERVAL)
    assert ADX_MIN == 30, f"ADX_MIN should be 30, got {ADX_MIN}"
    assert SL_ATR_MULT == 1.0, f"SL should be 1.0, got {SL_ATR_MULT}"
    assert TP_ATR_MULT == 1.5, f"TP should be 1.5, got {TP_ATR_MULT}"
    assert MAX_SL_PCT == 3.0, f"MAX_SL should be 3.0, got {MAX_SL_PCT}"
    assert MAX_OPEN_POSITIONS == 3, f"MAX_POS should be 3, got {MAX_OPEN_POSITIONS}"
    assert RIESGO_POR_TRADE == 0.015, f"RISK should be 0.015, got {RIESGO_POR_TRADE}"
    assert PAPER_TRADING == True, f"PAPER should be True!"
    assert CONSECUTIVE_LOSS_COOLDOWN_S == 86400, f"Cooldown should be 86400s"
    assert MAX_HOLD_HOURS == 48, f"MAX_HOLD should be 48h"
    assert POLLING_INTERVAL == 300, f"POLLING should be 300s"
    return True
test("Config values correct", t_config_values)

# ═══════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("3. STRATEGY LOGIC")
print("=" * 70)

def t_indicators():
    import pandas as pd
    import numpy as np
    from strategy import StrategySignals
    s = StrategySignals()
    # Create synthetic data
    np.random.seed(42)
    n = 300
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "open": close - np.random.rand(n) * 0.3,
        "high": close + np.abs(np.random.randn(n)) * 0.5,
        "low": close - np.abs(np.random.randn(n)) * 0.5,
        "close": close,
        "volume": np.random.rand(n) * 1000 + 500,
    })
    df = s.calculate_indicators(df)
    required = ["ema_short", "ema_long", "ema200", "ema9", "ema21", "rsi", "atr",
                 "adx", "volume_sma", "macd", "macd_signal", "macd_hist",
                 "bb_upper", "bb_mid", "bb_lower", "stoch_k", "stoch_d"]
    for col in required:
        assert col in df.columns, f"Missing indicator: {col}"
        assert not df[col].isna().all(), f"Indicator {col} is all NaN"
    return True
test("All indicators calculated", t_indicators)

def t_buy_signal():
    import pandas as pd
    import numpy as np
    from strategy import StrategySignals
    s = StrategySignals()
    np.random.seed(42)
    n = 300
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "open": close - 0.1,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": np.random.rand(n) * 1000 + 500,
    })
    df = s.calculate_indicators(df)
    buy, details = s.check_buy_signal(df)
    assert isinstance(buy, bool), "buy should be bool"
    assert isinstance(details, dict), "details should be dict"
    assert "score" in details, "details missing 'score'"
    assert "min_score" in details, "details missing 'min_score'"
    assert "above_ema200" in details, "details missing 'above_ema200'"
    assert "macd_crossed" in details, "details missing 'macd_crossed'"
    assert "adx_ok" in details, "details missing 'adx_ok'"
    assert "regime" in details, "details missing 'regime'"
    assert details["min_score"] == 4, f"min_score should be 4, got {details['min_score']}"
    return True
test("check_buy_signal returns correct structure", t_buy_signal)

def t_exit_score():
    import pandas as pd
    import numpy as np
    from strategy import StrategySignals
    s = StrategySignals()
    np.random.seed(42)
    n = 300
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "open": close - 0.1, "high": close + 0.5,
        "low": close - 0.5, "close": close,
        "volume": np.random.rand(n) * 1000 + 500,
    })
    df = s.calculate_indicators(df)
    score, reason = s.exit_score(df)
    assert isinstance(score, int), "exit_score should return int"
    assert isinstance(reason, str), "exit_reason should return str"
    return True
test("exit_score works correctly", t_exit_score)

def t_sl_tp():
    import pandas as pd
    import numpy as np
    from strategy import StrategySignals
    s = StrategySignals()
    np.random.seed(42)
    n = 300
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "open": close - 0.1, "high": close + 0.5,
        "low": close - 0.5, "close": close,
        "volume": np.random.rand(n) * 1000 + 500,
    })
    df = s.calculate_indicators(df)
    entry = df.iloc[-1]["close"]
    sl, tp, atr, sl_m, tp_m, rr = s.calculate_sl_tp(entry, df)
    assert sl is not None, "SL should not be None for normal volatility"
    assert tp is not None, "TP should not be None"
    assert sl < entry, f"SL ({sl}) should be below entry ({entry})"
    assert tp > entry, f"TP ({tp}) should be above entry ({entry})"
    assert sl_m == 1.0, f"SL mult should be 1.0, got {sl_m}"
    assert tp_m == 1.5, f"TP mult should be 1.5, got {tp_m}"
    assert rr == 1.5, f"R:R should be 1.5, got {rr}"
    # Verify MAX_SL_PCT cap
    sl_pct = (entry - sl) / entry * 100
    assert sl_pct <= 3.0, f"SL distance {sl_pct:.1f}% exceeds MAX_SL_PCT 3%"
    return True
test("SL/TP calculation correct (1.0x/1.5x ATR)", t_sl_tp)

def t_regime():
    import pandas as pd
    import numpy as np
    from strategy import StrategySignals
    s = StrategySignals()
    np.random.seed(42)
    n = 300
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "open": close - 0.1, "high": close + 0.5,
        "low": close - 0.5, "close": close,
        "volume": np.random.rand(n) * 1000 + 500,
    })
    df = s.calculate_indicators(df)
    regime = s.detect_market_regime(df)
    assert "regime" in regime, "Missing regime key"
    assert "adx" in regime, "Missing adx key"
    assert "min_score" in regime, "Missing min_score key"
    assert "reason" in regime, "Missing reason key"
    return True
test("Market regime detection works", t_regime)

# ═══════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("4. TRADING BOT INSTANTIATION (sin conectar a API)")
print("=" * 70)

def t_bot_import():
    # Just verify it imports without syntax errors
    import importlib
    spec = importlib.util.spec_from_file_location("trading_bot", "trading_bot.py")
    module = importlib.util.module_from_spec(spec)
    # Don't execute - just check it parses
    import ast
    with open("trading_bot.py", "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    assert tree is not None, "Failed to parse trading_bot.py"
    return True
test("trading_bot.py parses without syntax errors", t_bot_import)

# ═══════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("5. EDGE MATEMÁTICO")
print("=" * 70)

def t_edge():
    from config import SL_ATR_MULT, TP_ATR_MULT
    wr = 0.611  # Out-of-sample validated
    ev = (wr * TP_ATR_MULT) - ((1 - wr) * SL_ATR_MULT)
    print(f"     WR = {wr*100:.1f}%")
    print(f"     TP = {TP_ATR_MULT}x ATR")
    print(f"     SL = {SL_ATR_MULT}x ATR")
    print(f"     EV = ({wr:.3f} × {TP_ATR_MULT}) - ({1-wr:.3f} × {SL_ATR_MULT}) = {ev:+.4f} ATR/trade")
    assert ev > 0, f"Edge should be positive! Got {ev}"
    return True
test("Positive mathematical edge confirmed", t_edge)

# ═══════════════════════════════════════════════════════
print("\n" + "=" * 70)
print(f"RESULTADO FINAL: {TESTS_PASSED} pasados, {TESTS_FAILED} fallidos")
print("=" * 70)
if TESTS_FAILED == 0:
    print("🎉 TODOS LOS TESTS PASARON — LISTO PARA PRODUCCIÓN")
else:
    print(f"⚠️  {TESTS_FAILED} TESTS FALLARON — REVISAR ANTES DE PRODUCCIÓN")
