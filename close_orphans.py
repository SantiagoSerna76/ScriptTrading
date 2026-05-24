from database import TradeDatabase
import sqlite3

db = TradeDatabase()
conn = db._conn()
c = conn.cursor()

# Buscar trades abiertos de monedas que ya no monitoreamos
c.execute("SELECT id, symbol FROM trades WHERE status='OPEN' AND symbol='BNBUSDT'")
orphans = c.fetchall()

for row in orphans:
    trade_id = row[0]
    symbol = row[1]
    # Marcar como cerrado forzosamente
    c.execute("UPDATE trades SET status='CLOSED', exit_reason='Eliminado de Config', exit_price=entry_price, profit_loss=0, profit_percent=0, exit_time=CURRENT_TIMESTAMP WHERE id=?", (trade_id,))
    print(f"Trade fantasma de {symbol} cerrado.")

conn.commit()
conn.close()
print("Limpieza de base de datos terminada.")
