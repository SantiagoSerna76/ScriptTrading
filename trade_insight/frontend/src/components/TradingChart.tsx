import React, { useEffect, useState } from "react";
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";

interface TradingChartProps {
  symbol: string;
  data?: Array<{
    timestamp: string;
    close: number;
    ema_short: number;
    ema_long: number;
    volume: number;
  }>;
}

export default function TradingChart({ symbol, data }: TradingChartProps) {
  const [chartData, setChartData] = useState(data || []);

  useEffect(() => {
    // Mock data for demonstration
    const mockData = Array.from({ length: 24 }, (_, i) => ({
      timestamp: `${i}:00`,
      close: 45000 + Math.random() * 1000,
      ema_short: 44900 + Math.random() * 500,
      ema_long: 44800 + Math.random() * 500,
      volume: Math.random() * 1000,
    }));
    setChartData(mockData);
  }, [symbol]);

  return (
    <div className="w-full h-96 bg-slate-900 rounded-lg p-4 border border-slate-800">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="colorClose" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#475569" />
          <XAxis dataKey="timestamp" stroke="#94a3b8" />
          <YAxis stroke="#94a3b8" />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1e293b",
              border: "1px solid #475569",
              borderRadius: "8px",
            }}
          />
          <Legend />
          <Area
            type="monotone"
            dataKey="close"
            stroke="#3b82f6"
            fill="url(#colorClose)"
            name="Price"
          />
          <Line
            type="monotone"
            dataKey="ema_short"
            stroke="#f59e0b"
            dot={false}
            name="EMA 20"
          />
          <Line
            type="monotone"
            dataKey="ema_long"
            stroke="#8b5cf6"
            dot={false}
            name="EMA 50"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
