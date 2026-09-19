import React, { useEffect, useRef } from "react";
import { TranscriptSegment } from "../types/transcript";
import { User, Headphones, HelpCircle } from "lucide-react";

interface TranscriptViewerProps {
  segments: TranscriptSegment[];
  currentTimeMs: number;
  onSeek: (startMs: number) => void;
  activeEvidenceStartMs?: number | null;
}

// Client-side PCI card masking defense-in-depth
function maskClientPci(text: string): string {
  return text.replace(/\b(?:\d[ -]*?){13,19}\b/g, (match) => {
    const digits = match.replace(/\D/g, "");
    if (digits.length >= 13 && digits.length <= 19) {
      return `************${digits.slice(-4)}`;
    }
    return match;
  });
}

export const TranscriptViewer: React.FC<TranscriptViewerProps> = ({
  segments,
  currentTimeMs,
  onSeek,
  activeEvidenceStartMs,
}) => {
  const activeSegmentRef = useRef<HTMLDivElement | null>(null);

  const formatTimestamp = (ms: number) => {
    const totalSec = Math.floor(ms / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  // Smoothly scroll active segment into view
  useEffect(() => {
    if (activeSegmentRef.current) {
      activeSegmentRef.current.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }
  }, [currentTimeMs]);

  if (!segments || segments.length === 0) {
    return (
      <div style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>
        No transcript segments available
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        overflowY: "auto",
        maxHeight: "680px",
        paddingRight: "8px",
      }}
    >
      {segments.map((seg) => {
        const isActive = seg.start_ms <= currentTimeMs && currentTimeMs < seg.end_ms;
        const isEvidenceMatch =
          activeEvidenceStartMs !== null &&
          activeEvidenceStartMs !== undefined &&
          Math.abs(seg.start_ms - activeEvidenceStartMs) < 3000;

        const isAgent = seg.business_role === "AGENT";
        const isCustomer = seg.business_role === "CUSTOMER";

        return (
          <div
            key={seg.id}
            ref={isActive ? activeSegmentRef : null}
            onClick={() => onSeek(seg.start_ms)}
            style={{
              padding: "14px 16px",
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              transition: "var(--transition-fast)",
              border: isActive
                ? "1px solid var(--brand-cyan)"
                : isEvidenceMatch
                ? "1px solid var(--status-hold-border)"
                : "1px solid var(--border-subtle)",
              background: isActive
                ? "rgba(6, 182, 212, 0.08)"
                : isEvidenceMatch
                ? "rgba(244, 63, 94, 0.06)"
                : "var(--bg-card)",
              boxShadow: isActive ? "var(--shadow-glow-cyan)" : "none",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "6px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "5px",
                    padding: "2px 8px",
                    borderRadius: "var(--radius-full)",
                    fontSize: "11px",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                    background: isAgent
                      ? "rgba(59, 130, 246, 0.15)"
                      : isCustomer
                      ? "rgba(16, 185, 129, 0.15)"
                      : "rgba(148, 163, 184, 0.15)",
                    color: isAgent ? "#60a5fa" : isCustomer ? "#34d399" : "#cbd5e1",
                  }}
                >
                  {isAgent ? <Headphones size={12} /> : isCustomer ? <User size={12} /> : <HelpCircle size={12} />}
                  {seg.business_role}
                </span>

                <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                  Speaker {seg.speaker_label} ({Math.round(seg.role_confidence * 100)}% conf)
                </span>
              </div>

              <span
                style={{
                  fontSize: "12px",
                  fontFamily: "var(--font-mono)",
                  color: isActive ? "var(--brand-cyan)" : "var(--text-muted)",
                  fontWeight: 600,
                }}
              >
                {formatTimestamp(seg.start_ms)} - {formatTimestamp(seg.end_ms)}
              </span>
            </div>

            <p style={{ fontSize: "14px", color: "var(--text-primary)", lineHeight: 1.6 }}>
              {maskClientPci(seg.text)}
            </p>
          </div>
        );
      })}
    </div>
  );
};
