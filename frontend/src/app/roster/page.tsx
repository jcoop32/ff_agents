"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { getTeamRoster, getLeagueStandings, triggerESPNSync, comparePlayers, applyRecommendedLineup } from "@/lib/api";
import { TeamRosterResponse, LeagueStandingsResponse, RosterPlayer, PlayerComparisonResponse } from "@/lib/types";
import { TradePackageModal } from "@/components/TradePackageModal";

let memoryRoster: TeamRosterResponse | null = null;
let memoryStandings: LeagueStandingsResponse | null = null;

type LineupViewMode = "current" | "recommended" | "all";

interface SlotDefinition {
  id: string;
  label: string;
  shortLabel: string;
  positions: string[];
}

const SLOTS: SlotDefinition[] = [
  { id: "FLEX", label: "FLEX (RB / WR / TE)", shortLabel: "FLEX", positions: ["RB", "WR", "TE"] },
  { id: "WR", label: "WIDE RECEIVERS (WR1, WR2, WR3)", shortLabel: "WR 1/2/3", positions: ["WR"] },
  { id: "RB", label: "RUNNING BACKS (RB1, RB2)", shortLabel: "RB 1/2", positions: ["RB"] },
  { id: "TE", label: "TIGHT END (TE)", shortLabel: "TE", positions: ["TE"] },
  { id: "QB", label: "QUARTERBACK (QB)", shortLabel: "QB", positions: ["QB"] },
  { id: "K", label: "KICKER (K)", shortLabel: "K", positions: ["K"] },
  { id: "DST", label: "DEFENSE / SPECIAL TEAMS (D/ST)", shortLabel: "D/ST", positions: ["D/ST", "DST"] },
];

