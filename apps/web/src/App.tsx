import React, { useEffect, useState } from "react";
import { fetchQueue } from "./api/evaluations";
import { subscribeToEvents } from "./api/events";
import { setTenantId } from "./api/client";
import { QueueItem } from "./types/evaluation";
import { QueueDashboard } from "./components/QueueDashboard";
import { AnalyticsDashboard } from "./components/AnalyticsDashboard";
import { LiveStreamMonitor } from "./components/LiveStreamMonitor";
import { CallReview } from "./pages/CallReview";
import { ShieldCheck, BarChart3, List, Radio, Mic } from "lucide-react";

export const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<"QUEUE" | "ANALYTICS" | "REVIEW" | "LIVE_STREAM">("QUEUE");
  const [selectedSaleId, setSelectedSaleId] = useState<string | null>(null);
  const [queueStatus, setQueueStatus] = useState("ALL");
  const [tenant, setTenant] = useState("retailer-cimet-01");
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);
  const [sseConnected, setSseConnected] = useState(false);

  const loadQueue = async () => {
    try {
      const items = await fetchQueue(queueStatus);
      setQueueItems(items);
    } catch (err) {
      console.error("Failed to load queue:", err);
    }
  };

  useEffect(() => {
    setTenantId(tenant);
    loadQueue();
  }, [tenant, queueStatus]);

  // Real-time SSE event subscription
  useEffect(() => {
    const unsubscribe = subscribeToEvents((event) => {
      if (event.event_type === "Connected") {
        setSseConnected(true);
      } else {
        // Any business event (GateDecisionChanged, SaleSubmitted, etc.) triggers live queue refetch
        loadQueue();
      }
    }, tenant);

    return () => {
      unsubscribe();
      setSseConnected(false);
    };
  }, [tenant]);

  const handleSelectCall = (saleId: string) => {
    setSelectedSaleId(saleId);
    setCurrentView("REVIEW");
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Platform Top Header */}
      <header
        style={{
          background: "var(--bg-sidebar)",
          borderBottom: "1px solid var(--border-subtle)",
          padding: "12px 32px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div
            style={{
              width: "36px",
              height: "36px",
              borderRadius: "var(--radius-sm)",
              background: "linear-gradient(135deg, var(--brand-cyan), var(--brand-blue))",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "var(--shadow-glow-cyan)",
            }}
          >
            <ShieldCheck size={22} color="#090d16" />
          </div>
          <div>
            <h1 style={{ fontSize: "16px", fontWeight: 800, letterSpacing: "-0.5px" }}>
              SalesCall QA Platform
            </h1>
            <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
              Deterministic Compliance & Evidence Engine
            </span>
          </div>
        </div>

        {/* Center Nav Tabs */}
        <div style={{ display: "flex", gap: "6px" }}>
          <button
            onClick={() => {
              setCurrentView("QUEUE");
              setSelectedSaleId(null);
            }}
            style={{
              padding: "6px 16px",
              borderRadius: "var(--radius-sm)",
              fontSize: "13px",
              fontWeight: 600,
              cursor: "pointer",
              border: "none",
              background: currentView === "QUEUE" ? "var(--bg-surface)" : "transparent",
              color: currentView === "QUEUE" ? "var(--brand-cyan)" : "var(--text-secondary)",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <List size={15} />
            Review Queue
          </button>

          <button
            onClick={() => {
              setCurrentView("LIVE_STREAM");
              setSelectedSaleId(null);
            }}
            style={{
              padding: "6px 16px",
              borderRadius: "var(--radius-sm)",
              fontSize: "13px",
              fontWeight: 600,
              cursor: "pointer",
              border: "none",
              background: currentView === "LIVE_STREAM" ? "var(--bg-surface)" : "transparent",
              color: currentView === "LIVE_STREAM" ? "var(--brand-cyan)" : "var(--text-secondary)",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <Mic size={15} />
            Live Audio Stream Monitor
          </button>

          <button
            onClick={() => {
              setCurrentView("ANALYTICS");
              setSelectedSaleId(null);
            }}
            style={{
              padding: "6px 16px",
              borderRadius: "var(--radius-sm)",
              fontSize: "13px",
              fontWeight: 600,
              cursor: "pointer",
              border: "none",
              background: currentView === "ANALYTICS" ? "var(--bg-surface)" : "transparent",
              color: currentView === "ANALYTICS" ? "var(--brand-cyan)" : "var(--text-secondary)",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <BarChart3 size={15} />
            Calibration & Analytics
          </button>
        </div>

        {/* Live SSE Status Badge */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "3px 10px",
              borderRadius: "var(--radius-full)",
              fontSize: "11px",
              fontWeight: 600,
              background: sseConnected ? "rgba(16, 185, 129, 0.15)" : "rgba(244, 63, 94, 0.15)",
              color: sseConnected ? "#34d399" : "#fb7185",
            }}
          >
            <Radio size={12} className={sseConnected ? "animate-pulse" : ""} />
            {sseConnected ? "Live SSE Connected" : "Connecting..."}
          </span>
        </div>
      </header>

      {/* Main Container */}
      <main style={{ flex: 1, padding: "32px", maxWidth: "1540px", margin: "0 auto", width: "100%" }}>
        {currentView === "REVIEW" && selectedSaleId ? (
          <CallReview
            saleId={selectedSaleId}
            onBack={() => {
              setCurrentView("QUEUE");
              setSelectedSaleId(null);
              loadQueue();
            }}
          />
        ) : currentView === "LIVE_STREAM" ? (
          <LiveStreamMonitor />
        ) : currentView === "ANALYTICS" ? (
          <AnalyticsDashboard />
        ) : (
          <QueueDashboard
            items={queueItems}
            currentStatus={queueStatus}
            onStatusChange={setQueueStatus}
            onSelectCall={handleSelectCall}
            tenantId={tenant}
            onTenantChange={setTenant}
            onRefresh={loadQueue}
          />
        )}
      </main>
    </div>
  );
};
