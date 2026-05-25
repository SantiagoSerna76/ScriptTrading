#!/usr/bin/env python3
"""Verificar estado actual del bot y rentabilidad."""
import sqlite3
from datetime import datetime, date

conn = sqlite3.connect('trades.db')
c = conn.cursor()

# Estadísticas generales
c.execute('''
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) as losses,
        AVG(profit_loss) as avg_pnl,
        SUM(profit_loss) as total_pnl,
        AVG(profit_percent) as avg_pct,
        MIN(profit_percent) as min_pct,
        MAX(profit_percent) as max_pct
    FROM trades 
    WHERE status = 'CLOSED'
''')
row = c.fetchone()

print('=' * 60)
print('ESTADO ACTUAL DEL BOT')
print('=' * 60)
print(f'Trades cerrados: {row[0]}')
print(f'Wins: {row[1]} | Losses: {row[2]}')
wr = row[1]/row[0]*100 if row[0] > 0 else 0
print(f'Win Rate: {wr:.1f}%')
print(f'P&L Total: ${row[4]:.2f}')
print(f'Avg P&L/trade: ${row[3]:.2f}')
print(f'Avg %/trade: {row[5]:.2f}%')
print(f'Min trade: {row[6]:.2f}%')
print(f'Max trade: {row[7]:.2f}%')

# Profit Factor
c.execute('''
    SELECT 
        SUM(CASE WHEN profit_loss > 0 THEN profit_loss ELSE 0 END) as gross_profit,
        ABS(SUM(CASE WHEN profit_loss < 0 THEN profit_loss ELSE 0 END)) as gross_loss
    FROM trades WHERE status = 'CLOSED'
''')
gp_gl = c.fetchone()
pf = gp_gl[0] / gp_gl[1] if gp_gl[1] > 0 else float('inf')
print(f'Gross Profit: ${gp_gl[0]:.2f}')
print(f'Gross Loss: ${gp_gl[1]:.2f}')
print(f'Profit Factor: {pf:.2f}x')

# Por símbolo
c.execute('''
    SELECT symbol, COUNT(*) as trades, 
           SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as wins,
           SUM(profit_loss) as total_pl,
           AVG(profit_percent) as avg_pct
    FROM trades WHERE status = 'CLOSED'
    GROUP BY symbol
    ORDER BY total_pl DESC
''')
print('\nPerformance por símbolo:')
for r in c.fetchall():
    wr_sym = r[2]/r[1]*100 if r[1] > 0 else 0
    print(f'  {r[0]}: {r[1]} trades, WR={wr_sym:.0f}%, P&L=${r[3]:.2f}, Avg={r[4]:.2f}%')

# Posiciones abiertas
c.execute("SELECT id, symbol, entry_price, trailing_sl, entry_quantity, partial_exit_done FROM trades WHERE status = 'OPEN'")
opens = c.fetchall()
print(f'\nPosiciones abiertas: {len(opens)}')
for o in opens:
    pnl_pct = (o[3]/o[2]-1)*100
    print(f'  #{o[0]} {o[1]}: entry=${o[2]}, SL=${o[3]}, qty={o[4]}, parcial={bool(o[5])}, SL+{pnl_pct:.1f}%')

# Fecha del primer trade
c.execute('SELECT MIN(entry_time), MAX(entry_time) FROM trades')
ft = c.fetchone()
print(f'\nPrimer trade: {ft[0]}')
print(f'Último trade: {ft[1]}')

# ¿Cuántos trades faltan para ML?
min_trades_ml = 30
current = row[0]
if current >= min_trades_ml:
    print(f'\n[OK] ¡YA TIENES {current} TRADES! Listo para entrenar ML.')
else:
    print(f'\n[WARNING] Faltan {min_trades_ml - current} trades para entrenar ML (necesitas {min_trades_ml})')

conn.close()