export default function RosterAuditPage() {
  const router = useRouter();
  const [roster, setRoster] = useState<TeamRosterResponse | null>(memoryRoster);
  const [standings, setStandings] = useState<LeagueStandingsResponse | null>(memoryStandings);
  const [loading, setLoading] = useState(!memoryRoster);
  const [syncing, setSyncing] = useState(false);
  const [applyingLineup, setApplyingLineup] = useState(false);
  const [showDeepDive, setShowDeepDive] = useState(true);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<LineupViewMode>("current");

  // ── Trade Package Modal state ──
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [selectedTradeTarget, setSelectedTradeTarget] = useState<string | null>(null);
  const [selectedShopPlayer, setSelectedShopPlayer] = useState<string | null>(null);

  // ── Sit / Start Comparison Modal state ──
  const [compareModalOpen, setCompareModalOpen] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState<string>("FLEX");
  const [playerAId, setPlayerAId] = useState<string>("");
  const [playerBId, setPlayerBId] = useState<string>("");
  const [comparisonData, setComparisonData] = useState<PlayerComparisonResponse | null>(null);
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [rData, sData] = await Promise.all([
        getTeamRoster(2).catch(() => null),
        getLeagueStandings().catch(() => null),
      ]);
      if (rData) {
        memoryRoster = rData;
        setRoster(rData);
      }
      if (sData) {
        memoryStandings = sData;
        setStandings(sData);
      }
    } catch (err: unknown) {
      console.error("Roster fetch error:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSync = async () => {
    setSyncing(true);
    setStatusMsg(null);
    try {
      const res = await triggerESPNSync();
      setStatusMsg(`ESPN sync complete: ${res.synced_teams || 12} rosters updated.`);
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Sync error";
      setStatusMsg(`Sync error: ${msg}`);
    } finally {
      setSyncing(false);
    }
  };

  const handleApplyLineup = async () => {
    setApplyingLineup(true);
    setStatusMsg(null);
    try {
      const res = await applyRecommendedLineup(2);
      setStatusMsg(res.message || "Recommended lineup applied successfully!");
      await fetchData();
      setViewMode("current");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to apply lineup";
      setStatusMsg(`Apply error: ${msg}`);
    } finally {
      setApplyingLineup(false);
    }
  };

  const getEligiblePlayers = useCallback(
    (slotId: string) => {
      const slotDef = SLOTS.find((s) => s.id === slotId) || SLOTS[0];
      const all = roster?.players || [];
      return all.filter((p) => slotDef.positions.includes(p.position));
    },
    [roster]
  );

  const runComparison = async (idA: string, idB: string, slotId?: string) => {
    if (!idA || !idB || idA === idB) return;
    setComparing(true);
    setCompareError(null);
    try {
      const targetSlot = slotId || selectedSlot;
      const data = await comparePlayers(idA, idB, targetSlot);
      setComparisonData(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Comparison failed";
      setCompareError(msg);
    } finally {
      setComparing(false);
    }
  };

  const handleSelectSlot = (slotId: string, preferredPlayerAId?: string) => {
    setSelectedSlot(slotId);
    const eligible = getEligiblePlayers(slotId);
    if (eligible.length >= 2) {
      const first =
        preferredPlayerAId && eligible.some((p) => p.id === preferredPlayerAId)
          ? preferredPlayerAId
          : eligible.find((p) => p.is_starter)?.id || eligible[0].id;
      const second =
        eligible.find((p) => p.id !== first && !p.is_starter)?.id ||
        eligible.find((p) => p.id !== first)?.id ||
        "";
      setPlayerAId(first);
      setPlayerBId(second);
      if (first && second) {
        runComparison(first, second, slotId);
      }
    } else if (eligible.length === 1) {
      setPlayerAId(eligible[0].id);
      setPlayerBId("");
      setComparisonData(null);
    } else {
      setPlayerAId("");
      setPlayerBId("");
      setComparisonData(null);
    }
  };

  const openTradeModalForPlayer = (playerName: string) => {
    setSelectedShopPlayer(playerName);
    setSelectedTradeTarget(null);
    setTradeModalOpen(true);
  };

  const openCompareModal = (initialPlayerId?: string, initialSlot?: string, initialPos?: string) => {
    let targetSlot = "FLEX";
    if (initialSlot === "FLEX") {
      targetSlot = "FLEX";
    } else if (initialPos === "WR") {
      targetSlot = initialSlot === "FLEX" ? "FLEX" : "WR";
    } else if (initialPos === "RB") {
      targetSlot = initialSlot === "FLEX" ? "FLEX" : "RB";
    } else if (initialPos === "TE") {
      targetSlot = "TE";
    } else if (initialPos === "QB") {
      targetSlot = "QB";
    } else if (initialPos === "K") {
      targetSlot = "K";
    } else if (initialPos === "D/ST" || initialPos === "DST") {
      targetSlot = "DST";
    }
    handleSelectSlot(targetSlot, initialPlayerId);
    setCompareModalOpen(true);
  };

  const handleSelectPlayerA = (id: string) => {
    setPlayerAId(id);
    if (id && playerBId && id !== playerBId) {
      runComparison(id, playerBId, selectedSlot);
    }
  };

  const handleSelectPlayerB = (id: string) => {
    setPlayerBId(id);
    if (id && playerAId && id !== playerAId) {
      runComparison(playerAId, id, selectedSlot);
    }
  };

  const getStatusDot = (status: string) => {
    const s = (status || "").toLowerCase();
    if (s.includes("out") || s.includes("ir") || s.includes("dnp")) return "critical";
    if (s.includes("questionable") || s.includes("doubtful") || s.includes("limited"))
      return "warning";
    return "healthy";
  };

  // ── Dynamic player categorization for Positional Allocation ──
  const players = roster?.players || [];
  const qbs = players.filter((p) => p.position === "QB");
  const rbs = players.filter((p) => p.position === "RB");
  const wrs = players.filter((p) => p.position === "WR");
  const tes = players.filter((p) => p.position === "TE");
  const ks = players.filter((p) => p.position === "K");
  const dsts = players.filter((p) => p.position === "D/ST" || p.position === "DST");

  const formatPlayerNames = (playerList: RosterPlayer[], max = 4) => {
    if (!playerList || playerList.length === 0) return "None";
    const names = playerList.map((p) => {
      if (p.position === "D/ST" || p.position === "DST") {
        return p.name.replace(" D/ST", "").replace(" DST", "");
      }
      const parts = p.name.trim().split(" ");
      return parts[parts.length - 1]; // Last name
    });
    if (names.length <= max) return names.join(", ");
    return `${names.slice(0, max).join(", ")}...`;
  };

  // ── Lineup views ──
  const currentStarters = roster?.current_starters || players.filter((p) => p.is_starter);
  const currentBench = roster?.current_bench || players.filter((p) => !p.is_starter);
  const optimalStarters = roster?.optimal_starters || [];
  const optimalBench = roster?.optimal_bench || [];
  const delta = roster?.delta_vs_current ?? 0;
  const currentTotal = roster?.current_projected_total ?? currentStarters.reduce((acc, p) => acc + (p.weekly_projected_points || p.projected_avg || 0), 0);
  const optimalTotal = roster?.optimal_projected_total ?? optimalStarters.reduce((acc, p) => acc + (p.weekly_projected_points || p.projected_avg || 0), 0);
  const recommendations = roster?.recommendations || [];

  const renderPlayerRow = (p: RosterPlayer, isRecommended = false) => {
    const isSwap = isRecommended && p.is_optimal_swap;
    const weeklyPts = p.weekly_projected_points ?? p.projected_avg ?? 0;
    return (
      <tr key={p.id} style={isSwap ? styles.swapHighlightRow : undefined}>
        <td style={{ width: "75px" }}>
          <span
            style={{
              ...styles.slotBadge,
              ...(p.is_starter ? styles.slotStarter : {}),
              ...(isSwap ? styles.slotSwap : {}),
            }}
            className="font-mono"
          >
            {p.lineup_slot || (p.is_starter ? "STARTER" : "BENCH")}
          </span>
        </td>
        <td style={{ width: "50px" }}>
          <span style={styles.posBadge} className="font-mono">
            {p.position}
          </span>
        </td>
        <td>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <strong style={styles.playerName}>{p.name}</strong>
            {isSwap && (
              <span style={styles.swapBadge} className="font-mono">
                +SWAP OPTIMAL
              </span>
            )}
          </div>
        </td>
        <td className="font-mono" style={styles.teamText}>
          {p.nfl_team}
        </td>
        <td>
          <span style={styles.statusWrap}>
            <span className={`status-dot ${getStatusDot(p.injury_status)}`} />
            <span style={{ fontSize: "11px" }}>{p.injury_status}</span>
          </span>
        </td>
        <td style={{ textAlign: "right", color: "var(--accent-amber)", fontWeight: 700 }} className="font-mono">
          {weeklyPts > 0 ? weeklyPts.toFixed(1) : "-"}
        </td>
        <td style={{ textAlign: "right", color: "var(--text-muted)" }} className="font-mono">
          {p.projected_points > 0 ? p.projected_points.toFixed(1) : "-"}
        </td>
        <td style={{ textAlign: "center", width: "160px" }}>
          <div style={{ display: "flex", gap: "6px", justifyContent: "center" }}>
            <button
              type="button"
              onClick={() => openCompareModal(p.id, p.lineup_slot, p.position)}
              style={styles.rowCompareBtn}
              className="font-mono"
              title={`Compare for ${p.lineup_slot || p.position} slot`}
            >
              VS COMPARE
            </button>
            <button
              type="button"
              onClick={() => openTradeModalForPlayer(p.name)}
              style={styles.rowTradeBtn}
              className="font-mono"
              title={`Find trade packages for ${p.name}`}
            >
              🤝 TRADES
            </button>
          </div>
        </td>
      </tr>
    );
  };

  const eligibleInModal = getEligiblePlayers(selectedSlot);
  const currentSlotDef = SLOTS.find((s) => s.id === selectedSlot) || SLOTS[0];

  return (
    <div style={styles.container}>
      {/* Header */}
      <header style={styles.header}>
        <div>
          <h1 style={styles.title} className="font-mono">
            ROSTER AUDIT & LINEUP STATUS
          </h1>
          <span style={styles.headerSub}>
            Team Cooper (#2) — {standings?.standings?.length || 10}-Team PPR (3-WR + 1-FLEX) | Roster: {players.length} Players
          </span>
        </div>

        <div style={styles.headerControls}>
          {statusMsg && (
            <span style={styles.statusMsg} className="font-mono">
              {statusMsg}
            </span>
          )}
          <button
            type="button"
            onClick={handleSync}
            disabled={syncing}
            className="btn-secondary btn-sm font-mono"
          >
            {syncing ? "SYNCING..." : "SYNC ESPN ROSTERS"}
          </button>
          <a
            href={process.env.NEXT_PUBLIC_ESPN_LEAGUE_URL || "https://fantasy.espn.com/football/"}
            target="_blank"
            rel="noopener noreferrer"
            style={styles.openEspnBtn}
            className="font-mono"
            title="Open ESPN Fantasy in a new tab to make live roster changes"
          >
            OPEN ESPN ↗
          </a>
          <button
            type="button"
            onClick={() => {
              setSelectedShopPlayer(null);
              setSelectedTradeTarget("");
              setTradeModalOpen(true);
            }}
            style={styles.tradeHeaderBtn}
            className="font-mono"
          >
            🤝 TARGET / STAR TRADES
          </button>
          <button
            type="button"
            onClick={() => openCompareModal()}
            style={styles.compareHeaderBtn}
            className="font-mono"
          >
            ⚖ COMPARE SIT / START
          </button>
          <button
            type="button"
            onClick={() => router.push("/")}
            className="btn-primary btn-sm font-mono"
          >
            ASK GM ABOUT LINEUP
          </button>
        </div>
      </header>

      {/* Main Grid */}
      <div style={styles.content}>
        {/* Left Column: Team Cooper Roster & Lineups */}
        <div style={styles.rosterPanel}>
          {/* Panel Controls & View Switcher */}
          <div style={styles.panelHeader}>
            <div style={styles.tabGroup}>
              <button
                type="button"
                onClick={() => setViewMode("current")}
                style={{
                  ...styles.tabBtn,
                  ...(viewMode === "current" ? styles.tabBtnActive : {}),
                }}
                className="font-mono"
              >
                CURRENT LINEUP ({currentTotal.toFixed(1)} PTS)
              </button>
              <button
                type="button"
                onClick={() => setViewMode("recommended")}
                style={{
                  ...styles.tabBtn,
                  ...(viewMode === "recommended" ? styles.tabBtnActive : {}),
                }}
                className="font-mono"
              >
                AI RECOMMENDED ({optimalTotal > 0 ? optimalTotal.toFixed(1) : currentTotal.toFixed(1)} PTS)
                {delta > 0 && (
                  <span style={styles.deltaBadge}>
                    +{delta.toFixed(2)}
                  </span>
                )}
              </button>
              <button
                type="button"
                onClick={() => setViewMode("all")}
                style={{
                  ...styles.tabBtn,
                  ...(viewMode === "all" ? styles.tabBtnActive : {}),
                }}
                className="font-mono"
              >
                ALL PLAYERS ({players.length})
              </button>
            </div>
            <span style={styles.rosterSub} className="font-mono">
              RECORD: {roster?.wins ?? 0}W - {roster?.losses ?? 0}L | PF: {roster?.points_for?.toFixed(1) ?? "0.0"}
            </span>
          </div>

          {/* AI Recommended Tactical Alert Box (when recommended view active) */}
          {viewMode === "recommended" && (
            <div style={styles.tacticalBanner}>
              <div style={styles.tacticalHeader} className="font-mono">
                <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <span style={{ color: "var(--accent-amber)", fontSize: "14px" }}>⚡</span>
                    <strong>AI GM LINEUP OPTIMIZATION (WEEK 1)</strong>
                  </span>
                  <span style={delta > 0 ? styles.gainBadge : styles.neutralBadge}>
                    {delta > 0 ? `+${delta.toFixed(2)} PT ADVANTAGE` : "LINEUP FULLY OPTIMIZED"}
                  </span>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    onClick={() => setShowDeepDive(!showDeepDive)}
                    style={styles.toggleWhyBtn}
                    className="font-mono"
                    title="Toggle strategic explanation for recommendations"
                  >
                    {showDeepDive ? "▲ HIDE TACTICAL ANALYSIS" : "▼ WHY THIS LINEUP?"}
                  </button>

                  <button
                    type="button"
                    onClick={handleApplyLineup}
                    disabled={applyingLineup || delta <= 0}
                    style={{
                      ...styles.applyBtn,
                      ...(delta <= 0 || applyingLineup ? styles.applyBtnDisabled : {}),
                    }}
                    className="font-mono"
                    title={delta > 0 ? "Lock recommended lineup into Gridiron AI strategy and simulation models" : "Lineup is already optimal"}
                  >
                    {applyingLineup
                      ? "LOCKING STRATEGY..."
                      : delta > 0
                      ? "⚡ LOCK GM STRATEGY"
                      : "✓ LINEUP ALREADY OPTIMAL"}
                  </button>
                  {delta > 0 && (
                    <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "4px", textAlign: "right" }} className="font-mono">
                      * ESPN restricts API writes. Confirm move via{" "}
                      <a
                        href={process.env.NEXT_PUBLIC_ESPN_LEAGUE_URL || "https://fantasy.espn.com/football/"}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: "#60a5fa", textDecoration: "underline" }}
                      >
                        ESPN Fantasy ↗
                      </a>
                    </div>
                  )}
                </div>
              </div>

              <div style={styles.tacticalBody}>
                {recommendations.length > 0 ? (
                  recommendations.map((rec, i) => (
                    <div key={i} style={styles.recItem}>
                      <span
                        style={{
                          ...styles.recTypeBadge,
                          ...(rec.action === "SWAP" ? styles.recSwapBadge : rec.action === "ALERT" ? styles.recAlertBadge : styles.recKeepBadge),
                        }}
                        className="font-mono"
                      >
                        {rec.action}
                      </span>
                      <span style={{ fontSize: "12px", color: "var(--text-primary)" }}>
                        {rec.reason}
                      </span>
                    </div>
                  ))
                ) : (
                  <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                    Current starters maximize weekly projected output across all active slots.
                  </span>
                )}

                {/* Tactical Rationale Deep Dive */}
                {showDeepDive && roster?.tactical_rationale && (
                  <div style={styles.deepDiveCard}>
                    <div style={styles.deepDiveHeader} className="font-mono">
                      <span style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--accent-amber)" }}>
                        <span>🧠</span>
                        <strong>TACTICAL RATIONALE & ADVANTAGE ANALYSIS</strong>
                      </span>
                      <span style={styles.deepDiveHeadline} className="font-mono">
                        {roster.tactical_rationale.headline}
                      </span>
                    </div>

                    <p style={styles.deepDiveSummary}>
                      {roster.tactical_rationale.summary}
                    </p>

                    {roster.tactical_rationale.pillars && roster.tactical_rationale.pillars.length > 0 && (
                      <div style={styles.pillarsGrid}>
                        {roster.tactical_rationale.pillars.map((pillar, idx) => (
                          <div key={idx} style={styles.pillarCard}>
                            <div style={styles.pillarTitle} className="font-mono">
                              <span style={{ color: "var(--accent-amber)", marginRight: "4px" }}>#{idx + 1}</span>
                              {pillar.title}
                            </div>
                            <div style={styles.pillarContent}>
                              {pillar.content}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {roster.tactical_rationale.contingencies && roster.tactical_rationale.contingencies.length > 0 && (
                      <div style={styles.contingencyBox}>
                        <span style={styles.contingencyTitle} className="font-mono">
                          ⚠️ CONTINGENCY WATCH:
                        </span>
                        <div style={styles.contingencyList}>
                          {roster.tactical_rationale.contingencies.map((c, idx) => (
                            <span key={idx} style={styles.contingencyItem}>• {c}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* VIEW: CURRENT OR RECOMMENDED (STARTERS ON TOP, BENCH BELOW) */}
          {viewMode !== "all" ? (
            <div>
              {/* Starters Section */}
              <div style={styles.sectionDivider} className="font-mono">
                <span>
                  {viewMode === "recommended" ? "OPTIMAL STARTING LINEUP (10 STARTERS)" : "CURRENT STARTING LINEUP (10 STARTERS)"}
                </span>
                <span style={{ color: "var(--accent-amber)" }}>
                  PROJECTED: {(viewMode === "recommended" ? optimalTotal : currentTotal).toFixed(1)} PTS
                </span>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: "75px" }}>SLOT</th>
                    <th style={{ width: "50px" }}>POS</th>
                    <th>PLAYER</th>
                    <th>NFL TEAM</th>
                    <th>STATUS</th>
                    <th style={{ textAlign: "right" }}>WK 1 PROJ</th>
                    <th style={{ textAlign: "right" }}>SEASON PROJ</th>
                    <th style={{ textAlign: "center", width: "90px" }}>COMPARE</th>
                  </tr>
                </thead>
                <tbody>
                  {(viewMode === "recommended" ? optimalStarters : currentStarters).length > 0 ? (
                    (viewMode === "recommended" ? optimalStarters : currentStarters).map((p) =>
                      renderPlayerRow(p, viewMode === "recommended")
                    )
                  ) : (
                    <tr>
                      <td colSpan={8} style={styles.emptyCell}>
                        {loading ? "Querying starting lineup from ESPN..." : "No starters found."}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>

              {/* Bench Section */}
              <div style={styles.sectionDividerBench} className="font-mono">
                <span>BENCH & RESERVES ({(viewMode === "recommended" ? optimalBench : currentBench).length} PLAYERS)</span>
                <span style={{ color: "var(--text-dim)" }}>NON-STARTING ROSTER</span>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: "75px" }}>SLOT</th>
                    <th style={{ width: "50px" }}>POS</th>
                    <th>PLAYER</th>
                    <th>NFL TEAM</th>
                    <th>STATUS</th>
                    <th style={{ textAlign: "right" }}>WK 1 PROJ</th>
                    <th style={{ textAlign: "right" }}>SEASON PROJ</th>
                    <th style={{ textAlign: "center", width: "90px" }}>COMPARE</th>
                  </tr>
                </thead>
                <tbody>
                  {(viewMode === "recommended" ? optimalBench : currentBench).length > 0 ? (
                    (viewMode === "recommended" ? optimalBench : currentBench).map((p) =>
                      renderPlayerRow(p, false)
                    )
                  ) : (
                    <tr>
                      <td colSpan={8} style={styles.emptyCell}>
                        No bench players found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          ) : (
            /* VIEW: ALL PLAYERS SORTED BY POSITION */
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: "75px" }}>SLOT</th>
                  <th style={{ width: "50px" }}>POS</th>
                  <th>PLAYER</th>
                  <th>NFL TEAM</th>
                  <th>STATUS</th>
                  <th style={{ textAlign: "right" }}>WK 1 PROJ</th>
                  <th style={{ textAlign: "right" }}>SEASON PROJ</th>
                  <th style={{ textAlign: "center", width: "90px" }}>COMPARE</th>
                </tr>
              </thead>
              <tbody>
                {players.length > 0 ? (
                  players.map((p) => renderPlayerRow(p, false))
                ) : (
                  <tr>
                    <td colSpan={8} style={styles.emptyCell}>
                      {loading ? "Querying team roster from ESPN..." : "No players found. Click 'Sync ESPN Rosters' to import."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* Right Column: League Standings & Dynamic Positional Allocation */}
        <div style={styles.sideCol}>
          {/* League Standings Table */}
          <div style={styles.panel}>
            <div style={styles.panelHeaderSide} className="font-mono">
              <span>LEAGUE STANDINGS ({standings?.standings?.length || 10} TEAMS)</span>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: "36px" }}>#</th>
                  <th>TEAM</th>
                  <th style={{ textAlign: "center" }}>REC</th>
                  <th style={{ textAlign: "right" }}>PF</th>
                </tr>
              </thead>
              <tbody>
                {standings?.standings && standings.standings.length > 0 ? (
                  standings.standings.map((team, idx) => {
                    const isMyTeam = team.team_id === 2;
                    return (
                      <tr key={team.team_id} style={isMyTeam ? styles.myTeamRow : undefined}>
                        <td className="font-mono" style={{ color: "var(--text-dim)" }}>
                          {idx + 1}
                        </td>
                        <td>
                          <span
                            style={{
                              fontWeight: isMyTeam ? 700 : 500,
                              color: isMyTeam ? "var(--accent-amber)" : "var(--text-primary)",
                            }}
                          >
                            {team.team_name}
                          </span>
                        </td>
                        <td style={{ textAlign: "center" }} className="font-mono">
                          {team.wins}-{team.losses}
                        </td>
                        <td style={{ textAlign: "right" }} className="font-mono">
                          {team.points_for.toFixed(1)}
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={4} style={styles.emptyCell}>
                      {loading ? "Loading standings..." : "Standings unavailable."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Dynamic Positional Allocation Card */}
          <div style={styles.panel}>
            <div style={styles.panelHeaderSide} className="font-mono">
              POSITIONAL ALLOCATION
            </div>
            <div style={styles.allocationList} className="font-mono">
              <div style={styles.allocRow}>
                <span style={styles.allocKey}>QUARTERBACKS (1 START)</span>
                <span style={styles.allocVal}>
                  {qbs.length} ({formatPlayerNames(qbs, 2)})
                </span>
              </div>
              <div style={styles.allocRow}>
                <span style={styles.allocKey}>RUNNING BACKS (2 START)</span>
                <span style={styles.allocVal}>
                  {rbs.length} ({formatPlayerNames(rbs, 3)})
                </span>
              </div>
              <div style={styles.allocRow}>
                <span style={styles.allocKey}>WIDE RECEIVERS (3 START)</span>
                <span style={styles.allocVal}>
                  {wrs.length} ({formatPlayerNames(wrs, 3)})
                </span>
              </div>
              <div style={styles.allocRow}>
                <span style={styles.allocKey}>TIGHT ENDS (1 START)</span>
                <span style={styles.allocVal}>
                  {tes.length} ({formatPlayerNames(tes, 2)})
                </span>
              </div>
              <div style={styles.allocRow}>
                <span style={styles.allocKey}>KICKER & DST</span>
                <span style={styles.allocVal}>
                  {ks.length + dsts.length} ({formatPlayerNames([...ks, ...dsts], 2)})
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── SIT / START HEAD-TO-HEAD COMPARISON MODAL (BY SLOTTED POSITION) ── */}
      {compareModalOpen && (
        <div style={styles.modalOverlay} onClick={() => setCompareModalOpen(false)}>
          <div style={styles.modalBox} onClick={(e) => e.stopPropagation()}>
            <div style={styles.modalHeader}>
              <div>
                <h2 style={styles.modalTitle} className="font-mono">
                  SIT / START HEAD-TO-HEAD COMPARISON
                </h2>
                <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                  Evaluate matchup projections, volume metrics, and AI GM tactical recommendations for a specific starting slot.
                </span>
              </div>
              <button
                type="button"
                onClick={() => setCompareModalOpen(false)}
                style={styles.modalCloseBtn}
              >
                ✕
              </button>
            </div>

            {/* Slotted Position Selector */}
            <div style={styles.slotSelectorBar}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={styles.slotSelectorLabel} className="font-mono">
                  TARGET STARTING SLOT:
                </span>
                <span style={{ fontSize: "11px", color: "var(--accent-amber)", fontWeight: 700 }} className="font-mono">
                  {currentSlotDef.label}
                </span>
              </div>
              <div style={styles.slotPillGroup}>
                {SLOTS.map((slot) => {
                  const isSelected = selectedSlot === slot.id;
                  const eligibleCount = getEligiblePlayers(slot.id).length;
                  return (
                    <button
                      key={slot.id}
                      type="button"
                      onClick={() => handleSelectSlot(slot.id)}
                      style={{
                        ...styles.slotPill,
                        ...(isSelected ? styles.slotPillActive : {}),
                      }}
                      className="font-mono"
                    >
                      <span>{slot.shortLabel}</span>
                      <span style={styles.slotPillCount}>({eligibleCount})</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Selectors or Insufficient Notice */}
            {eligibleInModal.length < 2 ? (
              <div style={styles.insufficientEligible} className="font-mono">
                <span style={{ color: "var(--accent-amber)", fontSize: "12px", fontWeight: 700 }}>
                  ⚠️ Only {eligibleInModal.length} player ({eligibleInModal[0]?.name || "None"}) rostered for {currentSlotDef.shortLabel}.
                </span>
                <span style={{ fontSize: "11px", color: "var(--text-dim)", marginTop: "4px" }}>
                  To compare your starter against prospective free agents for this slot, visit the Waiver Wire tool.
                </span>
              </div>
            ) : (
              <div style={styles.compareSelectors}>
                <div style={styles.selectGroup}>
                  <label style={styles.selectLabel} className="font-mono">
                    CANDIDATE A ({currentSlotDef.shortLabel})
                  </label>
                  <select
                    value={playerAId}
                    onChange={(e) => handleSelectPlayerA(e.target.value)}
                    style={styles.selectInput}
                    className="font-mono"
                  >
                    <option value="">Select player...</option>
                    {eligibleInModal.map((p) => (
                      <option key={`a-${p.id}`} value={p.id}>
                        {p.name} ({p.position} - {p.nfl_team}) {p.is_starter ? `[${p.lineup_slot || "START"}]` : "[BENCH]"}
                      </option>
                    ))}
                  </select>
                </div>

                <div style={styles.vsBadge} className="font-mono">VS</div>

                <div style={styles.selectGroup}>
                  <label style={styles.selectLabel} className="font-mono">
                    CANDIDATE B ({currentSlotDef.shortLabel})
                  </label>
                  <select
                    value={playerBId}
                    onChange={(e) => handleSelectPlayerB(e.target.value)}
                    style={styles.selectInput}
                    className="font-mono"
                  >
                    <option value="">Select player...</option>
                    {eligibleInModal.map((p) => (
                      <option key={`b-${p.id}`} value={p.id}>
                        {p.name} ({p.position} - {p.nfl_team}) {p.is_starter ? `[${p.lineup_slot || "START"}]` : "[BENCH]"}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {/* Comparison Body */}
            {comparing ? (
              <div style={styles.comparingState} className="font-mono">
                Evaluating {currentSlotDef.shortLabel} metrics and matchup variables...
              </div>
            ) : compareError ? (
              <div style={styles.compareError} className="font-mono">
                {compareError}
              </div>
            ) : comparisonData && eligibleInModal.length >= 2 ? (
              <div style={styles.compareResults}>
                {/* Side-by-Side Cards */}
                <div style={styles.cardsGrid}>
                  {/* Card A */}
                  <div
                    style={{
                      ...styles.playerCard,
                      ...(comparisonData.recommended_id === comparisonData.player_a.id ? styles.winnerCard : {}),
                    }}
                  >
                    <div style={styles.cardTop}>
                      <div>
                        <span style={styles.posBadge} className="font-mono">{comparisonData.player_a.position}</span>
                        <h3 style={styles.cardPlayerName}>{comparisonData.player_a.name}</h3>
                        <span style={styles.teamText} className="font-mono">{comparisonData.player_a.nfl_team}</span>
                      </div>
                      {comparisonData.recommended_id === comparisonData.player_a.id ? (
                        <span style={styles.verdictStartBadge} className="font-mono">START AT {currentSlotDef.shortLabel}</span>
                      ) : (
                        <span style={styles.verdictSitBadge} className="font-mono">SIT / BENCH</span>
                      )}
                    </div>
                    <div style={styles.metricMain}>
                      <span style={styles.metricBig} className="font-mono">
                        {comparisonData.player_a.weekly_projected_points?.toFixed(1) || "-"}
                      </span>
                      <span style={styles.metricLabel} className="font-mono">WK 1 PROJ PTS</span>
                    </div>
                  </div>

                  {/* Card B */}
                  <div
                    style={{
                      ...styles.playerCard,
                      ...(comparisonData.recommended_id === comparisonData.player_b.id ? styles.winnerCard : {}),
                    }}
                  >
                    <div style={styles.cardTop}>
                      <div>
                        <span style={styles.posBadge} className="font-mono">{comparisonData.player_b.position}</span>
                        <h3 style={styles.cardPlayerName}>{comparisonData.player_b.name}</h3>
                        <span style={styles.teamText} className="font-mono">{comparisonData.player_b.nfl_team}</span>
                      </div>
                      {comparisonData.recommended_id === comparisonData.player_b.id ? (
                        <span style={styles.verdictStartBadge} className="font-mono">START AT {currentSlotDef.shortLabel}</span>
                      ) : (
                        <span style={styles.verdictSitBadge} className="font-mono">SIT / BENCH</span>
                      )}
                    </div>
                    <div style={styles.metricMain}>
                      <span style={styles.metricBig} className="font-mono">
                        {comparisonData.player_b.weekly_projected_points?.toFixed(1) || "-"}
                      </span>
                      <span style={styles.metricLabel} className="font-mono">WK 1 PROJ PTS</span>
                    </div>
                  </div>
                </div>

                {/* Detailed Metrics Table */}
                <table style={styles.compTable} className="font-mono">
                  <tbody>
                    <tr>
                      <td style={styles.compCellA}>{comparisonData.player_a.weekly_projected_points?.toFixed(1)}</td>
                      <td style={styles.compCellMetric}>WEEKLY PROJECTION</td>
                      <td style={styles.compCellB}>{comparisonData.player_b.weekly_projected_points?.toFixed(1)}</td>
                    </tr>
                    <tr>
                      <td style={styles.compCellA}>{comparisonData.player_a.projected_avg?.toFixed(1) || "-"}</td>
                      <td style={styles.compCellMetric}>SEASON AVG / GM</td>
                      <td style={styles.compCellB}>{comparisonData.player_b.projected_avg?.toFixed(1) || "-"}</td>
                    </tr>
                    <tr>
                      <td style={styles.compCellA}>{comparisonData.player_a.percent_owned ?? "-"}%</td>
                      <td style={styles.compCellMetric}>% ROSTERED (ESPN)</td>
                      <td style={styles.compCellB}>{comparisonData.player_b.percent_owned ?? "-"}%</td>
                    </tr>
                    <tr>
                      <td style={styles.compCellA}>{comparisonData.player_a.percent_started ?? "-"}%</td>
                      <td style={styles.compCellMetric}>% STARTED</td>
                      <td style={styles.compCellB}>{comparisonData.player_b.percent_started ?? "-"}%</td>
                    </tr>
                    <tr>
                      <td style={styles.compCellA}>
                        <span style={{ color: comparisonData.player_a.injury_status.toLowerCase().includes("out") ? "var(--accent-red)" : "var(--text-primary)" }}>
                          {comparisonData.player_a.injury_status}
                        </span>
                      </td>
                      <td style={styles.compCellMetric}>INJURY STATUS</td>
                      <td style={styles.compCellB}>
                        <span style={{ color: comparisonData.player_b.injury_status.toLowerCase().includes("out") ? "var(--accent-red)" : "var(--text-primary)" }}>
                          {comparisonData.player_b.injury_status}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>

                {/* AI GM Verdict Box */}
                <div style={styles.verdictBox}>
                  <div style={styles.verdictHeader} className="font-mono">
                    <span>🧠 AI GM TACTICAL VERDICT ({currentSlotDef.shortLabel})</span>
                    <span style={styles.deltaNotice}>
                      MARGIN: +{comparisonData.projected_delta.toFixed(2)} PTS
                    </span>
                  </div>
                  <div style={styles.verdictText}>
                    {comparisonData.verdict}
                  </div>
                </div>
              </div>
            ) : null}

            {/* Modal Footer */}
            <div style={styles.modalFooter}>
              <button
                type="button"
                onClick={() => setCompareModalOpen(false)}
                className="btn-secondary btn-sm font-mono"
              >
                CLOSE
              </button>
              <button
                type="button"
                onClick={() => {
                  setCompareModalOpen(false);
                  router.push("/");
                }}
                className="btn-primary btn-sm font-mono"
              >
                ASK GM ABOUT THIS IN CHAT →
              </button>
            </div>
          </div>
        </div>
      )}

      <TradePackageModal
        isOpen={tradeModalOpen}
        onClose={() => setTradeModalOpen(false)}
        initialTargetPlayer={selectedTradeTarget}
        shopPlayerName={selectedShopPlayer}
        onActionCreated={() => fetchData()}
      />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: "var(--space-6)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-6)",
    height: "100%",
    overflowY: "auto",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    paddingBottom: "var(--space-4)",
    borderBottom: "1px solid var(--border-subtle)",
  },
  title: {
    fontSize: "18px",
    fontWeight: 700,
    color: "var(--text-primary)",
    letterSpacing: "-0.02em",
  },
  headerSub: {
    fontSize: "12px",
    color: "var(--text-muted)",
  },
  headerControls: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-3)",
  },
  statusMsg: {
    fontSize: "11px",
    color: "var(--accent-amber)",
  },
  compareHeaderBtn: {
    padding: "6px 12px",
    backgroundColor: "rgba(245, 158, 11, 0.1)",
    border: "1px solid var(--accent-amber)",
    color: "var(--accent-amber)",
    borderRadius: "var(--radius-sm)",
    fontSize: "11px",
    fontWeight: 700,
    cursor: "pointer",
  },
  tradeHeaderBtn: {
    padding: "6px 12px",
    backgroundColor: "rgba(245, 158, 11, 0.18)",
    border: "1px solid var(--accent-amber)",
    color: "var(--accent-amber)",
    borderRadius: "var(--radius-sm)",
    fontSize: "11px",
    fontWeight: 700,
    cursor: "pointer",
  },
  openEspnBtn: {
    padding: "6px 12px",
    backgroundColor: "rgba(59, 130, 246, 0.12)",
    border: "1px solid rgba(59, 130, 246, 0.4)",
    color: "#60a5fa",
    borderRadius: "var(--radius-sm)",
    fontSize: "11px",
    fontWeight: 700,
    cursor: "pointer",
    textDecoration: "none",
    display: "inline-flex",
    alignItems: "center",
  },
  content: {
    display: "grid",
    gridTemplateColumns: "1fr 340px",
    gap: "var(--space-6)",
    flex: 1,
    alignItems: "start",
  },
  rosterPanel: {
    backgroundColor: "var(--bg-surface)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-md)",
    overflow: "hidden",
  },
  panelHeader: {
    padding: "var(--space-2) var(--space-4)",
    backgroundColor: "var(--bg-raised)",
    borderBottom: "1px solid var(--border-subtle)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    flexWrap: "wrap",
    gap: "var(--space-2)",
  },
  tabGroup: {
    display: "flex",
    gap: "6px",
    alignItems: "center",
  },
  tabBtn: {
    padding: "6px 12px",
    backgroundColor: "var(--bg-base)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-sm)",
    color: "var(--text-dim)",
    fontSize: "11px",
    fontWeight: 600,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    gap: "6px",
    transition: "all 0.15s ease",
  },
  tabBtnActive: {
    backgroundColor: "var(--bg-surface)",
    borderColor: "var(--accent-amber)",
    color: "var(--accent-amber)",
  },
  deltaBadge: {
    backgroundColor: "rgba(16, 185, 129, 0.15)",
    border: "1px solid rgba(16, 185, 129, 0.4)",
    color: "#34d399",
    padding: "1px 5px",
    borderRadius: "3px",
    fontSize: "10px",
    fontWeight: 700,
  },
  rosterSub: {
    fontSize: "11px",
    color: "var(--accent-amber)",
    fontWeight: 500,
  },
  tacticalBanner: {
    margin: "var(--space-3) var(--space-4)",
    padding: "var(--space-3) var(--space-4)",
    backgroundColor: "rgba(245, 158, 11, 0.05)",
    border: "1px solid rgba(245, 158, 11, 0.3)",
    borderRadius: "var(--radius-sm)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-2)",
  },
  tacticalHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: "11px",
    color: "var(--text-primary)",
    letterSpacing: "0.04em",
  },
  gainBadge: {
    backgroundColor: "rgba(16, 185, 129, 0.2)",
    color: "#34d399",
    border: "1px solid rgba(16, 185, 129, 0.4)",
    padding: "2px 6px",
    borderRadius: "3px",
    fontSize: "10px",
    fontWeight: 700,
  },
  neutralBadge: {
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    color: "var(--text-dim)",
    border: "1px solid var(--border-subtle)",
    padding: "2px 6px",
    borderRadius: "3px",
    fontSize: "10px",
  },
  tacticalBody: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  recItem: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  recTypeBadge: {
    fontSize: "9px",
    fontWeight: 700,
    padding: "1px 5px",
    borderRadius: "2px",
    letterSpacing: "0.04em",
  },
  recSwapBadge: {
    backgroundColor: "rgba(245, 158, 11, 0.2)",
    border: "1px solid var(--accent-amber)",
    color: "var(--accent-amber)",
  },
  recAlertBadge: {
    backgroundColor: "rgba(239, 68, 68, 0.2)",
    border: "1px solid #ef4444",
    color: "#f87171",
  },
  recKeepBadge: {
    backgroundColor: "rgba(16, 185, 129, 0.1)",
    border: "1px solid #10b981",
    color: "#34d399",
  },
  applyBtn: {
    padding: "6px 14px",
    backgroundColor: "var(--accent-amber)",
    color: "#000",
    fontWeight: 700,
    fontSize: "11px",
    borderRadius: "var(--radius-sm)",
    border: "none",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    gap: "6px",
    transition: "all 0.15s ease",
  },
  applyBtnDisabled: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
    color: "var(--text-dim)",
    cursor: "not-allowed",
    border: "1px solid var(--border-subtle)",
  },
  toggleWhyBtn: {
    padding: "5px 10px",
    backgroundColor: "rgba(245, 158, 11, 0.1)",
    color: "var(--accent-amber)",
    fontSize: "11px",
    border: "1px solid rgba(245, 158, 11, 0.3)",
    borderRadius: "var(--radius-sm)",
    cursor: "pointer",
    letterSpacing: "0.02em",
  },
  deepDiveCard: {
    marginTop: "var(--space-2)",
    padding: "12px 14px",
    backgroundColor: "rgba(0, 0, 0, 0.35)",
    border: "1px solid rgba(245, 158, 11, 0.25)",
    borderRadius: "var(--radius-sm)",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  },
  deepDiveHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: "11px",
  },
  deepDiveHeadline: {
    color: "#34d399",
    fontWeight: 700,
    fontSize: "11px",
  },
  deepDiveSummary: {
    fontSize: "12px",
    color: "var(--text-primary)",
    lineHeight: 1.5,
    margin: 0,
  },
  pillarsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: "10px",
  },
  pillarCard: {
    padding: "10px 12px",
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "var(--radius-sm)",
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  pillarTitle: {
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--text-primary)",
    letterSpacing: "0.04em",
  },
  pillarContent: {
    fontSize: "11px",
    color: "var(--text-muted)",
    lineHeight: 1.45,
  },
  contingencyBox: {
    padding: "8px 10px",
    backgroundColor: "rgba(239, 68, 68, 0.08)",
    border: "1px solid rgba(239, 68, 68, 0.25)",
    borderRadius: "var(--radius-sm)",
    display: "flex",
    alignItems: "center",
    gap: "10px",
    fontSize: "11px",
  },
  contingencyTitle: {
    color: "#f87171",
    fontWeight: 700,
    whiteSpace: "nowrap",
  },
  contingencyList: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
    color: "var(--text-primary)",
  },
  contingencyItem: {
    fontSize: "11px",
  },
  sectionDivider: {
    padding: "8px var(--space-4)",
    backgroundColor: "rgba(245, 158, 11, 0.08)",
    borderTop: "1px solid var(--border-subtle)",
    borderBottom: "1px solid var(--border-subtle)",
    fontSize: "10px",
    fontWeight: 700,
    letterSpacing: "0.06em",
    color: "var(--text-dim)",
    display: "flex",
    justifyContent: "space-between",
  },
  sectionDividerBench: {
    padding: "8px var(--space-4)",
    backgroundColor: "var(--bg-raised)",
    borderTop: "1px solid var(--border-subtle)",
    borderBottom: "1px solid var(--border-subtle)",
    fontSize: "10px",
    fontWeight: 700,
    letterSpacing: "0.06em",
    color: "var(--text-dim)",
    display: "flex",
    justifyContent: "space-between",
  },
  posBadge: {
    fontSize: "10px",
    padding: "1px 4px",
    backgroundColor: "var(--bg-base)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-sm)",
    color: "var(--accent-amber)",
    fontWeight: 600,
  },
  playerName: {
    color: "var(--text-primary)",
    fontSize: "13px",
  },
  teamText: {
    color: "var(--text-muted)",
    fontSize: "12px",
  },
  slotBadge: {
    fontSize: "10px",
    padding: "1px 5px",
    backgroundColor: "var(--bg-base)",
    color: "var(--text-dim)",
    borderRadius: "var(--radius-sm)",
    border: "1px solid var(--border-subtle)",
    fontWeight: 600,
  },
  slotStarter: {
    borderColor: "var(--accent-amber)",
    color: "var(--accent-amber)",
  },
  slotSwap: {
    borderColor: "#34d399",
    color: "#34d399",
  },
  swapHighlightRow: {
    backgroundColor: "rgba(16, 185, 129, 0.06)",
  },
  swapBadge: {
    fontSize: "9px",
    padding: "1px 5px",
    backgroundColor: "rgba(16, 185, 129, 0.2)",
    border: "1px solid #34d399",
    borderRadius: "2px",
    color: "#34d399",
    fontWeight: 700,
  },
  statusWrap: {
    display: "inline-flex",
    alignItems: "center",
    gap: "var(--space-2)",
  },
  rowCompareBtn: {
    padding: "3px 6px",
    backgroundColor: "transparent",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-dim)",
    fontSize: "9px",
    borderRadius: "2px",
    cursor: "pointer",
    fontWeight: 600,
  },
  rowTradeBtn: {
    padding: "3px 6px",
    backgroundColor: "rgba(245, 158, 11, 0.08)",
    border: "1px solid var(--accent-amber)",
    color: "var(--accent-amber)",
    fontSize: "9px",
    borderRadius: "2px",
    cursor: "pointer",
    fontWeight: 700,
  },
  emptyCell: {
    padding: "var(--space-6)",
    textAlign: "center",
    color: "var(--text-dim)",
  },
  sideCol: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-6)",
  },
  panel: {
    backgroundColor: "var(--bg-surface)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-md)",
    overflow: "hidden",
    height: "fit-content",
  },
  panelHeaderSide: {
    padding: "var(--space-3) var(--space-4)",
    backgroundColor: "var(--bg-raised)",
    borderBottom: "1px solid var(--border-subtle)",
    fontSize: "11px",
    fontWeight: 700,
    color: "var(--text-dim)",
    letterSpacing: "0.05em",
  },
  myTeamRow: {
    backgroundColor: "var(--bg-raised)",
  },
  allocationList: {
    padding: "var(--space-3) var(--space-4)",
    fontSize: "12px",
  },
  allocRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "var(--space-2) 0",
    borderBottom: "1px solid var(--border-subtle)",
  },
  allocKey: {
    color: "var(--text-dim)",
    fontSize: "11px",
  },
  allocVal: {
    color: "var(--text-secondary)",
    fontSize: "11px",
  },

  // ── Sit/Start Modal Styles ──
  modalOverlay: {
    position: "fixed",
    inset: 0,
    backgroundColor: "rgba(0, 0, 0, 0.75)",
    backdropFilter: "blur(4px)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 999,
    padding: "var(--space-4)",
  },
  modalBox: {
    backgroundColor: "var(--bg-surface)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-lg)",
    width: "100%",
    maxWidth: "700px",
    overflow: "hidden",
    boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
    display: "flex",
    flexDirection: "column",
  },
  modalHeader: {
    padding: "var(--space-4)",
    backgroundColor: "var(--bg-raised)",
    borderBottom: "1px solid var(--border-subtle)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  modalTitle: {
    fontSize: "15px",
    fontWeight: 700,
    color: "var(--text-primary)",
    letterSpacing: "0.02em",
  },
  modalCloseBtn: {
    background: "none",
    border: "none",
    color: "var(--text-dim)",
    fontSize: "16px",
    cursor: "pointer",
    padding: "4px",
  },
  slotSelectorBar: {
    padding: "10px var(--space-4)",
    backgroundColor: "rgba(0, 0, 0, 0.35)",
    borderBottom: "1px solid var(--border-subtle)",
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  slotSelectorLabel: {
    fontSize: "10px",
    fontWeight: 700,
    color: "var(--accent-amber)",
    letterSpacing: "0.06em",
  },
  slotPillGroup: {
    display: "flex",
    gap: "6px",
    flexWrap: "wrap",
  },
  slotPill: {
    padding: "4px 8px",
    backgroundColor: "var(--bg-base)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-sm)",
    color: "var(--text-dim)",
    fontSize: "10px",
    fontWeight: 700,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    gap: "4px",
    transition: "all 0.15s ease",
  },
  slotPillActive: {
    backgroundColor: "rgba(245, 158, 11, 0.15)",
    borderColor: "var(--accent-amber)",
    color: "var(--accent-amber)",
  },
  slotPillCount: {
    fontSize: "9px",
    opacity: 0.75,
  },
  insufficientEligible: {
    padding: "var(--space-6)",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    textAlign: "center",
    backgroundColor: "rgba(0, 0, 0, 0.15)",
    borderBottom: "1px solid var(--border-subtle)",
  },
  compareSelectors: {
    padding: "var(--space-4)",
    display: "flex",
    alignItems: "center",
    gap: "var(--space-4)",
    borderBottom: "1px solid var(--border-subtle)",
    backgroundColor: "rgba(0, 0, 0, 0.2)",
  },
  selectGroup: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  selectLabel: {
    fontSize: "10px",
    color: "var(--text-dim)",
    fontWeight: 700,
    letterSpacing: "0.05em",
  },
  selectInput: {
    padding: "6px 8px",
    backgroundColor: "var(--bg-base)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-sm)",
    color: "var(--text-primary)",
    fontSize: "11px",
    outline: "none",
  },
  vsBadge: {
    padding: "6px 10px",
    backgroundColor: "rgba(245, 158, 11, 0.15)",
    border: "1px solid var(--accent-amber)",
    borderRadius: "50%",
    color: "var(--accent-amber)",
    fontSize: "10px",
    fontWeight: 800,
    marginTop: "16px",
  },
  comparingState: {
    padding: "var(--space-8)",
    textAlign: "center",
    color: "var(--accent-amber)",
    fontSize: "12px",
  },
  compareError: {
    padding: "var(--space-6)",
    textAlign: "center",
    color: "var(--accent-red)",
    fontSize: "12px",
  },
  compareResults: {
    padding: "var(--space-4)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-4)",
  },
  cardsGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "var(--space-4)",
  },
  playerCard: {
    padding: "var(--space-3)",
    backgroundColor: "var(--bg-base)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-md)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-3)",
  },
  winnerCard: {
    borderColor: "#34d399",
    backgroundColor: "rgba(16, 185, 129, 0.04)",
  },
  cardTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  cardPlayerName: {
    fontSize: "14px",
    fontWeight: 700,
    color: "var(--text-primary)",
    margin: "4px 0 2px 0",
  },
  verdictStartBadge: {
    fontSize: "9px",
    fontWeight: 800,
    padding: "2px 6px",
    backgroundColor: "rgba(16, 185, 129, 0.2)",
    border: "1px solid #10b981",
    color: "#34d399",
    borderRadius: "3px",
  },
  verdictSitBadge: {
    fontSize: "9px",
    fontWeight: 700,
    padding: "2px 6px",
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    border: "1px solid var(--border-subtle)",
    color: "var(--text-dim)",
    borderRadius: "3px",
  },
  metricMain: {
    display: "flex",
    flexDirection: "column",
    borderTop: "1px solid var(--border-subtle)",
    paddingTop: "var(--space-2)",
  },
  metricBig: {
    fontSize: "22px",
    fontWeight: 800,
    color: "var(--accent-amber)",
  },
  metricLabel: {
    fontSize: "9px",
    color: "var(--text-dim)",
    letterSpacing: "0.06em",
  },
  compTable: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "11px",
  },
  compCellA: {
    width: "35%",
    padding: "6px 8px",
    textAlign: "right",
    color: "var(--text-primary)",
    fontWeight: 600,
  },
  compCellMetric: {
    width: "30%",
    padding: "6px 8px",
    textAlign: "center",
    color: "var(--text-dim)",
    fontSize: "10px",
    letterSpacing: "0.04em",
  },
  compCellB: {
    width: "35%",
    padding: "6px 8px",
    textAlign: "left",
    color: "var(--text-primary)",
    fontWeight: 600,
  },
  verdictBox: {
    padding: "var(--space-3)",
    backgroundColor: "rgba(245, 158, 11, 0.08)",
    border: "1px solid rgba(245, 158, 11, 0.4)",
    borderRadius: "var(--radius-md)",
  },
  verdictHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: "10px",
    fontWeight: 700,
    color: "var(--accent-amber)",
    marginBottom: "4px",
  },
  deltaNotice: {
    fontSize: "10px",
    color: "var(--text-muted)",
  },
  verdictText: {
    fontSize: "12px",
    color: "var(--text-primary)",
    lineHeight: 1.5,
  },
  modalFooter: {
    padding: "var(--space-3) var(--space-4)",
    backgroundColor: "var(--bg-raised)",
    borderTop: "1px solid var(--border-subtle)",
    display: "flex",
    justifyContent: "flex-end",
    gap: "var(--space-3)",
  },
};
