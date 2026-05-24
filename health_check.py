#!/usr/bin/env python3
"""
HEALTH CHECK - DETECCIÓN DE PERFORMANCE DEGRADADA

Este script monitorea la salud del bot y lo pausa si:
  • Win rate cae por debajo de 45%
  • Profit factor < 1.0 (operando en rojo)
  • P&L acumulado < -$15
  • Más de 3 pérdidas consecutivas

USO:
    python health_check.py
    
O ejecutar cada hora en cron:
    0 * * * * python /path/to/health_check.py

SALIDA:
    • Si bot está OK: exit 0 (todo bien)
    • Si bot debe pausarse: exit 1 (generar PAUSE signal)
"""

import sqlite3
import logging
from datetime import datetime, timedelta
import sys
import json
from pathlib import Path
from typing import Tuple

try:
    from config import ENTRY_SYMBOLS, STRATEGY_START_TIME
except Exception:
    ENTRY_SYMBOLS = []
    STRATEGY_START_TIME = None

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

DB_FILE = "trades.db"
PAUSE_SIGNAL_FILE = ".bot_pause_signal"  # Archivo que indica que el bot debe pausarse
HEALTH_REPORT_FILE = "health_check.log"

# Umbrales críticos
CRITICAL_WIN_RATE_MIN = 0.45        # < 45% = crítico
CRITICAL_PROFIT_FACTOR_MIN = 1.0    # < 1.0 = operando en rojo
CRITICAL_CUMULATIVE_LOSS = -15.0    # Pérdida acumulada > $15
CRITICAL_CONSECUTIVE_LOSSES = 3     # 3 pérdidas seguidas

def get_db_connection():
    return sqlite3.connect(DB_FILE)

def symbol_filter_sql() -> tuple:
    """Filtra health check a la estrategia activa, no a símbolos descartados."""
    clauses = []
    params = []
    if not ENTRY_SYMBOLS:
        pass
    else:
        placeholders = ",".join("?" for _ in ENTRY_SYMBOLS)
        clauses.append(f"symbol IN ({placeholders})")
        params.extend(ENTRY_SYMBOLS)

    if STRATEGY_START_TIME:
        clauses.append("entry_time >= ?")
        params.append(STRATEGY_START_TIME)

    if not clauses:
        return "", ()
    return " AND " + " AND ".join(clauses), tuple(params)

def get_recent_stats(hours: int = 24) -> dict:
    """Obtiene estadísticas de las últimas N horas."""
    conn = get_db_connection()
    c = conn.cursor()
    
    cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
    symbol_clause, symbol_params = symbol_filter_sql()
    
    # Trades recientes
    c.execute(f"""
        SELECT COUNT(*), SUM(profit_loss), AVG(profit_loss)
        FROM trades 
        WHERE exit_time > ? AND (status = 'CLOSED' OR exit_time IS NOT NULL)
        {symbol_clause}
    """, (cutoff_time, *symbol_params))
    row = c.fetchone()
    
    stats = {
        'recent_trades': row[0] or 0,
        'recent_pl': row[1] or 0.0,
        'recent_avg_pl': row[2] or 0.0,
    }
    
    # Win rate reciente
    c.execute(f"""
        SELECT COUNT(*) FROM trades 
        WHERE exit_time > ? AND (status = 'CLOSED' OR exit_time IS NOT NULL)
        AND profit_loss > 0
        {symbol_clause}
    """, (cutoff_time, *symbol_params))
    wins = c.fetchone()[0] or 0
    stats['recent_wins'] = wins
    stats['recent_losses'] = stats['recent_trades'] - wins
    stats['recent_win_rate'] = wins / stats['recent_trades'] if stats['recent_trades'] > 0 else 0.0
    
    # Profit factor reciente
    c.execute(f"""
        SELECT SUM(profit_loss) FROM trades 
        WHERE exit_time > ? AND (status = 'CLOSED' OR exit_time IS NOT NULL)
        AND profit_loss > 0
        {symbol_clause}
    """, (cutoff_time, *symbol_params))
    gross_profit = c.fetchone()[0] or 0.0
    
    c.execute(f"""
        SELECT ABS(SUM(profit_loss)) FROM trades 
        WHERE exit_time > ? AND (status = 'CLOSED' OR exit_time IS NOT NULL)
        AND profit_loss < 0
        {symbol_clause}
    """, (cutoff_time, *symbol_params))
    gross_loss = c.fetchone()[0] or 0.0
    
    stats['recent_gross_profit'] = gross_profit
    stats['recent_gross_loss'] = gross_loss
    stats['recent_profit_factor'] = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    conn.close()
    return stats

