import React, { useEffect, useState } from "react";
import { fetchEvaluation, rerunEvaluation } from "../api/evaluations";
import { fetchTranscriptSegments } from "../api/transcripts";
import { EvaluationLineage } from "../types/evaluation";
import { TranscriptSegment } from "../types/transcript";
import { AudioPlayer } from "../components/AudioPlayer";
import { TranscriptViewer } from "../components/TranscriptViewer";
import { EvaluationBreakdown } from "../components/EvaluationBreakdown";
import { HumanReviewModal } from "../components/HumanReviewModal";
import { ArrowLeft, RefreshCw, CheckSquare, Shield, FileText } from "lucide-react";

interface CallReviewProps {
  saleId: string;
  onBack: () => void;
}

export const CallReview: React.FC<CallReviewProps> = ({ saleId, onBack }) => {
  const [evaluation, setEvaluation] = useState<EvaluationLineage | null>(null);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Audio & Transcript sync states
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const [seekTargetMs, setSeekTargetMs] = useState<number | null>(null);
  const [activeEvidenceMs, setActiveEvidenceMs] = useState<number | null>(null);

  // Review modal
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [isRerunning, setIsRerunning] = useState(false);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const evalData = await fetchEvaluation(saleId);
      setEvaluation(evalData);

      if (evalData.transcript_id) {
        const segData = await fetchTranscriptSegments(evalData.transcript_id, 300);
        setSegments(segData.items);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load call details.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [saleId]);

  const handleSeekTo = (ms: number) => {
    setSeekTargetMs(ms);
    setActiveEvidenceMs(ms);
  };

  const handleRerun = async () => {
    if (!evaluation) return;
    try {
      setIsRerunning(true);
      await rerunEvaluation(evaluation.run_id, "EVALUATION_ONLY", "Auditor initiated rerun");
      alert("Evaluation rerun scheduled successfully.");
      await loadData();
    } catch (err: any) {
      alert(`Rerun failed: ${err.message}`);
    } finally {
      setIsRerunning(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: "60px", textAlign: "center", color: "var(--text-secondary)" }}>
        Loading call recording and evaluation evidence...
      </div>
    );
  }

  if (error || !evaluation) {
    return (
      <div style={{ padding: "40px", textAlign: "center" }}>
        <p style={{ color: "#fb7185", marginBottom: "16px" }}>{error || "Call not found."}</p>
        <button
          onClick={onBack}
          style={{
            padding: "8px 16px",
            borderRadius: "var(--radius-sm)",
            background: "var(--bg-surface)",
            border: "1px solid var(--border-subtle)",
            color: "var(--text-primary)",
            cursor: "pointer",
          }}
        >
          Back to Queue
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Top Navigation & Action Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--border-subtle)",
          paddingBottom: "16px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <button
            onClick={onBack}
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-sm)",
              padding: "8px 12px",
              color: "var(--text-secondary)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <ArrowLeft size={16} />
            Queue
          </button>

          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <h2 style={{ fontSize: "20px", fontWeight: 800, color: "var(--text-primary)" }}>
                Call Inspection: {evaluation.sale_id}
              </h2>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                ({evaluation.tenant_id})
              </span>
            </div>
            <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
              Run ID: {evaluation.run_id} | Policy: {evaluation.provenance.policy_version}
            </span>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <button
            onClick={handleRerun}
            disabled={isRerunning}
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-sm)",
              padding: "8px 14px",
              color: "var(--text-secondary)",
              fontSize: "13px",
              fontWeight: 600,
              cursor: isRerunning ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <RefreshCw size={14} className={isRerunning ? "animate-spin" : ""} />
            Rerun
          </button>

          {evaluation.gate_decision && (
            <button
              onClick={() => setShowReviewModal(true)}
              style={{
                background: "var(--brand-cyan)",
                color: "#090d16",
                border: "none",
                borderRadius: "var(--radius-sm)",
                padding: "8px 18px",
                fontSize: "13px",
                fontWeight: 700,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "6px",
                boxShadow: "var(--shadow-glow-cyan)",
              }}
            >
              <CheckSquare size={16} />
              Submit Review
            </button>
          )}
        </div>
      </div>

      {/* Main Split View: Left Transcript, Right Evaluation Breakdown */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
        {/* Left Column: Interactive Diarized Transcript */}
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-lg)",
            padding: "20px",
            display: "flex",
            flexDirection: "column",
            gap: "16px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "10px" }}>
            <h3 style={{ fontSize: "15px", fontWeight: 700, display: "flex", alignItems: "center", gap: "8px" }}>
              <FileText size={16} color="var(--brand-cyan)" />
              Diarized Transcript
            </h3>
            <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
              {segments.length} Utterances (PCI Redacted)
            </span>
          </div>

          <TranscriptViewer
            segments={segments}
            currentTimeMs={currentTimeMs}
            onSeek={handleSeekTo}
            activeEvidenceStartMs={activeEvidenceMs}
          />
        </div>

        {/* Right Column: Multi-Tier Evaluation Breakdown */}
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-lg)",
            padding: "20px",
            display: "flex",
            flexDirection: "column",
            gap: "16px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "10px" }}>
            <h3 style={{ fontSize: "15px", fontWeight: 700, display: "flex", alignItems: "center", gap: "8px" }}>
              <Shield size={16} color="var(--brand-cyan)" />
              Deterministic Evaluation & Evidence
            </h3>
            <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
              {evaluation.results.length} Checks Resolved
            </span>
          </div>

          <EvaluationBreakdown evaluation={evaluation} onSeekToEvidence={handleSeekTo} />
        </div>
      </div>

      {/* Persistent Audio Player Bar */}
      <div style={{ position: "sticky", bottom: "20px", zIndex: 100 }}>
        <AudioPlayer
          recordingId={evaluation.recording_id}
          currentTimeMs={currentTimeMs}
          onTimeUpdate={setCurrentTimeMs}
          seekTargetMs={seekTargetMs}
          onSeekHandled={() => setSeekTargetMs(null)}
        />
      </div>

      {/* Human Review Override Modal */}
      {showReviewModal && evaluation.gate_decision && (
        <HumanReviewModal
          gateDecisionId={evaluation.gate_decision.decision_id}
          pastReviews={evaluation.human_reviews}
          onClose={() => setShowReviewModal(false)}
          onReviewSubmitted={() => {
            loadData();
          }}
        />
      )}
    </div>
  );
};
