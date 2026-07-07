import React from "react";
import { cn } from "@/lib/utils";

export function Panel({ className, children, ...props }) {
  return (
    <div
      className={cn(
        "bg-white border border-paper-300 rounded-xl overflow-hidden",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function PanelHeader({ label, action, className }) {
  return (
    <div className={cn("px-6 py-4 border-b border-paper-300 flex items-center justify-between gap-3", className)}>
      <div className="text-xs font-medium uppercase tracking-[0.15em] text-forest-500">{label}</div>
      {action}
    </div>
  );
}

export function Metric({ label, value, unit, sub, className, testid, tone = "default" }) {
  const toneCls = {
    default: "text-forest-800",
    energy: "text-energy-600",
    warning: "text-amber-600",
    critical: "text-red-600",
  }[tone];
  return (
    <div className={cn("flex flex-col gap-1.5", className)} data-testid={testid}>
      <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">{label}</div>
      <div className="flex items-baseline gap-1.5">
        <div className={cn("text-4xl font-serif font-light tracking-tight", toneCls)}>{value}</div>
        {unit && <div className="text-xs font-mono text-slate-500">{unit}</div>}
      </div>
      {sub && <div className="text-xs text-slate-500 font-mono">{sub}</div>}
    </div>
  );
}

export function SeverityPill({ severity, className }) {
  const map = {
    critical: "text-red-700 bg-red-50 border-red-300",
    warning: "text-amber-800 bg-amber-50 border-amber-300",
    info: "text-sky-700 bg-sky-50 border-sky-300",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full border font-medium text-[10px] uppercase tracking-widest whitespace-nowrap",
        map[severity] || map.info,
        className
      )}
    >
      <span className="w-1 h-1 rounded-full bg-current opacity-70" />
      {severity}
    </span>
  );
}

export function Select({ label, value, onChange, children, ...props }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="bg-white border border-paper-300 rounded-lg px-3 py-2 text-sm text-forest-800 focus:outline-none focus:ring-2 focus:ring-forest-500/30 focus:border-forest-500 min-w-[170px] transition-all"
        {...props}>{children}</select>
    </label>
  );
}

export function Kv({ label, value, highlight, className, mono = true }) {
  return (
    <div className={cn("flex flex-col gap-0.5", className)}>
      <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">{label}</div>
      <div className={cn(mono ? "font-mono text-xs" : "text-sm", highlight ? "text-forest-600 font-medium" : "text-forest-800")}>
        {value != null && value !== "" ? String(value) : <span className="text-slate-400">—</span>}
      </div>
    </div>
  );
}
