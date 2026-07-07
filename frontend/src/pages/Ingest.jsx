import React, { useState, useRef, useEffect } from "react";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader, Kv } from "@/components/Panel";
import { toast } from "sonner";
import { Upload, Download, Cloud, RefreshCw, Sparkles, Check, X, Files, Thermometer, AlertTriangle } from "lucide-react";
import { Link } from "react-router-dom";
import { fmtDateOnly } from "@/lib/time";

export default function Ingest() {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [property, setProperty] = useState(null);
  const inputRef = useRef();

  const [billDragOver, setBillDragOver] = useState(false);
  const [billParsing, setBillParsing] = useState(false);
  const [billPreview, setBillPreview] = useState(null);
  const [applyRate, setApplyRate] = useState(true);
  const [billBulkResults, setBillBulkResults] = useState(null);
  const [billBulkBusy, setBillBulkBusy] = useState(false);
  const billInputRef = useRef();
  const billBulkRef = useRef();

  const [zoneBulkResults, setZoneBulkResults] = useState(null);
  const [zoneBulkBusy, setZoneBulkBusy] = useState(false);
  const zoneBulkRef = useRef();

  const [coverage, setCoverage] = useState(null);
  const [backfilling, setBackfilling] = useState(false);
  const loadCoverage = async () => {
    try { const r = await api.getCoverage(); setCoverage(r.data); } catch { toast.error("Couldn't load coverage — backend may be unreachable"); }
  };
  useEffect(() => {
    loadCoverage();
    (async () => { try { const r = await api.getProperty(); setProperty(r.data); } catch { /* non-fatal */ } })();
  }, []);

  const backfillAll = async () => {
    setBackfilling(true);
    toast.info("Processing your full upload history — this can take a moment for a year of data…");
    try {
      const r = await api.backfillAll();
      toast.success(`Backfilled ${r.data.attribution.attributed} intervals and found ${r.data.anomalies.anomalies} anomalies across your full history`);
      loadCoverage();
    } catch (e) { toast.error("Backfill failed: " + (e.response?.data?.detail || e.message)); }
    finally { setBackfilling(false); }
  };

  const handleFile = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const res = await api.uploadGreenButton(file);
      setResult(res.data);
      toast.success(`Ingested ${res.data.inserted} intervals`);
      await api.runAttribution(30);
      await api.runAnomalies(30);
      loadCoverage();
    } catch (e) { toast.error("Upload failed: " + (e.response?.data?.detail || e.message)); }
    finally { setUploading(false); }
  };

  const downloadSample = async () => {
    try {
      const blob = await api.downloadSampleXml();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "sample-green-button.xml"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Download failed"); }
  };

  const syncNOAA = async () => {
    toast.info("Fetching weather…");
    try { const r = await api.ingestNoaa(30); toast.success(`Weather: ${r.data.inserted} rows (${r.data.source})`); }
    catch (e) { toast.error(e.response?.data?.detail || "Weather sync failed"); }
  };

  const syncResideo = async () => {
    toast.info("Syncing thermostats…");
    try { const r = await api.resideoSync(30); toast.success(`Resideo: ${r.data.inserted} readings`); }
    catch (e) { toast.error(e.response?.data?.detail || "Resideo failed"); }
  };

  const parseBill = async (file) => {
    if (!file) return;
    setBillParsing(true);
    setBillPreview(null);
    try {
      const res = await api.parseBill(file);
      setBillPreview(res.data);
    } catch (e) { toast.error("Parse failed: " + (e.response?.data?.detail || e.message)); }
    finally { setBillParsing(false); }
  };

  const confirmBill = async () => {
    if (!billPreview) return;
    try {
      await api.confirmBill(billPreview.parsed, applyRate);
      toast.success("Bill reconciled");
      setBillPreview(null);
      loadCoverage();
    } catch (e) { toast.error("Confirm failed: " + (e.response?.data?.detail || e.message)); }
  };

  const bulkUploadBills = async (files) => {
    if (!files?.length) return;
    setBillBulkBusy(true);
    setBillBulkResults(null);
    try {
      const r = await api.bulkParseBills(Array.from(files));
      setBillBulkResults(r.data.results);
      const ok = r.data.results.filter((x) => x.ok).length;
      toast.success(`${ok}/${r.data.count} bills parsed`);
      loadCoverage();
    } catch (e) { toast.error("Bulk upload failed: " + (e.response?.data?.detail || e.message)); }
    finally { setBillBulkBusy(false); }
  };

  const bulkUploadZoneReports = async (files) => {
    if (!files?.length) return;
    setZoneBulkBusy(true);
    setZoneBulkResults(null);
    try {
      const r = await api.bulkParseHoneywellReports(Array.from(files));
      setZoneBulkResults(r.data.results);
      const ok = r.data.results.filter((x) => x.ok).length;
      toast.success(`${ok}/${r.data.count} zone reports parsed`);
      loadCoverage();
    } catch (e) { toast.error("Bulk upload failed: " + (e.response?.data?.detail || e.message)); }
    finally { setZoneBulkBusy(false); }
  };

  return (
    <div className="space-y-8 animate-fade-in" data-testid="ingest-page">
      <div>
        <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">data ingestion</div>
        <h1 className="text-4xl font-serif tracking-tight text-forest-900">Ingest</h1>
        <p className="text-sm text-slate-600 mt-1.5 max-w-xl">Upload utility data, bills, and thermostat zone reports — everything real feeds the same pipeline.</p>
      </div>

      <Panel data-testid="green-button-panel">
        <PanelHeader label="Green Button XML"
          action={<button onClick={downloadSample} className="text-[10px] font-medium uppercase tracking-[0.15em] text-forest-500 hover:text-forest-700 flex items-center gap-1" data-testid="download-sample"><Download size={11} strokeWidth={1.75} /> Sample</button>} />
        <div className="p-6">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }}
            onClick={() => inputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-14 text-center cursor-pointer transition-all ${
              dragOver ? "border-forest-500 bg-forest-50" : "border-paper-300 hover:border-forest-300 hover:bg-paper-100"
            }`}
            data-testid="dropzone"
          >
            <div className="w-14 h-14 rounded-full bg-paper-200 flex items-center justify-center mx-auto mb-4">
              <Upload size={22} strokeWidth={1.5} className="text-forest-600" />
            </div>
            <div className="text-base text-forest-800 mb-1 font-medium">{uploading ? "Uploading… (large files can take a moment)" : "Drop your Green Button XML here"}</div>
            <div className="text-xs text-slate-500">or click to browse — accepts .xml from Dominion, Duke, ConEd, etc.</div>
            <input ref={inputRef} type="file" accept=".xml" onChange={(e) => handleFile(e.target.files[0])} className="hidden" data-testid="file-input" />
          </div>
          {result && (
            <div className="mt-5 border border-paper-300 rounded-lg p-4 grid grid-cols-4 gap-4 bg-paper-50" data-testid="ingest-result">
              <StatCol label="Inserted" value={result.inserted} tone="energy" />
              <StatCol label="Skipped" value={result.skipped} tone="warning" />
              <StatCol label="Range start" value={fmtDateOnly(result.range_start, property)} />
              <StatCol label="Range end" value={fmtDateOnly(result.range_end, property)} />
            </div>
          )}
        </div>
      </Panel>

      <Panel data-testid="bill-upload-panel">
        <PanelHeader label="Utility Bills · AI parse (Claude Haiku 4.5)" />
        <div className="p-6 space-y-5">
          <div
            onDragOver={(e) => { e.preventDefault(); setBillDragOver(true); }}
            onDragLeave={() => setBillDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setBillDragOver(false); parseBill(e.dataTransfer.files[0]); }}
            onClick={() => billInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all ${
              billDragOver ? "border-forest-500 bg-forest-50" : "border-paper-300 hover:border-forest-300 hover:bg-paper-100"
            }`}
            data-testid="bill-dropzone"
          >
            <Sparkles size={20} strokeWidth={1.5} className="text-forest-600 mx-auto mb-3" />
            <div className="text-sm text-forest-800 font-medium">{billParsing ? "Parsing with Claude Haiku…" : "Drop one bill PDF/image here"}</div>
            <div className="text-xs text-slate-500 mt-1">Any US utility — universal AI extraction, no template needed</div>
            <input ref={billInputRef} type="file" accept=".pdf,image/*" onChange={(e) => parseBill(e.target.files[0])} className="hidden" data-testid="bill-file-input" />
          </div>

          {billPreview && (
            <div className="border border-paper-300 rounded-lg p-5 bg-paper-50 space-y-4" data-testid="bill-preview">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Kv label="Utility" value={billPreview.parsed.utility_name} />
                <Kv label="Period" value={`${billPreview.parsed.billing_period_start} → ${billPreview.parsed.billing_period_end}`} />
                <Kv label="Total kWh" value={billPreview.parsed.total_kwh} />
                <Kv label="Total cost" value={billPreview.parsed.total_cost != null ? `$${billPreview.parsed.total_cost}` : null} />
                <Kv label="Effective rate" value={billPreview.parsed.effective_rate_per_kwh != null ? `$${billPreview.parsed.effective_rate_per_kwh}/kWh` : null} />
                <Kv label="Computed kWh (pipeline)" value={billPreview.computed_kwh} />
                <Kv label="Computed cost (pipeline)" value={billPreview.computed_cost != null ? `$${billPreview.computed_cost}` : null} highlight />
                <Kv label="Current property rate" value={`$${billPreview.current_property_rate}/kWh`} />
              </div>
              <label className="flex items-center gap-2 text-sm text-forest-800 cursor-pointer">
                <input type="checkbox" checked={applyRate} onChange={(e) => setApplyRate(e.target.checked)} className="accent-forest-500 w-4 h-4" />
                Apply this bill's rate to the property going forward
              </label>
              <div className="flex gap-2">
                <button onClick={confirmBill} className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-4 py-2.5 text-sm font-medium flex items-center gap-2 transition-colors" data-testid="bill-confirm">
                  <Check size={14} strokeWidth={1.75} /> Reconcile this bill
                </button>
                <button onClick={() => setBillPreview(null)} className="bg-white border border-paper-300 hover:bg-paper-200 text-forest-700 rounded-lg px-4 py-2.5 text-sm font-medium flex items-center gap-2 transition-colors">
                  <X size={14} strokeWidth={1.75} /> Discard
                </button>
              </div>
            </div>
          )}

          <div className="border-t border-paper-200 pt-5">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs font-medium uppercase tracking-[0.15em] text-slate-500">Bulk upload (up to 13 at once)</div>
              <button onClick={() => billBulkRef.current?.click()} disabled={billBulkBusy}
                className="bg-white border border-paper-300 hover:bg-paper-200 text-forest-700 rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 transition-colors" data-testid="bill-bulk-btn">
                <Files size={13} strokeWidth={1.75} /> {billBulkBusy ? "Uploading…" : "Choose files"}
              </button>
              <input ref={billBulkRef} type="file" multiple accept=".pdf,image/*" className="hidden"
                onChange={(e) => bulkUploadBills(e.target.files)} data-testid="bill-bulk-input" />
            </div>
            {billBulkResults && (
              <div className="border border-paper-300 rounded-lg divide-y divide-paper-200 max-h-64 overflow-y-auto">
                {billBulkResults.map((r, i) => (
                  <div key={i} className="px-4 py-2.5 flex items-center gap-3 text-sm">
                    {r.ok ? <Check size={14} strokeWidth={1.75} className="text-energy-600 shrink-0" /> : <X size={14} strokeWidth={1.75} className="text-red-600 shrink-0" />}
                    <span className="font-mono text-xs text-slate-500 truncate flex-1">{r.filename}</span>
                    {r.ok ? (
                      <span className="text-xs text-slate-500">{r.utility} · {r.period} · {r.total_kwh} kWh</span>
                    ) : (
                      <span className="text-xs text-red-600 truncate">{r.error}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </Panel>

      <Panel data-testid="zone-report-upload-panel">
        <PanelHeader label={<span className="flex items-center gap-2"><Thermometer size={13} strokeWidth={1.75} /> Thermostat Zone Reports · AI parse</span>}
          action={<Link to="/honeywell" className="text-[10px] font-medium uppercase tracking-[0.15em] text-forest-500 hover:text-forest-700">view stored zones →</Link>} />
        <div className="p-6 space-y-4">
          <p className="text-sm text-slate-600 leading-relaxed">Upload monthly "Your &lt;Month&gt; Energy Report" emails (any vendor, any zone names) — a real workaround until live Resideo sync is available.</p>
          <div className="flex items-center gap-2">
            <button onClick={() => zoneBulkRef.current?.click()} disabled={zoneBulkBusy}
              className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-4 py-2.5 text-sm font-medium flex items-center gap-2 transition-colors" data-testid="zone-bulk-btn">
              <Files size={14} strokeWidth={1.75} /> {zoneBulkBusy ? "Uploading…" : "Bulk upload reports"}
            </button>
            <input ref={zoneBulkRef} type="file" multiple accept=".pdf,image/*" className="hidden"
              onChange={(e) => bulkUploadZoneReports(e.target.files)} data-testid="zone-bulk-input" />
          </div>
          {zoneBulkResults && (
            <div className="border border-paper-300 rounded-lg divide-y divide-paper-200 max-h-64 overflow-y-auto">
              {zoneBulkResults.map((r, i) => (
                <div key={i} className="px-4 py-2.5 flex items-center gap-3 text-sm">
                  {r.ok ? <Check size={14} strokeWidth={1.75} className="text-energy-600 shrink-0" /> : <X size={14} strokeWidth={1.75} className="text-red-600 shrink-0" />}
                  <span className="font-mono text-xs text-slate-500 truncate flex-1">{r.filename}</span>
                  {r.ok ? (
                    <span className="text-xs text-slate-500">{r.zones_processed} zone-periods</span>
                  ) : (
                    <span className="text-xs text-red-600 truncate">{r.error}</span>
                  )}
                  {r.ok && r.unmatched_zones?.length > 0 && (
                    <span className="text-[10px] uppercase tracking-widest text-amber-600 flex items-center gap-1"><AlertTriangle size={11} strokeWidth={1.75} /> needs assignment</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </Panel>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <Panel data-testid="noaa-panel" className="card-hover">
          <PanelHeader label="Weather" />
          <div className="p-6 space-y-4">
            <p className="text-sm text-slate-600 leading-relaxed">Pull real hourly outdoor temperature for your property's coordinates.</p>
            <button onClick={syncNOAA} className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-4 py-2.5 text-sm font-medium flex items-center gap-2 transition-colors" data-testid="noaa-sync">
              <Cloud size={15} strokeWidth={1.75} /> Sync 30 days
            </button>
          </div>
        </Panel>

        <Panel data-testid="resideo-panel" className="card-hover">
          <PanelHeader label="Resideo Thermostats"
            action={<span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-widest bg-amber-50 text-amber-800 border border-amber-300"><span className="w-1 h-1 rounded-full bg-current" />Mock</span>} />
          <div className="p-6 space-y-4">
            <p className="text-sm text-slate-600 leading-relaxed">Poll per-unit runtime + setpoint. Currently mock/estimated — Resideo developer approval pending.</p>
            <button onClick={syncResideo} className="bg-white border border-paper-300 hover:bg-paper-200 text-forest-700 rounded-lg px-4 py-2.5 text-sm font-medium flex items-center gap-2 transition-colors" data-testid="resideo-sync">
              <RefreshCw size={15} strokeWidth={1.75} /> Sync 30 days
            </button>
          </div>
        </Panel>
      </div>

      <Panel data-testid="coverage-panel">
        <PanelHeader label="Data coverage"
          action={<button onClick={backfillAll} disabled={backfilling}
            className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5 transition-colors" data-testid="backfill-all-btn">
            <RefreshCw size={13} strokeWidth={1.75} /> {backfilling ? "Processing…" : "Backfill full history"}
          </button>} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 border-b border-paper-300">
                <th className="text-left py-3 px-6">Month</th>
                <th className="text-right py-3 px-4">Green Button intervals</th>
                <th className="text-center py-3 px-4">Bill</th>
                <th className="text-right py-3 px-4">Zone reports</th>
                <th className="px-4"></th>
              </tr>
            </thead>
            <tbody>
              {!coverage && <tr><td colSpan="5" className="p-10 text-center text-slate-500">Loading…</td></tr>}
              {coverage && coverage.months.length === 0 && <tr><td colSpan="5" className="p-10 text-center text-slate-500">No data uploaded yet.</td></tr>}
              {coverage?.months.map((m) => (
                <tr key={m.month} className={`border-b border-paper-200 ${m.gap ? "bg-amber-50/50" : ""}`} data-testid={`coverage-${m.month}`}>
                  <td className="py-3 px-6 text-forest-800 font-mono">{m.month}</td>
                  <td className="text-right py-3 px-4 font-mono text-slate-500">{m.green_button_intervals}</td>
                  <td className="text-center py-3 px-4">{m.has_bill ? <Check size={14} strokeWidth={1.75} className="text-energy-600 inline" /> : <span className="text-slate-300">—</span>}</td>
                  <td className="text-right py-3 px-4 font-mono text-slate-500">{m.zone_reports}</td>
                  <td className="text-right py-3 px-4">{m.gap && <span className="text-[10px] uppercase tracking-widest text-amber-600">gap</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function StatCol({ label, value, tone }) {
  const cls = tone === "energy" ? "text-energy-600" : tone === "warning" ? "text-amber-600" : "text-forest-800";
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-1">{label}</div>
      <div className={`font-mono text-lg ${cls}`}>{value}</div>
    </div>
  );
}
