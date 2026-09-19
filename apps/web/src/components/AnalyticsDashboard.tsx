import React from "react";
import { QueueItem } from "../types/evaluation";
import { TrendingUp, ShieldCheck, UserCheck, Award } from "lucide-react";

interface AnalyticsDashboardProps {
  items: QueueItem[];
}

export const AnalyticsDashboard: React.FC<AnalyticsDashboardProps> = ({ items }) => {
  const total = items.length;
  const passed = items.filter((i) => i.status === "PASSED").length;
  const held = items.filter((i) => i.status === "HELD").length;
  const review = items.filter((i) => i.status === "REVIEW_REQUIRED").length;

  const fpyRate = total > 0 ? ((passed / total) * 100).toFixed(1) : "0.0";
  const holdRate = total > 0 ? ((held / total) * 100).toFixed(1) : "0.0";
  const reviewRate = total > 0 ? ((review / total) * 100).toFixed(1) : "0.0";

  // Score distribution
  const scores = items.map((i) => i.overall_score).filter((s): s is number => s !== null && s !== undefined);
  const avgScore = scores.length > 0 ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1) : "N/A";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      <div>
        <h2 style={{ fontSize: "24px", fontWeight: 800, color: "var(--text-primary)" }}>
          QA Compliance Analytics & Calibration
        </h2>
        <p style={{ fontSize: "14px", color: "var(--text-secondary)", marginTop: "4px" }}>
          First-Pass Yield, policy gate distribution, and deterministic compliance metrics
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px" }}>
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", padding: "18px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase" }}>First-Pass Yield</span>
            <TrendingUp size={18} color="var(--brand-cyan)" />
          </div>
          <div style={{ fontSize: "32px", fontWeight: 800, color: "var(--brand-cyan)", marginTop: "8px" }}>{fpyRate}%</div>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Auto-passed sales</span>
        </div>

        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", padding: "18px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase" }}>Average QA Score</span>
            <Award size={18} color="#34d399" />
          </div>
          <div style={{ fontSize: "32px", fontWeight: 800, color: "#34d399", marginTop: "8px" }}>{avgScore}%</div>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Weighted quality score</span>
        </div>

        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", padding: "18px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase" }}>Hold Rate</span>
            <ShieldCheck size={18} color="#fb7185" />
          </div>
          <div style={{ fontSize: "32px", fontWeight: 800, color: "#fb7185", marginTop: "8px" }}>{holdRate}%</div>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Critical non-compliance</span>
        </div>

        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", padding: "18px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase" }}>Review Rate</span>
            <UserCheck size={18} color="#fbbf24" />
          </div>
          <div style={{ fontSize: "32px", fontWeight: 800, color: "#fbbf24", marginTop: "8px" }}>{reviewRate}%</div>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Human QA required</span>
        </div>
      </div>

      {/* Gate Distribution Breakdown */}
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          padding: "24px",
        }}
      >
        <h3 style={{ fontSize: "16px", fontWeight: 700, color: "var(--text-primary)", marginBottom: "16px" }}>
          Deterministic Policy Gate Distribution
        </h3>

        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", marginBottom: "4px" }}>
              <span style={{ color: "var(--status-pass-text)" }}>Auto-Passed ({passed})</span>
              <span>{fpyRate}%</span>
            </div>
            <div style={{ background: "var(--bg-surface)", height: "8px", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
              <div style={{ background: "#10b981", height: "100%", width: `${fpyRate}%` }} />
            </div>
          </div>

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", marginBottom: "4px" }}>
              <span style={{ color: "var(--status-hold-text)" }}>Policy Hold ({held})</span>
              <span>{holdRate}%</span>
            </div>
            <div style={{ background: "var(--bg-surface)", height: "8px", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
              <div style={{ background: "#f43f5e", height: "100%", width: `${holdRate}%` }} />
            </div>
          </div>

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", marginBottom: "4px" }}>
              <span style={{ color: "var(--status-review-text)" }}>Review Required ({review})</span>
              <span>{reviewRate}%</span>
            </div>
            <div style={{ background: "var(--bg-surface)", height: "8px", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
              <div style={{ background: "#f59e0b", height: "100%", width: `${reviewRate}%` }} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
