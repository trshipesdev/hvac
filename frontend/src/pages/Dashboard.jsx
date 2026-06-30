import React, { useEffect, useState, useMemo } from "react";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader, Metric, SeverityPill } from "@/components/Panel";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Line, ComposedChart, Legend } from "recharts";
import { toast } from "sonner";
import { ArrowClockwiseIcon, FileArrowDownIcon, FilePdfIcon } from "@phosphor-icons/react";
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
  const [summary, setSummary] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [dataStatus, setDataStatus] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [property, setProperty] = useState(null);
  const [units, setUnits] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [p, u, s, t, ds, a] = await Promise.all([
        api.getProperty(),
        api.listUnits(),
        api.summary(range.days),
        api.timeline(range.days, range.bucket),
        api.dataStatus(),
        api.listAnomalies({ limit: 6 }),
      ]);
      setProperty(p.data);
      setUnits(u.data);
      setSummary(s.data);
      setTimeline(t.data);
      setDataStatus(ds.data);
      setAnomalies(a.data);
      if (u.data.length < 2) {
        nav("/setup");
      }
    } catch (e) {
      toast.error("Load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [range]);

  const runPipeline = async () => {
    toast.info("Running pipeline…");
    try {
      await api.runPipeline(30);
      toast.success("Pipeline complete");
      load();
    } catch { toast.error("Pipeline failed"); }
  };

  const downloadFile = async (kind) => {
    try {
      const blob = kind === "pdf" ? await api.downloadPdf(range.days) : await api.downloadCsv(range.days);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = kind === "pdf" ? "hvac-report.pdf" : "hvac-intervals.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
  };

  const chartData = useMemo(() => {
    if (!timeline?.series) return [];
    return timeline.series.map((b) => ({ ...b }));
  }, [timeline]);

  return (
    <div className="space-y-6" data-testid="dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-1">
            {property?.name || "property"} · {property?.zip_code || "—"}
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">Control Room</h1>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex border border-zinc-800 rounded-sm" data-testid="range-selector">
            {RANGES.map((r) => (
              <button
                key={r.label}
                onClick={() => setRange(r)}
                data-testid={`range-${r.label}`}
                className={`px-3 py-1.5 text-xs font-mono uppercase tracking-widest transition-colors ${
                  range.label === r.label ? "bg-white text-black" : "text-zinc-400 hover:text-white hover:bg-zinc-900"
                }`}
              >{r.label}</button>
            ))}
          </div>
          <button onClick={runPipeline} data-testid="pipeline-btn"
            className="border border-zinc-800 hover:bg-zinc-900 rounded-sm px-3 py-1.5 text-xs font-mono uppercase tracking-widest flex items-center gap-1.5 text-zinc-300">
            <ArrowClockwiseIcon size={12} /> Sync
          </button>
          <button onClick={() => downloadFile("csv")} data-testid="export-csv"
            className="border border-zinc-800 hover:bg-zinc-900 rounded-sm px-3 py-1.5 text-xs font-mono uppercase tracking-widest flex items-center gap-1.5 text-zinc-300">
            <FileArrowDownIcon size={12} /> CSV
          </button>
          <button onClick={() => downloadFile("pdf")} data-testid="export-pdf"
            className="border border-zinc-800 hover:bg-zinc-900 rounded-sm px-3 py-1.5 text-xs font-mono uppercase tracking-widest flex items-center gap-1.5 text-zinc-300">
            <FilePdfIcon size={12} /> PDF
          </button>
        </div>
      </div>

      {/* Top metrics */}
      <div className="grid grid-cols-4 gap-4">
        <Panel className="p-4">
          <Metric label="Total kWh" value={summary?.total_kwh?.toFixed(1) ?? "—"} unit="kWh" testid="metric-kwh"
            sub={`${range.days} day${range.days > 1 ? "s" : ""}`} />
        </Panel>
        <Panel className="p-4">
          <Metric label="Est. cost" value={`$${summary?.total_cost?.toFixed(2) ?? "—"}`} testid="metric-cost"
            sub={`@ $${summary?.rate_usd_per_kwh?.toFixed(3) ?? "—"}/kWh`} />
        </Panel>
        <Panel className="p-4">
          <Metric label="Anomalies" value={summary?.active_anomalies ?? "—"} unit="flags" testid="metric-anom"
            sub={`${summary?.critical_anomalies ?? 0} critical`}
            className={summary?.critical_anomalies > 0 ? "" : ""} />
        </Panel>
        <Panel className="p-4">
          <Metric label="Base load"
            value={summary?.base_load?.kwh?.toFixed(1) ?? "—"} unit="kWh" testid="metric-base"
            sub={`$${summary?.base_load?.cost?.toFixed(2) ?? "—"}`} />
        </Panel>
      </div>

      {/* Timeline chart */}
      <Panel data-testid="timeline-panel">
        <PanelHeader label="Whole-home timeline · per-unit attribution" />
        <div className="p-4" style={{ height: 320 }}>
          {chartData.length === 0 && (
            <div className="h-full flex items-center justify-center text-sm text-zinc-500 font-mono">
              no data — click Sync to seed
            </div>
          )}
          {chartData.length > 0 && (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
                <CartesianGrid stroke="#27272a" vertical={false} />
                <XAxis dataKey="ts" stroke="#71717a" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }}
                  tickFormatter={(v) => range.bucket === "day" ? v.slice(5) : v.slice(11, 16)} />
                <YAxis stroke="#71717a" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} yAxisId="left" />
                <YAxis stroke="#f59e0b" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} yAxisId="right" orientation="right"
                  tickFormatter={(v) => `${v}°F`} width={40} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 10, fontFamily: "IBM Plex Mono", textTransform: "uppercase", letterSpacing: "0.1em" }} />
                <Area yAxisId="left" type="monotone" dataKey="base_load" stackId="1" stroke="#71717a" fill="#71717a" fillOpacity={0.2} name="Base load" />
                {(timeline?.units || []).map((u) => (
                  <Area key={u.id} yAxisId="left" type="monotone" dataKey={u.id} stackId="1" stroke={u.color} fill={u.color} fillOpacity={0.4} name={u.name} />
                ))}
                <Line yAxisId="right" type="monotone" dataKey="outdoor_temp_f" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="Outdoor °F" />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </Panel>

      {/* Per-unit panels */}
      <div className="grid grid-cols-2 gap-4">
        {(summary?.units || []).map((u) => (
          <Panel key={u.id} data-testid={`unit-panel-${u.id}`}>
            <PanelHeader
              label={
                <span className="flex items-center gap-2">
                  <span className="inline-block w-2 h-2 rounded-sm" style={{ background: u.color }} />
                  {u.name}
                </span>
              }
            />
            <div className="p-4 grid grid-cols-2 gap-4">
              <Metric label="kWh" value={u.kwh?.toFixed(1) ?? "0"} unit="kWh" />
              <Metric label="Cost" value={`$${u.cost?.toFixed(2) ?? "0"}`} />
              <Metric label="Runtime" value={u.runtime_hours?.toFixed(1) ?? "0"} unit="hrs" />
              <Metric label="Efficiency" value={u.kwh_per_runtime_hour?.toFixed(2) ?? "0"} unit="kWh/hr" />
            </div>
          </Panel>
        ))}
      </div>

      {/* Recent anomalies + data status */}
      <div className="grid grid-cols-3 gap-4">
        <Panel className="col-span-2" data-testid="anomalies-panel">
          <PanelHeader label="Recent anomalies"
            action={<a href="/anomalies" className="font-mono text-[10px] uppercase tracking-[0.2em] text-blue-400 hover:text-blue-300">view all →</a>} />
          <div className="divide-y divide-zinc-800/60">
            {anomalies.length === 0 && (
              <div className="p-6 text-sm text-zinc-500 font-mono">no anomalies</div>
            )}
            {anomalies.map((a) => {
              const unit = units.find((u) => u.id === a.unit_id);
              return (
                <div key={a.id} className="px-4 py-3 flex items-start gap-3 hover:bg-zinc-900/40" data-testid={`anomaly-${a.id}`}>
                  <SeverityPill severity={a.severity} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-zinc-100 truncate">{a.title}</div>
                    <div className="text-xs text-zinc-500 font-mono mt-0.5">
                      {unit?.name || "—"} · {new Date(a.ts_start).toLocaleString()}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>
        <Panel data-testid="status-panel">
          <PanelHeader label="Data status" />
          <div className="p-4 space-y-3 font-mono text-xs">
            <StatusRow label="energy intervals" value={dataStatus?.energy_intervals ?? 0} />
            <StatusRow label="thermostat rows" value={dataStatus?.thermostat_readings ?? 0} />
            <StatusRow label="weather rows" value={dataStatus?.weather_readings ?? 0} />
            <div className="border-t border-zinc-800 pt-3 mt-3">
              <div className="text-zinc-500 uppercase tracking-widest text-[10px] mb-1">resideo</div>
              <div className={dataStatus?.resideo?.mock_mode ? "text-amber-500" : "text-emerald-500"}>
                {dataStatus?.resideo?.mock_mode ? "MOCK MODE" : "LIVE"}
              </div>
              <div className="text-zinc-500 text-[10px] mt-1 leading-relaxed">
                {dataStatus?.resideo?.message}
              </div>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function StatusRow({ label, value }) {
  return (
    <div className="flex justify-between">
      <span className="text-zinc-500 uppercase tracking-widest text-[10px]">{label}</span>
      <span className="text-zinc-100">{value}</span>
    </div>
  );
}
