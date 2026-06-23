import React, { useState } from "react";
import { Heart, Trash2, Plus } from "lucide-react";

interface WatchlistItem {
  symbol: string;
  price: number;
  change: number;
}

export default function WatchlistManager() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([
    { symbol: "BTCUSDT", price: 45234.50, change: 0.52 },
    { symbol: "ETHUSDT", price: 2534.50, change: -1.23 },
    { symbol: "BNBUSDT", price: 612.30, change: 2.15 },
  ]);

  const [newSymbol, setNewSymbol] = useState("");

  const addToWatchlist = () => {
    if (newSymbol.trim()) {
      setWatchlist([
        ...watchlist,
        { symbol: newSymbol.toUpperCase(), price: 0, change: 0 },
      ]);
      setNewSymbol("");
    }
  };

  const removeFromWatchlist = (symbol: string) => {
    setWatchlist(watchlist.filter((item) => item.symbol !== symbol));
  };

  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 p-4">
      <h3 className="text-lg font-bold text-white mb-4">📊 Watchlist</h3>

      {/* Add new */}
      <div className="flex gap-2 mb-4">
        <input
          type="text"
          placeholder="Add symbol (BTCUSDT)..."
          value={newSymbol}
          onChange={(e) => setNewSymbol(e.target.value)}
          onKeyPress={(e) => e.key === "Enter" && addToWatchlist()}
          className="flex-1 bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-white placeholder-slate-500"
        />
        <button
          onClick={addToWatchlist}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm font-semibold flex items-center gap-2"
        >
          <Plus size={16} /> Add
        </button>
      </div>

      {/* List */}
      <div className="space-y-2">
        {watchlist.map((item) => (
          <div
            key={item.symbol}
            className="flex items-center justify-between bg-slate-800/50 p-3 rounded border border-slate-700 hover:border-slate-600 transition"
          >
            <div className="flex-1">
              <p className="font-semibold text-white">{item.symbol}</p>
              <p className="text-xs text-slate-400">${item.price.toFixed(2)}</p>
            </div>
            <div className="text-right mr-3">
              <p
                className={`font-semibold text-sm ${
                  item.change >= 0 ? "text-green-400" : "text-red-400"
                }`}
              >
                {item.change >= 0 ? "+" : ""}{item.change.toFixed(2)}%
              </p>
            </div>
            <button
              onClick={() => removeFromWatchlist(item.symbol)}
              className="text-slate-400 hover:text-red-400 transition"
            >
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