def get_all_time_stats() -> dict:
    """Obtiene estadísticas de TODO el tiempo."""
    conn = get_db_connection()
    c = conn.cursor()
    symbol_clause, symbol_params = symbol_filter_sql()
    
    # Trades totales
    c.execute(f"""
        SELECT COUNT(*), SUM(profit_loss), AVG(profit_loss)
        FROM trades 
        WHERE (status = 'CLOSED' OR exit_time IS NOT NULL)
        {symbol_clause}
    """, symbol_params)
    row = c.fetchone()
    
    stats = {
        'total_trades': row[0] or 0,
        'total_pl': row[1] or 0.0,
        'total_avg_pl': row[2] or 0.0,
    }
    
    # Win rate total
    c.execute(f"""
        SELECT COUNT(*) FROM trades 
        WHERE (status = 'CLOSED' OR exit_time IS NOT NULL)
        AND profit_loss > 0
        {symbol_clause}
    """, symbol_params)
    wins = c.fetchone()[0] or 0
    stats['total_wins'] = wins
    stats['total_losses'] = stats['total_trades'] - wins
    stats['total_win_rate'] = wins / stats['total_trades'] if stats['total_trades'] > 0 else 0.0
    
    # Profit factor total
    c.execute(f"""
        SELECT SUM(profit_loss) FROM trades 
        WHERE (status = 'CLOSED' OR exit_time IS NOT NULL)
        AND profit_loss > 0
        {symbol_clause}
    """, symbol_params)
    gross_profit = c.fetchone()[0] or 0.0
    
    c.execute(f"""
        SELECT ABS(SUM(profit_loss)) FROM trades 
        WHERE (status = 'CLOSED' OR exit_time IS NOT NULL)
        AND profit_loss < 0
        {symbol_clause}
    """, symbol_params)
    gross_loss = c.fetchone()[0] or 0.0
    
    stats['total_gross_profit'] = gross_profit
    stats['total_gross_loss'] = gross_loss
    stats['total_profit_factor'] = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    conn.close()
    return stats

def check_consecutive_losses() -> int:
    """Cuenta pérdidas consecutivas al final."""
    conn = get_db_connection()
    c = conn.cursor()
    symbol_clause, symbol_params = symbol_filter_sql()
    
    c.execute(f"""
        SELECT profit_loss FROM trades
        WHERE (status = 'CLOSED' OR exit_time IS NOT NULL)
        {symbol_clause}
        ORDER BY exit_time DESC
        LIMIT 10
    """, symbol_params)
    
    recent_trades = [row[0] for row in c.fetchall()]
    conn.close()
    
    consecutive = 0
    for pl in recent_trades:
        if pl <= 0:
            consecutive += 1
        else:
            break
    
    return consecutive

def assess_health() -> Tuple[bool, list]:
    """
    Evalúa la salud del bot.
    
    Retorna:
        (is_healthy, list_of_issues)
    """
    issues = []
    
    recent_stats = get_recent_stats(24)  # Últimas 24h
    all_stats = get_all_time_stats()
    
    # Check 1: Win rate reciente muy bajo
    if recent_stats['recent_trades'] >= 5:  # Necesita mínimo 5 trades recientes
        if recent_stats['recent_win_rate'] < CRITICAL_WIN_RATE_MIN:
            issues.append(
                f"❌ Win rate reciente CRÍTICO: {recent_stats['recent_win_rate']*100:.1f}% "
                f"(< {CRITICAL_WIN_RATE_MIN*100:.0f}%). Últimas 24h: {recent_stats['recent_trades']} trades"
            )
    
    # Check 2: Profit factor reciente en rojo
    if recent_stats['recent_trades'] >= 5:
        if recent_stats['recent_profit_factor'] < CRITICAL_PROFIT_FACTOR_MIN:
            issues.append(
                f"❌ Profit factor reciente CRÍTICO: {recent_stats['recent_profit_factor']:.2f}x "
                f"(< {CRITICAL_PROFIT_FACTOR_MIN:.1f}x)"
            )

    # Check 2b: Performance total degradada (muestra suficiente)
    if all_stats['total_trades'] >= 10:
        if all_stats['total_win_rate'] < CRITICAL_WIN_RATE_MIN:
            issues.append(
                f"❌ Win rate total CRÍTICO: {all_stats['total_win_rate']*100:.1f}% "
                f"(< {CRITICAL_WIN_RATE_MIN*100:.0f}%). Total: {all_stats['total_trades']} trades"
            )

        if all_stats['total_profit_factor'] < CRITICAL_PROFIT_FACTOR_MIN:
            issues.append(
                f"❌ Profit factor total CRÍTICO: {all_stats['total_profit_factor']:.2f}x "
                f"(< {CRITICAL_PROFIT_FACTOR_MIN:.1f}x). Total: {all_stats['total_trades']} trades"
            )
    
    # Check 3: Pérdida acumulada total
    if all_stats['total_trades'] >= 5:
        if all_stats['total_pl'] < CRITICAL_CUMULATIVE_LOSS:
            issues.append(
                f"❌ P&L acumulado CRÍTICO: ${all_stats['total_pl']:.2f} "
                f"(< ${CRITICAL_CUMULATIVE_LOSS:.2f}). Total: {all_stats['total_trades']} trades"
            )
    
    # Check 4: Pérdidas consecutivas
    consecutive_losses = check_consecutive_losses()
    if consecutive_losses >= CRITICAL_CONSECUTIVE_LOSSES:
        issues.append(
            f"❌ {consecutive_losses} pérdidas CONSECUTIVAS (umbral: {CRITICAL_CONSECUTIVE_LOSSES})"
        )
    
    is_healthy = len(issues) == 0
    
    return is_healthy, issues

