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
    PAPER_TRADING, USE_TESTNET, TRADING_FEE_RATE, PARTIAL_TP_PCT, ADX_MIN,
    RELAXED_MACRO_SYMBOLS, ENTRY_SYMBOLS, PROXY_URL
)
from binance_api import BinanceAPI, parse_klines_to_dataframe
from strategy import StrategySignals, RiskManager, TrailingStopManager
from mtf_analyzer import MultiTimeframeAnalyzer
from microstructure import OrderBookAnalyzer
from database import TradeDatabase
from notifier import TelegramNotifier
from ml_signal import MLSignalFilter

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
PAUSE_SIGNAL_FILE = ".bot_pause_signal"

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
        self.risk     = RiskManager()
        self.db       = TradeDatabase()
        self.mtf      = MultiTimeframeAnalyzer()
        self.ob       = OrderBookAnalyzer(API_KEY, SECRET_KEY, proxy_url=PROXY_URL)
        self.trailing = TrailingStopManager()
        self.notifier = TelegramNotifier()
        self.ml_filter = MLSignalFilter()

        # Símbolos Activos y Hot-Swap
        self.symbols = SYMBOLS.copy()
        self.entry_symbols = ENTRY_SYMBOLS.copy()
        
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

            # Convertir entry_time string a datetime
            opened_at = datetime.now()
            if t.get("entry_time"):
                try:
                    opened_at = datetime.fromisoformat(t["entry_time"])
                except Exception:
                    pass

            self.open_trades[symbol] = {
                "trade_id":        t["id"],
                "entry_price":     t["entry_price"],
                "quantity":        t["entry_quantity"],
                "stop_loss":       t["stop_loss"],
                "take_profit":     t["take_profit"],
                "tp_target":       t.get("take_profit", t["stop_loss"]),
                "risk_per_unit":   abs(t["entry_price"] - t["stop_loss"]),
                "max_price":       t.get("max_price", t["entry_price"]),
                "opened_at":       opened_at,
                "trailing_sl":     t.get("trailing_sl", t["stop_loss"]),
                "partial_exit_done": t.get("partial_exit_done", False),
            }
            logger.info(
                f"📈  Recuperado trade abierto #{t['id']} para {symbol}: "
                f"Entrada=${t['entry_price']:.4f}, Qty={t['entry_quantity']:.6f}, "
                f"Trailing SL=${self.open_trades[symbol]['trailing_sl']:.4f}"
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
            if dynamic_entry_raw:
                dynamic_entry = json.loads(dynamic_entry_raw)
                if isinstance(dynamic_entry, list) and len(dynamic_entry) > 0:
                    self.entry_symbols = dynamic_entry
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

        # ── Si Circuit Breaker está activo, no evaluar nuevas entradas ───────
        if not can_open_new:
            return

        # Gestiona todos los símbolos, pero solo abre nuevas entradas en lista blanca.
        if symbol not in self.entry_symbols:
            # logger.info(f"{symbol} | Nuevas entradas deshabilitadas (self.entry_symbols). Solo monitoreo.")
            return

        # ── Sin posición → verificar entrada ────────────────────────────────
        try:
            buy_signal_1h, conds_1h = self.strategy.check_buy_signal(df_1h)
        except Exception as e:
            logger.error(f"{symbol} | Error en check_buy_signal: {e}", exc_info=True)
            return

        # ── Análisis de Sentimiento (Funding Rate) ─────────────────────────
        try:
            funding_rate = self.api.get_funding_rate(symbol)
        except Exception as e:
            logger.warning(f"{symbol} | Error obteniendo funding rate: {e}")
            funding_rate = None

        # Agrega detalles a conds_1h
        conds_1h["close_price"] = last_1h["close"]
        if funding_rate is not None:
            conds_1h["funding_rate"] = funding_rate
            conds_1h["funding_rate_pct"] = funding_rate * 100
            
            # Ajuste de score por Sentimiento / Short Squeeze
            # Binance devuelve decimales (ej. 0.01% = 0.0001)
            if funding_rate < -0.00005:  # -0.005% Muy negativo, shorts atrapados
                conds_1h["score"] += 1
                conds_1h["min_score"] -= 1 # Facilita la entrada
                logger.info(f"🔥 SHORT SQUEEZE DETECTADO en {symbol} (Funding: {funding_rate*100:.4f}%). Entradas facilitadas.")
            elif funding_rate > 0.00015: # +0.015% Muy positivo, longs sobre-apalancados (riesgo de dump)
                conds_1h["score"] -= 1
                logger.warning(f"⚠️  Exceso de Longs en {symbol} (Funding: {funding_rate*100:.4f}%). Penalizando score (-1).")
            
            # Reevaluar señal 1H tras el ajuste de score
            buy_signal_1h = conds_1h["score"] >= conds_1h["min_score"]

        funding_str = f"| Funding: {funding_rate*100:.4f}% " if funding_rate is not None else ""
        logger.info(
            f"{symbol} | precio=${last_1h['close']:.4f} {funding_str}| "
            f"RSI={conds_1h.get('rsi', 0):.1f} | "
            f"ADX={conds_1h.get('adx', 0):.1f} | "
            f"score={conds_1h.get('score', 0)}/{conds_1h.get('min_score', 7)} | "
            f"Régimen: {conds_1h.get('regime', 'NORMAL')}"
        )

        # ── Combina señal 1H + validación macro 4H ────────────────────────────
        if buy_signal_1h or conds_1h.get('score', 0) >= 6:
            if "No hay suficientes datos 4H" not in macro_conds.get('reason', ''):
                # Validación MTF completa con datos de 4H
                relaxed = symbol in RELAXED_MACRO_SYMBOLS
                buy_signal_mtf, mtf_details = self.mtf.validate_entry_with_macro(
                    df_1h, macro_conds, buy_signal_1h, conds_1h,
                    relaxed=relaxed
                )
            else:
                # Sin datos 4H suficientes → rechazar entrada por seguridad
                buy_signal_mtf = False
                mtf_details = {'reason': 'Datos 4H insuficientes para validación macro'}
                logger.warning(f"{symbol} | ⚠️  Sin datos 4H suficientes. Entrada rechazada.")

            if buy_signal_mtf:
                # ML filter: predict probability of winning trade
                # Prepare features for ML model
                order_book_dict = None
                mtf_dict = mtf_details  # reuse what we already have
                regime_info = self.strategy.detect_market_regime(df_1h)
                
                # Get order book data (we'll fetch it fresh for features)
                try:
                    ob_data = self.ob.get_order_book(symbol, limit=20)
                    if ob_data:
                        liquidity_ok, liquidity_detail = self.ob.validate_order_liquidity(
                            symbol, 0.001, side="BUY", ob=ob_data  # dummy quantity just for liquidity check
                        )
                        wall_detail = self.ob.detect_sell_wall(symbol, last_1h["close"], levels_to_check=10, ob=ob_data)
                        imbalance = self.ob.calculate_imbalance(symbol, levels=10, ob=ob_data)
                        order_book_dict = {
                            "liquidity": liquidity_detail,
                            "sell_wall": wall_detail,
                            "imbalance": imbalance
                        }
                except Exception as e:
                    logger.debug(f"Could not get order book for ML features: {e}")
                    order_book_dict = {}
                
                features = self.ml_filter.extract_features(
                    df=df_1h,
                    symbol=symbol,
                    order_book_dict=order_book_dict,
                    mtf_dict=mtf_dict,
                    regime_info=regime_info
                )
                
                win_prob = self.ml_filter.predict_proba(features)
                ml_threshold = 0.6  # Only take trades with >=60% predicted win probability
                
                logger.info(
                    f"{symbol} | ML Signal Filter: "
                    f"Win Prob={win_prob:.2f} "
                    f"(Threshold={ml_threshold}) "
                    f"{'✅ PASS' if win_prob >= ml_threshold else '❌ FAIL'}"
                )
                
                if win_prob >= ml_threshold:
                    self._open_trade(symbol, df_1h, mtf_details)
                else:
                    logger.info(f"{symbol} | Trade rejected by ML filter (low win probability)")
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
        from config import SL_COOLDOWN_S, CONSECUTIVE_LOSS_MAX
        
        last_exit = self.db.get_last_exit_time(symbol)
        elapsed_since_exit = time.time() - last_exit
        
        # Evaluar pérdidas consecutivas
        consec_losses = self.db.get_consecutive_losses(symbol)
        
        cooldown_needed = MIN_BUY_COOLDOWN_S
        if consec_losses >= CONSECUTIVE_LOSS_MAX:
            cooldown_needed = max(cooldown_needed, 12 * 3600)  # 12 horas pausa
            logger.info(f"⚠️ {symbol} tiene {consec_losses} pérdidas seguidas. Cooldown extendido (12h).")
        elif consec_losses > 0:
            cooldown_needed = max(cooldown_needed, SL_COOLDOWN_S)  # 8 horas pausa
            
        elapsed_since_buy = time.time() - self.last_buy_time[symbol]
        
        if elapsed_since_buy < cooldown_needed or elapsed_since_exit < cooldown_needed:
            remaining = max(cooldown_needed - elapsed_since_buy, cooldown_needed - elapsed_since_exit) / 3600
            logger.info(f"Cooldown activo para {symbol}: {remaining:.1f}h restantes.")
            return

        entry_price = df.iloc[-1]["close"]
        sl, tp, atr = self.strategy.calculate_sl_tp(entry_price, df)

        # Rechazo por alta volatilidad: calculate_sl_tp retorna None si ATR > 3%
        if sl is None:
            logger.info(f"{symbol} | Trade RECHAZADO: volatilidad excesiva (SL > 3% del entry). Protegiendo R:R.")
            return

        # ── Objetivo de Take Profit estático ──────────────────────────────────
        # TP objetivo = entry + (TP_ATR_MULT × ATR). Sirve como objetivo de
        # venta parcial: al alcanzarlo se vende el 50% y el SL se sube a breakeven.
        # El resto de la posición continúa con trailing SL.
        risk_per_unit = abs(entry_price - sl)  # riesgo $ por unidad

        # 1. Cálculo de tamaño (Sizing) basado en riesgo (Kelly)
        stats = self.db.get_symbol_trades_stats(symbol)
        risk_pct = self.risk.calculate_kelly_risk(stats, RIESGO_POR_TRADE)

        # Calcular cantidad ideal basado en el riesgo por unidad y el capital asignado
        qty_risk_based = self.risk.position_size(
            self.capital_per_trade, entry_price, sl, risk_pct
        )
        
        # 2. Aplicación de multiplicador de régimen (Ajuste estratégico)
        regime = conds.get('regime', 'NORMAL')
        size_multiplier = self.strategy.get_position_size_multiplier(regime)
        qty_adjusted = qty_risk_based * size_multiplier
        
        # 3. Limitar por capital total disponible (Safety Cap)
        max_qty_by_cap = self.capital_per_trade / entry_price
        qty = min(qty_adjusted, max_qty_by_cap)
        
        # 4. Redondeo y redondeo final de la cantidad
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

        imbalance_sentiment = ob_details.get("imbalance", {}).get("sentiment", "NEUTRAL")
        if imbalance_sentiment == "BEARISH":
            logger.warning(f"⚠️  {symbol}: Imbalance BEARISH en el Order Book. Rechazando trade por fuerte presión vendedora.")
            return

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
        logger.info(f"    Régimen     : {conds.get('regime', 'NORMAL')} ({conds.get('regime_desc', 'N/A')})")
        logger.info(f"    Riesgo Kelly: {risk_pct*100:.2f}% (Historial: {stats.get('total_trades', 0)} trades)")
        logger.info(f"    Score       : {conds.get('score', 0)}/{conds.get('min_score', 7)}")
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
                sl_new, tp_new, atr = self.strategy.calculate_sl_tp(entry_price, df)
                # Solo actualizar si no es rechazado por volatilidad (caso raro post-fill)
                if sl_new is not None:
                    sl, tp = sl_new, tp_new
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
            "trade_id":        trade_id,
            "entry_price":     entry_price,
            "quantity":        qty_rounded,
            "stop_loss":       sl,
            "take_profit":     tp,
            "tp_target":       tp,
            "risk_per_unit":   risk_per_unit,
            "max_price":       entry_price,
            "opened_at":       datetime.now(),
            "trailing_sl":     sl,
            "partial_exit_done": False,
        }
        self.last_buy_time[symbol] = time.time()
        logger.info(f"✅  {mode_tag}Compra ejecutada: {symbol} #{trade_id} a ${entry_price:.4f}")
        self.notifier.send_message(
            f"🟢 *COMPRA: {symbol}*\n"
            f"Precio: `${entry_price:.4f}`\n"
            f"Score: `{conds.get('score', 0)}`\n"
            f"Modo: {mode_tag.strip() or 'REAL'}"
        )

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
        max_updated = False
        if price > trade["max_price"]:
            trade["max_price"] = price
            max_updated = True

        # ── NUEVO: Trailing Stop dinámico 
        # Inteligencia Dinámica: El trailing stop se ajusta al régimen ACTUAL del mercado
        regime_info = self.strategy.detect_market_regime(df)
        regime = regime_info["regime"]
        adx_val = regime_info.get("adx", 0.0)
        
        if regime in ["TREND_STRONG_BULL", "TREND_BULL"]:
            trailing_mult = 2.0  # Da más respiro en tendencias fuertes
            breakeven_pct = 2.0  # Espera más para activar breakeven
        elif regime in ["RANGE_VOLATILE", "CHOPPY"]:
            trailing_mult = 1.0  # Stop súper ajustado en ruido
            breakeven_pct = 1.0  # Protege capital rápidamente
        else:
            trailing_mult = 1.5
            breakeven_pct = 1.5

        # --- Actualizar Trailing Stop ---
        trailing_result = self.trailing.update_trailing_stop(
            entry_price=trade["entry_price"],
            current_price=price,
            current_atr=last["atr"],
            max_price=trade["max_price"],
            initial_sl=trade["stop_loss"],
            trailing_atr_mult=trailing_mult,
            breakeven_pct=breakeven_pct
        )

        current_sl = trailing_result["new_sl"]
        sl_moved = current_sl != trade["trailing_sl"]
        trade["trailing_sl"] = current_sl

        # Guardar en base de datos si hubo cambios en max_price o en trailing_sl
        if max_updated or sl_moved:
            self.db.update_trailing_sl(trade_id, current_sl, trade["max_price"])

        # Muestra movimiento del SL si se movió con respecto al inicial
        if trailing_result["moved_sl"]:
            logger.info(
                f"{symbol} | Trailing SL actualizado: ${initial_sl:.4f} → ${current_sl:.4f} "
                f"(+{trailing_result['sl_movement_pct']:.2f}%)"
            )

        exit_price  = None
        exit_reason = None

        # ── TP Objetivo alcanzado → Venta Parcial + SL a breakeven ──────────────
        # Si el precio llega al objetivo de TP se vende el 50% de la posición
        # y el SL se mueve al precio de entrada (sin pérdidas).
        # El resto de la posición continúa con trailing SL.
        tp_target = trade.get("tp_target", 0.0)
        if (
            tp_target > 0
            and not trade.get("partial_exit_done", False)
            and price >= tp_target
            and (datetime.now() - trade["opened_at"]).total_seconds() >= MIN_HOLD_HOURS * 3600
        ):
            self._close_partial_trade(
                symbol, price, trade_id,
                reason=f"TP Objetivo alcanzado (${tp_target:.4f})",
                exit_quantity=trade["quantity"] * 0.5,
            )
            trade["partial_exit_done"] = True
            self.open_trades[symbol]["partial_exit_done"] = True
            # Mover SL a breakeven sobre el resto de la posición
            trade["trailing_sl"] = trade["entry_price"]
            self.db.update_trailing_sl(trade_id, trade["entry_price"], trade["max_price"])
            logger.info(f"{symbol} | 🛡️  SL movido a Break-Even (${trade['entry_price']:.4f}) después de venta parcial en TP")

        # 1. Trailing Stop Hit
        if price <= current_sl:
            exit_price, exit_reason = price, f"Trailing Stop (SL ${current_sl:.4f})"

        # 2. Señales de salida anticipada (score-based) — SOLO después del período mínimo
        elif (datetime.now() - trade["opened_at"]).total_seconds() >= MIN_HOLD_HOURS * 3600:
            s_score, s_reason = self.strategy.exit_score(df)
            if s_score >= self.strategy.MIN_SELL_SCORE:
                exit_price, exit_reason = price, s_reason

        # 3. RSI extremadamente bajo (crash en curso)
        # Ajuste: No requiere ADX alto, pero sí confirmación de caída severa de precio y RSI
        if exit_price is None and last["rsi"] < 25:
            # Solo salir si el precio cayó significativamente desde la entrada (ej. > 3%)
            # para evitar cerrar en un pullback normal
            if price < entry * 0.97:
                exit_price, exit_reason = price, "RSI Crash (<25) + Drop >3%"

        # 4. Cierre parcial opcional de ganancias
        if exit_price is None and not trade.get("partial_exit_done"):
            partial = self.trailing.calculate_partial_exit(
                entry_price=entry,
                current_price=price,
                total_quantity=trade["quantity"],
                profit_target_pct=PARTIAL_TP_PCT,
            )
            if partial.get("should_exit_partial"):
                logger.info(f"{symbol} | 💰 Cierre parcial activado: {partial['reason']}")
                self._close_partial_trade(symbol, price, trade_id, partial["reason"], exit_quantity=partial["exit_quantity"])
                trade["partial_exit_done"] = True
                
                # Forzar el trailing stop al break-even (precio de entrada)
                trade["trailing_sl"] = entry
                self.db.update_trailing_sl(trade_id, entry, trade["max_price"])
                logger.info(f"{symbol} | 🛡️ Trailing Stop movido a Break-Even (${entry:.4f})")

        if exit_price is None:
            return

        self._close_trade(symbol, exit_price, trade_id, exit_reason)

    # ─────────────────────────────────────────────────────────────────────────
    # Cerrar posición (Parcial y Total)
    # ─────────────────────────────────────────────────────────────────────────
    def _close_partial_trade(self, symbol: str, exit_price: float,
                             trade_id: int, reason: str, exit_quantity: float):
        trade = self.open_trades[symbol]
        entry = trade["entry_price"]
        
        exit_quantity_rounded = self.round_qty(symbol, exit_quantity)
        if exit_quantity_rounded <= 0:
            return
            
        pnl = (exit_price - entry) * exit_quantity_rounded

        if self.paper_trading:
            # PAPER TRADING: simular venta parcial
            fee = exit_price * exit_quantity_rounded * TRADING_FEE_RATE
            self.paper_fees += fee
            pnl_net = pnl - fee - (entry * exit_quantity_rounded * TRADING_FEE_RATE)
            self.paper_pnl += pnl_net
            logger.info(f"📝  [PAPER] Venta PARCIAL simulada: {exit_quantity_rounded} {symbol} @ ${exit_price:.4f} (fee ${fee:.4f})")
        else:
            order = self.api.place_order(
                symbol=symbol, side="SELL", type_="MARKET", quantity=exit_quantity_rounded
            )
            if not order:
                logger.error(f"❌  Orden de venta PARCIAL FALLIDA para {symbol}.")
                return
                
            fills = order.get("fills", [])
            if fills:
                total_qty = sum(float(f["qty"]) for f in fills)
                if total_qty > 0:
                    exit_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / total_qty
                    pnl = (exit_price - entry) * exit_quantity_rounded

        exit_price = self.round_price(symbol, exit_price)

        self.db.log_partial_exit(trade_id, exit_price, exit_quantity_rounded, reason)
        
        # Actualizar cantidad en memoria
        trade["quantity"] -= exit_quantity_rounded
        
        mode_tag = "[PAPER] " if self.paper_trading else ""
        logger.info(f"\n{'=' * 60}")
        logger.info(f"✨  {mode_tag}VENTA PARCIAL (50%): {symbol} — {reason}")
        logger.info(f"    Entrada: ${entry:.4f} → Salida: ${exit_price:.4f}")
        logger.info(f"    P&L Asegurado: ${pnl:.2f}")
        self.notifier.send_message(
            f"💰 *PARCIAL (50%): {symbol}*\n"
            f"P&L Asegurado: `${pnl:.2f}`\n"
            f"Modo: {mode_tag.strip() or 'REAL'}"
        )
        logger.info(f"{'=' * 60}\n")

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
