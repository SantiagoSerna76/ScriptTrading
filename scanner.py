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
    
    # Filtro suavizado para capturar más volumen de datos sin perder calidad base
    sniper_pool = [r for r in results if r["pnl"] > 0 and r["pf"] >= 1.15 and r["wr"] >= 45 and r["trades"] >= 3]
    elite_pool = [r for r in results if r["pnl"] > 0 and r["pf"] >= 1.5 and r["wr"] >= 55 and r["trades"] >= 5 and r.get("wf_valid", False)]
    
    if sniper_pool:
        sniper_syms = [r["symbol"] for r in sniper_pool]
        elite_syms = [r["symbol"] for r in elite_pool]
        total_pnl = sum(r["pnl"] for r in sniper_pool)
        
        # Guardar dinámicamente en SQLite (Hot-Swap)
        db.set_config_value("ENTRY_SYMBOLS", json.dumps(sniper_syms))
        db.set_config_value("RELAXED_MACRO_SYMBOLS", json.dumps(elite_syms))
        db.set_config_value("LAST_SCAN_TIME", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        if notifier:
            msg = f"✅ *Escaneo completado.*\n\n🔄 *Hot-Swap Activo* ({len(sniper_syms)} total, {len(elite_syms)} élite):\n"
            msg += f"\n_P&L Estimado_: `${total_pnl:+.2f}`"
            notifier.send_message(msg)
            
        logger.info(f"Hot-Swap completado. ENTRY_SYMBOLS: {sniper_syms} | RELAXED_MACRO_SYMBOLS: {elite_syms}")
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
    # Sniper: rentables básicos
    sniper_pool = [r for r in results if r["pnl"] > 0 and r["pf"] >= 1.15 and r["wr"] >= 45 and r["trades"] >= 3]
    # Elites: lo mejor de lo mejor
    elite_pool = [r for r in results if r["pnl"] > 0 and r["pf"] >= 1.5 and r["wr"] >= 55 and r["trades"] >= 5 and r.get("wf_valid", False)]
    
    print(f"\n{'=' * 80}")
    if sniper_pool:
        sniper_syms = [r["symbol"] for r in sniper_pool]
        elite_syms = [r["symbol"] for r in elite_pool]
        
        print(f"  ✅ MODO ÉLITE (Relajado): {len(elite_syms)} activos:")
        for r in elite_pool:
            print(f"     • {r['symbol']:12} → P&L ${r['pnl']:+.2f} | PF {r['pf']:.2f} | WR {r['wr']:.0f}%")
            
        print(f"\n  🎯 MODO FRANCOTIRADOR (Estricto): {len(sniper_syms)} activos en total (incluyendo élites):")
        for r in sniper_pool:
            if r["symbol"] not in elite_syms:
                print(f"     • {r['symbol']:12} → P&L ${r['pnl']:+.2f} | PF {r['pf']:.2f} | WR {r['wr']:.0f}%")
        
        print(f"\n  Actualizando config.py automáticamente...")
        
        import re
        config_path = "config.py"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Replace ENTRY_SYMBOLS
            content = re.sub(
                r"ENTRY_SYMBOLS\s*=\s*\[.*?\]",
                f"ENTRY_SYMBOLS = {sniper_syms}",
                content,
                flags=re.DOTALL
            )
            
            # Replace RELAXED_MACRO_SYMBOLS
            content = re.sub(
                r"RELAXED_MACRO_SYMBOLS\s*=\s*\[.*?\]",
                f"RELAXED_MACRO_SYMBOLS = {elite_syms}",
                content,
                flags=re.DOTALL
            )
            
            # Replace SYMBOLS (we'll keep it same as ENTRY_SYMBOLS for simplicity)
            content = re.sub(
                r"SYMBOLS\s*=\s*\[.*?\]",
                f"SYMBOLS = {sniper_syms}",
                content,
                flags=re.DOTALL
            )
            
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("  ✅ config.py actualizado exitosamente con la nueva configuración de dos niveles.")
        except Exception as e:
            print(f"  ❌ Error actualizando config.py: {e}")
            
    else:
        print("  ⚠️  Ningún activo supera los filtros de rentabilidad mínima.")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
