import threading
import json
from flask import Flask, render_template, jsonify, request
from database import TradeDatabase
from notifier import TelegramNotifier

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

@app.route('/api/config')
def api_config():
    entry_symbols_raw = db.get_config_value("ENTRY_SYMBOLS")
    elite_symbols_raw = db.get_config_value("RELAXED_MACRO_SYMBOLS")
    last_scan = db.get_config_value("LAST_SCAN_TIME", "Nunca")
    
    def parse_syms(raw_val, default_list):
        if not raw_val: return default_list
        try:
            if isinstance(raw_val, list): return raw_val
            parsed = json.loads(raw_val)
            if isinstance(parsed, list): return parsed
        except: pass
        return default_list

    from config import ENTRY_SYMBOLS, RELAXED_MACRO_SYMBOLS
    entry_symbols = parse_syms(entry_symbols_raw, ENTRY_SYMBOLS)
    elite_symbols = parse_syms(elite_symbols_raw, RELAXED_MACRO_SYMBOLS)

    return jsonify({
        "entry_symbols": entry_symbols,
        "elite_symbols": elite_symbols,
        "last_scan": last_scan
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
