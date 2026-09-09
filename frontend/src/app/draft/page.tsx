"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  getDraftPlayers,
  getTeamRoster,
  getTransactions,
  getWaiverWatchlist,
  addToWatchlist,
  removeFromWatchlist,
  triggerESPNSync,
  triggerDailySync,
} from "@/lib/api";
import {
  DraftPoolPlayer,
  WaiverWatchlistPlayer,
  RosterPlayer,
  Transaction,
} from "@/lib/types";
import { PlayerScoutingModal } from "@/components/PlayerScoutingModal";
import { WaiverAdviceModal } from "@/components/WaiverAdviceModal";
import { TradePackageModal } from "@/components/TradePackageModal";

const NFL_TEAMS = [
  "ALL", "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC",
  "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI",
  "PIT", "SEA", "SF", "TB", "TEN", "WSH"
];

const POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "K", "DST"];

export default function WaiverWirePage() {
  // ── Data state ──
  const [players, setPlayers] = useState<DraftPoolPlayer[]>([]);
  const [totalMatches, setTotalMatches] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null);

  // ── Waiver & Trade Modals state ──
  const [waiverModalOpen, setWaiverModalOpen] = useState(false);
  const [selectedWaiverPlayer, setSelectedWaiverPlayer] = useState<string | null>(null);
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [selectedTradeTarget, setSelectedTradeTarget] = useState<string | null>(null);

  const openWaiverAdvice = (playerName: string) => {
    setSelectedWaiverPlayer(playerName);
    setWaiverModalOpen(true);
  };

  const openTradeForPlayer = (playerName: string) => {
    setSelectedTradeTarget(playerName);
    setTradeModalOpen(true);
  };

  // Watchlist
  const [watchlist, setWatchlist] = useState<WaiverWatchlistPlayer[]>([]);
  const [watchlistLoading, setWatchlistLoading] = useState(true);

  // Roster
  const [roster, setRoster] = useState<RosterPlayer[]>([]);
  const [rosterLoading, setRosterLoading] = useState(true);

  // Transactions
  const [transactions, setTransactions] = useState<Transaction[]>([]);

  // Filters
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [selectedPositions, setSelectedPositions] = useState<string[]>(["ALL"]);
  const [selectedTeam, setSelectedTeam] = useState("ALL");
  const [sortBy, setSortBy] = useState("consensus_adp");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [availabilityFilter, setAvailabilityFilter] = useState("available");
  const [week, setWeek] = useState(1);

  // Layout
  const [isWatchlistCollapsed, setIsWatchlistCollapsed] = useState(false);
  const [isRosterCollapsed, setIsRosterCollapsed] = useState(true);
  const [isTransactionsCollapsed, setIsTransactionsCollapsed] = useState(true);
  const [rowDensity, setRowDensity] = useState<"compact" | "comfortable">("comfortable");

  // ── Debounced search ──
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // ── Fetch available players ──
  const fetchPlayers = useCallback(async () => {
    setLoading(true);
    try {
      const posFilter = selectedPositions.includes("ALL")
        ? undefined
        : selectedPositions.join(",");
      const res = await getDraftPlayers({
        page,
        page_size: pageSize,
        position: posFilter,
        nfl_team: selectedTeam !== "ALL" ? selectedTeam : undefined,
        availability: availabilityFilter,
        search: search || undefined,
        sort_by: sortBy,
        order: sortOrder,
      });
      setPlayers(res.players || []);
      setTotalMatches(res.total_matches || 0);
      setTotalPages(res.total_pages || 1);
    } catch (err) {
      console.error("Error fetching players:", err);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, selectedPositions, selectedTeam, availabilityFilter, search, sortBy, sortOrder]);

  useEffect(() => { fetchPlayers(); }, [fetchPlayers]);

  // ── Fetch watchlist ──
  const fetchWatchlist = useCallback(async () => {
    setWatchlistLoading(true);
    try {
      const res = await getWaiverWatchlist();
      setWatchlist(res.watchlist || []);
    } catch (err) {
      console.error("Error fetching watchlist:", err);
    } finally {
      setWatchlistLoading(false);
    }
  }, []);

  useEffect(() => { fetchWatchlist(); }, [fetchWatchlist]);

  // ── Fetch roster ──
  useEffect(() => {
    (async () => {
      setRosterLoading(true);
      try {
        const res = await getTeamRoster(2);
        setRoster(res.players || []);
      } catch (err) {
        console.error("Error fetching roster:", err);
      } finally {
        setRosterLoading(false);
      }
    })();
  }, []);

  // ── Fetch transactions ──
  useEffect(() => {
    (async () => {
      try {
        const res = await getTransactions(72);
        setTransactions(res.transactions || []);
      } catch (err) {
        console.error("Error fetching transactions:", err);
      }
    })();
  }, []);

  // ── Handlers ──
  const handleAddToWatchlist = async (playerName: string) => {
    try {
      await addToWatchlist(playerName);
      await fetchWatchlist();
    } catch (err) {
      console.error("Error adding to watchlist:", err);
    }
  };

  const handleRemoveFromWatchlist = async (playerName: string) => {
    try {
      await removeFromWatchlist(playerName);
      await fetchWatchlist();
    } catch (err) {
      console.error("Error removing from watchlist:", err);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      await Promise.all([triggerESPNSync(), triggerDailySync()]);
      await Promise.all([fetchPlayers(), fetchWatchlist()]);
    } catch (err) {
      console.error("Sync error:", err);
    } finally {
      setSyncing(false);
    }
  };

  const handleSort = (col: string) => {
    if (sortBy === col) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortBy(col);
      setSortOrder(col === "consensus_adp" ? "asc" : "desc");
    }
    setPage(1);
  };

  const togglePosition = (pos: string) => {
    if (pos === "ALL") {
      setSelectedPositions(["ALL"]);
    } else {
      const filtered = selectedPositions.filter((p) => p !== "ALL");
      if (filtered.includes(pos)) {
        const next = filtered.filter((p) => p !== pos);
        setSelectedPositions(next.length === 0 ? ["ALL"] : next);
      } else {
        setSelectedPositions([...filtered, pos]);
      }
    }
    setPage(1);
  };

  const isOnWatchlist = (name: string) => watchlist.some((w) => w.name === name);

  const getSortIcon = (col: string) => {
    if (sortBy !== col) return "↕";
    return sortOrder === "asc" ? "↑" : "↓";
  };

  const getInjuryColor = (status: string) => {
    const s = (status || "").toLowerCase();
    if (s === "out" || s === "ir") return "var(--accent-red, #ff4444)";
    if (s === "doubtful") return "var(--accent-red, #ff4444)";
    if (s === "questionable") return "var(--accent-amber, #f59e0b)";
    if (s === "probable") return "var(--accent-green, #22c55e)";
    return "var(--text-muted)";
  };

  const posColor = (pos: string) => {
    const m: Record<string, string> = {
      QB: "#e06c75", RB: "#56b6c2", WR: "#c678dd", TE: "#e5c07b", K: "#98c379", DST: "#61afef",
    };
    return m[pos] || "var(--text-muted)";
  };

  const rowPad = rowDensity === "compact" ? "5px 10px" : "8px 10px";

  return (
    <div style={S.page}>
      {/* ── Header ── */}
      <div style={S.header}>
        <div style={S.headerLeft}>
          <h1 style={S.title} className="font-mono">WAIVER WIRE</h1>
          <span style={S.weekBadge} className="font-mono">WEEK {week}</span>
          <select
            style={S.weekSelect}
            value={week}
            onChange={(e) => setWeek(Number(e.target.value))}
            className="font-mono"
          >
            {Array.from({ length: 18 }, (_, i) => (
              <option key={i + 1} value={i + 1}>WK {i + 1}</option>
            ))}
          </select>
        </div>
        <div style={S.headerRight}>
          <button
            style={{ ...S.syncBtn, opacity: syncing ? 0.5 : 1 }}
            onClick={handleSync}
            disabled={syncing}
            className="font-mono"
          >
            {syncing ? "⟳ SYNCING..." : "⟳ SYNC DATA"}
          </button>
          <select
            style={S.densitySelect}
            value={rowDensity}
            onChange={(e) => setRowDensity(e.target.value as "compact" | "comfortable")}
            className="font-mono"
          >
            <option value="compact">COMPACT</option>
            <option value="comfortable">COMFORTABLE</option>
          </select>
        </div>
      </div>

      {/* ── Top Panels Row ── */}
      <div style={S.topPanels}>
        {/* Watchlist Panel */}
        <div style={S.panel}>
          <div
            style={S.panelHeader}
            onClick={() => setIsWatchlistCollapsed(!isWatchlistCollapsed)}
          >
            <span className="font-mono" style={S.panelTitle}>
              👁 WATCHLIST {watchlist.length > 0 && `(${watchlist.length})`}
            </span>
            <span style={S.collapseIcon}>{isWatchlistCollapsed ? "▸" : "▾"}</span>
          </div>
          {!isWatchlistCollapsed && (
            <div style={S.panelBody}>
              {watchlistLoading ? (
                <div style={S.emptyMsg}>Loading watchlist...</div>
              ) : watchlist.length === 0 ? (
                <div style={S.emptyMsg}>No players on watchlist. Click ★ in the table to add.</div>
              ) : (
                <div style={S.watchlistGrid}>
                  {watchlist.map((w) => (
                    <div key={w.name} style={S.watchCard}>
                      <div style={S.watchCardTop}>
                        <span style={{ ...S.posBadge, color: posColor(w.position) }} className="font-mono">{w.position}</span>
                        <span style={S.watchName}>{w.name}</span>
                        <span style={S.watchTeam} className="font-mono">{w.nfl_team}</span>
                      </div>
                      <div style={S.watchCardMid}>
                        <span style={S.watchStat}>{w.consensus_proj} pts</span>
                        <span style={{ ...S.watchInjury, color: getInjuryColor(w.injury_status) }}>{w.injury_status}</span>
                        <span style={{ ...S.watchAvail, color: w.is_available ? "var(--accent-green, #22c55e)" : "var(--text-dim)" }}>
                          {w.is_available ? "FREE AGENT" : w.rostered_by}
                        </span>
                      </div>
                      <button
                        style={S.removeBtn}
                        onClick={() => handleRemoveFromWatchlist(w.name)}
                        title="Remove from watchlist"
                      >✕</button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Roster Panel */}
        <div style={S.panel}>
          <div
            style={S.panelHeader}
            onClick={() => setIsRosterCollapsed(!isRosterCollapsed)}
          >
            <span className="font-mono" style={S.panelTitle}>
              🏈 YOUR ROSTER ({roster.length})
            </span>
            <span style={S.collapseIcon}>{isRosterCollapsed ? "▸" : "▾"}</span>
          </div>
          {!isRosterCollapsed && (
            <div style={S.panelBody}>
              {rosterLoading ? (
                <div style={S.emptyMsg}>Loading roster...</div>
              ) : roster.length === 0 ? (
                <div style={S.emptyMsg}>No roster data. Run ESPN sync.</div>
              ) : (
                <div style={S.rosterGrid}>
                  {roster.map((p) => (
                    <div key={p.id} style={S.rosterCard}>
                      <span style={{ ...S.posBadge, color: posColor(p.position) }} className="font-mono">{p.position}</span>
                      <span style={S.rosterName}>{p.name}</span>
                      <span style={S.rosterTeam} className="font-mono">{p.nfl_team}</span>
                      <span style={{ ...S.rosterSlot, color: p.lineup_slot === "STARTER" ? "var(--accent-green, #22c55e)" : "var(--text-dim)" }} className="font-mono">
                        {p.lineup_slot === "STARTER" ? "START" : "BENCH"}
                      </span>
                      <span style={{ color: getInjuryColor(p.injury_status) }} className="font-mono">
                        {p.injury_status !== "Healthy" ? p.injury_status : ""}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Transactions Panel */}
        <div style={S.panel}>
          <div
            style={S.panelHeader}
            onClick={() => setIsTransactionsCollapsed(!isTransactionsCollapsed)}
          >
            <span className="font-mono" style={S.panelTitle}>
              📋 RECENT TRANSACTIONS ({transactions.length})
            </span>
            <span style={S.collapseIcon}>{isTransactionsCollapsed ? "▸" : "▾"}</span>
          </div>
          {!isTransactionsCollapsed && (
            <div style={S.panelBody}>
              {transactions.length === 0 ? (
                <div style={S.emptyMsg}>No recent transactions found.</div>
              ) : (
                <div style={{ maxHeight: "220px", overflowY: "auto" }}>
                  {transactions.slice(0, 15).map((tx, i) => (
                    <div key={tx.espn_transaction_id || i} style={S.txRow}>
                      <span style={{
                        ...S.txImpact,
                        color: tx.impact_tier === "CRITICAL" ? "#ff4444" : tx.impact_tier === "HIGH" ? "#f59e0b" : "var(--text-muted)"
                      }} className="font-mono">{tx.impact_tier}</span>
                      <span style={S.txType} className="font-mono">{tx.type}</span>
                      <span style={S.txDetails}>
                        {(tx.details?.items || []).map((item, j) => (
                          <span key={j}>{item.player} ({item.action}){j < (tx.details?.items?.length || 0) - 1 ? ", " : ""}</span>
                        ))}
                      </span>
                      <span style={S.txTime}>{tx.timestamp}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Filters ── */}
      <div style={S.filters}>
        <input
          style={S.searchInput}
          type="text"
          placeholder="Search players..."
          value={searchInput}
          onChange={(e) => { setSearchInput(e.target.value); setPage(1); }}
        />
        <div style={S.posFilters}>
          {POSITIONS.map((pos) => {
            const isActive = selectedPositions.includes(pos);
            return (
              <button
                key={pos}
                style={{
                  ...S.posBtn,
                  backgroundColor: isActive ? "var(--accent-amber, #f59e0b)" : "var(--bg-raised)",
                  color: isActive ? "var(--bg-base)" : "var(--text-muted)",
                }}
                onClick={() => togglePosition(pos)}
                className="font-mono"
              >
                {pos}
              </button>
            );
          })}
        </div>
        <select
          style={S.filterSelect}
          value={selectedTeam}
          onChange={(e) => { setSelectedTeam(e.target.value); setPage(1); }}
          className="font-mono"
        >
          {NFL_TEAMS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select
          style={S.filterSelect}
          value={availabilityFilter}
          onChange={(e) => { setAvailabilityFilter(e.target.value); setPage(1); }}
          className="font-mono"
        >
          <option value="available">FREE AGENTS</option>
          <option value="all">ALL PLAYERS</option>
          <option value="rostered">ROSTERED</option>
        </select>
      </div>

      {/* ── Table ── */}
      <div style={S.tableContainer}>
        <table style={S.table}>
          <thead>
            <tr style={S.thRow}>
              <th style={{ ...S.th, width: "40px" }}>★</th>
              <th style={{ ...S.th, width: "50px", cursor: "pointer" }} onClick={() => handleSort("position")}>POS {getSortIcon("position")}</th>
              <th style={{ ...S.th, width: "55px" }}>DEPTH</th>
              <th style={{ ...S.th, minWidth: "180px", textAlign: "left" }}>PLAYER</th>
              <th style={{ ...S.th, width: "55px" }}>TEAM</th>
              <th style={{ ...S.th, width: "80px", cursor: "pointer" }} onClick={() => handleSort("consensus_proj")}>PROJ {getSortIcon("consensus_proj")}</th>
              <th style={{ ...S.th, width: "70px", cursor: "pointer" }} onClick={() => handleSort("vorp")}>VORP {getSortIcon("vorp")}</th>
              <th style={{ ...S.th, width: "80px", cursor: "pointer" }} onClick={() => handleSort("consensus_adp")}>ADP {getSortIcon("consensus_adp")}</th>
              <th style={{ ...S.th, width: "60px", cursor: "pointer" }} onClick={() => handleSort("percent_owned")}>%OWN {getSortIcon("percent_owned")}</th>
              <th style={{ ...S.th, width: "60px", cursor: "pointer" }} onClick={() => handleSort("percent_started")}>%START {getSortIcon("percent_started")}</th>
              <th style={{ ...S.th, width: "90px" }}>INJURY</th>
              <th style={{ ...S.th, minWidth: "120px" }}>STATUS</th>
              <th style={{ ...S.th, width: "105px", textAlign: "center" }}>ACTION</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={13} style={S.loadingCell}>Loading free agent pool...</td></tr>
            ) : players.length === 0 ? (
              <tr><td colSpan={13} style={S.loadingCell}>No players match filters.</td></tr>
            ) : (
              players.map((p) => {
                const onWatch = isOnWatchlist(p.name);
                return (
                  <tr
                    key={p.id}
                    style={S.tr}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLElement).style.backgroundColor = "var(--bg-surface, #1a1a2e)";
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.backgroundColor = "transparent";
                    }}
                  >
                    <td style={{ ...S.td, padding: rowPad, textAlign: "center" }}>
                      <button
                        style={{
                          ...S.watchBtn,
                          color: onWatch ? "var(--accent-amber, #f59e0b)" : "var(--text-dim)",
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          onWatch ? handleRemoveFromWatchlist(p.name) : handleAddToWatchlist(p.name);
                        }}
                        title={onWatch ? "Remove from watchlist" : "Add to watchlist"}
                      >
                        {onWatch ? "★" : "☆"}
                      </button>
                    </td>
                    <td style={{ ...S.td, padding: rowPad, textAlign: "center" }}>
                      <span style={{ color: posColor(p.position), fontWeight: 600 }} className="font-mono">{p.position}</span>
                    </td>
                    <td style={{ ...S.td, padding: rowPad, textAlign: "center", fontSize: "10px" }} className="font-mono">
                      <span style={{ color: "var(--text-muted)" }}>{(p as any).depth_chart_pos || ""}</span>
                    </td>
                    <td
                      style={{ ...S.td, padding: rowPad, cursor: "pointer", fontWeight: 500 }}
                      onClick={() => setSelectedPlayerId(p.id)}
                    >
                      {p.name}
                    </td>
                    <td style={{ ...S.td, padding: rowPad, textAlign: "center" }} className="font-mono">{p.nfl_team}</td>
                    <td style={{ ...S.td, padding: rowPad, textAlign: "center" }} className="font-mono">{p.consensus_proj}</td>
                    <td style={{
                      ...S.td, padding: rowPad, textAlign: "center",
                      color: p.vorp > 0 ? "var(--accent-green, #22c55e)" : p.vorp < -20 ? "var(--accent-red, #ff4444)" : "var(--text-muted)"
                    }} className="font-mono">
                      {p.vorp > 0 ? "+" : ""}{p.vorp}
                    </td>
                    <td style={{ ...S.td, padding: rowPad, textAlign: "center" }} className="font-mono">
                      {p.consensus_adp || p.adp || "—"}
                    </td>
                    <td style={{
                      ...S.td, padding: rowPad, textAlign: "center",
                      color: ((p as any).percent_owned || 0) > 80 ? "var(--accent-green, #22c55e)" : ((p as any).percent_owned || 0) > 40 ? "var(--accent-amber, #f59e0b)" : "var(--text-dim)"
                    }} className="font-mono">
                      {(p as any).percent_owned ? `${(p as any).percent_owned}%` : "—"}
                    </td>
                    <td style={{
                      ...S.td, padding: rowPad, textAlign: "center",
                      color: ((p as any).percent_started || 0) > 50 ? "var(--accent-green, #22c55e)" : ((p as any).percent_started || 0) > 20 ? "var(--accent-amber, #f59e0b)" : "var(--text-dim)"
                    }} className="font-mono">
                      {(p as any).percent_started ? `${(p as any).percent_started}%` : "—"}
                    </td>
                    <td style={{ ...S.td, padding: rowPad, textAlign: "center", color: getInjuryColor(p.injury_status) }} className="font-mono">
                      {p.injury_status !== "Active" && p.injury_status !== "Healthy" ? p.injury_status : "—"}
                    </td>
                    <td style={{ ...S.td, padding: rowPad, fontSize: "11px" }}>
                      {p.is_available ? (
                        <span style={{ color: "var(--accent-green, #22c55e)" }} className="font-mono">FREE AGENT</span>
                      ) : (
                        <span style={{ color: "var(--text-dim)" }}>{p.rostered_by || "Rostered"}</span>
                      )}
                    </td>
                    <td style={{ ...S.td, padding: rowPad, textAlign: "center" }}>
                      {p.is_available ? (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openWaiverAdvice(p.name);
                          }}
                          style={S.adviceBtn}
                          className="font-mono"
                          title="Evaluate pickup and bench cut candidate"
                        >
                          ⚡ ADVICE
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openTradeForPlayer(p.name);
                          }}
                          style={S.tradeBtn}
                          className="font-mono"
                          title="Find trade packages to acquire this player"
                        >
                          🤝 TRADE
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* ── Pagination ── */}
      <div style={S.pagination}>
        <span style={S.pageInfo} className="font-mono">
          {totalMatches} players • Page {page}/{totalPages}
        </span>
        <div style={S.pageControls}>
          <button
            style={{ ...S.pageBtn, opacity: page <= 1 ? 0.3 : 1 }}
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="font-mono"
          >← PREV</button>
          <select
            style={S.pageSizeSelect}
            value={pageSize}
            onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
            className="font-mono"
          >
            <option value={25}>25/page</option>
            <option value={50}>50/page</option>
            <option value={100}>100/page</option>
          </select>
          <button
            style={{ ...S.pageBtn, opacity: page >= totalPages ? 0.3 : 1 }}
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="font-mono"
          >NEXT →</button>
        </div>
      </div>

      {/* ── Waiver Advice Modal ── */}
      <WaiverAdviceModal
        isOpen={waiverModalOpen}
        onClose={() => setWaiverModalOpen(false)}
        playerName={selectedWaiverPlayer}
        onActionCreated={() => {
          fetchPlayers();
        }}
      />

      {/* ── Trade Package Modal (for rostered players) ── */}
      <TradePackageModal
        isOpen={tradeModalOpen}
        onClose={() => setTradeModalOpen(false)}
        initialTargetPlayer={selectedTradeTarget}
        onActionCreated={() => {
          fetchPlayers();
        }}
      />

      {/* ── Scouting Modal ── */}
      {selectedPlayerId && (
        <PlayerScoutingModal
          playerId={selectedPlayerId}
          onClose={() => setSelectedPlayerId(null)}
        />
      )}
    </div>
  );
}


// ── Styles ──────────────────────────────────────────────────────────
const S: Record<string, React.CSSProperties> = {
  page: {
    display: "flex", flexDirection: "column", height: "100%",
    padding: "var(--space-4)", gap: "var(--space-3)", overflowY: "auto",
  },
  header: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    paddingBottom: "var(--space-3)", borderBottom: "1px solid var(--border-subtle)",
  },
  headerLeft: { display: "flex", alignItems: "center", gap: "var(--space-3)" },
  headerRight: { display: "flex", alignItems: "center", gap: "var(--space-2)" },
  title: {
    fontSize: "18px", fontWeight: 700, letterSpacing: "0.08em",
    color: "var(--accent-amber, #f59e0b)", margin: 0,
  },
  weekBadge: {
    fontSize: "11px", letterSpacing: "0.06em", padding: "3px 8px",
    borderRadius: "4px", backgroundColor: "var(--bg-surface)", color: "var(--text-secondary)",
    border: "1px solid var(--border-subtle)",
  },
  weekSelect: {
    fontSize: "11px", padding: "4px 6px", backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)", borderRadius: "4px", color: "var(--text-secondary)",
  },
  syncBtn: {
    fontSize: "11px", padding: "6px 12px", border: "1px solid var(--border-subtle)",
    borderRadius: "4px", backgroundColor: "var(--bg-raised)", color: "var(--text-secondary)",
    cursor: "pointer",
  },
  densitySelect: {
    fontSize: "10px", padding: "4px 6px", backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)", borderRadius: "4px", color: "var(--text-dim)",
  },

  // Top panels
  topPanels: {
    display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "var(--space-3)",
  },
  panel: {
    border: "1px solid var(--border-subtle)", borderRadius: "6px",
    backgroundColor: "var(--bg-raised)", overflow: "hidden",
  },
  panelHeader: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "8px 12px", cursor: "pointer", borderBottom: "1px solid var(--border-subtle)",
    backgroundColor: "var(--bg-surface)",
  },
  panelTitle: { fontSize: "11px", letterSpacing: "0.06em", color: "var(--text-secondary)" },
  collapseIcon: { fontSize: "12px", color: "var(--text-dim)" },
  panelBody: { padding: "8px 12px", maxHeight: "250px", overflowY: "auto" },
  emptyMsg: { fontSize: "12px", color: "var(--text-dim)", padding: "12px 0", textAlign: "center" as const },

  // Watchlist
  watchlistGrid: { display: "flex", flexDirection: "column" as const, gap: "6px" },
  watchCard: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "6px 8px", borderRadius: "4px", backgroundColor: "var(--bg-base)",
    border: "1px solid var(--border-subtle)", position: "relative" as const,
  },
  watchCardTop: { display: "flex", alignItems: "center", gap: "8px", flex: 1 },
  watchCardMid: { display: "flex", alignItems: "center", gap: "10px", fontSize: "11px" },
  watchName: { fontSize: "13px", fontWeight: 500, color: "var(--text-primary)" },
  watchTeam: { fontSize: "10px", color: "var(--text-dim)" },
  watchStat: { color: "var(--text-secondary)", fontFamily: "var(--font-jetbrains-mono)" },
  watchInjury: { fontSize: "10px", fontFamily: "var(--font-jetbrains-mono)" },
  watchAvail: { fontSize: "10px", fontFamily: "var(--font-jetbrains-mono)" },
  removeBtn: {
    background: "none", border: "none", color: "var(--text-dim)", cursor: "pointer",
    fontSize: "14px", padding: "2px 6px", marginLeft: "8px",
  },

  // Roster
  rosterGrid: { display: "flex", flexDirection: "column" as const, gap: "4px" },
  rosterCard: {
    display: "flex", alignItems: "center", gap: "8px",
    padding: "4px 6px", fontSize: "12px", borderBottom: "1px solid var(--border-subtle)",
  },
  rosterName: { flex: 1, fontWeight: 500, color: "var(--text-primary)" },
  rosterTeam: { fontSize: "10px", color: "var(--text-dim)", width: "35px" },
  rosterSlot: { fontSize: "10px", width: "45px" },

  // Transactions
  txRow: {
    display: "flex", alignItems: "center", gap: "8px",
    padding: "5px 0", fontSize: "11px", borderBottom: "1px solid var(--border-subtle)",
  },
  txImpact: { fontSize: "9px", width: "60px", letterSpacing: "0.04em" },
  txType: { fontSize: "10px", color: "var(--text-muted)", width: "60px" },
  txDetails: { flex: 1, color: "var(--text-secondary)" },
  txTime: { fontSize: "10px", color: "var(--text-dim)", minWidth: "80px", textAlign: "right" as const },

  // Filters
  filters: {
    display: "flex", alignItems: "center", gap: "var(--space-2)",
    flexWrap: "wrap" as const,
  },
  searchInput: {
    flex: 1, minWidth: "200px", maxWidth: "300px", padding: "7px 10px",
    fontSize: "13px", border: "1px solid var(--border-subtle)", borderRadius: "4px",
    backgroundColor: "var(--bg-raised)", color: "var(--text-primary)",
    outline: "none",
  },
  posFilters: { display: "flex", gap: "3px" },
  posBtn: {
    fontSize: "10px", padding: "5px 8px", border: "1px solid var(--border-subtle)",
    borderRadius: "3px", cursor: "pointer", letterSpacing: "0.04em",
  },
  filterSelect: {
    fontSize: "11px", padding: "5px 8px", backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)", borderRadius: "4px", color: "var(--text-secondary)",
  },

  // Table
  tableContainer: {
    flex: 1, overflow: "auto", borderRadius: "6px",
    border: "1px solid var(--border-subtle)",
  },
  table: {
    width: "100%", borderCollapse: "collapse" as const, fontSize: "12px",
  },
  thRow: { backgroundColor: "var(--bg-surface)" },
  th: {
    padding: "8px 10px", fontSize: "10px", fontWeight: 600,
    letterSpacing: "0.06em", color: "var(--text-dim)",
    textAlign: "center" as const, borderBottom: "1px solid var(--border-subtle)",
    fontFamily: "var(--font-jetbrains-mono)", userSelect: "none" as const,
  },
  tr: {
    borderBottom: "1px solid var(--border-subtle)", transition: "background-color 100ms ease",
  },
  td: {
    color: "var(--text-secondary)", fontSize: "12px",
  },
  loadingCell: {
    padding: "40px", textAlign: "center" as const, color: "var(--text-dim)",
    fontSize: "13px",
  },
  posBadge: { fontSize: "10px", fontWeight: 700, letterSpacing: "0.04em" },
  watchBtn: {
    background: "none", border: "none", cursor: "pointer", fontSize: "16px",
    padding: "0", lineHeight: 1,
  },
  adviceBtn: {
    padding: "3px 8px",
    fontSize: "10px",
    fontWeight: 700,
    backgroundColor: "rgba(16, 185, 129, 0.12)",
    border: "1px solid var(--accent-green, #22c55e)",
    color: "var(--accent-green, #22c55e)",
    borderRadius: "4px",
    cursor: "pointer",
  },
  tradeBtn: {
    padding: "3px 8px",
    fontSize: "10px",
    fontWeight: 700,
    backgroundColor: "rgba(245, 158, 11, 0.12)",
    border: "1px solid var(--accent-amber, #f59e0b)",
    color: "var(--accent-amber, #f59e0b)",
    borderRadius: "4px",
    cursor: "pointer",
  },

  // Pagination
  pagination: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "8px 0", borderTop: "1px solid var(--border-subtle)",
  },
  pageInfo: { fontSize: "11px", color: "var(--text-dim)" },
  pageControls: { display: "flex", alignItems: "center", gap: "8px" },
  pageBtn: {
    fontSize: "11px", padding: "5px 10px", border: "1px solid var(--border-subtle)",
    borderRadius: "4px", backgroundColor: "var(--bg-raised)", color: "var(--text-secondary)",
    cursor: "pointer",
  },
  pageSizeSelect: {
    fontSize: "11px", padding: "4px 8px", backgroundColor: "var(--bg-raised)",
    border: "1px solid var(--border-subtle)", borderRadius: "4px", color: "var(--text-secondary)",
  },
};
