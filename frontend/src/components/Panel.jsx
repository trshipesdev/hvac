import React from "react";
import { cn } from "@/lib/utils";

export function Panel({ className, children, ...props }) {
  return (
    <div
      className={cn(
        "bg-zinc-900/40 border border-zinc-800 rounded-sm backdrop-blur-sm",
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
    <div className={cn("px-4 py-3 border-b border-zinc-800 flex items-center justify-between", className)}>
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500">{label}</div>
      {action}
    </div>
  );
}

export function Metric({ label, value, unit, sub, className, testid }) {
  return (
    <div className={cn("flex flex-col gap-1", className)} data-testid={testid}>
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500">{label}</div>
      <div className="flex items-baseline gap-1">
        <div className="text-3xl font-mono tracking-tight text-white">{value}</div>
        {unit && <div className="text-xs font-mono text-zinc-500">{unit}</div>}
      </div>
      {sub && <div className="text-xs text-zinc-500">{sub}</div>}
    </div>
  );
}

export function SeverityPill({ severity }) {
  const map = {
    critical: "text-red-500 bg-red-500/10 border-red-500/20",
    warning: "text-amber-500 bg-amber-500/10 border-amber-500/20",
    info: "text-blue-400 bg-blue-500/10 border-blue-500/20",
  };
  return (
    <span
      className={cn(
        "inline-block px-2 py-0.5 rounded-sm border font-mono text-[10px] uppercase tracking-widest",
        map[severity] || map.info
      )}
    >
      {severity}
    </span>
  );
}
