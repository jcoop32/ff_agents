"use client";

import React, { useState, useEffect, useCallback } from "react";
import { acquireTargetPlayerTrades, getTradePackages, proposeTradeAction } from "@/lib/api";
import { AcquireTradeResponse, TradePackage } from "@/lib/types";

interface TradePackageModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTargetPlayer?: string | null;
  shopPlayerName?: string | null;
  onActionCreated?: () => void;
}

export function TradePackageModal({
  isOpen,
  onClose,
  initialTargetPlayer = null,
  shopPlayerName = null,
  onActionCreated,
}: TradePackageModalProps) {
  const [mode, setMode] = useState<"TARGET" | "SHOP">(shopPlayerName ? "SHOP" : "TARGET");
  const [searchQuery, setSearchQuery] = useState(initialTargetPlayer || shopPlayerName || "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acquireData, setAcquireData] = useState<AcquireTradeResponse | null>(null);
  const [shopPackages, setShopPackages] = useState<TradePackage[]>([]);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [proposingIndex, setProposingIndex] = useState<number | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const handleSearch = useCallback(async (queryToSearch?: string) => {
    const q = (queryToSearch !== undefined ? queryToSearch : searchQuery).trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setActionMsg(null);
    setCopiedIndex(null);

    try {
      if (mode === "TARGET") {
        const res = await acquireTargetPlayerTrades(q);
        setAcquireData(res);
        setShopPackages([]);
      } else {
        const res = await getTradePackages(q);
        setShopPackages(res.packages || []);
        setAcquireData(null);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to find trade packages";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [mode, searchQuery]);

  useEffect(() => {
    if (isOpen) {
      if (shopPlayerName) {
        setMode("SHOP");
        setSearchQuery(shopPlayerName);
        handleSearch(shopPlayerName);
      } else if (initialTargetPlayer) {
        setMode("TARGET");
        setSearchQuery(initialTargetPlayer);
        handleSearch(initialTargetPlayer);
      } else if (searchQuery) {
        handleSearch();
      }
    }
  }, [isOpen, initialTargetPlayer, shopPlayerName]);

  if (!isOpen) return null;

  const handleCopyPitch = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2500);
  };

  const handleProposeTrade = async (pkg: TradePackage, index: number) => {
    setProposingIndex(index);
    setActionMsg(null);
    try {
      const targetTeamId = pkg.target_team_id || acquireData?.target_owner?.espn_team_id || 1;
      const targetTeamName = pkg.target_team_name || acquireData?.target_owner?.team_name || "Rival Team";
      
      await proposeTradeAction({
        target_team_id: targetTeamId,
        target_team_name: targetTeamName,
        send_players: pkg.players_sent,
        receive_players: pkg.players_received,
        rationale: pkg.rationale,
        pitch: pkg.negotiation_pitch || pkg.pitch,
      });

      setActionMsg("✅ Trade proposal successfully drafted to Command Center Pending Actions!");
      if (onActionCreated) onActionCreated();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to draft trade action";
      setActionMsg(`❌ ${msg}`);
    } finally {
      setProposingIndex(null);
    }
  };

  const p = acquireData?.target_player;
  const owner = acquireData?.target_owner;
  const packages = mode === "TARGET" ? (acquireData?.packages || []) : shopPackages;

  return (
    <div style={styles.backdrop} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.headerLeft}>
            <div style={styles.badgeRow}>
              <span style={styles.iconTag} className="font-mono">🤝 TRADE STRATEGIST</span>
              <span style={styles.subTag} className="font-mono">10-TEAM PPR | 4-BENCH LEAGUE</span>
            </div>
            <h2 style={styles.title}>
              {mode === "TARGET" ? "Target Player & Star Hunting" : "Shop Roster Surplus"}
            </h2>
          </div>
          <button type="button" onClick={onClose} style={styles.closeBtn} className="font-mono">
            ✕
          </button>
        </div>

        {/* Mode Switcher & Search Bar */}
        <div style={styles.controlsBar}>
          <div style={styles.modeTabs} className="font-mono">
            <button
              type="button"
              onClick={() => {
                setMode("TARGET");
                setAcquireData(null);
              }}
              style={{
                ...styles.modeTab,
                ...(mode === "TARGET" ? styles.modeTabActive : {}),
              }}
            >
              🎯 ACQUIRE TARGET (BUY)
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("SHOP");
                setShopPackages([]);
              }}
              style={{
                ...styles.modeTab,
                ...(mode === "SHOP" ? styles.modeTabActive : {}),
              }}
            >
              📤 SHOP MY PLAYER (SELL)
            </button>
          </div>

          <div style={styles.searchRow}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder={
                mode === "TARGET"
                  ? "Enter target player to acquire (e.g. Carnell Tate, Justin Jefferson)..."
                  : "Enter your player to shop across league (e.g. Kenneth Walker)..."
              }
              style={styles.searchInput}
              className="font-mono"
            />
            <button
              type="button"
              onClick={() => handleSearch()}
              disabled={loading || !searchQuery.trim()}
              style={{
                ...styles.searchBtn,
                opacity: loading || !searchQuery.trim() ? 0.6 : 1,
              }}
              className="font-mono"
            >
              {loading ? "ANALYZING..." : "FIND TRADES"}
            </button>
          </div>
        </div>

        {actionMsg && (
          <div style={styles.actionNotice} className="font-mono">
            {actionMsg}
          </div>
        )}

        {/* Body Content */}
        <div style={styles.body}>
          {error && <div style={styles.errorBox}>{error}</div>}

          {/* Target Mode: Player & Owner Diagnosis Card */}
          {mode === "TARGET" && acquireData && (
            <div style={styles.diagnosisSection}>
              {acquireData.status === "FREE_AGENT" ? (
                <div style={styles.freeAgentBanner}>
                  <div style={styles.freeAgentTitle}>⚡ Free Agent / Waiver Wire Notice</div>
                  <div>{acquireData.message}</div>
                </div>
              ) : acquireData.status === "ALREADY_OWNED" ? (
                <div style={styles.alreadyOwnedBanner}>
                  <div>{acquireData.message}</div>
                </div>
              ) : p && owner ? (
                <div style={styles.targetDossierCard}>
                  <div style={styles.targetHeader}>
                    <div>
                      <div style={styles.targetNameRow}>
                        <span style={styles.posPill} className="font-mono">{p.position}</span>
                        <span style={styles.targetName}>{p.name}</span>
                        <span style={styles.teamPill} className="font-mono">{p.team}</span>
                        {p.is_star && (
                          <span style={styles.starBadge} className="font-mono">⭐ ELITE STUD</span>
                        )}
                      </div>
                      <div style={styles.targetStats} className="font-mono">
                        <span>Projected: <strong>{p.projected_ppg.toFixed(1)} PPG</strong></span>
                        <span style={{ margin: "0 8px" }}>•</span>
                        <span>ROS Value: <strong>{p.ros_trade_value} pts</strong></span>
                      </div>
                    </div>

                    <div style={styles.ownerBox}>
                      <div style={styles.ownerLabel} className="font-mono">CURRENT OWNER</div>
                      <div style={styles.ownerTeam}>{owner.team_name}</div>
                      <div style={styles.ownerName} className="font-mono">{owner.owner_name}</div>
                    </div>
                  </div>

                  {/* Opponent Weak Spot Analysis */}
                  <div style={styles.weaknessBanner}>
                    <span style={styles.weaknessIcon}>🔴</span>
                    <div>
                      <span style={styles.weaknessTitle} className="font-mono">
                        OPPONENT WEAK SPOT DETECTED: {owner.weakest_position}
                      </span>
                      <p style={styles.weaknessDesc}>
                        {owner.team_name}&apos;s weakest starter is <strong>{owner.weakest_starter?.name}</strong> averaging only{" "}
                        <strong>{owner.weak_starter_ppg} PPG</strong>. They desperately need an upgrade at {owner.weakest_position},
                        giving Team Cooper prime leverage.
                      </p>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          )}

          {/* Packages List */}
          <div style={styles.packagesHeader} className="font-mono">
            <span>PROPOSED TRADE PACKAGES ({packages.length})</span>
            <span style={styles.packagesSub}>
              {mode === "TARGET"
                ? "Asymmetrical Win-Win: Solves rival's hole while securing star asset for Cooper"
                : "Matched against rival starting deficits"}
            </span>
          </div>

          {packages.length === 0 && !loading && (
            <div style={styles.emptyState}>
              <div style={styles.emptyIcon}>🔍</div>
              <div style={styles.emptyTitle}>No trade packages found yet</div>
              <div style={styles.emptySub}>
                Type a player name above to discover win-win packages tailored to rival roster weaknesses.
              </div>
            </div>
          )}

          <div style={styles.packagesList}>
            {packages.map((pkg, idx) => (
              <div key={idx} style={styles.packageCard}>
                <div style={styles.packageCardTop}>
                  <div style={styles.packageTypeBadge} className="font-mono">
                    {pkg.package_type === "2_FOR_1_CONSOLIDATION"
                      ? "⭐ 2-FOR-1 STAR CONSOLIDATION"
                      : "🔄 1-FOR-1 NEED SWAP"}
                  </div>
                  <div style={styles.packageVerdict} className="font-mono">
                    VERDICT: <span style={{ color: "var(--accent-emerald)" }}>{pkg.verdict}</span>
                  </div>
                </div>

                <div style={styles.packageTitle}>{pkg.title}</div>

                {/* Trade Flow Grid */}
                <div style={styles.tradeFlowGrid}>
                  {/* Cooper Sends */}
                  <div style={styles.tradeSideBox}>
                    <div style={styles.sideLabel} className="font-mono">TEAM COOPER GIVES UP</div>
                    <div style={styles.playerList}>
                      {pkg.players_sent.map((name, i) => (
                        <div key={i} style={styles.playerItem}>
                          <span style={styles.sendBullet}>▲</span>
                          <span style={styles.playerItemName}>{name}</span>
                        </div>
                      ))}
                    </div>
                    {pkg.package_type === "2_FOR_1_CONSOLIDATION" && (
                      <div style={styles.qualityNotice} className="font-mono">
                        Solid starter talent offered to make star deal realistic
                      </div>
                    )}
                  </div>

                  {/* Arrow */}
                  <div style={styles.flowArrow}>⇄</div>

                  {/* Cooper Receives */}
                  <div style={{ ...styles.tradeSideBox, borderColor: "rgba(16, 185, 129, 0.4)" }}>
                    <div style={{ ...styles.sideLabel, color: "var(--accent-emerald)" }} className="font-mono">
                      TEAM COOPER ACQUIRES
                    </div>
                    <div style={styles.playerList}>
                      {pkg.players_received.map((name, i) => (
                        <div key={i} style={styles.playerItem}>
                          <span style={{ ...styles.sendBullet, color: "var(--accent-emerald)" }}>★</span>
                          <span style={{ ...styles.playerItemName, fontWeight: 700, color: "var(--accent-emerald)" }}>
                            {name}
                          </span>
                        </div>
                      ))}
                    </div>
                    {pkg.package_type === "2_FOR_1_CONSOLIDATION" && (
                      <div style={styles.bonusTag} className="font-mono">
                        +8% Consolidation Win & +1 Bench Slot Freed
                      </div>
                    )}
                  </div>
                </div>

                {/* Win-Win Metrics Bar */}
                <div style={styles.metricsBar} className="font-mono">
                  <div style={styles.metricItem}>
                    <span style={styles.metricLabel}>OPPONENT STARTING GAIN</span>
                    <span style={{ ...styles.metricVal, color: "var(--accent-amber)" }}>
                      +{pkg.opponent_weekly_delta.toFixed(1)} PPG
                    </span>
                  </div>
                  <div style={styles.metricItem}>
                    <span style={styles.metricLabel}>COOPER NET ROS EQUITY</span>
                    <span style={{ ...styles.metricVal, color: "var(--accent-emerald)" }}>
                      {pkg.net_trade_equity > 0 ? `+${pkg.net_trade_equity}` : pkg.net_trade_equity} pts
                    </span>
                  </div>
                  <div style={styles.metricItem}>
                    <span style={styles.metricLabel}>TARGET PARTNER</span>
                    <span style={styles.metricVal}>{pkg.target_team_name}</span>
                  </div>
                </div>

                <p style={styles.rationaleText}>{pkg.rationale}</p>

                {/* Negotiation Pitch */}
                {(pkg.negotiation_pitch || pkg.pitch) && (
                  <div style={styles.pitchBox}>
                    <div style={styles.pitchHeader}>
                      <span style={styles.pitchLabel} className="font-mono">
                        💬 READY-TO-SEND NEGOTIATION PITCH
                      </span>
                      <button
                        type="button"
                        onClick={() => handleCopyPitch(pkg.negotiation_pitch || pkg.pitch || "", idx)}
                        style={styles.copyBtn}
                        className="font-mono"
                      >
                        {copiedIndex === idx ? "COPIED! ✓" : "📋 COPY PITCH"}
                      </button>
                    </div>
                    <div style={styles.pitchText}>
                      &quot;{pkg.negotiation_pitch || pkg.pitch}&quot;
                    </div>
                  </div>
                )}

                {/* Card Action */}
                <div style={styles.cardFooter}>
                  <button
                    type="button"
                    onClick={() => handleProposeTrade(pkg, idx)}
                    disabled={proposingIndex === idx}
                    style={styles.proposeBtn}
                    className="font-mono"
                  >
                    {proposingIndex === idx ? "DRAFTING ACTION..." : "⚡ DRAFT APPROVAL-GATED PROPOSAL"}
                  </button>
                </div>
              </div>
            ))}
          </div>
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
    maxWidth: "920px",
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
  badgeRow: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
  },
  iconTag: {
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--accent-amber, #f59e0b)",
    letterSpacing: "0.08em",
  },
  subTag: {
    fontSize: "10px",
    color: "var(--text-muted, #a1a1aa)",
    letterSpacing: "0.05em",
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
  controlsBar: {
    padding: "16px 24px",
    borderBottom: "1px solid var(--border-subtle, #27272a)",
    backgroundColor: "var(--bg-base, #09090b)",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
  modeTabs: {
    display: "flex",
    gap: "8px",
  },
  modeTab: {
    padding: "6px 14px",
    fontSize: "11px",
    fontWeight: 600,
    backgroundColor: "transparent",
    border: "1px solid var(--border-subtle, #27272a)",
    borderRadius: "6px",
    color: "var(--text-secondary, #d4d4d8)",
    cursor: "pointer",
    transition: "all 0.15s ease",
  },
  modeTabActive: {
    backgroundColor: "var(--accent-amber, #f59e0b)",
    borderColor: "var(--accent-amber, #f59e0b)",
    color: "#000000",
    fontWeight: 700,
  },
  searchRow: {
    display: "flex",
    gap: "10px",
  },
  searchInput: {
    flex: 1,
    padding: "10px 14px",
    fontSize: "13px",
    backgroundColor: "var(--bg-raised, #18181b)",
    border: "1px solid var(--border-subtle, #27272a)",
    borderRadius: "6px",
    color: "var(--text-primary, #ffffff)",
    outline: "none",
  },
  searchBtn: {
    padding: "10px 20px",
    fontSize: "12px",
    fontWeight: 700,
    backgroundColor: "var(--accent-amber, #f59e0b)",
    border: "none",
    borderRadius: "6px",
    color: "#000000",
    cursor: "pointer",
    whiteSpace: "nowrap",
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
  errorBox: {
    padding: "12px",
    backgroundColor: "rgba(239, 68, 68, 0.15)",
    border: "1px solid rgba(239, 68, 68, 0.3)",
    borderRadius: "6px",
    color: "#ef4444",
    fontSize: "13px",
  },
  diagnosisSection: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
  freeAgentBanner: {
    padding: "14px",
    backgroundColor: "rgba(59, 130, 246, 0.15)",
    border: "1px solid rgba(59, 130, 246, 0.3)",
    borderRadius: "8px",
    color: "#60a5fa",
    fontSize: "13px",
  },
  freeAgentTitle: {
    fontWeight: 700,
    marginBottom: "4px",
  },
  alreadyOwnedBanner: {
    padding: "14px",
    backgroundColor: "rgba(16, 185, 129, 0.15)",
    border: "1px solid rgba(16, 185, 129, 0.3)",
    borderRadius: "8px",
    color: "#34d399",
    fontSize: "13px",
  },
  targetDossierCard: {
    padding: "16px",
    backgroundColor: "var(--bg-raised, #18181b)",
    border: "1px solid var(--border-subtle, #27272a)",
    borderRadius: "8px",
    display: "flex",
    flexDirection: "column",
    gap: "14px",
  },
  targetHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  targetNameRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    marginBottom: "4px",
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
  targetName: {
    fontSize: "18px",
    fontWeight: 700,
    color: "var(--text-primary, #ffffff)",
  },
  teamPill: {
    fontSize: "12px",
    color: "var(--text-muted, #a1a1aa)",
  },
  starBadge: {
    padding: "2px 8px",
    fontSize: "10px",
    fontWeight: 700,
    backgroundColor: "rgba(245, 158, 11, 0.2)",
    border: "1px solid rgba(245, 158, 11, 0.4)",
    borderRadius: "4px",
    color: "var(--accent-amber, #f59e0b)",
  },
  targetStats: {
    fontSize: "12px",
    color: "var(--text-secondary, #d4d4d8)",
  },
  ownerBox: {
    textAlign: "right",
  },
  ownerLabel: {
    fontSize: "10px",
    color: "var(--text-muted, #a1a1aa)",
    letterSpacing: "0.06em",
  },
  ownerTeam: {
    fontSize: "14px",
    fontWeight: 700,
    color: "var(--text-primary, #ffffff)",
  },
  ownerName: {
    fontSize: "12px",
    color: "var(--text-secondary, #d4d4d8)",
  },
  weaknessBanner: {
    padding: "12px 14px",
    backgroundColor: "rgba(239, 68, 68, 0.1)",
    border: "1px solid rgba(239, 68, 68, 0.25)",
    borderRadius: "6px",
    display: "flex",
    gap: "12px",
    alignItems: "flex-start",
  },
  weaknessIcon: {
    fontSize: "16px",
  },
  weaknessTitle: {
    fontSize: "11px",
    fontWeight: 700,
    color: "#f87171",
    letterSpacing: "0.05em",
    display: "block",
    marginBottom: "4px",
  },
  weaknessDesc: {
    fontSize: "12px",
    color: "var(--text-secondary, #d4d4d8)",
    margin: 0,
    lineHeight: 1.4,
  },
  packagesHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--text-secondary, #d4d4d8)",
    letterSpacing: "0.06em",
    marginTop: "8px",
  },
  packagesSub: {
    fontSize: "11px",
    color: "var(--text-muted, #a1a1aa)",
    fontWeight: 400,
  },
  emptyState: {
    padding: "40px 20px",
    textAlign: "center",
    backgroundColor: "var(--bg-raised, #18181b)",
    borderRadius: "8px",
    border: "1px dashed var(--border-subtle, #27272a)",
  },
  emptyIcon: {
    fontSize: "28px",
    marginBottom: "8px",
  },
  emptyTitle: {
    fontSize: "15px",
    fontWeight: 600,
    color: "var(--text-primary, #ffffff)",
    marginBottom: "4px",
  },
  emptySub: {
    fontSize: "12px",
    color: "var(--text-muted, #a1a1aa)",
    maxWidth: "400px",
    margin: "0 auto",
  },
  packagesList: {
    display: "flex",
    flexDirection: "column",
    gap: "16px",
  },
  packageCard: {
    padding: "16px",
    backgroundColor: "var(--bg-raised, #18181b)",
    border: "1px solid var(--border-subtle, #27272a)",
    borderRadius: "8px",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
  packageCardTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  packageTypeBadge: {
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--accent-amber, #f59e0b)",
    letterSpacing: "0.05em",
  },
  packageVerdict: {
    fontSize: "11px",
    color: "var(--text-muted, #a1a1aa)",
    fontWeight: 700,
  },
  packageTitle: {
    fontSize: "15px",
    fontWeight: 700,
    color: "var(--text-primary, #ffffff)",
  },
  tradeFlowGrid: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    backgroundColor: "var(--bg-base, #09090b)",
    padding: "12px",
    borderRadius: "6px",
    border: "1px solid var(--border-subtle, #27272a)",
  },
  tradeSideBox: {
    flex: 1,
    padding: "10px",
    backgroundColor: "var(--bg-raised, #18181b)",
    border: "1px solid var(--border-subtle, #27272a)",
    borderRadius: "6px",
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  sideLabel: {
    fontSize: "10px",
    fontWeight: 700,
    color: "var(--accent-amber, #f59e0b)",
    letterSpacing: "0.05em",
  },
  playerList: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  playerItem: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    fontSize: "13px",
  },
  sendBullet: {
    fontSize: "10px",
    color: "var(--accent-amber, #f59e0b)",
  },
  playerItemName: {
    color: "var(--text-primary, #ffffff)",
  },
  qualityNotice: {
    fontSize: "10px",
    color: "var(--text-muted, #a1a1aa)",
    marginTop: "4px",
  },
  flowArrow: {
    fontSize: "18px",
    color: "var(--text-muted, #a1a1aa)",
  },
  bonusTag: {
    fontSize: "10px",
    color: "var(--accent-emerald, #10b981)",
    fontWeight: 600,
    marginTop: "4px",
  },
  metricsBar: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: "10px",
    padding: "10px 14px",
    backgroundColor: "rgba(0,0,0,0.3)",
    borderRadius: "6px",
    border: "1px solid var(--border-subtle, #27272a)",
  },
  metricItem: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
  },
  metricLabel: {
    fontSize: "10px",
    color: "var(--text-muted, #a1a1aa)",
    letterSpacing: "0.05em",
  },
  metricVal: {
    fontSize: "13px",
    fontWeight: 700,
    color: "var(--text-primary, #ffffff)",
  },
  rationaleText: {
    fontSize: "12px",
    color: "var(--text-secondary, #d4d4d8)",
    margin: 0,
    lineHeight: 1.5,
  },
  pitchBox: {
    padding: "12px",
    backgroundColor: "rgba(245, 158, 11, 0.08)",
    border: "1px solid rgba(245, 158, 11, 0.2)",
    borderRadius: "6px",
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  pitchHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  pitchLabel: {
    fontSize: "10px",
    fontWeight: 700,
    color: "var(--accent-amber, #f59e0b)",
    letterSpacing: "0.06em",
  },
  copyBtn: {
    padding: "4px 10px",
    fontSize: "10px",
    fontWeight: 700,
    backgroundColor: "transparent",
    border: "1px solid var(--accent-amber, #f59e0b)",
    borderRadius: "4px",
    color: "var(--accent-amber, #f59e0b)",
    cursor: "pointer",
  },
  pitchText: {
    fontSize: "12px",
    fontStyle: "italic",
    color: "var(--text-primary, #ffffff)",
    lineHeight: 1.4,
  },
  cardFooter: {
    display: "flex",
    justifyContent: "flex-end",
  },
  proposeBtn: {
    padding: "10px 18px",
    fontSize: "11px",
    fontWeight: 700,
    backgroundColor: "transparent",
    border: "1px solid var(--accent-emerald, #10b981)",
    borderRadius: "6px",
    color: "var(--accent-emerald, #10b981)",
    cursor: "pointer",
    transition: "all 0.15s ease",
  },
};
