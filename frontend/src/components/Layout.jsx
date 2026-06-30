import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import { GaugeIcon, WaveTriangleIcon, WarningOctagonIcon, ReceiptIcon, GearSixIcon, UploadIcon } from "@phosphor-icons/react";

const NAV = [
  { to: "/dashboard", label: "Dashboard", key: "dashboard", Icon: GaugeIcon },
  { to: "/ingest", label: "Ingest", key: "ingest", Icon: UploadIcon },
  { to: "/anomalies", label: "Anomalies", key: "anomalies", Icon: WarningOctagonIcon },
  { to: "/bills", label: "Bills", key: "bills", Icon: ReceiptIcon },
  { to: "/settings", label: "Settings", key: "settings", Icon: GearSixIcon },
];

export default function Layout({ children }) {
  const location = useLocation();

  return (
    <div className="min-h-screen flex bg-zinc-950 text-zinc-100">
      {/* Sidebar */}
      <aside className="w-56 border-r border-zinc-800 bg-zinc-950 flex flex-col" data-testid="sidebar">
        <div className="px-4 py-5 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <WaveTriangleIcon size={20} weight="bold" className="text-blue-400" />
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500">HVAC</div>
              <div className="text-sm font-semibold tracking-tight">Efficiency Analyzer</div>
            </div>
          </div>
        </div>
        <nav className="flex-1 py-3">
          {NAV.map(({ to, label, key, Icon }) => (
            <NavLink
              key={to}
              to={to}
              data-testid={`nav-${key}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2 text-sm border-l-2 transition-colors ${
                  isActive
                    ? "text-white border-blue-500 bg-zinc-900"
                    : "text-zinc-400 border-transparent hover:text-white hover:bg-zinc-900/50"
                }`
              }
            >
              <Icon size={16} weight="regular" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-zinc-800 px-4 py-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-600">
            single-user · local
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-x-hidden" data-testid="main-content">
        <div className="border-b border-zinc-800 px-8 py-3 flex items-center justify-between bg-zinc-950/80 backdrop-blur">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500">
            {location.pathname.replace("/", "").toUpperCase() || "DASHBOARD"}
          </div>
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500">
            <span className="text-emerald-500">●</span> live
          </div>
        </div>
        <div className="p-8">{children}</div>
      </main>
    </div>
  );
}
