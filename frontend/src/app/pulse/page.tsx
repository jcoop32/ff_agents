"use client";

import React, { useState, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BudgetBar } from "@/components/BudgetBar";
import { TransactionCard } from "@/components/TransactionCard";
import { ActionCard } from "@/components/ActionCard";

function formatMarkdownContent(raw: string): string {
  if (!raw) return "";
  // 1. Trim accidental spaces inside bold markers like `**team **` -> `**team**`
  let text = raw.replace(/\*\*\s*([^*]+?)\s*\*\*/g, "**$1**");
  // 2. Convert unicode bullets (• or ●) at the start of lines to standard markdown list items (- )
  text = text.replace(/^[ \t]*[•●][ \t]*/gm, "- ");
  // 3. Ensure markdown headings (##, ###, ####) have a blank line before them so CommonMark parses them properly
  text = text.replace(/([^\n])\n(#{1,6}\s)/g, "$1\n\n$2");
  // 4. Ensure list items directly following headings or colons have clean spacing
  text = text.replace(/(:\s*)\n([ \t]*-\s)/g, "$1\n\n$2");
  return text;
}
import {
  getBudgetStatus,
  getTransactions,
  getHealthStatus,
  triggerLeaguePoll,
  getBriefings,
  getPendingActions,
  getPowerRankings,
  getSeasonStrategy,
  triggerProactiveJob,
  markBriefingRead,
  getSseUrl,
} from "@/lib/api";
import {
  BudgetStatus,
  Transaction,
  HealthStatus,
  AgentBriefing,
  PendingAction,
  PowerRankingItem,
  SeasonStrategy,
} from "@/lib/types";

export default function LeaguePulsePage() {
  const [activeTab, setActiveTab] = useState<"FEED" | "RANKINGS" | "STRATEGY" | "BUDGET">("FEED");
  const [briefings, setBriefings] = useState<AgentBriefing[]>([]);
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [rankings, setRankings] = useState<PowerRankingItem[]>([]);
  const [strategy, setStrategy] = useState<SeasonStrategy | null>(null);
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);

  const [loading, setLoading] = useState(true);
  const [sseConnected, setSseConnected] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [triggeringJob, setTriggeringJob] = useState<string | null>(null);

  const [selectedBriefing, setSelectedBriefing] = useState<AgentBriefing | null>(null);
  const [showRawJson, setShowRawJson] = useState(false);

  // Close modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelectedBriefing(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Fetch initial data
  const loadData = useCallback(async () => {
    try {
      const [bData, aData, tData, hData, rData, sData, bgData] = await Promise.all([
        getBriefings().catch(() => ({ briefings: [], count: 0 })),
        getPendingActions("PENDING").catch(() => ({ actions: [], count: 0 })),
        getTransactions(72).catch(() => ({ count: 0, transactions: [] })),
        getHealthStatus().catch(() => null),
        getPowerRankings().catch(() => ({ league: "", rankings: [], updated_at: "" })),
        getSeasonStrategy().catch(() => ({ team: "", strategy: null as any })),
        getBudgetStatus().catch(() => null),
      ]);

      setBriefings(bData.briefings || []);
      setPendingActions(aData.actions || []);
      setTransactions(tData.transactions || []);
      setHealth(hData);
      setRankings(rData.rankings || []);
      setStrategy(sData.strategy || null);
      setBudget(bgData);
    } catch (err: any) {
      console.error("Error loading pulse data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Connect to SSE real-time stream
  useEffect(() => {
    if (typeof window === "undefined") return;

    const sseUrl = getSseUrl();
    let es: EventSource | null = null;

    try {
      es = new EventSource(sseUrl);

      es.onopen = () => {
        setSseConnected(true);
      };

      es.onmessage = (event) => {
        try {
          const envelope = JSON.parse(event.data);
          if (envelope.type === "BRIEFING" && envelope.data) {
            setBriefings((prev) => [envelope.data, ...prev.filter((b) => b.id !== envelope.data.id)]);
            setStatusMsg(`⚡ New ${envelope.data.briefing_type}: ${envelope.data.title}`);
          } else if (envelope.type === "PENDING_ACTION" && envelope.data) {
            setPendingActions((prev) => [envelope.data, ...prev.filter((a) => a.id !== envelope.data.id)]);
            setStatusMsg(`⚡ Approval Required: ${envelope.data.title}`);
          }
        } catch (e) {
          // keepalive
        }
      };

      es.onerror = () => {
        setSseConnected(false);
      };
    } catch (e) {
      setSseConnected(false);
    }

    return () => {
      if (es) es.close();
    };
  }, []);

  const handleActionComplete = (actionId: number, newStatus: string) => {
    setPendingActions((prev) => prev.filter((a) => a.id !== actionId));
    setStatusMsg(`Action #${actionId} updated to ${newStatus}.`);
  };

  const handleTriggerJob = async (jobName: string, label: string) => {
    setTriggeringJob(jobName);
    setStatusMsg(null);
    try {
      await triggerProactiveJob(jobName);
      setStatusMsg(`Dispatched ${label} in background! Monitoring for response...`);
      setTimeout(loadData, 4000);
    } catch (err: any) {
      setStatusMsg(`Job trigger error: ${err.message}`);
    } finally {
      setTriggeringJob(null);
    }
  };

  const handleMarkRead = async (id: number) => {
    try {
      await markBriefingRead(id);
      setBriefings((prev) =>
        prev.map((b) => (b.id === id ? { ...b, read: true } : b))
      );
    } catch (e) {
      // ignore
    }
  };

  return (
    <div style={styles.container}>
      {/* Page Header */}
      <header style={styles.header}>
        <div>
          <div style={styles.preTitle} className="font-mono">
            AUTONOMOUS GENERAL MANAGER INTELLIGENCE
          </div>
          <h1 style={styles.title} className="font-mono">
            PROACTIVE PULSE & COMMAND
          </h1>
          <div style={styles.streamIndicator}>
            <span
              style={{
                ...styles.dot,
                backgroundColor: sseConnected ? "#10b981" : "#f59e0b",
                boxShadow: sseConnected ? "0 0 8px #10b981" : "none",
              }}
            />
            <span style={styles.streamText} className="font-mono">
              {sseConnected ? "LIVE SSE STREAM ACTIVE" : "CONNECTING REAL-TIME STREAM..."}
            </span>
          </div>
        </div>

        {/* Action Triggers */}
        <div style={styles.headerActions}>
          {statusMsg && (
            <span style={styles.statusBadge} className="font-mono">
              {statusMsg}
            </span>
          )}
          <div style={styles.buttonRow}>
            <button
              type="button"
              onClick={() => handleTriggerJob("job_waiver_scout", "Waiver Scout")}
              disabled={!!triggeringJob}
              style={styles.triggerBtn}
              className="font-mono"
            >
              {triggeringJob === "job_waiver_scout" ? "RUNNING..." : "⚡ SCOUT WAIVERS"}
            </button>
            <button
              type="button"
              onClick={() => handleTriggerJob("job_trade_finder", "Trade Finder")}
              disabled={!!triggeringJob}
              style={styles.triggerBtn}
              className="font-mono"
            >
              {triggeringJob === "job_trade_finder" ? "RUNNING..." : "🤝 SCAN TRADES"}
            </button>
            <button
              type="button"
              onClick={() => handleTriggerJob("job_morning_digest", "Morning Digest")}
              disabled={!!triggeringJob}
              style={styles.triggerBtn}
              className="font-mono"
            >
              {triggeringJob === "job_morning_digest" ? "RUNNING..." : "☀️ MORNING BRIEF"}
            </button>
          </div>
        </div>
      </header>

      {/* SECTION 1: PENDING APPROVAL ACTIONS */}
      {pendingActions.length > 0 && (
        <section style={styles.approvalSection}>
          <div style={styles.approvalHeader}>
            <div style={styles.approvalTitleGroup}>
              <span style={styles.pulseDot} />
              <h2 style={styles.approvalTitle} className="font-mono">
                APPROVAL GATES: {pendingActions.length} PENDING ROSTER ACTIONS
              </h2>
            </div>
            <span style={styles.approvalSubtitle}>
              Autonomous recommendations awaiting your 1-click execution on ESPN
            </span>
          </div>

          <div style={styles.actionCardsList}>
            {pendingActions.map((action) => (
              <ActionCard
                key={action.id}
                action={action}
                onActionComplete={handleActionComplete}
                onAskAgent={(prompt) => {
                  window.location.href = `/?prompt=${encodeURIComponent(prompt)}`;
                }}
              />
            ))}
          </div>
        </section>
      )}

      {/* Navigation Tabs */}
      <div style={styles.tabNav}>
        {[
          { id: "FEED", label: "INTELLIGENCE FEED", count: briefings.length },
          { id: "RANKINGS", label: "POWER RANKINGS", count: rankings.length },
          { id: "STRATEGY", label: "MACRO STRATEGY", count: strategy ? 1 : 0 },
          { id: "BUDGET", label: "API TELEMETRY & HEALTH", count: null },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id as any)}
            style={{
              ...styles.tabBtn,
              ...(activeTab === tab.id ? styles.tabBtnActive : {}),
            }}
            className="font-mono"
          >
            {tab.label} {tab.count !== null ? `(${tab.count})` : ""}
          </button>
        ))}
      </div>

      {/* TAB CONTENT */}
      {activeTab === "FEED" && (
        <div style={styles.feedContainer}>
          {briefings.length === 0 ? (
            <div style={styles.emptyCard} className="font-mono">
              NO BRIEFINGS RECORDED YET. CLICK &ldquo;⚡ MORNING BRIEF&rdquo; OR &ldquo;⚡ SCOUT WAIVERS&rdquo; TO TRIGGER AGENTS.
            </div>
          ) : (
            briefings.map((b) => {
              const urgencyColors = {
                CRITICAL: "#ef4444",
                HIGH: "#f59e0b",
                MEDIUM: "#3b82f6",
                LOW: "#10b981",
              };
              const color = urgencyColors[b.urgency] || "#3b82f6";

              return (
                <div
                  key={b.id}
                  onClick={() => {
                    setSelectedBriefing(b);
                    setShowRawJson(false);
                  }}
                  style={{
                    ...styles.briefingCard,
                    borderLeftColor: color,
                    opacity: b.read ? 0.75 : 1,
                    cursor: "pointer",
                  }}
                  className="briefing-card-hover"
                >
                  <div style={styles.briefingTop}>
                    <div style={styles.briefingBadgeRow}>
                      <span
                        style={{ ...styles.urgencyPill, backgroundColor: `${color}20`, color: color }}
                        className="font-mono"
                      >
                        {b.urgency}
                      </span>
                      <span style={styles.typePill} className="font-mono">
                        {b.briefing_type.replace("_", " ")}
                      </span>
                      <span style={styles.sourceAgent} className="font-mono">
                        by {b.source_agent}
                      </span>
                    </div>

                    <div style={styles.briefingMeta}>
                      <span style={styles.briefingTime} className="font-mono">
                        {new Date(b.created_at).toLocaleString([], {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                      {!b.read && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleMarkRead(b.id);
                          }}
                          style={styles.markReadBtn}
                          className="font-mono"
                        >
                          MARK READ
                        </button>
                      )}
                      <span style={styles.expandPrompt} className="font-mono">
                        EXPAND INTEL ↗
                      </span>
                    </div>
                  </div>

                  <h3 style={styles.briefingTitle}>{b.title}</h3>
                  <div className="prose briefing-prose" style={styles.briefingContent}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {formatMarkdownContent(b.content)}
                    </ReactMarkdown>
                  </div>

                  {b.action_items && b.action_items.length > 0 && (
                    <div style={styles.actionItemsBox}>
                      <div style={styles.actionItemsTitle} className="font-mono">
                        RECOMMENDED ACTION STEPS:
                      </div>
                      <div style={styles.actionItemsList}>
                        {b.action_items.map((act, idx) => (
                          <div key={idx} style={styles.actionItemRow} className="font-mono">
                            <span style={styles.actionArrow}>➔</span>
                            <span>{act.label || act.type}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}

      {activeTab === "RANKINGS" && (
        <div style={styles.rankingsContainer}>
          <div style={styles.sectionTitleRow}>
            <div>
              <h2 style={styles.subHeading} className="font-mono">
                OFFICIAL LEAGUE POWER RANKINGS
              </h2>
              <p style={styles.subDesc}>
                Algorithmic composite ranking based on Points For (40%), Records (30%), and Projected Strength (30%)
              </p>
            </div>
            <button
              type="button"
              onClick={() => handleTriggerJob("job_power_rankings", "Power Rankings")}
              style={styles.refreshBtn}
              className="font-mono"
            >
              🔄 RECALCULATE
            </button>
          </div>

          <div style={styles.rankingsGrid}>
            {rankings.map((team) => {
              const isUser = team.team_id === 2; // Team Cooper
              return (
                <div
                  key={team.team_id}
                  style={{
                    ...styles.rankingCard,
                    borderColor: isUser ? "var(--accent-amber)" : "var(--border-subtle)",
                    backgroundColor: isUser ? "rgba(245, 158, 11, 0.05)" : "var(--bg-raised)",
                  }}
                >
                  <div style={styles.rankBadge} className="font-mono">
                    #{team.rank}
                  </div>
                  <div style={styles.rankingBody}>
                    <div style={styles.teamHeaderRow}>
                      <h3 style={styles.teamCardName}>
                        {team.team_name} {isUser && <span style={styles.userTag}>(YOUR TEAM)</span>}
                      </h3>
                      <span style={styles.tierTag} className="font-mono">
                        {team.tier}
                      </span>
                    </div>

                    <div style={styles.teamStatsRow} className="font-mono">
                      <span>
                        RECORD: <strong>{team.wins}-{team.losses}</strong>
                      </span>
                      <span>
                        PTS FOR: <strong>{team.points_for.toFixed(1)}</strong>
                      </span>
                      <span style={{ color: "var(--accent-amber)" }}>
                        POWER SCORE: <strong>{team.power_score.toFixed(1)}</strong>
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {activeTab === "STRATEGY" && strategy && (
        <div style={styles.strategyContainer}>
          <div style={styles.sectionTitleRow}>
            <div>
              <h2 style={styles.subHeading} className="font-mono">
                MACRO SEASON STRATEGY & PLAYOFF ROADMAP
              </h2>
              <p style={styles.subDesc}>
                Season-long tactical objectives, schedule forecasting, and trade deadline directives
              </p>
            </div>
            <button
              type="button"
              onClick={() => handleTriggerJob("job_season_strategy", "Season Strategy")}
              style={styles.refreshBtn}
              className="font-mono"
            >
              🔄 RECALCULATE
            </button>
          </div>

          <div style={styles.strategyCardsGrid}>
            <div style={styles.strategyCard}>
              <div style={styles.stratLabel} className="font-mono">
                PLAYOFF ODDS
              </div>
              <div style={styles.stratBigVal} className="font-mono">
                {strategy.playoff_probability_pct}%
              </div>
              <p style={styles.stratText}>
                Based on current {strategy.current_record} standing and projected 3-WR roster scoring power.
              </p>
            </div>

            <div style={styles.strategyCard}>
              <div style={styles.stratLabel} className="font-mono">
                PLAYOFF SCHEDULE GRADE
              </div>
              <div style={{ ...styles.stratBigVal, color: "#10b981" }} className="font-mono">
                {strategy.playoff_schedule_grade.split(" ")[0]}
              </div>
              <p style={styles.stratText}>
                Weeks 15-17 defense matchups favor our high-volume pass-catching core.
              </p>
            </div>

            <div style={styles.strategyCard}>
              <div style={styles.stratLabel} className="font-mono">
                UPCOMING BYE WEEK RISKS
              </div>
              {strategy.bye_week_crunches.map((b) => (
                <div key={b.week} style={styles.byeRow} className="font-mono">
                  <span>WEEK {b.week}:</span>
                  <span style={{ color: "var(--accent-amber)" }}>{b.impact}</span>
                </div>
              ))}
            </div>
          </div>

          <div style={styles.directivesCard}>
            <h3 style={styles.directivesTitle} className="font-mono">
              STRATEGIC OPERATIONAL DIRECTIVES
            </h3>
            <ul style={styles.directivesList}>
              {strategy.strategic_directives.map((dir, idx) => (
                <li key={idx} style={styles.directiveItem}>
                  {dir}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {activeTab === "BUDGET" && (
        <div style={styles.telemetryContainer}>
          <div style={styles.sectionTitleRow}>
            <h2 style={styles.subHeading} className="font-mono">
              API USAGE & SYSTEM HEALTH
            </h2>
          </div>

          {budget && (
            <div style={styles.budgetBox}>
              <div style={styles.healthHeader} className="font-mono">
                FREE-TIER LLM RATE LIMIT BUDGETS
              </div>
              <BudgetBar
                label="Gemini Requests Per Day (RPD)"
                used={budget.gemini?.rpd_used || 0}
                limit={budget.gemini?.rpd_limit || 1500}
                unit="req"
              />
              <BudgetBar
                label="Gemini Requests Per Min (RPM)"
                used={budget.gemini?.rpm_used || 0}
                limit={budget.gemini?.rpm_limit || 15}
                unit="req"
              />
              <BudgetBar
                label="Groq Requests Per Day (RPD)"
                used={budget.groq?.rpd_used || 0}
                limit={budget.groq?.rpd_limit || 14400}
                unit="req"
              />
              <BudgetBar
                label="Groq Tokens Per Min (TPM)"
                used={budget.groq?.tpm_used || 0}
                limit={budget.groq?.tpm_limit || 6000}
                unit="tokens"
              />
            </div>
          )}

          {health && (
            <div style={styles.healthBox}>
              <div style={styles.healthHeader} className="font-mono">
                KUBERNETES & ESPN HEALTH STATUS
              </div>
              <div style={styles.healthGrid} className="font-mono">
                <div style={styles.healthItem}>
                  <span>SERVICE:</span> <strong>{health.service}</strong>
                </div>
                <div style={styles.healthItem}>
                  <span>STATUS:</span> <strong style={{ color: "#10b981" }}>{health.status.toUpperCase()}</strong>
                </div>
                <div style={styles.healthItem}>
                  <span>ESPN CREDENTIALS:</span>{" "}
                  <strong style={{ color: health.espn_auth.valid ? "#10b981" : "#f59e0b" }}>
                    {health.espn_auth.valid ? "AUTHENTICATED" : "MOCK/OFFLINE"}
                  </strong>
                </div>
                <div style={styles.healthItem}>
                  <span>CACHE HIT RATE:</span>{" "}
                  <strong>{health.cache_metrics.hit_rate_pct.toFixed(1)}%</strong>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* FULL INTEL DOSSIER MODAL */}
      {selectedBriefing && (
        <div
          style={styles.modalBackdrop}
          onClick={() => setSelectedBriefing(null)}
        >
          <div
            style={{
              ...styles.modalBox,
              borderLeftColor:
                {
                  CRITICAL: "#ef4444",
                  HIGH: "#f59e0b",
                  MEDIUM: "#3b82f6",
                  LOW: "#10b981",
                }[selectedBriefing.urgency] || "var(--border-subtle)",
            }}
            className="modal-animate"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Top Bar */}
            <div style={styles.modalHeader}>
              <div style={styles.briefingBadgeRow}>
                <span
                  style={{
                    ...styles.urgencyPill,
                    backgroundColor: `${
                      {
                        CRITICAL: "#ef4444",
                        HIGH: "#f59e0b",
                        MEDIUM: "#3b82f6",
                        LOW: "#10b981",
                      }[selectedBriefing.urgency] || "#3b82f6"
                    }20`,
                    color:
                      {
                        CRITICAL: "#ef4444",
                        HIGH: "#f59e0b",
                        MEDIUM: "#3b82f6",
                        LOW: "#10b981",
                      }[selectedBriefing.urgency] || "#3b82f6",
                  }}
                  className="font-mono"
                >
                  {selectedBriefing.urgency}
                </span>
                <span style={styles.typePill} className="font-mono">
                  {selectedBriefing.briefing_type.replace("_", " ")}
                </span>
                <span style={styles.sourceAgent} className="font-mono">
                  SOURCE: {selectedBriefing.source_agent}
                </span>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <span style={styles.briefingTime} className="font-mono">
                  {new Date(selectedBriefing.created_at).toLocaleString([], {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedBriefing(null)}
                  style={styles.modalCloseBtn}
                  className="font-mono"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Modal Title */}
            <h2 style={styles.modalTitle}>{selectedBriefing.title}</h2>

            {/* Modal Scrollable Body */}
            <div style={styles.modalScrollArea}>
              {/* Full Markdown Intel */}
              <div className="prose briefing-prose" style={styles.modalContentProse}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {formatMarkdownContent(selectedBriefing.content)}
                </ReactMarkdown>
              </div>

              {/* Special Structured Data Panels */}
              {selectedBriefing.structured_data && (
                <div style={styles.structuredSection}>
                  {/* Flagged Players (Practice / Injury Intel) */}
                  {Array.isArray((selectedBriefing.structured_data as any).flagged_players) && (
                    <div style={styles.flaggedPanel}>
                      <div style={styles.structuredTitle} className="font-mono">
                        🏥 DETAILED MEDICAL & PARTICIPATION DOSSIER
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                        {(selectedBriefing.structured_data as any).flagged_players.map((fp: any, idx: number) => (
                          <div key={idx} style={styles.playerDossierCard}>
                            <div style={styles.playerDossierHeader}>
                              <span style={styles.playerDossierName}>{fp.player}</span>
                              <span style={styles.playerDossierStatus} className="font-mono">
                                {fp.status}
                              </span>
                            </div>
                            <div style={styles.playerDossierText}>
                              {fp.summary || "No specific practice restrictions reported."}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* League Rankings Table if present in structured_data */}
                  {Array.isArray((selectedBriefing.structured_data as any).rankings) && (
                    <div style={styles.rankingsTableWrap}>
                      <div style={styles.structuredTitle} className="font-mono">
                        📊 COMPLETE 10-TEAM POWER RANKINGS BREAKDOWN
                      </div>
                      <table style={styles.rankingsTable}>
                        <thead>
                          <tr>
                            <th style={styles.th}>RANK</th>
                            <th style={styles.th}>TEAM</th>
                            <th style={styles.th}>RECORD</th>
                            <th style={styles.th}>PTS FOR</th>
                            <th style={styles.th}>POWER SCORE</th>
                            <th style={styles.th}>TIER</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(selectedBriefing.structured_data as any).rankings.map((tm: any) => (
                            <tr
                              key={tm.team_id}
                              style={{
                                backgroundColor: tm.team_id === 2 ? "rgba(245, 158, 11, 0.12)" : "transparent",
                              }}
                            >
                              <td style={styles.tdBold}>#{tm.rank}</td>
                              <td style={styles.td}>
                                {tm.team_name} {tm.team_id === 2 ? <strong style={{ color: "var(--accent-amber)" }}>(YOU)</strong> : ""}
                              </td>
                              <td style={styles.tdMono}>{tm.wins}-{tm.losses}</td>
                              <td style={styles.tdMono}>{Number(tm.points_for).toFixed(1)}</td>
                              <td style={{ ...styles.tdMono, color: "var(--accent-amber)" }}>
                                {Number(tm.power_score).toFixed(1)}
                              </td>
                              <td style={styles.tdTier}>{tm.tier}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Toggle raw JSON telemetry */}
                  <div style={{ marginTop: "16px" }}>
                    <button
                      type="button"
                      onClick={() => setShowRawJson(!showRawJson)}
                      style={styles.rawJsonToggle}
                      className="font-mono"
                    >
                      {showRawJson ? "▲ HIDE TELEMETRY DATA" : "▼ VIEW RAW INTELLIGENCE PAYLOAD (JSON)"}
                    </button>
                    {showRawJson && (
                      <pre style={styles.rawJsonBox} className="font-mono">
                        {JSON.stringify(selectedBriefing.structured_data, null, 2)}
                      </pre>
                    )}
                  </div>
                </div>
              )}

              {/* Action Items Box */}
              {selectedBriefing.action_items && selectedBriefing.action_items.length > 0 && (
                <div style={styles.actionItemsBox}>
                  <div style={styles.actionItemsTitle} className="font-mono">
                    RECOMMENDED STRATEGIC ACTIONS:
                  </div>
                  <div style={styles.actionItemsList}>
                    {selectedBriefing.action_items.map((act, idx) => (
                      <div key={idx} style={styles.actionItemRow} className="font-mono">
                        <span style={styles.actionArrow}>➔</span>
                        <span>{act.label || act.type}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer Controls */}
            <div style={styles.modalFooter}>
              <button
                type="button"
                onClick={() => {
                  const query = `Regarding briefing "${selectedBriefing.title}": Can you give me an in-depth strategic breakdown and what actions I should take?`;
                  window.location.href = `/?prompt=${encodeURIComponent(query)}`;
                }}
                style={styles.modalDiscussBtn}
                className="font-mono"
              >
                💬 DISCUSS WITH GENERAL MANAGER
              </button>

              <div style={{ display: "flex", gap: "10px" }}>
                {!selectedBriefing.read && (
                  <button
                    type="button"
                    onClick={() => {
                      handleMarkRead(selectedBriefing.id);
                      setSelectedBriefing({ ...selectedBriefing, read: true });
                    }}
                    style={styles.modalMarkReadBtn}
                    className="font-mono"
                  >
                    ✓ MARK READ
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setSelectedBriefing(null)}
                  style={styles.modalCloseFooterBtn}
                  className="font-mono"
                >
                  CLOSE
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: "var(--space-6) var(--space-8)",
    maxWidth: "1400px",
    margin: "0 auto",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: "var(--space-6)",
    flexWrap: "wrap",
    gap: "var(--space-4)",
    borderBottom: "1px solid var(--border-subtle)",
    paddingBottom: "var(--space-5)",
  },
  preTitle: {
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--accent-amber)",
    letterSpacing: "0.1em",
    marginBottom: "4px",
  },
  title: {
    fontSize: "24px",
    fontWeight: 800,
    color: "var(--text-primary)",
    margin: "0 0 8px 0",
    letterSpacing: "-0.02em",
  },
  streamIndicator: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  dot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
  },
  streamText: {
    fontSize: "11px",
    color: "var(--text-dim)",
    letterSpacing: "0.05em",
  },
  headerActions: {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-end",
    gap: "var(--space-2)",
  },
  statusBadge: {
    fontSize: "12px",
    color: "var(--accent-amber)",
    backgroundColor: "var(--bg-surface)",
    padding: "6px 12px",
    borderRadius: "4px",
    border: "1px solid var(--border-subtle)",
  },
  buttonRow: {
    display: "flex",
    gap: "var(--space-2)",
  },
  triggerBtn: {
    backgroundColor: "var(--bg-surface)",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-primary)",
    fontSize: "11px",
    fontWeight: 700,
    padding: "8px 14px",
    borderRadius: "4px",
    cursor: "pointer",
    letterSpacing: "0.05em",
  },
  approvalSection: {
    backgroundColor: "rgba(239, 68, 68, 0.04)",
    border: "1px solid rgba(239, 68, 68, 0.3)",
    borderRadius: "8px",
    padding: "var(--space-5)",
    marginBottom: "var(--space-6)",
  },
  approvalHeader: {
    marginBottom: "var(--space-4)",
  },
  approvalTitleGroup: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
  },
  pulseDot: {
    width: "10px",
    height: "10px",
    borderRadius: "50%",
    backgroundColor: "#ef4444",
    boxShadow: "0 0 10px #ef4444",
  },
  approvalTitle: {
    fontSize: "15px",
    fontWeight: 800,
    color: "#ef4444",
    margin: 0,
    letterSpacing: "0.05em",
  },
  approvalSubtitle: {
    fontSize: "12px",
    color: "var(--text-secondary)",
    marginTop: "4px",
    display: "block",
  },
  actionCardsList: {
    display: "flex",
    flexDirection: "column",
  },
  tabNav: {
    display: "flex",
    gap: "var(--space-2)",
    marginBottom: "var(--space-6)",
    borderBottom: "1px solid var(--border-subtle)",
    paddingBottom: "var(--space-2)",
  },
  tabBtn: {
    background: "transparent",
    border: "none",
    color: "var(--text-dim)",
    fontSize: "12px",
    fontWeight: 700,
    padding: "8px 16px",
    cursor: "pointer",
    borderRadius: "4px",
  },
  tabBtnActive: {
    backgroundColor: "var(--bg-surface)",
    color: "var(--accent-amber)",
    border: "1px solid var(--border-subtle)",
  },
  feedContainer: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-4)",
  },
  emptyCard: {
    padding: "var(--space-12)",
    textAlign: "center",
    backgroundColor: "var(--bg-raised)",
    border: "1px dashed var(--border-subtle)",
    borderRadius: "8px",
    color: "var(--text-dim)",
    fontSize: "12px",
  },
  briefingCard: {
    backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)",
    borderLeftWidth: "4px",
    borderRadius: "6px",
    padding: "var(--space-5)",
  },
  briefingTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "var(--space-2)",
    flexWrap: "wrap",
    gap: "var(--space-2)",
  },
  briefingBadgeRow: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-2)",
  },
  urgencyPill: {
    fontSize: "10px",
    fontWeight: 700,
    padding: "2px 8px",
    borderRadius: "3px",
  },
  typePill: {
    fontSize: "10px",
    fontWeight: 600,
    backgroundColor: "var(--bg-surface)",
    color: "var(--text-secondary)",
    padding: "2px 8px",
    borderRadius: "3px",
  },
  sourceAgent: {
    fontSize: "10px",
    color: "var(--text-dim)",
  },
  briefingMeta: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-3)",
  },
  briefingTime: {
    fontSize: "11px",
    color: "var(--text-dim)",
  },
  markReadBtn: {
    background: "transparent",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-muted)",
    fontSize: "9px",
    padding: "2px 6px",
    borderRadius: "3px",
    cursor: "pointer",
  },
  briefingTitle: {
    fontSize: "16px",
    fontWeight: 700,
    color: "var(--text-primary)",
    margin: "0 0 var(--space-3) 0",
  },
  briefingContent: {
    fontSize: "13px",
    color: "var(--text-secondary)",
    lineHeight: 1.6,
  },
  para: {
    margin: "0 0 var(--space-2) 0",
  },
  actionItemsBox: {
    marginTop: "var(--space-4)",
    backgroundColor: "var(--bg-base)",
    padding: "var(--space-3)",
    borderRadius: "4px",
    border: "1px solid var(--border-subtle)",
  },
  actionItemsTitle: {
    fontSize: "10px",
    color: "var(--accent-amber)",
    marginBottom: "var(--space-2)",
  },
  actionItemsList: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  actionItemRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    fontSize: "12px",
    color: "var(--text-primary)",
  },
  actionArrow: {
    color: "var(--accent-amber)",
    fontSize: "10px",
  },
  rankingsContainer: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-4)",
  },
  sectionTitleRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: "var(--space-4)",
  },
  subHeading: {
    fontSize: "16px",
    fontWeight: 800,
    color: "var(--text-primary)",
    margin: "0 0 4px 0",
  },
  subDesc: {
    fontSize: "12px",
    color: "var(--text-secondary)",
    margin: 0,
  },
  refreshBtn: {
    background: "transparent",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-secondary)",
    fontSize: "11px",
    padding: "6px 12px",
    borderRadius: "4px",
    cursor: "pointer",
  },
  rankingsGrid: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-3)",
  },
  rankingCard: {
    display: "flex",
    alignItems: "center",
    border: "1px solid var(--border-subtle)",
    borderRadius: "6px",
    padding: "var(--space-3) var(--space-4)",
    gap: "var(--space-4)",
  },
  rankBadge: {
    fontSize: "18px",
    fontWeight: 800,
    color: "var(--accent-amber)",
    width: "45px",
  },
  rankingBody: {
    flex: 1,
  },
  teamHeaderRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "var(--space-1)",
  },
  teamCardName: {
    fontSize: "15px",
    fontWeight: 700,
    color: "var(--text-primary)",
    margin: 0,
  },
  userTag: {
    fontSize: "11px",
    color: "var(--accent-amber)",
    marginLeft: "6px",
  },
  tierTag: {
    fontSize: "11px",
    color: "var(--text-dim)",
  },
  teamStatsRow: {
    display: "flex",
    gap: "var(--space-6)",
    fontSize: "11px",
    color: "var(--text-secondary)",
  },
  strategyContainer: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-5)",
  },
  strategyCardsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
    gap: "var(--space-4)",
  },
  strategyCard: {
    backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "6px",
    padding: "var(--space-5)",
  },
  stratLabel: {
    fontSize: "10px",
    color: "var(--text-dim)",
    marginBottom: "var(--space-2)",
  },
  stratBigVal: {
    fontSize: "32px",
    fontWeight: 800,
    color: "var(--accent-amber)",
    marginBottom: "var(--space-2)",
  },
  stratText: {
    fontSize: "12px",
    color: "var(--text-secondary)",
    margin: 0,
    lineHeight: 1.4,
  },
  byeRow: {
    display: "flex",
    justifyContent: "space-between",
    fontSize: "12px",
    marginBottom: "4px",
  },
  directivesCard: {
    backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "6px",
    padding: "var(--space-5)",
  },
  directivesTitle: {
    fontSize: "13px",
    fontWeight: 700,
    color: "var(--accent-amber)",
    marginBottom: "var(--space-3)",
  },
  directivesList: {
    margin: 0,
    paddingLeft: "var(--space-4)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-2)",
  },
  directiveItem: {
    fontSize: "13px",
    color: "var(--text-secondary)",
    lineHeight: 1.5,
  },
  telemetryContainer: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-5)",
  },
  budgetBox: {
    backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "6px",
    padding: "var(--space-5)",
  },
  healthBox: {
    backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "6px",
    padding: "var(--space-5)",
  },
  healthHeader: {
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--text-dim)",
    marginBottom: "var(--space-3)",
  },
  healthGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: "var(--space-3)",
    fontSize: "12px",
  },
  healthItem: {
    display: "flex",
    justifyContent: "space-between",
    backgroundColor: "var(--bg-surface)",
    padding: "var(--space-3)",
    borderRadius: "4px",
  },
  expandPrompt: {
    fontSize: "9px",
    fontWeight: 700,
    color: "var(--accent-amber)",
    border: "1px solid rgba(245, 158, 11, 0.3)",
    backgroundColor: "rgba(245, 158, 11, 0.08)",
    padding: "2px 6px",
    borderRadius: "3px",
    letterSpacing: "0.05em",
  },
  modalBackdrop: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(0, 0, 0, 0.78)",
    backdropFilter: "blur(6px)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 9999,
    padding: "var(--space-4)",
  },
  modalBox: {
    backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)",
    borderLeftWidth: "5px",
    borderRadius: "10px",
    width: "100%",
    maxWidth: "840px",
    maxHeight: "88vh",
    display: "flex",
    flexDirection: "column",
    boxShadow: "0 16px 40px rgba(0, 0, 0, 0.65)",
    overflow: "hidden",
  },
  modalHeader: {
    padding: "var(--space-4) var(--space-5)",
    borderBottom: "1px solid var(--border-subtle)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    backgroundColor: "var(--bg-surface)",
  },
  modalCloseBtn: {
    background: "transparent",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-dim)",
    fontSize: "13px",
    fontWeight: 700,
    cursor: "pointer",
    padding: "4px 8px",
    borderRadius: "4px",
  },
  modalTitle: {
    fontSize: "18px",
    fontWeight: 800,
    color: "var(--text-primary)",
    margin: "0",
    padding: "var(--space-4) var(--space-5) var(--space-2) var(--space-5)",
    borderBottom: "1px solid var(--border-subtle)",
    letterSpacing: "-0.01em",
  },
  modalScrollArea: {
    padding: "var(--space-5)",
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-4)",
  },
  modalContentProse: {
    fontSize: "14px",
    color: "var(--text-secondary)",
    lineHeight: 1.65,
  },
  structuredSection: {
    marginTop: "var(--space-3)",
    paddingTop: "var(--space-4)",
    borderTop: "1px solid var(--border-subtle)",
  },
  structuredTitle: {
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--accent-amber)",
    letterSpacing: "0.08em",
    marginBottom: "var(--space-3)",
  },
  flaggedPanel: {
    backgroundColor: "var(--bg-base)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "6px",
    padding: "var(--space-4)",
  },
  playerDossierCard: {
    backgroundColor: "var(--bg-surface)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "5px",
    padding: "var(--space-3)",
  },
  playerDossierHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "6px",
  },
  playerDossierName: {
    fontSize: "14px",
    fontWeight: 700,
    color: "var(--text-primary)",
  },
  playerDossierStatus: {
    fontSize: "10px",
    fontWeight: 700,
    color: "#f59e0b",
    backgroundColor: "rgba(245, 158, 11, 0.15)",
    padding: "2px 6px",
    borderRadius: "3px",
  },
  playerDossierText: {
    fontSize: "12.5px",
    color: "var(--text-secondary)",
    lineHeight: 1.5,
  },
  rankingsTableWrap: {
    backgroundColor: "var(--bg-base)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "6px",
    padding: "var(--space-4)",
    overflowX: "auto",
  },
  rankingsTable: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "12.5px",
  },
  th: {
    textAlign: "left",
    padding: "6px 8px",
    color: "var(--text-dim)",
    fontSize: "10.5px",
    fontWeight: 700,
    borderBottom: "1px solid var(--border-subtle)",
    letterSpacing: "0.05em",
  },
  td: {
    padding: "6px 8px",
    color: "var(--text-primary)",
    borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
  },
  tdBold: {
    padding: "6px 8px",
    color: "var(--text-primary)",
    fontWeight: 700,
    borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
  },
  tdMono: {
    padding: "6px 8px",
    color: "var(--text-secondary)",
    fontFamily: "var(--font-mono)",
    borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
  },
  tdTier: {
    padding: "6px 8px",
    color: "var(--text-dim)",
    fontSize: "11px",
    fontStyle: "italic",
    borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
  },
  rawJsonToggle: {
    background: "transparent",
    border: "1px dashed var(--border-subtle)",
    color: "var(--text-dim)",
    fontSize: "10px",
    padding: "4px 8px",
    borderRadius: "4px",
    cursor: "pointer",
  },
  rawJsonBox: {
    marginTop: "8px",
    backgroundColor: "var(--bg-base)",
    padding: "var(--space-3)",
    borderRadius: "4px",
    fontSize: "11px",
    color: "var(--text-muted)",
    maxHeight: "180px",
    overflowY: "auto",
  },
  modalFooter: {
    padding: "var(--space-4) var(--space-5)",
    borderTop: "1px solid var(--border-subtle)",
    backgroundColor: "var(--bg-surface)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    flexWrap: "wrap",
    gap: "var(--space-3)",
  },
  modalDiscussBtn: {
    backgroundColor: "var(--accent-amber)",
    color: "#000000",
    border: "none",
    fontSize: "11px",
    fontWeight: 700,
    padding: "8px 16px",
    borderRadius: "4px",
    cursor: "pointer",
  },
  modalMarkReadBtn: {
    backgroundColor: "transparent",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-primary)",
    fontSize: "11px",
    fontWeight: 600,
    padding: "8px 14px",
    borderRadius: "4px",
    cursor: "pointer",
  },
  modalCloseFooterBtn: {
    backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-dim)",
    fontSize: "11px",
    fontWeight: 600,
    padding: "8px 14px",
    borderRadius: "4px",
    cursor: "pointer",
  },
};
