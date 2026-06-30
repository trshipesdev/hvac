import React, { useEffect, useState, useRef } from "react";
import { API } from "@/lib/apiClient";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader } from "@/components/Panel";
import { toast } from "sonner";
import { TrashIcon, PlusIcon, UploadIcon, SparkleIcon, CheckCircleIcon, XCircleIcon } from "@phosphor-icons/react";
import axios from "axios";

export default function Bills() {
  const [bills, setBills] = useState([]);
  const [form, setForm] = useState({ start: "", end: "", total_kwh: "", total_cost: "", rate_usd_per_kwh: "", notes: "" });
  const [dragOver, setDragOver] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [preview, setPreview] = useState(null); // { parsed, computed_kwh, computed_cost, current_property_rate }
  const [applyRate, setApplyRate] = useState(true);
  const inputRef = useRef();

  const load = async () => {
    try { const r = await api.listBills(); setBills(r.data); } catch {}
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        start: new Date(form.start).toISOString(),
        end: new Date(form.end).toISOString(),
        total_kwh: form.total_kwh ? parseFloat(form.total_kwh) : null,
        total_cost: form.total_cost ? parseFloat(form.total_cost) : null,
        rate_usd_per_kwh: form.rate_usd_per_kwh ? parseFloat(form.rate_usd_per_kwh) : null,
        notes: form.notes || null,
      };
      await api.createBill(payload);
      toast.success("Bill period saved");
      setForm({ start: "", end: "", total_kwh: "", total_cost: "", rate_usd_per_kwh: "", notes: "" });
      load();
    } catch { toast.error("Save failed"); }
  };

  const remove = async (id) => { try { await api.deleteBill(id); load(); } catch {} };

  const handleFile = async (file) => {
    if (!file) return;
    setParsing(true);
    setPreview(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await axios.post(`${API}/bills/parse`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(res.data);
      toast.success("Bill parsed — review below and confirm");
    } catch (e) {
      toast.error("Parse failed: " + (e.response?.data?.detail || e.message));
    } finally { setParsing(false); }
  };

  const confirmParsed = async () => {
    if (!preview) return;
    try {
      await axios.post(`${API}/bills/confirm`, {
        parsed: preview.parsed,
        apply_rate: applyRate,
      });
      toast.success(applyRate ? "Bill saved & rate updated" : "Bill saved");
      setPreview(null);
      load();
    } catch (e) {
      toast.error("Save failed: " + (e.response?.data?.detail || e.message));
    }
  };

  return (
    <div className="space-y-6" data-testid="bills-page">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-1">&gt; bill reconciliation</div>
        <h1 className="text-3xl font-semibold tracking-tight">Bills</h1>
      </div>

      {/* AI upload */}
      <Panel data-testid="bill-upload-panel">
        <PanelHeader label={
          <span className="flex items-center gap-2">
            <SparkleIcon size={12} weight="fill" className="text-blue-400" />
            Upload PDF · AI parse (Claude Haiku 4.5)
          </span>
        } />
        <div className="p-4">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }}
            onClick={() => inputRef.current?.click()}
            className={`border-2 border-dashed rounded-sm p-8 text-center cursor-pointer transition-colors ${
              dragOver ? "border-blue-500 bg-blue-500/5" : "border-zinc-800 hover:border-zinc-700"
            }`}
            data-testid="bill-dropzone"
          >
            <UploadIcon size={28} weight="thin" className="text-zinc-500 mx-auto mb-2" />
            <div className="text-sm text-zinc-300">
              {parsing ? "Parsing with Claude Haiku…" : "Drop utility bill PDF (or image)"}
            </div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mt-1">click to browse</div>
            <input ref={inputRef} type="file" accept="application/pdf,image/*"
              onChange={(e) => handleFile(e.target.files[0])} className="hidden" data-testid="bill-file-input" />
          </div>
        </div>

        {preview && (
          <div className="border-t border-zinc-800 p-4 space-y-4" data-testid="bill-preview">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500">extracted fields</div>
            <div className="grid grid-cols-4 gap-3 font-mono text-xs">
              <Kv label="utility" value={preview.parsed.utility_name} />
              <Kv label="account" value={preview.parsed.account_number} />
              <Kv label="rate schedule" value={preview.parsed.rate_schedule} />
              <Kv label="period" value={`${preview.parsed.billing_period_start || "—"} → ${preview.parsed.billing_period_end || "—"}`} />
              <Kv label="total kWh" value={preview.parsed.total_kwh} highlight />
              <Kv label="total $" value={preview.parsed.total_cost != null ? `$${preview.parsed.total_cost}` : null} highlight />
              <Kv label="effective $/kWh" value={preview.parsed.effective_rate_per_kwh != null ? `$${preview.parsed.effective_rate_per_kwh}` : null} highlight />
              <Kv label="days" value={preview.parsed.days_in_period} />
              <Kv label="prev reading" value={preview.parsed.previous_meter_reading} />
              <Kv label="curr reading" value={preview.parsed.current_meter_reading} />
              <Kv label="avg daily kWh" value={preview.parsed.average_daily_kwh} />
              <Kv label="avg daily $" value={preview.parsed.average_daily_cost != null ? `$${preview.parsed.average_daily_cost}` : null} />
              <Kv label="service address" value={preview.parsed.service_address} className="col-span-4" />
            </div>

            {preview.parsed.tier_breakdown?.length > 0 && (
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-2">tier breakdown</div>
                <div className="border border-zinc-800 rounded-sm overflow-hidden">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr className="text-[10px] uppercase tracking-widest text-zinc-500 border-b border-zinc-800 bg-zinc-900/50">
                        <th className="text-left px-3 py-1.5">tier</th>
                        <th className="text-right px-3 py-1.5">kWh</th>
                        <th className="text-right px-3 py-1.5">$/kWh</th>
                        <th className="text-right px-3 py-1.5">amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.parsed.tier_breakdown.map((t, i) => (
                        <tr key={i} className="border-b border-zinc-800/50">
                          <td className="px-3 py-1.5">{t.tier_name}</td>
                          <td className="text-right px-3 py-1.5">{t.kwh ?? "—"}</td>
                          <td className="text-right px-3 py-1.5">{t.rate_per_kwh ?? "—"}</td>
                          <td className="text-right px-3 py-1.5">{t.amount != null ? `$${t.amount}` : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {preview.parsed.line_items?.length > 0 && (
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-2">line items</div>
                <div className="border border-zinc-800 rounded-sm max-h-48 overflow-y-auto">
                  {preview.parsed.line_items.map((li, i) => (
                    <div key={i} className="flex justify-between px-3 py-1 border-b border-zinc-800/50 font-mono text-xs">
                      <span className="text-zinc-300">{li.description}</span>
                      <span className="text-zinc-100">${li.amount}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="border border-zinc-800 rounded-sm p-3 bg-zinc-900/40">
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-2">reconciliation vs your data</div>
              <div className="grid grid-cols-4 gap-3 font-mono text-xs">
                <Kv label="bill kWh" value={preview.parsed.total_kwh} />
                <Kv label="pipeline kWh" value={preview.computed_kwh} />
                <Kv label="Δ kWh"
                  value={preview.computed_kwh != null && preview.parsed.total_kwh != null
                    ? `${(preview.parsed.total_kwh - preview.computed_kwh).toFixed(1)}` : "—"} />
                <Kv label="current property rate" value={`$${preview.current_property_rate}/kWh`} />
              </div>
            </div>

            <div className="flex items-center justify-between pt-2">
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input type="checkbox" checked={applyRate} onChange={(e) => setApplyRate(e.target.checked)} data-testid="apply-rate-toggle" />
                Apply effective rate (${preview.parsed.effective_rate_per_kwh ?? "—"}/kWh) to property
              </label>
              <div className="flex gap-2">
                <button onClick={() => setPreview(null)} data-testid="cancel-preview"
                  className="border border-zinc-800 hover:bg-zinc-900 rounded-sm px-3 py-2 text-xs font-mono uppercase tracking-widest text-zinc-400 flex items-center gap-1.5">
                  <XCircleIcon size={12} /> Discard
                </button>
                <button onClick={confirmParsed} data-testid="confirm-parsed"
                  className="bg-white text-black hover:bg-zinc-200 rounded-sm px-3 py-2 text-xs font-mono uppercase tracking-widest flex items-center gap-1.5">
                  <CheckCircleIcon size={12} /> Confirm & save
                </button>
              </div>
            </div>
          </div>
        )}
      </Panel>

      {/* Manual form */}
      <Panel data-testid="bill-form-panel">
        <PanelHeader label="Add bill period manually" />
        <form onSubmit={submit} className="p-4 grid grid-cols-3 gap-3">
          <Field label="Period start"><input type="date" required value={form.start} onChange={(e) => setForm({...form, start: e.target.value})} className={inputCls} data-testid="bill-start" /></Field>
          <Field label="Period end"><input type="date" required value={form.end} onChange={(e) => setForm({...form, end: e.target.value})} className={inputCls} data-testid="bill-end" /></Field>
          <Field label="Rate ($/kWh)"><input type="number" step="0.001" value={form.rate_usd_per_kwh} onChange={(e) => setForm({...form, rate_usd_per_kwh: e.target.value})} className={inputCls} data-testid="bill-rate" /></Field>
          <Field label="Bill total (kWh)"><input type="number" step="0.01" value={form.total_kwh} onChange={(e) => setForm({...form, total_kwh: e.target.value})} className={inputCls} data-testid="bill-kwh" /></Field>
          <Field label="Bill total ($)"><input type="number" step="0.01" value={form.total_cost} onChange={(e) => setForm({...form, total_cost: e.target.value})} className={inputCls} data-testid="bill-cost" /></Field>
          <Field label="Notes"><input value={form.notes} onChange={(e) => setForm({...form, notes: e.target.value})} className={inputCls} data-testid="bill-notes" /></Field>
          <div className="col-span-3 flex justify-end">
            <button type="submit" data-testid="bill-submit"
              className="bg-white text-black hover:bg-zinc-200 rounded-sm px-4 py-2 text-sm font-medium flex items-center gap-2">
              <PlusIcon size={14} /> Reconcile
            </button>
          </div>
        </form>
      </Panel>

      {/* History */}
      <Panel data-testid="bills-list-panel">
        <PanelHeader label="History" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-mono">
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-2 px-4">period</th>
                <th className="text-right py-2 px-4">bill kWh</th>
                <th className="text-right py-2 px-4">bill $</th>
                <th className="text-right py-2 px-4">rate</th>
                <th className="text-right py-2 px-4">computed kWh</th>
                <th className="text-right py-2 px-4">computed $</th>
                <th className="text-right py-2 px-4">Δ kWh</th>
                <th className="text-right py-2 px-4">Δ $</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {bills.length === 0 && (<tr><td colSpan="9" className="p-6 text-center text-zinc-500">no bill periods yet</td></tr>)}
              {bills.map((b) => {
                const dKwh = (b.total_kwh || 0) - (b.computed_kwh || 0);
                const dCost = (b.total_cost || 0) - (b.computed_cost || 0);
                return (
                  <tr key={b.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30" data-testid={`bill-${b.id}`}>
                    <td className="py-2 px-4 text-zinc-200">{b.start?.slice(0, 10)} → {b.end?.slice(0, 10)}</td>
                    <td className="text-right py-2 px-4">{b.total_kwh ?? "—"}</td>
                    <td className="text-right py-2 px-4">${b.total_cost?.toFixed(2) ?? "—"}</td>
                    <td className="text-right py-2 px-4 text-blue-400">${b.rate_usd_per_kwh?.toFixed(4) ?? "—"}</td>
                    <td className="text-right py-2 px-4 text-zinc-400">{b.computed_kwh?.toFixed(2) ?? "—"}</td>
                    <td className="text-right py-2 px-4 text-zinc-400">${b.computed_cost?.toFixed(2) ?? "—"}</td>
                    <td className={`text-right py-2 px-4 ${Math.abs(dKwh) > 5 ? "text-amber-500" : "text-emerald-500"}`}>{dKwh >= 0 ? "+" : ""}{dKwh.toFixed(1)}</td>
                    <td className={`text-right py-2 px-4 ${Math.abs(dCost) > 5 ? "text-amber-500" : "text-emerald-500"}`}>{dCost >= 0 ? "+" : ""}${dCost.toFixed(2)}</td>
                    <td className="text-right py-2 px-4">
                      <button onClick={() => remove(b.id)} className="text-zinc-500 hover:text-red-500" data-testid={`bill-delete-${b.id}`}><TrashIcon size={14} /></button>
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

const inputCls = "w-full bg-zinc-950 border border-zinc-800 rounded-sm px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500 focus:border-zinc-500 font-mono";

function Field({ label, children }) {
  return (
    <label className="block">
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-1">{label}</div>
      {children}
    </label>
  );
}

function Kv({ label, value, highlight, className }) {
  return (
    <div className={className || ""}>
      <div className="text-zinc-500 uppercase text-[10px] tracking-widest mb-0.5">{label}</div>
      <div className={highlight ? "text-blue-400" : "text-zinc-100"}>
        {value != null && value !== "" ? String(value) : <span className="text-zinc-600">—</span>}
      </div>
    </div>
  );
}
