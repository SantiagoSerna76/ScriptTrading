#!/usr/bin/env python3
"""
Backtesting mejorado — usa la misma estrategia del bot en vivo.
Incluye: Trailing Stop dinámico, Multi-Timeframe, gestión de riesgo,
         simulación de comisiones y período mínimo de retención.
"""

import logging
import pandas as pd
from binance_api import BinanceAPI, parse_klines_to_dataframe
from strategy import StrategySignals, RiskManager, TrailingStopManager
from mtf_analyzer import MultiTimeframeAnalyzer
from data_validator import DataValidator, BacktestValidator
from config import (
    CAPITAL_TOTAL_USDT, RIESGO_POR_TRADE, TIMEFRAME,
    SL_ATR_MULT, TP_ATR_MULT, SYMBOLS, MAX_OPEN_POSITIONS,
    TRADING_FEE_RATE, MIN_HOLD_HOURS, PARTIAL_TP_PCT,
    RELAXED_MACRO_SYMBOLS, PROXY_URL,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Período mínimo de retención en velas (1 vela = 15 min en timeframe 15m)
# MIN_HOLD_HOURS=0.25 → 0.25h / 0.25h = 1 vela mínimo
MIN_HOLD_CANDLES = max(1, int(MIN_HOLD_HOURS / 0.25))


class Backtest:

    def __init__(self, symbol: str, initial_capital: float = 1000.0):
        self.symbol   = symbol
        self.capital0 = initial_capital
        self.capital  = initial_capital
        self.strategy = StrategySignals()
        self.risk     = RiskManager()
        self.mtf      = MultiTimeframeAnalyzer()
        self.trailing = TrailingStopManager()
        self.api      = BinanceAPI("", "", use_testnet=False, proxy_url=PROXY_URL)
        self.trades   = []
        self.total_fees = 0.0

    def run(self, days: int = 60, print_results: bool = True):
        # Para 1H, el límite de Binance es 1000 (aprox 41 días). 
        # Para backtest más largo, se necesitaría paginar, pero usamos 1000.
        limit_1h = 1000
        klines_1h = self.api.get_klines(self.symbol, TIMEFRAME, limit=limit_1h)
        if not klines_1h:
            logger.error(f"Sin datos 1H para {self.symbol}")
            return

        # Para 4H, necesitamos al menos 210 velas para la EMA200
        klines_4h = self.api.get_klines(self.symbol, "4h", limit=1000)
        if not klines_4h:
            logger.error(f"Sin datos 4H para {self.symbol}")
            return

        df = parse_klines_to_dataframe(klines_1h)

        # V4: Validar datos antes del backtest
        is_valid, issues = DataValidator.validate(df, self.symbol)
        if not is_valid:
            logger.error(f"⚠️ Backtest abortado para {self.symbol} debido a datos corruptos.")
            return

        df = self.strategy.calculate_indicators(df)
        
        df_4h_full = parse_klines_to_dataframe(klines_4h)

        # Para 15min, necesitamos al menos 210 velas de warmup para EMA200
        start = 210
        if print_results:
            logger.info(f"Backtesting {self.symbol} | {len(df) - start} velas útiles | "
                        f"Capital: ${self.capital0:.2f} | Fee: {TRADING_FEE_RATE*100:.2f}%")

        position = None

        for idx in range(start, len(df)):
            window  = df.iloc[:idx + 1]
            current = df.iloc[idx]
            price   = current["close"]

            # Sin posición: busca entrada
            if position is None:
                signal_1h, conds_1h = self.strategy.check_buy_signal(window)
                
                # Validar con MTF
                if signal_1h or conds_1h.get('score', 0) >= 6:
                    # Encontrar los datos de 4H disponibles hasta este momento de forma optimizada
                    current_ts = current["timestamp"]
                    idx_4h = df_4h_full["timestamp"].searchsorted(current_ts, side="right")
                    df_4h_window = df_4h_full.iloc[:idx_4h]
                    
                    macro_conds = self.mtf.analyze_macro_trend(df_4h_window)
                    
                    relaxed = self.symbol in RELAXED_MACRO_SYMBOLS
                    signal, conds = self.mtf.validate_entry_with_macro(
                        window, macro_conds, signal_1h, conds_1h,
                        relaxed=relaxed
                    )
                else:
                    signal, conds = False, conds_1h

                if signal:
                    sl, tp, atr = self.strategy.calculate_sl_tp(price, window)
                    
                    # Rechazo por volatilidad excesiva (ATR > 4% del entry)
                    if sl is None:
                        continue
                        
                    capital_per_trade = self.capital / MAX_OPEN_POSITIONS
                    
                    # Criterio de Kelly dinámico en backtesting
                    stats = self._get_simulated_stats()
                    risk_pct = self.risk.calculate_kelly_risk(stats, RIESGO_POR_TRADE)
                    
                    # NUEVO: Sizing sobre capital total dinámico, TRENDING usa 100% del slot
                    qty_risk = self.risk.position_size(self.capital, price, sl, risk_pct)
                    
                    regime = conds.get("regime", "NORMAL")
                    size_multiplier = self.strategy.get_position_size_multiplier(regime)
                    
                    max_qty_by_cap = (capital_per_trade * size_multiplier) / price
                    
                    if size_multiplier < 1.0:
                        qty = min(qty_risk, max_qty_by_cap)
                    else:
                        qty = max_qty_by_cap  # TRENDING usa el 100%
                        
                    notional = qty * price
                    if qty > 0 and notional >= 5:
                        # Descontar comisión de compra
                        buy_fee = notional * TRADING_FEE_RATE
                        self.total_fees += buy_fee
                        self.capital -= buy_fee

                        # Resolve score: MTF combined_score > 1H score > 0 (never None)
                        entry_score = (
                            conds.get("combined_score")
                            or conds.get("score")
                            or conds_1h.get("score")
                            or 0
                        )
                        entry_regime = conds.get("regime") or conds_1h.get("regime") or "NORMAL"
                        position = {
                            "entry_idx": idx, "entry": price,
                            "qty": qty, "sl": sl, "tp": tp,
                            "max": price, "score": entry_score,
                            "macro": conds.get("macro_bullish", conds_1h.get("macro_bullish")),
                            "trailing_sl": sl,
                            "regime": entry_regime,
                            "risk_pct": risk_pct,
                        }

            # Con posición: verifica salida
            else:
                if price > position["max"]:
                    position["max"] = price

                # Trailing Stop dinámico — misma lógica que el bot en vivo
                regime_info = self.strategy.detect_market_regime(window)
                regime = regime_info["regime"]
                if regime in ["TREND_STRONG_BULL", "TREND_BULL"]:
                    trailing_mult = 3.0   # Más espacio en tendencias (ATR pequeño en 15min)
                    breakeven_pct  = 1.0  # Breakeven rápido para proteger capital
                elif regime in ["RANGE_VOLATILE", "CHOPPY"]:
                    trailing_mult = 2.0   # Más holgura contra ruido de 15min
                    breakeven_pct  = 0.5  # Protección inmediata
                else:
                    trailing_mult = 2.5
                    breakeven_pct  = 0.8

                trailing_result = self.trailing.update_trailing_stop(
                    entry_price=position["entry"],
                    current_price=price,
                    current_atr=current["atr"],
                    max_price=position["max"],
                    initial_sl=position["sl"],
                    trailing_atr_mult=trailing_mult,
                    breakeven_pct=breakeven_pct,
                )
                position["trailing_sl"] = trailing_result["new_sl"]

                exit_p, exit_r = None, None
                hold_time = idx - position["entry_idx"]

                # 1. Trailing Stop Hit — siempre activo
                if price <= position["trailing_sl"]:
                    exit_p, exit_r = price, "Trailing Stop"

                # 2. Señales de salida anticipada — SOLO después del período mínimo
                elif hold_time >= MIN_HOLD_CANDLES:
                    s_score, s_reason = self.strategy.exit_score(window)
                    if s_score >= self.strategy.MIN_SELL_SCORE:
                        exit_p, exit_r = price, s_reason or "Signal Exit"

                # 3. RSI Crash — siempre activo, pero requiere caída
                if exit_p is None and current["rsi"] < 25 and price < position["entry"] * 0.97:
                    exit_p, exit_r = price, "RSI Crash + Drop >3%"

                # 4. Cierre Parcial Seguro
                if exit_p is None and not position.get("partial_exit_done"):
                    gain_pct = (price / position["entry"] - 1) * 100
                    if gain_pct >= PARTIAL_TP_PCT:
                        exit_qty = position["qty"] * 0.5
                        sell_fee = (price * exit_qty) * TRADING_FEE_RATE
                        self.total_fees += sell_fee
                        
                        pnl = (price - position["entry"]) * exit_qty - sell_fee - (position["entry"] * exit_qty * TRADING_FEE_RATE)
                        pct = gain_pct
                        
                        self.capital += (price - position["entry"]) * exit_qty - sell_fee
                        self.trades.append({
                            "entry": position["entry"], "exit": price,
                            "qty": exit_qty, "pnl": pnl, "pct": pct,
                            "reason": "Cierre Parcial (50%)", "dur": hold_time,
                            "score": position["score"], "macro": position["macro"],
                            "max_sl": position["max"],
                            "regime": position["regime"],
                        })
                        
                        position["partial_exit_done"] = True
                        position["qty"] -= exit_qty
                        position["trailing_sl"] = position["entry"]

                if exit_p:
                    # Descontar comisión de venta
                    sell_notional = exit_p * position["qty"]
                    sell_fee = sell_notional * TRADING_FEE_RATE
                    self.total_fees += sell_fee

                    pnl = (exit_p - position["entry"]) * position["qty"] - sell_fee - (position["entry"] * position["qty"] * TRADING_FEE_RATE)
                    pct = (exit_p / position["entry"] - 1) * 100
                    self.capital += (exit_p - position["entry"]) * position["qty"] - sell_fee
                    self.trades.append({
                        "entry": position["entry"], "exit": exit_p,
                        "qty": position["qty"], "pnl": pnl, "pct": pct,
                        "reason": exit_r, "dur": hold_time,
                        "score": position["score"], "macro": position["macro"],
                        "max_sl": position["max"],
                        "breakeven": trailing_result.get("breakeven_active", False),
                        "regime": position.get("regime", "NORMAL"),
                        "risk_pct": position.get("risk_pct", 0.02),
                    })
                    position = None

        if print_results:
            self._print_results()

    def summary(self) -> dict:
        """Devuelve métricas compactas para scanners y auditorías."""
        if not self.trades:
            return {
                "symbol": self.symbol,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "pnl": 0.0,
                "roi": 0.0,
                "pf": 0.0,
                "wr": 0.0,
                "avg_dur": 0.0,
                "fees": round(self.total_fees, 2),
            }

        wins = [t for t in self.trades if t["pnl"] > 0]
        losses = [t for t in self.trades if t["pnl"] <= 0]
        total_pnl = sum(t["pnl"] for t in self.trades)
        gross_win = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        pf = gross_win / gross_loss if gross_loss > 0 else 999.0
        roi = (self.capital - self.capital0) / self.capital0 * 100
        avg_dur = sum(t["dur"] for t in self.trades) / len(self.trades)

        return {
            "symbol": self.symbol,
            "trades": len(self.trades),
            "wins": len(wins),
            "losses": len(losses),
            "pnl": round(total_pnl, 2),
            "roi": round(roi, 2),
            "pf": round(pf, 2),
            "wr": round(len(wins) / len(self.trades) * 100, 1),
            "avg_dur": round(avg_dur, 1),
            "fees": round(self.total_fees, 2),
        }

    def _print_results(self):
        sep = "=" * 65
        logger.info(f"\n{sep}")
        logger.info(f"  BACKTEST: {self.symbol} (Con Fees + Break-Even + Hold Mínimo)")
        logger.info(sep)

        if not self.trades:
            logger.info("  Sin trades ejecutados.")
            logger.info(f"  → Posible causa: mercado sin tendencia alcista (EMA200)\n{sep}\n")
            return

        wins   = [t for t in self.trades if t["pnl"] > 0]
        losses = [t for t in self.trades if t["pnl"] <= 0]
        total_pnl = sum(t["pnl"] for t in self.trades)
        win_rate  = len(wins) / len(self.trades) * 100
        avg_win   = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss  = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
        gross_win = sum(t["pnl"] for t in wins)
        gross_los = abs(sum(t["pnl"] for t in losses))
        pf        = gross_win / gross_los if gross_los > 0 else 999
        avg_dur   = sum(t["dur"] for t in self.trades) / len(self.trades)

        roi = (self.capital - self.capital0) / self.capital0 * 100

        logger.info(f"  Capital inicial : ${self.capital0:.2f}")
        logger.info(f"  Capital final   : ${self.capital:.2f}  (ROI {roi:+.2f}%)")
        logger.info(f"  P&L neto (fees) : ${total_pnl:+.2f}")
        logger.info(f"  Fees pagados    : ${self.total_fees:.2f}")
        logger.info(f"  Trades          : {len(self.trades)}  "
                    f"(✅ {len(wins)} ganadores  ❌ {len(losses)} perdedores)")
        logger.info(f"  Win Rate        : {win_rate:.1f}%")
        logger.info(f"  Promedio win    : ${avg_win:+.2f}  |  Promedio loss: ${avg_loss:+.2f}")
        logger.info(f"  Profit Factor   : {pf:.2f}   (>1.5 = bueno, >2.0 = excelente)")
        
        # Sharpe Ratio
        returns = [t["pct"] for t in self.trades]
        if len(returns) > 1:
            mean_ret = sum(returns) / len(returns)
            std_ret = (sum((r - mean_ret)**2 for r in returns) / (len(returns)-1))**0.5
            sharpe = mean_ret / std_ret if std_ret > 0 else 0
            logger.info(f"  Sharpe Ratio    : {sharpe:.2f}")

        logger.info(f"  Duración media  : {avg_dur:.1f}h")

        # Máximo drawdown
        equity = self.capital0
        peak   = equity
        max_dd = 0.0
        for t in self.trades:
            equity += t["pnl"]
            peak    = max(peak, equity)
            max_dd  = max(max_dd, (peak - equity) / peak * 100)
        logger.info(f"  Max Drawdown    : -{max_dd:.2f}%")

        # Conteo de break-evens
        be_count = sum(1 for t in self.trades if t.get("breakeven"))
        logger.info(f"  Break-evens     : {be_count} trades protegidos")
        
        # Validación de overfitting V4
        is_valid_bt, bt_warnings = BacktestValidator.validate_backtest_results({
            "profit_factor": pf,
            "win_rate": win_rate,
            "total_trades": len(self.trades)
        })
        if not is_valid_bt:
            logger.warning(f"  ⚠️ ADVERTENCIAS DE OVERFITTING:")
            for w in bt_warnings:
                logger.warning(f"     {w}")

        logger.info(f"\n  Últimos 5 trades:")
        for t in self.trades[-5:]:
            e = "✅" if t["pnl"] > 0 else "❌"
            be = " [BE]" if t.get("breakeven") else ""
            reg = f" | reg={t.get('regime', 'N/A')}" if t.get("regime") else ""
            risk = f" | risk={t.get('risk_pct', 0.0)*100:.1f}%" if t.get("risk_pct") else ""
            logger.info(f"  {e} entrada ${t['entry']:.2f} → ${t['exit']:.2f} | "
                        f"P&L ${t['pnl']:+.2f} ({t['pct']:+.2f}%) | "
                        f"{t['reason']} | {t['dur']}h | score={t['score']}{be}{reg}{risk}")
        logger.info(f"{sep}\n")

    def _get_simulated_stats(self) -> dict:
        closed_trades = self.trades
        total = len(closed_trades)
        if total == 0:
            return {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "win_loss_ratio": 0.0}
            
        wins_list = [t["pnl"] for t in closed_trades if t["pnl"] > 0]
        losses_list = [abs(t["pnl"]) for t in closed_trades if t["pnl"] < 0]
        
        wins = len(wins_list)
        losses = len(losses_list)
        avg_win = sum(wins_list) / wins if wins > 0 else 0.0
        avg_loss = sum(losses_list) / losses if losses > 0 else 0.0
        
        win_rate = wins / total
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


def main():
    days = 60   # 2 meses de datos

    for sym in SYMBOLS:
        bt = Backtest(sym, CAPITAL_TOTAL_USDT)
        bt.run(days=days)

        import time; time.sleep(1)

if __name__ == "__main__":
    main()
