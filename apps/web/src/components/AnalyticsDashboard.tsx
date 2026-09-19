import React, { useEffect, useMemo, useState } from "react";
import { fetchDashboard } from "../api/analytics";
import { BreakdownEntry, Dashboard, Granularity, PeriodMetrics } from "../types/analytics";
import { AlertTriangle, CheckCircle2, ShieldAlert, UserCheck } from "lucide-react";

/**
 * Gate outcomes use the reserved status palette, never the categorical series slots. Each is
 * always accompanied by a label and a count, so the state is never carried by colour alone.
 */
const OUTCOME_SERIES = [
  { key: "auto", label: "Auto-submitted", colour: "var(--status-pass-text)" },
  { key: "review", label: "Sent to QA", colour: "var(--status-review-text)" },
  { key: "held", label: "Held", colour: "var(--status-hold-text)" },
] as const;

const percent = (value: number | null | undefined, digits = 1) =>
  value == null ? "—" : `${(value * 100).toFixed(digits)}%`;

const score = (value: number | null | undefined) => (value == null ? "—" : `${value.toFixed(1)}%`);

const card: React.CSSProperties = {
  background: "var(--bg-card)",
  border: "1px solid var(--border-subtle)",
  borderRadius: "var(--radius-lg)",
  padding: "20px",
};

const tableCell: React.CSSProperties = {
  padding: "8px 10px",
  fontSize: "13px",
  color: "var(--text-secondary)",
  textAlign: "left",
  borderBottom: "1px solid var(--border-subtle)",
};

const headerCell: React.CSSProperties = {
  ...tableCell,
  fontSize: "11px",
  color: "var(--text-muted)",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  fontWeight: 600,
};

/** A single headline figure. No plot, so no hover layer. */
const StatTile: React.FC<{
  label: string;
  value: string;
  caption: string;
  colour?: string;
  icon: React.ReactNode;
}> = ({ label, value, caption, colour = "var(--text-primary)", icon }) => (
  <div style={{ ...card, padding: "18px" }}>
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <span style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
        {label}
      </span>
      {icon}
    </div>
    <div style={{ fontSize: "30px", fontWeight: 800, color: colour, marginTop: "8px", lineHeight: 1.1 }}>
      {value}
    </div>
    <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>{caption}</span>
  </div>
);

/**
 * Gate outcomes over time. Bar height encodes call volume on one axis; the stack splits that
 * volume by outcome. Segments carry a 2px surface gap, and only the data end is rounded.
 */
