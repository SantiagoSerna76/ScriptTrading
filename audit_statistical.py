"""
AUDITORÍA ESTADÍSTICA RIGUROSA
=====================================
Verifica potencial overfitting, consistencia inter-símbolos,
y solidez de la estrategia optimizada.

Análisis:
1. Overfitting detection (WR vs PF tradeoff, Sharpe vs WR)
2. Distribución de trades y consistencia
3. Out-of-sample validation conceptual
4. Análisis de curva de equity
5. Sesgos de datos y exclusiones
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

DB_FILE = "trades.db"
STRATEGY_START_TIME = "2026-05-24T00:58:00"

# ═══════════════════════════════════════════════════════════════════════════
# BACKTEST RESULTS (Optimized Configuration)
# ═══════════════════════════════════════════════════════════════════════════
OPTIMIZED_RESULTS = {
    "INJUSDT": {"roi": 3.47, "pf": 2.13, "wr": 70.4, "trades": 27, "sharpe": 0.37, "drawdown": -0.98},
    "ICPUSDT": {"roi": 0.85, "pf": 8.54, "wr": 92.3, "trades": 13, "sharpe": 0.64, "drawdown": -0.11},
    "UNIUSDT": {"roi": 2.71, "pf": 2.99, "wr": 68.4, "trades": 19, "sharpe": 0.67, "drawdown": -0.56},
    "APTUSDT": {"roi": 1.64, "pf": 4.07, "wr": 83.3, "trades": 12, "sharpe": 0.92, "drawdown": -0.48},
    "FILUSDT": {"roi": 1.54, "pf": 3.55, "wr": 58.3, "trades": 12, "sharpe": 0.54, "drawdown": -0.32},
    "NEARUSDT": {"roi": -0.11, "pf": 0.87, "wr": 50.0, "trades": 10, "sharpe": 0.22, "drawdown": -0.65},
}

BASELINE_RESULTS = {
    "INJUSDT": {"roi": 2.74, "pf": 2.24, "wr": 71.4, "trades": 28, "sharpe": 0.35, "drawdown": -1.05},
    "ICPUSDT": {"roi": 0.78, "pf": 3.67, "wr": 84.6, "trades": 13, "sharpe": 0.60, "drawdown": -0.15},
    "UNIUSDT": {"roi": 2.15, "pf": 2.82, "wr": 76.5, "trades": 20, "sharpe": 0.61, "drawdown": -0.62},
    "APTUSDT": {"roi": 1.41, "pf": 4.07, "wr": 83.3, "trades": 12, "sharpe": 0.88, "drawdown": -0.50},
    "FILUSDT": {"roi": 1.36, "pf": 3.48, "wr": 58.3, "trades": 12, "sharpe": 0.52, "drawdown": -0.35},
}

# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: OVERFITTING DETECTION (Profit Factor vs Win Rate)
# ═══════════════════════════════════════════════════════════════════════════

def test_overfitting_signal():
    """
    ⚠️  RED FLAG: Profit Factor crece pero Win Rate cae = overfitting
    ✅ GREEN: PF y WR correlacionan positivamente = robustez real
    """
    logger.info("\n" + "="*70)
    logger.info("TEST 1: OVERFITTING DETECTION (PF vs WR correlation)")
    logger.info("="*70)
    
    symbols = ['INJUSDT', 'ICPUSDT', 'UNIUSDT', 'APTUSDT', 'FILUSDT']
    
    pf_changes = []
    wr_changes = []
    
    for sym in symbols:
        baseline = BASELINE_RESULTS.get(sym, {})
        optimized = OPTIMIZED_RESULTS.get(sym, {})
        
        if not baseline or not optimized:
            continue
        
        pf_chg = ((optimized["pf"] - baseline["pf"]) / baseline["pf"]) * 100
        wr_chg = optimized["wr"] - baseline["wr"]
        
        pf_changes.append(pf_chg)
        wr_changes.append(wr_chg)
        
        logger.info(f"\n{sym}:")
        logger.info(f"  PF: {baseline['pf']:.2f} → {optimized['pf']:.2f} ({pf_chg:+.1f}%)")
        logger.info(f"  WR: {baseline['wr']:.1f}% → {optimized['wr']:.1f}% ({wr_chg:+.1f}pp)")
        logger.info(f"  Trades: {baseline['trades']} → {optimized['trades']} ({optimized['trades']-baseline['trades']:+d})")
    
    # Análisis de correlación
    correlation = np.corrcoef(pf_changes, wr_changes)[0, 1]
    logger.info(f"\n📊 CORRELATION: PF change vs WR change = {correlation:.3f}")
    
    if correlation > 0.5:
        logger.info("✅ GOOD: Positive correlation → PF gains = genuine edge, not overfitting")
        return True
    elif correlation < -0.5:
        logger.warning("⚠️  WARNING: Negative correlation → PF gained but WR lost (potential overfitting)")
        return False
    else:
        logger.info("🟡 NEUTRAL: Weak correlation → independent effects (needs manual inspection)")
        return None

# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: CONSISTENCY ACROSS SYMBOLS
# ═══════════════════════════════════════════════════════════════════════════

def test_consistency_across_symbols():
    """
    ✅ GOOD: Performance consistent across all symbols (low variance)
    ⚠️  RED FLAG: One symbol drives entire profit (high variance = curve-fitting)
    """
    logger.info("\n" + "="*70)
    logger.info("TEST 2: CONSISTENCY ACROSS SYMBOLS (Low variance = robust)")
    logger.info("="*70)
    
    symbols = ['INJUSDT', 'ICPUSDT', 'UNIUSDT', 'APTUSDT', 'FILUSDT']
    
    optimized_roi = [OPTIMIZED_RESULTS[sym]["roi"] for sym in symbols]
    optimized_pf = [OPTIMIZED_RESULTS[sym]["pf"] for sym in symbols]
    optimized_wr = [OPTIMIZED_RESULTS[sym]["wr"] for sym in symbols]
    optimized_trades = [OPTIMIZED_RESULTS[sym]["trades"] for sym in symbols]
    
    logger.info(f"\n📈 ROI per symbol: {optimized_roi}")
    logger.info(f"   Mean: {np.mean(optimized_roi):.2f}% | Std Dev: {np.std(optimized_roi):.2f}%")
    logger.info(f"   Coefficient of Variation: {(np.std(optimized_roi) / np.mean(optimized_roi)):.2f}")
    
    logger.info(f"\n📊 PF per symbol: {[f'{x:.2f}' for x in optimized_pf]}")
    logger.info(f"   Mean: {np.mean(optimized_pf):.2f} | Std Dev: {np.std(optimized_pf):.2f}")
    logger.info(f"   Min: {np.min(optimized_pf):.2f} | Max: {np.max(optimized_pf):.2f}")
    
    logger.info(f"\n🎯 Win Rate per symbol: {[f'{x:.1f}%' for x in optimized_wr]}")
    logger.info(f"   Mean: {np.mean(optimized_wr):.1f}% | Std Dev: {np.std(optimized_wr):.1f}%")
    
    logger.info(f"\n📝 Trades per symbol: {optimized_trades}")
    logger.info(f"   Total: {np.sum(optimized_trades)} | Mean per symbol: {np.mean(optimized_trades):.1f}")
    
    # Red flags
    cv_roi = np.std(optimized_roi) / np.mean(optimized_roi)
    cv_pf = np.std(optimized_pf) / np.mean(optimized_pf)
    
    logger.info(f"\n🔍 STABILITY CHECK:")
    if cv_roi < 0.30:
        logger.info(f"✅ ROI Coefficient of Variation = {cv_roi:.2f} (Good: consistent across symbols)")
        roi_ok = True
    else:
        logger.warning(f"⚠️  ROI Coefficient of Variation = {cv_roi:.2f} (High: may indicate curve-fitting)")
        roi_ok = False
    
    if cv_pf < 0.40:
        logger.info(f"✅ PF Coefficient of Variation = {cv_pf:.2f} (Good: robust edge)")
        pf_ok = True
    else:
        logger.warning(f"⚠️  PF Coefficient of Variation = {cv_pf:.2f} (High: may indicate symbol-specific tuning)")
        pf_ok = False
    
    # Check for dominant symbol
    roi_pct_by_symbol = [(sym, roi) for sym, roi in zip(symbols, optimized_roi)]
    roi_pct_by_symbol.sort(key=lambda x: x[1], reverse=True)
    top_roi = roi_pct_by_symbol[0][1]
    sum_roi = np.sum(optimized_roi)
    if top_roi > sum_roi * 0.5:
        logger.warning(f"⚠️  {roi_pct_by_symbol[0][0]} contributes >{50}% of total ROI (potential dominant symbol effect)")
    
    return roi_ok and pf_ok

# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: BASELINE COMPARISON (Improvement magnitude)
# ═══════════════════════════════════════════════════════════════════════════

def test_baseline_improvement():
    """
    ✅ GOOD: Modest but consistent improvement (5-20% on PF, 5-10% on ROI)
    ⚠️  RED FLAG: Huge improvement (>30%) on backtest but tiny on live = overfitting
    """
    logger.info("\n" + "="*70)
    logger.info("TEST 3: BASELINE COMPARISON (Sanity check on improvement magnitude)")
    logger.info("="*70)
    
    symbols = ['INJUSDT', 'ICPUSDT', 'UNIUSDT', 'APTUSDT', 'FILUSDT']
    
    total_improvements = {"roi": [], "pf": [], "wr": [], "trades": []}
    
    for sym in symbols:
        baseline = BASELINE_RESULTS.get(sym, {})
        optimized = OPTIMIZED_RESULTS.get(sym, {})
        
        if not baseline or not optimized:
            continue
        
        roi_imp = ((optimized["roi"] - baseline["roi"]) / abs(baseline["roi"])) * 100 if baseline["roi"] != 0 else 0
        pf_imp = ((optimized["pf"] - baseline["pf"]) / baseline["pf"]) * 100
        wr_imp = optimized["wr"] - baseline["wr"]
        trades_imp = optimized["trades"] - baseline["trades"]
        
        total_improvements["roi"].append(roi_imp)
        total_improvements["pf"].append(pf_imp)
        total_improvements["wr"].append(wr_imp)
        total_improvements["trades"].append(trades_imp)
        
        logger.info(f"\n{sym}:")
        logger.info(f"  ROI improvement: {roi_imp:+.1f}%")
        logger.info(f"  PF improvement: {pf_imp:+.1f}%")
        logger.info(f"  WR improvement: {wr_imp:+.1f}pp")
        logger.info(f"  Trades change: {trades_imp:+d}")
    
    mean_pf_imp = np.mean(total_improvements["pf"])
    mean_roi_imp = np.mean(total_improvements["roi"])
    mean_wr_imp = np.mean(total_improvements["wr"])
    
    logger.info(f"\n📊 AVERAGE IMPROVEMENTS:")
    logger.info(f"  PF: {mean_pf_imp:+.1f}%")
    logger.info(f"  ROI: {mean_roi_imp:+.1f}%")
    logger.info(f"  WR: {mean_wr_imp:+.1f}pp")
    
    # Sanity check
    if 5 <= abs(mean_pf_imp) <= 35 and 5 <= abs(mean_roi_imp) <= 25:
        logger.info("✅ GOOD: Improvements are in reasonable range (5-35% PF, 5-25% ROI)")
        return True
    elif abs(mean_pf_imp) > 50:
        logger.warning(f"⚠️  WARNING: Huge PF improvement ({mean_pf_imp:.1f}%) may indicate overfitting")
        return False
    else:
        logger.info("🟡 ACCEPTABLE: Within typical optimization range")
        return True

# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: SHARPE RATIO ANALYSIS (Risk-adjusted returns)
# ═══════════════════════════════════════════════════════════════════════════

def test_sharpe_ratio():
    """
    ✅ GOOD: Sharpe ratio improves or stays stable (risk-adjusted return improved)
    ⚠️  RED FLAG: Sharpe drops while PF rises (chasing outliers)
    """
    logger.info("\n" + "="*70)
    logger.info("TEST 4: SHARPE RATIO ANALYSIS (Risk-adjusted returns)")
    logger.info("="*70)
    
    symbols = ['INJUSDT', 'ICPUSDT', 'UNIUSDT', 'APTUSDT', 'FILUSDT']
    
    sharpe_changes = []
    
    for sym in symbols:
        baseline = BASELINE_RESULTS.get(sym, {})
        optimized = OPTIMIZED_RESULTS.get(sym, {})
        
        if not baseline or not optimized:
            continue
        
        sharpe_chg = optimized["sharpe"] - baseline["sharpe"]
        sharpe_pct = ((optimized["sharpe"] - baseline["sharpe"]) / baseline["sharpe"]) * 100 if baseline["sharpe"] != 0 else 0
        
        sharpe_changes.append(sharpe_chg)
        
        logger.info(f"\n{sym}:")
        logger.info(f"  Sharpe: {baseline['sharpe']:.2f} → {optimized['sharpe']:.2f} ({sharpe_pct:+.1f}%)")
        logger.info(f"  Drawdown: {baseline['drawdown']:.2f}% → {optimized['drawdown']:.2f}%")
    
    mean_sharpe_chg = np.mean(sharpe_changes)
    logger.info(f"\n📊 Average Sharpe change: {mean_sharpe_chg:+.3f}")
    
    if mean_sharpe_chg >= 0:
        logger.info("✅ GOOD: Sharpe ratio improved or stable (better risk-adjusted returns)")
        return True
    else:
        logger.warning("⚠️  WARNING: Sharpe ratio deteriorated (taking more risk for same profit)")
        return False

# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: NEAR EXCLUSION ANALYSIS (Check for survivorship bias)
# ═══════════════════════════════════════════════════════════════════════════

def test_near_exclusion():
    """
    ✅ GOOD: Exclusion is data-driven (PF < 1.0 backtest, WR < 50%)
    ⚠️  RED FLAG: Excluding best/worst performers to boost aggregate stats
    """
    logger.info("\n" + "="*70)
    logger.info("TEST 5: NEAR EXCLUSION ANALYSIS (Survivorship bias check)")
    logger.info("="*70)
    
    near_opt = OPTIMIZED_RESULTS["NEARUSDT"]
    
    logger.info(f"\nNEARUSDT Performance (Optimized Config):")
    logger.info(f"  ROI: {near_opt['roi']:.2f}%")
    logger.info(f"  PF: {near_opt['pf']:.2f} (Target: > 1.5)")
    logger.info(f"  WR: {near_opt['wr']:.1f}% (Target: > 55%)")
    logger.info(f"  Trades: {near_opt['trades']}")
    
    near_baseline = BASELINE_RESULTS.get("NEARUSDT", {})
    if near_baseline:
        logger.info(f"\nNEARUSDT Performance (Baseline Config):")
        logger.info(f"  ROI: {near_baseline['roi']:.2f}%")
        logger.info(f"  PF: {near_baseline['pf']:.2f}")
        logger.info(f"  WR: {near_baseline['wr']:.1f}%")
    
    # Analysis
    logger.info(f"\n🔍 EXCLUSION CRITERIA:")
    
    if near_opt["pf"] < 1.0:
        logger.info(f"✅ PF < 1.0 → Mathematically losing strategy (correct to exclude)")
    
    if near_opt["wr"] < 50.0:
        logger.info(f"⚠️  WR = {near_opt['wr']:.1f}% (not deeply negative, but below 50%)")
    
    # Check if excluding NEAR improves aggregate stats artificially
    with_near = []
    without_near = []
    
    for sym in ['INJUSDT', 'ICPUSDT', 'UNIUSDT', 'APTUSDT', 'FILUSDT', 'NEARUSDT']:
        with_near.append(OPTIMIZED_RESULTS[sym]["pf"])
    
    for sym in ['INJUSDT', 'ICPUSDT', 'UNIUSDT', 'APTUSDT', 'FILUSDT']:
        without_near.append(OPTIMIZED_RESULTS[sym]["pf"])
    
    avg_with = np.mean(with_near)
    avg_without = np.mean(without_near)
    
    logger.info(f"\n📊 Aggregate PF (6 symbols): {avg_with:.2f}")
    logger.info(f"📊 Aggregate PF (5 symbols, excluding NEAR): {avg_without:.2f}")
    logger.info(f"   Difference: {avg_without - avg_with:+.2f} ({((avg_without/avg_with - 1)*100):+.1f}%)")
    
    if avg_without > avg_with * 1.1:
        logger.warning(f"⚠️  Excluding NEAR boosts aggregate PF by >{10}% (potential survivorship bias)")
        return False
    else:
        logger.info(f"✅ Exclusion has minimal impact on aggregate stats (justifiable data-driven decision)")
        return True

# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: DATABASE INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════

def test_database_integrity():
    """Verify trades.db is consistent and not corrupted"""
    logger.info("\n" + "="*70)
    logger.info("TEST 6: DATABASE INTEGRITY")
    logger.info("="*70)
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM trades")
        total_trades = cursor.fetchone()[0]
        logger.info(f"\n✅ Database accessible")
        logger.info(f"   Total trades in DB: {total_trades}")
        
        # Count trades since STRATEGY_START_TIME
        cursor.execute("""
            SELECT COUNT(*) FROM trades 
            WHERE exit_time IS NOT NULL
            AND exit_time >= ?
        """, (STRATEGY_START_TIME,))
        new_trades = cursor.fetchone()[0]
        logger.info(f"   Closed trades since STRATEGY_START_TIME: {new_trades}")
        
        # Check for data consistency
        cursor.execute("SELECT symbol, COUNT(*) as cnt FROM trades GROUP BY symbol ORDER BY cnt DESC")
        symbol_counts = cursor.fetchall()
        logger.info(f"\n   Trades by symbol:")
        for sym, cnt in symbol_counts:
            logger.info(f"     {sym}: {cnt}")
        
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Database error: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════
# MAIN AUDIT
# ═══════════════════════════════════════════════════════════════════════════

def run_full_audit():
    logger.info("\n" + "🔍" * 35)
    logger.info("STATISTICAL AUDIT: OPTIMIZED STRATEGY")
    logger.info("🔍" * 35)
    logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    results["overfitting"] = test_overfitting_signal()
    results["consistency"] = test_consistency_across_symbols()
    results["improvement"] = test_baseline_improvement()
    results["sharpe"] = test_sharpe_ratio()
    results["near_exclusion"] = test_near_exclusion()
    results["database"] = test_database_integrity()
    
    # Final verdict
    logger.info("\n" + "="*70)
    logger.info("FINAL VERDICT")
    logger.info("="*70)
    
    passed_tests = sum([1 for v in results.values() if v is True])
    total_tests = len(results)
    
    logger.info(f"\n✅ Passed: {passed_tests}/{total_tests}")
    logger.info(f"\nTest Results:")
    for test_name, result in results.items():
        status = "✅ PASS" if result else ("⚠️  WARN" if result is None else "❌ FAIL")
        logger.info(f"  {status:8} → {test_name.replace('_', ' ').title()}")
    
    if passed_tests >= 5:
        logger.info("\n" + "="*70)
        logger.info("✅ OVERALL: STRATEGY APPEARS ROBUST")
        logger.info("="*70)
        logger.info("\nConclusion:")
        logger.info("  • No major overfitting signals detected")
        logger.info("  • Performance consistent across symbols")
        logger.info("  • Improvements are reasonable and data-driven")
        logger.info("  • Ready for live paper trading accumulation")
        logger.info("\nNext: Accumulate 30+ closed trades to unlock ML training")
    else:
        logger.warning("\n" + "="*70)
        logger.warning("⚠️  OVERALL: CAUTION RECOMMENDED")
        logger.warning("="*70)
        logger.warning("\nRecommendation: Review failed tests before live deployment")
    
    return results

if __name__ == "__main__":
    run_full_audit()
