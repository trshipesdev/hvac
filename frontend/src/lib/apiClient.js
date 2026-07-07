import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API });
export default client;

export const api = {
  authCheck: () => client.get("/auth/check"),
  getProperty: () => client.get("/property"),
  updateProperty: (data) => client.put("/property", data),
  listUnits: () => client.get("/units"),
  createUnit: (data) => client.post("/units", data),
  updateUnit: (id, data) => client.put(`/units/${id}`, data),
  deleteUnit: (id) => client.delete(`/units/${id}`),
  uploadGreenButton: (file) => {
    const fd = new FormData(); fd.append("file", file);
    return client.post("/ingest/green-button", fd, { headers: { "Content-Type": "multipart/form-data" } });
  },
  ingestNoaa: (days = 30) => client.post(`/ingest/noaa?days=${days}`),
  noaaStations: (zip) => client.get(`/noaa/stations?zip_code=${zip}`),
  resideoStatus: () => client.get("/resideo/status"),
  resideoSync: (days = 10) => client.post(`/resideo/sync?days=${days}`),
  resideoExchangeCode: (code) => client.post("/resideo/exchange-code", { code }),
  resideoLocations: () => client.get("/resideo/locations"),
  runAttribution: (days = 30) => client.post(`/attribution/run?days=${days}`),
  runAnomalies: (days = 30) => client.post(`/anomalies/run?days=${days}`),
  runPipeline: (days = 14) => client.post(`/pipeline/run?days=${days}`),
  listAnomalies: (params = {}) => client.get("/anomalies", { params }),
  ackAnomaly: (id, ack_note = null) => client.post(`/anomalies/${id}/ack`, { ack_note }),
  unackAnomaly: (id) => client.post(`/anomalies/${id}/unack`),
  timeline: (params) => client.get("/dashboard/timeline", { params }),
  summary: (params) => client.get("/dashboard/summary", { params }),
  dataStatus: () => client.get("/dashboard/data-status"),
  yoy: () => client.get("/dashboard/yoy"),
  drilldown: (ts, bucket) => client.get("/dashboard/drilldown", { params: { ts, bucket } }),
  listBills: () => client.get("/bills"),
  createBill: (data) => client.post("/bills", data),
  deleteBill: (id) => client.delete(`/bills/${id}`),
  parseBill: (file) => {
    const fd = new FormData(); fd.append("file", file);
    return client.post("/bills/parse", fd, { headers: { "Content-Type": "multipart/form-data" } });
  },
  confirmBill: (parsed, apply_rate = true) => client.post("/bills/confirm", { parsed, apply_rate }),
  bulkParseBills: (files) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    return client.post("/bills/bulk-parse", fd, { headers: { "Content-Type": "multipart/form-data" } });
  },
  rescanBillAnomalies: () => client.post("/bills/rescan-anomalies"),
  listRatePeriods: () => client.get("/rate-periods"),
  parseHoneywellReport: (file) => {
    const fd = new FormData(); fd.append("file", file);
    return client.post("/honeywell/parse", fd, { headers: { "Content-Type": "multipart/form-data" } });
  },
  confirmHoneywellReport: (payload) => client.post("/honeywell/confirm", payload),
  bulkParseHoneywellReports: (files) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    return client.post("/honeywell/bulk-parse", fd, { headers: { "Content-Type": "multipart/form-data" } });
  },
  listHoneywellZoneMonths: (params = {}) => client.get("/honeywell/zone-months", { params }),
  patchHoneywellZoneMonth: (id, body) => client.patch(`/honeywell/zone-months/${id}`, body),
  getUnitCostComparison: (params = {}) => client.get("/honeywell/comparison", { params }),
  rescanZoneAnomalies: () => client.post("/honeywell/rescan-anomalies"),
  getCoverage: () => client.get("/coverage"),
  backfillAll: () => client.post("/pipeline/backfill-all"),
  downloadCsv: async (params) => (await client.get("/export/csv", { params, responseType: "blob" })).data,
  downloadPdf: async (params) => (await client.get("/export/pdf", { params, responseType: "blob" })).data,
  downloadBillsCsv: async () => (await client.get("/export/bills-csv", { responseType: "blob" })).data,
  downloadZoneMonthsCsv: async () => (await client.get("/export/zone-months-csv", { responseType: "blob" })).data,
  downloadSampleXml: async () => (await client.get("/ingest/sample-xml", { responseType: "blob" })).data,
};
