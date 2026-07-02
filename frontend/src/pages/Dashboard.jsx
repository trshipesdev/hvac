import React, { useEffect, useState, useMemo } from "react";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader, Metric, SeverityPill } from "@/components/Panel";
import DrilldownModal from "@/components/DrilldownModal";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Line, ComposedChart, Legend } from "recharts";
import { toast } from "sonner";
import { RefreshCw, FileText, FileSpreadsheet, TrendingUp, TrendingDown, Calendar } from "lucide-react";
import { useNavigate } from "react-router-dom";

const RANGES = [
  { label: "24H", days: 1, bucket: "hour" },
  { label: "7D", days: 7, bucket: "hour" },
  { label: "30D", days: 30, bucket: "day" },
  { label: "90D", days: 90, bucket: "day" },
];

export default function Dashboard() {
  const nav = useNavigate();
  const [range, setRange] = useState(RANGES[1]);
  const [billMode, setBillMode] = useState(null); // { id, start, end, label }
  const [bills, setBills] = useState([]);
  const [summary, setSummary] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [dataStatus, setDataStatus] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [yoy, setYoy] = useState(null);
  const [property, setProperty] = useState(null);
  const [units, setUnits] = useState([]);
  const [drillTs, setDrillTs] = useState(null);

  const loadBills = async () => { try { const r = await api.listBills(); setBills(r.data); } catch {} };

  const load = async () => {
    const params = billMode
      ? { start_iso: billMode.start, end_iso: billMode.end }
      : { days: range.days };
    const tlParams = billMode
      ? { start_iso: billMode.start, end_iso: billMode.end, bucket: "day" }
      : { days: range.days, bucket: range.bucket };
    try {
      const [p, u, s, t, ds, a, y] = await Promise.all([
        api.getProperty(), api.listUnits(),
        api.summary(params), api.timeline(tlParams),
        api.dataStatus(), api.listAnomalies({ limit: 5 }), api.yoy(),
      ]);
      setProperty(p.data); setUnits(u.data); setSummary(s.data);
      setTimeline(t.data); setDataStatus(ds.data); setAnomalies(a.data); setYoy(y.data);
      if (u.data.length < 2) nav("/setup");
    } catch { toast.error("Load failed"); }
  };

  useEffect(() => { load(); loadBills(); /* eslint-disable-next-line */ }, [range, billMode]);

  const runPipeline = async () => {
    toast.info("Syncing…");
    try { await api.runPipeline(30); toast.success("Pipeline complete"); load(); }
    catch { toast.error("Pipeline failed"); }
  };

  const downloadFile = async (kind) => {
    const params = billMode ? { start_iso: billMode.start, end_iso: billMode.end } : { days: range.days };
    try {
      const blob = kind === "pdf" ? await api.downloadPdf(params) : await api.downloadCsv(params);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = kind === "pdf" ? "hvac-report.pdf" : "hvac-intervals.csv"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
  };

  const chartData = useMemo(() => timeline?.series?.map((b) => ({ ...b })) || [], [timeline]);
  const bucketKind = billMode ? "day" : range.bucket;

  return (
    <div className="space-y-8 animate-fade-in" data-testid="dashboard">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">
            {property?.name || "property"}{property?.zip_code ? ` · ${property.zip_code}` : ""}
          </div>
          <h1 className="text-4xl font-serif tracking-tight text-forest-900">Control Room</h1>
          <p className="text-sm text-slate-600 mt-1.5 max-w-xl">Real-time visibility into per-unit HVAC efficiency, cost attribution, and anomalies.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex border border-paper-300 rounded-lg bg-white overflow-hidden" data-testid="range-selector">
            {RANGES.map((r) => (
              <button key={r.label} onClick={() => { setBillMode(null); setRange(r); }} data-testid={`range-${r.label}`}
                className={`px-3.5 py-2 text-xs font-medium uppercase tracking-wider transition-colors ${
                  !billMode && range.label === r.label ? "bg-forest-500 text-white" : "text-forest-700 hover:bg-paper-200"
                }`}>{r.label}</button>
            ))}
          </div>
          {bills.length > 0 && (
            <select
              onChange={(e) => {
                if (!e.target.value) { setBillMode(null); return; }
                const b = bills.find((x) => x.id === e.target.value);
                if (b) setBillMode({ id: b.id, start: b.start, end: b.end, label: `${b.start.slice(0, 10)} → ${b.end.slice(0, 10)}` });
              }}
              value={billMode?.id || ""}
              data-testid="bill-period-selector"
              className="border border-paper-300 rounded-lg bg-white text-xs font-medium uppercase tracking-wider text-forest-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-forest-500/30">
              <option value="">Bill period…</option>
              {bills.map((b) => (
                <option key={b.id} value={b.id}>{b.start?.slice(0, 10)} → {b.end?.slice(0, 10)}</option>
              ))}
            </select>
          )}
          <button onClick={runPipeline} data-testid="pipeline-btn"
            className="bg-white border border-paper-300 hover:bg-paper-200 rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 text-forest-700 transition-colors">
            <RefreshCw size={13} strokeWidth={1.75} /> Sync
          </button>
          <button onClick={() => downloadFile("csv")} data-testid="export-csv"
            className="bg-white border border-paper-300 hover:bg-paper-200 rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 text-forest-700 transition-colors">
            <FileSpreadsheet size={13} strokeWidth={1.75} /> CSV
          </button>
          <button onClick={() => downloadFile("pdf")} data-testid="export-pdf"
            className="bg-forest-500 hover:bg-forest-600 rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 text-white transition-colors">
            <FileText size={13} strokeWidth={1.75} /> Report
          </button>
        </div>
      </div>

      {billMode && (
        <div className="border border-forest-300 bg-forest-50 rounded-lg px-4 py-2.5 flex items-center gap-3 text-sm text-forest-800">
          <Calendar size={14} strokeWidth={1.75} />
          <span>Viewing bill period · <span className="font-mono">{billMode.label}</span></span>
          <button onClick={() => setBillMode(null)} className="ml-auto text-xs text-forest-500 hover:text-forest-700 uppercase tracking-widest font-medium">Clear</button>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-5">
        <Panel className="p-6 card-hover"><Metric label="Total kWh" value={summary?.total_kwh?.toFixed(1) ?? "—"} unit="kWh" testid="metric-kwh" sub={billMode ? billMode.label : `${range.days} day window`} tone="energy" /></Panel>
        <Panel className="p-6 card-hover"><Metric label="Est. cost" value={`$${summary?.total_cost?.toFixed(2) ?? "—"}`} testid="metric-cost" sub={`@ $${summary?.rate_usd_per_kwh?.toFixed(4) ?? "—"}/kWh`} /></Panel>
        <Panel className="p-6 card-hover"><Metric label="Anomalies" value={summary?.active_anomalies ?? "—"} unit="flags" testid="metric-anom" sub={`${summary?.critical_anomalies ?? 0} critical`} tone={summary?.critical_anomalies > 0 ? "critical" : "default"} /></Panel>
        <Panel className="p-6 card-hover"><Metric label="Base load" value={summary?.base_load?.kwh?.toFixed(1) ?? "—"} unit="kWh" testid="metric-base" sub={`$${summary?.base_load?.cost?.toFixed(2) ?? "—"} · always-on`} /></Panel>
        <Panel className="p-6 card-hover" data-testid="yoy-card">
          <div className="flex flex-col gap-1.5">
            <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">YoY (30d)</div>
            {(yoy?.prior_year_kwh ?? 0) < 500 ? (
              <>
                <div className="text-4xl font-serif font-light tracking-tight text-slate-400">—</div>
                <div className="text-xs text-slate-500 leading-tight">Not enough prior-year data yet (need &gt;500 kWh in the same 30-day window last year).</div>
              </>
            ) : (
              <>
                <div className="flex items-baseline gap-1.5">
                  <div className={`text-4xl font-serif font-light tracking-tight ${
                    yoy?.pct_change == null ? "text-slate-400" :
                    yoy.pct_change > 0 ? "text-amber-600" : "text-energy-600"
                  }`}>
                    {yoy?.pct_change != null ? `${yoy.pct_change > 0 ? "+" : ""}${yoy.pct_change}` : "—"}
                  </div>
                  <div className="text-xs font-mono text-slate-500">%</div>
                  {yoy?.pct_change != null && (yoy.pct_change > 0 ? <TrendingUp size={14} className="text-amber-600" strokeWidth={1.75} /> : <TrendingDown size={14} className="text-energy-600" strokeWidth={1.75} />)}
                </div>
                <div className="text-xs text-slate-500 font-mono">{yoy?.prior_year_kwh?.toFixed(0) ?? "—"} kWh prior yr</div>
              </>
            )}
          </div>
        </Panel>
      </div>

      <Panel data-testid="timeline-panel">
        <PanelHeader label="Whole-home timeline · per-unit attribution"
          action={<div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500"><TrendingUp size={11} strokeWidth={2} /> click a point to drill down</div>} />
        <div className="p-6" style={{ height: 340 }}>
          {chartData.length === 0 && <div className="h-full flex items-center justify-center text-sm text-slate-500">No data yet — click Sync to seed the pipeline.</div>}
          {chartData.length > 0 && (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
                onClick={(e) => { if (e && e.activeLabel) setDrillTs(e.activeLabel); }}>
                <defs>
                  {(timeline?.units || []).map((u, i) => (
                    <linearGradient key={u.id} id={`grad-${i}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={u.color} stopOpacity={0.55} />
                      <stop offset="100%" stopColor={u.color} stopOpacity={0.15} />
                    </linearGradient>
                  ))}
                  <linearGradient id="grad-base" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#94A3B8" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#94A3B8" stopOpacity={0.1} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#E2E0D8" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="ts" stroke="#94A3B8" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono", fill: "#64748B" }}
                  tickFormatter={(v) => bucketKind === "day" ? v.slice(5) : v.slice(11, 16)} />
                <YAxis stroke="#94A3B8" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono", fill: "#64748B" }} yAxisId="left" />
                <YAxis stroke="#F59E0B" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono", fill: "#B45309" }} yAxisId="right" orientation="right" tickFormatter={(v) => `${v}°`} width={40} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 11, fontFamily: "DM Sans", paddingTop: 8, color: "#5E6C64" }} iconType="circle" />
                <Area yAxisId="left" type="monotone" dataKey="base_load" stackId="1" stroke="#94A3B8" strokeWidth={1} fill="url(#grad-base)" name="Base load" />
                {(timeline?.units || []).map((u, i) => (
                  <Area key={u.id} yAxisId="left" type="monotone" dataKey={u.id} stackId="1" stroke={u.color} strokeWidth={1.5} fill={`url(#grad-${i})`} name={u.name} />
                ))}
                <Line yAxisId="right" type="monotone" dataKey="outdoor_temp_f" stroke="#F59E0B" strokeWidth={1.75} dot={false} name="Outdoor °F" />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </Panel>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {(summary?.units || []).map((u) => (
          <Panel key={u.id} className="card-hover" data-testid={`unit-panel-${u.id}`}>
            <PanelHeader label={<span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full" style={{ background: u.color }} />{u.name}</span>} />
            <div className="p-6 grid grid-cols-2 gap-6">
              <Metric label="kWh" value={u.kwh?.toFixed(1) ?? "0"} unit="kWh" tone="energy" />
              <Metric label="Cost" value={`$${u.cost?.toFixed(2) ?? "0"}`} />
              <Metric label="Runtime" value={u.runtime_hours?.toFixed(1) ?? "0"} unit="hrs" />
              <Metric label="Efficiency" value={u.kwh_per_runtime_hour?.toFixed(2) ?? "0"} unit="kWh/hr" />
            </div>
          </Panel>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <Panel className="md:col-span-2" data-testid="anomalies-panel">
          <PanelHeader label="Recent anomalies" action={<a href="/anomalies" className="text-[10px] font-medium uppercase tracking-[0.15em] text-forest-500 hover:text-forest-700">view all →</a>} />
          <div className="divide-y divide-paper-200">
            {anomalies.length === 0 && <div className="p-8 text-sm text-slate-500 text-center">No anomalies detected in the current window.</div>}
            {anomalies.map((a) => {
              const unit = units.find((u) => u.id === a.unit_id);
              return (
                <div key={a.id} className="px-6 py-3.5 flex items-start gap-3 hover:bg-paper-50 transition-colors" data-testid={`anomaly-${a.id}`}>
                  <SeverityPill severity={a.severity} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-forest-800">{a.title}</div>
                    <div className="text-xs text-slate-500 font-mono mt-0.5">
                      {a.category === "bill" ? "Bill" : (unit?.name || "—")} · {new Date(a.ts_start).toLocaleString()}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel data-testid="status-panel">
          <PanelHeader label="Data status" />
          <div className="p-6 space-y-4">
            <StatusRow label="Energy intervals" value={dataStatus?.energy_intervals ?? 0} />
            <StatusRow label="Thermostat rows" value={dataStatus?.thermostat_readings ?? 0} />
            <StatusRow label="Weather rows" value={dataStatus?.weather_readings ?? 0} />
            <div className="border-t border-paper-300 pt-4">
              <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-1.5">Resideo</div>
              <div className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-widest border ${
                dataStatus?.resideo?.mock_mode ? "bg-amber-50 text-amber-800 border-amber-300" : "bg-energy-50 text-energy-700 border-energy-500/40"
              }`}><span className="w-1 h-1 rounded-full bg-current" />{dataStatus?.resideo?.mock_mode ? "Mock mode" : "Live"}</div>
              <div className="text-xs text-slate-500 mt-2 leading-relaxed">{dataStatus?.resideo?.message}</div>
            </div>
          </div>
        </Panel>
      </div>

      {drillTs && <DrilldownModal ts={drillTs} bucket={bucketKind} onClose={() => setDrillTs(null)} />}
    </div>
  );
}

function StatusRow({ label, value }) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">{label}</span>
      <span className="font-mono text-sm text-forest-800">{value.toLocaleString()}</span>
    </div>
  );
}
