#!/usr/bin/env python3
"""
MONITOREO DIARIO AUTOMATIZADO

Ejecuta un resumen diario del performance del bot:
  • P&L total y ROI
  • Win rate
  • Trades ejecutados hoy
  • Drawdown máximo
  • Alertas si algo está fuera de rango

USO:
    python monitor_daily.py
    
O agregar a cron (Linux/Mac):
    0 9,12,18,21 * * * python /path/to/monitor_daily.py
    
O programar en Windows Task Scheduler para:
    09:00, 12:00, 18:00, 21:00
"""

import sqlite3
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple
import sys

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
MONITOR_LOG_FILE = "monitor_daily.log"

# Umbrales de alerta
ALERT_WIN_RATE_MIN = 0.45  # Alerta si < 45%
ALERT_DAILY_LOSS = 5.0     # Alerta si pérdida diaria > $5
ALERT_MAX_CONSECUTIVE_LOSSES = 3

def get_db_connection():
    """Retorna conexión a BD."""
    return sqlite3.connect(DB_FILE)

def get_all_time_stats() -> Dict:
    """Retorna estadísticas de TODO el tiempo."""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Trades cerrados
    c.execute("""
        SELECT COUNT(*), SUM(profit_loss), AVG(profit_loss), 
               MAX(profit_loss), MIN(profit_loss), AVG(profit_percent)
        FROM trades 
        WHERE status = 'CLOSED' OR exit_time IS NOT NULL
    """)
    row = c.fetchone()
    
    stats = {
        'total_trades': row[0] or 0,
        'total_pl': row[1] or 0.0,
        'avg_trade_pl': row[2] or 0.0,
        'best_trade': row[3] or 0.0,
        'worst_trade': row[4] or 0.0,
        'avg_trade_pct': row[5] or 0.0,
    }
    
    # Win rate
    c.execute("""
        SELECT COUNT(*) FROM trades 
        WHERE (status = 'CLOSED' OR exit_time IS NOT NULL) 
        AND profit_loss > 0
    """)
    wins = c.fetchone()[0] or 0
    stats['wins'] = wins
    stats['losses'] = stats['total_trades'] - wins
    stats['win_rate'] = wins / stats['total_trades'] if stats['total_trades'] > 0 else 0.0
    
    # Profit Factor
    c.execute("""
        SELECT SUM(profit_loss) FROM trades 
        WHERE (status = 'CLOSED' OR exit_time IS NOT NULL) 
        AND profit_loss > 0
    """)
    gross_profit = c.fetchone()[0] or 0.0
    
    c.execute("""
        SELECT ABS(SUM(profit_loss)) FROM trades 
        WHERE (status = 'CLOSED' OR exit_time IS NOT NULL) 
        AND profit_loss < 0
    """)
    gross_loss = c.fetchone()[0] or 0.0
    
    stats['gross_profit'] = gross_profit
    stats['gross_loss'] = gross_loss
    stats['profit_factor'] = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    conn.close()
    return stats

def get_daily_stats(date_str: str = None) -> Dict:
    """Retorna estadísticas del día especificado (o hoy)."""
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Trades del día
    c.execute("""
        SELECT COUNT(*), SUM(profit_loss), AVG(profit_loss)
        FROM trades 
        WHERE DATE(exit_time) = ? AND (status = 'CLOSED' OR exit_time IS NOT NULL)
    """, (date_str,))
    row = c.fetchone()
    
    stats = {
        'date': date_str,
        'total_trades': row[0] or 0,
        'total_pl': row[1] or 0.0,
        'avg_trade_pl': row[2] or 0.0,
    }
    
    # Win rate del día
    c.execute("""
        SELECT COUNT(*) FROM trades 
        WHERE DATE(exit_time) = ? AND (status = 'CLOSED' OR exit_time IS NOT NULL) 
        AND profit_loss > 0
    """, (date_str,))
    wins = c.fetchone()[0] or 0
    stats['wins'] = wins
    stats['losses'] = stats['total_trades'] - wins
    stats['win_rate'] = wins / stats['total_trades'] if stats['total_trades'] > 0 else 0.0
    
    # Posiciones abiertas
    c.execute("""
        SELECT COUNT(*) FROM trades WHERE status = 'OPEN' OR exit_time IS NULL
    """)
    stats['open_positions'] = c.fetchone()[0] or 0
    
    conn.close()
    return stats

def get_last_n_trades(n: int = 10) -> list:
    """Retorna los últimos N trades."""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("""
        SELECT symbol, entry_time, exit_time, entry_price, exit_price, 
               profit_loss, profit_percent, status
        FROM trades
        WHERE status = 'CLOSED' OR exit_time IS NOT NULL
        ORDER BY entry_time DESC
        LIMIT ?
    """, (n,))
    
    trades = []
    for row in c.fetchall():
        trades.append({
            'symbol': row[0],
            'entry_time': row[1],
            'exit_time': row[2],
            'entry_price': row[3],
            'exit_price': row[4],
            'pl': row[5],
            'pl_pct': row[6],
            'status': row[7],
        })
    
    conn.close()
    return trades

