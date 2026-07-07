import React, { useEffect, useState } from "react";
import { api } from "@/lib/apiClient";
import { Panel, PanelHeader } from "@/components/Panel";
import { toast } from "sonner";
import { Trash2, Save, Plus, RefreshCw, BellRing } from "lucide-react";

const ANOMALY_TYPES = [
  { group: "HVAC", id: "extended_runtime", label: "Extended runtime" },
  { group: "HVAC", id: "overnight_draw", label: "Overnight draw" },
  { group: "HVAC", id: "efficiency_regression", label: "Efficiency regression" },
  { group: "HVAC", id: "weather_disproportion", label: "Weather disproportion" },
  { group: "HVAC", id: "setpoint_gap_widening", label: "Setpoint gap widening" },
  { group: "HVAC", id: "zone_mode_weather_mismatch", label: "Heating/cooling vs. monthly weather" },
  { group: "HVAC", id: "mode_weather_mismatch", label: "Heat/cool ran on the wrong kind of day (daily)" },
  { group: "Bill", id: "bill_rate_spike", label: "Rate spike" },
  { group: "Bill", id: "bill_usage_spike", label: "Usage spike" },
  { group: "Bill", id: "bill_meter_mismatch", label: "Meter mismatch" },
  { group: "Bill", id: "bill_period_gap", label: "Billing period gap" },
  { group: "Bill", id: "bill_past_due", label: "Past due balance" },
  { group: "Bill", id: "bill_late_fee", label: "Late/reconnect fee" },
];
const ALL_ANOMALY_TYPE_IDS = ANOMALY_TYPES.map((t) => t.id);

