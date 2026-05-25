#!/usr/bin/env python3
"""Simulación: ¿Cuántos trades abriría el bot con ADX>=20 en diferentes escenarios?"""
from backtest import Backtest
import logging
logging.basicConfig(level=logging.WARNING)

SYMBOLS = ['INJUSDT', 'ICPUSDT', 'UNIUSDT', 'APTUSDT', 'FILUSDT']

print('=' * 60)
print('BACKTEST CON NUEVO FILTRO ADX>=20')
print('=' * 60)

total_trades = 0
total_pnl = 0
total_wins = 0

for sym in SYMBOLS:
    bt = Backtest(sym, 500)
    bt.run(days=60, print_results=False)
    s = bt.summary()
    total_trades += s['trades']
    total_pnl += s['pnl']
    total_wins += s['wins']
    
    wr = s['wr']
    status = 'GREEN' if wr >= 55 else 'YELLOW' if wr >= 50 else 'RED'
    print(f'{sym}: {s["trades"]} trades | WR={wr:.0f}% | P&L=${s["pnl"]:.2f}')

overall_wr = total_wins/total_trades*100 if total_trades > 0 else 0
print(f'\nTOTAL: {total_trades} trades | WR={overall_wr:.0f}% | P&L=${total_pnl:.2f}')
print(f'\nCon 30+ trades podrías entrenar el modelo ML.')
