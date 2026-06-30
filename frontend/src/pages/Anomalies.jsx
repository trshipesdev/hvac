import React, { useEffect, useState } from "react";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader, SeverityPill } from "@/components/Panel";
import { CaretDownIcon, CaretUpIcon } from "@phosphor-icons/react";
import { toast } from "sonner";

const TYPES = [
  { id: "", label: "all" },
  { id: "extended_runtime", label: "extended runtime" },
  { id: "overnight_draw", label: "overnight draw" },
  { id: "efficiency_regression", label: "efficiency regression" },
  { id: "weather_disproportion", label: "weather disproportion" },
  { id: "setpoint_gap_widening", label: "setpoint gap" },
];

const SEVERITIES = ["", "critical", "warning", "info"];

export default function Anomalies() {
  const [items, setItems] = useState([]);
  const [units, setUnits] = useState([]);
  const [expanded, setExpanded] = useState({});
  const [filters, setFilters] = useState({ type: "", severity: "", unit_id: "" });
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [a, u] = await Promise.all([
        api.listAnomalies({ ...Object.fromEntries(Object.entries(filters).filter(([_, v]) => v)) }),
        api.listUnits(),
      ]);
      setItems(a.data);
      setUnits(u.data);
    } catch { toast.error("Load failed"); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filters]);

  const rerun = async () => {
    toast.info("Running detectors…");
    try { await api.runAnomalies(60); toast.success("Detection complete"); load(); }
    catch { toast.error("Detection failed"); }
  };

  return (
    <div className="space-y-6" data-testid="anomalies-page">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-1">&gt; anomaly log</div>
          <h1 className="text-3xl font-semibold tracking-tight">Anomalies</h1>
        </div>
        <button onClick={rerun} data-testid="rerun-detectors"
          className="bg-white text-black hover:bg-zinc-200 rounded-sm px-4 py-2 text-sm font-medium">
          Re-run detectors
        </button>
      </div>

      <Panel>
        <div className="p-4 flex flex-wrap gap-3 border-b border-zinc-800">
          <Select label="type" value={filters.type} onChange={(v) => setFilters({...filters, type: v})} data-testid="filter-type">
            {TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </Select>
          <Select label="severity" value={filters.severity} onChange={(v) => setFilters({...filters, severity: v})} data-testid="filter-severity">
            {SEVERITIES.map((s) => <option key={s} value={s}>{s || "all"}</option>)}
          </Select>
          <Select label="unit" value={filters.unit_id} onChange={(v) => setFilters({...filters, unit_id: v})} data-testid="filter-unit">
            <option value="">all</option>
            {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </Select>
          <div className="ml-auto font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 self-end">
            {items.length} result{items.length !== 1 ? "s" : ""}
          </div>
        </div>

        <div className="divide-y divide-zinc-800/60">
          {loading && <div className="p-6 text-sm text-zinc-500 font-mono">loading…</div>}
          {!loading && items.length === 0 && (
            <div className="p-8 text-center text-sm text-zinc-500 font-mono">
              no anomalies detected in this window
            </div>
          )}
          {items.map((a) => {
            const unit = units.find((u) => u.id === a.unit_id);
            const isOpen = expanded[a.id];
            return (
              <div key={a.id} data-testid={`anomaly-row-${a.id}`}>
                <div
                  className="px-4 py-3 flex items-start gap-3 hover:bg-zinc-900/40 cursor-pointer"
                  onClick={() => setExpanded({...expanded, [a.id]: !isOpen})}
                >
                  <SeverityPill severity={a.severity} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-zinc-100">{a.title}</div>
                    <div className="text-xs text-zinc-500 font-mono mt-0.5">
                      {unit?.name || "—"} · {a.type.replace(/_/g, " ")} · {new Date(a.ts_start).toLocaleString()}
                    </div>
                  </div>
                  {isOpen ? <CaretUpIcon size={16} className="text-zinc-500" /> : <CaretDownIcon size={16} className="text-zinc-500" />}
                </div>
                {isOpen && (
                  <div className="px-4 pb-4 pl-16 space-y-3 bg-zinc-900/20">
                    <p className="text-sm text-zinc-300 leading-relaxed">{a.description}</p>
                    <div className="grid grid-cols-3 gap-3 border border-zinc-800 rounded-sm p-3 font-mono text-xs">
                      {Object.entries(a.context || {}).map(([k, v]) => (
                        <div key={k}>
                          <div className="text-zinc-500 uppercase text-[10px] tracking-widest">{k.replace(/_/g, " ")}</div>
                          <div className="text-zinc-100">{typeof v === "number" ? v.toString() : String(v)}</div>
                        </div>
                      ))}
                      <div>
                        <div className="text-zinc-500 uppercase text-[10px] tracking-widest">start</div>
                        <div className="text-zinc-100">{new Date(a.ts_start).toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="text-zinc-500 uppercase text-[10px] tracking-widest">end</div>
                        <div className="text-zinc-100">{new Date(a.ts_end).toLocaleString()}</div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}

function Select({ label, value, onChange, children, ...props }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-zinc-950 border border-zinc-800 rounded-sm px-3 py-1.5 text-sm text-zinc-100 focus:ring-1 focus:ring-zinc-500 font-mono min-w-[160px]"
        {...props}
      >
        {children}
      </select>
    </label>
  );
}