const OutcomeTrend: React.FC<{ periods: PeriodMetrics[]; granularity: Granularity }> = ({
  periods,
  granularity,
}) => {
  const [hovered, setHovered] = useState<number | null>(null);

  const bars = useMemo(
    () =>
      periods.map((period) => {
        const auto = Math.round(period.first_pass_yield * period.total_sales);
        const held = Math.round(period.hold_rate * period.total_sales);
        const review = Math.max(0, period.total_sales - auto - held);
        return { period, auto, review, held };
      }),
    [periods]
  );

  const maxTotal = Math.max(1, ...bars.map((bar) => bar.period.total_sales));

  if (bars.length === 0) {
    return (
      <div style={card}>
        <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>
          No scored calls in this window.
        </p>
      </div>
    );
  }

  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: "8px" }}>
        <h3 style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-primary)" }}>
          Gate outcomes, {granularity}
        </h3>
        {/* Legend is always present for more than one series. */}
        <div style={{ display: "flex", gap: "14px", flexWrap: "wrap" }}>
          {OUTCOME_SERIES.map((series) => (
            <span key={series.key} style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "var(--text-secondary)" }}>
              <span style={{ width: "10px", height: "10px", borderRadius: "3px", background: series.colour }} />
              {series.label}
            </span>
          ))}
        </div>
      </div>

      <div
        style={{
          position: "relative",
          display: "flex",
          alignItems: "flex-end",
          gap: "6px",
          height: "180px",
          marginTop: "20px",
          paddingBottom: "22px",
          borderBottom: "1px solid var(--border-subtle)",
        }}
      >
        {bars.map((bar, index) => {
          const heightPct = (bar.period.total_sales / maxTotal) * 100;
          return (
            <div
              key={bar.period.period}
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
              style={{
                flex: 1,
                minWidth: "10px",
                height: "100%",
                display: "flex",
                flexDirection: "column",
                justifyContent: "flex-end",
                cursor: "default",
                position: "relative",
              }}
            >
              <div
                style={{
                  height: `${heightPct}%`,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "flex-end",
                  gap: "2px",
                  opacity: hovered === null || hovered === index ? 1 : 0.55,
                  transition: "opacity var(--transition-fast)",
                }}
              >
                {/* Order top-to-bottom: held sits above review above auto-submitted. */}
                {[
                  { count: bar.held, colour: "var(--status-hold-text)" },
                  { count: bar.review, colour: "var(--status-review-text)" },
                  { count: bar.auto, colour: "var(--status-pass-text)" },
                ].map((segment, segmentIndex) => {
                  if (segment.count <= 0) return null;
                  const share = segment.count / bar.period.total_sales;
                  return (
                    <div
                      key={segmentIndex}
                      style={{
                        flex: share,
                        background: segment.colour,
                        borderRadius: segmentIndex === 0 ? "4px 4px 0 0" : "0",
                        minHeight: "3px",
                      }}
                    />
                  );
                })}
              </div>

              <span
                style={{
                  position: "absolute",
                  bottom: "-20px",
                  left: 0,
                  right: 0,
                  textAlign: "center",
                  fontSize: "10px",
                  color: "var(--text-muted)",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {/* Label selectively, so the axis stays readable at any window length. */}
                {bars.length <= 12 || index % Math.ceil(bars.length / 8) === 0
                  ? bar.period.period.slice(5)
                  : ""}
              </span>

              {hovered === index && (
                <div
                  style={{
                    position: "absolute",
                    bottom: "calc(100% + 8px)",
                    left: "50%",
                    transform: "translateX(-50%)",
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border-accent)",
                    borderRadius: "var(--radius-sm)",
                    padding: "8px 10px",
                    whiteSpace: "nowrap",
                    zIndex: 5,
                    boxShadow: "var(--shadow-lg)",
                  }}
                >
                  <div style={{ fontSize: "12px", fontWeight: 700, color: "var(--text-primary)", marginBottom: "4px" }}>
                    {bar.period.period}
                  </div>
                  {[
                    { label: "Auto-submitted", count: bar.auto, colour: "var(--status-pass-text)" },
                    { label: "Sent to QA", count: bar.review, colour: "var(--status-review-text)" },
                    { label: "Held", count: bar.held, colour: "var(--status-hold-text)" },
                  ].map((row) => (
                    <div key={row.label} style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "11px", color: "var(--text-secondary)" }}>
                      <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: row.colour }} />
                      {row.label}: {row.count}
                    </div>
                  ))}
                  <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px" }}>
                    {bar.period.total_sales} calls · FPY {percent(bar.period.first_pass_yield, 0)}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const BreakdownTable: React.FC<{ rows: BreakdownEntry[]; nameHeader: string }> = ({
  rows,
  nameHeader,
}) => {
  if (rows.length === 0) {
    return <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>No data in this window.</p>;
  }
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "560px" }}>
        <thead>
          <tr>
            <th style={headerCell}>{nameHeader}</th>
            <th style={headerCell}>Calls</th>
            <th style={headerCell}>First-pass yield</th>
            <th style={headerCell}>Critical fail rate</th>
            <th style={headerCell}>Score (no fatals)</th>
            <th style={headerCell}>Score (with fatals)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td style={{ ...tableCell, color: "var(--text-primary)", fontWeight: 600 }}>{row.label}</td>
              <td style={tableCell}>{row.total_sales}</td>
              <td style={{ ...tableCell, color: "var(--status-pass-text)" }}>{percent(row.first_pass_yield)}</td>
              <td style={{ ...tableCell, color: row.critical_fail_rate > 0 ? "var(--status-hold-text)" : "var(--text-secondary)" }}>
                {percent(row.critical_fail_rate)}
              </td>
              <td style={tableCell}>{score(row.avg_score_without_fatal_factors)}</td>
              <td style={tableCell}>{score(row.avg_score_with_fatal_factors)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

type BreakdownTab = "by_agent" | "by_team_lead" | "by_campaign" | "by_channel" | "by_retailer";

const BREAKDOWN_TABS: { id: BreakdownTab; label: string; nameHeader: string }[] = [
  { id: "by_agent", label: "Agent", nameHeader: "Agent" },
  { id: "by_team_lead", label: "Team lead", nameHeader: "Team lead" },
  { id: "by_campaign", label: "Campaign", nameHeader: "Campaign" },
  { id: "by_channel", label: "Channel", nameHeader: "Channel" },
  { id: "by_retailer", label: "Retailer", nameHeader: "Retailer" },
];

export const AnalyticsDashboard: React.FC = () => {
  const [granularity, setGranularity] = useState<Granularity>("daily");
  const [days, setDays] = useState(30);
  const [tab, setTab] = useState<BreakdownTab>("by_agent");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchDashboard({ granularity, days })
      .then((data) => {
        if (!cancelled) {
          setDashboard(data);
          setError(null);
        }
      })
      .catch((err: Error) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [granularity, days]);

  if (error) {
    return (
      <div style={{ ...card, borderColor: "var(--status-hold-border)" }}>
        <p style={{ color: "var(--status-hold-text)", fontSize: "14px" }}>
          Could not load analytics: {error}
        </p>
      </div>
    );
  }

  if (loading && !dashboard) {
    return <p style={{ color: "var(--text-muted)", fontSize: "14px" }}>Loading analytics…</p>;
  }
  if (!dashboard) return null;

  const { summary, auditor_agreement: agreement } = dashboard;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: "16px", flexWrap: "wrap" }}>
        <div>
          <h2 style={{ fontSize: "24px", fontWeight: 800, color: "var(--text-primary)" }}>
            QA Performance & Calibration
          </h2>
          <p style={{ fontSize: "14px", color: "var(--text-secondary)", marginTop: "4px" }}>
            Aggregated server-side across the full window — {summary.total_sales} scored calls
          </p>
        </div>

        {/* Filters sit in one row above the charts. */}
        <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
          {(["daily", "weekly", "monthly"] as Granularity[]).map((option) => (
            <button
              key={option}
              onClick={() => setGranularity(option)}
              style={{
                padding: "6px 12px",
                borderRadius: "var(--radius-sm)",
                border: "none",
                cursor: "pointer",
                fontSize: "12px",
                fontWeight: 600,
                textTransform: "capitalize",
                background: granularity === option ? "var(--brand-cyan)" : "var(--bg-surface)",
                color: granularity === option ? "#090d16" : "var(--text-secondary)",
              }}
            >
              {option}
            </button>
          ))}
          <select
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            style={{
              padding: "7px 12px",
              borderRadius: "var(--radius-sm)",
              background: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-secondary)",
              fontSize: "12px",
            }}
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last 12 months</option>
          </select>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "16px" }}>
        <StatTile
          label="First-pass yield"
          value={percent(summary.first_pass_yield)}
          caption="Shipped with no human touch"
          colour="var(--status-pass-text)"
          icon={<CheckCircle2 size={18} color="var(--status-pass-text)" />}
        />
        <StatTile
          label="Critical fail rate"
          value={percent(summary.critical_fail_rate)}
          caption="At least one critical check failed"
          colour="var(--status-hold-text)"
          icon={<ShieldAlert size={18} color="var(--status-hold-text)" />}
        />
        <StatTile
          label="Score without fatals"
          value={score(summary.avg_score_without_fatal_factors)}
          caption="Weighted score, fatal rule off"
          icon={<CheckCircle2 size={18} color="var(--text-muted)" />}
        />
        <StatTile
          label="Score with fatals"
          value={score(summary.avg_score_with_fatal_factors)}
          caption="A critical failure zeroes the card"
          icon={<ShieldAlert size={18} color="var(--text-muted)" />}
        />
        <StatTile
          label="Auditor agreement"
          value={percent(agreement.agreement_rate)}
          caption={`${agreement.upheld} upheld · ${agreement.overturned} overturned`}
          colour="var(--brand-cyan)"
          icon={<UserCheck size={18} color="var(--brand-cyan)" />}
        />
      </div>

      <OutcomeTrend periods={dashboard.timeseries} granularity={dashboard.granularity} />

      {dashboard.repeat_offences.length > 0 && (
        <div style={{ ...card, borderColor: "var(--status-hold-border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
            <AlertTriangle size={18} color="var(--status-hold-text)" />
            <h3 style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-primary)" }}>
              Repeat offences — team lead flagged
            </h3>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "560px" }}>
              <thead>
                <tr>
                  <th style={headerCell}>Agent</th>
                  <th style={headerCell}>Check</th>
                  <th style={headerCell}>Failures</th>
                  <th style={headerCell}>Window</th>
                  <th style={headerCell}>Team lead</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.repeat_offences.map((offence) => (
                  <tr key={`${offence.agent_id}-${offence.check_id}`}>
                    <td style={{ ...tableCell, color: "var(--text-primary)", fontWeight: 600 }}>
                      {offence.agent_name}
                    </td>
                    <td style={tableCell}>{offence.check_code}</td>
                    <td style={{ ...tableCell, color: "var(--status-hold-text)", fontWeight: 700 }}>
                      {offence.occurrences}
                    </td>
                    <td style={tableCell}>rolling {offence.window_days} days</td>
                    <td style={tableCell}>{offence.team_lead_id ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div style={card}>
        <h3 style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-primary)", marginBottom: "12px" }}>
          Which check is failing
        </h3>
        {dashboard.failing_checks.length === 0 ? (
          <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>
            No critical check failed in this window.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {dashboard.failing_checks.slice(0, 10).map((check) => {
              const widest = dashboard.failing_checks[0].failures || 1;
              return (
                <div key={check.check_id}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", marginBottom: "4px" }}>
                    <span style={{ color: "var(--text-primary)" }}>{check.check_code}</span>
                    <span style={{ color: "var(--text-secondary)" }}>
                      {check.failures} · {percent(check.failure_rate, 0)} of calls
                    </span>
                  </div>
                  <div style={{ background: "var(--bg-surface)", height: "8px", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
                    <div
                      style={{
                        background: "var(--status-hold-text)",
                        height: "100%",
                        width: `${(check.failures / widest) * 100}%`,
                        borderRadius: "0 4px 4px 0",
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div style={card}>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "14px" }}>
          {BREAKDOWN_TABS.map((option) => (
            <button
              key={option.id}
              onClick={() => setTab(option.id)}
              style={{
                padding: "6px 12px",
                borderRadius: "var(--radius-sm)",
                border: "none",
                cursor: "pointer",
                fontSize: "12px",
                fontWeight: 600,
                background: tab === option.id ? "var(--brand-cyan)" : "var(--bg-surface)",
                color: tab === option.id ? "#090d16" : "var(--text-secondary)",
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
        <BreakdownTable
          rows={dashboard[tab]}
          nameHeader={BREAKDOWN_TABS.find((option) => option.id === tab)!.nameHeader}
        />
      </div>

      <div style={{ ...card, padding: "16px 20px" }}>
        <h3 style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-primary)", marginBottom: "6px" }}>
          Model calibration
        </h3>
        <p style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
          {agreement.calibration_sampled} clean calls were sampled to a human anyway;{" "}
          {agreement.calibration_sampled_reviewed} have been scored, with{" "}
          {agreement.calibration_disagreements} disagreeing with the gate. Sampling measures the
          model rather than trusting it.
        </p>
      </div>
    </div>
  );
};
