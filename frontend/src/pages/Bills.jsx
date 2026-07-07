import React, { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader, Select } from "@/components/Panel";
import { toast } from "sonner";
import { Trash2, Plus, Upload, ScanSearch, RefreshCw, FileSpreadsheet } from "lucide-react";
import { Link } from "react-router-dom";

export default function Bills() {
  const [bills, setBills] = useState([]);
  const [ratePeriods, setRatePeriods] = useState([]);
  const [form, setForm] = useState({ start: "", end: "", total_kwh: "", total_cost: "", rate_usd_per_kwh: "", notes: "" });
  const [rescanning, setRescanning] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [filterYear, setFilterYear] = useState("");
  const [discrepancyOnly, setDiscrepancyOnly] = useState(false);

  const load = async () => {
    setLoadError(false);
    try {
      const [b, rp] = await Promise.all([api.listBills(), api.listRatePeriods()]);
      setBills(b.data); setRatePeriods(rp.data);
      setLoaded(true);
    } catch {
      toast.error("Couldn't load bills — backend may be unreachable");
      setLoadError(true);
    }
  };
  useEffect(() => { load(); }, []);

  const rescan = async () => {
    setRescanning(true);
    try {
      const r = await api.rescanBillAnomalies();
      toast.success(`Scanned ${r.data.bills_scanned} bills — ${r.data.new_anomalies} new anomalies found`);
    } catch (e) { toast.error("Rescan failed: " + (e.response?.data?.detail || e.message)); }
    finally { setRescanning(false); }
  };

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.createBill({
        start: new Date(form.start).toISOString(),
        end: new Date(form.end).toISOString(),
        total_kwh: form.total_kwh ? parseFloat(form.total_kwh) : null,
        total_cost: form.total_cost ? parseFloat(form.total_cost) : null,
        rate_usd_per_kwh: form.rate_usd_per_kwh ? parseFloat(form.rate_usd_per_kwh) : null,
        notes: form.notes || null,
      });
      toast.success("Bill period saved");
      setForm({ start: "", end: "", total_kwh: "", total_cost: "", rate_usd_per_kwh: "", notes: "" });
      load();
    } catch { toast.error("Save failed"); }
  };

  const remove = async (id) => { try { await api.deleteBill(id); load(); } catch { toast.error("Delete failed"); } };

  const exportCsv = async () => {
    try {
      const blob = await api.downloadBillsCsv();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "hvac-bills.csv"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
  };

  const years = useMemo(() => Array.from(new Set(bills.map((b) => b.start?.slice(0, 4)).filter(Boolean))).sort((a, b) => b.localeCompare(a)), [bills]);
  const filteredBills = useMemo(() => bills.filter((b) => {
    if (filterYear && b.start?.slice(0, 4) !== filterYear) return false;
    if (discrepancyOnly) {
      const dKwh = (b.total_kwh || 0) - (b.computed_kwh || 0);
      const dCost = (b.total_cost || 0) - (b.computed_cost || 0);
      if (Math.abs(dKwh) <= 5 && Math.abs(dCost) <= 5) return false;
    }
    return true;
  }), [bills, filterYear, discrepancyOnly]);

  return (
    <div className="space-y-8 animate-fade-in" data-testid="bills-page">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">bill reconciliation</div>
          <h1 className="text-4xl font-serif tracking-tight text-forest-900">Bills</h1>
          <p className="text-sm text-slate-600 mt-1.5 max-w-xl">Real rate history derived from your uploaded bills, reconciled against your Green Button data.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={exportCsv} data-testid="export-bills-csv"
            className="bg-white border border-paper-300 hover:bg-paper-200 text-forest-700 rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 transition-colors">
            <FileSpreadsheet size={13} strokeWidth={1.75} /> Export CSV
          </button>
          <button onClick={rescan} disabled={rescanning} data-testid="rescan-anomalies-btn"
            className="bg-white border border-paper-300 hover:bg-paper-200 text-forest-700 rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 transition-colors">
            <ScanSearch size={13} strokeWidth={1.75} /> {rescanning ? "Scanning…" : "Rescan anomalies"}
          </button>
          <Link to="/ingest" className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 transition-colors">
            <Upload size={13} strokeWidth={1.75} /> Upload bills on Ingest
          </Link>
        </div>
      </div>

      {loadError && (
        <Panel data-testid="bills-load-error" className="p-6 flex items-center justify-between">
          <div className="text-sm text-slate-500">Couldn't reach the backend to load bills — this is NOT the same as having no bills.</div>
          <button onClick={load} className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 transition-colors">
            <RefreshCw size={13} strokeWidth={1.75} /> Retry
          </button>
        </Panel>
      )}

      {ratePeriods.length > 0 && (
        <Panel data-testid="rate-periods-panel">
          <PanelHeader label="Rate history · derived from parsed bills" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 border-b border-paper-300">
                  <th className="text-left py-3 px-6">Period</th>
                  <th className="text-left py-3 px-4">Utility</th>
                  <th className="text-right py-3 px-4">Effective $/kWh</th>
                  <th className="text-left py-3 px-4">Tiers</th>
                </tr>
              </thead>
              <tbody>
                {ratePeriods.map((rp) => (
                  <tr key={rp.id} className="border-b border-paper-200 hover:bg-paper-50 transition-colors">
                    <td className="py-3 px-6 text-forest-800">{rp.start?.slice(0, 10)} → {rp.end?.slice(0, 10)}</td>
                    <td className="py-3 px-4 text-forest-800">{rp.utility_name || "—"}</td>
                    <td className="text-right py-3 px-4 font-mono text-forest-600">${rp.effective_rate?.toFixed(4)}</td>
                    <td className="py-3 px-4 text-xs text-slate-500 font-mono">
                      {rp.tiers?.length ? rp.tiers.map((t) => `${t.tier_name}: $${t.rate_per_kwh}`).join(" · ") : "flat"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <Panel data-testid="bill-form-panel">
        <PanelHeader label="Add bill period manually" />
        <form onSubmit={submit} className="p-6 grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="Period start"><input type="date" required value={form.start} onChange={(e) => setForm({...form, start: e.target.value})} className={inputCls} data-testid="bill-start" /></Field>
          <Field label="Period end"><input type="date" required value={form.end} onChange={(e) => setForm({...form, end: e.target.value})} className={inputCls} data-testid="bill-end" /></Field>
          <Field label="Rate ($/kWh)"><input type="number" step="0.001" value={form.rate_usd_per_kwh} onChange={(e) => setForm({...form, rate_usd_per_kwh: e.target.value})} className={inputCls} data-testid="bill-rate" /></Field>
          <Field label="Bill total (kWh)"><input type="number" step="0.01" value={form.total_kwh} onChange={(e) => setForm({...form, total_kwh: e.target.value})} className={inputCls} data-testid="bill-kwh" /></Field>
          <Field label="Bill total ($)"><input type="number" step="0.01" value={form.total_cost} onChange={(e) => setForm({...form, total_cost: e.target.value})} className={inputCls} data-testid="bill-cost" /></Field>
          <Field label="Notes"><input value={form.notes} onChange={(e) => setForm({...form, notes: e.target.value})} className={inputCls} data-testid="bill-notes" /></Field>
          <div className="md:col-span-3 flex justify-end">
            <button type="submit" data-testid="bill-submit"
              className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-4 py-2.5 text-sm font-medium flex items-center gap-2 transition-colors">
              <Plus size={14} strokeWidth={1.75} /> Reconcile
            </button>
          </div>
        </form>
      </Panel>

      <Panel data-testid="bills-list-panel">
        <PanelHeader label="History" />
        {bills.length > 0 && (
          <div className="p-5 flex flex-wrap gap-4 border-b border-paper-300 items-end">
            <Select label="Year" value={filterYear} onChange={setFilterYear} data-testid="bills-filter-year">
              <option value="">All years</option>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </Select>
            <label className="flex items-center gap-2 text-sm text-forest-800 cursor-pointer h-9">
              <input type="checkbox" checked={discrepancyOnly} onChange={(e) => setDiscrepancyOnly(e.target.checked)} className="accent-forest-500 w-4 h-4" data-testid="bills-filter-discrepancy" />
              Only bills with a $/kWh discrepancy
            </label>
            <div className="ml-auto text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">{filteredBills.length} result{filteredBills.length !== 1 ? "s" : ""}</div>
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 border-b border-paper-300">
                <th className="text-left py-3 px-6">Period</th>
                <th className="text-right py-3 px-4">Bill kWh</th>
                <th className="text-right py-3 px-4">Bill $</th>
                <th className="text-right py-3 px-4">Rate</th>
                <th className="text-right py-3 px-4">Computed kWh</th>
                <th className="text-right py-3 px-4">Computed $</th>
                <th className="text-right py-3 px-4">Δ kWh</th>
                <th className="text-right py-3 px-4">Δ $</th>
                <th className="px-4"></th>
              </tr>
            </thead>
            <tbody>
              {loaded && bills.length === 0 && (<tr><td colSpan="9" className="p-10 text-center text-slate-500">No bill periods yet — upload PDFs on the Ingest page to get started.</td></tr>)}
              {loaded && bills.length > 0 && filteredBills.length === 0 && (<tr><td colSpan="9" className="p-10 text-center text-slate-500">No bills match the current filters.</td></tr>)}
              {filteredBills.map((b) => {
                const dKwh = (b.total_kwh || 0) - (b.computed_kwh || 0);
                const dCost = (b.total_cost || 0) - (b.computed_cost || 0);
                return (
                  <tr key={b.id} className="border-b border-paper-200 hover:bg-paper-50 transition-colors" data-testid={`bill-${b.id}`}>
                    <td className="py-3 px-6 text-forest-800 font-medium">{b.start?.slice(0, 10)} → {b.end?.slice(0, 10)}</td>
                    <td className="text-right py-3 px-4 font-mono text-forest-800">{b.total_kwh ?? "—"}</td>
                    <td className="text-right py-3 px-4 font-mono text-forest-800">${b.total_cost?.toFixed(2) ?? "—"}</td>
                    <td className="text-right py-3 px-4 font-mono text-forest-500">${b.rate_usd_per_kwh?.toFixed(4) ?? "—"}</td>
                    <td className="text-right py-3 px-4 font-mono text-slate-500">{b.computed_kwh?.toFixed(2) ?? "—"}</td>
                    <td className="text-right py-3 px-4 font-mono text-slate-500">${b.computed_cost?.toFixed(2) ?? "—"}</td>
                    <td className={`text-right py-3 px-4 font-mono ${Math.abs(dKwh) > 5 ? "text-amber-600" : "text-energy-600"}`}>{dKwh >= 0 ? "+" : ""}{dKwh.toFixed(1)}</td>
                    <td className={`text-right py-3 px-4 font-mono ${Math.abs(dCost) > 5 ? "text-amber-600" : "text-energy-600"}`}>{dCost >= 0 ? "+" : ""}${dCost.toFixed(2)}</td>
                    <td className="text-right py-3 px-4">
                      <button onClick={() => remove(b.id)} className="text-slate-400 hover:text-red-600 transition-colors" data-testid={`bill-delete-${b.id}`}><Trash2 size={14} strokeWidth={1.75} /></button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

const inputCls = "w-full bg-white border border-paper-300 rounded-lg px-3 py-2 text-sm text-forest-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-forest-500/30 focus:border-forest-500 transition-all";

function Field({ label, children, className }) {
  return (
    <label className={`block ${className || ""}`}>
      <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-1.5">{label}</div>
      {children}
    </label>
  );
}
