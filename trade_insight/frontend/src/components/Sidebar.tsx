import React from "react";
import { BarChart3, Settings, LogOut, Home } from "lucide-react";

export default function Sidebar() {
  return (
    <aside className="w-64 bg-slate-900 border-r border-slate-800 min-h-screen">
      <nav className="p-4 space-y-2">
        <NavItem icon={<Home size={20} />} label="Dashboard" active />
        <NavItem icon={<BarChart3 size={20} />} label="Signals" />
        <NavItem icon={<Settings size={20} />} label="Settings" />
      </nav>

      <div className="absolute bottom-4 left-4 right-4">
        <button className="w-full flex items-center gap-2 text-red-400 hover:text-red-300 font-semibold py-2 px-3 rounded hover:bg-red-900/20 transition">
          <LogOut size={18} /> Logout
        </button>
      </div>
    </aside>
  );
}

function NavItem({
  icon,
  label,
  active = false,
}: {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
}) {
  return (
    <button
      className={`w-full flex items-center gap-3 px-4 py-3 rounded transition ${
        active
          ? "bg-blue-600/20 text-blue-400 border border-blue-500/50"
          : "text-slate-300 hover:bg-slate-800/50"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
