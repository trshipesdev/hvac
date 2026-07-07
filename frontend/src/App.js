import React, { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import Layout from "@/components/Layout";
import Setup from "@/pages/Setup";
import Dashboard from "@/pages/Dashboard";
import Ingest from "@/pages/Ingest";
import Anomalies from "@/pages/Anomalies";
import Bills from "@/pages/Bills";
import Honeywell from "@/pages/Honeywell";
import Settings from "@/pages/Settings";
import { api } from "@/lib/apiClient";
import "@/App.css";

function BootGate({ children }) {
  const [state, setState] = useState({ loading: true, hasUnits: false });
  const location = useLocation();

  useEffect(() => {
    const check = async () => {
      try {
        const units = await api.listUnits();
        setState({ loading: false, hasUnits: (units.data || []).length >= 2 });
      } catch {
        setState({ loading: false, hasUnits: false });
      }
    };
    check();
  }, [location.pathname]);

  if (state.loading)
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center text-zinc-500 font-mono terminal-cursor">
        booting
      </div>
    );
  if (!state.hasUnits && location.pathname !== "/setup") return <Navigate to="/setup" replace />;
  return children;
}

function AppShell({ children }) {
  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster
        theme="light"
        position="top-right"
        toastOptions={{
          style: {
            background: "#FFFFFF",
            border: "1px solid #E2E0D8",
            color: "#1E3A2F",
            fontFamily: "DM Sans, system-ui, sans-serif",
            borderRadius: "12px",
          },
        }}
      />
      <Routes>
        <Route path="/setup" element={<BootGate><Setup /></BootGate>} />
        <Route path="/dashboard" element={<BootGate><AppShell><Dashboard /></AppShell></BootGate>} />
        <Route path="/ingest" element={<BootGate><AppShell><Ingest /></AppShell></BootGate>} />
        <Route path="/anomalies" element={<BootGate><AppShell><Anomalies /></AppShell></BootGate>} />
        <Route path="/bills" element={<BootGate><AppShell><Bills /></AppShell></BootGate>} />
        <Route path="/honeywell" element={<BootGate><AppShell><Honeywell /></AppShell></BootGate>} />
        <Route path="/settings" element={<BootGate><AppShell><Settings /></AppShell></BootGate>} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
