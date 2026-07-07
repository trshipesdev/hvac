import React, { useEffect, useState } from "react";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader, SeverityPill, Select } from "@/components/Panel";
import { ChevronDown, ChevronUp, RefreshCw, Check, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { fmtDateTime } from "@/lib/time";

const TYPES = [
  { id: "", label: "All types" },
  { id: "extended_runtime", label: "Extended runtime" },
  { id: "overnight_draw", label: "Overnight draw" },
  { id: "efficiency_regression", label: "Efficiency regression" },
  { id: "weather_disproportion", label: "Weather disproportion" },
  { id: "setpoint_gap_widening", label: "Setpoint gap widening" },
  { id: "zone_mode_weather_mismatch", label: "Zone heat/cool vs. monthly weather" },
  { id: "mode_weather_mismatch", label: "Heat/cool ran on wrong kind of day" },
  { id: "bill_rate_spike", label: "Bill: rate spike" },
  { id: "bill_past_due", label: "Bill: past due" },
  { id: "bill_late_fee", label: "Bill: late fee" },
  { id: "bill_usage_spike", label: "Bill: usage spike" },
  { id: "bill_meter_mismatch", label: "Bill: meter mismatch" },
  { id: "bill_period_gap", label: "Bill: period gap" },
];

const SEVERITIES = [
  { id: "", label: "All severities" },
  { id: "critical", label: "Critical" },
  { id: "warning", label: "Warning" },
  { id: "info", label: "Info" },
];

const CATEGORIES = [
  { id: "", label: "All" },
  { id: "hvac", label: "HVAC" },
  { id: "bill", label: "Bill" },
];

export default function Anomalies() {
  const [items, setItems] = useState([]);
  const [units, setUnits] = useState([]);
  const [property, setProperty] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [filters, setFilters] = useState({ type: "", severity: "", unit_id: "", category: "" });
  const [showAcked, setShowAcked] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const params = { ...Object.fromEntries(Object.entries(filters).filter(([_, v]) => v)), include_acknowledged: showAcked };
      const [a, u, p] = await Promise.all([api.listAnomalies(params), api.listUnits(), api.getProperty()]);
      setItems(a.data); setUnits(u.data); setProperty(p.data);
    } catch { toast.error("Load failed"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filters, showAcked]);

  const rerun = async () => {
    toast.info("Running detectors…");
    try { await api.runAnomalies(60); toast.success("Detection complete"); load(); }
    catch { toast.error("Detection failed"); }
  };

  const ack = async (id) => { try { await api.ackAnomaly(id); toast.success("Acknowledged"); load(); } catch { toast.error("Ack failed"); } };
  const unack = async (id) => { try { await api.unackAnomaly(id); load(); } catch { toast.error("Unacknowledge failed"); } };

  return (
    <div className="space-y-8 animate-fade-in" data-testid="anomalies-page">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">anomaly log</div>
          <h1 className="text-4xl font-serif tracking-tight text-forest-900">Anomalies</h1>
          <p className="text-sm text-slate-600 mt-1.5">Five HVAC detectors + four bill detectors continuously monitor your system. Acknowledge a flag to silence future duplicates of the same pattern.</p>
        </div>
        <button onClick={rerun} data-testid="rerun-detectors"
          className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-4 py-2.5 text-sm font-medium flex items-center gap-2 transition-colors">
          <RefreshCw size={14} strokeWidth={1.75} /> Re-run detectors
        </button>
      </div>

      <Panel>
        <div className="p-5 flex flex-wrap gap-4 border-b border-paper-300 items-end">
          <Select label="Category" value={filters.category} onChange={(v) => setFilters({...filters, category: v})} data-testid="filter-category">
            {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </Select>
          <Select label="Type" value={filters.type} onChange={(v) => setFilters({...filters, type: v})} data-testid="filter-type">
            {TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </Select>
          <Select label="Severity" value={filters.severity} onChange={(v) => setFilters({...filters, severity: v})} data-testid="filter-severity">
            {SEVERITIES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </Select>
          <Select label="Unit" value={filters.unit_id} onChange={(v) => setFilters({...filters, unit_id: v})} data-testid="filter-unit">
            <option value="">All units</option>
            {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </Select>
          <label className="flex items-center gap-2 text-sm text-forest-800 cursor-pointer h-9">
            <input type="checkbox" checked={showAcked} onChange={(e) => setShowAcked(e.target.checked)} className="accent-forest-500 w-4 h-4" data-testid="show-acked" />
            Show acknowledged
          </label>
          <div className="ml-auto text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">{items.length} result{items.length !== 1 ? "s" : ""}</div>
        </div>

        <div className="divide-y divide-paper-200">
          {loading && <div className="p-8 text-sm text-slate-500 text-center">Loading…</div>}
          {!loading && items.length === 0 && <div className="p-10 text-center text-sm text-slate-500">No anomalies match the current filters.</div>}
          {items.map((a) => {
            const unit = units.find((u) => u.id === a.unit_id);
            const isOpen = expanded[a.id];
            return (
              <div key={a.id} data-testid={`anomaly-row-${a.id}`} className={a.acknowledged ? "opacity-60" : ""}>
                <div className="px-6 py-4 flex items-start gap-4 hover:bg-paper-50 cursor-pointer transition-colors" onClick={() => setExpanded({...expanded, [a.id]: !isOpen})}>
                  <SeverityPill severity={a.severity} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-forest-800 font-medium flex items-center gap-2">
                      {a.title}
                      {a.acknowledged && <span className="text-[10px] uppercase tracking-widest font-normal text-slate-500">acked</span>}
                    </div>
                    <div className="text-xs text-slate-500 font-mono mt-1">
                      {a.category === "bill" ? "Bill" : (unit?.name || "—")} · {a.type.replace(/_/g, " ")} · {fmtDateTime(a.ts_start, property)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                    {a.acknowledged ? (
                      <button onClick={() => unack(a.id)} title="Un-acknowledge" data-testid={`unack-${a.id}`}
                        className="text-slate-400 hover:text-forest-600 p-1.5 rounded-lg hover:bg-paper-200 transition-colors"><Undo2 size={14} strokeWidth={1.75} /></button>
                    ) : (
                      <button onClick={() => ack(a.id)} title="Acknowledge" data-testid={`ack-${a.id}`}
                        className="text-slate-400 hover:text-energy-600 p-1.5 rounded-lg hover:bg-paper-200 transition-colors"><Check size={14} strokeWidth={1.75} /></button>
                    )}
                    {isOpen ? <ChevronUp size={16} strokeWidth={1.75} className="text-slate-400" /> : <ChevronDown size={16} strokeWidth={1.75} className="text-slate-400" />}
                  </div>
                </div>
                {isOpen && (
                  <div className="px-6 pb-5 pl-24 space-y-3 bg-paper-50 animate-fade-in">
                    <p className="text-sm text-forest-800 leading-relaxed">{a.description}</p>
                    <div className="grid grid-cols-3 gap-3 border border-paper-300 rounded-lg p-3 bg-white">
                      {Object.entries(a.context || {}).filter(([k]) => !["fees", "raw_notes"].includes(k)).map(([k, v]) => (
                        <div key={k}>
                          <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-0.5">{k.replace(/_/g, " ")}</div>
                          <div className="font-mono text-xs text-forest-800">{typeof v === "number" ? v.toString() : String(v).slice(0, 60)}</div>
                        </div>
                      ))}
                      <div>
                        <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-0.5">Start</div>
                        <div className="font-mono text-xs text-forest-800">{fmtDateTime(a.ts_start, property)}</div>
                      </div>
                      <div>
                        <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-0.5">End</div>
                        <div className="font-mono text-xs text-forest-800">{fmtDateTime(a.ts_end, property)}</div>
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
