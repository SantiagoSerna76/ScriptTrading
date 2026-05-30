#!/usr/bin/env python3
"""
Bot de Trading Spot — Binance
Estrategia: EMA + RSI (Wilder) + ATR + ADX + MACD + Stoch
Sistema de señales por puntuación + circuit breaker diario
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from config import (
    API_KEY, SECRET_KEY, SYMBOLS, CAPITAL_TOTAL_USDT,
    RIESGO_POR_TRADE, TIMEFRAME, POLLING_INTERVAL, LOG_FILE,
    MAX_OPEN_POSITIONS, MIN_BUY_COOLDOWN_S,
    MAX_DAILY_LOSS_USDT, MAX_DAILY_TRADES,
    MIN_ORDER_NOTIONAL, KLINES_LIMIT, MIN_HOLD_HOURS,
    PAPER_TRADING, USE_TESTNET, TRADING_FEE_RATE, ADX_MIN,
    RELAXED_MACRO_SYMBOLS, ENTRY_SYMBOLS, PROXY_URL,
    BREAKEVEN_ATR_MULT, MAX_HOLD_HOURS, PAUSE_SIGNAL_FILE,
)
from binance_api import BinanceAPI, parse_klines_to_dataframe
from strategy import StrategySignals
from mtf_analyzer import MultiTimeframeAnalyzer
from database import TradeDatabase
from notifier import TelegramNotifier

# ── Ajuste de Codificación Consola (Windows) ──────────────────────────────────
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

def round_step(value: float, step: float) -> float:
    """Redondea un valor hacia abajo al paso (step) especificado."""
    if not step or step == 0:
        return value
    return round(int(round(value, 8) / step) * step, 8)


class TradingBot:
    """Bot principal de trading con gestión de riesgo y circuit breaker."""

    def __init__(self):
        self.paper_trading = PAPER_TRADING
        self.api      = BinanceAPI(API_KEY, SECRET_KEY, use_testnet=USE_TESTNET, proxy_url=PROXY_URL)
        self.strategy = StrategySignals()
        self.db       = TradeDatabase()
        self.mtf      = MultiTimeframeAnalyzer()
        self.notifier = TelegramNotifier()

        # Símbolos Activos y Hot-Swap
        self.symbols = SYMBOLS.copy()
        self.entry_symbols = ENTRY_SYMBOLS.copy()
        self.relaxed_symbols = RELAXED_MACRO_SYMBOLS.copy()

        # Garantizar que todos los ENTRY_SYMBOLS sean monitoreados y analizados
        for s in self.entry_symbols:
            if s not in self.symbols:
                self.symbols.append(s)

        # Reglas de precisión dinámicas
        self.trading_rules: Dict[str, Dict] = {}
        self._load_trading_rules()

        # Estado en memoria
        self.open_trades: Dict[str, Dict]  = {}
        self.last_buy_time: Dict[str, float] = {s: 0.0 for s in self.symbols}
        self.last_daily_summary = datetime.now().date()

        # Capital por posición
        self.capital_per_trade = CAPITAL_TOTAL_USDT / MAX_OPEN_POSITIONS

        # P&L tracking para paper trading
        self.paper_pnl = 0.0
        self.paper_fees = 0.0

        mode = "📝 PAPER TRADING (sin órdenes reales)" if self.paper_trading else "💰 PRODUCCIÓN (órdenes reales)"
        net = "MAINNET" if not USE_TESTNET else "TESTNET"

        logger.info("=" * 60)
        logger.info(f"🤖  Bot de Trading iniciado — {mode}")
        logger.info(f"    Red            : {net}")
        logger.info(f"    Capital total  : ${CAPITAL_TOTAL_USDT}")
        logger.info(f"    Capital/trade  : ${self.capital_per_trade:.2f}")
        logger.info(f"    Riesgo/trade   : {RIESGO_POR_TRADE * 100:.1f} %")
        logger.info(f"    Posiciones max : {MAX_OPEN_POSITIONS}")
        logger.info(f"    Símbolos       : {self.symbols}")
        logger.info(f"    Timeframe      : {TIMEFRAME}")
        logger.info(f"    Fee rate       : {TRADING_FEE_RATE*100:.2f}%")
        logger.info("=" * 60)
        self.notifier.send_message(
            f"🚀 *Bot Iniciado*\n"
            f"Modo: `{mode}`\n"
            f"Red: `{net}`\n"
            f"Capital: `${CAPITAL_TOTAL_USDT}`"
        )

        # Recuperar posiciones abiertas de la base de datos (evita huérfanas en reinicios)
        self._load_open_trades_from_db()

    @staticmethod
    def _resolve_tp_target(take_profit, stop_loss) -> float:
        """Normaliza TP a float; evita TypeError si take_profit es NULL en BD."""
        tp = take_profit if take_profit is not None else stop_loss
        if tp is None:
            return 0.0
        try:
            return float(tp)
        except (TypeError, ValueError):
            return 0.0

    def _load_open_trades_from_db(self):
        """Carga las posiciones abiertas guardadas en la base de datos para recuperar el estado tras un reinicio."""
        logger.info("Cargando posiciones abiertas desde la base de datos...")
        open_trades_db = self.db.get_open_trades()
        for t in open_trades_db:
            symbol = t["symbol"]
            # Failsafe Hot-Swap: Asegurar que las posiciones huérfanas NO se abandonen
            if symbol not in self.symbols:
                logger.warning(f"⚠️ Posición abierta huérfana detectada para {symbol}. Se agrega al monitoreo activo de forma forzosa (Hot-Swap Failsafe).")
                self.symbols.append(symbol)
                if symbol not in self.trading_rules:
                    rules = self.api.get_symbol_rules(symbol)
                    self.trading_rules[symbol] = rules if rules else {"step_size": 0.01, "tick_size": 0.01, "min_notional": MIN_ORDER_NOTIONAL}
                if symbol not in self.last_buy_time:
                    self.last_buy_time[symbol] = 0.0

            # Carga la fecha de apertura para lógica de Time Stop
            opened_at = t.get("opened_at")
            if isinstance(opened_at, str):
                try:
                    opened_at = datetime.fromisoformat(opened_at)
                except (ValueError, TypeError):
                    opened_at = datetime.now()
            elif opened_at is None:
                opened_at = datetime.now()

            self.open_trades[symbol] = {
                "trade_id":        t["id"],
                "entry_price":     t["entry_price"],
                "quantity":        t["entry_quantity"],
                "stop_loss":       t["stop_loss"],
                "take_profit":     t["take_profit"],
                "max_price":       t.get("max_price", t["entry_price"]),
                "opened_at":       opened_at,
                "atr":             0,  # No podemos recuperar ATR de DB
                "breakeven_active": False,
            }
            logger.info(
                f"📈  Recuperado trade abierto #{t['id']} para {symbol}: "
                f"Entrada=${t['entry_price']:.4f}, Qty={t['entry_quantity']:.6f}, "
                f"SL=${t['stop_loss']:.4f}"
            )

    def _load_trading_rules(self):
        """Descarga reglas de trading de Binance en tiempo de ejecución."""
        logger.info("Cargando filtros de precisión y reglas de trading desde Binance...")
        for symbol in self.symbols:
            rules = self.api.get_symbol_rules(symbol)
            if rules:
                self.trading_rules[symbol] = rules
                logger.info(
                    f"⚙️  Reglas para {symbol}: "
                    f"step_size={rules['step_size']}, "
                    f"tick_size={rules['tick_size']}, "
                    f"min_notional=${rules['min_notional']}"
                )
            else:
                # Fallback por seguridad si Binance API no responde
                fallback_steps = {"BTCUSDT": 0.00001, "ETHUSDT": 0.0001, "BNBUSDT": 0.01, "SOLUSDT": 0.01}
                self.trading_rules[symbol] = {
                    "step_size": fallback_steps.get(symbol, 0.01),
                    "tick_size": 0.01,
                    "min_notional": MIN_ORDER_NOTIONAL
                }
                logger.warning(f"⚠️  No se pudieron obtener reglas de Binance para {symbol}. Usando fallback.")

    def round_qty(self, symbol: str, quantity: float) -> float:
        step = self.trading_rules.get(symbol, {}).get("step_size", 0.01)
        return round_step(quantity, step)

    def round_price(self, symbol: str, price: float) -> float:
        tick = self.trading_rules.get(symbol, {}).get("tick_size", 0.01)
        return round_step(price, tick)

    # ─────────────────────────────────────────────────────────────────────────
    # Circuit Breaker diario
    # ─────────────────────────────────────────────────────────────────────────
    def _circuit_breaker_ok(self) -> bool:
        """
        Devuelve False si el bot debe dejar de operar por el resto del día:
          - Pérdida diaria supera MAX_DAILY_LOSS_USDT
          - Se alcanzó MAX_DAILY_TRADES
        """
        daily_pnl    = self.db.get_daily_pnl()
        daily_trades = self.db.get_daily_trade_count()

        if daily_pnl <= -abs(MAX_DAILY_LOSS_USDT):
            logger.warning(
                f"🛑  CIRCUIT BREAKER: pérdida diaria ${daily_pnl:.2f} "
                f"≥ límite ${MAX_DAILY_LOSS_USDT}. "
                f"Sin más trades hoy."
            )
            return False

        if daily_trades >= MAX_DAILY_TRADES:
            logger.warning(
                f"🛑  CIRCUIT BREAKER: {daily_trades} trades hoy "
                f"≥ límite {MAX_DAILY_TRADES}."
            )
            return False

        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Loop principal
    # ─────────────────────────────────────────────────────────────────────────
    def run(self):
        """Loop principal — NO recursivo. Usa while con sleep."""
        logger.info("🚀  Iniciando loop de trading …\n")
        iteration = 0

        while True:
            iteration += 1
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[{ts}] — Iteración #{iteration}")

            # ── Resumen diario (cada día a medianoche) ──
            today = datetime.now().date()
            if today > self.last_daily_summary:
                self._print_daily_summary()
                self.last_daily_summary = today

            try:
                self._cycle()
            except KeyboardInterrupt:
                logger.info("\n⚠️  Bot detenido por el usuario.")
                self._print_stats()
                sys.exit(0)
            except Exception as e:
                # Registra el error pero NO termina el proceso
                logger.error(f"Error en ciclo #{iteration}: {e}", exc_info=True)

            if iteration % 10 == 0:
                self._print_stats()

            try:
                logger.info(f"⏳  Esperando {POLLING_INTERVAL}s …\n")
                time.sleep(POLLING_INTERVAL)
            except KeyboardInterrupt:
                logger.info("\n⚠️  Bot detenido por el usuario.")
                self._print_stats()
                sys.exit(0)

    def _cycle(self):
        """Un ciclo completo de análisis sobre todos los símbolos."""

        # --- NUEVO: Interés Compuesto Dinámico ---
        if self.paper_trading:
            # En paper trading, sumamos el P&L simulado al capital inicial
            current_balance = CAPITAL_TOTAL_USDT + self.paper_pnl
        else:
            # En real, leemos el saldo real disponible (usando fallback si falla)
            try:
                current_balance = float(self.api.get_usdt_balance())
            except Exception as e:
                logger.warning(f"Error leyendo balance para compounding: {e}")
                current_balance = self.capital_per_trade * MAX_OPEN_POSITIONS

        # Aseguramos un mínimo para evitar divisiones por cero si el balance baja mucho
        current_balance = max(current_balance, MIN_ORDER_NOTIONAL * MAX_OPEN_POSITIONS)

        open_pos_count = len(self.open_trades)
        if open_pos_count < MAX_OPEN_POSITIONS:
            # Dividimos el balance actual entre el TOTAL de slots (no los disponibles).
            # Esto evita sobredimensionar posiciones cuando quedan pocos slots libres.
            # Ej: balance=$500, MAX=3 → capital_per_trade=$167 siempre, no $500 si solo queda 1 slot.
            self.capital_per_trade = current_balance / MAX_OPEN_POSITIONS
        else:
            self.capital_per_trade = 0.0
        # -----------------------------------------

        # 1) Verificamos circuit breaker pero NO salimos (debemos monitorear posiciones abiertas)
        can_open_new = self._circuit_breaker_ok()

        # Health check puede pausar NUEVAS entradas sin desatender salidas/trailing.
        if Path(PAUSE_SIGNAL_FILE).exists():
            can_open_new = False
            logger.warning(f"🛑  Señal de pausa activa ({PAUSE_SIGNAL_FILE}). Solo se gestionan posiciones abiertas.")

        # ── HOT-SWAP DYNAMIC CONFIG ──
        try:
            import json
            dynamic_entry_raw = self.db.get_config_value("ENTRY_SYMBOLS")
            dynamic_elite_raw = self.db.get_config_value("RELAXED_MACRO_SYMBOLS")
            
            if dynamic_entry_raw:
                dynamic_entry = json.loads(dynamic_entry_raw)
                if isinstance(dynamic_entry, list) and len(dynamic_entry) > 0:
                    self.entry_symbols = dynamic_entry
                    
            if dynamic_elite_raw:
                dynamic_elite = json.loads(dynamic_elite_raw)
                if isinstance(dynamic_elite, list) and len(dynamic_elite) > 0:
                    self.relaxed_symbols = dynamic_elite
                    # Asegurar que las nuevas monedas estén en el universo general (symbols)
                    for s in self.entry_symbols:
                        if s not in self.symbols:
                            self.symbols.append(s)
                            if s not in self.trading_rules:
                                rules = self.api.get_symbol_rules(s)
                                self.trading_rules[s] = rules if rules else {"step_size": 0.01, "tick_size": 0.01, "min_notional": MIN_ORDER_NOTIONAL}
                            if s not in self.last_buy_time:
                                self.last_buy_time[s] = 0.0
        except Exception as e:
            logger.error(f"Error cargando config dinámica: {e}")

        for symbol in self.symbols:
            try:
                self._analyze(symbol, can_open_new=can_open_new)
            except Exception as e:
                logger.error(f"Error analizando {symbol}: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Análisis por símbolo (ahora con MTF)
    # ─────────────────────────────────────────────────────────────────────────
    def _analyze(self, symbol: str, can_open_new: bool = True):
        """Análisis por símbolo: entrada y salida."""
        klines_1h = self.api.get_klines(symbol, TIMEFRAME, limit=KLINES_LIMIT)
        klines_4h = self.api.get_klines(symbol, "4h", limit=300)

        if not klines_1h:
            logger.warning(f"Sin datos para {symbol}")
            return

        df_1h = parse_klines_to_dataframe(klines_1h)
        df_1h = self.strategy.calculate_indicators(df_1h)
        last_1h = df_1h.iloc[-1]

        # Log macro context (informativo, no bloquea)
        if klines_4h:
            df_4h = parse_klines_to_dataframe(klines_4h)
            macro_ctx = self.mtf.get_macro_context(df_4h)
            logger.info(f"{symbol} | 4H: {macro_ctx}")

        # Guardar indicadores en BD
        try:
            self.db.log_indicators(symbol, {
                "ema_short":  last_1h["ema_short"],
                "ema_long":   last_1h["ema_long"],
                "rsi":        last_1h["rsi"],
                "atr":        last_1h["atr"],
                "adx":        last_1h["adx"],
                "volume":     last_1h["volume"],
                "volume_sma": last_1h["volume_sma"],
            })
        except Exception:
            pass

        # ── Posición abierta → verificar salida
        if symbol in self.open_trades:
            self._check_exit(symbol, last_1h["close"], df_1h)
            return

        # ── Si no puede abrir nuevas → salir
        if not can_open_new:
            return

        # Solo abre en entry_symbols
        if symbol not in self.entry_symbols:
            return

        # ── Check buy signal
        buy_signal, conds = self.strategy.check_buy_signal(df_1h)

        logger.info(
            f"{symbol} | ${last_1h['close']:.4f} | "
            f"RSI={conds.get('rsi', 0):.1f} | "
            f"ADX={conds.get('adx', 0):.1f} | "
            f"Dist EMA20={conds.get('dist_ema20', 99):.1f}% | "
            f"score={conds.get('score', 0)}/{conds.get('min_score', 3)} | "
            f"{conds.get('regime', 'N/A')}"
        )

        if buy_signal:
            self._open_trade(symbol, df_1h, conds)

    # ─────────────────────────────────────────────────────────────────────────
    # Abrir posición
    # ─────────────────────────────────────────────────────────────────────────
    def _open_trade(self, symbol: str, df, conds: Dict):
        # ── Guards de pre-entrada ─────────────────────────────────────────────

        # 1. Demasiadas posiciones abiertas
        if len(self.open_trades) >= MAX_OPEN_POSITIONS:
            logger.info(f"Max posiciones ({MAX_OPEN_POSITIONS}) alcanzado. Ignorando {symbol}.")
            return

        # 2. Cooldown por símbolo
        from config import SL_COOLDOWN_S, CONSECUTIVE_LOSS_MAX

        last_exit = self.db.get_last_exit_time(symbol)
        elapsed_since_exit = time.time() - last_exit

        consec_losses = self.db.get_consecutive_losses(symbol)

        cooldown_needed = MIN_BUY_COOLDOWN_S
        if consec_losses >= CONSECUTIVE_LOSS_MAX:
            cooldown_needed = max(cooldown_needed, 4 * 3600)
            logger.info(f"⚠️ {symbol} tiene {consec_losses} pérdidas seguidas. Cooldown extendido (4h).")
        elif consec_losses > 0:
            cooldown_needed = max(cooldown_needed, SL_COOLDOWN_S)

        elapsed_since_buy = time.time() - self.last_buy_time[symbol]

        if elapsed_since_buy < cooldown_needed or elapsed_since_exit < cooldown_needed:
            remaining = max(cooldown_needed - elapsed_since_buy, cooldown_needed - elapsed_since_exit) / 3600
            logger.info(f"Cooldown activo para {symbol}: {remaining:.1f}h restantes.")
            return

        entry_price = df.iloc[-1]["close"]
        sl, tp, atr = self.strategy.calculate_sl_tp(entry_price, df)

        if sl is None:
            logger.info(f"{symbol} | Trade RECHAZADO: volatilidad excesiva (SL > {MAX_SL_PCT}% del entry).")
            return

        # ── Position Sizing ───────────────────────────────────────────────────
        regime = conds.get('regime', 'NORMAL')
        size_multiplier = self.strategy.get_position_size_multiplier(regime)
        qty = (self.capital_per_trade * size_multiplier) / entry_price

        qty_rounded = self.round_qty(symbol, qty)

        # Ajuste automático al mínimo notional
        notional = qty_rounded * entry_price
        if 0 < notional < MIN_ORDER_NOTIONAL:
            min_qty = MIN_ORDER_NOTIONAL / entry_price * 1.05
            min_qty = min(min_qty, self.capital_per_trade / entry_price)
            qty_rounded = self.round_qty(symbol, min_qty)
            logger.info(f"{symbol} | Qty ajustado al mínimo: {qty_rounded} (notional ${qty_rounded * entry_price:.2f})")

        # Validación notional
        if qty_rounded * entry_price < MIN_ORDER_NOTIONAL:
            logger.warning(f"Trade rechazado ({symbol}): notional ${qty_rounded * entry_price:.2f} < min ${MIN_ORDER_NOTIONAL}")
            return

        # ── Log y Ejecución ───────────────────────────────────────────────────
        logger.info(f"\n{'=' * 60}")
        logger.info(f"🟢  SEÑAL DE COMPRA: {symbol}")
        logger.info(f"    Régimen     : {conds.get('regime', 'N/A')}")
        logger.info(f"    Score       : {conds.get('score', 0)}/{conds.get('min_score', 3)}")
        logger.info(f"    Precio Est. : ${entry_price:.4f}")
        logger.info(f"    Stop Loss   : ${sl:.4f}  ({(sl/entry_price - 1)*100:.2f}%)")
        logger.info(f"    Take Profit : ${tp:.4f}  ({(tp/entry_price - 1)*100:+.2f}%)")
        logger.info(f"    Cantidad    : {qty_rounded:.6f}  (notional est. ${qty_rounded*entry_price:.2f})")
        logger.info(f"    ATR         : ${atr:.4f}")
        logger.info(f"{'=' * 60}\n")

        if self.paper_trading:
            order = {"status": "FILLED", "fills": [{"price": str(entry_price), "qty": str(qty_rounded)}]}
            fee = entry_price * qty_rounded * TRADING_FEE_RATE
            self.paper_fees += fee
            logger.info(f"📝  [PAPER] Compra simulada: {qty_rounded} {symbol} @ ${entry_price:.4f} (fee ${fee:.4f})")
        else:
            order = self.api.place_order(
                symbol=symbol, side="BUY", type_="MARKET", quantity=qty_rounded
            )

        if not order:
            logger.error(f"❌  Orden de compra rechazada por Binance para {symbol}")
            return

        # Calcular precio real de ejecución desde fills
        fills = order.get("fills", [])
        if fills:
            total_qty = sum(float(f["qty"]) for f in fills)
            if total_qty > 0:
                entry_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / total_qty
                sl_new, tp_new, atr = self.strategy.calculate_sl_tp(entry_price, df)
                if sl_new is not None:
                    sl, tp = sl_new, tp_new
                if not self.paper_trading:
                    logger.info(f"✨ Precio real de entrada (fills): ${entry_price:.4f}. SL y TP recalculados.")

        sl = self.round_price(symbol, sl)
        tp = self.round_price(symbol, tp)

        mode_tag = "[PAPER] " if self.paper_trading else ""
        trade_id = self.db.log_entry(
            symbol=symbol, entry_price=entry_price, quantity=qty_rounded,
            stop_loss=sl, take_profit=tp,
            reason=f"{mode_tag}Score {conds.get('score')}/{conds.get('min_score', 3)} | {conds.get('regime', 'N/A')}",
        )

        self.open_trades[symbol] = {
            "trade_id":        trade_id,
            "entry_price":     entry_price,
            "quantity":        qty_rounded,
            "stop_loss":       sl,
            "take_profit":     tp,
            "max_price":       entry_price,
            "opened_at":       datetime.now(),
            "atr":             atr,
            "breakeven_active": False,
        }

        self.last_buy_time[symbol] = time.time()
        logger.info(f"✅  {mode_tag}Compra ejecutada: {symbol} #{trade_id} a ${entry_price:.4f}")
        self.notifier.send_message(
            f"🟢 *COMPRA: {symbol}*\n"
            f"Precio: `${entry_price:.4f}`\n"
            f"SL: `${sl:.4f}` ({(sl/entry_price-1)*100:.1f}%)\n"
            f"TP: `${tp:.4f}` ({(tp/entry_price-1)*100:+.1f}%)\n"
            f"Score: `{conds.get('score', 0)}/{conds.get('min_score', 3)}`\n"
            f"Modo: {mode_tag.strip() or 'REAL'}"
        )

    def _check_exit(self, symbol: str, price: float, df):
        """
        Momentum Dip Buyer Exit:
        1. Take Profit fijo
        2. Stop Loss fijo
        3. Breakeven: después de +1 ATR, SL sube a entry
        4. Time Stop: después de MAX_HOLD_HOURS, cerrar al mercado
        """
        trade = self.open_trades[symbol]
        entry    = trade["entry_price"]
        sl       = trade["stop_loss"]
        tp       = trade["take_profit"]
        trade_id = trade["trade_id"]
        atr      = trade.get("atr", 0)

        # Actualiza máximo histórico
        if price > trade["max_price"]:
            trade["max_price"] = price

        # ── Breakeven: si ganancia >= BREAKEVEN_ATR_MULT × ATR → SL sube a entry
        if atr > 0 and not trade.get("breakeven_active", False):
            breakeven_target = entry + (BREAKEVEN_ATR_MULT * atr)
            if price >= breakeven_target:
                trade["stop_loss"] = entry
                trade["breakeven_active"] = True
                sl = entry
                logger.info(f"🛡️  {symbol} | Breakeven activado: SL subido a ${entry:.4f}")

        exit_price  = None
        exit_reason = None

        # 1. Take Profit
        if price >= tp:
            exit_price  = price
            exit_reason = f"✅ Take Profit ${tp:.4f} (+{(tp/entry-1)*100:.1f}%)"

        # 2. Stop Loss
        elif price <= sl:
            exit_price  = price
            be_tag = " (Breakeven)" if trade.get("breakeven_active") else ""
            exit_reason = f"🛑 Stop Loss ${sl:.4f}{be_tag} ({(sl/entry-1)*100:.1f}%)"

        # 3. Time Stop
        elif "opened_at" in trade:
            hold_hours = (datetime.now() - trade["opened_at"]).total_seconds() / 3600
            if hold_hours >= MAX_HOLD_HOURS:
                pnl_pct = (price / entry - 1) * 100
                exit_price = price
                exit_reason = f"⏰ Time Stop ({hold_hours:.0f}h, {pnl_pct:+.1f}%)"

        if exit_price is None:
            return

        self._close_trade(symbol, exit_price, trade_id, exit_reason)

    def _close_trade(self, symbol: str, exit_price: float,
                     trade_id: int, reason: str):
        trade = self.open_trades[symbol]
        qty   = trade["quantity"]
        entry = trade["entry_price"]
        pnl   = (exit_price - entry) * qty

        qty_rounded = self.round_qty(symbol, qty)

        if self.paper_trading:
            # PAPER TRADING: simular venta
            order = {"status": "FILLED", "fills": [{"price": str(exit_price), "qty": str(qty_rounded)}]}
            fee = exit_price * qty_rounded * TRADING_FEE_RATE
            self.paper_fees += fee
            pnl_net = pnl - fee - (entry * qty * TRADING_FEE_RATE)
            self.paper_pnl += pnl_net
            logger.info(f"📝  [PAPER] Venta simulada: {qty_rounded} {symbol} @ ${exit_price:.4f} (fee ${fee:.4f})")
        else:
            order = self.api.place_order(
                symbol=symbol, side="SELL", type_="MARKET", quantity=qty_rounded
            )

        if not order:
            logger.error(f"❌  Orden de venta FALLIDA para {symbol}. Reintentando en próximo ciclo.")
            return

        # Calcular precio real de ejecución de la venta desde fills
        fills = order.get("fills", [])
        if fills:
            total_qty = sum(float(f["qty"]) for f in fills)
            if total_qty > 0:
                exit_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / total_qty
                pnl = (exit_price - entry) * qty
                if not self.paper_trading:
                    logger.info(f"✨ Precio real de salida (fills): ${exit_price:.4f}")

        exit_price = self.round_price(symbol, exit_price)

        self.db.log_exit(trade_id, exit_price, qty, reason)

        mode_tag = "[PAPER] " if self.paper_trading else ""
        emoji = "✅" if pnl >= 0 else "❌"
        logger.info(f"\n{'=' * 60}")
        logger.info(f"{emoji}  {mode_tag}VENTA: {symbol} — {reason}")
        logger.info(f"    Entrada: ${entry:.4f} → Salida: ${exit_price:.4f}")
        logger.info(f"    P&L    : ${pnl:.2f}  ({(exit_price/entry - 1)*100:.2f}%)")
        self.notifier.send_message(
            f"{emoji} *VENTA: {symbol}*\n"
            f"P&L: `${pnl:.2f}` ({(exit_price/entry - 1)*100:.2f}%)\n"
            f"Razón: {reason}\n"
            f"Modo: {mode_tag.strip() or 'REAL'}"
        )
        if self.paper_trading:
            logger.info(f"    P&L acumulado (paper): ${self.paper_pnl:.2f} | Fees: ${self.paper_fees:.2f}")
        logger.info(f"{'=' * 60}\n")

        del self.open_trades[symbol]

    # ─────────────────────────────────────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────────────────────────────────────
    def _print_stats(self):
        """Estadísticas rápidas cada 10 iteraciones."""
        logger.info(f"\n{'─' * 60}")
        logger.info(f"📊  SNAPSHOT")
        logger.info(f"    Posiciones abiertas: {len(self.open_trades)}")
        if self.open_trades:
            for symbol, trade in self.open_trades.items():
                logger.info(f"      • {symbol} @ ${trade['entry_price']:.4f} (SL ${trade['stop_loss']:.4f})")

        stats = self.db.get_trades_stats()
        if stats and stats.get("total_trades", 0) > 0:
            daily_pnl = self.db.get_daily_pnl()
            logger.info(f"    Trades cerrados: {stats['total_trades']} ({stats['wins']}W/{stats['losses']}L, {stats['win_rate']:.1f}% WR)")
            logger.info(f"    P&L hoy: ${daily_pnl:.2f} | Total: ${stats['total_pnl']:.2f}")
        else:
            logger.info(f"    Sin trades cerrados aún")
        logger.info(f"{'─' * 60}\n")

    def _print_daily_summary(self):
        """Resumen completo al cambiar de día."""
        yesterday = self.last_daily_summary
        logger.info(f"\n{'=' * 60}")
        logger.info(f"📈  RESUMEN DEL DÍA {yesterday}")
        logger.info(f"{'=' * 60}")

        stats = self.db.get_trades_stats()
        daily_pnl = self.db.get_daily_pnl()

        if not stats or stats.get("total_trades", 0) == 0:
            logger.info(f"Sin trades ejecutados el {yesterday}")
        else:
            logger.info(f"  Trades        : {stats['total_trades']} ({stats['wins']}W / {stats['losses']}L)")
            logger.info(f"  Win Rate      : {stats['win_rate']:.2f}%")
            logger.info(f"  P&L día       : ${daily_pnl:+.2f}")
            logger.info(f"  P&L total     : ${stats['total_pnl']:+.2f}")
            logger.info(f"  Avg/trade     : {stats['avg_percent_per_trade']:+.2f}%")

        logger.info(f"{'=' * 60}\n")
        if stats and stats.get("total_trades", 0) > 0:
            self.notifier.send_message(
                f"📊 *Resumen Diario*\n"
                f"P&L Hoy: `${daily_pnl:+.2f}`\n"
                f"Win Rate: `{stats['win_rate']:.2f}%`"
            )


def main():
    bot = TradingBot()
    bot.run()


if __name__ == "__main__":
    main()
