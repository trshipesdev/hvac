import React, { useState } from "react";
import { api } from "@/lib/apiClient";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Panel } from "@/components/Panel";
import { ArrowRight, Check, Leaf } from "lucide-react";

export default function Setup() {
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [property, setProperty] = useState({ name: "My Home", address: "", zip_code: "", noaa_station_id: "", rate_usd_per_kwh: 0.14 });
  const [unit1, setUnit1] = useState({ name: "Upstairs", floor: "Upstairs", tonnage: 2.5, color: "#4A6B53" });
  const [unit2, setUnit2] = useState({ name: "Downstairs", floor: "Downstairs", tonnage: 3.0, color: "#8FAB98" });
  const [stations, setStations] = useState([]);
  const [loading, setLoading] = useState(false);

  const searchStations = async () => {
    if (!property.zip_code) return;
    try {
      const res = await api.noaaStations(property.zip_code);
      setStations(res.data || []);
      if (!res.data?.length) toast.info("No stations found — enter one manually");
    } catch { toast.error("NOAA lookup failed"); }
  };

  const finish = async () => {
    setLoading(true);
    try {
      await api.updateProperty(property);
      await api.createUnit(unit1);
      await api.createUnit(unit2);
      toast.success("Setup complete — syncing data");
      await api.runPipeline(14);
      toast.success("Data pipeline complete");
      nav("/dashboard");
    } catch (e) { toast.error("Setup failed: " + (e.response?.data?.detail || e.message)); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-paper-100 paper-grid py-16 px-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-lg bg-forest-500 flex items-center justify-center">
            <Leaf className="text-white" size={20} strokeWidth={1.75} />
          </div>
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-forest-500">First-run setup</div>
            <div className="text-lg font-serif text-forest-900">Watt · Home</div>
          </div>
        </div>

        <h1 className="text-5xl font-serif tracking-tight text-forest-900 mb-3">Configure your property</h1>
        <p className="text-slate-600 mb-8 max-w-xl">Three quick steps to start attributing per-unit HVAC cost and flagging anomalies.</p>

        <div className="flex gap-2 mb-8">
          {[0, 1, 2].map((i) => (
            <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${i <= step ? "bg-forest-500" : "bg-paper-300"}`} />
          ))}
        </div>

        {step === 0 && (
          <Panel className="p-8" data-testid="setup-step-property">
            <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-forest-500 mb-5">step 01 · property</div>
            <div className="grid grid-cols-2 gap-5">
              <Field label="Property name"><input className={inputCls} value={property.name} onChange={(e) => setProperty({...property, name: e.target.value})} data-testid="prop-name" /></Field>
              <Field label="Rate ($/kWh)"><input type="number" step="0.001" className={inputCls} value={property.rate_usd_per_kwh} onChange={(e) => setProperty({...property, rate_usd_per_kwh: parseFloat(e.target.value)})} data-testid="prop-rate" /></Field>
              <Field label="Address" className="col-span-2"><input className={inputCls} value={property.address} onChange={(e) => setProperty({...property, address: e.target.value})} data-testid="prop-address" /></Field>
              <Field label="ZIP code">
                <div className="flex gap-2">
                  <input className={inputCls} value={property.zip_code} onChange={(e) => setProperty({...property, zip_code: e.target.value})} data-testid="prop-zip" />
                  <button onClick={searchStations} className={btnSecondaryCls} data-testid="find-stations">Find</button>
                </div>
              </Field>
              <Field label="NOAA station ID"><input className={inputCls} value={property.noaa_station_id} placeholder="GHCND:USW00…" onChange={(e) => setProperty({...property, noaa_station_id: e.target.value})} data-testid="prop-station" /></Field>
            </div>
            {stations.length > 0 && (
              <div className="mt-5 border border-paper-300 rounded-lg bg-paper-50">
                <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-forest-500 px-4 py-2 border-b border-paper-300">Nearby stations</div>
                <div className="max-h-40 overflow-y-auto">
                  {stations.map((s) => (
                    <button key={s.id} onClick={() => setProperty({...property, noaa_station_id: s.id})}
                      className="w-full text-left px-4 py-2 text-xs font-mono hover:bg-white border-b border-paper-200 last:border-0"
                      data-testid={`station-${s.id}`}>{s.id} — {s.name}</button>
                  ))}
                </div>
              </div>
            )}
            <div className="flex justify-end mt-8">
              <button onClick={() => setStep(1)} className={btnPrimaryCls} data-testid="next-1">Next <ArrowRight size={14} strokeWidth={1.75} /></button>
            </div>
          </Panel>
        )}

        {step === 1 && (
          <Panel className="p-8" data-testid="setup-step-units">
            <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-forest-500 mb-5">step 02 · define units</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <UnitCard unit={unit1} setUnit={setUnit1} testId="unit-1" />
              <UnitCard unit={unit2} setUnit={setUnit2} testId="unit-2" />
            </div>
            <div className="flex justify-between mt-8">
              <button onClick={() => setStep(0)} className={btnSecondaryCls}>Back</button>
              <button onClick={() => setStep(2)} className={btnPrimaryCls} data-testid="next-2">Next <ArrowRight size={14} strokeWidth={1.75} /></button>
            </div>
          </Panel>
        )}

        {step === 2 && (
          <Panel className="p-8" data-testid="setup-step-confirm">
            <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-forest-500 mb-5">step 03 · confirm & sync</div>
            <p className="text-sm text-slate-600 mb-5">We'll seed 14 days of mock thermostat data (Resideo is mocked pending developer approval) and pull weather.</p>
            <div className="grid grid-cols-2 gap-3 border border-paper-300 rounded-lg p-5 mb-6 bg-paper-50 text-sm">
              <div className="text-slate-500">Property</div><div className="text-forest-800 font-medium">{property.name}</div>
              <div className="text-slate-500">Rate</div><div className="text-forest-800 font-mono">${property.rate_usd_per_kwh}/kWh</div>
              <div className="text-slate-500">NOAA station</div><div className="text-forest-800 font-mono text-xs">{property.noaa_station_id || "—"}</div>
              <div className="text-slate-500">Unit 1</div><div className="text-forest-800">{unit1.name} · {unit1.tonnage}t</div>
              <div className="text-slate-500">Unit 2</div><div className="text-forest-800">{unit2.name} · {unit2.tonnage}t</div>
            </div>
            <div className="flex justify-between">
              <button onClick={() => setStep(1)} className={btnSecondaryCls}>Back</button>
              <button onClick={finish} disabled={loading} className={btnPrimaryCls} data-testid="finish-setup">
                {loading ? "Syncing…" : "Finish & Sync"} <Check size={14} strokeWidth={1.75} />
              </button>
            </div>
          </Panel>
        )}
      </div>
    </div>
  );
}

const inputCls = "w-full bg-white border border-paper-300 rounded-lg px-3 py-2 text-sm text-forest-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-forest-500/30 focus:border-forest-500 transition-all";
const btnPrimaryCls = "bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-4 py-2.5 text-sm font-medium flex items-center gap-2 transition-colors";
const btnSecondaryCls = "bg-white border border-paper-300 hover:bg-paper-200 text-forest-700 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors";

function Field({ label, children, className }) {
  return (
    <label className={`block ${className || ""}`}>
      <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-1.5">{label}</div>
      {children}
    </label>
  );
}

function UnitCard({ unit, setUnit, testId }) {
  return (
    <div className="border border-paper-300 rounded-lg p-5 space-y-3 bg-paper-50" data-testid={testId}>
      <div className="flex items-center gap-2">
        <div className="w-3 h-3 rounded-full" style={{ background: unit.color }} />
        <input className={inputCls} value={unit.name} onChange={(e) => setUnit({...unit, name: e.target.value})} />
      </div>
      <Field label="Floor"><input className={inputCls} value={unit.floor} onChange={(e) => setUnit({...unit, floor: e.target.value})} /></Field>
      <Field label="Tonnage"><input type="number" step="0.5" className={inputCls} value={unit.tonnage} onChange={(e) => setUnit({...unit, tonnage: parseFloat(e.target.value)})} /></Field>
      <Field label="Color"><input type="color" className="w-full h-10 bg-white border border-paper-300 rounded-lg cursor-pointer" value={unit.color} onChange={(e) => setUnit({...unit, color: e.target.value})} /></Field>
    </div>
  );
}
