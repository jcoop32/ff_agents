"use client";

import React, { useState, useEffect, useCallback } from "react";
import { evaluateWaiverPickup, proposeWaiverAction } from "@/lib/api";
import { WaiverAdviceResponse } from "@/lib/types";

interface WaiverAdviceModalProps {
  isOpen: boolean;
  onClose: () => void;
  playerName: string | null;
  onActionCreated?: () => void;
}

export function WaiverAdviceModal({
  isOpen,
  onClose,
  playerName,
  onActionCreated,
}: WaiverAdviceModalProps) {
  const [data, setData] = useState<WaiverAdviceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposing, setProposing] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const fetchAdvice = useCallback(async (name: string) => {
    setLoading(true);
    setError(null);
    setActionMsg(null);
    try {
      const res = await evaluateWaiverPickup(name);
      setData(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to evaluate waiver pickup";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen && playerName) {
      fetchAdvice(playerName);
    }
  }, [isOpen, playerName, fetchAdvice]);

  if (!isOpen || !playerName) return null;

  const handlePropose = async () => {
    if (!data) return;
    setProposing(true);
    setActionMsg(null);
    try {
      const payload = data.action_payload || {
        action_type: data.zero_cost_ir_stash ? "IR_STASH" : "WAIVER_CLAIM",
        add_player_name: data.target_player.name,
        add_player_id: undefined,
        drop_player_name: data.primary_cut_candidate?.name,
        drop_player_id: data.primary_cut_candidate?.espn_id,
        ir_player_name: data.ir_recommendation?.eligible_player,
        rationale: data.rationale,
      };

      await proposeWaiverAction({
        action_type: payload.action_type,
        add_player_name: payload.add_player_name || data.target_player.name,
        add_player_id: payload.add_player_id,
        drop_player_name: payload.drop_player_name,
        drop_player_id: payload.drop_player_id,
        ir_player_name: payload.ir_player_name,
        rationale: data.rationale,
      });

      setActionMsg("✅ Transaction drafted to Command Center Pending Actions!");
      if (onActionCreated) onActionCreated();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to draft action";
      setActionMsg(`❌ ${msg}`);
    } finally {
      setProposing(false);
    }
  };

  const tp = data?.target_player;
  const cut = data?.primary_cut_candidate;
  const altCut = data?.secondary_cut_candidate;

  const getVerdictStyle = (badge: string) => {
    if (badge === "FREE IR ADD" || badge === "STRONG ADD") return styles.badgeGreen;
    if (badge === "SPECULATIVE STASH") return styles.badgeAmber;
    return styles.badgeRed;
  };

  return (
    <div style={styles.backdrop} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.headerLeft}>
            <div style={styles.tagRow}>
              <span style={styles.stratTag} className="font-mono">⚡ WAIVER & CUT ADVISOR</span>
              <span style={styles.leagueTag} className="font-mono">4-BENCH SLOT & IR OPTIMIZATION</span>
            </div>
            <h2 style={styles.title}>Pickup & Drop Recommendation</h2>
          </div>
          <button type="button" onClick={onClose} style={styles.closeBtn} className="font-mono">
            ✕
          </button>
        </div>

        {actionMsg && (
          <div style={styles.actionNotice} className="font-mono">
            {actionMsg}
          </div>
        )}

        {/* Content */}
        <div style={styles.body}>
          {loading && (
            <div style={styles.loadingBox} className="font-mono">
              Auditing Team Cooper bench and evaluating {playerName}...
            </div>
          )}

          {error && <div style={styles.errorBox}>{error}</div>}

          {data && tp && (
            <>
              {/* Target Player Dossier Bar */}
              <div style={styles.targetBar}>
                <div style={styles.targetInfo}>
                  <div style={styles.nameRow}>
                    <span style={styles.posPill} className="font-mono">{tp.position}</span>
                    <span style={styles.playerName}>{tp.name}</span>
                    <span style={styles.teamPill} className="font-mono">{tp.team}</span>
                  </div>
                  <div style={styles.statsRow} className="font-mono">
                    <span>Projected: <strong>{tp.projected_ppg.toFixed(1)} PPG</strong></span>
                    <span style={{ margin: "0 8px" }}>•</span>
                    <span>ROS Value: <strong>{tp.ros_trade_value} pts</strong></span>
                    <span style={{ margin: "0 8px" }}>•</span>
                    <span>Status: {tp.injury_status}</span>
                  </div>
                </div>

                <div style={styles.verdictCol}>
                  <div style={styles.verdictLabel} className="font-mono">VERDICT</div>
                  <div style={{ ...styles.verdictBadge, ...getVerdictStyle(data.verdict_badge) }} className="font-mono">
                    {data.verdict_badge}
                  </div>
                </div>
              </div>

              {/* Zero-Cost IR Stash Banner (Priority #1) */}
              {data.zero_cost_ir_stash && data.ir_recommendation && (
                <div style={styles.irStashCallout}>
                  <div style={styles.irCalloutHeader}>
                    <span style={styles.irIcon}>🆓</span>
                    <span style={styles.irTitle} className="font-mono">
                      ZERO-COST PICKUP: EMPTY IR SLOT DETECTED
                    </span>
                  </div>
                  <div style={styles.irDesc}>
                    {data.ir_recommendation.instructions}
                  </div>
                  <div style={styles.irStepBox} className="font-mono">
                    Step 1: Move <strong>{data.ir_recommendation.eligible_player}</strong> ({data.ir_recommendation.injury_status}) from Bench ➔ IR Slot<br />
                    Step 2: Add <strong>{tp.name}</strong> to the opened bench slot for <strong>0 drops</strong>!
                  </div>
                </div>
              )}

              {/* Bench Cut Analysis (If drop needed or secondary) */}
              {!data.zero_cost_ir_stash && cut && (
                <div style={styles.cutSection}>
                  <div style={styles.sectionHeader} className="font-mono">
                    <span>RECOMMENDED BENCH CUT CANDIDATE</span>
                    <span style={styles.sectionSub}>Evaluated across Team Cooper&apos;s 4-man bench</span>
                  </div>

                  <div style={styles.cutCard}>
                    <div style={styles.cutCardHeader}>
                      <div>
                        <div style={styles.cutNameRow}>
                          <span style={styles.posPill} className="font-mono">{cut.position}</span>
                          <span style={styles.cutName}>{cut.name}</span>
                          <span style={styles.teamPill} className="font-mono">{cut.team}</span>
                        </div>
                        <div style={styles.cutStats} className="font-mono">
                          <span>{cut.projected_ppg.toFixed(1)} PPG</span>
                          <span style={{ margin: "0 6px" }}>•</span>
                          <span>ROS Value: {cut.ros_trade_value}</span>
                          <span style={{ margin: "0 6px" }}>•</span>
                          <span>Droppability Score: {cut.droppability_score}</span>
                        </div>
                      </div>

                      <div style={styles.deltaBox} className="font-mono">
                        <span style={styles.deltaLabel}>NET UPGRADE DELTA</span>
                        <span style={{ ...styles.deltaVal, color: data.net_weekly_delta >= 0 ? "var(--accent-emerald)" : "#ef4444" }}>
                          {data.net_weekly_delta >= 0 ? `+${data.net_weekly_delta}` : data.net_weekly_delta} PPG
                        </span>
                        <span style={styles.deltaSub}>
                          {data.net_ros_delta >= 0 ? `+${data.net_ros_delta}` : data.net_ros_delta} pts ROS
                        </span>
                      </div>
                    </div>

                    <div style={styles.cutReason} className="font-mono">
                      Why cut: Lowest projected ROS production on active bench with positional redundancy.
                    </div>
                  </div>

                  {altCut && (
                    <div style={styles.altCutBox} className="font-mono">
                      <span>Alternative Cut Option: </span>
                      <strong>{altCut.name}</strong> ({altCut.position}, {altCut.projected_ppg.toFixed(1)} PPG)
                    </div>
                  )}
                </div>
              )}

              {/* Rationale */}
              <div style={styles.rationaleBox}>
                <div style={styles.rationaleTitle} className="font-mono">
                  💡 STRATEGIC RATIONALE
                </div>
                <p style={styles.rationaleText}>{data.rationale}</p>
              </div>

              {/* Action Button */}
              <div style={styles.actionRow}>
                <button
                  type="button"
                  onClick={handlePropose}
                  disabled={proposing}
                  style={styles.actionBtn}
                  className="font-mono"
                >
                  {proposing
                    ? "DRAFTING ACTION..."
                    : data.zero_cost_ir_stash
                    ? "⚡ DRAFT IR STASH & ADD TRANSACTION"
                    : `⚡ DRAFT CLAIM (DROP ${cut?.name || "BENCH"})`}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: "fixed",
    inset: 0,
    backgroundColor: "rgba(0, 0, 0, 0.8)",
    backdropFilter: "blur(6px)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 9999,
    padding: "20px",
  },
  modal: {
    width: "100%",
    maxWidth: "720px",
    maxHeight: "90vh",
    backgroundColor: "var(--bg-card, #121316)",
    border: "1px solid var(--border-subtle, #27272a)",
    borderRadius: "12px",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.7)",
  },
  header: {
    padding: "18px 24px",
    borderBottom: "1px solid var(--border-subtle, #27272a)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    backgroundColor: "var(--bg-raised, #18181b)",
  },
  headerLeft: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  tagRow: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
  },
  stratTag: {
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--accent-amber, #f59e0b)",
    letterSpacing: "0.08em",
  },
  leagueTag: {
    fontSize: "10px",
    color: "var(--text-muted, #a1a1aa)",
  },
  title: {
    fontSize: "20px",
    fontWeight: 700,
    color: "var(--text-primary, #ffffff)",
    margin: 0,
  },
  closeBtn: {
    background: "none",
    border: "none",
    color: "var(--text-muted, #a1a1aa)",
    fontSize: "18px",
    cursor: "pointer",
    padding: "4px 8px",
  },
  actionNotice: {
    margin: "12px 24px 0",
    padding: "10px 14px",
    backgroundColor: "rgba(16, 185, 129, 0.15)",
    border: "1px solid rgba(16, 185, 129, 0.3)",
    borderRadius: "6px",
    fontSize: "12px",
    color: "var(--accent-emerald, #10b981)",
  },
  body: {
    padding: "20px 24px",
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: "18px",
  },
  loadingBox: {
    padding: "30px",
    textAlign: "center",
    color: "var(--text-secondary, #d4d4d8)",
    fontSize: "13px",
  },
  errorBox: {
    padding: "12px",
    backgroundColor: "rgba(239, 68, 68, 0.15)",
    border: "1px solid rgba(239, 68, 68, 0.3)",
    borderRadius: "6px",
    color: "#ef4444",
    fontSize: "13px",
  },
  targetBar: {
    padding: "16px",
    backgroundColor: "var(--bg-raised, #18181b)",
    border: "1px solid var(--border-subtle, #27272a)",
    borderRadius: "8px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  targetInfo: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  nameRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  posPill: {
    padding: "2px 6px",
    fontSize: "11px",
    fontWeight: 700,
    backgroundColor: "var(--bg-base, #09090b)",
    border: "1px solid var(--border-subtle, #27272a)",
    borderRadius: "4px",
    color: "var(--accent-amber, #f59e0b)",
  },
  playerName: {
    fontSize: "18px",
    fontWeight: 700,
    color: "var(--text-primary, #ffffff)",
  },
  teamPill: {
    fontSize: "12px",
    color: "var(--text-muted, #a1a1aa)",
  },
  statsRow: {
    fontSize: "12px",
    color: "var(--text-secondary, #d4d4d8)",
  },
  verdictCol: {
    textAlign: "right",
  },
  verdictLabel: {
    fontSize: "10px",
    color: "var(--text-muted, #a1a1aa)",
    letterSpacing: "0.06em",
    marginBottom: "4px",
  },
  verdictBadge: {
    padding: "6px 14px",
    fontSize: "12px",
    fontWeight: 800,
    borderRadius: "6px",
    letterSpacing: "0.05em",
  },
  badgeGreen: {
    backgroundColor: "rgba(16, 185, 129, 0.2)",
    border: "1px solid rgba(16, 185, 129, 0.4)",
    color: "var(--accent-emerald, #10b981)",
  },
  badgeAmber: {
    backgroundColor: "rgba(245, 158, 11, 0.2)",
    border: "1px solid rgba(245, 158, 11, 0.4)",
    color: "var(--accent-amber, #f59e0b)",
  },
  badgeRed: {
    backgroundColor: "rgba(239, 68, 68, 0.2)",
    border: "1px solid rgba(239, 68, 68, 0.4)",
    color: "#ef4444",
  },
  irStashCallout: {
    padding: "16px",
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    border: "1px solid rgba(16, 185, 129, 0.35)",
    borderRadius: "8px",
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  irCalloutHeader: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  irIcon: {
    fontSize: "18px",
  },
  irTitle: {
    fontSize: "12px",
    fontWeight: 700,
    color: "var(--accent-emerald, #10b981)",
    letterSpacing: "0.05em",
  },
  irDesc: {
    fontSize: "13px",
    color: "var(--text-primary, #ffffff)",
    lineHeight: 1.4,
  },
  irStepBox: {
    padding: "10px 12px",
    backgroundColor: "var(--bg-base, #09090b)",
    border: "1px solid var(--border-subtle, #27272a)",
    borderRadius: "6px",
    fontSize: "11px",
    color: "var(--text-secondary, #d4d4d8)",
    lineHeight: 1.6,
  },
  cutSection: {
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  },
  sectionHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--text-secondary, #d4d4d8)",
  },
  sectionSub: {
    fontSize: "10px",
    color: "var(--text-muted, #a1a1aa)",
    fontWeight: 400,
  },
  cutCard: {
    padding: "14px",
    backgroundColor: "var(--bg-raised, #18181b)",
    border: "1px solid var(--border-subtle, #27272a)",
    borderRadius: "8px",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  },
  cutCardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  cutNameRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    marginBottom: "4px",
  },
  cutName: {
    fontSize: "16px",
    fontWeight: 700,
    color: "var(--text-primary, #ffffff)",
  },
  cutStats: {
    fontSize: "11px",
    color: "var(--text-muted, #a1a1aa)",
  },
  deltaBox: {
    textAlign: "right",
  },
  deltaLabel: {
    fontSize: "10px",
    color: "var(--text-muted, #a1a1aa)",
    letterSpacing: "0.05em",
    display: "block",
  },
  deltaVal: {
    fontSize: "15px",
    fontWeight: 700,
  },
  deltaSub: {
    fontSize: "10px",
    color: "var(--text-muted, #a1a1aa)",
    display: "block",
  },
  cutReason: {
    fontSize: "11px",
    color: "var(--text-secondary, #d4d4d8)",
    backgroundColor: "var(--bg-base, #09090b)",
    padding: "8px 12px",
    borderRadius: "4px",
    border: "1px solid var(--border-subtle, #27272a)",
  },
  altCutBox: {
    fontSize: "11px",
    color: "var(--text-muted, #a1a1aa)",
    padding: "4px 8px",
  },
  rationaleBox: {
    padding: "14px",
    backgroundColor: "var(--bg-base, #09090b)",
    border: "1px solid var(--border-subtle, #27272a)",
    borderRadius: "8px",
  },
  rationaleTitle: {
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--accent-amber, #f59e0b)",
    letterSpacing: "0.06em",
    marginBottom: "6px",
  },
  rationaleText: {
    fontSize: "12px",
    color: "var(--text-secondary, #d4d4d8)",
    lineHeight: 1.5,
    margin: 0,
  },
  actionRow: {
    display: "flex",
    justifyContent: "flex-end",
  },
  actionBtn: {
    padding: "12px 22px",
    fontSize: "12px",
    fontWeight: 700,
    backgroundColor: "var(--accent-emerald, #10b981)",
    border: "none",
    borderRadius: "6px",
    color: "#000000",
    cursor: "pointer",
    transition: "all 0.15s ease",
  },
};
