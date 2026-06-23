import React from "react";
import Head from "next/head";
import Header from "@/components/Header";
import Sidebar from "@/components/Sidebar";
import TradingChart from "@/components/TradingChart";
import SignalCard from "@/components/SignalCard";
import OrderBook from "@/components/OrderBook";
import WatchlistManager from "@/components/WatchlistManager";
import AlertPanel from "@/components/AlertPanel";

export default function Dashboard() {
  const mockSignals = [
    {
      symbol: "BTCUSDT",
      action: "BUY" as const,
      confidence: 0.85,
      price: 45234.5,
      entryZone: [45200, 45300] as [number, number],
      stopLoss: 44500,
      takeProfit: 47000,
      reasons: ["EMA bullish", "ADX > 30 (strong trend)", "RSI neutral", "Order book bullish"],
      winRate: 0.62,
    },
    {
      symbol: "ETHUSDT",
      action: "HOLD" as const,
      confidence: 0.5,
      price: 2534.5,
      entryZone: [2500, 2550] as [number, number],
      stopLoss: 2450,
      takeProfit: 2650,
      reasons: ["No clear signal", "Waiting for confirmation"],
      winRate: 0.5,
    },
  ];

  return (
    <>
      <Head>
        <title>TradeInsight - Professional Trading Analysis</title>
        <meta name="description" content="Real-time trading signals and analysis" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <div className="flex h-screen bg-slate-950">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <Header />
          <div className="max-w-7xl mx-auto p-6 space-y-6">
            {/* Charts and Signals */}
            <div className="grid grid-cols-3 gap-6">
              {/* Chart */}
              <div className="col-span-2">
                <h2 className="text-xl font-bold text-white mb-4">📈 BTCUSDT 1H</h2>
                <TradingChart symbol="BTCUSDT" />
              </div>

              {/* Alerts */}
              <div>
                <AlertPanel />
              </div>
            </div>

            {/* Signals and OrderBook */}
            <div className="grid grid-cols-3 gap-6">
              {/* Signals */}
              <div className="col-span-1">
                <h2 className="text-xl font-bold text-white mb-4">🟢 Active Signals</h2>
                <div className="space-y-4">
                  {mockSignals.map((signal) => (
                    <SignalCard key={signal.symbol} {...signal} />
                  ))}
                </div>
              </div>

              {/* OrderBook */}
              <div className="col-span-2">
                <h2 className="text-xl font-bold text-white mb-4">📊 Market Depth</h2>
                <div className="grid grid-cols-2 gap-6">
                  <OrderBook symbol="BTCUSDT" sentiment="BULLISH" spread={0.10} />
                  <WatchlistManager />
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </>
  );
}
