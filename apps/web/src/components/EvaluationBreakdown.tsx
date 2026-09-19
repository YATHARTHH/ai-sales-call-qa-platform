import React, { useState } from "react";
import { CheckResult, EvaluationLineage } from "../types/evaluation";
import {
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Mic,
  PlayCircle,
  Scale,
  ShieldCheck,
  XCircle,
} from "lucide-react";

interface EvaluationBreakdownProps {
  evaluation: EvaluationLineage;
  onSeekToEvidence: (startMs: number) => void;
}

type Tier = "ALL" | "TIER_A" | "TIER_B" | "TIER_C";

const formatTimestamp = (ms: number) => {
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
};

const formatDate = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : null;

/** Display label for a check, preferring the human name over the internal id. */
const checkLabel = (check: CheckResult) => check.check_name || check.check_code || check.check_id;

/** Tier is derived from the check code, which encodes it, rather than guessed from the id. */
const tierOf = (check: CheckResult): Tier => {
  const code = (check.check_code || check.check_id).toUpperCase();
  if (code.startsWith("VERBATIM")) return "TIER_A";
  if (code.startsWith("FACTUAL")) return "TIER_B";
  if (code.startsWith("BEHAVIOUR") || code.startsWith("BEHAVIOR")) return "TIER_C";
  return "ALL";
};

const outcomeStyle = (result: string) => {
  switch (result) {
    case "PASS":
      return { bg: "var(--status-pass-bg)", text: "var(--status-pass-text)", colour: "#10b981" };
    case "FAIL":
      return { bg: "var(--status-hold-bg)", text: "var(--status-hold-text)", colour: "#f43f5e" };
    default:
      return { bg: "var(--status-review-bg)", text: "var(--status-review-text)", colour: "#f59e0b" };
  }
};

const OutcomeIcon: React.FC<{ result: string }> = ({ result }) => {
  if (result === "PASS") return <CheckCircle2 size={18} color="#10b981" />;
  if (result === "FAIL") return <XCircle size={18} color="#f43f5e" />;
  if (result === "NOT_EVALUABLE" || result === "UNSUPPORTED")
    return <HelpCircle size={18} color="#94a3b8" />;
  return <AlertTriangle size={18} color="#f59e0b" />;
};

/**
 * Provenance strip: the exact rule version that was live on the call date, plus the regulation it
 * comes from. Traceability is the point — a score has to be defensible in a retailer audit.
 */
const CheckProvenance: React.FC<{ check: CheckResult }> = ({ check }) => {
  const effectiveFrom = formatDate(check.effective_from);
  const effectiveTo = formatDate(check.effective_to);

  const parts: string[] = [];
  if (check.check_version_number != null) parts.push(`rule v${check.check_version_number}`);
  if (effectiveFrom) parts.push(`in force from ${effectiveFrom}${effectiveTo ? ` to ${effectiveTo}` : ""}`);
  if (check.jurisdiction) parts.push(check.jurisdiction);

  if (parts.length === 0 && !check.regulatory_reference) return null;

  return (
    <div
      style={{
        marginTop: "8px",
        paddingTop: "8px",
        borderTop: "1px dashed var(--border-subtle)",
        display: "flex",
        flexWrap: "wrap",
        gap: "6px 14px",
        fontSize: "11px",
        color: "var(--text-muted)",
      }}
    >
      {parts.length > 0 && <span>{parts.join(" · ")}</span>}
      {check.regulatory_reference && (
        <span style={{ fontStyle: "italic" }}>{check.regulatory_reference}</span>
      )}
      <span style={{ opacity: 0.7 }}>version id {check.check_version_id}</span>
    </div>
  );
};

/** Expected vs observed, so the reviewer sees the actual mismatch without opening the transcript. */
const ValueDiff: React.FC<{ expected: any; observed: any; matched: boolean }> = ({
  expected,
  observed,
  matched,
}) => {
  if (expected == null && observed == null) return null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center", fontSize: "12px" }}>
      <span style={{ color: "var(--text-muted)" }}>CRM</span>
      <code
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "4px",
          padding: "1px 6px",
          color: "var(--text-primary)",
        }}
      >
        {String(expected)}
      </code>
      <span style={{ color: "var(--text-muted)" }}>heard</span>
      <code
        style={{
          background: matched ? "var(--status-pass-bg)" : "var(--status-hold-bg)",
          border: `1px solid ${matched ? "var(--status-pass-border)" : "var(--status-hold-border)"}`,
          borderRadius: "4px",
          padding: "1px 6px",
          color: matched ? "var(--status-pass-text)" : "var(--status-hold-text)",
        }}
      >
        {String(observed)}
      </code>
    </div>
  );
};

