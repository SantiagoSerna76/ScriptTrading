import React from "react";
import { TrendingUp, TrendingDown } from "lucide-react";

interface SignalCardProps {
  symbol: string;
  action: "BUY" | "SELL" | "HOLD";
  confidence: number;
  price: number;
  entryZone: [number, number];
  stopLoss: number;
  takeProfit: number;
  reasons: string[];
  winRate: number;
}

export default function SignalCard({
  symbol,
  action,
  confidence,
  price,
  entryZone,
  stopLoss,
  takeProfit,
  reasons,
  winRate,
}: SignalCardProps) {
  const bgColor =
    action === "BUY" ? "bg-green-900/20" : action === "SELL" ? "bg-red-900/20" : "bg-gray-900/20";
  const borderColor =
    action === "BUY" ? "border-green-500" : action === "SELL" ? "border-red-500" : "border-gray-500";
  const textColor =
    action === "BUY" ? "text-green-400" : action === "SELL" ? "text-red-400" : "text-gray-400";
  const Icon = action === "BUY" ? TrendingUp : TrendingDown;

  return (
    <div className={`${bgColor} ${borderColor} border rounded-lg p-4 mb-4`}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-lg font-bold text-white">{symbol}</h3>
          <p className={`text-sm ${textColor} font-semibold`}>{action}</p>
        </div>
        <Icon className={`w-6 h-6 ${textColor}`} />
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3 text-xs text-slate-300">
        <div>
          <p className="text-slate-400">Current Price</p>
          <p className="font-bold text-white">${price.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-slate-400">Confidence</p>
          <p className="font-bold text-white">{(confidence * 100).toFixed(0)}%</p>
        </div>
        <div>
          <p className="text-slate-400">Entry Zone</p>
          <p className="font-bold text-white">${entryZone[0].toFixed(2)} - ${entryZone[1].toFixed(2)}</p>
        </div>
        <div>
          <p className="text-slate-400">Win Rate</p>
          <p className="font-bold text-white">{(winRate * 100).toFixed(0)}%</p>
        </div>
      </div>

      <div className="border-t border-slate-700 pt-3 mb-3">
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div>
            <p className="text-red-400 font-semibold">Stop Loss</p>
            <p className="text-white">${stopLoss.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-green-400 font-semibold">Take Profit</p>
            <p className="text-white">${takeProfit.toFixed(2)}</p>
          </div>
        </div>
      </div>

      <div className="bg-slate-800/50 rounded p-2 text-xs text-slate-300">
        <p className="font-semibold mb-1">Why?</p>
        <ul className="space-y-1">
          {reasons.slice(0, 3).map((reason, i) => (
            <li key={i} className="flex items-start">
              <span className="text-green-400 mr-2">✓</span>
              {reason}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
