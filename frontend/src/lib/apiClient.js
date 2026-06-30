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
    const fd = new FormData();
    fd.append("file", file);
    return client.post("/ingest/green-button", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  ingestNoaa: (days = 30) => client.post(`/ingest/noaa?days=${days}`),
  noaaStations: (zip) => client.get(`/noaa/stations?zip_code=${zip}`),
  resideoStatus: () => client.get("/resideo/status"),
  resideoSync: (days = 10) => client.post(`/resideo/sync?days=${days}`),
  runAttribution: (days = 30) => client.post(`/attribution/run?days=${days}`),
  runAnomalies: (days = 30) => client.post(`/anomalies/run?days=${days}`),
  runPipeline: (days = 14) => client.post(`/pipeline/run?days=${days}`),
  listAnomalies: (params = {}) => client.get("/anomalies", { params }),
  timeline: (days = 7, bucket = "hour") =>
    client.get(`/dashboard/timeline?days=${days}&bucket=${bucket}`),
  summary: (days = 7) => client.get(`/dashboard/summary?days=${days}`),
  dataStatus: () => client.get("/dashboard/data-status"),
  listBills: () => client.get("/bills"),
  createBill: (data) => client.post("/bills", data),
  deleteBill: (id) => client.delete(`/bills/${id}`),
  downloadCsv: async (days = 30) => {
    const res = await client.get(`/export/csv?days=${days}`, { responseType: "blob" });
    return res.data;
  },
  downloadPdf: async (days = 30) => {
    const res = await client.get(`/export/pdf?days=${days}`, { responseType: "blob" });
    return res.data;
  },
  downloadSampleXml: async () => {
    const res = await client.get(`/ingest/sample-xml`, { responseType: "blob" });
    return res.data;
  },
};
