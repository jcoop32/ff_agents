"use client";

import React, { useState } from "react";
import { Transaction } from "@/lib/types";

interface Props {
  tx: Transaction;
}

export function TransactionCard({ tx }: Props) {
  const [expanded, setExpanded] = useState(false);

  const tier = tx.impact_tier || "LOW";
  let dotClass = "dim";
  if (tier === "CRITICAL") dotClass = "critical";
  else if (tier === "HIGH") dotClass = "warning";
  else if (tier === "MEDIUM") dotClass = "info";
  else if (tier === "LOW") dotClass = "healthy";

  // Parse items from details
  const items = tx.details?.items || [];
  const team = tx.details?.team || "League";
  const timeFormatted = new Date(tx.timestamp).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div style={styles.wrapper}>
      <div
        style={styles.headerRow}
        onClick={() => setExpanded(!expanded)}
        title="Click to view detailed impact analysis"
      >
        <div style={styles.leftCol}>
          <span className={`status-dot ${dotClass}`} />
          <span style={styles.tierTag} className="font-mono">
            {tier}
          </span>
          <span style={styles.typeTag} className="font-mono">
            {tx.type}
          </span>
          <span style={styles.teamTag}>{team}</span>
        </div>

        <div style={styles.itemsCol}>
          {items.length > 0 ? (
            items.map((it, idx) => (
              <span key={idx} style={styles.playerItem}>
                <strong style={styles.action}>{it.action || "MOVE"}</strong>: {it.player || "Player"}
              </span>
            ))
          ) : (
            <span style={styles.summaryText}>{JSON.stringify(tx.details).slice(0, 70)}</span>
          )}
        </div>

        <div style={styles.rightCol}>
          <span style={styles.timeText} className="font-mono">
            {timeFormatted}
          </span>
          <button type="button" style={styles.expandBtn} className="font-mono">
            {expanded ? "HIDE" : "ANALYSIS"}
          </button>
        </div>
      </div>

      {expanded && (
        <div style={styles.analysisBody}>
          <div style={styles.analysisLabel} className="font-mono">
            PROACTIVE AGENT VERDICT:
          </div>
          <div style={styles.analysisText}>
            {tx.agent_analysis ||
              "No proactive agent intervention was required for this transaction tier."}
          </div>
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-md)",
    marginBottom: "var(--space-2)",
    overflow: "hidden",
  },
  headerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "var(--space-2) var(--space-4)",
    cursor: "pointer",
    gap: "var(--space-3)",
  },
  leftCol: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-2)",
    minWidth: "190px",
  },
  tierTag: {
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--text-primary)",
    letterSpacing: "0.03em",
  },
  typeTag: {
    fontSize: "11px",
    color: "var(--text-dim)",
    backgroundColor: "var(--bg-surface)",
    padding: "1px 5px",
    borderRadius: "var(--radius-sm)",
  },
  teamTag: {
    fontSize: "12px",
    color: "var(--text-secondary)",
    fontWeight: 500,
  },
  itemsCol: {
    flex: 1,
    display: "flex",
    flexWrap: "wrap",
    gap: "var(--space-2)",
    fontSize: "12px",
  },
  playerItem: {
    backgroundColor: "var(--bg-surface)",
    padding: "2px 6px",
    borderRadius: "var(--radius-sm)",
    color: "var(--text-secondary)",
  },
  action: {
    color: "var(--accent-amber)",
    fontSize: "11px",
  },
  summaryText: {
    color: "var(--text-muted)",
    fontSize: "12px",
  },
  rightCol: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-3)",
  },
  timeText: {
    fontSize: "11px",
    color: "var(--text-dim)",
  },
  expandBtn: {
    fontSize: "10px",
    padding: "2px 6px",
    backgroundColor: "var(--bg-surface)",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-muted)",
    borderRadius: "var(--radius-sm)",
  },
  analysisBody: {
    padding: "var(--space-3) var(--space-4)",
    backgroundColor: "var(--bg-surface)",
    borderTop: "1px solid var(--border-subtle)",
    fontSize: "12px",
    lineHeight: 1.5,
  },
  analysisLabel: {
    fontSize: "10px",
    color: "var(--accent-amber)",
    marginBottom: "var(--space-1)",
    letterSpacing: "0.05em",
  },
  analysisText: {
    color: "var(--text-secondary)",
  },
};
