import React, { useState, useEffect } from "react";
import { Bell, Settings } from "lucide-react";

interface Alert {
  id: string;
  symbol: string;
  type: "SIGNAL" | "PRICE" | "NEWS";
  severity: "INFO" | "WARNING" | "CRITICAL";
  message: string;
  timestamp: Date;
  read: boolean;
}

export default function AlertPanel() {
  const [alerts, setAlerts] = useState<Alert[]>([
    {
      id: "1",
      symbol: "BTCUSDT",
      type: "SIGNAL",
      severity: "CRITICAL",
      message: "🟢 BUY Signal: BTCUSDT (85% confidence)",
      timestamp: new Date(),
      read: false,
    },
    {
      id: "2",
      symbol: "ETHUSDT",
      type: "PRICE",
      severity: "WARNING",
      message: "⚠️ Price Alert: ETHUSDT crossed $2500",
      timestamp: new Date(Date.now() - 300000),
      read: false,
    },
  ]);

  const unreadCount = alerts.filter((a) => !a.read).length;

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "CRITICAL":
        return "bg-red-900/20 border-red-500";
      case "WARNING":
        return "bg-yellow-900/20 border-yellow-500";
      default:
        return "bg-blue-900/20 border-blue-500";
    }
  };

  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white flex items-center gap-2">
          <Bell size={20} />
          Alerts ({unreadCount})
        </h3>
        <button className="text-slate-400 hover:text-white transition">
          <Settings size={18} />
        </button>
      </div>

      <div className="space-y-2 max-h-96 overflow-y-auto scrollbar-hide">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={`${getSeverityColor(alert.severity)} border rounded-lg p-3 cursor-pointer hover:opacity-80 transition`}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <p className="font-semibold text-white text-sm">{alert.message}</p>
                <p className="text-xs text-slate-400 mt-1">
                  {alert.timestamp.toLocaleTimeString()}
                </p>
              </div>
              {!alert.read && (
                <div className="w-2 h-2 bg-red-500 rounded-full ml-2 mt-1" />
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
