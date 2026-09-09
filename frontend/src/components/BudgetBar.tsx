import React from "react";

interface Props {
  label: string;
  used: number;
  limit: number;
  unit?: string;
}

export function BudgetBar({ label, used, limit, unit = "" }: Props) {
  const pct = limit > 0 ? Math.min(Math.round((used / limit) * 100), 100) : 0;

  // Color thresholding for rate limit safety
  let barColor = "var(--status-healthy)";
  if (pct >= 90) {
    barColor = "var(--status-critical)";
  } else if (pct >= 70) {
    barColor = "var(--status-warning)";
  }

  return (
    <div style={styles.container}>
      <div style={styles.header} className="font-mono">
        <span style={styles.label}>{label}</span>
        <span style={styles.metrics}>
          {used.toLocaleString()} / {limit.toLocaleString()} {unit} ({pct}%)
        </span>
      </div>

      <div style={styles.track}>
        <div
          style={{
            ...styles.fill,
            width: `${pct}%`,
            backgroundColor: barColor,
          }}
        />
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-1)",
    marginBottom: "var(--space-3)",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: "11px",
  },
  label: {
    color: "var(--text-dim)",
    letterSpacing: "0.03em",
  },
  metrics: {
    color: "var(--text-secondary)",
  },
  track: {
    width: "100%",
    height: "6px",
    backgroundColor: "var(--bg-base)",
    borderRadius: "2px",
    overflow: "hidden",
    border: "1px solid var(--border-subtle)",
  },
  fill: {
    height: "100%",
    transition: "width 200ms ease",
  },
};