export default function Settings() {
  const [property, setProperty] = useState(null);
  const [units, setUnits] = useState([]);
  const [resideo, setResideo] = useState(null);
  const [newUnit, setNewUnit] = useState({ name: "", floor: "", tonnage: 0, color: "#10B981" });
  const [loadError, setLoadError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [stations, setStations] = useState([]);
  const [searchingStations, setSearchingStations] = useState(false);
  const [resideoCode, setResideoCode] = useState("");
  const [connectingResideo, setConnectingResideo] = useState(false);
  const [resideoDevices, setResideoDevices] = useState([]);

  const load = async () => {
    setLoading(true); setLoadError(false);
    try {
      const [p, u, r] = await Promise.all([api.getProperty(), api.listUnits(), api.resideoStatus()]);
      setProperty(p.data); setUnits(u.data); setResideo(r.data);
      if (r.data?.connected) {
        try { const loc = await api.resideoLocations(); setResideoDevices(loc.data || []); } catch { /* non-fatal */ }
      }
    } catch {
      toast.error("Load failed");
      setLoadError(true);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const connectResideo = async () => {
    if (!resideoCode.trim()) { toast.error("Paste the code Resideo shows you first"); return; }
    setConnectingResideo(true);
    try {
      await api.resideoExchangeCode(resideoCode.trim());
      toast.success("Connected to Resideo");
      setResideoCode("");
      load();
    } catch (e) { toast.error("Connect failed: " + (e.response?.data?.detail || e.message)); }
    finally { setConnectingResideo(false); }
  };
  const assignResideoDevice = async (unitId, deviceId, locationId) => {
    try {
      await api.updateUnit(unitId, { thermostat_device_id: deviceId, resideo_location_id: locationId });
      toast.success("Device assigned");
      load();
    } catch (e) { toast.error("Assign failed: " + (e.response?.data?.detail || e.message)); }
  };

  const saveProperty = async () => { try { await api.updateProperty(property); toast.success("Property saved"); } catch { toast.error("Save failed"); } };
  const searchStations = async () => {
    if (!property.zip_code) { toast.error("Enter a ZIP code first"); return; }
    setSearchingStations(true);
    try {
      const res = await api.noaaStations(property.zip_code);
      setStations(res.data || []);
      if (!res.data?.length) toast.info("No stations found — enter one manually");
    } catch (e) { toast.error("NOAA lookup failed: " + (e.response?.data?.detail || e.message)); }
    finally { setSearchingStations(false); }
  };
  const saveUnit = async (u) => { try { await api.updateUnit(u.id, u); toast.success(`${u.name} saved`); } catch { toast.error("Save failed"); } };
  const enabledAnomalyTypes = property?.dashboard_anomaly_types ?? ALL_ANOMALY_TYPE_IDS;
  const toggleAnomalyType = (id) => {
    const next = enabledAnomalyTypes.includes(id)
      ? enabledAnomalyTypes.filter((t) => t !== id)
      : [...enabledAnomalyTypes, id];
    setProperty({ ...property, dashboard_anomaly_types: next });
  };
  const removeUnit = async (id) => { try { await api.deleteUnit(id); load(); } catch { toast.error("Delete failed"); } };
  const addUnit = async () => { if (!newUnit.name) return; try { await api.createUnit(newUnit); setNewUnit({ name: "", floor: "", tonnage: 0, color: "#10B981" }); load(); } catch { toast.error("Add failed"); } };

  if (loadError) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center" data-testid="settings-load-error">
        <div className="text-sm text-slate-500">Couldn't reach the backend to load settings.</div>
        <button onClick={load} className={btnPrimary}><RefreshCw size={14} strokeWidth={1.75} /> Retry</button>
      </div>
    );
  }
  if (!property) return <div className="text-slate-500">{loading ? "Loading…" : "No property data."}</div>;

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
          <Field label="ZIP code">
            <div className="flex gap-2">
              <input className={inputCls} value={property.zip_code || ""} onChange={(e) => setProperty({...property, zip_code: e.target.value})} data-testid="setting-zip" />
              <button onClick={searchStations} disabled={searchingStations} className="bg-white border border-paper-300 hover:bg-paper-200 text-forest-700 rounded-lg px-4 py-2 text-sm font-medium transition-colors" data-testid="setting-find-stations">
                {searchingStations ? "…" : "Find"}
              </button>
            </div>
          </Field>
          <Field label="NOAA station ID"><input className={inputCls} value={property.noaa_station_id || ""} onChange={(e) => setProperty({...property, noaa_station_id: e.target.value})} placeholder="GHCND:USW00…" data-testid="setting-station" /></Field>
          <Field label={property.timezone ? "Timezone (auto-detected — override if wrong)" : "Timezone (not detected yet — enter a ZIP and Find, or set manually)"}>
            <input className={inputCls} value={property.timezone || ""} onChange={(e) => setProperty({...property, timezone: e.target.value})} placeholder="America/New_York" data-testid="setting-timezone" />
          </Field>
          <Field label="Time format">
            <label className="flex items-center gap-2 text-sm text-forest-800 cursor-pointer h-10">
              <input type="checkbox" className="accent-forest-500 w-4 h-4" checked={!!property.use_24h_time}
                onChange={(e) => setProperty({...property, use_24h_time: e.target.checked})} data-testid="setting-24h" />
              Use 24-hour time (military)
            </label>
          </Field>
          {stations.length > 0 && (
            <div className="md:col-span-2 border border-paper-300 rounded-lg bg-paper-50">
              <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-forest-500 px-4 py-2 border-b border-paper-300">Nearby stations</div>
              <div className="max-h-40 overflow-y-auto">
                {stations.map((s) => (
                  <button key={s.id} onClick={() => setProperty({...property, noaa_station_id: s.id, latitude: s.latitude, longitude: s.longitude})}
                    className="w-full text-left px-4 py-2 text-xs font-mono hover:bg-white border-b border-paper-200 last:border-0"
                    data-testid={`setting-station-${s.id}`}>{s.id} — {s.name}</button>
                ))}
              </div>
            </div>
          )}
          <div className="md:col-span-2 flex justify-end">
            <button onClick={saveProperty} className={btnPrimary} data-testid="save-property"><Save size={14} strokeWidth={1.75} /> Save property</button>
          </div>
        </div>
      </Panel>

      <Panel data-testid="dashboard-alerts-panel">
        <PanelHeader label={<span className="flex items-center gap-2"><BellRing size={12} strokeWidth={2} className="text-forest-500" />Dashboard alerts</span>} />
        <div className="p-6">
          <p className="text-sm text-slate-600 mb-4">Choose which anomaly types show up in the Dashboard's KPI count and Recent Anomalies list. Unchecked types still exist and stay visible on the full Anomalies page — this only mutes what surfaces on the Dashboard.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
            {["HVAC", "Bill"].map((group) => (
              <div key={group}>
                <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500 mb-2">{group}</div>
                <div className="space-y-2">
                  {ANOMALY_TYPES.filter((t) => t.group === group).map((t) => (
                    <label key={t.id} className="flex items-center gap-2 text-sm text-forest-800 cursor-pointer" data-testid={`anomaly-type-${t.id}`}>
                      <input type="checkbox" className="accent-forest-500 w-4 h-4"
                        checked={enabledAnomalyTypes.includes(t.id)}
                        onChange={() => toggleAnomalyType(t.id)} />
                      {t.label}
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="flex justify-end mt-5">
            <button onClick={saveProperty} className={btnPrimary} data-testid="save-anomaly-prefs"><Save size={14} strokeWidth={1.75} /> Save alert preferences</button>
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
          <div className="border border-paper-300 rounded-lg p-4 bg-white md:col-span-2">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">Resideo / Honeywell</div>
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-widest border ${
                resideo?.mock_mode ? "bg-amber-50 text-amber-800 border-amber-300" : (resideo?.connected ? "bg-energy-50 text-energy-700 border-energy-500/40" : "bg-sky-50 text-sky-700 border-sky-300")
              }`}><span className="w-1 h-1 rounded-full bg-current" />{resideo?.mock_mode ? "Mock" : (resideo?.connected ? "Live" : "Not connected")}</span>
            </div>
            <div className="text-xs text-slate-600 leading-relaxed mb-3">{resideo?.message}</div>

            {!resideo?.mock_mode && !resideo?.connected && resideo?.oauth_url && (
              <div className="flex flex-wrap items-center gap-2" data-testid="resideo-connect-panel">
                <a href={resideo.oauth_url} target="_blank" rel="noreferrer"
                  className="bg-forest-500 hover:bg-forest-600 text-white rounded-lg px-3.5 py-2 text-xs font-medium uppercase tracking-wider transition-colors"
                  data-testid="resideo-connect-link">Connect Resideo</a>
                <input className={inputCls + " max-w-xs"} placeholder="Paste the code Resideo shows you"
                  value={resideoCode} onChange={(e) => setResideoCode(e.target.value)} data-testid="resideo-code-input" />
                <button onClick={connectResideo} disabled={connectingResideo} className={btnPrimary} data-testid="resideo-submit-code">
                  {connectingResideo ? "…" : "Submit code"}
                </button>
              </div>
            )}

            {resideo?.connected && (
              <div className="space-y-2" data-testid="resideo-device-assignment">
                <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">Assign each unit to a real thermostat</div>
                {units.map((u) => (
                  <div key={u.id} className="flex items-center gap-2">
                    <div className="text-sm text-forest-800 w-32 shrink-0">{u.name}</div>
                    <select defaultValue={u.thermostat_device_id ? `${u.resideo_location_id}::${u.thermostat_device_id}` : ""}
                      onChange={(e) => {
                        const [locationId, deviceId] = e.target.value.split("::");
                        if (deviceId) assignResideoDevice(u.id, deviceId, locationId);
                      }}
                      className="bg-white border border-paper-300 rounded-lg px-2 py-1.5 text-sm text-forest-800 flex-1"
                      data-testid={`resideo-device-select-${u.id}`}>
                      <option value="">Select thermostat…</option>
                      {resideoDevices.flatMap((loc) => (loc.devices || []).map((d) => (
                        <option key={d.deviceID || d.deviceId} value={`${loc.locationID || loc.locationId}::${d.deviceID || d.deviceId}`}>
                          {loc.name} / {d.userDefinedDeviceName || d.name || d.deviceID}
                        </option>
                      )))}
                    </select>
                  </div>
                ))}
                {resideoDevices.length === 0 && <div className="text-xs text-slate-500">No locations/devices returned yet.</div>}
              </div>
            )}
          </div>
          <div className="border border-paper-300 rounded-lg p-4 bg-white">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">NOAA CDO</div>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-widest bg-energy-50 text-energy-700 border border-energy-500/40"><span className="w-1 h-1 rounded-full bg-current" />Configured</span>
            </div>
            <div className="text-xs text-slate-600 leading-relaxed">Enter a ZIP code above and click Find to look up your nearest station.</div>
          </div>
          <div className="border border-paper-300 rounded-lg p-4 bg-white md:col-span-2">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-slate-500">Claude Haiku 4.5 · Bill Parser</div>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-widest bg-energy-50 text-energy-700 border border-energy-500/40"><span className="w-1 h-1 rounded-full bg-current" />Live</span>
            </div>
            <div className="text-xs text-slate-600 leading-relaxed">Utility bill PDFs are sent directly to Anthropic. Model: <span className="font-mono text-forest-700">claude-haiku-4-5-20251001</span>.</div>
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
