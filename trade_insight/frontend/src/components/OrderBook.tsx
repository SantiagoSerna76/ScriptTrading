import React, { useState } from "react";
import { ChevronDown, Plus, X } from "lucide-react";

interface OrderBookProps {
  symbol: string;
  bids: Array<{ price: number; quantity: number }>;
  asks: Array<{ price: number; quantity: number }>;
  spread: number;
  sentiment: "BULLISH" | "NEUTRAL" | "BEARISH";
}

export default function OrderBook({
  symbol,
  bids = [],
  asks = [],
  spread,
  sentiment,
}: OrderBookProps) {
  const sentimentColor =
    sentiment === "BULLISH" ? "text-green-400" : sentiment === "BEARISH" ? "text-red-400" : "text-yellow-400";

  // Mock data
  const mockBids = bids.length
    ? bids
    : [
        { price: 45234.50, quantity: 1.5 },
        { price: 45230.00, quantity: 2.3 },
        { price: 45225.00, quantity: 1.8 },
      ];

  const mockAsks = asks.length
    ? asks
    : [
        { price: 45240.00, quantity: 1.2 },
        { price: 45245.00, quantity: 2.1 },
        { price: 45250.00, quantity: 1.9 },
      ];

  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">Order Book - {symbol}</h3>
        <div className="flex items-center gap-2">
          <span className={`text-sm font-semibold ${sentimentColor}`}>
            {sentiment}
          </span>
          <span className="text-xs text-slate-400">Spread: ${spread.toFixed(2)}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Sell Side (Red) */}
        <div>
          <h4 className="text-xs font-bold text-red-400 mb-2 uppercase">Ask Orders</h4>
          <div className="space-y-1">
            {mockAsks.map((ask, i) => (
              <div key={i} className="flex justify-between text-xs text-slate-300">
                <span className="text-red-400 font-semibold">${ask.price.toFixed(2)}</span>
                <span>{ask.quantity.toFixed(4)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Buy Side (Green) */}
        <div>
          <h4 className="text-xs font-bold text-green-400 mb-2 uppercase">Bid Orders</h4>
          <div className="space-y-1">
            {mockBids.map((bid, i) => (
              <div key={i} className="flex justify-between text-xs text-slate-300">
                <span className="text-green-400 font-semibold">${bid.price.toFixed(2)}</span>
                <span>{bid.quantity.toFixed(4)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
