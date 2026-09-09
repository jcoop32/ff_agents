"use client";

import React, { useState, useRef, useEffect } from "react";
import { getDraftPrompts } from "@/lib/api";

interface Props {
  onSend: (message: string, week: number) => void;
  isLoading: boolean;
}

export function ChatInput({ onSend, isLoading }: Props) {
  const [text, setText] = useState("");
  const [week, setWeek] = useState<number>(1);
  const [showPrompts, setShowPrompts] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [prompts, setPrompts] = useState<string[]>([
    "How does keeping Javonte Williams in Round 8 impact our early-round WR vs RB draft priority?",
    "What is our best draft strategy in a 3-WR format with a locked Round 8 RB keeper?",
    "Run VORP baseline analysis on Tier 1 and Tier 2 Wide Receivers",
    "Should we draft Hero RB or Zero RB given our Round 8 Javonte Williams surplus?",
  ]);

  // Restore prompts collapse state from localStorage
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = localStorage.getItem("gridiron_chat_show_prompts");
      if (saved !== null) {
        setShowPrompts(saved === "true");
      }
    } catch (e) {
      console.error("Could not read show prompts preference:", e);
    }
  }, []);

  const togglePrompts = () => {
    setShowPrompts((prev) => {
      const next = !prev;
      if (typeof window !== "undefined") {
        localStorage.setItem("gridiron_chat_show_prompts", String(next));
      }
      return next;
    });
  };

  useEffect(() => {
    getDraftPrompts()
      .then((res) => {
        if (res?.prompts && res.prompts.length > 0) {
          setPrompts(res.prompts);
        }
      })
      .catch((err) => console.error("Could not fetch dynamic draft prompts:", err));
  }, []);

  const handleSend = () => {
    if (!text.trim() || isLoading) return;
    onSend(text.trim(), week);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`;
    }
  };

  return (
    <div style={styles.container}>
      {/* Quick Prompt Chips with Collapse Toggle */}
      <div style={styles.chipRow} className="no-scrollbar">
        <button
          type="button"
          onClick={togglePrompts}
          style={styles.togglePromptsBtn}
          className="font-mono"
          title={showPrompts ? "Hide prompt suggestions" : "Show prompt suggestions"}
        >
          {showPrompts ? "▼ PROMPTS" : "▶ PROMPTS"}
        </button>
        {showPrompts &&
          prompts.map((prompt, i) => (
            <button
              key={i}
              type="button"
              style={styles.chipBtn}
              onClick={() => setText(prompt)}
              disabled={isLoading}
            >
              {prompt}
            </button>
          ))}
      </div>

      {/* Input controls */}
      <div style={styles.inputRow}>
        <div style={styles.weekSelectWrapper}>
          <label style={styles.weekLabel} className="font-mono">
            WEEK
          </label>
          <select
            value={week}
            onChange={(e) => setWeek(Number(e.target.value))}
            style={styles.weekSelect}
            disabled={isLoading}
            className="font-mono"
          >
            {Array.from({ length: 18 }, (_, i) => i + 1).map((w) => (
              <option key={w} value={w}>
                W{w}
              </option>
            ))}
          </select>
        </div>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Consult the General Manager regarding trades, waivers, start/sit, or draft strategy..."
          rows={1}
          style={styles.textarea}
          disabled={isLoading}
        />

        <button
          type="button"
          onClick={handleSend}
          disabled={isLoading || !text.trim()}
          className="btn-primary"
          style={styles.sendBtn}
        >
          {isLoading ? (
            <span className="font-mono">THINKING</span>
          ) : (
            <span className="font-mono">SEND</span>
          )}
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: "var(--space-3) var(--space-6) var(--space-4)",
    backgroundColor: "var(--bg-raised)",
    borderTop: "1px solid var(--border-subtle)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-2)",
  },
  chipRow: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-2)",
    overflowX: "auto",
    paddingBottom: "var(--space-1)",
    scrollbarWidth: "none",
    msOverflowStyle: "none",
  },
  togglePromptsBtn: {
    fontSize: "10px",
    fontWeight: 700,
    padding: "2px 6px",
    backgroundColor: "var(--bg-surface)",
    border: "1px solid var(--border-subtle)",
    color: "var(--accent-amber)",
    borderRadius: "var(--radius-sm)",
    cursor: "pointer",
    whiteSpace: "nowrap",
    flexShrink: 0,
    letterSpacing: "0.05em",
  },
  chipLabel: {
    fontSize: "10px",
    color: "var(--text-dim)",
    letterSpacing: "0.05em",
    flexShrink: 0,
  },
  chipBtn: {
    fontSize: "11px",
    padding: "2px 8px",
    backgroundColor: "var(--bg-surface)",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-muted)",
    borderRadius: "var(--radius-sm)",
    whiteSpace: "nowrap",
    flexShrink: 0,
  },
  inputRow: {
    display: "flex",
    alignItems: "flex-end",
    gap: "var(--space-3)",
  },
  weekSelectWrapper: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
  },
  weekLabel: {
    fontSize: "10px",
    color: "var(--text-dim)",
  },
  weekSelect: {
    padding: "var(--space-2) var(--space-2)",
    fontSize: "12px",
    minWidth: "64px",
  },
  textarea: {
    flex: 1,
    resize: "none",
    minHeight: "40px",
    maxHeight: "140px",
    lineHeight: "1.4",
  },
  sendBtn: {
    minHeight: "40px",
    minWidth: "90px",
  },
};
