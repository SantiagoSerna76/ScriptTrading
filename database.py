import os
import logging
from datetime import datetime, date
from typing import Optional, List, Dict
import json
import sqlite3

try:
    import psycopg2
    from psycopg2 import errors
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

logger = logging.getLogger(__name__)

# Wrapper classes to adapt SQLite connections to match PostgreSQL parameter syntax (%s -> ?)
class SQLiteCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor
        
    def execute(self, sql, parameters=None):
        sql = sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        sql = sql.replace("%s", "?")
        if parameters is not None:
            return self.cursor.execute(sql, parameters)
        else:
            return self.cursor.execute(sql)
            
    def fetchone(self):
        return self.cursor.fetchone()
        
    def fetchall(self):
        return self.cursor.fetchall()
        
    def close(self):
        return self.cursor.close()
        
    def __iter__(self):
        return iter(self.cursor)
        
    def __getattr__(self, name):
        return getattr(self.cursor, name)

class SQLiteConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn
        
    def cursor(self):
        return SQLiteCursorWrapper(self.conn.cursor())
        
    def commit(self):
        return self.conn.commit()
        
    def rollback(self):
        return self.conn.rollback()
        
    def close(self):
        return self.conn.close()
        
    def __getattr__(self, name):
        return getattr(self.conn, name)

