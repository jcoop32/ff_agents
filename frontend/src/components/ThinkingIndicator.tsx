import React from "react";

interface Props {
  text?: string;
}

export function ThinkingIndicator({ text = "General Manager orchestrating sub-agents..." }: Props) {
  return (
    <div style={styles.container}>
      <span className="status-dot pulse" />
      <span style={styles.text} className="font-mono">
        {text}
      </span>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "inline-flex",
    alignItems: "center",
    gap: "var(--space-2)",
    padding: "var(--space-2) var(--space-3)",
    backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-md)",
    width: "fit-content",
    margin: "var(--space-2) 0",
  },
  text: {
    fontSize: "12px",
    color: "var(--text-muted)",
    letterSpacing: "0.02em",
  },
};
