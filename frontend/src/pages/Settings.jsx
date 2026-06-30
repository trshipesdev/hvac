import React, { useEffect, useState } from "react";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader } from "@/components/Panel";
import { toast } from "sonner";
import { TrashIcon, FloppyDiskIcon, PlusIcon } from "@phosphor-icons/react";

export default function Settings() {
  const [property, setProperty] = useState(null);
  const [units, setUnits] = useState([]);
  const [resideo, setResideo] = useState(null);
  const [newUnit, setNewUnit] = useState({ name: "", floor: "", tonnage: 0, color: "#10b981" });

  const load = async () => {
    try {
      const [p, u, r] = await Promise.all([api.getProperty(), api.listUnits(), api.resideoStatus()]);
      setProperty(p.data); setUnits(u.data); setResideo(r.data);
    } catch { toast.error("Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const saveProperty = async () => {
    try { await api.updateProperty(property); toast.success("Property saved"); }
    catch { toast.error("Save failed"); }
  };

  const saveUnit = async (u) => {
    try { await api.updateUnit(u.id, u); toast.success(`${u.name} saved`); }
    catch { toast.error("Save failed"); }
  };

  const removeUnit = async (id) => {
    try { await api.deleteUnit(id); load(); }
    catch { toast.error("Delete failed"); }
  };

  const addUnit = async () => {
    if (!newUnit.name) return;
    try { await api.createUnit(newUnit); setNewUnit({ name: "", floor: "", tonnage: 0, color: "#10b981" }); load(); }
    catch { toast.error("Add failed"); }
  };

  if (!property) return <div className="text-zinc-500 font-mono">loading…</div>;

  return (
    <div className="space-y-6" data-testid="settings-page">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-1">&gt; configuration</div>
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
      </div>

      <Panel data-testid="property-panel">
        <PanelHeader label="Property" />
        <div className="p-4 grid grid-cols-2 gap-3">
          <Field label="Name">
            <input className={inputCls} value={property.name || ""} onChange={(e) => setProperty({...property, name: e.target.value})} data-testid="setting-name" />
          </Field>
          <Field label="Rate ($/kWh)">
            <input type="number" step="0.001" className={inputCls} value={property.rate_usd_per_kwh}
              onChange={(e) => setProperty({...property, rate_usd_per_kwh: parseFloat(e.target.value)})} data-testid="setting-rate" />
          </Field>
          <Field label="Address" className="col-span-2">
            <input className={inputCls} value={property.address || ""} onChange={(e) => setProperty({...property, address: e.target.value})} />
          </Field>
          <Field label="ZIP code">
            <input className={inputCls} value={property.zip_code || ""} onChange={(e) => setProperty({...property, zip_code: e.target.value})} />
          </Field>
          <Field label="NOAA station ID">
            <input className={inputCls} value={property.noaa_station_id || ""} onChange={(e) => setProperty({...property, noaa_station_id: e.target.value})} data-testid="setting-station" />
          </Field>
          <div className="col-span-2 flex justify-end">
            <button onClick={saveProperty} className={btnPrimary} data-testid="save-property">
              <FloppyDiskIcon size={14} /> Save property
            </button>
          </div>
        </div>
      </Panel>

      <Panel data-testid="units-panel">
        <PanelHeader label="HVAC Units" />
        <div className="divide-y divide-zinc-800/60">
          {units.map((u) => (
            <div key={u.id} className="p-4 grid grid-cols-6 gap-3 items-end" data-testid={`unit-row-${u.id}`}>
              <Field label="Name" className="col-span-2">
                <input className={inputCls} value={u.name} onChange={(e) => {
                  const upd = units.map((x) => x.id === u.id ? {...x, name: e.target.value} : x); setUnits(upd);
                }} />
              </Field>
              <Field label="Floor">
                <input className={inputCls} value={u.floor || ""} onChange={(e) => {
                  const upd = units.map((x) => x.id === u.id ? {...x, floor: e.target.value} : x); setUnits(upd);
                }} />
              </Field>
              <Field label="Tonnage">
                <input type="number" step="0.5" className={inputCls} value={u.tonnage || 0} onChange={(e) => {
                  const upd = units.map((x) => x.id === u.id ? {...x, tonnage: parseFloat(e.target.value)} : x); setUnits(upd);
                }} />
              </Field>
              <Field label="Color">
                <input type="color" className="w-full h-9 bg-zinc-950 border border-zinc-800 rounded-sm" value={u.color} onChange={(e) => {
                  const upd = units.map((x) => x.id === u.id ? {...x, color: e.target.value} : x); setUnits(upd);
                }} />
              </Field>
              <div className="flex gap-2">
                <button onClick={() => saveUnit(u)} className={btnPrimary}><FloppyDiskIcon size={14} /></button>
                <button onClick={() => removeUnit(u.id)} className="border border-zinc-800 hover:bg-red-500/10 hover:text-red-500 text-zinc-400 rounded-sm px-3 py-2 text-sm"><TrashIcon size={14} /></button>
              </div>
            </div>
          ))}
          <div className="p-4 grid grid-cols-6 gap-3 items-end bg-zinc-900/20" data-testid="add-unit-row">
            <Field label="Add unit — name" className="col-span-2">
              <input className={inputCls} value={newUnit.name} onChange={(e) => setNewUnit({...newUnit, name: e.target.value})} />
            </Field>
            <Field label="Floor">
              <input className={inputCls} value={newUnit.floor} onChange={(e) => setNewUnit({...newUnit, floor: e.target.value})} />
            </Field>
            <Field label="Tonnage">
              <input type="number" step="0.5" className={inputCls} value={newUnit.tonnage} onChange={(e) => setNewUnit({...newUnit, tonnage: parseFloat(e.target.value)})} />
            </Field>
            <Field label="Color">
              <input type="color" className="w-full h-9 bg-zinc-950 border border-zinc-800 rounded-sm" value={newUnit.color} onChange={(e) => setNewUnit({...newUnit, color: e.target.value})} />
            </Field>
            <button onClick={addUnit} className={btnPrimary} data-testid="add-unit-btn"><PlusIcon size={14} /> Add</button>
          </div>
        </div>
      </Panel>

      <Panel data-testid="integration-panel">
        <PanelHeader label="Integrations" />
        <div className="p-4 space-y-3 font-mono text-xs">
          <div className="border border-zinc-800 rounded-sm p-3">
            <div className="text-zinc-500 uppercase tracking-widest text-[10px] mb-1">resideo / honeywell</div>
            <div className={resideo?.mock_mode ? "text-amber-500" : "text-emerald-500"}>
              {resideo?.mock_mode ? "MOCK MODE" : "LIVE"}
            </div>
            <div className="text-zinc-400 text-[11px] mt-2 leading-relaxed">{resideo?.message}</div>
          </div>
          <div className="border border-zinc-800 rounded-sm p-3">
            <div className="text-zinc-500 uppercase tracking-widest text-[10px] mb-1">noaa cdo</div>
            <div className="text-emerald-500">API TOKEN CONFIGURED</div>
            <div className="text-zinc-400 text-[11px] mt-2">Configure station in the Property panel above.</div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

const inputCls = "w-full bg-zinc-950 border border-zinc-800 rounded-sm px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500 focus:border-zinc-500 font-mono";
const btnPrimary = "bg-white text-black hover:bg-zinc-200 rounded-sm px-3 py-2 text-sm font-medium flex items-center gap-1.5";

function Field({ label, children, className }) {
  return (
    <label className={`block ${className || ""}`}>
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-1">{label}</div>
      {children}
    </label>
  );
}
