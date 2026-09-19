import React, { useState } from "react";
import { QueueItem } from "../types/evaluation";
import { Search, ArrowRight } from "lucide-react";

interface QueueDashboardProps {
  items: QueueItem[];
  currentStatus: string;
  onStatusChange: (status: string) => void;
  onSelectCall: (saleId: string) => void;
  tenantId: string;
  onTenantChange: (tenant: string) => void;
  onRefresh: () => void;
}

export const QueueDashboard: React.FC<QueueDashboardProps> = ({
  items,
  currentStatus,
  onStatusChange,
  onSelectCall,
  tenantId,
  onTenantChange,
  onRefresh,
}) => {
  const [searchTerm, setSearchTerm] = useState("");

  const filteredItems = items.filter((item) => {
    const term = searchTerm.toLowerCase();
    return (
      item.sale_id.toLowerCase().includes(term) ||
      (item.agent_name && item.agent_name.toLowerCase().includes(term)) ||
      (item.customer_name && item.customer_name.toLowerCase().includes(term)) ||
      (item.campaign_name && item.campaign_name.toLowerCase().includes(term))
    );
  });

  // Calculate KPIs
  const totalCalls = items.length;
  const passedCalls = items.filter((i) => i.status === "PASSED").length;
  const heldCalls = items.filter((i) => i.status === "HELD").length;
  const reviewCalls = items.filter((i) => i.status === "REVIEW_REQUIRED").length;
  const fpyRate = totalCalls > 0 ? Math.round((passedCalls / totalCalls) * 100) : 0;

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "PASSED":
        return { bg: "var(--status-pass-bg)", border: "var(--status-pass-border)", text: "var(--status-pass-text)" };
      case "HELD":
        return { bg: "var(--status-hold-bg)", border: "var(--status-hold-border)", text: "var(--status-hold-text)" };
      case "REVIEW_REQUIRED":
        return { bg: "var(--status-review-bg)", border: "var(--status-review-border)", text: "var(--status-review-text)" };
      default:
        return { bg: "var(--bg-surface)", border: "var(--border-subtle)", text: "var(--text-secondary)" };
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Header & Tenant Selector */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h2 style={{ fontSize: "24px", fontWeight: 800, color: "var(--text-primary)" }}>
            QA Audit & Compliance Queue
          </h2>
          <p style={{ fontSize: "14px", color: "var(--text-secondary)", marginTop: "4px" }}>
            Deterministic post-call verification, DMO/VDO adherence, and CRM rate diffing
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <label style={{ fontSize: "13px", color: "var(--text-muted)" }}>Tenant:</label>
          <select
            value={tenantId}
            onChange={(e) => onTenantChange(e.target.value)}
            style={{
              padding: "8px 14px",
              borderRadius: "var(--radius-sm)",
              background: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              color: "var(--brand-cyan)",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <option value="retailer-cimet-01">retailer-cimet-01</option>
            <option value="retailer-prod-001">retailer-prod-001</option>
            <option value="retailer-01">retailer-01</option>
          </select>

          <button
            onClick={onRefresh}
            style={{
              padding: "8px 14px",
              borderRadius: "var(--radius-sm)",
              background: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-secondary)",
              fontSize: "13px",
              cursor: "pointer",
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px" }}>
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", padding: "18px" }}>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>First-Pass Yield (FPY)</span>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--brand-cyan)", marginTop: "6px" }}>{fpyRate}%</div>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Auto-submitted clean sales</span>
        </div>

        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", padding: "18px" }}>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Pending QA Holds</span>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "#fb7185", marginTop: "6px" }}>{heldCalls}</div>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Critical non-compliance</span>
        </div>

        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", padding: "18px" }}>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Review Required</span>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "#fbbf24", marginTop: "6px" }}>{reviewCalls}</div>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Ambiguous / Low confidence</span>
        </div>

        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", padding: "18px" }}>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Passed Sales</span>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "#34d399", marginTop: "6px" }}>{passedCalls}</div>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Auto-submitted to CRM</span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "16px" }}>
        <div style={{ display: "flex", gap: "8px" }}>
          {["ALL", "HELD", "REVIEW_REQUIRED", "PASSED"].map((st) => (
            <button
              key={st}
              onClick={() => onStatusChange(st)}
              style={{
                padding: "8px 16px",
                borderRadius: "var(--radius-full)",
                fontSize: "12px",
                fontWeight: 700,
                cursor: "pointer",
                border: "none",
                background: currentStatus === st ? "var(--brand-cyan)" : "var(--bg-card)",
                color: currentStatus === st ? "#090d16" : "var(--text-secondary)",
                transition: "var(--transition-fast)",
              }}
            >
              {st.replace("_", " ")}
            </button>
          ))}
        </div>

        <div style={{ position: "relative", width: "280px" }}>
          <Search size={16} color="var(--text-muted)" style={{ position: "absolute", left: "12px", top: "10px" }} />
          <input
            type="text"
            placeholder="Search lead, agent, campaign..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: "100%",
              padding: "8px 12px 8px 36px",
              borderRadius: "var(--radius-md)",
              background: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-primary)",
              fontSize: "13px",
            }}
          />
        </div>
      </div>

      {/* Queue Table */}
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          overflow: "hidden",
          boxShadow: "var(--shadow-md)",
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
          <thead>
            <tr style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-subtle)" }}>
              <th style={{ padding: "12px 16px", fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase" }}>Sale / Lead</th>
              <th style={{ padding: "12px 16px", fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase" }}>Customer</th>
              <th style={{ padding: "12px 16px", fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase" }}>Agent</th>
              <th style={{ padding: "12px 16px", fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase" }}>Campaign</th>
              <th style={{ padding: "12px 16px", fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase" }}>Gate Status</th>
              <th style={{ padding: "12px 16px", fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase" }}>Score</th>
              <th style={{ padding: "12px 16px", fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase" }}>Reason Code</th>
              <th style={{ padding: "12px 16px", fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", textAlign: "right" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredItems.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>
                  No calls currently in this queue
                </td>
              </tr>
            ) : (
              filteredItems.map((item) => {
                const badge = getStatusBadge(item.status);
                return (
                  <tr
                    key={item.decision_id}
                    style={{
                      borderBottom: "1px solid var(--border-subtle)",
                      transition: "var(--transition-fast)",
                    }}
                  >
                    <td style={{ padding: "14px 16px", fontFamily: "var(--font-mono)", fontSize: "13px", fontWeight: 600, color: "var(--brand-cyan)" }}>
                      {item.sale_id}
                    </td>
                    <td style={{ padding: "14px 16px", fontSize: "14px", color: "var(--text-primary)" }}>
                      {item.customer_name || "N/A"}
                    </td>
                    <td style={{ padding: "14px 16px", fontSize: "14px", color: "var(--text-secondary)" }}>
                      {item.agent_name || "Agent"}
                    </td>
                    <td style={{ padding: "14px 16px", fontSize: "13px", color: "var(--text-muted)" }}>
                      {item.campaign_name || "Standard"}
                    </td>
                    <td style={{ padding: "14px 16px" }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 10px",
                          borderRadius: "var(--radius-full)",
                          fontSize: "11px",
                          fontWeight: 700,
                          background: badge.bg,
                          border: `1px solid ${badge.border}`,
                          color: badge.text,
                        }}
                      >
                        {item.status}
                      </span>
                    </td>
                    <td style={{ padding: "14px 16px", fontSize: "14px", fontWeight: 700, color: item.overall_score && item.overall_score >= 85 ? "#34d399" : item.overall_score && item.overall_score >= 70 ? "#fbbf24" : "#fb7185" }}>
                      {item.overall_score !== null && item.overall_score !== undefined ? `${item.overall_score}%` : "-"}
                    </td>
                    <td style={{ padding: "14px 16px", fontSize: "12px", color: "var(--text-muted)" }}>
                      {item.decision_reason_code}
                    </td>
                    <td style={{ padding: "14px 16px", textAlign: "right" }}>
                      <button
                        onClick={() => onSelectCall(item.sale_id)}
                        style={{
                          background: "var(--bg-surface)",
                          border: "1px solid var(--border-accent)",
                          borderRadius: "var(--radius-sm)",
                          padding: "6px 12px",
                          color: "var(--text-primary)",
                          fontSize: "12px",
                          fontWeight: 600,
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          transition: "var(--transition-fast)",
                        }}
                      >
                        Inspect
                        <ArrowRight size={14} />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
