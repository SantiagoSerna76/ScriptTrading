#!/usr/bin/env python3
"""
Herramientas de análisis de trades
Úsalo para ver histórico, estadísticas, etc.
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from config import DB_FILE

class TradeAnalyzer:
    """Analiza histórico de trades"""
    
    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
    
    def get_all_trades(self):
        """Obtiene todos los trades cerrados"""
        try:
            conn = sqlite3.connect(self.db_file)
            query = """
            SELECT id, symbol, entry_price, exit_price, entry_quantity, 
                   profit_loss, profit_percent, entry_time, exit_time,
                   entry_reason, exit_reason
            FROM trades 
            WHERE status = 'CLOSED'
            ORDER BY exit_time DESC
            """
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def get_symbol_stats(self, symbol: str):
        """Estadísticas por símbolo"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) as losses,
                ROUND(100.0 * SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) / COUNT(*), 2) as win_rate,
                ROUND(SUM(profit_loss), 2) as total_pnl,
                ROUND(AVG(profit_percent), 2) as avg_return,
                ROUND(MAX(profit_loss), 2) as best_trade,
                ROUND(MIN(profit_loss), 2) as worst_trade
            FROM trades
            WHERE symbol = ? AND status = 'CLOSED'
            """, (symbol,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'symbol': symbol,
                    'total_trades': result[0] or 0,
                    'wins': result[1] or 0,
                    'losses': result[2] or 0,
                    'win_rate': result[3] or 0,
                    'total_pnl': result[4] or 0,
                    'avg_return': result[5] or 0,
                    'best_trade': result[6] or 0,
                    'worst_trade': result[7] or 0
                }
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def get_monthly_stats(self):
        """Estadísticas por mes"""
        try:
            conn = sqlite3.connect(self.db_file)
            query = """
            SELECT 
                strftime('%Y-%m', exit_time) as month,
                COUNT(*) as trades,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as wins,
                ROUND(SUM(profit_loss), 2) as pnl,
                ROUND(AVG(profit_percent), 2) as avg_return
            FROM trades
            WHERE status = 'CLOSED' AND exit_time IS NOT NULL
            GROUP BY strftime('%Y-%m', exit_time)
            ORDER BY month DESC
            """
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def get_best_and_worst_trades(self, limit: int = 5):
        """Mejores y peores trades"""
        try:
            conn = sqlite3.connect(self.db_file)
            
            # Mejores
            best_query = """
            SELECT id, symbol, entry_price, exit_price, profit_loss, profit_percent
            FROM trades
            WHERE status = 'CLOSED'
            ORDER BY profit_loss DESC
            LIMIT ?
            """
            
            # Peores
            worst_query = """
            SELECT id, symbol, entry_price, exit_price, profit_loss, profit_percent
            FROM trades
            WHERE status = 'CLOSED'
            ORDER BY profit_loss ASC
            LIMIT ?
            """
            
            best = pd.read_sql_query(best_query, conn, params=(limit,))
            worst = pd.read_sql_query(worst_query, conn, params=(limit,))
            
            conn.close()
            
            return {'best': best, 'worst': worst}
        except Exception as e:
            print(f"Error: {e}")
            return None

def print_all_trades():
    """Imprime todos los trades"""
    analyzer = TradeAnalyzer()
    trades = analyzer.get_all_trades()
    
    if trades is not None and len(trades) > 0:
        print("\n" + "=" * 100)
        print("HISTÓRICO DE TRADES")
        print("=" * 100)
        print(trades.to_string(index=False))
        print("=" * 100 + "\n")
    else:
        print("No hay trades registrados")

def print_symbol_stats(symbols: list = None):
    """Imprime estadísticas por símbolo"""
    analyzer = TradeAnalyzer()
    
    if symbols is None:
        # Obtén todos los símbolos
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM trades WHERE status = 'CLOSED'")
        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()
    
    if not symbols:
        print("No hay trades para analizar")
        return
    
    print("\n" + "=" * 100)
    print("ESTADÍSTICAS POR SÍMBOLO")
    print("=" * 100)
    
    for symbol in symbols:
        stats = analyzer.get_symbol_stats(symbol)
        if stats:
            print(f"\n{symbol}")
            print(f"  Trades: {stats['total_trades']} | Ganancias: {stats['wins']} | Pérdidas: {stats['losses']}")
            print(f"  Win Rate: {stats['win_rate']}% | Retorno Promedio: {stats['avg_return']}%")
            print(f"  P&L Total: ${stats['total_pnl']} | Mejor Trade: ${stats['best_trade']} | Peor Trade: ${stats['worst_trade']}")

def print_monthly_stats():
    """Imprime estadísticas mensuales"""
    analyzer = TradeAnalyzer()
    monthly = analyzer.get_monthly_stats()
    
    if monthly is not None and len(monthly) > 0:
        print("\n" + "=" * 80)
        print("ESTADÍSTICAS MENSUALES")
        print("=" * 80)
        print(monthly.to_string(index=False))
        print("=" * 80 + "\n")
    else:
        print("No hay datos mensuales")

def print_best_worst_trades(limit: int = 5):
    """Imprime mejores y peores trades"""
    analyzer = TradeAnalyzer()
    trades = analyzer.get_best_and_worst_trades(limit)
    
    if trades:
        print("\n" + "=" * 100)
        print(f"TOP {limit} MEJORES TRADES")
        print("=" * 100)
        print(trades['best'].to_string(index=False))
        
        print("\n" + "=" * 100)
        print(f"TOP {limit} PEORES TRADES")
        print("=" * 100)
        print(trades['worst'].to_string(index=False))
        print("=" * 100 + "\n")

def main():
    """Menú principal"""
    while True:
        print("\n=== ANALIZADOR DE TRADES ===")
        print("1. Ver todos los trades")
        print("2. Estadísticas por símbolo")
        print("3. Estadísticas mensuales")
        print("4. Top 5 mejores y peores trades")
        print("5. Salir")
        
        choice = input("\nElige opción (1-5): ").strip()
        
        if choice == '1':
            print_all_trades()
        elif choice == '2':
            print_symbol_stats()
        elif choice == '3':
            print_monthly_stats()
        elif choice == '4':
            limit = input("¿Cuántos top trades? (default 5): ").strip()
            limit = int(limit) if limit.isdigit() else 5
            print_best_worst_trades(limit)
        elif choice == '5':
            break
        else:
            print("Opción inválida")

if __name__ == "__main__":
    main()