def create_pause_signal():
    """Crea archivo de señal para pausar el bot."""
    try:
        Path(PAUSE_SIGNAL_FILE).touch()
        logger.warning(f"🛑 Archivo de pausa creado: {PAUSE_SIGNAL_FILE}")
    except Exception as e:
        logger.error(f"Error creando archivo de pausa: {e}")

def remove_pause_signal():
    """Elimina archivo de señal de pausa."""
    try:
        if Path(PAUSE_SIGNAL_FILE).exists():
            Path(PAUSE_SIGNAL_FILE).unlink()
            logger.info(f"✅ Archivo de pausa eliminado: {PAUSE_SIGNAL_FILE}")
    except Exception as e:
        logger.error(f"Error eliminando archivo de pausa: {e}")

def format_health_report(is_healthy: bool, issues: list, recent_stats: dict, all_stats: dict) -> str:
    """Formatea reporte de salud."""
    report = []
    report.append("=" * 80)
    report.append(f"🏥 HEALTH CHECK - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 80)
    
    # Estado general
    status_emoji = "✅" if is_healthy else "❌"
    status_text = "SALUDABLE" if is_healthy else "CRÍTICO - BOT PAUSADO"
    report.append(f"\n{status_emoji} ESTADO: {status_text}")
    
    # Estadísticas últimas 24h
    report.append(f"\n📊 ÚLTIMAS 24 HORAS:")
    report.append(f"  • Trades: {recent_stats['recent_trades']}")
    report.append(f"  • Win rate: {recent_stats['recent_win_rate']*100:.1f}%")
    report.append(f"  • P&L: ${recent_stats['recent_pl']:.2f}")
    report.append(f"  • Profit factor: {recent_stats['recent_profit_factor']:.2f}x")
    
    # Estadísticas todo el tiempo
    report.append(f"\n📈 TODO EL TIEMPO:")
    report.append(f"  • Trades: {all_stats['total_trades']}")
    report.append(f"  • Win rate: {all_stats['total_win_rate']*100:.1f}%")
    report.append(f"  • P&L: ${all_stats['total_pl']:.2f}")
    report.append(f"  • Profit factor: {all_stats['total_profit_factor']:.2f}x")
    
    # Issues
    if issues:
        report.append(f"\n⚠️ PROBLEMAS DETECTADOS ({len(issues)}):")
        for issue in issues:
            report.append(f"  {issue}")
    else:
        report.append(f"\n✅ Sin problemas detectados")
    
    # Recomendaciones
    if not is_healthy:
        report.append(f"\n💡 RECOMENDACIONES:")
        report.append(f"  1. Bot ha sido PAUSADO automáticamente")
        report.append(f"  2. Revisa los últimos trades en monitor_daily.py")
        report.append(f"  3. Considera:")
        report.append(f"     - Entrenar nuevo modelo ML")
        report.append(f"     - Ajustar parámetros en config.py")
        report.append(f"     - Revisar performance de los símbolos")
        report.append(f"  4. Cuando esté listo, elimina {PAUSE_SIGNAL_FILE}")
        report.append(f"  5. Reinicia el bot")
    
    report.append("\n" + "=" * 80)
    
    return "\n".join(report)

def main():
    """Flujo principal."""
    logger.info("🏥 Iniciando health check...")
    
    try:
        # 1. Evaluar salud
        is_healthy, issues = assess_health()
        
        # 2. Obtener estadísticas
        recent_stats = get_recent_stats(24)
        all_stats = get_all_time_stats()
        
        # 3. Formatear reporte
        report = format_health_report(is_healthy, issues, recent_stats, all_stats)
        
        # 4. Mostrar reporte
        print(report)
        
        # 5. Guardar a archivo
        with open(HEALTH_REPORT_FILE, 'a', encoding='utf-8') as f:
            f.write(report)
            f.write("\n\n")
        
        # 6. Si no está saludable, crear señal de pausa
        if not is_healthy:
            logger.error(f"❌ BOT NO SALUDABLE - Creando señal de pausa")
            create_pause_signal()
            send_telegram_alert(issues)
            return False
        else:
            logger.info(f"✅ BOT SALUDABLE - Removiendo señal de pausa si existe")
            remove_pause_signal()
            return True
    
    except Exception as e:
        logger.error(f"❌ Error en health check: {e}", exc_info=True)
        create_pause_signal()
        return False

def send_telegram_alert(issues: list):
    """Envía alerta crítica por Telegram."""
    if not issues:
        return
    
    try:
        from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
        
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return
        
        import requests
        
        message = "🚨 BOT PAUSADO POR SALUD CRÍTICA:\n\n" + "\n".join(issues)
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        requests.post(url, data=data, timeout=5)
    except:
        pass

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
