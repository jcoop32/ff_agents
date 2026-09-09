"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export interface MessageItem {
  id: string;
  sender: "user" | "gm";
  text: string;
  timestamp: string;
}

interface Props {
  message: MessageItem;
}

export function ChatMessage({ message }: Props) {
  const isUser = message.sender === "user";

  return (
    <div
      style={{
        ...styles.wrapper,
        justifyContent: isUser ? "flex-end" : "flex-start",
      }}
    >
      <div
        style={{
          ...styles.bubble,
          ...(isUser ? styles.userBubble : styles.gmBubble),
        }}
      >
        <div style={styles.header} className="font-mono">
          <span style={isUser ? styles.userTag : styles.gmTag}>
            {isUser ? "YOU" : "GENERAL MANAGER"}
          </span>
          <span style={styles.timestamp}>{message.timestamp}</span>
        </div>

        {isUser ? (
          <div style={styles.userText}>{message.text}</div>
        ) : (
          <div className="prose" style={styles.proseContainer}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.text}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    display: "flex",
    width: "100%",
    marginBottom: "var(--space-4)",
  },
  bubble: {
    maxWidth: "82%",
    borderRadius: "var(--radius-md)",
    padding: "var(--space-3) var(--space-4)",
    borderWidth: "1px",
    borderStyle: "solid",
    borderColor: "var(--border-subtle)",
    wordBreak: "break-word",
  },
  userBubble: {
    backgroundColor: "var(--bg-card)",
    borderColor: "var(--border-muted)",
  },
  gmBubble: {
    backgroundColor: "var(--bg-raised)",
    borderColor: "var(--border-subtle)",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "var(--space-4)",
    marginBottom: "var(--space-2)",
    fontSize: "11px",
    letterSpacing: "0.05em",
    borderBottom: "1px solid var(--border-subtle)",
    paddingBottom: "var(--space-1)",
  },
  userTag: {
    color: "var(--text-dim)",
    fontWeight: 600,
  },
  gmTag: {
    color: "var(--accent-amber)",
    fontWeight: 700,
  },
  timestamp: {
    color: "var(--text-dim)",
  },
  userText: {
    color: "var(--text-primary)",
    fontSize: "14px",
    lineHeight: 1.5,
    whiteSpace: "pre-wrap",
  },
  proseContainer: {
    fontSize: "13.5px",
  },
};
