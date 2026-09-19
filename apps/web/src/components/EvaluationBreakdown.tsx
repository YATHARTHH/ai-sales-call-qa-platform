import React, { useState } from "react";
import { EvaluationLineage } from "../types/evaluation";
import { CheckCircle2, XCircle, AlertTriangle, PlayCircle, ShieldCheck, Scale, Mic } from "lucide-react";

interface EvaluationBreakdownProps {
  evaluation: EvaluationLineage;
  onSeekToEvidence: (startMs: number) => void;
}

export const EvaluationBreakdown: React.FC<EvaluationBreakdownProps> = ({
  evaluation,
  onSeekToEvidence,
}) => {
  const [activeTab, setActiveTab] = useState<"ALL" | "TIER_A" | "TIER_B" | "TIER_C">("ALL");

  const gate = evaluation.gate_decision;
  const results = evaluation.results || [];

  // Calculate overall score from results
  const scoreable = results.filter((r) => r.score_numeric !== null);
  const overallScore =
    scoreable.length > 0
      ? Math.round(scoreable.reduce((acc, r) => acc + (r.score_numeric || 0), 0) / scoreable.length)
      : null;

  const formatTimestamp = (ms: number) => {
    const totalSec = Math.floor(ms / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const getGateStyle = (status?: string) => {
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

  const gateStyle = getGateStyle(gate?.status);

  // Group checks into Tiers
  const tierAChecks = results.filter((r) => r.check_id.includes("script") || r.check_id.includes("dmo") || r.check_id.includes("eic") || r.check_id.includes("verbatim") || r.check_id.includes("t_and_c"));
  const tierBChecks = results.filter((r) => r.check_id.includes("rate") || r.check_id.includes("factual") || r.check_id.includes("tariff") || r.check_id.includes("supply"));
  const tierCChecks = results.filter((r) => r.check_id.includes("silence") || r.check_id.includes("dead_air") || r.check_id.includes("behavior") || r.check_id.includes("sentiment"));

  const displayedChecks =
    activeTab === "TIER_A"
      ? tierAChecks
      : activeTab === "TIER_B"
      ? tierBChecks
      : activeTab === "TIER_C"
      ? tierCChecks
      : results;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Top Gate & Score Summary Card */}
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          padding: "20px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          boxShadow: "var(--shadow-md)",
        }}
      >
        <div>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>
            Deterministic Policy Decision
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginTop: "6px" }}>
            <span
              style={{
                display: "inline-block",
                padding: "6px 14px",
                borderRadius: "var(--radius-full)",
                fontSize: "14px",
                fontWeight: 800,
                letterSpacing: "0.5px",
                background: gateStyle.bg,
                border: `1px solid ${gateStyle.border}`,
                color: gateStyle.text,
              }}
            >
              {gate?.status || "PENDING"}
            </span>

            <span style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
              {gate?.decision_reason_code || "Awaiting policy gate"}
            </span>
          </div>
        </div>

        <div style={{ textAlign: "right" }}>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>
            Weighted QA Score
          </span>
          <div style={{ fontSize: "32px", fontWeight: 800, color: overallScore && overallScore >= 85 ? "var(--status-pass-text)" : overallScore && overallScore >= 70 ? "var(--status-review-text)" : "var(--status-hold-text)" }}>
            {overallScore !== null ? `${overallScore}%` : "N/A"}
          </div>
        </div>
      </div>

      {/* Blocking Checks Warning Banner */}
      {gate?.blocking_check_ids && gate.blocking_check_ids.length > 0 && (
        <div
          style={{
            background: "rgba(244, 63, 94, 0.1)",
            border: "1px solid var(--status-hold-border)",
            borderRadius: "var(--radius-md)",
            padding: "12px 16px",
            display: "flex",
            alignItems: "center",
            gap: "10px",
          }}
        >
          <AlertTriangle size={18} color="#f43f5e" />
          <span style={{ fontSize: "13px", color: "#fb7185", fontWeight: 500 }}>
            Blocking non-compliance checks: {gate.blocking_check_ids.join(", ")}
          </span>
        </div>
      )}

      {/* Tier Tabs */}
      <div style={{ display: "flex", gap: "8px", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "10px" }}>
        {[
          { id: "ALL", label: `All Checks (${results.length})` },
          { id: "TIER_A", label: `Tier A: Verbatim (${tierAChecks.length})`, icon: ShieldCheck },
          { id: "TIER_B", label: `Tier B: Factual (${tierBChecks.length})`, icon: Scale },
          { id: "TIER_C", label: `Tier C: Behavioral (${tierCChecks.length})`, icon: Mic },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            style={{
              padding: "6px 14px",
              borderRadius: "var(--radius-sm)",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
              border: "none",
              background: activeTab === tab.id ? "var(--brand-cyan)" : "var(--bg-surface)",
              color: activeTab === tab.id ? "#090d16" : "var(--text-secondary)",
              transition: "var(--transition-fast)",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Checks and Evidence List */}
      <div style={{ display: "flex", flexDirection: "column", gap: "12px", overflowY: "auto", maxHeight: "560px" }}>
        {displayedChecks.map((check) => {
          const isPass = check.result === "PASS";
          const isFail = check.result === "FAIL";

          return (
            <div
              key={check.result_id}
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-md)",
                padding: "16px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "8px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  {isPass ? (
                    <CheckCircle2 size={18} color="#10b981" />
                  ) : isFail ? (
                    <XCircle size={18} color="#f43f5e" />
                  ) : (
                    <AlertTriangle size={18} color="#f59e0b" />
                  )}
                  <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)" }}>
                    {check.check_id}
                  </span>
                  {check.is_critical && (
                    <span style={{ fontSize: "10px", fontWeight: 700, padding: "1px 6px", borderRadius: "4px", background: "rgba(244, 63, 94, 0.2)", color: "#f43f5e" }}>
                      CRITICAL
                    </span>
                  )}
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  {check.confidence !== null && (
                    <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                      Conf: {Math.round(check.confidence * 100)}%
                    </span>
                  )}
                  <span
                    style={{
                      fontSize: "12px",
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: "var(--radius-full)",
                      background: isPass ? "var(--status-pass-bg)" : isFail ? "var(--status-hold-bg)" : "var(--status-review-bg)",
                      color: isPass ? "var(--status-pass-text)" : isFail ? "var(--status-hold-text)" : "var(--status-review-text)",
                    }}
                  >
                    {check.result}
                  </span>
                </div>
              </div>

              {/* Evidence Items */}
              {check.evidence && check.evidence.length > 0 && (
                <div style={{ marginTop: "10px", display: "flex", flexDirection: "column", gap: "8px" }}>
                  {check.evidence.map((ev) => (
                    <div
                      key={ev.evidence_id}
                      style={{
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: "var(--radius-sm)",
                        padding: "10px 12px",
                        display: "flex",
                        flexDirection: "column",
                        gap: "6px",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <button
                          onClick={() => onSeekToEvidence(ev.start_ms)}
                          style={{
                            background: "rgba(6, 182, 212, 0.15)",
                            border: "1px solid rgba(6, 182, 212, 0.3)",
                            color: "var(--brand-cyan)",
                            borderRadius: "var(--radius-full)",
                            padding: "2px 10px",
                            fontSize: "11px",
                            fontWeight: 600,
                            cursor: "pointer",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "5px",
                          }}
                        >
                          <PlayCircle size={12} />
                          Jump to {formatTimestamp(ev.start_ms)}
                        </button>

                        <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                          Speaker: {ev.speaker}
                        </span>
                      </div>

                      <p style={{ fontSize: "13px", color: "var(--text-secondary)", fontStyle: "italic" }}>
                        "{ev.transcript_excerpt}"
                      </p>

                      {ev.ai_explanation && (
                        <p style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                          {ev.ai_explanation}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
