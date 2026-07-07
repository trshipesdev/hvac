import React, { useEffect, useState } from "react";
import { api } from "@/lib/apiClient";
import { X, Thermometer, Zap, AlertTriangle } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { SeverityPill } from "@/components/Panel";
import { createPortal } from "react-dom";
import { fmtTimeOnly, fmtBucketLabel } from "@/lib/time";

export default function DrilldownModal({ ts, bucket, onClose, property }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try { const r = await api.drilldown(ts, bucket); setData(r.data); }
      catch { setData({ error: true }); }
      finally { setLoading(false); }
    })();
  }, [ts, bucket]);

  // Build chart data merging thermostat + weather + interval. Keyed by the
  // raw UTC ISO instant (always correctly sortable) — the localized 12h/24h
  // label is only computed after sorting, so AM/PM formatting never breaks
  // chronological order the way sorting on a formatted string would.
  const chartData = React.useMemo(() => {
    if (!data?.intervals?.length && !data?.readings_by_unit) return [];
    const byTs = new Map();
    (data.intervals || []).forEach((iv) => {
      byTs.set(iv.ts_start, { key: iv.ts_start, kwh: iv.kwh });
    });
    Object.entries(data.readings_by_unit || {}).forEach(([uid, readings]) => {
      readings.forEach((r) => {
        const row = byTs.get(r.ts) || { key: r.ts };
        row[`setpoint_${uid}`] = r.setpoint_f;
        row[`actual_${uid}`] = r.actual_temp_f;
        row[`on_${uid}`] = r.compressor_on ? 1 : 0;
        byTs.set(r.ts, row);
      });
    });
    (data.weather || []).forEach((w) => {
      const row = byTs.get(w.ts) || { key: w.ts };
      row.outdoor = w.outdoor_temp_f;
      byTs.set(w.ts, row);
    });
    return Array.from(byTs.values())
      .sort((a, b) => a.key.localeCompare(b.key))
      .map((row) => ({ ...row, ts: fmtTimeOnly(row.key, property) }));
  }, [data, property]);

  return createPortal(
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-6 animate-fade-in" onClick={onClose} data-testid="drilldown-modal">
      <div className="bg-white rounded-xl border border-paper-300 max-w-5xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="px-6 py-4 border-b border-paper-300 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-forest-500">Drill-down · {bucket}</div>
            <div className="text-lg font-serif text-forest-900">{bucket === "day" ? ts : `${ts.slice(0, 10)} ${fmtBucketLabel(ts, "hour", property)}`}</div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-forest-800 p-1 rounded-lg hover:bg-paper-200" data-testid="drilldown-close">
            <X size={20} strokeWidth={1.75} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {loading && <div className="text-sm text-slate-500 text-center py-10">Loading…</div>}
          {data?.error && <div className="text-sm text-red-600 text-center py-10">Failed to load window.</div>}
          {data && !data.error && (
            <>
              <div className="grid grid-cols-3 gap-4">
                <Stat label="Intervals" value={data.intervals?.length ?? 0} icon={<Zap size={13} strokeWidth={1.75} className="text-energy-600" />} />
                <Stat label="Thermostat readings" value={Object.values(data.readings_by_unit || {}).reduce((s, r) => s + r.length, 0)} icon={<Thermometer size={13} strokeWidth={1.75} className="text-forest-600" />} />
                <Stat label="Anomalies" value={data.anomalies?.length ?? 0} icon={<AlertTriangle size={13} strokeWidth={1.75} className="text-amber-600" />} />
              </div>

              {(data.units || []).some((u) => (data.readings_by_unit?.[u.id] || []).length > 0) && (
                <div className="flex flex-wrap gap-3">
                  {(data.units || []).map((u) => {
                    const readings = data.readings_by_unit?.[u.id] || [];
                    if (!readings.length) return null;
                    const sources = new Set(readings.map((r) => r.source || "mock"));
                    const label = sources.has("mock") ? "mock" : sources.has("estimated") ? "estimated" : "live";
                    return (
                      <span key={u.id} className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full border ${
                        label === "live" ? "text-energy-700 bg-energy-50 border-energy-500/40" : "text-amber-700 bg-amber-50 border-amber-300"
                      }`} data-testid={`drilldown-source-${u.id}`}>{u.name}: {label}</span>
                    );
                  })}
                </div>
              )}

              {chartData.length > 0 && (
                <div className="border border-paper-300 rounded-lg p-4">
                  <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-3">Temperature vs compressor state</div>
                  <div style={{ height: 220 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData}>
                        <CartesianGrid stroke="#E2E0D8" strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="ts" stroke="#94A3B8" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono", fill: "#64748B" }} />
                        <YAxis stroke="#94A3B8" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono", fill: "#64748B" }} />
                        <Tooltip />
                        <Legend wrapperStyle={{ fontSize: 10, fontFamily: "DM Sans", color: "#5E6C64" }} />
                        {(data.units || []).map((u, i) => (
                          <React.Fragment key={u.id}>
                            <Line type="monotone" dataKey={`setpoint_${u.id}`} name={`${u.name} setpoint`} stroke={u.color} strokeDasharray="4 4" strokeWidth={1.25} dot={false} />
                            <Line type="monotone" dataKey={`actual_${u.id}`} name={`${u.name} actual`} stroke={u.color} strokeWidth={1.75} dot={false} />
                          </React.Fragment>
                        ))}
                        <Line type="monotone" dataKey="outdoor" name="Outdoor" stroke="#F59E0B" strokeWidth={1.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {data.anomalies?.length > 0 && (
                <div>
                  <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">Anomalies in this window</div>
                  <div className="border border-paper-300 rounded-lg divide-y divide-paper-200">
                    {data.anomalies.map((a) => (
                      <div key={a.id} className="px-4 py-2.5 flex items-start gap-3">
                        <SeverityPill severity={a.severity} />
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-forest-800">{a.title}</div>
                          <div className="text-xs text-slate-500 mt-0.5">{a.description}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">Raw intervals ({data.intervals?.length ?? 0})</div>
                <div className="border border-paper-300 rounded-lg overflow-hidden max-h-56 overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-paper-100 sticky top-0">
                      <tr className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 border-b border-paper-300">
                        <th className="text-left py-2 px-3">Start</th>
                        <th className="text-right py-2 px-3">kWh</th>
                        <th className="text-right py-2 px-3">Base</th>
                        {(data.units || []).map((u) => <th key={u.id} className="text-right py-2 px-3">{u.name}</th>)}
                        <th className="text-right py-2 px-3">Cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data.intervals || []).map((iv) => (
                        <tr key={iv.id} className="border-b border-paper-200 last:border-0 font-mono">
                          <td className="py-1.5 px-3 text-forest-800">{fmtTimeOnly(iv.ts_start, property)}</td>
                          <td className="text-right py-1.5 px-3 text-forest-800">{iv.kwh?.toFixed(3)}</td>
                          <td className="text-right py-1.5 px-3 text-slate-500">{iv.base_load_kwh?.toFixed(3) ?? "—"}</td>
                          {(data.units || []).map((u) => (
                            <td key={u.id} className="text-right py-1.5 px-3" style={{ color: u.color }}>
                              {iv.unit_kwh?.[u.id]?.toFixed(3) ?? "—"}
                            </td>
                          ))}
                          <td className="text-right py-1.5 px-3 text-forest-800">${((iv.base_load_cost || 0) + Object.values(iv.unit_cost || {}).reduce((a, b) => a + b, 0)).toFixed(3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

function Stat({ label, value, icon }) {
  return (
    <div className="border border-paper-300 rounded-lg p-3 bg-paper-50 flex items-center gap-3">
      <div className="w-8 h-8 rounded-lg bg-white border border-paper-300 flex items-center justify-center">{icon}</div>
      <div>
        <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">{label}</div>
        <div className="font-mono text-lg text-forest-800">{value}</div>
      </div>
    </div>
  );
}
