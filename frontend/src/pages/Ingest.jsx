import React, { useState, useRef } from "react";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader } from "@/components/Panel";
import { toast } from "sonner";
import { Upload, Download, Cloud, RefreshCw } from "lucide-react";

export default function Ingest() {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const inputRef = useRef();

  const handleFile = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const res = await api.uploadGreenButton(file);
      setResult(res.data);
      toast.success(`Ingested ${res.data.inserted} intervals`);
      await api.runAttribution(30);
      await api.runAnomalies(30);
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
    toast.info("Fetching NOAA weather…");
    try { const r = await api.ingestNoaa(30); toast.success(`NOAA: ${r.data.inserted} rows (${r.data.source})`); }
    catch (e) { toast.error(e.response?.data?.detail || "NOAA failed"); }
  };

  const syncResideo = async () => {
    toast.info("Syncing thermostats…");
    try { const r = await api.resideoSync(30); toast.success(`Resideo: ${r.data.inserted} readings`); }
    catch (e) { toast.error(e.response?.data?.detail || "Resideo failed"); }
  };

  return (
    <div className="space-y-8 animate-fade-in" data-testid="ingest-page">
      <div>
        <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">data ingestion</div>
        <h1 className="text-4xl font-serif tracking-tight text-forest-900">Ingest</h1>
        <p className="text-sm text-slate-600 mt-1.5 max-w-xl">Upload utility data, sync weather, and pull thermostat readings.</p>
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
            <div className="text-base text-forest-800 mb-1 font-medium">{uploading ? "Uploading…" : "Drop your Green Button XML here"}</div>
            <div className="text-xs text-slate-500">or click to browse — accepts .xml from Dominion, Duke, ConEd, etc.</div>
            <input ref={inputRef} type="file" accept=".xml" onChange={(e) => handleFile(e.target.files[0])} className="hidden" data-testid="file-input" />
          </div>
          {result && (
            <div className="mt-5 border border-paper-300 rounded-lg p-4 grid grid-cols-4 gap-4 bg-paper-50" data-testid="ingest-result">
              <StatCol label="Inserted" value={result.inserted} tone="energy" />
              <StatCol label="Skipped" value={result.skipped} tone="warning" />
              <StatCol label="Range start" value={result.range_start?.slice(0, 10)} />
              <StatCol label="Range end" value={result.range_end?.slice(0, 10)} />
            </div>
          )}
        </div>
      </Panel>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <Panel data-testid="noaa-panel" className="card-hover">
          <PanelHeader label="NOAA Weather" />
          <div className="p-6 space-y-4">
            <p className="text-sm text-slate-600 leading-relaxed">Pull outdoor temperature from your configured NOAA station. Synthetic hourly weather is used as fallback.</p>
            <button onClick={syncNOAA} className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-4 py-2.5 text-sm font-medium flex items-center gap-2 transition-colors" data-testid="noaa-sync">
              <Cloud size={15} strokeWidth={1.75} /> Sync 30 days
            </button>
          </div>
        </Panel>

        <Panel data-testid="resideo-panel" className="card-hover">
          <PanelHeader label="Resideo Thermostats"
            action={<span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-widest bg-amber-50 text-amber-800 border border-amber-300"><span className="w-1 h-1 rounded-full bg-current" />Mock</span>} />
          <div className="p-6 space-y-4">
            <p className="text-sm text-slate-600 leading-relaxed">Poll per-unit runtime + setpoint. Currently mocked — Resideo developer approval pending.</p>
            <button onClick={syncResideo} className="bg-white border border-paper-300 hover:bg-paper-200 text-forest-700 rounded-lg px-4 py-2.5 text-sm font-medium flex items-center gap-2 transition-colors" data-testid="resideo-sync">
              <RefreshCw size={15} strokeWidth={1.75} /> Sync 30 days
            </button>
          </div>
        </Panel>
      </div>
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
