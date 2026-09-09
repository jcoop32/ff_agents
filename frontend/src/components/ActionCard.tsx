"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PendingAction } from "@/lib/types";
import { approvePendingAction, rejectPendingAction } from "@/lib/api";

interface ActionCardProps {
  action: PendingAction;
  onActionComplete?: (actionId: number, newStatus: string) => void;
  onAskAgent?: (prompt: string) => void;
}

export function ActionCard({ action, onActionComplete, onAskAgent }: ActionCardProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState(action.status);
  const [showDetails, setShowDetails] = useState(false);

  const isPending = status === "PENDING";

  const handleApprove = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await approvePendingAction(action.id);
      setStatus(res.action.status);
      if (onActionComplete) {
        onActionComplete(action.id, res.action.status);
      }
    } catch (err: any) {
      setError(err.message || "Approval execution failed");
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await rejectPendingAction(action.id, "Rejected via UI");
      setStatus(res.action.status);
      if (onActionComplete) {
        onActionComplete(action.id, res.action.status);
      }
    } catch (err: any) {
      setError(err.message || "Rejection failed");
    } finally {
      setLoading(false);
    }
  };

  const urgencyColors = {
    CRITICAL: { border: "rgba(239, 68, 68, 0.4)", bg: "rgba(239, 68, 68, 0.08)", text: "#ef4444" },
    HIGH: { border: "rgba(245, 158, 11, 0.4)", bg: "rgba(245, 158, 11, 0.08)", text: "#f59e0b" },
    MEDIUM: { border: "rgba(59, 130, 246, 0.4)", bg: "rgba(59, 130, 246, 0.08)", text: "#3b82f6" },
    LOW: { border: "rgba(16, 185, 129, 0.4)", bg: "rgba(16, 185, 129, 0.08)", text: "#10b981" },
  };

  const urgencyStyle = urgencyColors[action.urgency] || urgencyColors.MEDIUM;

  return (
    <div
      style={{
        ...styles.card,
        borderColor: isPending ? urgencyStyle.border : "var(--border-subtle)",
        boxShadow: isPending && action.urgency === "CRITICAL" ? "0 0 16px rgba(239, 68, 68, 0.2)" : "none",
      }}
    >
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.badgeGroup}>
          <span
            style={{
              ...styles.urgencyBadge,
              backgroundColor: urgencyStyle.bg,
              color: urgencyStyle.text,
              borderColor: urgencyStyle.border,
            }}
            className="font-mono"
          >
            {action.urgency}
          </span>
          <span style={styles.typeBadge} className="font-mono">
            {action.action_type.replace("_", " ")}
          </span>
          <span style={styles.agentBadge} className="font-mono">
            {action.source_agent}
          </span>
        </div>

        <div style={styles.confidenceWrap}>
          <span style={styles.confidenceLabel} className="font-mono">
            CONFIDENCE
          </span>
          <div style={styles.confidenceBarBg}>
            <div
              style={{
                ...styles.confidenceBarFill,
                width: `${Math.round(action.confidence_score * 100)}%`,
                backgroundColor:
                  action.confidence_score >= 0.85
                    ? "#10b981"
                    : action.confidence_score >= 0.7
                    ? "#f59e0b"
                    : "#ef4444",
              }}
            />
          </div>
          <span style={styles.confidenceVal} className="font-mono">
            {Math.round(action.confidence_score * 100)}%
          </span>
        </div>
      </div>

      {/* Title & Description */}
      <div style={styles.body}>
        <h3 style={styles.title}>{action.title}</h3>
        <div className="prose" style={styles.description}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {action.description}
          </ReactMarkdown>
        </div>

        {/* Rationale Quote */}
        <div style={styles.rationaleBox}>
          <div style={styles.rationaleHeader} className="font-mono">
            <span>💡 AGENT RATIONALE</span>
          </div>
          <div className="prose" style={styles.rationaleText}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {action.rationale}
            </ReactMarkdown>
          </div>
        </div>

        {/* Expandable Payload / Parameters */}
        {showDetails && action.payload && (
          <div style={styles.detailsBox}>
            <div style={styles.detailsHeader} className="font-mono">
              TRANSACTION PARAMETERS
            </div>
            <pre style={styles.detailsCode} className="font-mono">
              {JSON.stringify(action.payload, null, 2)}
            </pre>
          </div>
        )}

        {/* Status result if executed or rejected */}
        {!isPending && (
          <div
            style={{
              ...styles.statusBanner,
              backgroundColor:
                status === "EXECUTED"
                  ? "rgba(16, 185, 129, 0.1)"
                  : status === "REJECTED"
                  ? "rgba(156, 163, 175, 0.1)"
                  : "rgba(239, 68, 68, 0.1)",
              color:
                status === "EXECUTED"
                  ? "#10b981"
                  : status === "REJECTED"
                  ? "#9ca3af"
                  : "#ef4444",
            }}
            className="font-mono"
          >
            STATUS: {status}
            {action.execution_result && typeof action.execution_result === "object" && (
              <span style={{ display: "block", fontSize: "11px", marginTop: "4px", color: "var(--text-secondary)" }}>
                {(action.execution_result as any).message || (action.execution_result as any).reason || ""}
              </span>
            )}
          </div>
        )}

        {error && (
          <div style={styles.errorBanner} className="font-mono">
            ⚠️ {error}
          </div>
        )}
      </div>

      {/* Footer Controls */}
      <div style={styles.footer}>
        <button
          type="button"
          onClick={() => setShowDetails(!showDetails)}
          style={styles.detailsToggle}
          className="font-mono"
        >
          {showDetails ? "HIDE SPECS ▲" : "VIEW SPECS ▼"}
        </button>

        <div style={styles.buttonGroup}>
          {onAskAgent && (
            <button
              type="button"
              onClick={() =>
                onAskAgent(
                  `Tell me more about the pending action: "${action.title}". What are the risks and alternatives?`
                )
              }
              style={styles.discussBtn}
              className="font-mono"
            >
              💬 ASK GM
            </button>
          )}

          {isPending && (
            <>
              <button
                type="button"
                onClick={handleReject}
                disabled={loading}
                style={styles.rejectBtn}
                className="font-mono"
              >
                DISMISS
              </button>
              <button
                type="button"
                onClick={handleApprove}
                disabled={loading}
                style={styles.approveBtn}
                className="font-mono"
              >
                {loading ? "EXECUTING..." : "✓ APPROVE & EXECUTE"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "8px",
    padding: "var(--space-4)",
    marginBottom: "var(--space-4)",
    transition: "border-color 200ms ease, box-shadow 200ms ease",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "var(--space-3)",
    flexWrap: "wrap",
    gap: "var(--space-2)",
  },
  badgeGroup: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-2)",
  },
  urgencyBadge: {
    fontSize: "10px",
    fontWeight: 700,
    letterSpacing: "0.05em",
    padding: "2px 8px",
    borderRadius: "4px",
    border: "1px solid transparent",
  },
  typeBadge: {
    fontSize: "10px",
    fontWeight: 600,
    backgroundColor: "var(--bg-surface)",
    color: "var(--text-secondary)",
    padding: "2px 8px",
    borderRadius: "4px",
    border: "1px solid var(--border-subtle)",
  },
  agentBadge: {
    fontSize: "10px",
    color: "var(--text-dim)",
  },
  confidenceWrap: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-2)",
  },
  confidenceLabel: {
    fontSize: "10px",
    color: "var(--text-dim)",
  },
  confidenceBarBg: {
    width: "60px",
    height: "6px",
    backgroundColor: "var(--bg-surface)",
    borderRadius: "3px",
    overflow: "hidden",
  },
  confidenceBarFill: {
    height: "100%",
    borderRadius: "3px",
  },
  confidenceVal: {
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--text-secondary)",
  },
  body: {
    marginBottom: "var(--space-3)",
  },
  title: {
    fontSize: "15px",
    fontWeight: 700,
    color: "var(--text-primary)",
    margin: "0 0 var(--space-1) 0",
  },
  description: {
    fontSize: "13px",
    color: "var(--text-secondary)",
    margin: "0 0 var(--space-3) 0",
    lineHeight: 1.5,
  },
  rationaleBox: {
    backgroundColor: "var(--bg-surface)",
    borderLeft: "3px solid var(--accent-amber)",
    borderRadius: "0 4px 4px 0",
    padding: "var(--space-3)",
    marginBottom: "var(--space-3)",
  },
  rationaleHeader: {
    fontSize: "10px",
    fontWeight: 700,
    color: "var(--accent-amber)",
    marginBottom: "var(--space-1)",
    letterSpacing: "0.05em",
  },
  rationaleText: {
    fontSize: "12px",
    color: "var(--text-secondary)",
    margin: 0,
    lineHeight: 1.4,
  },
  detailsBox: {
    backgroundColor: "var(--bg-base)",
    padding: "var(--space-3)",
    borderRadius: "4px",
    marginBottom: "var(--space-3)",
    border: "1px solid var(--border-subtle)",
  },
  detailsHeader: {
    fontSize: "10px",
    color: "var(--text-dim)",
    marginBottom: "var(--space-1)",
  },
  detailsCode: {
    fontSize: "11px",
    color: "var(--text-muted)",
    margin: 0,
    overflowX: "auto",
  },
  statusBanner: {
    padding: "var(--space-2) var(--space-3)",
    borderRadius: "4px",
    fontSize: "12px",
    fontWeight: 700,
    letterSpacing: "0.05em",
    marginTop: "var(--space-2)",
  },
  errorBanner: {
    padding: "var(--space-2) var(--space-3)",
    backgroundColor: "rgba(239, 68, 68, 0.1)",
    color: "#ef4444",
    borderRadius: "4px",
    fontSize: "11px",
    marginTop: "var(--space-2)",
  },
  footer: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    borderTop: "1px solid var(--border-subtle)",
    paddingTop: "var(--space-3)",
    flexWrap: "wrap",
    gap: "var(--space-2)",
  },
  detailsToggle: {
    background: "transparent",
    border: "none",
    color: "var(--text-dim)",
    fontSize: "10px",
    cursor: "pointer",
    padding: "4px",
  },
  buttonGroup: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-2)",
  },
  discussBtn: {
    background: "transparent",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-secondary)",
    fontSize: "11px",
    padding: "6px 12px",
    borderRadius: "4px",
    cursor: "pointer",
  },
  rejectBtn: {
    background: "transparent",
    border: "1px solid rgba(239, 68, 68, 0.4)",
    color: "#ef4444",
    fontSize: "11px",
    fontWeight: 600,
    padding: "6px 14px",
    borderRadius: "4px",
    cursor: "pointer",
  },
  approveBtn: {
    backgroundColor: "#10b981",
    border: "1px solid #10b981",
    color: "#ffffff",
    fontSize: "11px",
    fontWeight: 700,
    padding: "6px 16px",
    borderRadius: "4px",
    cursor: "pointer",
  },
};
