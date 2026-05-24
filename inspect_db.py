import sqlite3
conn = sqlite3.connect('trades.db')
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(trades)")
columns = cursor.fetchall()
print("Columns in 'trades' table:")
for col in columns:
    print(col)
conn.close()
