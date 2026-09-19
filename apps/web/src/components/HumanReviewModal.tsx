import React, { useState } from "react";
import { submitHumanReview } from "../api/evaluations";
import { HumanReview } from "../types/evaluation";
import { X, CheckCircle, AlertCircle, Ban, History } from "lucide-react";

interface HumanReviewModalProps {
  gateDecisionId: string;
  pastReviews?: HumanReview[];
  onClose: () => void;
  onReviewSubmitted: (review: HumanReview) => void;
}

export const HumanReviewModal: React.FC<HumanReviewModalProps> = ({
  gateDecisionId,
  pastReviews = [],
  onClose,
  onReviewSubmitted,
}) => {
  const [action, setAction] = useState<"OVERRIDE_TO_PASS" | "CONFIRM_HOLD" | "CANCEL_SALE">("CONFIRM_HOLD");
  const [reasonNotes, setReasonNotes] = useState("");
  const [reviewerRole, setReviewerRole] = useState("qa_auditor");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (reasonNotes.trim().length < 10) {
      setErrorMsg("Reason notes must be at least 10 characters long.");
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const review = await submitHumanReview(gateDecisionId, action, reasonNotes.trim(), reviewerRole);
      onReviewSubmitted(review);
      onClose();
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to submit human review.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.75)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: "20px",
      }}
    >
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-accent)",
          borderRadius: "var(--radius-lg)",
          width: "100%",
          maxWidth: "560px",
          padding: "24px",
          boxShadow: "var(--shadow-lg)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px" }}>
          <h3 style={{ fontSize: "18px", fontWeight: 700, color: "var(--text-primary)" }}>
            Submit QA Auditor Decision
          </h3>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
            }}
          >
            <X size={20} />
          </button>
        </div>

        {errorMsg && (
          <div
            style={{
              background: "rgba(244, 63, 94, 0.15)",
              border: "1px solid var(--status-hold-border)",
              borderRadius: "var(--radius-sm)",
              padding: "10px 14px",
              color: "#fb7185",
              fontSize: "13px",
              marginBottom: "16px",
            }}
          >
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {/* Action selection buttons */}
          <div>
            <label style={{ display: "block", fontSize: "13px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "8px" }}>
              Select Human Review Action
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px" }}>
              <button
                type="button"
                onClick={() => setAction("OVERRIDE_TO_PASS")}
                style={{
                  padding: "12px",
                  borderRadius: "var(--radius-md)",
                  border: action === "OVERRIDE_TO_PASS" ? "2px solid #10b981" : "1px solid var(--border-subtle)",
                  background: action === "OVERRIDE_TO_PASS" ? "var(--status-pass-bg)" : "var(--bg-surface)",
                  color: action === "OVERRIDE_TO_PASS" ? "var(--status-pass-text)" : "var(--text-secondary)",
                  cursor: "pointer",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "12px",
                  fontWeight: 700,
                }}
              >
                <CheckCircle size={18} />
                Override to Pass
              </button>

              <button
                type="button"
                onClick={() => setAction("CONFIRM_HOLD")}
                style={{
                  padding: "12px",
                  borderRadius: "var(--radius-md)",
                  border: action === "CONFIRM_HOLD" ? "2px solid #f59e0b" : "1px solid var(--border-subtle)",
                  background: action === "CONFIRM_HOLD" ? "var(--status-review-bg)" : "var(--bg-surface)",
                  color: action === "CONFIRM_HOLD" ? "var(--status-review-text)" : "var(--text-secondary)",
                  cursor: "pointer",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "12px",
                  fontWeight: 700,
                }}
              >
                <AlertCircle size={18} />
                Confirm Hold
              </button>

              <button
                type="button"
                onClick={() => setAction("CANCEL_SALE")}
                style={{
                  padding: "12px",
                  borderRadius: "var(--radius-md)",
                  border: action === "CANCEL_SALE" ? "2px solid #f43f5e" : "1px solid var(--border-subtle)",
                  background: action === "CANCEL_SALE" ? "var(--status-hold-bg)" : "var(--bg-surface)",
                  color: action === "CANCEL_SALE" ? "var(--status-hold-text)" : "var(--text-secondary)",
                  cursor: "pointer",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "12px",
                  fontWeight: 700,
                }}
              >
                <Ban size={18} />
                Cancel Sale
              </button>
            </div>
          </div>

          <div>
            <label style={{ display: "block", fontSize: "13px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
              Auditor Role
            </label>
            <select
              value={reviewerRole}
              onChange={(e) => setReviewerRole(e.target.value)}
              style={{
                width: "100%",
                padding: "8px 12px",
                borderRadius: "var(--radius-sm)",
                background: "var(--bg-surface)",
                border: "1px solid var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            >
              <option value="qa_auditor">QA Compliance Auditor</option>
              <option value="team_lead">Team Lead / Supervisor</option>
              <option value="operations_manager">Operations Manager</option>
            </select>
          </div>

          <div>
            <label style={{ display: "block", fontSize: "13px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
              Justification & Notes (Mandatory, min 10 chars)
            </label>
            <textarea
              value={reasonNotes}
              onChange={(e) => setReasonNotes(e.target.value)}
              placeholder="Provide exact regulatory or commercial reasoning for this review decision..."
              rows={4}
              style={{
                width: "100%",
                padding: "10px 12px",
                borderRadius: "var(--radius-sm)",
                background: "var(--bg-surface)",
                border: "1px solid var(--border-subtle)",
                color: "var(--text-primary)",
                resize: "vertical",
              }}
            />
          </div>

          {/* Past reviews trail */}
          {pastReviews.length > 0 && (
            <div style={{ background: "var(--bg-surface)", borderRadius: "var(--radius-sm)", padding: "10px 12px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "6px", fontSize: "12px", fontWeight: 600, color: "var(--text-muted)" }}>
                <History size={14} />
                Audit Trail ({pastReviews.length})
              </div>
              {pastReviews.map((pr) => (
                <div key={pr.review_id} style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "4px" }}>
                  <strong>{pr.action}</strong> by {pr.reviewer_id} ({pr.reviewer_role}): "{pr.reason_notes}"
                </div>
              ))}
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "10px" }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: "8px 16px",
                borderRadius: "var(--radius-sm)",
                background: "var(--bg-surface)",
                border: "1px solid var(--border-subtle)",
                color: "var(--text-secondary)",
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              style={{
                padding: "8px 20px",
                borderRadius: "var(--radius-sm)",
                background: "var(--brand-cyan)",
                color: "#090d16",
                border: "none",
                fontWeight: 700,
                cursor: isSubmitting ? "not-allowed" : "pointer",
                opacity: isSubmitting ? 0.6 : 1,
              }}
            >
              {isSubmitting ? "Submitting..." : "Submit Decision"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
