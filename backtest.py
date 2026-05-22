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
from config import (
    CAPITAL_TOTAL_USDT, RIESGO_POR_TRADE, TIMEFRAME,
    SL_ATR_MULT, TP_ATR_MULT, SYMBOLS, MAX_OPEN_POSITIONS,
    TRADING_FEE_RATE, MIN_HOLD_HOURS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Período mínimo de retención en velas (1 vela = 1 hora en timeframe 1H)
MIN_HOLD_CANDLES = MIN_HOLD_HOURS


class Backtest:

    def __init__(self, symbol: str, initial_capital: float = 1000.0):
        self.symbol   = symbol
        self.capital0 = initial_capital
        self.capital  = initial_capital
        self.strategy = StrategySignals()
        self.risk     = RiskManager()
        self.mtf      = MultiTimeframeAnalyzer()
        self.trailing = TrailingStopManager()
        self.api      = BinanceAPI("", "", use_testnet=False)
        self.trades   = []
        self.total_fees = 0.0

    def run(self, days: int = 60):
        limit = min(days * 24 + 250, 1000)   # +250 para que EMA200 tenga datos
        klines = self.api.get_klines(self.symbol, TIMEFRAME, limit=limit)
        if not klines:
            logger.error(f"Sin datos para {self.symbol}")
            return

        df = parse_klines_to_dataframe(klines)
        df = self.strategy.calculate_indicators(df)

        # Necesitamos al menos 210 velas antes de empezar (EMA200 + margen)
        start = 210
        logger.info(f"Backtesting {self.symbol} | {len(df) - start} velas útiles | "
                    f"Capital: ${self.capital0:.2f} | Fee: {TRADING_FEE_RATE*100:.2f}%")

        position = None

        for idx in range(start, len(df)):
            window  = df.iloc[:idx + 1]
            current = df.iloc[idx]
            price   = current["close"]

            # Sin posición: busca entrada
            if position is None:
                signal, conds = self.strategy.check_buy_signal(window)
                if signal:
                    sl, tp, atr = self.strategy.calculate_sl_tp(price, window)
                    capital_per_trade = self.capital / MAX_OPEN_POSITIONS
                    qty = self.risk.position_size(capital_per_trade, price, sl, RIESGO_POR_TRADE)
                    qty = min(qty, capital_per_trade / price)
                    notional = qty * price
                    if qty > 0 and notional >= 5:
                        # Descontar comisión de compra
                        buy_fee = notional * TRADING_FEE_RATE
                        self.total_fees += buy_fee
                        self.capital -= buy_fee

                        position = {
                            "entry_idx": idx, "entry": price,
                            "qty": qty, "sl": sl, "tp": tp,
                            "max": price, "score": conds.get("score"),
                            "macro": conds.get("macro_bullish"),
                            "trailing_sl": sl,
                        }

            # Con posición: verifica salida
            else:
                if price > position["max"]:
                    position["max"] = price

                # Actualiza Trailing Stop dinámico (con break-even)
                trailing_result = self.trailing.update_trailing_stop(
                    entry_price=position["entry"],
                    current_price=price,
                    current_atr=current["atr"],
                    max_price=position["max"],
                    initial_sl=position["sl"],
                    trailing_atr_mult=3.0,
                    breakeven_pct=1.0,
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

                # 3. RSI Crash — siempre activo
                if exit_p is None and current["rsi"] < 25:
                    exit_p, exit_r = price, "RSI Crash"

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
                    })
                    position = None

        self._print_results()

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

        logger.info(f"\n  Últimos 5 trades:")
        for t in self.trades[-5:]:
            e = "✅" if t["pnl"] > 0 else "❌"
            be = " [BE]" if t.get("breakeven") else ""
            logger.info(f"  {e} entrada ${t['entry']:.2f} → ${t['exit']:.2f} | "
                        f"P&L ${t['pnl']:+.2f} ({t['pct']:+.2f}%) | "
                        f"{t['reason']} | {t['dur']}h | score={t['score']}{be}")
        logger.info(f"{sep}\n")


def main():
    days = 60   # 2 meses de datos

    for sym in SYMBOLS:
        bt = Backtest(sym, CAPITAL_TOTAL_USDT)
        bt.run(days=days)

        import time; time.sleep(1)

if __name__ == "__main__":
    main()
