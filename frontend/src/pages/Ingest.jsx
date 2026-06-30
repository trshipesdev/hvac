import React, { useState, useRef } from "react";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader } from "@/components/Panel";
import { toast } from "sonner";
import { UploadIcon, FileArrowDownIcon, CloudArrowDownIcon, ArrowClockwiseIcon } from "@phosphor-icons/react";

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
    } catch (e) {
      toast.error("Upload failed: " + (e.response?.data?.detail || e.message));
    } finally { setUploading(false); }
  };

  const downloadSample = async () => {
    try {
      const blob = await api.downloadSampleXml();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "sample-green-button.xml";
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Download failed"); }
  };

  const syncNOAA = async () => {
    toast.info("Fetching NOAA weather…");
    try {
      const res = await api.ingestNoaa(30);
      toast.success(`NOAA: ${res.data.inserted} rows (${res.data.source})`);
    } catch (e) { toast.error(e.response?.data?.detail || "NOAA failed"); }
  };

  const syncResideo = async () => {
    toast.info("Syncing thermostats…");
    try {
      const res = await api.resideoSync(30);
      toast.success(`Resideo: ${res.data.inserted} readings`);
    } catch (e) { toast.error(e.response?.data?.detail || "Resideo failed"); }
  };

  return (
    <div className="space-y-6" data-testid="ingest-page">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-1">&gt; data ingestion</div>
        <h1 className="text-3xl font-semibold tracking-tight">Ingest</h1>
      </div>

      <Panel data-testid="green-button-panel">
        <PanelHeader label="Green Button XML" action={
          <button onClick={downloadSample} className="font-mono text-[10px] uppercase tracking-[0.2em] text-blue-400 hover:text-blue-300 flex items-center gap-1" data-testid="download-sample">
            <FileArrowDownIcon size={12} /> download sample
          </button>
        } />
        <div className="p-6">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault(); setDragOver(false);
              const f = e.dataTransfer.files[0];
              handleFile(f);
            }}
            onClick={() => inputRef.current?.click()}
            className={`border-2 border-dashed rounded-sm p-12 text-center cursor-pointer transition-colors ${
              dragOver ? "border-blue-500 bg-blue-500/5" : "border-zinc-800 hover:border-zinc-700"
            }`}
            data-testid="dropzone"
          >
            <UploadIcon size={32} weight="thin" className="text-zinc-500 mx-auto mb-3" />
            <div className="text-sm text-zinc-300 mb-1">{uploading ? "Uploading…" : "Drop Green Button XML here"}</div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500">or click to browse</div>
            <input
              ref={inputRef}
              type="file"
              accept=".xml"
              onChange={(e) => handleFile(e.target.files[0])}
              className="hidden"
              data-testid="file-input"
            />
          </div>
          {result && (
            <div className="mt-4 border border-zinc-800 rounded-sm p-3 font-mono text-xs" data-testid="ingest-result">
              <div className="grid grid-cols-4 gap-3">
                <div><div className="text-zinc-500 uppercase text-[10px] tracking-widest">inserted</div><div className="text-emerald-500">{result.inserted}</div></div>
                <div><div className="text-zinc-500 uppercase text-[10px] tracking-widest">skipped</div><div className="text-amber-500">{result.skipped}</div></div>
                <div><div className="text-zinc-500 uppercase text-[10px] tracking-widest">range start</div><div className="text-zinc-200">{result.range_start?.slice(0, 16)}</div></div>
                <div><div className="text-zinc-500 uppercase text-[10px] tracking-widest">range end</div><div className="text-zinc-200">{result.range_end?.slice(0, 16)}</div></div>
              </div>
            </div>
          )}
        </div>
      </Panel>

      <div className="grid grid-cols-2 gap-4">
        <Panel data-testid="noaa-panel">
          <PanelHeader label="NOAA Weather" />
          <div className="p-6">
            <p className="text-sm text-zinc-400 mb-4">
              Pull 30 days of outdoor temperature from your configured NOAA station.
              If NOAA fails, synthetic hourly weather is used as fallback.
            </p>
            <button onClick={syncNOAA} className="bg-white text-black hover:bg-zinc-200 rounded-sm px-4 py-2 text-sm font-medium flex items-center gap-2" data-testid="noaa-sync">
              <CloudArrowDownIcon size={14} /> Sync NOAA
            </button>
          </div>
        </Panel>

        <Panel data-testid="resideo-panel">
          <PanelHeader label="Resideo Thermostats" />
          <div className="p-6">
            <p className="text-sm text-zinc-400 mb-4">
              Poll thermostat runtime + setpoint. Currently in <span className="text-amber-500 font-mono">MOCK MODE</span> — Resideo dev approval pending.
            </p>
            <button onClick={syncResideo} className="bg-white text-black hover:bg-zinc-200 rounded-sm px-4 py-2 text-sm font-medium flex items-center gap-2" data-testid="resideo-sync">
              <ArrowClockwiseIcon size={14} /> Sync Thermostats
            </button>
          </div>
        </Panel>
      </div>
    </div>
  );
}
