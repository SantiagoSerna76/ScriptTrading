#!/usr/bin/env python3
"""
Backtest v5.0 — Validación de Estrategia Institucional
Usa requests directo a Binance (sin proxy) para klines públicas.
"""
import sys, os
sys.path.append(os.path.dirname(__file__))

import numpy as np
import pandas as pd
import requests
import time

def get_klines(symbol, interval="1h", limit=1000):
    """Descarga klines directo de Binance (endpoint público, sin API key)."""
    urls = [
        "https://api1.binance.com",
        "https://api2.binance.com", 
        "https://api3.binance.com",
        "https://api.binance.com",
        "https://data-api.binance.vision",
    ]
    for url in urls:
        try:
            r = requests.get(
                f"{url}/api/v3/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                df = pd.DataFrame(data, columns=[
                    "timestamp", "open", "high", "low", "close", "volume",
                    "close_time", "quote_vol", "trades", "taker_buy_base",
                    "taker_buy_quote", "ignore"
                ])
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = df[col].astype(float)
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                return df
        except Exception:
            continue
    return None

from strategy import StrategySignals
strat = StrategySignals()

def simulate(df, tp_mult, sl_mult, max_sl_pct=3.0):
    """Simula trades con los 6 filtros obligatorios."""
    if df is None or len(df) < 200:
        return 0, 0, 0

    trades = []
    in_trade = False
    entry_price = 0
    sl_price = 0
    tp_price = 0
    entry_bar = 0

    for i in range(60, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]

        if in_trade:
            if row["low"] <= sl_price:
                pct = (sl_price / entry_price) - 1
                trades.append(pct - 0.002)
                in_trade = False
            elif row["high"] >= tp_price:
                pct = (tp_price / entry_price) - 1
                trades.append(pct - 0.002)
                in_trade = False
            elif (i - entry_bar) >= 48:
                pct = (row["close"] / entry_price) - 1
                trades.append(pct - 0.002)
                in_trade = False
        else:
            close = row["close"]
            ema200 = row.get("ema200", close)
            ema9 = row.get("ema9", close)
            ema21 = row.get("ema21", close)
            prev_ema9 = prev.get("ema9", prev["close"])
            prev_ema21 = prev.get("ema21", prev["close"])
            macd = row.get("macd", 0)
            macd_sig = row.get("macd_signal", 0)
            rsi = row.get("rsi", 50)
            adx = row.get("adx", 0)
            vol = row.get("volume", 0)
            vol_sma = row.get("volume_sma", vol)
            atr = row.get("atr", 0)

            # 6 filtros obligatorios
            c1 = close > ema200
            c2 = ema9 > ema21 and prev_ema9 <= prev_ema21
            c3 = macd > macd_sig
            c4 = adx >= 22
            c5 = 40 <= rsi <= 65
            c6 = vol > vol_sma

            if c1 and c2 and c3 and c4 and c5 and c6:
                sl_dist = (sl_mult * atr) / close * 100
                if sl_dist <= max_sl_pct and atr > 0:
                    entry_price = close
                    sl_price = close - (sl_mult * atr)
                    tp_price = close + (tp_mult * atr)
                    entry_bar = i
                    in_trade = True

    wins = len([t for t in trades if t > 0])
    total_return = sum(trades) * 100
    return len(trades), wins, total_return


symbols = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "NEARUSDT",
    "APTUSDT", "INJUSDT", "RENDERUSDT", "FETUSDT", "UNIUSDT",
    "ICPUSDT", "SEIUSDT", "AXSUSDT", "SUIUSDT", "ARBUSDT",
]

print(f"Descargando datos de {len(symbols)} monedas...")
dfs = {}
for sym in symbols:
    raw = get_klines(sym, "1h", 1000)
    if raw is not None:
        dfs[sym] = strat.calculate_indicators(raw)
        print(f"  {sym}: {len(dfs[sym])} velas OK")
    else:
        dfs[sym] = None
        print(f"  {sym}: ERROR")
    time.sleep(0.2)

print(f"\nOptimizando con 6 filtros (ADX>=22, RSI 40-65, Vol>SMA, MAX_SL<=3%)...\n")

results = []
for tp in [2.0, 2.5, 3.0, 3.5, 4.0]:
    for sl in [1.0, 1.5, 2.0, 2.5]:
        total_pnl = 0
        total_trades = 0
        total_wins = 0
        for sym in symbols:
            if dfs[sym] is not None:
                tr, w, pnl = simulate(dfs[sym], tp, sl)
                total_pnl += pnl
                total_trades += tr
                total_wins += w

        if total_trades > 5:
            wr = total_wins / total_trades * 100 if total_trades > 0 else 0
            results.append((total_pnl, tp, sl, total_trades, wr, total_wins))

results.sort(key=lambda x: x[0], reverse=True)

print("=" * 85)
print(f"{'TP':>6} | {'SL':>6} | {'PnL Neto':>10} | {'Trades':>7} | {'Wins':>5} | {'WinRate':>8} | {'Avg/Trade':>10}")
print("=" * 85)
for pnl, tp, sl, trades, wr, wins in results[:10]:
    avg = pnl / trades if trades > 0 else 0
    marker = " <<<" if wr >= 50 else ""
    print(f"  {tp:.1f}x | {sl:.1f}x | {pnl:>+9.2f}% | {trades:>7} | {wins:>5} | {wr:>7.1f}% | {avg:>+9.2f}%{marker}")

print("\n" + "=" * 85)
if results:
    best = results[0]
    print(f"MEJOR PnL:     TP={best[1]}x | SL={best[2]}x | PnL={best[0]:+.2f}% | WR={best[4]:.1f}% | {best[3]} trades")
    wr_sorted = sorted(results, key=lambda x: x[4], reverse=True)
    best_wr = wr_sorted[0]
    print(f"MEJOR WinRate: TP={best_wr[1]}x | SL={best_wr[2]}x | PnL={best_wr[0]:+.2f}% | WR={best_wr[4]:.1f}% | {best_wr[3]} trades")
