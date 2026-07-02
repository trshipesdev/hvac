import React, { useEffect, useState, useRef } from "react";
import { API, api } from "@/lib/apiClient";
import { Panel, PanelHeader, Kv } from "@/components/Panel";
import { toast } from "sonner";
import { Trash2, Plus, Upload, Sparkles, Check, X, Files } from "lucide-react";
import axios from "axios";

export default function Bills() {
  const [bills, setBills] = useState([]);
  const [ratePeriods, setRatePeriods] = useState([]);
  const [form, setForm] = useState({ start: "", end: "", total_kwh: "", total_cost: "", rate_usd_per_kwh: "", notes: "" });
  const [dragOver, setDragOver] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [preview, setPreview] = useState(null);
  const [applyRate, setApplyRate] = useState(true);
  const [bulkResults, setBulkResults] = useState(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const inputRef = useRef();
  const bulkRef = useRef();

  const load = async () => {
    try {
      const [b, rp] = await Promise.all([api.listBills(), api.listRatePeriods()]);
      setBills(b.data); setRatePeriods(rp.data);
    } catch {}
  };
  useEffect(() => { load(); }, []);

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

  const remove = async (id) => { try { await api.deleteBill(id); load(); } catch {} };

  const handleFile = async (file) => {
    if (!file) return;
    setParsing(true); setPreview(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await axios.post(`${API}/bills/parse`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setPreview(res.data);
      toast.success("Bill parsed — review below and confirm");
    } catch (e) { toast.error("Parse failed: " + (e.response?.data?.detail || e.message)); }
    finally { setParsing(false); }
  };

  const confirmParsed = async () => {
    if (!preview) return;
    try {
      await axios.post(`${API}/bills/confirm`, { parsed: preview.parsed, apply_rate: applyRate });
      toast.success(applyRate ? "Bill saved & rate updated" : "Bill saved");
      setPreview(null); load();
    } catch (e) { toast.error("Save failed: " + (e.response?.data?.detail || e.message)); }
  };

  const handleBulk = async (files) => {
    if (!files?.length) return;
    setBulkBusy(true); setBulkResults(null);
    try {
      const r = await api.bulkParseBills(files);
      setBulkResults(r.data);
      const ok = r.data.results.filter((x) => x.ok).length;
      toast.success(`Bulk done: ${ok}/${r.data.count} bills parsed`);
      load();
    } catch (e) { toast.error("Bulk failed: " + (e.response?.data?.detail || e.message)); }
    finally { setBulkBusy(false); }
  };

  return (
    <div className="space-y-8 animate-fade-in" data-testid="bills-page">
      <div>
        <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">bill reconciliation</div>
        <h1 className="text-4xl font-serif tracking-tight text-forest-900">Bills</h1>
        <p className="text-sm text-slate-600 mt-1.5 max-w-xl">Drop any utility PDF — Claude Haiku extracts rate, fees, tiers, and usage history automatically.</p>
      </div>

      <Panel data-testid="bill-upload-panel">
        <PanelHeader label={
          <span className="flex items-center gap-2">
            <Sparkles size={12} strokeWidth={2} className="text-forest-500" />
            Upload PDF · AI parse (Claude Haiku 4.5)
          </span>
        } />
        <div className="p-6">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }}
            onClick={() => inputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all ${
              dragOver ? "border-forest-500 bg-forest-50" : "border-paper-300 hover:border-forest-300 hover:bg-paper-100"
            }`}
            data-testid="bill-dropzone"
          >
            <div className="w-12 h-12 rounded-full bg-paper-200 flex items-center justify-center mx-auto mb-3">
              <Upload size={20} strokeWidth={1.5} className="text-forest-600" />
            </div>
            <div className="text-sm text-forest-800 font-medium">{parsing ? "Parsing with Claude Haiku…" : "Drop utility bill PDF or image"}</div>
            <div className="text-xs text-slate-500 mt-1">works with any US utility · Dominion, Duke, ConEd, PG&E…</div>
            <input ref={inputRef} type="file" accept="application/pdf,image/*" onChange={(e) => handleFile(e.target.files[0])} className="hidden" data-testid="bill-file-input" />
          </div>
        </div>

        {preview && (
          <div className="border-t border-paper-300 p-6 space-y-6 animate-fade-in bg-paper-50" data-testid="bill-preview">
            <div>
              <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-3">Extracted fields</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Kv label="Utility" value={preview.parsed.utility_name} mono={false} />
                <Kv label="Account" value={preview.parsed.account_number} />
                <Kv label="Rate schedule" value={preview.parsed.rate_schedule} mono={false} />
                <Kv label="Period" value={`${preview.parsed.billing_period_start || "—"} → ${preview.parsed.billing_period_end || "—"}`} />
                <Kv label="Total kWh" value={preview.parsed.total_kwh} highlight />
                <Kv label="Total $" value={preview.parsed.total_cost != null ? `$${preview.parsed.total_cost}` : null} highlight />
                <Kv label="Effective $/kWh" value={preview.parsed.effective_rate_per_kwh != null ? `$${preview.parsed.effective_rate_per_kwh}` : null} highlight />
                <Kv label="Days in period" value={preview.parsed.days_in_period} />
                <Kv label="Prev meter" value={preview.parsed.previous_meter_reading} />
                <Kv label="Curr meter" value={preview.parsed.current_meter_reading} />
                <Kv label="Avg daily kWh" value={preview.parsed.average_daily_kwh} />
                <Kv label="Avg daily $" value={preview.parsed.average_daily_cost != null ? `$${preview.parsed.average_daily_cost}` : null} />
                <Kv label="Service address" value={preview.parsed.service_address} mono={false} className="col-span-2 md:col-span-4" />
              </div>
            </div>

            {preview.parsed.tier_breakdown?.length > 0 && (
              <div>
                <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">Tier breakdown</div>
                <div className="border border-paper-300 rounded-lg overflow-hidden bg-white">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 border-b border-paper-300 bg-paper-50">
                        <th className="text-left px-4 py-2">Tier</th>
                        <th className="text-right px-4 py-2">kWh</th>
                        <th className="text-right px-4 py-2">$/kWh</th>
                        <th className="text-right px-4 py-2">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.parsed.tier_breakdown.map((t, i) => (
                        <tr key={i} className="border-b border-paper-200 last:border-b-0">
                          <td className="px-4 py-2 text-forest-800">{t.tier_name}</td>
                          <td className="text-right px-4 py-2 font-mono text-forest-800">{t.kwh ?? "—"}</td>
                          <td className="text-right px-4 py-2 font-mono text-forest-800">${t.rate_per_kwh?.toFixed(4) ?? "—"}</td>
                          <td className="text-right px-4 py-2 font-mono text-forest-800">${t.amount ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {preview.parsed.line_items?.length > 0 && (
              <div>
                <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">Line items</div>
                <div className="border border-paper-300 rounded-lg max-h-60 overflow-y-auto bg-white divide-y divide-paper-200">
                  {preview.parsed.line_items.map((li, i) => (
                    <div key={i} className="flex justify-between items-center px-4 py-2">
                      <span className="text-sm text-forest-800">{li.description}</span>
                      <span className="font-mono text-sm text-forest-800">${li.amount}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="border border-paper-300 rounded-lg p-4 bg-white">
              <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-3">Reconciliation vs your data</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Kv label="Bill kWh" value={preview.parsed.total_kwh} />
                <Kv label="Pipeline kWh" value={preview.computed_kwh} />
                <Kv label="Δ kWh" value={preview.computed_kwh != null && preview.parsed.total_kwh != null ? (preview.parsed.total_kwh - preview.computed_kwh).toFixed(1) : "—"} />
                <Kv label="Current property rate" value={`$${preview.current_property_rate}/kWh`} />
              </div>
            </div>

            <div className="flex items-center justify-between flex-wrap gap-3 pt-2">
              <label className="flex items-center gap-2 text-sm text-forest-800 cursor-pointer">
                <input type="checkbox" checked={applyRate} onChange={(e) => setApplyRate(e.target.checked)} data-testid="apply-rate-toggle"
                  className="accent-forest-500 w-4 h-4" />
                Apply effective rate (${preview.parsed.effective_rate_per_kwh ?? "—"}/kWh) to property
              </label>
              <div className="flex gap-2">
                <button onClick={() => setPreview(null)} data-testid="cancel-preview"
                  className="bg-white border border-paper-300 hover:bg-paper-200 text-forest-700 rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 transition-colors">
                  <X size={13} strokeWidth={1.75} /> Discard
                </button>
                <button onClick={confirmParsed} data-testid="confirm-parsed"
                  className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 transition-colors">
                  <Check size={13} strokeWidth={1.75} /> Confirm & save
                </button>
              </div>
            </div>
          </div>
        )}
      </Panel>

      <Panel data-testid="bulk-upload-panel">
        <PanelHeader label={<span className="flex items-center gap-2"><Files size={12} strokeWidth={2} className="text-forest-500" />Bulk upload · backfill rate history</span>}
          action={<span className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">auto-confirm each</span>} />
        <div className="p-6">
          <input ref={bulkRef} type="file" multiple accept="application/pdf,image/*"
            onChange={(e) => handleBulk(Array.from(e.target.files || []))} className="hidden" data-testid="bulk-file-input" />
          <button onClick={() => bulkRef.current?.click()} disabled={bulkBusy}
            className="w-full border-2 border-dashed border-paper-300 hover:border-forest-300 hover:bg-paper-100 rounded-xl py-6 flex flex-col items-center gap-2 transition-all"
            data-testid="bulk-upload-btn">
            <Files size={22} strokeWidth={1.5} className="text-forest-600" />
            <div className="text-sm text-forest-800 font-medium">{bulkBusy ? "Parsing bills…" : "Select multiple bill PDFs"}</div>
            <div className="text-xs text-slate-500">Rates for each period are stored so past cost is accurate</div>
          </button>

          {bulkResults && (
            <div className="mt-4 border border-paper-300 rounded-lg overflow-hidden bg-white" data-testid="bulk-results">
              <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 px-4 py-2 border-b border-paper-300 bg-paper-50">
                Results ({bulkResults.results.filter((x) => x.ok).length}/{bulkResults.count})
              </div>
              <div className="max-h-56 overflow-y-auto divide-y divide-paper-200">
                {bulkResults.results.map((r, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-2 text-sm">
                    {r.ok ? <Check size={14} className="text-energy-600" strokeWidth={2} /> : <X size={14} className="text-red-600" strokeWidth={2} />}
                    <div className="flex-1 min-w-0">
                      <div className="text-forest-800 truncate">{r.filename}</div>
                      {r.ok
                        ? <div className="text-xs text-slate-500 font-mono">{r.utility} · {r.period} · {r.total_kwh} kWh · ${r.total_cost} · ${r.effective_rate}/kWh</div>
                        : <div className="text-xs text-red-600 truncate">{r.error}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </Panel>

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
              {bills.length === 0 && (<tr><td colSpan="9" className="p-10 text-center text-slate-500">No bill periods yet — drop a PDF above to get started.</td></tr>)}
              {bills.map((b) => {
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

function Field({ label, children }) {
  return (
    <label className="block">
      <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-1.5">{label}</div>
      {children}
    </label>
  );
}
