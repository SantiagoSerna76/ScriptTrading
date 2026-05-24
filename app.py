from flask import Flask, render_template, jsonify
from database import TradeDatabase

app = Flask(__name__)
db = TradeDatabase()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def api_stats():
    stats = db.get_trades_stats()
    daily_pnl = db.get_daily_pnl()
    if not stats:
        stats = {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl": 0}
    stats["daily_pnl"] = daily_pnl
    return jsonify(stats)

@app.route('/api/open_trades')
def api_open_trades():
    trades = db.get_open_trades()
    return jsonify(trades)

@app.route('/api/history')
def api_history():
    conn = db._conn()
    c = conn.cursor()
    c.execute("""
        SELECT symbol, side, entry_price, exit_price, exit_reason, profit_loss, profit_percent, exit_time
        FROM trades 
        WHERE status='CLOSED' 
        ORDER BY exit_time DESC LIMIT 20
    """)
    rows = c.fetchall()
    conn.close()
    
    history = []
    for r in rows:
        history.append({
            "symbol": r[0],
            "side": r[1],
            "entry_price": r[2],
            "exit_price": r[3],
            "reason": r[4],
            "pnl": r[5],
            "percent": r[6],
            "time": r[7]
        })
    return jsonify(history)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
