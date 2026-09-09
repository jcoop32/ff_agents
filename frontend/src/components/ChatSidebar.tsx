"use client";

import React, { useState } from "react";
import { ChatSessionSummary } from "@/lib/types";

interface Props {
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onDeleteSession: (id: string) => void;
  isOpen: boolean;
  onToggleOpen: () => void;
}

export function ChatSidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  isOpen,
  onToggleOpen,
}: Props) {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const [isDragging, setIsDragging] = useState(false);

  // Restore persisted sidebar width on client mount
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const savedWidth = localStorage.getItem("gridiron_chat_sidebar_width");
      if (savedWidth !== null) {
        const parsed = parseInt(savedWidth, 10);
        if (!isNaN(parsed) && parsed >= 200 && parsed <= 500) {
          setSidebarWidth(parsed);
        }
      }
    } catch (e) {
      console.error("Could not read sidebar width:", e);
    }
  }, []);

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    const startX = e.clientX;
    const startWidth = sidebarWidth;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const newWidth = Math.max(200, Math.min(500, startWidth + deltaX));
      setSidebarWidth(newWidth);
    };

    const onMouseUp = (upEvent: MouseEvent) => {
      const deltaX = upEvent.clientX - startX;
      const finalWidth = Math.max(200, Math.min(500, startWidth + deltaX));
      setSidebarWidth(finalWidth);
      if (typeof window !== "undefined") {
        localStorage.setItem("gridiron_chat_sidebar_width", String(finalWidth));
      }
      setIsDragging(false);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  };

  const formatTimeAgo = (isoString?: string | null) => {
    if (!isoString) return "";
    const date = new Date(isoString);
    const now = new Date();
    const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffSec < 60) return "Just now";
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    if (diffSec < 604800) return `${Math.floor(diffSec / 86400)}d ago`;
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  };

  return (
    <aside
      style={{
        ...styles.sidebar,
        width: isOpen ? `${sidebarWidth}px` : "0px",
        minWidth: isOpen ? `${sidebarWidth}px` : "0px",
        borderRight: isOpen ? "1px solid var(--border-color, #27272a)" : "none",
        opacity: isOpen ? 1 : 0,
        pointerEvents: isOpen ? "auto" : "none",
      }}
    >
      {/* Resizable Drag Splitter on right edge */}
      {isOpen && (
        <div
          onMouseDown={handleResizeStart}
          style={{
            ...styles.resizer,
            ...(isDragging ? styles.resizerActive : {}),
          }}
          title="Drag horizontally to resize chat history sidebar"
        />
      )}
      {/* Sidebar Header & New Chat Action */}
      <div style={styles.header}>
        <div style={styles.headerTitleRow}>
            <span style={styles.sidebarTitle} className="font-mono">
              SAVED CHATS
            </span>
            <span style={styles.sessionCountBadge} className="font-mono">
              {sessions.length}
            </span>
          </div>

          <button
            type="button"
            onClick={onNewChat}
            style={styles.newChatBtn}
            className="font-mono"
            title="Start a fresh strategy conversation thread"
          >
            <span style={styles.plusIcon}>+</span> NEW CHAT
          </button>
        </div>

        {/* Sessions Scrollable List */}
        <div style={styles.sessionList}>
          {sessions.length === 0 ? (
            <div style={styles.emptyWrap} className="font-mono">
              <span style={styles.emptyIcon}>💬</span>
              <p style={styles.emptyText}>No saved chat threads yet.</p>
              <p style={styles.emptySubText}>
                Queries sent to the General Manager are automatically archived here.
              </p>
            </div>
          ) : (
            sessions.map((session) => {
              const isActive = session.id === activeSessionId;
              const isDeleting = confirmDeleteId === session.id;

              return (
                <div
                  key={session.id}
                  style={{
                    ...styles.sessionItem,
                    ...(isActive ? styles.sessionItemActive : {}),
                  }}
                  onClick={() => onSelectSession(session.id)}
                >
                  <div style={styles.itemMain}>
                    <div style={styles.itemTitleRow}>
                      <span
                        style={{
                          ...styles.itemTitle,
                          ...(isActive ? styles.itemTitleActive : {}),
                        }}
                        className="font-mono"
                        title={session.title}
                      >
                        {session.title || "Untitled Chat"}
                      </span>
                    </div>

                    <div style={styles.itemMetaRow} className="font-mono">
                      <span style={styles.itemTime}>
                        {formatTimeAgo(session.updated_at || session.created_at)}
                      </span>
                      <span style={styles.msgBadge}>
                        {session.message_count} {session.message_count === 1 ? "msg" : "msgs"}
                      </span>
                    </div>
                  </div>

                  {/* Delete Action with In-Line Confirmation */}
                  <div
                    style={styles.actionWrap}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {isDeleting ? (
                      <div style={styles.confirmDeleteRow}>
                        <button
                          type="button"
                          onClick={() => {
                            onDeleteSession(session.id);
                            setConfirmDeleteId(null);
                          }}
                          style={styles.confirmBtn}
                          className="font-mono"
                          title="Confirm Delete"
                        >
                          DEL
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmDeleteId(null)}
                          style={styles.cancelBtn}
                          className="font-mono"
                          title="Cancel"
                        >
                          ✕
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setConfirmDeleteId(session.id)}
                        style={styles.deleteIconBtn}
                        className="font-mono"
                        title="Delete this conversation"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </aside>
  );
}

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    position: "relative",
    background: "var(--bg-surface, #121215)",
    display: "flex",
    flexDirection: "column",
    flexShrink: 0,
    height: "100%",
    transition: "opacity 0.2s ease",
    zIndex: 10,
  },
  resizer: {
    position: "absolute",
    top: 0,
    right: "-4px",
    width: "8px",
    height: "100%",
    cursor: "col-resize",
    zIndex: 50,
    userSelect: "none",
    transition: "background-color 0.15s ease",
  },
  resizerActive: {
    backgroundColor: "var(--accent-amber, #f59e0b)",
  },
  sidebarOpen: {
    transform: "translateX(0)",
  },
  sidebarClosed: {
    // Hidden on very small screens if toggled, otherwise visible on desktop
  },
  header: {
    padding: "1rem",
    borderBottom: "1px solid var(--border-color, #27272a)",
    display: "flex",
    flexDirection: "column",
    gap: "0.75rem",
    background: "var(--bg-card, #18181b)",
  },
  headerTitleRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  sidebarTitle: {
    fontSize: "0.75rem",
    fontWeight: 700,
    color: "var(--text-muted, #a1a1aa)",
    letterSpacing: "0.08em",
  },
  sessionCountBadge: {
    fontSize: "0.7rem",
    fontWeight: 700,
    padding: "1px 6px",
    borderRadius: "10px",
    background: "var(--border-color, #27272a)",
    color: "var(--text-dim, #71717a)",
  },
  newChatBtn: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "6px",
    width: "100%",
    padding: "0.6rem 0.75rem",
    fontSize: "0.8rem",
    fontWeight: 700,
    letterSpacing: "0.05em",
    color: "#09090b",
    background: "var(--accent-amber, #f59e0b)",
    border: "none",
    borderRadius: "6px",
    cursor: "pointer",
    transition: "background 0.15s ease, transform 0.1s ease",
  },
  plusIcon: {
    fontSize: "1rem",
    lineHeight: "1",
    fontWeight: 900,
  },
  sessionList: {
    flex: 1,
    overflowY: "auto",
    padding: "0.5rem",
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  emptyWrap: {
    padding: "2.5rem 1rem",
    textAlign: "center",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "0.5rem",
  },
  emptyIcon: {
    fontSize: "1.8rem",
    opacity: 0.4,
  },
  emptyText: {
    fontSize: "0.82rem",
    fontWeight: 600,
    color: "var(--text-muted, #a1a1aa)",
    margin: 0,
  },
  emptySubText: {
    fontSize: "0.72rem",
    color: "var(--text-dim, #71717a)",
    margin: 0,
    lineHeight: 1.4,
  },
  sessionItem: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0.65rem 0.75rem",
    borderRadius: "6px",
    border: "1px solid transparent",
    background: "transparent",
    cursor: "pointer",
    transition: "all 0.15s ease",
    gap: "8px",
  },
  sessionItemActive: {
    background: "rgba(245, 158, 11, 0.08)",
    borderColor: "rgba(245, 158, 11, 0.35)",
  },
  itemMain: {
    flex: 1,
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: "3px",
  },
  itemTitleRow: {
    display: "flex",
    alignItems: "center",
  },
  itemTitle: {
    fontSize: "0.8rem",
    fontWeight: 500,
    color: "var(--text-main, #fafafa)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  itemTitleActive: {
    fontWeight: 700,
    color: "var(--accent-amber, #f59e0b)",
  },
  itemMetaRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    fontSize: "0.68rem",
    color: "var(--text-dim, #71717a)",
  },
  itemTime: {
    opacity: 0.8,
  },
  msgBadge: {
    background: "rgba(255, 255, 255, 0.05)",
    padding: "1px 5px",
    borderRadius: "4px",
    fontSize: "0.65rem",
  },
  actionWrap: {
    display: "flex",
    alignItems: "center",
    flexShrink: 0,
  },
  deleteIconBtn: {
    background: "transparent",
    border: "none",
    color: "var(--text-dim, #71717a)",
    cursor: "pointer",
    fontSize: "0.75rem",
    padding: "4px 6px",
    borderRadius: "4px",
    opacity: 0.5,
    transition: "opacity 0.15s ease, color 0.15s ease",
  },
  confirmDeleteRow: {
    display: "flex",
    alignItems: "center",
    gap: "3px",
  },
  confirmBtn: {
    background: "rgba(239, 68, 68, 0.2)",
    border: "1px solid rgba(239, 68, 68, 0.4)",
    color: "#ef4444",
    fontSize: "0.65rem",
    fontWeight: 700,
    padding: "2px 5px",
    borderRadius: "3px",
    cursor: "pointer",
  },
  cancelBtn: {
    background: "var(--border-color, #27272a)",
    border: "none",
    color: "var(--text-muted, #a1a1aa)",
    fontSize: "0.65rem",
    padding: "2px 5px",
    borderRadius: "3px",
    cursor: "pointer",
  },
};
