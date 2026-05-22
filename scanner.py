#!/usr/bin/env python3
"""
Escáner de activos — Ejecuta backtest en múltiples pares USDT de Binance
para encontrar los activos donde la estrategia es rentable.
"""

import logging
import time
import sys
import io
import pandas as pd
from binance_api import BinanceAPI, parse_klines_to_dataframe
from strategy import StrategySignals, RiskManager, TrailingStopManager
from config import (
    CAPITAL_TOTAL_USDT, RIESGO_POR_TRADE, TIMEFRAME,
    MAX_OPEN_POSITIONS, TRADING_FEE_RATE, MIN_HOLD_HOURS,
)

# Forzar UTF-8 en Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MIN_HOLD_CANDLES = MIN_HOLD_HOURS

# Universo amplio de altcoins con buena liquidez en Binance Spot
SCAN_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "SHIBUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT",
    "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
    "FILUSDT", "AAVEUSDT", "INJUSDT", "RENDERUSDT", "FETUSDT",
    "PEPEUSDT", "WIFUSDT", "FLOKIUSDT", "TRXUSDT", "ICPUSDT",
]


def run_quick_backtest(symbol: str, days: int = 60) -> dict:
    """Ejecuta un backtest rápido y devuelve métricas clave."""
    api = BinanceAPI("", "", use_testnet=False)
    strategy = StrategySignals()
    risk = RiskManager()
    trailing = TrailingStopManager()

    capital = CAPITAL_TOTAL_USDT
    capital0 = capital
    total_fees = 0.0
    trades = []

    limit = min(days * 24 + 250, 1000)
    klines = api.get_klines(symbol, TIMEFRAME, limit=limit)
    if not klines or len(klines) < 300:
        return {"symbol": symbol, "error": "Sin datos suficientes"}

    df = parse_klines_to_dataframe(klines)
    df = strategy.calculate_indicators(df)

    start = 210
    position = None

    for idx in range(start, len(df)):
        window = df.iloc[:idx + 1]
        current = df.iloc[idx]
        price = current["close"]

        if position is None:
            signal, conds = strategy.check_buy_signal(window)
            if signal:
                sl, tp, atr = strategy.calculate_sl_tp(price, window)
                capital_per_trade = capital / MAX_OPEN_POSITIONS
                qty = risk.position_size(capital_per_trade, price, sl, RIESGO_POR_TRADE)
                qty = min(qty, capital_per_trade / price)
                notional = qty * price
                if qty > 0 and notional >= 5:
                    buy_fee = notional * TRADING_FEE_RATE
                    total_fees += buy_fee
                    capital -= buy_fee
                    position = {
                        "entry_idx": idx, "entry": price,
                        "qty": qty, "sl": sl, "max": price,
                        "score": conds.get("score"),
                    }
        else:
            if price > position["max"]:
                position["max"] = price

            trailing_result = trailing.update_trailing_stop(
                entry_price=position["entry"],
                current_price=price,
                current_atr=current["atr"],
                max_price=position["max"],
                initial_sl=position["sl"],
                trailing_atr_mult=3.0,
                breakeven_pct=1.0,
            )

            exit_p, exit_r = None, None
            hold_time = idx - position["entry_idx"]

            if price <= trailing_result["new_sl"]:
                exit_p, exit_r = price, "Trailing Stop"
            elif hold_time >= MIN_HOLD_CANDLES:
                s_score, s_reason = strategy.exit_score(window)
                if s_score >= strategy.MIN_SELL_SCORE:
                    exit_p, exit_r = price, s_reason or "Signal Exit"

            if exit_p is None and current["rsi"] < 25:
                exit_p, exit_r = price, "RSI Crash"

            if exit_p:
                sell_notional = exit_p * position["qty"]
                sell_fee = sell_notional * TRADING_FEE_RATE
                total_fees += sell_fee
                entry_fee = position["entry"] * position["qty"] * TRADING_FEE_RATE
                pnl = (exit_p - position["entry"]) * position["qty"] - sell_fee - entry_fee
                pct = (exit_p / position["entry"] - 1) * 100
                capital += (exit_p - position["entry"]) * position["qty"] - sell_fee
                trades.append({"pnl": pnl, "pct": pct, "dur": hold_time})
                position = None

    # Calcular métricas
    if not trades:
        return {
            "symbol": symbol, "trades": 0, "pnl": 0, "roi": 0,
            "pf": 0, "wr": 0, "avg_dur": 0, "fees": total_fees,
        }

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)
    gross_win = sum(t["pnl"] for t in wins)
    gross_los = abs(sum(t["pnl"] for t in losses))
    pf = gross_win / gross_los if gross_los > 0 else 999
    wr = len(wins) / len(trades) * 100
    avg_dur = sum(t["dur"] for t in trades) / len(trades)
    roi = (capital - capital0) / capital0 * 100

    return {
        "symbol": symbol,
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "pnl": round(total_pnl, 2),
        "roi": round(roi, 2),
        "pf": round(pf, 2),
        "wr": round(wr, 1),
        "avg_dur": round(avg_dur, 1),
        "fees": round(total_fees, 2),
    }


