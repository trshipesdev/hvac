import React, { useEffect, useState } from "react";
import { api } from "@/lib/apiClient";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Panel } from "@/components/Panel";
import { ArrowRightIcon, CheckCircleIcon } from "@phosphor-icons/react";

export default function Setup() {
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [property, setProperty] = useState({
    name: "My Home",
    address: "",
    zip_code: "",
    noaa_station_id: "",
    rate_usd_per_kwh: 0.14,
  });
  const [unit1, setUnit1] = useState({ name: "Upstairs", floor: "Upstairs", tonnage: 2.5, color: "#3b82f6" });
  const [unit2, setUnit2] = useState({ name: "Downstairs", floor: "Downstairs", tonnage: 3.0, color: "#8b5cf6" });
  const [stations, setStations] = useState([]);
  const [loading, setLoading] = useState(false);

  const searchStations = async () => {
    if (!property.zip_code) return;
    try {
      const res = await api.noaaStations(property.zip_code);
      setStations(res.data || []);
      if (!res.data?.length) toast.info("No stations found — you can enter one manually");
    } catch {
      toast.error("NOAA lookup failed");
    }
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
    } catch (e) {
      toast.error("Setup failed: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 grid-lines-bg py-12 px-6">
      <div className="max-w-2xl mx-auto">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-2">
          &gt; first-run setup
        </div>
        <h1 className="text-3xl font-semibold tracking-tight mb-2">Configure your property</h1>
        <p className="text-sm text-zinc-500 mb-8">3 quick steps to get the analyzer running.</p>

        {/* Step indicator */}
        <div className="flex gap-2 mb-6">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-sm ${i <= step ? "bg-blue-500" : "bg-zinc-800"}`}
            />
          ))}
        </div>

        {step === 0 && (
          <Panel className="p-6" data-testid="setup-step-property">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-4">
              step 01 · property
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Property name">
                <input className={inputCls} value={property.name} onChange={(e) => setProperty({...property, name: e.target.value})} data-testid="prop-name" />
              </Field>
              <Field label="Rate ($/kWh)">
                <input type="number" step="0.001" className={inputCls} value={property.rate_usd_per_kwh}
                  onChange={(e) => setProperty({...property, rate_usd_per_kwh: parseFloat(e.target.value)})} data-testid="prop-rate" />
              </Field>
              <Field label="Address" className="col-span-2">
                <input className={inputCls} value={property.address}
                  onChange={(e) => setProperty({...property, address: e.target.value})} data-testid="prop-address" />
              </Field>
              <Field label="ZIP code">
                <div className="flex gap-2">
                  <input className={inputCls} value={property.zip_code}
                    onChange={(e) => setProperty({...property, zip_code: e.target.value})} data-testid="prop-zip" />
                  <button onClick={searchStations} className={btnSecondaryCls} data-testid="find-stations">Find</button>
                </div>
              </Field>
              <Field label="NOAA station ID">
                <input className={inputCls} value={property.noaa_station_id}
                  placeholder="GHCND:USW00..."
                  onChange={(e) => setProperty({...property, noaa_station_id: e.target.value})} data-testid="prop-station" />
              </Field>
            </div>
            {stations.length > 0 && (
              <div className="mt-4 border border-zinc-800 rounded-sm">
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 px-3 py-2 border-b border-zinc-800">
                  nearby stations
                </div>
                <div className="max-h-40 overflow-y-auto">
                  {stations.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setProperty({...property, noaa_station_id: s.id})}
                      className="w-full text-left px-3 py-2 text-xs font-mono hover:bg-zinc-800/50 border-b border-zinc-800/50"
                      data-testid={`station-${s.id}`}
                    >
                      {s.id} — {s.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="flex justify-end mt-6">
              <button onClick={() => setStep(1)} className={btnPrimaryCls} data-testid="next-1">
                Next <ArrowRightIcon size={14} />
              </button>
            </div>
          </Panel>
        )}

        {step === 1 && (
          <Panel className="p-6" data-testid="setup-step-units">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-4">
              step 02 · define units
            </div>
            <div className="grid grid-cols-2 gap-4">
              <UnitCard unit={unit1} setUnit={setUnit1} testId="unit-1" />
              <UnitCard unit={unit2} setUnit={setUnit2} testId="unit-2" />
            </div>
            <div className="flex justify-between mt-6">
              <button onClick={() => setStep(0)} className={btnSecondaryCls}>Back</button>
              <button onClick={() => setStep(2)} className={btnPrimaryCls} data-testid="next-2">
                Next <ArrowRightIcon size={14} />
              </button>
            </div>
          </Panel>
        )}

        {step === 2 && (
          <Panel className="p-6" data-testid="setup-step-confirm">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-4">
              step 03 · confirm & sync
            </div>
            <p className="text-sm text-zinc-400 mb-4">
              We'll seed 14 days of mock thermostat data (Resideo is in mock mode until developer approval) and pull weather.
            </p>
            <div className="grid grid-cols-2 gap-3 text-xs font-mono border border-zinc-800 rounded-sm p-4 mb-6">
              <div className="text-zinc-500">property</div><div className="text-zinc-200">{property.name}</div>
              <div className="text-zinc-500">rate</div><div className="text-zinc-200">${property.rate_usd_per_kwh}/kWh</div>
              <div className="text-zinc-500">noaa station</div><div className="text-zinc-200">{property.noaa_station_id || "—"}</div>
              <div className="text-zinc-500">unit 1</div><div className="text-zinc-200">{unit1.name} · {unit1.tonnage}t</div>
              <div className="text-zinc-500">unit 2</div><div className="text-zinc-200">{unit2.name} · {unit2.tonnage}t</div>
            </div>
            <div className="flex justify-between">
              <button onClick={() => setStep(1)} className={btnSecondaryCls}>Back</button>
              <button onClick={finish} disabled={loading} className={btnPrimaryCls} data-testid="finish-setup">
                {loading ? "Syncing…" : "Finish & Sync"} <CheckCircleIcon size={14} />
              </button>
            </div>
          </Panel>
        )}
      </div>
    </div>
  );
}

const inputCls = "w-full bg-zinc-950 border border-zinc-800 rounded-sm px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500 focus:border-zinc-500 font-mono";
const btnPrimaryCls = "bg-white text-black hover:bg-zinc-200 rounded-sm px-4 py-2 text-sm font-medium transition-colors flex items-center gap-2";
const btnSecondaryCls = "bg-zinc-900 text-zinc-100 border border-zinc-800 hover:bg-zinc-800 rounded-sm px-4 py-2 text-sm font-medium";

function Field({ label, children, className }) {
  return (
    <label className={`block ${className || ""}`}>
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-1">{label}</div>
      {children}
    </label>
  );
}

function UnitCard({ unit, setUnit, testId }) {
  return (
    <div className="border border-zinc-800 rounded-sm p-4 space-y-3" data-testid={testId}>
      <div className="flex items-center gap-2">
        <div className="w-3 h-3 rounded-sm" style={{ background: unit.color }} />
        <input className={inputCls} value={unit.name} onChange={(e) => setUnit({...unit, name: e.target.value})} />
      </div>
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-1">Floor</div>
        <input className={inputCls} value={unit.floor} onChange={(e) => setUnit({...unit, floor: e.target.value})} />
      </div>
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-1">Tonnage</div>
        <input type="number" step="0.5" className={inputCls} value={unit.tonnage}
          onChange={(e) => setUnit({...unit, tonnage: parseFloat(e.target.value)})} />
      </div>
    </div>
  );
}
