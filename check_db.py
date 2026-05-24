import sqlite3
import pandas as pd

try:
    conn = sqlite3.connect('trades.db')
    df = pd.read_sql_query("SELECT id, symbol, status, entry_price, stop_loss, trailing_sl, max_price FROM trades WHERE status='OPEN'", conn)
    print("--- POSICIONES ABIERTAS ---")
    print(df.to_string(index=False))
    
    df2 = pd.read_sql_query("SELECT id, symbol, exit_price, profit_loss, exit_reason FROM trades WHERE status='CLOSED' ORDER BY id DESC LIMIT 2", conn)
    print("\n--- ULTIMOS 2 TRADES CERRADOS ---")
    print(df2.to_string(index=False))
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")
