"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { getPlayerScouting } from "@/lib/api";
import { PlayerScoutingDossier } from "@/lib/types";

interface PlayerScoutingModalProps {
  playerId: string | null;
  onClose: () => void;
}

export function PlayerScoutingModal({ playerId, onClose }: PlayerScoutingModalProps) {
  const router = useRouter();
  const [dossier, setDossier] = useState<PlayerScoutingDossier | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeSubTab, setActiveSubTab] = useState<"OVERVIEW" | "SOURCES">("OVERVIEW");

  useEffect(() => {
    if (!playerId) return;
    setLoading(true);
    getPlayerScouting(playerId)
      .then((data) => setDossier(data))
      .catch((err) => {
        console.error("Failed to load scouting dossier:", err);
      })
      .finally(() => setLoading(false));
  }, [playerId]);

  if (!playerId) return null;

  const handleAskGM = () => {
    if (!dossier) return;
    const p = dossier.player;
    const c = dossier.consensus;
    const query = `Analyze ${p.name} (${p.position}, ${p.nfl_team}) for draft selection. Consensus projection is ${c.points} pts (${c.avg}/gm) [Floor: ${c.floor}, Ceiling: ${c.ceiling}]. How does their risk/reward profile fit my roster needs?`;
    router.push(`/?prompt=${encodeURIComponent(query)}`);
  };

  const p = dossier?.player;
  const c = dossier?.consensus;
  const s = dossier?.sources;
  const v = dossier?.variance;

  const getSentimentStyle = (tag: string) => {
    if (tag === "BULLISH") return styles.sentimentBullish;
    if (tag === "BEARISH") return styles.sentimentBearish;
    return styles.sentimentNeutral;
  };

  return (
    <div style={styles.backdrop} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div style={styles.header}>
          <div style={styles.headerLeft}>
            <div style={styles.titleRow}>
              {p && (
                <span style={styles.posBadge} className="font-mono">
                  {p.position}
                </span>
              )}
              <h2 style={styles.playerName}>{p?.name || "Player Dossier"}</h2>
              {p?.nfl_team && (
                <span style={styles.teamTag} className="font-mono">
                  {p.nfl_team}
                </span>
              )}
            </div>
            <div style={styles.subTitle} className="font-mono">
              Status: {p?.injury_status || "Healthy"} | Bye: Wk {p?.bye_week || "-"}
              {p?.sentiment_tag && (
                <span style={{ ...styles.sentimentBadge, ...getSentimentStyle(p.sentiment_tag) }}>
                  {p.sentiment_tag}
                </span>
              )}
            </div>
          </div>

          <div style={styles.headerRight}>
            {c && (
              <div style={styles.ptsBox} className="font-mono">
                <span style={styles.ptsVal}>{c.points.toFixed(1)}</span>
                <span style={styles.ptsLabel}>CONSENSUS PTS</span>
                <span style={styles.ptsSub}>{c.avg.toFixed(1)} / GM</span>
              </div>
            )}
            <button type="button" onClick={onClose} style={styles.closeBtn} className="font-mono">
              ✕
            </button>
          </div>
        </div>

        {/* Sub-tabs */}
        <div style={styles.tabBar} className="font-mono">
          <button
            type="button"
            onClick={() => setActiveSubTab("OVERVIEW")}
            style={{
              ...styles.tabBtn,
              ...(activeSubTab === "OVERVIEW" ? styles.tabBtnActive : {}),
            }}
          >
            CONSENSUS & STAT VOLUME
          </button>
          <button
            type="button"
            onClick={() => setActiveSubTab("SOURCES")}
            style={{
              ...styles.tabBtn,
              ...(activeSubTab === "SOURCES" ? styles.tabBtnActive : {}),
            }}
          >
            SOURCES BREAKDOWN (ESPN / SLEEPER / YAHOO)
          </button>
        </div>

        {/* Modal Body */}
        <div style={styles.body}>
          {loading ? (
            <div style={styles.loadingBox} className="font-mono">
              Querying multi-source projections and beat news...
            </div>
          ) : !dossier ? (
            <div style={styles.loadingBox} className="font-mono">
              Failed to load player dossier.
            </div>
          ) : activeSubTab === "OVERVIEW" ? (
            /* Tab 1: Consensus & Volume Stats */
            <div style={styles.overviewGrid}>
              {/* Injury Intelligence Callout */}
              {p?.injury_notes && (
                <div style={styles.injuryAlertCard} className="font-mono">
                  <span style={styles.injuryAlertLabel}>INJURY INTELLIGENCE:</span>
                  <span style={styles.injuryAlertText}>{p.injury_notes}</span>
                </div>
              )}

              {/* Multi-Source ADP Comparison Card */}
              <div style={styles.metricCard}>
                <div style={styles.cardHeader} className="font-mono">
                  MULTI-SOURCE DRAFT POSITION (ADP) CONSENSUS
                </div>
                <div style={styles.rangeRow} className="font-mono">
                  <div style={styles.rangeCol}>
                    <span style={styles.rangeLabel}>SLEEPER ADP</span>
                    <span style={styles.rangeVal}>{s?.sleeper?.adp ? `#${s.sleeper.adp}` : "-"}</span>
                  </div>
                  <div style={styles.rangeDivider} />
                  <div style={styles.rangeCol}>
                    <span style={styles.rangeLabel}>ESPN ADP</span>
                    <span style={styles.rangeVal}>{s?.espn?.adp ? `#${s.espn.adp}` : "-"}</span>
                  </div>
                  <div style={styles.rangeDivider} />
                  <div style={styles.rangeCol}>
                    <span style={styles.rangeLabel}>YAHOO ADP</span>
                    <span style={styles.rangeVal}>{s?.yahoo?.adp ? `#${s.yahoo.adp}` : "-"}</span>
                  </div>
                  <div style={styles.rangeDivider} />
                  <div style={styles.rangeCol}>
                    <span style={styles.rangeLabel}>AVG CONSENSUS</span>
                    <span style={{ ...styles.rangeVal, color: "var(--accent-amber)" }}>
                      {c?.adp ? `#${c.adp}` : "-"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Floor / Ceiling Bar */}
              <div style={styles.metricCard}>
                <div style={styles.cardHeader} className="font-mono">
                  VOLATILITY RANGE & FLOOR/CEILING
                </div>
                <div style={styles.rangeRow} className="font-mono">
                  <div style={styles.rangeCol}>
                    <span style={styles.rangeLabel}>FLOOR</span>
                    <span style={styles.rangeVal}>{c?.floor?.toFixed(1)}</span>
                  </div>
                  <div style={styles.rangeDivider} />
                  <div style={styles.rangeCol}>
                    <span style={styles.rangeLabel}>CONSENSUS</span>
                    <span style={{ ...styles.rangeVal, color: "var(--accent-amber)" }}>
                      {c?.points?.toFixed(1)}
                    </span>
                  </div>
                  <div style={styles.rangeDivider} />
                  <div style={styles.rangeCol}>
                    <span style={styles.rangeLabel}>CEILING</span>
                    <span style={styles.rangeVal}>{c?.ceiling?.toFixed(1)}</span>
                  </div>
                </div>
              </div>

              {/* Volume Projection Breakdown */}
              <div style={styles.metricCard}>
                <div style={styles.cardHeader} className="font-mono">
                  CONSENSUS SEASON STAT PROJECTION
                </div>
                <div style={styles.statGrid} className="font-mono">
                  <div style={styles.statCell}>
                    <span style={styles.statKey}>PASS YDS</span>
                    <span style={styles.statNum}>{c?.pass_yds ?? 0}</span>
                  </div>
                  <div style={styles.statCell}>
                    <span style={styles.statKey}>RUSH YDS</span>
                    <span style={styles.statNum}>{c?.rush_yds ?? 0}</span>
                  </div>
                  <div style={styles.statCell}>
                    <span style={styles.statKey}>REC YDS</span>
                    <span style={styles.statNum}>{c?.rec_yds ?? 0}</span>
                  </div>
                  <div style={styles.statCell}>
                    <span style={styles.statKey}>RECEPTIONS</span>
                    <span style={styles.statNum}>{c?.rec ?? 0}</span>
                  </div>
                </div>
              </div>

              {/* Recent Beat News & Reports */}
              <div style={styles.metricCard}>
                <div style={styles.cardHeader} className="font-mono">
                  RECENT BEAT REPORTING & INJURY NOTES
                </div>
                <div style={styles.newsList}>
                  {dossier.recent_news && dossier.recent_news.length > 0 ? (
                    dossier.recent_news.map((item, idx) => (
                      <div key={idx} style={styles.newsItem}>
                        <div style={styles.newsMeta} className="font-mono">
                          <span style={styles.newsSource}>{item.source}</span>
                          {item.tag && <span style={styles.newsTag}>{item.tag}</span>}
                          {item.timestamp && (
                            <span style={styles.newsTime}>{item.timestamp.slice(0, 10)}</span>
                          )}
                        </div>
                        {item.headline && <strong style={styles.newsHeadline}>{item.headline}</strong>}
                        <p style={styles.newsText}>{item.text}</p>
                      </div>
                    ))
                  ) : (
                    <div style={styles.emptyText} className="font-mono">
                      No recent injury flags or beat updates recorded. Player is practicing fully.
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            /* Tab 2: Sources Comparison (ESPN vs Sleeper vs Yahoo) */
            <div style={styles.sourcesGrid}>
              {/* ESPN Column */}
              <div style={styles.sourceCard}>
                <div style={styles.sourceHeader} className="font-mono">
                  <span>ESPN</span>
                  <span style={styles.sourcePts}>{s?.espn?.points ? `${s.espn.points.toFixed(1)} PTS` : "-"}</span>
                </div>
                <div style={styles.sourceBody} className="font-mono">
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>ESPN ADP</span>
                    <span style={{ ...styles.sourceVal, color: "var(--accent-amber)" }}>
                      {s?.espn?.adp ? `#${s.espn.adp}` : "N/A"}
                    </span>
                  </div>
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>AVG / GM</span>
                    <span style={styles.sourceVal}>{s?.espn?.avg?.toFixed(1) ?? "-"}</span>
                  </div>
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>PASSING</span>
                    <span style={styles.sourceVal}>
                      {Math.round(Number((s?.espn?.stats as Record<string, unknown>)?.passingYards ?? 0))} yds
                    </span>
                  </div>
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>RUSHING</span>
                    <span style={styles.sourceVal}>
                      {Math.round(Number((s?.espn?.stats as Record<string, unknown>)?.rushingYards ?? 0))} yds
                    </span>
                  </div>
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>RECEIVING</span>
                    <span style={styles.sourceVal}>
                      {Math.round(Number((s?.espn?.stats as Record<string, unknown>)?.receivingYards ?? 0))} yds /{" "}
                      {Math.round(Number((s?.espn?.stats as Record<string, unknown>)?.receivingReceptions ?? 0))} rec
                    </span>
                  </div>
                </div>
              </div>

              {/* Sleeper Column */}
              <div style={styles.sourceCard}>
                <div style={styles.sourceHeader} className="font-mono">
                  <span>SLEEPER</span>
                  <span style={styles.sourcePts}>{s?.sleeper?.points ? `${s.sleeper.points.toFixed(1)} PTS` : "-"}</span>
                </div>
                <div style={styles.sourceBody} className="font-mono">
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>SLEEPER ADP</span>
                    <span style={{ ...styles.sourceVal, color: "var(--accent-amber)" }}>
                      {s?.sleeper?.adp ? `#${s.sleeper.adp}` : "N/A"}
                    </span>
                  </div>
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>AVG / GM</span>
                    <span style={styles.sourceVal}>{s?.sleeper?.avg?.toFixed(1) ?? "-"}</span>
                  </div>
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>PASSING</span>
                    <span style={styles.sourceVal}>
                      {String((s?.sleeper?.stats as Record<string, unknown>)?.pass_yd ?? 0)} yds
                    </span>
                  </div>
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>RUSHING</span>
                    <span style={styles.sourceVal}>
                      {String((s?.sleeper?.stats as Record<string, unknown>)?.rush_yd ?? 0)} yds
                    </span>
                  </div>
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>RECEIVING</span>
                    <span style={styles.sourceVal}>
                      {String((s?.sleeper?.stats as Record<string, unknown>)?.rec_yd ?? 0)} yds /{" "}
                      {String((s?.sleeper?.stats as Record<string, unknown>)?.rec ?? 0)} rec
                    </span>
                  </div>
                </div>
              </div>

              {/* Yahoo Column */}
              <div style={styles.sourceCard}>
                <div style={styles.sourceHeader} className="font-mono">
                  <span>YAHOO FANTASY</span>
                  <span style={styles.sourcePts}>DRAFT INTEL</span>
                </div>
                <div style={styles.sourceBody} className="font-mono">
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>YAHOO ADP</span>
                    <span style={{ ...styles.sourceVal, color: "var(--accent-amber)" }}>
                      {s?.yahoo?.adp ? `#${s.yahoo.adp}` : "N/A"}
                    </span>
                  </div>
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>INJURY STATUS</span>
                    <span style={styles.sourceVal}>{s?.yahoo?.status || p?.injury_status || "Healthy"}</span>
                  </div>
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>INJURY NOTE</span>
                    <span style={styles.sourceVal}>{s?.yahoo?.injury_note || "None"}</span>
                  </div>
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>% DRAFTED</span>
                    <span style={styles.sourceVal}>{s?.yahoo?.percent_drafted ? `${Math.round(Number(s.yahoo.percent_drafted) * 100)}%` : "N/A"}</span>
                  </div>
                  <div style={styles.sourceRow}>
                    <span style={styles.sourceKey}>SOURCE TYPE</span>
                    <span style={styles.sourceVal}>Yahoo Live Mock/Draft</span>
                  </div>
                </div>
              </div>

              {/* Model Variance Callout */}
              <div style={styles.varianceCard} className="font-mono">
                <span style={styles.varLabel}>MODEL DIVERGENCE:</span>
                <span style={styles.varVal}>{v?.points_delta?.toFixed(1) ?? 0} PTS SPREAD</span>
                <span style={styles.varRating}>AGREEMENT: {v?.agreement_rating}</span>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer Action */}
        <div style={styles.footer}>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm font-mono">
            CLOSE
          </button>
          {p?.name && (
            <button
              type="button"
              onClick={() => {
                onClose();
                router.push(`/?prompt=${encodeURIComponent(`Evaluate picking up ${p.name} on waivers. Who should I drop or can I move anyone to IR?`)}`);
              }}
              style={styles.waiverActionBtn}
              className="font-mono"
            >
              ⚡ WAIVER PICK/DROP ADVICE
            </button>
          )}
          <button type="button" onClick={handleAskGM} className="btn-primary btn-sm font-mono">
            ASK GM ABOUT {p?.name?.toUpperCase() || "PLAYER"}
          </button>
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: "fixed",
    inset: 0,
    backgroundColor: "rgba(0, 0, 0, 0.75)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
    padding: "var(--space-6)",
  },
  modal: {
    backgroundColor: "var(--bg-surface)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-lg)",
    width: "100%",
    maxWidth: "760px",
    maxHeight: "88vh",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    padding: "var(--space-4) var(--space-6)",
    backgroundColor: "var(--bg-raised)",
    borderBottom: "1px solid var(--border-subtle)",
  },
  headerLeft: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-2)",
  },
  titleRow: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-3)",
  },
  playerName: {
    fontSize: "18px",
    fontWeight: 700,
    color: "var(--text-primary)",
    letterSpacing: "-0.01em",
  },
  posBadge: {
    fontSize: "11px",
    padding: "2px 6px",
    backgroundColor: "var(--bg-base)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-sm)",
    color: "var(--accent-amber)",
    fontWeight: 700,
  },
  teamTag: {
    fontSize: "12px",
    color: "var(--text-muted)",
  },
  subTitle: {
    fontSize: "11px",
    color: "var(--text-dim)",
    display: "flex",
    alignItems: "center",
    gap: "var(--space-3)",
  },
  sentimentBadge: {
    fontSize: "10px",
    padding: "1px 5px",
    borderRadius: "var(--radius-sm)",
    fontWeight: 700,
  },
  sentimentBullish: {
    backgroundColor: "#052e16",
    color: "#4ade80",
    border: "1px solid #15803d",
  },
  sentimentBearish: {
    backgroundColor: "#450a0a",
    color: "#f87171",
    border: "1px solid #b91c1c",
  },
  sentimentNeutral: {
    backgroundColor: "var(--bg-base)",
    color: "var(--text-dim)",
    border: "1px solid var(--border-subtle)",
  },
  headerRight: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-4)",
  },
  ptsBox: {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-end",
  },
  ptsVal: {
    fontSize: "20px",
    fontWeight: 700,
    color: "var(--accent-amber)",
    lineHeight: 1,
  },
  ptsLabel: {
    fontSize: "9px",
    color: "var(--text-dim)",
    letterSpacing: "0.05em",
  },
  ptsSub: {
    fontSize: "11px",
    color: "var(--text-muted)",
  },
  closeBtn: {
    background: "transparent",
    border: "none",
    color: "var(--text-dim)",
    fontSize: "16px",
    cursor: "pointer",
    padding: "4px 8px",
    borderRadius: "var(--radius-sm)",
  },
  tabBar: {
    display: "flex",
    gap: "var(--space-2)",
    padding: "var(--space-2) var(--space-6)",
    backgroundColor: "var(--bg-base)",
    borderBottom: "1px solid var(--border-subtle)",
  },
  tabBtn: {
    background: "transparent",
    borderWidth: "1px",
    borderStyle: "solid",
    borderColor: "transparent",
    color: "var(--text-dim)",
    fontSize: "11px",
    fontWeight: 600,
    padding: "4px 10px",
    cursor: "pointer",
    borderRadius: "var(--radius-sm)",
  },
  tabBtnActive: {
    backgroundColor: "var(--bg-surface)",
    borderColor: "var(--border-subtle)",
    color: "var(--accent-amber)",
  },
  body: {
    padding: "var(--space-6)",
    overflowY: "auto",
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-4)",
  },
  loadingBox: {
    padding: "var(--space-8)",
    textAlign: "center",
    color: "var(--text-dim)",
    fontSize: "12px",
  },
  overviewGrid: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-4)",
  },
  metricCard: {
    backgroundColor: "var(--bg-base)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-md)",
    overflow: "hidden",
  },
  cardHeader: {
    padding: "var(--space-2) var(--space-4)",
    backgroundColor: "var(--bg-raised)",
    borderBottom: "1px solid var(--border-subtle)",
    fontSize: "10px",
    fontWeight: 700,
    color: "var(--text-dim)",
    letterSpacing: "0.05em",
  },
  rangeRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-around",
    padding: "var(--space-4)",
  },
  rangeCol: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "2px",
  },
  rangeLabel: {
    fontSize: "10px",
    color: "var(--text-dim)",
  },
  rangeVal: {
    fontSize: "16px",
    fontWeight: 700,
    color: "var(--text-primary)",
  },
  rangeDivider: {
    width: "1px",
    height: "28px",
    backgroundColor: "var(--border-subtle)",
  },
  statGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, 1fr)",
    padding: "var(--space-3) var(--space-4)",
    gap: "var(--space-3)",
  },
  statCell: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
  },
  statKey: {
    fontSize: "10px",
    color: "var(--text-dim)",
  },
  statNum: {
    fontSize: "14px",
    fontWeight: 600,
    color: "var(--text-primary)",
  },
  newsList: {
    padding: "var(--space-3) var(--space-4)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-3)",
    maxHeight: "220px",
    overflowY: "auto",
  },
  newsItem: {
    paddingBottom: "var(--space-2)",
    borderBottom: "1px solid var(--border-subtle)",
    display: "flex",
    flexDirection: "column",
    gap: "2px",
  },
  newsMeta: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-2)",
    fontSize: "10px",
  },
  newsSource: {
    color: "var(--accent-amber)",
    fontWeight: 600,
  },
  newsTag: {
    color: "var(--text-dim)",
    padding: "0 4px",
    backgroundColor: "var(--bg-surface)",
    borderRadius: "var(--radius-sm)",
  },
  newsTime: {
    color: "var(--text-dim)",
    marginLeft: "auto",
  },
  newsHeadline: {
    fontSize: "12px",
    color: "var(--text-primary)",
  },
  newsText: {
    fontSize: "11px",
    color: "var(--text-muted)",
    lineHeight: 1.4,
  },
  emptyText: {
    color: "var(--text-dim)",
    fontSize: "11px",
    textAlign: "center",
    padding: "var(--space-4)",
  },
  injuryAlertCard: {
    backgroundColor: "rgba(220, 38, 38, 0.08)",
    border: "1px solid rgba(220, 38, 38, 0.3)",
    borderRadius: "var(--radius-md)",
    padding: "var(--space-3) var(--space-4)",
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  injuryAlertLabel: {
    color: "#f87171",
    fontSize: "10px",
    fontWeight: 700,
  },
  injuryAlertText: {
    color: "var(--text-primary)",
    fontSize: "12px",
  },
  sourcesGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
    gap: "var(--space-4)",
  },
  sourceCard: {
    backgroundColor: "var(--bg-base)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-md)",
    overflow: "hidden",
  },
  sourceHeader: {
    padding: "var(--space-3) var(--space-4)",
    backgroundColor: "var(--bg-raised)",
    borderBottom: "1px solid var(--border-subtle)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--text-dim)",
  },
  sourcePts: {
    color: "var(--accent-amber)",
    fontWeight: 700,
  },
  sourceBody: {
    padding: "var(--space-3) var(--space-4)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-2)",
    fontSize: "11px",
  },
  sourceRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    paddingBottom: "4px",
    borderBottom: "1px solid var(--border-subtle)",
  },
  sourceKey: {
    color: "var(--text-dim)",
  },
  sourceVal: {
    color: "var(--text-secondary)",
    fontWeight: 500,
  },
  varianceCard: {
    gridColumn: "1 / -1",
    padding: "var(--space-3) var(--space-4)",
    backgroundColor: "var(--bg-base)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-md)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: "11px",
  },
  varLabel: {
    color: "var(--text-dim)",
  },
  varVal: {
    color: "var(--accent-amber)",
    fontWeight: 700,
  },
  varRating: {
    color: "var(--text-muted)",
  },
  footer: {
    padding: "var(--space-3) var(--space-6)",
    backgroundColor: "var(--bg-raised)",
    borderTop: "1px solid var(--border-subtle)",
    display: "flex",
    justifyContent: "flex-end",
    gap: "var(--space-3)",
  },
  waiverActionBtn: {
    padding: "6px 14px",
    backgroundColor: "rgba(16, 185, 129, 0.15)",
    border: "1px solid var(--accent-emerald, #10b981)",
    color: "var(--accent-emerald, #10b981)",
    borderRadius: "var(--radius-sm)",
    fontSize: "11px",
    fontWeight: 700,
    cursor: "pointer",
  },
};