def check_alerts(all_stats: Dict, daily_stats: Dict) -> list:
    """Verifica si hay alertas que mostrar."""
    alerts = []
    
    # Alerta 1: Win rate bajó
    if all_stats['total_trades'] >= 10 and all_stats['win_rate'] < ALERT_WIN_RATE_MIN:
        alerts.append(f"⚠️ WIN RATE BAJO: {all_stats['win_rate']*100:.1f}% (< {ALERT_WIN_RATE_MIN*100:.0f}%)")
    
    # Alerta 2: Pérdida del día muy alta
    if daily_stats['total_pl'] < -ALERT_DAILY_LOSS:
        alerts.append(f"⚠️ PÉRDIDA DIARIA ALTA: ${daily_stats['total_pl']:.2f}")
    
    # Alerta 3: Posiciones abiertas sin cerrar
    if daily_stats['open_positions'] > 2:
        alerts.append(f"⚠️ MUCHAS POSICIONES ABIERTAS: {daily_stats['open_positions']}")
    
    # Alerta 4: Profit Factor bajo
    if all_stats['total_trades'] >= 10 and all_stats['profit_factor'] < 1.2:
        alerts.append(f"⚠️ PROFIT FACTOR BAJO: {all_stats['profit_factor']:.2f} (< 1.2)")
    
    return alerts

def format_report(all_stats: Dict, daily_stats: Dict, alerts: list) -> str:
    """Formatea el reporte de monitoreo."""
    report = []
    report.append("=" * 80)
    report.append(f"📊 REPORTE DE MONITOREO - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 80)
    
    # Estadísticas generales
    report.append("\n📈 ESTADÍSTICAS GENERAL (TODO EL TIEMPO):")
    report.append(f"  • Total trades: {all_stats['total_trades']}")
    report.append(f"  • Ganancias: {all_stats['wins']}")
    report.append(f"  • Pérdidas: {all_stats['losses']}")
    report.append(f"  • Win rate: {all_stats['win_rate']*100:.1f}%")
    report.append(f"  • P&L total: ${all_stats['total_pl']:.2f}")
    report.append(f"  • P&L promedio/trade: ${all_stats['avg_trade_pl']:.2f}")
    report.append(f"  • Mejor trade: ${all_stats['best_trade']:.2f}")
    report.append(f"  • Peor trade: ${all_stats['worst_trade']:.2f}")
    report.append(f"  • Gross profit: ${all_stats['gross_profit']:.2f}")
    report.append(f"  • Gross loss: ${all_stats['gross_loss']:.2f}")
    report.append(f"  • Profit factor: {all_stats['profit_factor']:.2f}x")
    
    # Estadísticas del día
    report.append(f"\n📅 ESTADÍSTICAS HOY ({daily_stats['date']}):")
    report.append(f"  • Trades: {daily_stats['total_trades']}")
    report.append(f"  • Ganancias: {daily_stats['wins']}")
    report.append(f"  • Pérdidas: {daily_stats['losses']}")
    report.append(f"  • Win rate: {daily_stats['win_rate']*100:.1f}%")
    report.append(f"  • P&L: ${daily_stats['total_pl']:.2f}")
    report.append(f"  • P&L promedio: ${daily_stats['avg_trade_pl']:.2f}")
    report.append(f"  • Posiciones abiertas: {daily_stats['open_positions']}")
    
    # Últimos 5 trades
    report.append("\n📋 ÚLTIMOS 5 TRADES:")
    last_trades = get_last_n_trades(5)
    if last_trades:
        for i, trade in enumerate(last_trades, 1):
            pl_emoji = "✅" if trade['pl'] > 0 else "❌"
            report.append(f"  {i}. {pl_emoji} {trade['symbol']} @ {trade['entry_price']:.4f} → "
                         f"{trade['exit_price']:.4f} | P&L: ${trade['pl']:.2f} ({trade['pl_pct']:.2f}%) | "
                         f"Status: {trade['status']}")
    else:
        report.append("  (Sin trades aún)")
    
    # Alertas
    if alerts:
        report.append("\n⚠️ ALERTAS:")
        for alert in alerts:
            report.append(f"  {alert}")
    else:
        report.append("\n✅ Sin alertas")
    
    report.append("\n" + "=" * 80)
    
    return "\n".join(report)

def save_to_file(report: str):
    """Guarda el reporte a archivo log."""
    with open(MONITOR_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(report)
        f.write("\n\n")

def send_telegram_alert(alerts: list):
    """Envía alertas por Telegram si existen."""
    if not alerts:
        return
    
    try:
        from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
        
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.warning("Telegram no configurado")
            return
        
        import requests
        
        message = "🚨 ALERTAS DEL BOT:\n\n" + "\n".join(alerts)
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, data=data, timeout=5)
        if response.status_code == 200:
            logger.info("✅ Alertas enviadas por Telegram")
        else:
            logger.warning(f"Error al enviar Telegram: {response.status_code}")
    
    except Exception as e:
        logger.warning(f"No se pudieron enviar alertas por Telegram: {e}")

def main():
    """Flujo principal."""
    logger.info("🔍 Generando reporte de monitoreo...")
    
    try:
        # 1. Obtener estadísticas
        all_stats = get_all_time_stats()
        daily_stats = get_daily_stats()
        
        # 2. Verificar alertas
        alerts = check_alerts(all_stats, daily_stats)
        
        # 3. Formatear reporte
        report = format_report(all_stats, daily_stats, alerts)
        
        # 4. Mostrar en terminal
        print(report)
        
        # 5. Guardar a archivo
        save_to_file(report)
        
        # 6. Enviar alertas por Telegram
        if alerts:
            send_telegram_alert(alerts)
        
        logger.info("✅ Reporte generado exitosamente")
        return True
    
    except Exception as e:
        logger.error(f"❌ Error al generar reporte: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
