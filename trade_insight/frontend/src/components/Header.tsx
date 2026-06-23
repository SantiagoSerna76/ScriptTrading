import React from "react";
import { Activity } from "lucide-react";

export default function Header() {
  return (
    <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-8 h-8 text-blue-400" />
          <h1 className="text-2xl font-bold text-white">TradeInsight</h1>
          <span className="text-xs bg-blue-600/20 text-blue-400 px-2 py-1 rounded border border-blue-500/50">
            BETA
          </span>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-sm text-slate-400">Status</p>
            <p className="text-xs font-semibold text-green-400">● Connected</p>
          </div>
        </div>
      </div>
    </header>
  );
}
