import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import { LayoutDashboard, Upload, AlertTriangle, Receipt, Settings2, Leaf, Thermometer } from "lucide-react";

const NAV = [
  { to: "/dashboard", label: "Dashboard", key: "dashboard", Icon: LayoutDashboard },
  { to: "/ingest", label: "Ingest", key: "ingest", Icon: Upload },
  { to: "/anomalies", label: "Anomalies", key: "anomalies", Icon: AlertTriangle },
  { to: "/bills", label: "Bills", key: "bills", Icon: Receipt },
  { to: "/honeywell", label: "Zone Reports", key: "honeywell", Icon: Thermometer },
  { to: "/settings", label: "Settings", key: "settings", Icon: Settings2 },
];

export default function Layout({ children }) {
  const location = useLocation();
  const active = location.pathname.replace("/", "") || "dashboard";

  return (
    <div className="min-h-screen flex bg-paper-100">
      <aside className="w-64 border-r border-paper-300 bg-paper-50 flex flex-col shrink-0" data-testid="sidebar">
        <div className="px-6 py-6 border-b border-paper-300">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-forest-500 flex items-center justify-center">
              <Leaf className="text-white" size={18} strokeWidth={1.75} />
            </div>
            <div>
              <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-forest-500">Analyzer</div>
              <div className="text-base font-serif text-forest-900 leading-tight">Watt · Home</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 py-4 px-3 space-y-0.5">
          {NAV.map(({ to, label, key, Icon }) => (
            <NavLink
              key={to}
              to={to}
              data-testid={`nav-${key}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? "bg-forest-500 text-white"
                    : "text-forest-700 hover:bg-paper-200"
                }`
              }
            >
              <Icon size={17} strokeWidth={1.75} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-paper-300 px-6 py-4">
          <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">
            single-user · local
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-x-hidden" data-testid="main-content">
        <div className="border-b border-paper-300 px-8 py-3.5 flex items-center justify-between bg-paper-100/80 backdrop-blur sticky top-0 z-10">
          <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">
            {active}
          </div>
          <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">
            <span className="w-1.5 h-1.5 rounded-full bg-energy-500 animate-pulse" /> live
          </div>
        </div>
        <div className="p-8 max-w-[1600px] mx-auto">{children}</div>
      </main>
    </div>
  );
}
