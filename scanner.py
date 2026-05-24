#!/usr/bin/env python3
"""
Escáner de activos — Ejecuta backtest en múltiples pares USDT de Binance
para encontrar los activos donde la estrategia es rentable.
"""

import logging
import time
import sys
import io
from backtest import Backtest
from config import CAPITAL_TOTAL_USDT, TRADING_FEE_RATE

# Forzar UTF-8 en Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

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
    """Ejecuta el MISMO motor de backtest que el bot, no una simulación simplificada."""
    bt = Backtest(symbol, CAPITAL_TOTAL_USDT)
    bt.run(days=days, print_results=False)
    return bt.summary()


def main():
    print("=" * 80)
    print("  ESCÁNER MTF REAL — Mismo motor que backtest.py / bot")
    print(f"  Universo: {len(SCAN_SYMBOLS)} pares | Periodo: ~1000 velas 1H | Fees: {TRADING_FEE_RATE*100:.1f}%")
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
    profitable = [r for r in results if r["pnl"] > 0 and r["pf"] >= 1.5 and r["wr"] >= 55 and r["trades"] >= 8]
    print(f"\n{'=' * 80}")
    if profitable:
        syms = [r["symbol"] for r in profitable]
        total_pnl = sum(r["pnl"] for r in profitable)
        print(f"  ✅ RECOMENDACIÓN: permitir NUEVAS entradas en estos {len(profitable)} activos:")
        for r in profitable:
            print(f"     • {r['symbol']:12} → P&L ${r['pnl']:+.2f} | PF {r['pf']:.2f} | {r['trades']} trades")
        print(f"\n  P&L combinado estimado: ${total_pnl:+.2f} en 60 días")
        print(f"\n  Configuración sugerida para config.py:")
        print(f'  ENTRY_SYMBOLS = {syms}')
    else:
        print("  ⚠️  Ningún activo supera los filtros de rentabilidad mínima.")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
