"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { ChatMessage, MessageItem } from "@/components/ChatMessage";
import { ChatInput } from "@/components/ChatInput";
import { ThinkingIndicator } from "@/components/ThinkingIndicator";
import { ChatSidebar } from "@/components/ChatSidebar";
import {
  chatWithGM,
  getChatSessions,
  createChatSession,
  getSessionMessages,
  deleteChatSession,
} from "@/lib/api";
import { ChatSessionSummary } from "@/lib/types";

const WELCOME_MESSAGE: MessageItem = {
  id: "init-gm",
  sender: "gm",
  text:
    "**Gridiron AI General Manager online.**\n\n" +
    "Connected to **WA minus Josh** (10-Team PPR, 3-WR + 1-FLEX).\n" +
    "- **Roster Audit**: Team Cooper holds locked Round 8 keeper **Javonte Williams (DAL RB)** with Round 3 ADP surplus value.\n" +
    "- **Sub-Agents Active**: Multi-Source Consensus ADP (Yahoo / Sleeper / ESPN), VORP Engine (3-WR PPR baseline), Tier Cliff Monitor, and Pre-Draft Intelligence.\n\n" +
    "Submit a query below or select a prompt to begin strategic analysis.",
  timestamp: "READY",
};

export default function CommandCenterPage() {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activeSessionTitle, setActiveSessionTitle] = useState<string>("Pre-Draft Strategy Session");
  const [messages, setMessages] = useState<MessageItem[]>([WELCOME_MESSAGE]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  // Load chat sessions from backend
  const loadSessions = useCallback(async () => {
    try {
      const data = await getChatSessions();
      if (data?.sessions) {
        setSessions(data.sessions);
        return data.sessions;
      }
    } catch (err) {
      console.error("Failed to load chat sessions:", err);
    }
    return [];
  }, []);

  // Switch to a specific session
  const handleSelectSession = useCallback(async (sessionId: string) => {
    setErrorMsg(null);
    setActiveSessionId(sessionId);
    if (typeof window !== "undefined") {
      localStorage.setItem("gridiron_active_session_id", sessionId);
    }

    try {
      setIsLoading(true);
      const data = await getSessionMessages(sessionId);
      if (data?.session) {
        setActiveSessionTitle(data.session.title || "Strategy Discussion");
      }
      if (data?.messages && data.messages.length > 0) {
        setMessages(
          data.messages.map((m) => ({
            id: m.id,
            sender: m.sender,
            text: m.text,
            timestamp: m.timestamp || new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          }))
        );
      } else {
        setMessages([WELCOME_MESSAGE]);
      }
    } catch (err) {
      console.error("Failed to load session history:", err);
      setErrorMsg("Failed to load conversation history.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial load: fetch sessions and restore active session
  useEffect(() => {
    const init = async () => {
      const loaded = await loadSessions();
      const savedId = typeof window !== "undefined" ? localStorage.getItem("gridiron_active_session_id") : null;

      if (savedId && loaded.some((s) => s.id === savedId)) {
        await handleSelectSession(savedId);
      } else if (loaded.length > 0) {
        await handleSelectSession(loaded[0].id);
      }
    };
    init();
  }, [loadSessions, handleSelectSession]);

  // Start a new chat session
  const handleNewChat = async () => {
    setErrorMsg(null);
    try {
      const newSession = await createChatSession("New Strategy Discussion");
      setSessions((prev) => [newSession, ...prev]);
      setActiveSessionId(newSession.id);
      setActiveSessionTitle(newSession.title);
      setMessages([WELCOME_MESSAGE]);
      if (typeof window !== "undefined") {
        localStorage.setItem("gridiron_active_session_id", newSession.id);
      }
    } catch (err) {
      console.error("Failed to create new chat session:", err);
      setErrorMsg("Failed to start new chat session.");
    }
  };

  // Delete a chat session
  const handleDeleteSession = async (sessionId: string) => {
    try {
      await deleteChatSession(sessionId);
      const remaining = sessions.filter((s) => s.id !== sessionId);
      setSessions(remaining);

      if (activeSessionId === sessionId) {
        if (remaining.length > 0) {
          handleSelectSession(remaining[0].id);
        } else {
          setActiveSessionId(null);
          setActiveSessionTitle("Pre-Draft Strategy Session");
          setMessages([WELCOME_MESSAGE]);
          if (typeof window !== "undefined") {
            localStorage.removeItem("gridiron_active_session_id");
          }
        }
      }
    } catch (err) {
      console.error("Failed to delete chat session:", err);
      setErrorMsg("Failed to delete chat session.");
    }
  };

  // Send a message and persist to current session
  const handleSend = async (text: string, week: number) => {
    setErrorMsg(null);
    const userMsg: MessageItem = {
      id: `user-${Date.now()}`,
      sender: "user",
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const response = await chatWithGM({
        message: text,
        week,
        session_id: activeSessionId || undefined,
      });

      if (response.session_id && response.session_id !== activeSessionId) {
        setActiveSessionId(response.session_id);
        if (typeof window !== "undefined") {
          localStorage.setItem("gridiron_active_session_id", response.session_id);
        }
      }

      const gmMsg: MessageItem = {
        id: response.gm_message_id || `gm-${Date.now()}`,
        sender: "gm",
        text: response.response,
        timestamp: response.timestamp || new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, gmMsg]);

      // Refresh sessions in background so title & timestamp update in sidebar
      loadSessions();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to reach General Manager. Is the backend server running?";
      setErrorMsg(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      {/* Top Header Bar */}
      <header style={styles.header}>
        <div style={styles.headerLeft}>
          <button
            type="button"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={styles.sidebarToggleBtn}
            className="font-mono"
            title={sidebarOpen ? "Hide Chat History" : "Show Chat History"}
          >
            ☰ CHATS {sessions.length > 0 ? `(${sessions.length})` : ""}
          </button>
          <div style={styles.titleWrap}>
            <h1 style={styles.title} className="font-mono">
              COMMAND CENTER
            </h1>
            <span style={styles.headerSub}>General Manager Orchestrator</span>
          </div>
        </div>

        <div style={styles.headerRight}>
          <span style={styles.activeThreadLabel} className="font-mono">
            {activeSessionTitle.length > 38 ? `${activeSessionTitle.slice(0, 38)}...` : activeSessionTitle}
          </span>
          <div style={styles.statPill} className="font-mono">
            <span style={styles.statLabel}>SUPERVISOR:</span>
            <span style={styles.statVal}>Groq / Gemini</span>
          </div>
          <button
            type="button"
            onClick={handleNewChat}
            className="btn-secondary btn-sm font-mono"
            style={styles.newChatHeaderBtn}
          >
            + NEW CHAT
          </button>
        </div>
      </header>

      {/* Main Content Area with Sidebar & Chat Feed */}
      <div style={styles.bodyLayout}>
        {/* Chat History Sidebar */}
        <ChatSidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
          onDeleteSession={handleDeleteSession}
          isOpen={sidebarOpen}
          onToggleOpen={() => setSidebarOpen(false)}
        />

        {/* Chat Main Area */}
        <main style={styles.chatMainArea}>
          {/* Error alert banner */}
          {errorMsg && (
            <div style={styles.errorBanner} className="font-mono">
              <span className="status-dot critical" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Messages Scroll Area */}
          <div ref={scrollRef} style={styles.messageList}>
            {messages.map((m) => (
              <ChatMessage key={m.id} message={m} />
            ))}
            {isLoading && <ThinkingIndicator />}
          </div>

          {/* Pinned Input Bar with Dynamic Pre-Draft Prompts */}
          <ChatInput onSend={handleSend} isLoading={isLoading} />
        </main>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    width: "100%",
    backgroundColor: "var(--bg-base, #09090b)",
    overflow: "hidden",
  },
  header: {
    padding: "0.6rem 1.25rem",
    backgroundColor: "var(--bg-raised, #121215)",
    borderBottom: "1px solid var(--border-subtle, #27272a)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    flexShrink: 0,
    zIndex: 10,
  },
  headerLeft: {
    display: "flex",
    alignItems: "center",
    gap: "0.85rem",
  },
  sidebarToggleBtn: {
    background: "var(--bg-surface, #18181b)",
    border: "1px solid var(--border-subtle, #27272a)",
    color: "var(--text-main, #fafafa)",
    borderRadius: "4px",
    padding: "4px 8px",
    fontSize: "0.72rem",
    fontWeight: 700,
    cursor: "pointer",
    transition: "border-color 0.15s ease",
  },
  titleWrap: {
    display: "flex",
    alignItems: "baseline",
    gap: "0.5rem",
  },
  title: {
    fontSize: "13px",
    fontWeight: 700,
    color: "var(--text-primary, #fafafa)",
    letterSpacing: "0.05em",
  },
  headerSub: {
    fontSize: "11px",
    color: "var(--text-dim, #71717a)",
  },
  headerRight: {
    display: "flex",
    alignItems: "center",
    gap: "0.75rem",
  },
  activeThreadLabel: {
    fontSize: "0.75rem",
    color: "var(--accent-amber, #f59e0b)",
    opacity: 0.9,
    maxWidth: "280px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  statPill: {
    fontSize: "11px",
    backgroundColor: "var(--bg-surface, #18181b)",
    padding: "3px 8px",
    borderRadius: "4px",
    border: "1px solid var(--border-subtle, #27272a)",
    display: "flex",
    gap: "4px",
  },
  statLabel: {
    color: "var(--text-dim, #71717a)",
  },
  statVal: {
    color: "var(--text-secondary, #a1a1aa)",
  },
  newChatHeaderBtn: {
    fontSize: "11px",
    padding: "4px 9px",
    color: "var(--accent-amber, #f59e0b)",
    borderColor: "rgba(245, 158, 11, 0.4)",
  },
  bodyLayout: {
    display: "flex",
    flex: 1,
    overflow: "hidden",
    position: "relative",
  },
  chatMainArea: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    background: "var(--bg-base, #09090b)",
  },
  errorBanner: {
    padding: "0.5rem 1.25rem",
    backgroundColor: "var(--bg-surface, #18181b)",
    borderBottom: "1px solid #ef4444",
    color: "#fafafa",
    fontSize: "12px",
    display: "flex",
    alignItems: "center",
    gap: "0.5rem",
  },
  messageList: {
    flex: 1,
    overflowY: "auto",
    padding: "1rem 1.5rem",
    display: "flex",
    flexDirection: "column",
    gap: "1rem",
  },
};
