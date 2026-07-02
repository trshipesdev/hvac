import React, { useEffect, useState } from "react";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader } from "@/components/Panel";
import { toast } from "sonner";
import { Trash2, Save, Plus } from "lucide-react";

export default function Settings() {
  const [property, setProperty] = useState(null);
  const [units, setUnits] = useState([]);
  const [resideo, setResideo] = useState(null);
  const [newUnit, setNewUnit] = useState({ name: "", floor: "", tonnage: 0, color: "#10B981" });

  const load = async () => {
    try {
      const [p, u, r] = await Promise.all([api.getProperty(), api.listUnits(), api.resideoStatus()]);
      setProperty(p.data); setUnits(u.data); setResideo(r.data);
    } catch { toast.error("Load failed"); }
  };
  useEffect(() => { load(); }, []);

  const saveProperty = async () => { try { await api.updateProperty(property); toast.success("Property saved"); } catch { toast.error("Save failed"); } };
  const saveUnit = async (u) => { try { await api.updateUnit(u.id, u); toast.success(`${u.name} saved`); } catch { toast.error("Save failed"); } };
  const removeUnit = async (id) => { try { await api.deleteUnit(id); load(); } catch { toast.error("Delete failed"); } };
  const addUnit = async () => { if (!newUnit.name) return; try { await api.createUnit(newUnit); setNewUnit({ name: "", floor: "", tonnage: 0, color: "#10B981" }); load(); } catch { toast.error("Add failed"); } };

  if (!property) return <div className="text-slate-500">Loading…</div>;

  return (
    <div className="space-y-8 animate-fade-in" data-testid="settings-page">
      <div>
        <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">configuration</div>
        <h1 className="text-4xl font-serif tracking-tight text-forest-900">Settings</h1>
        <p className="text-sm text-slate-600 mt-1.5">Property, HVAC units, and integration status.</p>
      </div>

      <Panel data-testid="property-panel">
        <PanelHeader label="Property" />
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-5">
          <Field label="Name"><input className={inputCls} value={property.name || ""} onChange={(e) => setProperty({...property, name: e.target.value})} data-testid="setting-name" /></Field>
          <Field label="Rate ($/kWh)"><input type="number" step="0.001" className={inputCls} value={property.rate_usd_per_kwh} onChange={(e) => setProperty({...property, rate_usd_per_kwh: parseFloat(e.target.value)})} data-testid="setting-rate" /></Field>
          <Field label="Address" className="md:col-span-2"><input className={inputCls} value={property.address || ""} onChange={(e) => setProperty({...property, address: e.target.value})} /></Field>
          <Field label="ZIP code"><input className={inputCls} value={property.zip_code || ""} onChange={(e) => setProperty({...property, zip_code: e.target.value})} /></Field>
          <Field label="NOAA station ID"><input className={inputCls} value={property.noaa_station_id || ""} onChange={(e) => setProperty({...property, noaa_station_id: e.target.value})} data-testid="setting-station" /></Field>
          <div className="md:col-span-2 flex justify-end">
            <button onClick={saveProperty} className={btnPrimary} data-testid="save-property"><Save size={14} strokeWidth={1.75} /> Save property</button>
          </div>
        </div>
      </Panel>

      <Panel data-testid="units-panel">
        <PanelHeader label="HVAC Units" />
        <div className="divide-y divide-paper-200">
          {units.map((u) => (
            <div key={u.id} className="p-5 grid grid-cols-2 md:grid-cols-6 gap-3 items-end" data-testid={`unit-row-${u.id}`}>
              <Field label="Name" className="md:col-span-2">
                <input className={inputCls} value={u.name} onChange={(e) => setUnits(units.map((x) => x.id === u.id ? {...x, name: e.target.value} : x))} />
              </Field>
              <Field label="Floor"><input className={inputCls} value={u.floor || ""} onChange={(e) => setUnits(units.map((x) => x.id === u.id ? {...x, floor: e.target.value} : x))} /></Field>
              <Field label="Tonnage"><input type="number" step="0.5" className={inputCls} value={u.tonnage || 0} onChange={(e) => setUnits(units.map((x) => x.id === u.id ? {...x, tonnage: parseFloat(e.target.value)} : x))} /></Field>
              <Field label="Color"><input type="color" className="w-full h-10 bg-white border border-paper-300 rounded-lg cursor-pointer" value={u.color} onChange={(e) => setUnits(units.map((x) => x.id === u.id ? {...x, color: e.target.value} : x))} /></Field>
              <div className="flex gap-2">
                <button onClick={() => saveUnit(u)} className={btnPrimary}><Save size={14} strokeWidth={1.75} /></button>
                <button onClick={() => removeUnit(u.id)} className="bg-white border border-paper-300 hover:bg-red-50 hover:border-red-300 hover:text-red-600 text-slate-500 rounded-lg px-3 py-2.5 transition-colors"><Trash2 size={14} strokeWidth={1.75} /></button>
              </div>
            </div>
          ))}
          <div className="p-5 grid grid-cols-2 md:grid-cols-6 gap-3 items-end bg-paper-50" data-testid="add-unit-row">
            <Field label="Add unit · name" className="md:col-span-2"><input className={inputCls} value={newUnit.name} onChange={(e) => setNewUnit({...newUnit, name: e.target.value})} /></Field>
            <Field label="Floor"><input className={inputCls} value={newUnit.floor} onChange={(e) => setNewUnit({...newUnit, floor: e.target.value})} /></Field>
            <Field label="Tonnage"><input type="number" step="0.5" className={inputCls} value={newUnit.tonnage} onChange={(e) => setNewUnit({...newUnit, tonnage: parseFloat(e.target.value)})} /></Field>
            <Field label="Color"><input type="color" className="w-full h-10 bg-white border border-paper-300 rounded-lg cursor-pointer" value={newUnit.color} onChange={(e) => setNewUnit({...newUnit, color: e.target.value})} /></Field>
            <button onClick={addUnit} className={btnPrimary} data-testid="add-unit-btn"><Plus size={14} strokeWidth={1.75} /> Add</button>
          </div>
        </div>
      </Panel>

      <Panel data-testid="integration-panel">
        <PanelHeader label="Integrations" />
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="border border-paper-300 rounded-lg p-4 bg-white">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">Resideo / Honeywell</div>
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-widest border ${
                resideo?.mock_mode ? "bg-amber-50 text-amber-800 border-amber-300" : "bg-energy-50 text-energy-700 border-energy-500/40"
              }`}><span className="w-1 h-1 rounded-full bg-current" />{resideo?.mock_mode ? "Mock" : "Live"}</span>
            </div>
            <div className="text-xs text-slate-600 leading-relaxed">{resideo?.message}</div>
          </div>
          <div className="border border-paper-300 rounded-lg p-4 bg-white">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">NOAA CDO</div>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-widest bg-energy-50 text-energy-700 border border-energy-500/40"><span className="w-1 h-1 rounded-full bg-current" />Configured</span>
            </div>
            <div className="text-xs text-slate-600 leading-relaxed">Set your station ID in the Property panel above. ZIP-code station lookup available on the Setup wizard.</div>
          </div>
          <div className="border border-paper-300 rounded-lg p-4 bg-white md:col-span-2">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">Claude Haiku 4.5 · Bill Parser</div>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-widest bg-energy-50 text-energy-700 border border-energy-500/40"><span className="w-1 h-1 rounded-full bg-current" />Live</span>
            </div>
            <div className="text-xs text-slate-600 leading-relaxed">Utility bill PDFs are sent directly to Anthropic (not via Emergent). Model: <span className="font-mono text-forest-700">claude-haiku-4-5-20251001</span>.</div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

const inputCls = "w-full bg-white border border-paper-300 rounded-lg px-3 py-2 text-sm text-forest-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-forest-500/30 focus:border-forest-500 transition-all";
const btnPrimary = "bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-3 py-2.5 text-sm font-medium flex items-center gap-1.5 transition-colors";

function Field({ label, children, className }) {
  return (
    <label className={`block ${className || ""}`}>
      <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-1.5">{label}</div>
      {children}
    </label>
  );
}
