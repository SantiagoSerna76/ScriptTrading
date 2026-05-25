#!/usr/bin/env python3
"""
Escáner de activos — Ejecuta backtest en múltiples pares USDT de Binance
para encontrar los activos donde la estrategia es rentable.
"""

import logging
import time
import sys
import io
import json
from datetime import datetime
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
    summary = bt.summary()
    
    # ── Walk-Forward Validation (Anti-Overfitting) ──
    summary["wf_valid"] = False
    if len(bt.trades) >= 6:
        # Dividir secuencialmente en 3 ventanas de tiempo/trades
        chunk_size = len(bt.trades) // 3
        chunks = [
            bt.trades[:chunk_size],
            bt.trades[chunk_size:chunk_size*2],
            bt.trades[chunk_size*2:]
        ]
        
        consistent = True
        for chunk in chunks:
            if not chunk: continue
            gw = sum(t["pnl"] for t in chunk if t["pnl"] > 0)
            gl = abs(sum(t["pnl"] for t in chunk if t["pnl"] <= 0))
            pf_chunk = gw / gl if gl > 0 else 999.0
            
            # Se exige rentabilidad o leve pérdida aceptable (PF >= 0.75) en todas las ventanas
            if pf_chunk < 0.75:
                consistent = False
                break
                
        summary["wf_valid"] = consistent
        
    return summary

def run_dynamic_scanner(db, notifier=None):
    """
    Ejecuta el escáner asíncronamente desde el dashboard/Flask y actualiza 
    la base de datos directamente con las mejores monedas (Hot-Swap).
    """
    if notifier:
        notifier.send_message("🔍 *Iniciando escáner dinámico en background...* Evaluando 30 altcoins (60 días).")
    
    logger.info("Iniciando escaneo en background...")
    results = []
    for i, sym in enumerate(SCAN_SYMBOLS):
        try:
            r = run_quick_backtest(sym, days=60)
            if "error" not in r and r["trades"] > 0:
                results.append(r)
        except Exception as e:
            logger.error(f"Error escaneando {sym}: {e}")
        time.sleep(0.1)
    
    results.sort(key=lambda x: x["pnl"], reverse=True)
    
    # Filtro estricto + Walk-Forward Validation (mínimo 10 trades para validez estadística)
    profitable = [r for r in results if r["pnl"] > 0 and r["pf"] >= 1.5 and r["wr"] >= 55 and r["trades"] >= 10 and r.get("wf_valid", False)]
    
    if profitable:
        syms = [r["symbol"] for r in profitable]
        total_pnl = sum(r["pnl"] for r in profitable)
        
        # Guardar dinámicamente en SQLite (Hot-Swap)
        db.set_config_value("ENTRY_SYMBOLS", json.dumps(syms))
        db.set_config_value("LAST_SCAN_TIME", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        if notifier:
            msg = f"✅ *Escaneo completado.*\n\n🔄 *Hot-Swap Activo* ({len(syms)} monedas):\n"
            for r in profitable:
                msg += f"• `{r['symbol']}` (PF: {r['pf']:.2f}, WR: {r['wr']:.0f}%)\n"
            msg += f"\n_P&L Estimado_: `${total_pnl:+.2f}`"
            notifier.send_message(msg)
            
        logger.info(f"Hot-Swap completado. ENTRY_SYMBOLS actualizados a: {syms}")
    else:
        logger.warning("Ningún activo pasó el filtro en el escaneo dinámico.")
        if notifier:
            notifier.send_message("⚠️ *Escaneo completado.* Ningún activo pasó los filtros de rentabilidad mínima. Se mantienen las monedas actuales.")


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
    profitable = [r for r in results if r["pnl"] > 0 and r["pf"] >= 1.5 and r["wr"] >= 55 and r["trades"] >= 10 and r.get("wf_valid", False)]
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
