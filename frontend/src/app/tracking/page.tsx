"use client";

import React, { useState, useEffect, useCallback } from "react";
import { TrackingJob } from "@/lib/types";
import {
  getTrackingJobs,
  createTrackingJob,
  cancelTrackingJob,
  triggerTrackingJob,
} from "@/lib/api";

export default function TrackingPage() {
  const [jobs, setJobs] = useState<TrackingJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"ACTIVE" | "ALL">("ACTIVE");
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // New Watch Modal state
  const [showModal, setShowModal] = useState(false);
  const [playerName, setPlayerName] = useState("");
  const [frequency, setFrequency] = useState(60);
  const [duration, setDuration] = useState(48);
  const [customQuery, setCustomQuery] = useState("");
  const [focusAreas, setFocusAreas] = useState<string[]>([
    "injury",
    "practice",
    "depth_chart",
    "sentiment",
  ]);
  const [submitting, setSubmitting] = useState(false);

  const fetchJobs = useCallback(async () => {
    try {
      const res = await getTrackingJobs(filter === "ALL");
      setJobs(res.jobs || []);
    } catch (err: any) {
      console.error("Failed to load tracking jobs:", err);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchJobs();
    const timer = setInterval(fetchJobs, 15000);
    return () => clearInterval(timer);
  }, [fetchJobs]);

  const handleCancel = async (jobId: string, name: string) => {
    try {
      await cancelTrackingJob(jobId);
      setStatusMsg(`Surveillance halted for ${name}.`);
      await fetchJobs();
    } catch (err: any) {
      setStatusMsg(`Failed to cancel: ${err.message}`);
    }
  };

  const handleTriggerNow = async (jobId: string, name: string) => {
    try {
      await triggerTrackingJob(jobId);
      setStatusMsg(`Surveillance tick triggered for ${name}.`);
      await fetchJobs();
    } catch (err: any) {
      setStatusMsg(`Failed to trigger: ${err.message}`);
    }
  };

  const handleCreateWatch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!playerName.trim()) return;

    setSubmitting(true);
    setStatusMsg(null);
    try {
      await createTrackingJob({
        player_name: playerName.trim(),
        frequency_minutes: frequency,
        duration_hours: duration,
        focus_areas: focusAreas,
        custom_query: customQuery.trim() || undefined,
        reason: "Initiated from Surveillance Command Center",
      });
      setShowModal(false);
      setPlayerName("");
      setCustomQuery("");
      setStatusMsg(`Autonomous surveillance job active for ${playerName}!`);
      await fetchJobs();
    } catch (err: any) {
      setStatusMsg(`Error creating job: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const toggleFocusArea = (area: string) => {
    setFocusAreas((prev) =>
      prev.includes(area) ? prev.filter((a) => a !== area) : [...prev, area]
    );
  };

  const activeCount = jobs.filter((j) => j.status === "ACTIVE").length;

  return (
    <div style={styles.container}>
      {/* Page Header */}
      <header style={styles.header}>
        <div>
          <div style={styles.preTitle} className="font-mono">
            AUTONOMOUS SURVEILLANCE FLEET
          </div>
          <h1 style={styles.title} className="font-mono">
            PLAYER TRACKING & ADAPTIVE JOBS
          </h1>
          <p style={styles.subTitle}>
            Background agents monitoring injury logs, practice participation, and breaking web news
          </p>
        </div>

        <div style={styles.headerControls}>
          {statusMsg && (
            <span style={styles.statusMsg} className="font-mono">
              {statusMsg}
            </span>
          )}
          <button
            type="button"
            onClick={() => setShowModal(true)}
            style={styles.newWatchBtn}
            className="font-mono"
          >
            + SPAWN NEW WATCH
          </button>
        </div>
      </header>

      {/* Filter Tabs */}
      <div style={styles.tabRow}>
        <div style={styles.tabGroup}>
          <button
            type="button"
            onClick={() => setFilter("ACTIVE")}
            style={{
              ...styles.tabBtn,
              ...(filter === "ACTIVE" ? styles.tabBtnActive : {}),
            }}
            className="font-mono"
          >
            ACTIVE JOBS ({activeCount})
          </button>
          <button
            type="button"
            onClick={() => setFilter("ALL")}
            style={{
              ...styles.tabBtn,
              ...(filter === "ALL" ? styles.tabBtnActive : {}),
            }}
            className="font-mono"
          >
            ALL ARCHIVES ({jobs.length})
          </button>
        </div>

        <div style={styles.legendWrap} className="font-mono">
          <span style={styles.legendItem}>
            <span style={{ ...styles.dot, backgroundColor: "#10b981" }} /> ACTIVE
          </span>
          <span style={styles.legendItem}>
            <span style={{ ...styles.dot, backgroundColor: "#f59e0b" }} /> ESCALATED
          </span>
          <span style={styles.legendItem}>
            <span style={{ ...styles.dot, backgroundColor: "#6b7280" }} /> EXPIRED
          </span>
        </div>
      </div>

      {/* Main Jobs Grid */}
      {loading ? (
        <div style={styles.emptyBox} className="font-mono">
          LOADING ACTIVE SURVEILLANCE FLEET...
        </div>
      ) : jobs.length === 0 ? (
        <div style={styles.emptyBox}>
          <div style={styles.emptyTitle} className="font-mono">
            NO ACTIVE SURVEILLANCE JOBS
          </div>
          <p style={styles.emptyText}>
            Ask the General Manager in chat (e.g. &ldquo;Keep up with Caleb Williams&rdquo;) or click
            &ldquo;+ SPAWN NEW WATCH&rdquo; to deploy autonomous agents.
          </p>
          <button
            type="button"
            onClick={() => setShowModal(true)}
            style={styles.emptyBtn}
            className="font-mono"
          >
            DEPLOY FIRST WATCH
          </button>
        </div>
      ) : (
        <div style={styles.grid}>
          {jobs.map((job) => {
            const isActive = job.status === "ACTIVE";
            const isEscalated = job.frequency_minutes <= 30 && isActive;

            return (
              <div
                key={job.job_id}
                style={{
                  ...styles.jobCard,
                  borderColor: isEscalated
                    ? "rgba(245, 158, 11, 0.4)"
                    : isActive
                    ? "var(--border-subtle)"
                    : "rgba(255, 255, 255, 0.05)",
                  opacity: isActive ? 1 : 0.65,
                }}
              >
                {/* Job Card Top */}
                <div style={styles.jobTop}>
                  <div>
                    <div style={styles.jobBadgeRow}>
                      <span
                        style={{
                          ...styles.statusBadge,
                          backgroundColor: isEscalated
                            ? "rgba(245, 158, 11, 0.15)"
                            : isActive
                            ? "rgba(16, 185, 129, 0.15)"
                            : "rgba(107, 114, 128, 0.15)",
                          color: isEscalated
                            ? "#f59e0b"
                            : isActive
                            ? "#10b981"
                            : "#9ca3af",
                        }}
                        className="font-mono"
                      >
                        {isEscalated ? "⚡ ESCALATED" : job.status}
                      </span>
                      <span style={styles.intervalBadge} className="font-mono">
                        EVERY {job.frequency_minutes}M
                      </span>
                      <span style={styles.sourceBadge} className="font-mono">
                        SRC: {job.source.toUpperCase()}
                      </span>
                    </div>
                    <h2 style={styles.playerName}>{job.player_name}</h2>
                  </div>

                  {isActive && (
                    <div style={styles.jobActionButtons}>
                      <button
                        type="button"
                        onClick={() => handleTriggerNow(job.job_id, job.player_name)}
                        title="Run check immediately"
                        style={styles.pollBtn}
                        className="font-mono"
                      >
                        ⚡ RUN NOW
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCancel(job.job_id, job.player_name)}
                        title="Cancel this surveillance job"
                        style={styles.cancelBtn}
                        className="font-mono"
                      >
                        ✕ CANCEL
                      </button>
                    </div>
                  )}
                </div>

                {/* Job Reason & Focus */}
                <div style={styles.jobBody}>
                  <p style={styles.reasonText}>
                    <span style={styles.reasonLabel} className="font-mono">
                      OBJECTIVE:
                    </span>{" "}
                    {job.reason}
                  </p>

                  <div style={styles.tagWrap}>
                    {job.focus_areas.map((area) => (
                      <span key={area} style={styles.focusTag} className="font-mono">
                        #{area}
                      </span>
                    ))}
                  </div>

                  {job.custom_query && (
                    <div style={styles.querySnippet} className="font-mono">
                      QUERY: &ldquo;{job.custom_query}&rdquo;
                    </div>
                  )}
                </div>

                {/* Telemetry Footer */}
                <div style={styles.jobFooter} className="font-mono">
                  <div style={styles.telemetryItem}>
                    <span style={styles.telemetryLabel}>RUN COUNT</span>
                    <span style={styles.telemetryVal}>{job.run_count} ticks</span>
                  </div>
                  <div style={styles.telemetryItem}>
                    <span style={styles.telemetryLabel}>LAST TICK</span>
                    <span style={styles.telemetryVal}>
                      {job.last_run_at
                        ? new Date(job.last_run_at).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })
                        : "Pending first run"}
                    </span>
                  </div>
                  <div style={styles.telemetryItem}>
                    <span style={styles.telemetryLabel}>EXPIRES</span>
                    <span style={styles.telemetryVal}>
                      {job.expires_at
                        ? new Date(job.expires_at).toLocaleDateString([], {
                            month: "short",
                            day: "numeric",
                          })
                        : "Indefinite"}
                    </span>
                  </div>
                </div>

                {/* Escalation / Modification History */}
                {job.history && job.history.length > 1 && (
                  <div style={styles.historyDrawer}>
                    <div style={styles.historyTitle} className="font-mono">
                      ADAPTIVE SCHEDULE LOG
                    </div>
                    {job.history.slice(-3).map((h, idx) => (
                      <div key={idx} style={styles.historyRow} className="font-mono">
                        <span style={styles.historyTime}>
                          {new Date(h.timestamp).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                        <span style={styles.historyEvent}>[{h.event}]</span>
                        <span style={styles.historyReason}>{h.reason}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* New Surveillance Modal */}
      {showModal && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalBox}>
            <div style={styles.modalHeader}>
              <h2 style={styles.modalTitle} className="font-mono">
                DEPLOY AUTONOMOUS PLAYER SURVEILLANCE
              </h2>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                style={styles.modalCloseBtn}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateWatch} style={styles.modalForm}>
              <div style={styles.formGroup}>
                <label style={styles.label} className="font-mono">
                  PLAYER NAME *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Caleb Williams, Christian McCaffrey"
                  value={playerName}
                  onChange={(e) => setPlayerName(e.target.value)}
                  style={styles.input}
                  required
                  autoFocus
                />
              </div>

              <div style={styles.formRow}>
                <div style={styles.formGroup}>
                  <label style={styles.label} className="font-mono">
                    SURVEILLANCE INTERVAL
                  </label>
                  <select
                    value={frequency}
                    onChange={(e) => setFrequency(Number(e.target.value))}
                    style={styles.select}
                    className="font-mono"
                  >
                    <option value={15}>Every 15 minutes (Critical)</option>
                    <option value={30}>Every 30 minutes (Active Injury)</option>
                    <option value={60}>Every 1 hour (Standard Watch)</option>
                    <option value={120}>Every 2 hours (General Intel)</option>
                    <option value={360}>Every 6 hours (Deep Radar)</option>
                  </select>
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.label} className="font-mono">
                    DURATION
                  </label>
                  <select
                    value={duration}
                    onChange={(e) => setDuration(Number(e.target.value))}
                    style={styles.select}
                    className="font-mono"
                  >
                    <option value={24}>24 Hours (Next Day)</option>
                    <option value={48}>48 Hours (Weekend Kickoff)</option>
                    <option value={72}>72 Hours (3 Days)</option>
                    <option value={168}>7 Days (Full Fantasy Week)</option>
                  </select>
                </div>
              </div>

              <div style={styles.formGroup}>
                <label style={styles.label} className="font-mono">
                  SURVEILLANCE FOCUS DOMAINS
                </label>
                <div style={styles.checkboxGrid}>
                  {[
                    { id: "injury", label: "Injury Tags & Severity" },
                    { id: "practice", label: "Practice Logs (DNP/LP/FP)" },
                    { id: "depth_chart", label: "Depth Chart & Snaps" },
                    { id: "sentiment", label: "Beat Writers & Reddit" },
                  ].map((f) => (
                    <label key={f.id} style={styles.checkboxLabel}>
                      <input
                        type="checkbox"
                        checked={focusAreas.includes(f.id)}
                        onChange={() => toggleFocusArea(f.id)}
                        style={{ accentColor: "var(--accent-amber)" }}
                      />
                      <span style={styles.checkboxText}>{f.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div style={styles.formGroup}>
                <label style={styles.label} className="font-mono">
                  CUSTOM SEARCH DIRECTIVE (OPTIONAL)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Monitor ankle recovery and Friday walk-through participation"
                  value={customQuery}
                  onChange={(e) => setCustomQuery(e.target.value)}
                  style={styles.input}
                />
              </div>

              <div style={styles.modalActions}>
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  style={styles.modalCancelBtn}
                  className="font-mono"
                >
                  CANCEL
                </button>
                <button
                  type="submit"
                  disabled={submitting || !playerName.trim()}
                  style={styles.modalSubmitBtn}
                  className="font-mono"
                >
                  {submitting ? "SCHEDULING..." : "DEPLOY SURVEILLANCE"}
                </button>
              </div>
            </form>
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
    fontSize: "22px",
    fontWeight: 800,
    color: "var(--text-primary)",
    margin: "0 0 6px 0",
    letterSpacing: "-0.02em",
  },
  subTitle: {
    fontSize: "13px",
    color: "var(--text-secondary)",
    margin: 0,
  },
  headerControls: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-3)",
  },
  statusMsg: {
    fontSize: "12px",
    color: "var(--accent-amber)",
    padding: "6px 12px",
    backgroundColor: "var(--bg-surface)",
    borderRadius: "4px",
    border: "1px solid var(--border-subtle)",
  },
  newWatchBtn: {
    backgroundColor: "var(--accent-amber)",
    color: "#000000",
    fontWeight: 800,
    fontSize: "12px",
    padding: "8px 18px",
    borderRadius: "4px",
    border: "none",
    cursor: "pointer",
    letterSpacing: "0.05em",
  },
  tabRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "var(--space-5)",
    borderBottom: "1px solid var(--border-subtle)",
    paddingBottom: "var(--space-3)",
    flexWrap: "wrap",
    gap: "var(--space-3)",
  },
  tabGroup: {
    display: "flex",
    gap: "var(--space-2)",
  },
  tabBtn: {
    background: "transparent",
    border: "none",
    color: "var(--text-dim)",
    fontSize: "12px",
    fontWeight: 700,
    padding: "6px 14px",
    cursor: "pointer",
    borderRadius: "4px",
  },
  tabBtnActive: {
    backgroundColor: "var(--bg-surface)",
    color: "var(--text-primary)",
    border: "1px solid var(--border-subtle)",
  },
  legendWrap: {
    display: "flex",
    gap: "var(--space-4)",
    fontSize: "11px",
    color: "var(--text-dim)",
  },
  legendItem: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
  },
  dot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
  },
  emptyBox: {
    padding: "var(--space-12) var(--space-6)",
    textAlign: "center",
    backgroundColor: "var(--bg-raised)",
    border: "1px dashed var(--border-subtle)",
    borderRadius: "8px",
    margin: "var(--space-8) 0",
  },
  emptyTitle: {
    fontSize: "16px",
    fontWeight: 800,
    color: "var(--text-secondary)",
    marginBottom: "var(--space-2)",
  },
  emptyText: {
    fontSize: "13px",
    color: "var(--text-muted)",
    maxWidth: "500px",
    margin: "0 auto var(--space-4)",
    lineHeight: 1.5,
  },
  emptyBtn: {
    backgroundColor: "var(--accent-amber)",
    color: "#000000",
    fontWeight: 700,
    fontSize: "12px",
    padding: "8px 20px",
    borderRadius: "4px",
    border: "none",
    cursor: "pointer",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))",
    gap: "var(--space-4)",
  },
  jobCard: {
    backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "8px",
    padding: "var(--space-4)",
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
  },
  jobTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: "var(--space-3)",
  },
  jobBadgeRow: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-2)",
    marginBottom: "6px",
    flexWrap: "wrap",
  },
  statusBadge: {
    fontSize: "10px",
    fontWeight: 800,
    padding: "2px 8px",
    borderRadius: "3px",
  },
  intervalBadge: {
    fontSize: "10px",
    fontWeight: 600,
    backgroundColor: "var(--bg-surface)",
    color: "var(--text-secondary)",
    padding: "2px 8px",
    borderRadius: "3px",
    border: "1px solid var(--border-subtle)",
  },
  sourceBadge: {
    fontSize: "9px",
    color: "var(--text-dim)",
  },
  playerName: {
    fontSize: "18px",
    fontWeight: 800,
    color: "var(--text-primary)",
    margin: 0,
  },
  jobActionButtons: {
    display: "flex",
    gap: "6px",
  },
  pollBtn: {
    background: "transparent",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-secondary)",
    fontSize: "10px",
    fontWeight: 700,
    padding: "4px 8px",
    borderRadius: "3px",
    cursor: "pointer",
  },
  cancelBtn: {
    background: "transparent",
    border: "1px solid rgba(239, 68, 68, 0.4)",
    color: "#ef4444",
    fontSize: "10px",
    fontWeight: 700,
    padding: "4px 8px",
    borderRadius: "3px",
    cursor: "pointer",
  },
  jobBody: {
    marginBottom: "var(--space-3)",
  },
  reasonText: {
    fontSize: "12px",
    color: "var(--text-secondary)",
    margin: "0 0 var(--space-2) 0",
    lineHeight: 1.4,
  },
  reasonLabel: {
    fontSize: "10px",
    color: "var(--accent-amber)",
    marginRight: "4px",
  },
  tagWrap: {
    display: "flex",
    gap: "6px",
    flexWrap: "wrap",
    marginBottom: "var(--space-2)",
  },
  focusTag: {
    fontSize: "10px",
    backgroundColor: "var(--bg-surface)",
    color: "var(--text-dim)",
    padding: "2px 6px",
    borderRadius: "3px",
  },
  querySnippet: {
    fontSize: "11px",
    color: "var(--text-muted)",
    backgroundColor: "var(--bg-base)",
    padding: "4px 8px",
    borderRadius: "3px",
    marginTop: "6px",
  },
  jobFooter: {
    display: "flex",
    justifyContent: "space-between",
    borderTop: "1px solid var(--border-subtle)",
    paddingTop: "var(--space-3)",
    fontSize: "11px",
    backgroundColor: "var(--bg-base)",
    padding: "var(--space-2) var(--space-3)",
    borderRadius: "4px",
  },
  telemetryItem: {
    display: "flex",
    flexDirection: "column",
  },
  telemetryLabel: {
    fontSize: "9px",
    color: "var(--text-dim)",
  },
  telemetryVal: {
    color: "var(--text-secondary)",
    fontWeight: 600,
  },
  historyDrawer: {
    marginTop: "var(--space-3)",
    borderTop: "1px dashed var(--border-subtle)",
    paddingTop: "var(--space-2)",
  },
  historyTitle: {
    fontSize: "9px",
    color: "var(--accent-amber)",
    marginBottom: "4px",
    letterSpacing: "0.05em",
  },
  historyRow: {
    display: "flex",
    gap: "6px",
    fontSize: "10px",
    color: "var(--text-dim)",
    marginBottom: "2px",
  },
  historyTime: {
    color: "var(--text-muted)",
  },
  historyEvent: {
    color: "#f59e0b",
  },
  historyReason: {
    color: "var(--text-secondary)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  modalOverlay: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(0, 0, 0, 0.75)",
    backdropFilter: "blur(4px)",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    zIndex: 1000,
    padding: "var(--space-4)",
  },
  modalBox: {
    backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "8px",
    width: "100%",
    maxWidth: "540px",
    padding: "var(--space-6)",
    boxShadow: "0 20px 40px rgba(0, 0, 0, 0.5)",
  },
  modalHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "var(--space-4)",
    borderBottom: "1px solid var(--border-subtle)",
    paddingBottom: "var(--space-3)",
  },
  modalTitle: {
    fontSize: "14px",
    fontWeight: 800,
    color: "var(--accent-amber)",
    margin: 0,
  },
  modalCloseBtn: {
    background: "transparent",
    border: "none",
    color: "var(--text-dim)",
    fontSize: "16px",
    cursor: "pointer",
  },
  modalForm: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-4)",
  },
  formGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-1)",
    flex: 1,
  },
  formRow: {
    display: "flex",
    gap: "var(--space-3)",
  },
  label: {
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--text-secondary)",
  },
  input: {
    backgroundColor: "var(--bg-surface)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "4px",
    padding: "10px var(--space-3)",
    color: "var(--text-primary)",
    fontSize: "13px",
  },
  select: {
    backgroundColor: "var(--bg-surface)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "4px",
    padding: "10px var(--space-3)",
    color: "var(--text-primary)",
    fontSize: "12px",
  },
  checkboxGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "var(--space-2)",
    backgroundColor: "var(--bg-base)",
    padding: "var(--space-3)",
    borderRadius: "4px",
    border: "1px solid var(--border-subtle)",
  },
  checkboxLabel: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    cursor: "pointer",
  },
  checkboxText: {
    fontSize: "12px",
    color: "var(--text-secondary)",
  },
  modalActions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: "var(--space-3)",
    marginTop: "var(--space-4)",
    borderTop: "1px solid var(--border-subtle)",
    paddingTop: "var(--space-4)",
  },
  modalCancelBtn: {
    background: "transparent",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-dim)",
    fontSize: "12px",
    fontWeight: 700,
    padding: "8px 16px",
    borderRadius: "4px",
    cursor: "pointer",
  },
  modalSubmitBtn: {
    backgroundColor: "var(--accent-amber)",
    color: "#000000",
    border: "none",
    fontSize: "12px",
    fontWeight: 800,
    padding: "8px 20px",
    borderRadius: "4px",
    cursor: "pointer",
  },
};