def main():
    print("=" * 80)
    print("  ESCÁNER DE ACTIVOS — Buscando los pares más rentables para el bot")
    print(f"  Universo: {len(SCAN_SYMBOLS)} pares | Periodo: 60 días | Fees: {TRADING_FEE_RATE*100:.1f}%")
    print("=" * 80)

    results = []
    for i, sym in enumerate(SCAN_SYMBOLS):
        print(f"  [{i+1}/{len(SCAN_SYMBOLS)}] Testeando {sym}...", end=" ", flush=True)
        try:
            r = run_quick_backtest(sym, days=60)
            if "error" in r:
                print(f"⚠️  {r['error']}")
            elif r["trades"] == 0:
                print(f"— Sin trades")
            else:
                emoji = "✅" if r["pnl"] > 0 else "❌"
                print(f"{emoji} {r['trades']} trades | P&L ${r['pnl']:+.2f} | PF {r['pf']:.2f} | WR {r['wr']:.0f}% | Dur {r['avg_dur']:.0f}h")
                results.append(r)
        except Exception as e:
            print(f"❌ Error: {e}")
        time.sleep(0.5)

    # Ordenar por P&L
    results.sort(key=lambda x: x["pnl"], reverse=True)

    print(f"\n{'=' * 80}")
    print("  📊 RANKING DE ACTIVOS (ordenados por P&L neto con comisiones)")
    print(f"{'=' * 80}")
    print(f"  {'Símbolo':<12} {'Trades':>6} {'W/L':>7} {'WR%':>5} {'P&L':>9} {'ROI%':>7} {'PF':>6} {'Dur(h)':>7} {'Fees':>7}")
    print(f"  {'-'*12} {'-'*6} {'-'*7} {'-'*5} {'-'*9} {'-'*7} {'-'*6} {'-'*7} {'-'*7}")

    for r in results:
        emoji = "🟢" if r["pnl"] > 0 else "🔴"
        wl = f"{r['wins']}/{r['losses']}"
        print(f"  {emoji} {r['symbol']:<10} {r['trades']:>5} {wl:>7} {r['wr']:>4.0f}% ${r['pnl']:>+7.2f} {r['roi']:>+6.2f}% {r['pf']:>5.2f} {r['avg_dur']:>6.1f} ${r['fees']:>5.2f}")

    # Recomendar configuración
    profitable = [r for r in results if r["pnl"] > 0 and r["pf"] >= 1.3 and r["trades"] >= 3]
    print(f"\n{'=' * 80}")
    if profitable:
        syms = [r["symbol"] for r in profitable]
        total_pnl = sum(r["pnl"] for r in profitable)
        print(f"  ✅ RECOMENDACIÓN: Usar estos {len(profitable)} activos:")
        for r in profitable:
            print(f"     • {r['symbol']:12} → P&L ${r['pnl']:+.2f} | PF {r['pf']:.2f} | {r['trades']} trades")
        print(f"\n  P&L combinado estimado: ${total_pnl:+.2f} en 60 días")
        print(f"\n  Configuración sugerida para config.py:")
        print(f'  SYMBOLS = {syms}')
    else:
        print("  ⚠️  Ningún activo supera los filtros de rentabilidad mínima.")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
