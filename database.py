import sqlite3
import logging
from datetime import datetime, date
from typing import Optional, List, Dict
from config import DB_FILE

logger = logging.getLogger(__name__)


class TradeDatabase:
    """Base de datos de trades — SQLite con índices y estadísticas diarias."""

    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
        self._init()

    # ── Inicialización ────────────────────────────────────────────────────────
    def _init(self):
        conn = self._conn()
        try:
            c = conn.cursor()

            c.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    partial_exit_done BOOLEAN DEFAULT 0
                )
            """)

            # Migración: Añadir columnas si no existen en base de datos previa
            try:
                c.execute("ALTER TABLE trades ADD COLUMN max_price REAL")
            except sqlite3.OperationalError:
                pass  # La columna ya existe

            try:
                c.execute("ALTER TABLE trades ADD COLUMN trailing_sl REAL")
            except sqlite3.OperationalError:
                pass  # La columna ya existe
                
            try:
                c.execute("ALTER TABLE trades ADD COLUMN partial_exit_done BOOLEAN DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # La columna ya existe

            c.execute("""
                CREATE TABLE IF NOT EXISTS indicators (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
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

            # Índices para consultas rápidas
            c.execute("CREATE INDEX IF NOT EXISTS idx_trades_status  ON trades (status)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol  ON trades (symbol)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_trades_exit    ON trades (exit_time)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_indicators_sym ON indicators (symbol, timestamp)")

            conn.commit()
            logger.info(f"Base de datos lista y migrada: {self.db_file}")
        except Exception as e:
            logger.error(f"Error inicializando base de datos: {e}")
        finally:
            conn.close()

    def _conn(self):
        return sqlite3.connect(self.db_file)

    # ── Escritura ─────────────────────────────────────────────────────────────
    def log_entry(self, symbol: str, entry_price: float, quantity: float,
                  stop_loss: float, take_profit: float, reason: str) -> int:
        conn = self._conn()
        try:
            c = conn.cursor()
            c.execute("""
                INSERT INTO trades
                (symbol, side, entry_price, entry_quantity, entry_time,
                 entry_reason, stop_loss, take_profit, max_price, trailing_sl, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (symbol, "BUY", entry_price, quantity,
                  datetime.now().isoformat(), reason,
                  stop_loss, take_profit, entry_price, stop_loss, "OPEN"))
            trade_id = c.lastrowid
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
        try:
            c = conn.cursor()
            c.execute("SELECT entry_price, entry_quantity FROM trades WHERE id=?",
                      (trade_id,))
            row = c.fetchone()
            if not row:
                return False

            entry_price, entry_qty = row
            pnl     = (exit_price - entry_price) * exit_quantity
            pct     = (exit_price - entry_price) / entry_price * 100

            c.execute("""
                UPDATE trades
                SET exit_price=?, exit_quantity=?, exit_time=?,
                    exit_reason=?, profit_loss=?, profit_percent=?, status=?
                WHERE id=?
            """, (exit_price, exit_quantity, datetime.now().isoformat(),
                  reason, pnl, pct, "CLOSED", trade_id))
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
        try:
            c = conn.cursor()
            c.execute("SELECT symbol, side, entry_price, entry_quantity, entry_time, entry_reason, stop_loss, take_profit, max_price, trailing_sl FROM trades WHERE id=?", (trade_id,))
            orig = c.fetchone()
            if not orig:
                return False
                
            symbol, side, entry_price, entry_qty, entry_time, entry_reason, sl, tp, max_p, tr_sl = orig
            
            # 1. Update original trade to reduce its quantity and set flag
            new_qty = entry_qty - exit_quantity
            c.execute("UPDATE trades SET entry_quantity=?, partial_exit_done=1 WHERE id=?", (new_qty, trade_id))
            
            # 2. Insert new CLOSED trade record for the exited portion
            pnl = (exit_price - entry_price) * exit_quantity
            pct = (exit_price - entry_price) / entry_price * 100
            
            c.execute("""
                INSERT INTO trades
                (symbol, side, entry_price, entry_quantity, entry_time, entry_reason,
                 exit_price, exit_quantity, exit_time, exit_reason, stop_loss, take_profit,
                 profit_loss, profit_percent, max_price, trailing_sl, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                symbol, side, entry_price, exit_quantity, entry_time, entry_reason,
                exit_price, exit_quantity, datetime.now().isoformat(), reason, sl, tp,
                pnl, pct, max_p, tr_sl, "CLOSED"
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
        try:
            c = conn.cursor()
            c.execute("""
                INSERT INTO indicators
                (symbol, timestamp, ema_short, ema_long, rsi, atr, adx, volume, volume_sma)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (symbol, datetime.now().isoformat(),
                  indicators.get("ema_short"), indicators.get("ema_long"),
                  indicators.get("rsi"),       indicators.get("atr"),
                  indicators.get("adx"),       indicators.get("volume"),
                  indicators.get("volume_sma")))
            conn.commit()
        except Exception as e:
            logger.error(f"Error guardando indicadores: {e}")
        finally:
            conn.close()

    # ── Lectura ───────────────────────────────────────────────────────────────
    def get_open_trades(self) -> List[Dict]:
        conn = self._conn()
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
        try:
            c = conn.cursor()
            c.execute("""
                UPDATE trades
                SET trailing_sl=?, max_price=?
                WHERE id=?
            """, (trailing_sl, max_price, trade_id))
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
        try:
            c = conn.cursor()
            c.execute("""
                SELECT COALESCE(SUM(profit_loss), 0)
                FROM trades
                WHERE status='CLOSED'
                  AND DATE(exit_time) = ?
            """, (day_str,))
            return c.fetchone()[0]
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
        try:
            c = conn.cursor()
            c.execute("""
                SELECT COUNT(*) FROM trades
                WHERE status='CLOSED' AND DATE(exit_time) = ?
            """, (day_str,))
            return c.fetchone()[0]
        except Exception as e:
            return 0
        finally:
            conn.close()

    def get_trades_stats(self) -> Dict:
        conn = self._conn()
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
                "avg_percent_per_trade": round(r[4], 2),
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
                WHERE symbol = ? AND status = 'CLOSED'
            """, (symbol,))
            r = c.fetchone()
            
            total = r[0] or 0
            wins = r[1] or 0
            losses = r[2] or 0
            avg_win = r[3] or 0.0
            avg_loss = r[4] or 0.0
            
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