class TradeDatabase:
    """Base de datos de trades — Soporta PostgreSQL y SQLite de forma transparente."""

    def __init__(self, db_url=None):
        self.db_url = db_url or os.environ.get("DATABASE_URL")
        if not self.db_url:
            self.db_url = "trades.db"
            
        self.is_postgres = self.db_url.startswith("postgresql://") or self.db_url.startswith("postgres://")
        self._init()

    # ── Inicialización ────────────────────────────────────────────────────────
    def _init(self):
        conn = self._conn()
        if not conn: return
        try:
            c = conn.cursor()

            c.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id             SERIAL PRIMARY KEY,
                    symbol         TEXT    NOT NULL,
                    side           TEXT    NOT NULL DEFAULT 'BUY',
                    entry_price    REAL    NOT NULL,
                    entry_quantity REAL    NOT NULL,
                    entry_time     TEXT    NOT NULL,
                    entry_reason   TEXT,
                    exit_price     REAL,
                    exit_quantity  REAL,
                    exit_time      TEXT,
                    exit_reason    TEXT,
                    stop_loss      REAL,
                    take_profit    REAL,
                    profit_loss    REAL,
                    profit_percent REAL,
                    max_price      REAL,
                    trailing_sl    REAL,
                    status         TEXT    DEFAULT 'OPEN',
                    partial_exit_done BOOLEAN DEFAULT FALSE
                )
            """)
            conn.commit()

            # Migración: Añadir columnas si no existen
            try:
                c.execute("ALTER TABLE trades ADD COLUMN max_price REAL")
                conn.commit()
            except Exception:
                conn.rollback() # Limpiar estado de la transacción fallida
                
            try:
                c.execute("ALTER TABLE trades ADD COLUMN trailing_sl REAL")
                conn.commit()
            except Exception:
                conn.rollback()
                
            try:
                c.execute("ALTER TABLE trades ADD COLUMN partial_exit_done BOOLEAN DEFAULT FALSE")
                conn.commit()
            except Exception:
                conn.rollback()

            c.execute("""
                CREATE TABLE IF NOT EXISTS indicators (
                    id         SERIAL PRIMARY KEY,
                    symbol     TEXT NOT NULL,
                    timestamp  TEXT NOT NULL,
                    ema_short  REAL,
                    ema_long   REAL,
                    rsi        REAL,
                    atr        REAL,
                    adx        REAL,
                    volume     REAL,
                    volume_sma REAL
                )
            """)
            conn.commit()

            # Índices para consultas rápidas
            c.execute("CREATE INDEX IF NOT EXISTS idx_trades_status  ON trades (status)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol  ON trades (symbol)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_trades_exit    ON trades (exit_time)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_indicators_sym ON indicators (symbol, timestamp)")
            conn.commit()

            c.execute("""
                CREATE TABLE IF NOT EXISTS system_config (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()
            logger.info("Base de datos inicializada y migrada correctamente.")
        except Exception as e:
            logger.error(f"Error inicializando base de datos: {e}")
        finally:
            conn.close()

    def _conn(self):
        if not self.db_url:
            return None
        if self.is_postgres:
            if not PSYCOPG2_AVAILABLE:
                raise ImportError("Se requiere psycopg2 para conectar a PostgreSQL, pero no está disponible.")
            return psycopg2.connect(self.db_url)
        else:
            return SQLiteConnectionWrapper(sqlite3.connect(self.db_url))

    # ── Configuración Dinámica (Hot-Swapping) ─────────────────────────────────
    def set_config_value(self, key: str, value: str) -> None:
        """Guarda un valor de configuración dinámica en la base de datos."""
        conn = self._conn()
        if not conn: return
        try:
            c = conn.cursor()
            c.execute("""
                INSERT INTO system_config (key, value)
                VALUES (%s, %s)
                ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value
            """, (key, value))
            conn.commit()
        except Exception as e:
            logger.error(f"Error guardando config '{key}': {e}")
        finally:
            conn.close()

    def get_config_value(self, key: str, default_val: str = None) -> str:
        """Obtiene un valor de configuración de la base de datos."""
        conn = self._conn()
        if not conn: return default_val
        try:
            c = conn.cursor()
            c.execute("SELECT value FROM system_config WHERE key=%s", (key,))
            row = c.fetchone()
            if row:
                return row[0]
            return default_val
        except Exception as e:
            logger.error(f"Error leyendo config '{key}': {e}")
            return default_val
        finally:
            conn.close()

    # ── Escritura ─────────────────────────────────────────────────────────────
    def log_entry(self, symbol: str, entry_price: float, quantity: float,
                  stop_loss: float, take_profit: float, reason: str) -> int:
        conn = self._conn()
        if not conn: return -1
        try:
            c = conn.cursor()
            c.execute("""
                INSERT INTO trades
                (symbol, side, entry_price, entry_quantity, entry_time,
                 entry_reason, stop_loss, take_profit, max_price, trailing_sl, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (symbol, "BUY", float(entry_price), float(quantity),
                  datetime.now().isoformat(), reason,
                  float(stop_loss) if stop_loss is not None else None,
                  float(take_profit) if take_profit is not None else None,
                  float(entry_price),
                  float(stop_loss) if stop_loss is not None else None, "OPEN"))
            trade_id = c.fetchone()[0]
            conn.commit()
            logger.info(f"Trade abierto #{trade_id}: {symbol} @ ${entry_price:.4f}")
            return trade_id
        except Exception as e:
            logger.error(f"Error registrando entrada: {e}")
            return -1
        finally:
            conn.close()

    # back-compat alias
    def log_entry_signal(self, symbol, entry_price, quantity,
                         stop_loss, take_profit, reason):
        return self.log_entry(symbol, entry_price, quantity,
                              stop_loss, take_profit, reason)

    def log_exit(self, trade_id: int, exit_price: float,
                 exit_quantity: float, reason: str) -> bool:
        conn = self._conn()
        if not conn: return False
        try:
            c = conn.cursor()
            c.execute("SELECT entry_price, entry_quantity FROM trades WHERE id=%s",
                      (trade_id,))
            row = c.fetchone()
            if not row:
                return False

            entry_price, entry_qty = row
            pnl     = (float(exit_price) - float(entry_price)) * float(exit_quantity)
            pct     = (float(exit_price) - float(entry_price)) / float(entry_price) * 100

            c.execute("""
                UPDATE trades
                SET exit_price=%s, exit_quantity=%s, exit_time=%s,
                    exit_reason=%s, profit_loss=%s, profit_percent=%s, status=%s
                WHERE id=%s
            """, (float(exit_price), float(exit_quantity), datetime.now().isoformat(),
                  reason, float(pnl), float(pct), "CLOSED", int(trade_id)))
            conn.commit()

            emoji = "✅" if pnl >= 0 else "❌"
            logger.info(f"{emoji} Trade #{trade_id} cerrado ({reason}) → P&L ${pnl:.2f} ({pct:.2f}%)")
            return True
        except Exception as e:
            logger.error(f"Error registrando salida: {e}")
            return False
        finally:
            conn.close()

    def log_partial_exit(self, trade_id: int, exit_price: float, exit_quantity: float, reason: str) -> bool:
        """Registra una salida parcial reduciendo la cantidad del trade original y creando un registro de ganancia cerrada."""
        conn = self._conn()
        if not conn: return False
        try:
            c = conn.cursor()
            c.execute("SELECT symbol, side, entry_price, entry_quantity, entry_time, entry_reason, stop_loss, take_profit, max_price, trailing_sl FROM trades WHERE id=%s", (trade_id,))
            orig = c.fetchone()
            if not orig:
                return False
                
            symbol, side, entry_price, entry_qty, entry_time, entry_reason, sl, tp, max_p, tr_sl = orig
            
            # 1. Update original trade to reduce its quantity and set flag
            new_qty = float(entry_qty) - float(exit_quantity)
            c.execute("UPDATE trades SET entry_quantity=%s, partial_exit_done=TRUE WHERE id=%s", (new_qty, int(trade_id)))
            
            # 2. Insert new CLOSED trade record for the exited portion
            pnl = (float(exit_price) - float(entry_price)) * float(exit_quantity)
            pct = (float(exit_price) - float(entry_price)) / float(entry_price) * 100
            
            c.execute("""
                INSERT INTO trades
                (symbol, side, entry_price, entry_quantity, entry_time, entry_reason,
                 exit_price, exit_quantity, exit_time, exit_reason, stop_loss, take_profit,
                 profit_loss, profit_percent, max_price, trailing_sl, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                symbol, side, float(entry_price), float(exit_quantity), entry_time, entry_reason,
                float(exit_price), float(exit_quantity), datetime.now().isoformat(), reason,
                float(sl) if sl is not None else None,
                float(tp) if tp is not None else None,
                float(pnl), float(pct),
                float(max_p) if max_p is not None else None,
                float(tr_sl) if tr_sl is not None else None, "CLOSED"
            ))
            
            conn.commit()
            logger.info(f"✨ Trade #{trade_id} (Parcial 50% cerrado a ${exit_price:.4f}) → Ganancia asegurada ${pnl:.2f}")
            return True
        except Exception as e:
            logger.error(f"Error registrando salida parcial en BD: {e}")
            return False
        finally:
            conn.close()

    # back-compat alias
    def log_exit_signal(self, trade_id, exit_price, exit_quantity, reason):
        return self.log_exit(trade_id, exit_price, exit_quantity, reason)

    def log_indicators(self, symbol: str, indicators: Dict):
        conn = self._conn()
        if not conn: return
        
        def s_float(val):
            return float(val) if val is not None else None
            
        try:
            c = conn.cursor()
            c.execute("""
                INSERT INTO indicators
                (symbol, timestamp, ema_short, ema_long, rsi, atr, adx, volume, volume_sma)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (symbol, datetime.now().isoformat(),
                  s_float(indicators.get("ema_short")), s_float(indicators.get("ema_long")),
                  s_float(indicators.get("rsi")),       s_float(indicators.get("atr")),
                  s_float(indicators.get("adx")),       s_float(indicators.get("volume")),
                  s_float(indicators.get("volume_sma"))))
            conn.commit()
        except Exception as e:
            logger.error(f"Error guardando indicadores: {e}")
        finally:
            conn.close()

    # ── Lectura ───────────────────────────────────────────────────────────────
    def get_open_trades(self) -> List[Dict]:
        conn = self._conn()
        if not conn: return []
        try:
            c = conn.cursor()
            c.execute("""
                SELECT id, symbol, entry_price, entry_quantity, stop_loss, take_profit, entry_time, max_price, trailing_sl, partial_exit_done
                FROM trades WHERE status='OPEN'
            """)
            rows = c.fetchall()
            return [
                {
                    "id": r[0],
                    "symbol": r[1],
                    "entry_price": r[2],
                    "entry_quantity": r[3],
                    "stop_loss": r[4],
                    "take_profit": r[5],
                    "entry_time": r[6],
                    "max_price": r[7] if r[7] is not None else r[2],
                    "trailing_sl": r[8] if r[8] is not None else r[4],
                    "partial_exit_done": bool(r[9]) if r[9] is not None else False
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Error leyendo trades abiertos: {e}")
            return []
        finally:
            conn.close()

    def update_trailing_sl(self, trade_id: int, trailing_sl: float, max_price: float) -> bool:
        """Actualiza el trailing stop loss y el precio máximo en la base de datos para persistencia."""
        conn = self._conn()
        if not conn: return False
        try:
            c = conn.cursor()
            c.execute("""
                UPDATE trades
                SET trailing_sl=%s, max_price=%s
                WHERE id=%s
            """, (float(trailing_sl) if trailing_sl is not None else None,
                  float(max_price) if max_price is not None else None, int(trade_id)))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error actualizando trailing stop en BD para trade #{trade_id}: {e}")
            return False
        finally:
            conn.close()

    def get_daily_pnl(self, day: date = None) -> float:
        """P&L realizado en el día calendario indicado (default: hoy)."""
        if day is None:
            day = date.today()
        day_str = day.isoformat()
        conn = self._conn()
        if not conn: return 0.0
        try:
            c = conn.cursor()
            c.execute("""
                SELECT COALESCE(SUM(profit_loss), 0)
                FROM trades
                WHERE status='CLOSED'
                  AND exit_time LIKE %s
            """, (day_str + '%',))
            return float(c.fetchone()[0] or 0.0)
        except Exception as e:
            logger.error(f"Error calculando P&L diario: {e}")
            return 0.0
        finally:
            conn.close()

    def get_daily_trade_count(self, day: date = None) -> int:
        """Número de trades cerrados en el día."""
        if day is None:
            day = date.today()
        day_str = day.isoformat()
        conn = self._conn()
        if not conn: return 0
        try:
            c = conn.cursor()
            c.execute("""
                SELECT COUNT(*) FROM trades
                WHERE status='CLOSED' AND exit_time LIKE %s
            """, (day_str + '%',))
            return int(c.fetchone()[0])
        except Exception as e:
            return 0
        finally:
            conn.close()

    def get_trades_stats(self) -> Dict:
        conn = self._conn()
        if not conn: return {}
        try:
            c = conn.cursor()
            c.execute("""
                SELECT
                  COUNT(*),
                  SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END),
                  SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END),
                  COALESCE(SUM(profit_loss), 0),
                  COALESCE(AVG(profit_percent), 0),
                  COALESCE(SUM(CASE WHEN profit_loss > 0 THEN profit_loss ELSE 0 END), 0),
                  COALESCE(SUM(CASE WHEN profit_loss < 0 THEN profit_loss ELSE 0 END), 0)
                FROM trades WHERE status='CLOSED'
            """)
            r = c.fetchone()

            total = r[0] or 0
            wins  = r[1] or 0
            return {
                "total_trades":          total,
                "wins":                  wins,
                "losses":                r[2] or 0,
                "win_rate":              round(wins / total * 100, 2) if total else 0,
                "total_pnl":             round(r[3], 2),
                "avg_percent_per_trade": round(float(r[4]), 2) if r[4] else 0.0,
                "win_amount":            round(r[5], 2),
                "loss_amount":           round(r[6], 2),
            }
        except Exception as e:
            logger.error(f"Error calculando stats: {e}")
            return {}
        finally:
            conn.close()

    def get_symbol_trades_stats(self, symbol: str) -> Dict:
        """Obtiene estadísticas de rendimiento históricas para un símbolo específico."""
        conn = self._conn()
        if not conn:
            return {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "win_loss_ratio": 0.0}
        try:
            c = conn.cursor()
            c.execute("""
                SELECT
                  COUNT(*),
                  SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END),
                  SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END),
                  COALESCE(AVG(CASE WHEN profit_loss > 0 THEN profit_loss END), 0),
                  COALESCE(AVG(CASE WHEN profit_loss < 0 THEN ABS(profit_loss) END), 0)
                FROM trades 
                WHERE symbol = %s AND status = 'CLOSED'
            """, (symbol,))
            r = c.fetchone()
            
            total = r[0] or 0
            wins = r[1] or 0
            losses = r[2] or 0
            avg_win = float(r[3]) if r[3] else 0.0
            avg_loss = float(r[4]) if r[4] else 0.0
            
            win_rate = wins / total if total > 0 else 0.0
            win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0
            
            return {
                "total_trades": total,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "win_loss_ratio": win_loss_ratio
            }
        except Exception as e:
            logger.error(f"Error calculando stats para {symbol}: {e}")
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "win_loss_ratio": 0.0
            }
        finally:
            conn.close()

    def get_consecutive_losses(self, symbol: str) -> int:
        """Cuenta cuántas pérdidas consecutivas lleva un símbolo."""
        conn = self._conn()
        if not conn: return 0
        try:
            c = conn.cursor()
            c.execute("""
                SELECT profit_loss FROM trades 
                WHERE symbol = %s AND status = 'CLOSED' 
                ORDER BY exit_time DESC LIMIT 10
            """, (symbol,))
            rows = c.fetchall()
            losses = 0
            for r in rows:
                if r[0] < 0:
                    losses += 1
                else:
                    break
            return losses
        except Exception as e:
            logger.error(f"Error contando pérdidas consecutivas para {symbol}: {e}")
            return 0
        finally:
            conn.close()

    def get_last_exit_time(self, symbol: str) -> float:
        """Devuelve el timestamp de la última vez que se cerró un trade de este símbolo."""
        conn = self._conn()
        if not conn: return 0.0
        try:
            c = conn.cursor()
            c.execute("""
                SELECT exit_time FROM trades 
                WHERE symbol = %s AND status = 'CLOSED' 
                ORDER BY exit_time DESC LIMIT 1
            """, (symbol,))
            row = c.fetchone()
            if row and row[0]:
                return datetime.fromisoformat(row[0]).timestamp()
            return 0.0
        except Exception as e:
            logger.error(f"Error obteniendo last exit time para {symbol}: {e}")
            return 0.0
        finally:
            conn.close()
