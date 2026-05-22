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
from typing import Dict, Optional

from config import (
    API_KEY, SECRET_KEY, SYMBOLS, CAPITAL_TOTAL_USDT,
    RIESGO_POR_TRADE, TIMEFRAME, POLLING_INTERVAL, LOG_FILE,
    MAX_OPEN_POSITIONS, MIN_BUY_COOLDOWN_S,
    MAX_DAILY_LOSS_USDT, MAX_DAILY_TRADES,
    MIN_ORDER_NOTIONAL, KLINES_LIMIT, MIN_HOLD_HOURS,
    PAPER_TRADING, USE_TESTNET, TRADING_FEE_RATE,
)
from binance_api import BinanceAPI, parse_klines_to_dataframe
from strategy import StrategySignals, RiskManager, TrailingStopManager
from mtf_analyzer import MultiTimeframeAnalyzer
from microstructure import OrderBookAnalyzer
from database import TradeDatabase

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
        self.api      = BinanceAPI(API_KEY, SECRET_KEY, use_testnet=USE_TESTNET)
        self.strategy = StrategySignals()
        self.risk     = RiskManager()
        self.db       = TradeDatabase()
        self.mtf      = MultiTimeframeAnalyzer()
        self.ob       = OrderBookAnalyzer(API_KEY, SECRET_KEY)
        self.trailing = TrailingStopManager()

        # Reglas de precisión dinámicas
        self.trading_rules: Dict[str, Dict] = {}
        self._load_trading_rules()

        # Estado en memoria
        self.open_trades: Dict[str, Dict]  = {}
        self.last_buy_time: Dict[str, float] = {s: 0.0 for s in SYMBOLS}
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
        logger.info(f"    Símbolos       : {SYMBOLS}")
        logger.info(f"    Timeframe      : {TIMEFRAME}")
        logger.info(f"    Fee rate       : {TRADING_FEE_RATE*100:.2f}%")
        logger.info("=" * 60)

    def _load_trading_rules(self):
        """Descarga reglas de trading de Binance en tiempo de ejecución."""
        logger.info("Cargando filtros de precisión y reglas de trading desde Binance...")
        for symbol in SYMBOLS:
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

            logger.info(f"⏳  Esperando {POLLING_INTERVAL}s …\n")
            time.sleep(POLLING_INTERVAL)

    def _cycle(self):
        """Un ciclo completo de análisis sobre todos los símbolos."""
        # 1) Circuit breaker antes de cualquier análisis nuevo
        if not self._circuit_breaker_ok():
            return

        for symbol in SYMBOLS:
            try:
                self._analyze(symbol)
            except Exception as e:
                logger.error(f"Error analizando {symbol}: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Análisis por símbolo (ahora con MTF)
    # ─────────────────────────────────────────────────────────────────────────
    def _analyze(self, symbol: str):
        # ── Obtiene datos de múltiples timeframes ──────────────────────────────
        klines_1h = self.api.get_klines(symbol, "1h", limit=KLINES_LIMIT)
        klines_4h = self.api.get_klines(symbol, "4h", limit=300)  # 300 velas de 4H para asegurar datos suficientes para EMA200 (>210)

        if not klines_1h or not klines_4h:
            logger.warning(f"Sin datos para {symbol} (1H o 4H)")
            return

        df_1h = parse_klines_to_dataframe(klines_1h)
        df_4h = parse_klines_to_dataframe(klines_4h)

        df_1h = self.strategy.calculate_indicators(df_1h)
        df_4h = self.strategy.calculate_indicators(df_4h)

        last_1h = df_1h.iloc[-1]

        # ── Análisis Multi-Timeframe ──────────────────────────────────────────
        macro_conds = self.mtf.analyze_macro_trend(df_4h)
        logger.info(
            f"{symbol} | 4H Macro: {macro_conds.get('reason', 'ERROR')} | "
            f"ADX={macro_conds.get('adx', 0):.1f} | EMA200=${macro_conds.get('ema200', 0):.2f}"
        )

        # Guarda indicadores en BD
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

        # ── Posición abierta → verificar salida ──────────────────────────────
        if symbol in self.open_trades:
            self._check_exit(symbol, last_1h["close"], df_1h)
            return

        # ── Sin posición → verificar entrada ────────────────────────────────
        buy_signal_1h, conds_1h = self.strategy.check_buy_signal(df_1h)

        # Agrega precio actual a los detalles
        conds_1h["close_price"] = last_1h["close"]

        logger.info(
            f"{symbol} | precio=${last_1h['close']:.4f} | "
            f"RSI={conds_1h.get('rsi', 0):.1f} | "
            f"ADX={conds_1h.get('adx', 0):.1f} | "
            f"score={conds_1h.get('score', 0)}/{conds_1h.get('min_score', 7)}"
        )

        # ── Combina señal 1H + validación macro 4H ────────────────────────────
        if buy_signal_1h or conds_1h.get('score', 0) >= 6:
            if "No hay suficientes datos 4H" not in macro_conds.get('reason', ''):
                # Validación MTF completa con datos de 4H
                buy_signal_mtf, mtf_details = self.mtf.validate_entry_with_macro(
                    df_1h, macro_conds, buy_signal_1h, conds_1h
                )
            else:
                # Sin datos 4H suficientes → rechazar entrada por seguridad
                buy_signal_mtf = False
                mtf_details = {'reason': 'Datos 4H insuficientes para validación macro'}
                logger.warning(f"{symbol} | ⚠️  Sin datos 4H suficientes. Entrada rechazada.")

            if buy_signal_mtf:
                self._open_trade(symbol, df_1h, mtf_details)
            else:
                logger.info(f"{symbol} | Señal rechazada: {mtf_details.get('reason', 'N/A')}")

    # ─────────────────────────────────────────────────────────────────────────
    # Abrir posición (con validación de Order Book)
    # ─────────────────────────────────────────────────────────────────────────
    def _open_trade(self, symbol: str, df, conds: Dict):
        # ── Guards de pre-entrada ─────────────────────────────────────────────

        # 1. Demasiadas posiciones abiertas
        if len(self.open_trades) >= MAX_OPEN_POSITIONS:
            logger.info(f"Max posiciones ({MAX_OPEN_POSITIONS}) alcanzado. Ignorando {symbol}.")
            return

        # 2. Cooldown por símbolo
        elapsed = time.time() - self.last_buy_time[symbol]
        if elapsed < MIN_BUY_COOLDOWN_S:
            remaining = (MIN_BUY_COOLDOWN_S - elapsed) / 3600
            logger.info(f"Cooldown activo para {symbol}: {remaining:.1f}h restantes.")
            return

        entry_price = df.iloc[-1]["close"]
        sl, tp, atr = self.strategy.calculate_sl_tp(entry_price, df)

        # Sizing con CAP de presupuesto asignado por posición (capital_per_trade)
        qty = self.risk.position_size(
            self.capital_per_trade, entry_price, sl, RIESGO_POR_TRADE
        )
        qty = min(qty, self.capital_per_trade / entry_price)
        qty_rounded = self.round_qty(symbol, qty)

        # Ajuste automático: si el notional es menor al mínimo, subir qty
        notional = qty_rounded * entry_price
        if 0 < notional < MIN_ORDER_NOTIONAL:
            min_qty = MIN_ORDER_NOTIONAL / entry_price * 1.05  # +5% margen
            min_qty = min(min_qty, self.capital_per_trade / entry_price)
            qty_rounded = self.round_qty(symbol, min_qty)
            logger.info(f"{symbol} | Qty ajustado al mínimo: {qty_rounded} (notional ${qty_rounded * entry_price:.2f})")

        # Validación: notional mínimo y balance
        if self.paper_trading:
            real_balance = CAPITAL_TOTAL_USDT
        else:
            real_balance = self.api.get_usdt_balance()
        ok, msg = self.risk.validate_trade(qty_rounded, entry_price, real_balance, MIN_ORDER_NOTIONAL)
        if not ok:
            logger.warning(f"Trade rechazado ({symbol}): {msg}")
            return

        # ── Validación de Order Book ─────────────────────────────────
        logger.info(f"{symbol} | Validando microestructura (Order Book)...")
        ob_proceed, ob_details = self.ob.pre_order_check(
            symbol=symbol,
            entry_price=entry_price,
            quantity=qty_rounded,
            side="BUY",
            sell_wall_threshold="MEDIUM"  # Rechaza muros MEDIUM y HIGH
        )

        if not ob_proceed:
            wall_detail = ob_details.get("sell_wall", {})
            if wall_detail.get("has_wall"):
                logger.warning(
                    f"⚠️  {symbol}: Muro de venta {wall_detail.get('severity')} "
                    f"a ${wall_detail.get('wall_price'):.4f} "
                    f"({wall_detail.get('distance_pct'):.2f}% arriba) — Trade RECHAZADO"
                )
            else:
                logger.warning(f"❌  {symbol} rechazado por liquidez: {ob_details}")
            return

        logger.info(f"✅  Order Book OK para {symbol} | Imbalance: {ob_details.get('imbalance', {}).get('sentiment')}")

        logger.info(f"\n{'=' * 60}")
        logger.info(f"🟢  SEÑAL DE COMPRA: {symbol}")
        logger.info(f"    Score       : {conds.get('score', 0)}/{self.strategy.MIN_BUY_SCORE}")
        logger.info(f"    Precio Est. : ${entry_price:.4f}")
        logger.info(f"    Stop Loss   : ${sl:.4f}  ({(sl/entry_price - 1)*100:.2f}%)")
        logger.info(f"    Take Profit : ${tp:.4f}  (DESACTIVADO - Trailing Stop)")
        logger.info(f"    Cantidad    : {qty_rounded:.6f}  (notional est. ${qty_rounded*entry_price:.2f})")
        logger.info(f"    ATR         : ${atr:.4f}")
        logger.info(f"{'=' * 60}\n")

        if self.paper_trading:
            # PAPER TRADING: simular orden sin ejecutar
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
                # Recalcular SL y TP con el precio real
                sl, tp, atr = self.strategy.calculate_sl_tp(entry_price, df)
                if not self.paper_trading:
                    logger.info(f"✨ Precio real de entrada (fills): ${entry_price:.4f}. SL y TP recalculados.")

        # Asegurar redondeo correcto de precios según reglas del símbolo
        sl = self.round_price(symbol, sl)
        tp = self.round_price(symbol, tp)

        mode_tag = "[PAPER] " if self.paper_trading else ""
        trade_id = self.db.log_entry(
            symbol=symbol, entry_price=entry_price, quantity=qty_rounded,
            stop_loss=sl, take_profit=tp,
            reason=f"{mode_tag}MTF Score {conds.get('combined_score', conds.get('score'))}/{conds.get('min_score', 7)} | "
                   f"Macro: {conds.get('macro_info', {})} | OB: OK",
        )

        self.open_trades[symbol] = {
            "trade_id":    trade_id,
            "entry_price": entry_price,
            "quantity":    qty_rounded,
            "stop_loss":   sl,
            "take_profit": tp,
            "max_price":   entry_price,
            "opened_at":   datetime.now(),
            "trailing_sl": sl,
        }
        self.last_buy_time[symbol] = time.time()
        logger.info(f"✅  {mode_tag}Compra ejecutada: {symbol} #{trade_id} a ${entry_price:.4f}")

    # ─────────────────────────────────────────────────────────────────────────
    # Verificar salida (ahora con Trailing Stop dinámico)
    # ─────────────────────────────────────────────────────────────────────────
    def _check_exit(self, symbol: str, price: float, df):
        trade = self.open_trades[symbol]
        entry    = trade["entry_price"]
        initial_sl = trade["stop_loss"]
        trade_id = trade["trade_id"]
        last     = df.iloc[-1]

        # Actualiza máximo histórico de la posición
        if price > trade["max_price"]:
            trade["max_price"] = price

        # ── NUEVO: Trailing Stop dinámico ──────────────────────────────────────
        trailing_result = self.trailing.update_trailing_stop(
            entry_price=entry,
            current_price=price,
            current_atr=last["atr"],
            max_price=trade["max_price"],
            initial_sl=initial_sl,
            trailing_atr_mult=3.0,  # Aumentado de 2.5 para máximo respaldo
        )

        current_sl = trailing_result["new_sl"]
        trade["trailing_sl"] = current_sl

        # Muestra movimiento del SL cada 5 ciclos (si se movió)
        if trailing_result["moved_sl"]:
            logger.info(
                f"{symbol} | Trailing SL actualizado: ${initial_sl:.4f} → ${current_sl:.4f} "
                f"(+{trailing_result['sl_movement_pct']:.2f}%)"
            )

        exit_price  = None
        exit_reason = None

        # 1. Trailing Stop Hit
        if price <= current_sl:
            exit_price, exit_reason = price, f"Trailing Stop (SL ${current_sl:.4f})"

        # 2. Señales de salida anticipada (score-based) — SOLO después del período mínimo
        elif (datetime.now() - trade["opened_at"]).total_seconds() >= MIN_HOLD_HOURS * 3600:
            s_score, s_reason = self.strategy.exit_score(df)
            if s_score >= self.strategy.MIN_SELL_SCORE:
                exit_price, exit_reason = price, s_reason

        # 3. RSI extremadamente bajo (crash en curso) — siempre activo
        if exit_price is None and last["rsi"] < 25:
            exit_price, exit_reason = price, "RSI Crash (<25)"

        # 4. Cierre parcial opcional de ganancias
        if exit_price is None:
            partial = self.trailing.calculate_partial_exit(
                entry_price=entry,
                current_price=price,
                total_quantity=trade["quantity"],
                profit_target_pct=2.5,
            )
            # Nota: Por ahora no implementamos cierre parcial (requiere más lógica)
            # if partial["should_exit_partial"]:
            #     logger.info(f"{symbol} | Cierre parcial: {partial['reason']}")

        if exit_price is None:
            return

        self._close_trade(symbol, exit_price, trade_id, exit_reason)

    # ─────────────────────────────────────────────────────────────────────────
    # Cerrar posición
    # ─────────────────────────────────────────────────────────────────────────
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


def main():
    bot = TradingBot()
    bot.run()


if __name__ == "__main__":
    main()
