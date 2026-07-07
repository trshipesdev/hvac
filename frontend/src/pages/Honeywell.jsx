import React, { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader, Select } from "@/components/Panel";
import { GroupedTable } from "@/components/GroupedTable";
import { toast } from "sonner";
import { Upload, RefreshCw, FileSpreadsheet, ScanSearch } from "lucide-react";
import { Link } from "react-router-dom";

export default function Honeywell() {
  const [units, setUnits] = useState([]);
  const [zoneMonths, setZoneMonths] = useState([]);
  const [loadError, setLoadError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [rescanning, setRescanning] = useState(false);
  const [filterUnit, setFilterUnit] = useState("");
  const [filterYear, setFilterYear] = useState("");
  const [unassignedOnly, setUnassignedOnly] = useState(false);

  const load = async () => {
    setLoadError(false);
    try {
      const [u, zm] = await Promise.all([api.listUnits(), api.listHoneywellZoneMonths()]);
      setUnits(u.data);
      setZoneMonths(zm.data);
      setLoaded(true);
    } catch {
      toast.error("Couldn't load zone reports — backend may be unreachable");
      setLoadError(true);
    }
  };
  useEffect(() => { load(); }, []);

  const assign = async (id, unitId) => {
    if (!unitId) return;
    try {
      await api.patchHoneywellZoneMonth(id, { unit_id: unitId });
      toast.success("Zone assigned");
      load();
    } catch (e) { toast.error("Assign failed: " + (e.response?.data?.detail || e.message)); }
  };

  const unmatched = zoneMonths.filter((z) => !z.unit_id);

  const years = useMemo(() => Array.from(new Set(zoneMonths.map((z) => z.year))).sort((a, b) => b - a), [zoneMonths]);
  const filteredZoneMonths = useMemo(() => zoneMonths.filter((z) =>
    (!filterUnit || z.unit_id === filterUnit) &&
    (!filterYear || String(z.year) === filterYear) &&
    (!unassignedOnly || !z.unit_id)
  ), [zoneMonths, filterUnit, filterYear, unassignedOnly]);
  const monthGroups = useMemo(() => {
    const byMonth = new Map();
    for (const z of filteredZoneMonths) {
      const key = `${z.year}-${z.month}`;
      const g = byMonth.get(key) || { key, year: z.year, month: z.month, rows: [] };
      g.rows.push(z);
      byMonth.set(key, g);
    }
    return Array.from(byMonth.values())
      .sort((a, b) => (b.year - a.year) || (b.month - a.month))
      .map((g) => ({ ...g, totalRuntime: g.rows.reduce((s, z) => s + (z.total_runtime_hours || 0), 0) }));
  }, [filteredZoneMonths]);

  const exportCsv = async () => {
    try {
      const blob = await api.downloadZoneMonthsCsv();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "hvac-zone-months.csv"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
  };

  const rescan = async () => {
    setRescanning(true);
    try {
      const r = await api.rescanZoneAnomalies();
      toast.success(`Scanned ${r.data.zone_months_scanned} zone-months — ${r.data.new_anomalies} new anomalies found`);
    } catch (e) { toast.error("Rescan failed: " + (e.response?.data?.detail || e.message)); }
    finally { setRescanning(false); }
  };

  return (
    <div className="space-y-8 animate-fade-in" data-testid="honeywell-page">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">thermostat runtime reports</div>
          <h1 className="text-4xl font-serif tracking-tight text-forest-900">Zone Reports</h1>
          <p className="text-sm text-slate-600 mt-1.5 max-w-xl">
            Real per-zone runtime hours parsed from your thermostat energy-report emails —
            a workaround until live thermostat sync is available.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={exportCsv} data-testid="export-zone-months-csv"
            className="bg-white border border-paper-300 hover:bg-paper-200 text-forest-700 rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 transition-colors">
            <FileSpreadsheet size={13} strokeWidth={1.75} /> Export CSV
          </button>
          <button onClick={rescan} disabled={rescanning} data-testid="rescan-zone-anomalies-btn"
            className="bg-white border border-paper-300 hover:bg-paper-200 text-forest-700 rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 transition-colors">
            <ScanSearch size={13} strokeWidth={1.75} /> {rescanning ? "Scanning…" : "Rescan anomalies"}
          </button>
          <Link to="/ingest" className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 transition-colors">
            <Upload size={13} strokeWidth={1.75} /> Upload reports on Ingest
          </Link>
        </div>
      </div>

      {loadError && (
        <Panel data-testid="honeywell-load-error" className="p-6 flex items-center justify-between">
          <div className="text-sm text-slate-500">Couldn't reach the backend to load zone reports — this is NOT the same as having no data.</div>
          <button onClick={load} className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 transition-colors">
            <RefreshCw size={13} strokeWidth={1.75} /> Retry
          </button>
        </Panel>
      )}

      {unmatched.length > 0 && (
        <Panel data-testid="honeywell-unmatched-panel">
          <PanelHeader label="Ambiguous zones — assign to a unit" />
          <div className="p-4 text-xs text-slate-500 border-b border-paper-300">
            These zone names matched more than one existing unit and couldn't be auto-assigned.
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 border-b border-paper-300">
                  <th className="text-left py-3 px-6">Zone</th>
                  <th className="text-left py-3 px-4">Month</th>
                  <th className="text-right py-3 px-4">Runtime hrs</th>
                  <th className="text-left py-3 px-4">Assign to unit</th>
                </tr>
              </thead>
              <tbody>
                {unmatched.map((z) => (
                  <tr key={z.id} className="border-b border-paper-200" data-testid={`honeywell-unmatched-${z.id}`}>
                    <td className="py-3 px-6 text-forest-800 font-medium">{z.zone_name}</td>
                    <td className="py-3 px-4 text-slate-600 font-mono">{z.year}-{String(z.month).padStart(2, "0")}</td>
                    <td className="text-right py-3 px-4 font-mono text-forest-800">{z.total_runtime_hours ?? "—"}</td>
                    <td className="py-3 px-4">
                      <select onChange={(e) => assign(z.id, e.target.value)} defaultValue=""
                        className="bg-white border border-paper-300 rounded-lg px-2 py-1.5 text-sm text-forest-800"
                        data-testid={`honeywell-assign-${z.id}`}>
                        <option value="" disabled>Select unit…</option>
                        {units.map((u) => <option key={u.id} value={u.id}>{u.name}{u.floor ? ` (${u.floor})` : ""}</option>)}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <Panel data-testid="honeywell-history-panel">
        <PanelHeader label="Stored zone-months" />
        {zoneMonths.length > 0 && (
          <div className="p-5 flex flex-wrap gap-4 border-b border-paper-300 items-end">
            <Select label="Unit" value={filterUnit} onChange={setFilterUnit} data-testid="honeywell-filter-unit">
              <option value="">All units</option>
              {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </Select>
            <Select label="Year" value={filterYear} onChange={setFilterYear} data-testid="honeywell-filter-year">
              <option value="">All years</option>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </Select>
            <label className="flex items-center gap-2 text-sm text-forest-800 cursor-pointer h-9">
              <input type="checkbox" checked={unassignedOnly} onChange={(e) => setUnassignedOnly(e.target.checked)} className="accent-forest-500 w-4 h-4" data-testid="honeywell-filter-unassigned" />
              Unassigned only
            </label>
            <div className="ml-auto text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">{filteredZoneMonths.length} row{filteredZoneMonths.length !== 1 ? "s" : ""}</div>
          </div>
        )}
        <div className="overflow-x-auto">
          {loaded && zoneMonths.length === 0 && (
            <div className="p-10 text-center text-slate-500">No zone reports yet — upload some on the Ingest page to get started.</div>
          )}
          {zoneMonths.length > 0 && (
            <GroupedTable
              columns={[
                { key: "zone", label: "Zone", className: "text-left py-3 px-6" },
                { key: "month", label: "Month", className: "text-left py-3 px-4" },
                { key: "runtime", label: "Runtime hrs", className: "text-right py-3 px-4" },
                { key: "heat", label: "Heating", className: "text-right py-3 px-4" },
                { key: "cool", label: "Cooling", className: "text-right py-3 px-4" },
                { key: "off", label: "Off hrs", className: "text-right py-3 px-4" },
                { key: "unit", label: "Unit", className: "text-left py-3 px-4" },
                { key: "flag", label: "", className: "px-4" },
              ]}
              groups={monthGroups}
              rowKey={(z) => z.id}
              renderGroupHeader={(g) => (
                <div className="flex items-center justify-between text-xs">
                  <span className="font-mono text-forest-800 font-medium">{g.year}-{String(g.month).padStart(2, "0")}</span>
                  <span className="text-slate-500 font-mono">{g.totalRuntime.toFixed(0)} hrs total across {g.rows.length} zone{g.rows.length === 1 ? "" : "s"}</span>
                </div>
              )}
              renderRow={(z) => {
                const unit = units.find((u) => u.id === z.unit_id);
                return (
                  <>
                    <td className="py-3 px-6 text-forest-800 font-medium">{z.zone_name}</td>
                    <td className="py-3 px-4"></td>
                    <td className="text-right py-3 px-4 font-mono text-forest-800">{z.total_runtime_hours ?? "—"}</td>
                    <td className="text-right py-3 px-4 font-mono text-slate-500">{z.heating_hours ?? "—"}</td>
                    <td className="text-right py-3 px-4 font-mono text-slate-500">{z.cooling_hours ?? "—"}</td>
                    <td className="text-right py-3 px-4 font-mono text-slate-500">{z.equipment_off_hours ?? "—"}</td>
                    <td className="py-3 px-4 text-forest-800">{unit ? unit.name : <span className="text-amber-600">unassigned</span>}</td>
                    <td className="text-right py-3 px-4">{z.is_estimated && <span className="text-[10px] uppercase tracking-widest text-amber-600">estimated</span>}</td>
                  </>
                );
              }}
            />
          )}
        </div>
      </Panel>
    </div>
  );
}