export const EvaluationBreakdown: React.FC<EvaluationBreakdownProps> = ({
  evaluation,
  onSeekToEvidence,
}) => {
  const [activeTab, setActiveTab] = useState<Tier>("ALL");

  const gate = evaluation.gate_decision;
  const results = evaluation.results || [];

  // The score the gate actually decided on, not a recomputed approximation of it.
  const overallScore = gate?.overall_score ?? null;

  const byTier = (tier: Tier) => results.filter((r) => tierOf(r) === tier);
  const tierAChecks = byTier("TIER_A");
  const tierBChecks = byTier("TIER_B");
  const tierCChecks = byTier("TIER_C");

  const displayedChecks =
    activeTab === "ALL"
      ? results
      : activeTab === "TIER_A"
      ? tierAChecks
      : activeTab === "TIER_B"
      ? tierBChecks
      : tierCChecks;

  const labelById = new Map(results.map((r) => [r.check_id, checkLabel(r)]));
  const blockingLabels = (gate?.blocking_check_ids || []).map((id) => labelById.get(id) || id);

  const gateStyle = (() => {
    switch (gate?.status) {
      case "PASSED":
        return { bg: "var(--status-pass-bg)", border: "var(--status-pass-border)", text: "var(--status-pass-text)" };
      case "HELD":
        return { bg: "var(--status-hold-bg)", border: "var(--status-hold-border)", text: "var(--status-hold-text)" };
      case "REVIEW_REQUIRED":
        return { bg: "var(--status-review-bg)", border: "var(--status-review-border)", text: "var(--status-review-text)" };
      default:
        return { bg: "var(--bg-surface)", border: "var(--border-subtle)", text: "var(--text-secondary)" };
    }
  })();

  const scoreColour =
    overallScore == null
      ? "var(--text-muted)"
      : overallScore >= 85
      ? "var(--status-pass-text)"
      : overallScore >= 70
      ? "var(--status-review-text)"
      : "var(--status-hold-text)";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Gate decision and score */}
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          padding: "20px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "16px",
          flexWrap: "wrap",
          boxShadow: "var(--shadow-md)",
        }}
      >
        <div>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>
            Deterministic Policy Decision
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginTop: "6px", flexWrap: "wrap" }}>
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
            {gate?.policy_version && (
              <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                policy {gate.policy_version}
              </span>
            )}
          </div>
        </div>

        <div style={{ textAlign: "right" }}>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>
            Weighted QA Score
          </span>
          <div style={{ fontSize: "32px", fontWeight: 800, color: scoreColour }}>
            {overallScore != null ? `${overallScore}%` : "N/A"}
          </div>
        </div>
      </div>

      {/* Which criteria are holding the sale */}
      {blockingLabels.length > 0 && (
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
            Holding this sale: {blockingLabels.join(", ")}
          </span>
        </div>
      )}

      {/* Tier tabs */}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "10px" }}>
        {[
          { id: "ALL" as Tier, label: `All Checks (${results.length})`, icon: null },
          { id: "TIER_A" as Tier, label: `Tier A · Verbatim (${tierAChecks.length})`, icon: ShieldCheck },
          { id: "TIER_B" as Tier, label: `Tier B · Factual (${tierBChecks.length})`, icon: Scale },
          { id: "TIER_C" as Tier, label: `Tier C · Behaviour (${tierCChecks.length})`, icon: Mic },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
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

      {/* Checks and grounded evidence */}
      <div style={{ display: "flex", flexDirection: "column", gap: "12px", overflowY: "auto", maxHeight: "560px" }}>
        {displayedChecks.map((check) => {
          const style = outcomeStyle(check.result);
          const isBlocking = (gate?.blocking_check_ids || []).includes(check.check_id);

          return (
            <div
              key={check.result_id}
              style={{
                background: "var(--bg-card)",
                border: `1px solid ${isBlocking ? "var(--status-hold-border)" : "var(--border-subtle)"}`,
                borderRadius: "var(--radius-md)",
                padding: "16px",
              }}
            >
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                  <OutcomeIcon result={check.result} />
                  <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)" }}>
                    {checkLabel(check)}
                  </span>
                  {check.is_critical && (
                    <span style={{ fontSize: "10px", fontWeight: 700, padding: "1px 6px", borderRadius: "4px", background: "rgba(244, 63, 94, 0.2)", color: "#f43f5e" }}>
                      CRITICAL
                    </span>
                  )}
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  {check.confidence !== null && check.confidence !== undefined && (
                    <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                      Conf {Math.round(check.confidence * 100)}%
                    </span>
                  )}
                  <span
                    style={{
                      fontSize: "12px",
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: "var(--radius-full)",
                      background: style.bg,
                      color: style.text,
                    }}
                  >
                    {check.result}
                  </span>
                </div>
              </div>

              {check.reason_codes && check.reason_codes.length > 0 && (
                <div style={{ marginTop: "6px", fontSize: "11px", color: "var(--text-muted)" }}>
                  {check.reason_codes.join(" · ")}
                </div>
              )}

              {/* Grounded evidence */}
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
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", flexWrap: "wrap" }}>
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
                          {ev.speaker}
                          {ev.comparison_source ? ` · ${ev.comparison_source}` : ""}
                        </span>
                      </div>

                      <ValueDiff
                        expected={ev.expected_value}
                        observed={ev.observed_value}
                        matched={ev.evidence_type === "SUPPORTING"}
                      />

                      <p style={{ fontSize: "13px", color: "var(--text-secondary)", fontStyle: "italic" }}>
                        "{ev.transcript_excerpt}"
                      </p>

                      {ev.ai_explanation && (
                        <p style={{ fontSize: "12px", color: "var(--text-muted)" }}>{ev.ai_explanation}</p>
                      )}

                      {ev.expected_value_source && (
                        <span style={{ fontSize: "10px", color: "var(--text-muted)", opacity: 0.8 }}>
                          expected from {ev.expected_value_source}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}

              <CheckProvenance check={check} />
            </div>
          );
        })}
      </div>
    </div>
  );
};
