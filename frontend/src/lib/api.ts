import {
  ChatRequest,
  ChatResponse,
  BudgetStatus,
  Transaction,
  HealthStatus,
  TeamRosterResponse,
  LeagueStandingsResponse,
  SyncResult,
  PlayerComparisonResponse,
} from "./types";

const getApiBase = (): string => {
  if (typeof window !== "undefined") {
    // In browser: relative path proxies through Next.js rewrites to backend ClusterIP.
    // Eliminates all CORS issues, port mismatches, and hostname dependencies.
    return "";
  }
  return process.env.INTERNAL_API_URL || "http://localhost:8000";
};

export async function chatWithGM(payload: ChatRequest): Promise<ChatResponse> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errData.detail || `Request failed with status ${res.status}`);
  }

  const data: ChatResponse = await res.json();
  return data;
}

export async function getChatSessions(): Promise<{ sessions: import("./types").ChatSessionSummary[]; count: number }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/chat/sessions`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch chat sessions");
  return res.json();
}

export async function createChatSession(title?: string): Promise<import("./types").ChatSessionSummary> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title || "New Conversation" }),
  });
  if (!res.ok) throw new Error("Failed to create chat session");
  return res.json();
}

export async function getSessionMessages(
  sessionId: string
): Promise<{
  session: import("./types").ChatSessionSummary;
  messages: Array<{
    id: string;
    session_id: string;
    sender: "user" | "gm";
    text: string;
    week: number;
    timestamp: string;
    created_at: string;
  }>;
}> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/chat/sessions/${encodeURIComponent(sessionId)}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch session messages");
  return res.json();
}

export async function deleteChatSession(sessionId: string): Promise<{ success: boolean; session_id: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete chat session");
  return res.json();
}

export async function getBudgetStatus(): Promise<BudgetStatus> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/budget`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch budget status");
  return res.json();
}

export async function getTransactions(hours: number = 48): Promise<{ count: number; transactions: Transaction[] }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/transactions?hours=${hours}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch transactions");
  return res.json();
}

export async function getHealthStatus(): Promise<HealthStatus> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/health`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch health status");
  return res.json();
}

export async function getTeamRoster(teamId: number = 2): Promise<TeamRosterResponse> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/roster/${teamId}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch team roster");
  return res.json();
}

export async function comparePlayers(playerAId: string, playerBId: string, slot?: string): Promise<PlayerComparisonResponse> {
  const base = getApiBase();
  const slotParam = slot ? `&slot=${encodeURIComponent(slot)}` : "";
  const res = await fetch(`${base}/api/lineup/compare?player_a_id=${encodeURIComponent(playerAId)}&player_b_id=${encodeURIComponent(playerBId)}${slotParam}`, { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to compare players" }));
    throw new Error(err.detail || "Failed to compare players");
  }
  return res.json();
}

export async function applyRecommendedLineup(teamId: number = 2): Promise<{ success: boolean; message: string; current_projected_total: number }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/lineup/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ team_id: teamId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to apply recommended lineup" }));
    throw new Error(err.detail || "Failed to apply recommended lineup");
  }
  return res.json();
}

export async function getLeagueStandings(): Promise<LeagueStandingsResponse> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/league/standings`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch league standings");
  return res.json();
}

export async function triggerESPNSync(): Promise<SyncResult> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/sync/espn`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to trigger ESPN sync");
  return res.json();
}

export async function triggerLeaguePoll(): Promise<{ count: number; [key: string]: unknown }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/monitor/poll`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to trigger league poll");
  return res.json();
}

export async function getDraftProjections(position?: string, limit: number = 100): Promise<import("./types").DraftProjectionsResponse> {
  const base = getApiBase();
  const query = new URLSearchParams();
  if (position && position !== "ALL") query.set("position", position);
  query.set("limit", limit.toString());
  const res = await fetch(`${base}/api/draft/projections?${query.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch draft projections");
  return res.json();
}

export async function getDraftLive(): Promise<import("./types").LiveDraftStatus> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/draft/live`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch live draft status");
  return res.json();
}

export async function getDraftRecommendations(pick?: number, limit: number = 10): Promise<import("./types").DraftRecommendationsResponse> {
  const base = getApiBase();
  const query = new URLSearchParams();
  if (pick !== undefined) query.set("pick", pick.toString());
  query.set("limit", limit.toString());
  const res = await fetch(`${base}/api/draft/recommendations?${query.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch draft recommendations");
  return res.json();
}

export async function getDraftPlayers(params: {
  page?: number;
  page_size?: number;
  position?: string;
  nfl_team?: string;
  availability?: string;
  search?: string;
  sort_by?: string;
  order?: string;
  limit?: number;
} = {}): Promise<import("./types").DraftPlayersResponse> {
  const base = getApiBase();
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page.toString());
  if (params.page_size) query.set("page_size", params.page_size.toString());
  if (params.position && params.position !== "ALL") query.set("position", params.position);
  if (params.nfl_team && params.nfl_team !== "ALL") query.set("nfl_team", params.nfl_team);
  if (params.availability) query.set("availability", params.availability);
  if (params.search) query.set("search", params.search);
  if (params.sort_by) query.set("sort_by", params.sort_by);
  if (params.order) query.set("order", params.order);
  if (params.limit) query.set("limit", params.limit.toString());
  const res = await fetch(`${base}/api/draft/players?${query.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch draft players pool");
  return res.json();
}

export async function getPlayerScouting(playerId: string): Promise<import("./types").PlayerScoutingDossier> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/player/${encodeURIComponent(playerId)}/scouting`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch player scouting dossier");
  return res.json();
}

export async function getDraftPrompts(): Promise<{ prompts: string[]; count: number }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/draft/prompts`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch dynamic draft prompts");
  return res.json();
}

export async function triggerDailySync(): Promise<Record<string, unknown>> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/draft/daily-sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error("Failed to trigger daily draft sync");
  return res.json();
}


// ── Waiver Wire Watchlist ──────────────────────────────────────────

export async function getWaiverWatchlist(): Promise<import("./types").WaiverWatchlistResponse> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/waivers/watchlist`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch waiver watchlist");
  return res.json();
}

export async function addToWatchlist(playerName: string): Promise<{ success: boolean; player_name: string; message: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/waivers/watchlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_name: playerName }),
  });
  if (!res.ok) throw new Error("Failed to add to watchlist");
  return res.json();
}

export async function removeFromWatchlist(playerName: string): Promise<{ success: boolean; player_name: string; message: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/waivers/watchlist/${encodeURIComponent(playerName)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to remove from watchlist");
  return res.json();
}


// ── Proactive Intelligence & Briefings ──────────────────────────

export async function getBriefings(unreadOnly: boolean = false): Promise<{ briefings: import("./types").AgentBriefing[]; count: number }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/briefings?unread_only=${unreadOnly}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch agent briefings");
  return res.json();
}

export async function markBriefingRead(briefingId: number): Promise<{ success: boolean; id: number }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/briefings/${briefingId}/read`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error("Failed to mark briefing as read");
  return res.json();
}

export async function markAllBriefingsRead(): Promise<{ success: boolean; message: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/briefings/mark-all-read`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error("Failed to mark all briefings read");
  return res.json();
}


// ── Tracking Jobs (Surveillance) ────────────────────────────────

export async function getTrackingJobs(includeInactive: boolean = false): Promise<{ jobs: import("./types").TrackingJob[]; count: number }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/tracking/jobs?include_inactive=${includeInactive}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch tracking jobs");
  return res.json();
}

export async function createTrackingJob(data: {
  player_name: string;
  focus_areas?: string[];
  frequency_minutes?: number;
  duration_hours?: number;
  reason?: string;
  custom_query?: string;
}): Promise<{ success: boolean; job: import("./types").TrackingJob }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/tracking/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create tracking job");
  return res.json();
}

export async function cancelTrackingJob(jobId: string): Promise<{ success: boolean; job_id: string; message: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/tracking/jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to cancel tracking job");
  return res.json();
}

export async function triggerTrackingJob(jobId: string): Promise<{ success: boolean; job_id: string; message: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/tracking/jobs/${encodeURIComponent(jobId)}/run`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to trigger tracking job run");
  return res.json();
}


// ── Pending Actions (Approval Gates) ────────────────────────────

export async function getPendingActions(status: string = "PENDING"): Promise<{ actions: import("./types").PendingAction[]; count: number }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/actions/pending?status=${status}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch pending actions");
  return res.json();
}

export async function approvePendingAction(actionId: number): Promise<{ success: boolean; action: import("./types").PendingAction }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/actions/${actionId}/approve`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to approve action");
  }
  return res.json();
}

export async function rejectPendingAction(actionId: number, reason?: string): Promise<{ success: boolean; action: import("./types").PendingAction }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/actions/${actionId}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: reason || "Rejected by user" }),
  });
  if (!res.ok) throw new Error("Failed to reject action");
  return res.json();
}


// ── Power Rankings & Season Strategy ────────────────────────────

export async function getPowerRankings(): Promise<{ league: string; rankings: import("./types").PowerRankingItem[]; updated_at: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/league/power-rankings`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch power rankings");
  return res.json();
}

export async function getSeasonStrategy(): Promise<{ team: string; strategy: import("./types").SeasonStrategy }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/team/season-strategy`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch season strategy");
  return res.json();
}

export async function triggerProactiveJob(jobName: string): Promise<{ success: boolean; job_name: string; message: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/proactive/trigger/${encodeURIComponent(jobName)}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to trigger autonomous job");
  return res.json();
}

export function getSseUrl(): string {
  return `${getApiBase()}/api/pulse/stream`;
}

// ── Trade Package & Target Acquisition API ───────────────────────

export async function acquireTargetPlayerTrades(
  targetPlayer: string
): Promise<import("./types").AcquireTradeResponse> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/trades/acquire?target_player=${encodeURIComponent(targetPlayer)}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to find trade packages for player");
  }
  return res.json();
}

export async function getTradePackages(
  playerName?: string
): Promise<{ packages: import("./types").TradePackage[]; count: number }> {
  const base = getApiBase();
  const url = playerName
    ? `${base}/api/trades/packages?player_name=${encodeURIComponent(playerName)}`
    : `${base}/api/trades/packages`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch trade packages");
  return res.json();
}

export async function getLeagueNeeds(): Promise<import("./types").TeamNeedsMatrix> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/trades/needs`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch league needs matrix");
  return res.json();
}

export async function proposeTradeAction(payload: {
  target_team_id: number;
  target_team_name: string;
  send_players: string[];
  receive_players: string[];
  rationale: string;
  pitch?: string;
}): Promise<{ success: boolean; action: import("./types").PendingAction }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/trades/propose-action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to create trade proposal action");
  }
  return res.json();
}

// ── Waiver Pickup & Drop Advice API ──────────────────────────────

export async function evaluateWaiverPickup(
  playerName: string
): Promise<import("./types").WaiverAdviceResponse> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/waivers/evaluate?player_name=${encodeURIComponent(playerName)}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to evaluate waiver pickup");
  }
  return res.json();
}

export async function proposeWaiverAction(payload: {
  action_type: string;
  add_player_name?: string;
  add_player_id?: string;
  drop_player_name?: string | null;
  drop_player_id?: string | null;
  ir_player_name?: string | null;
  ir_player_id?: string | null;
  bid_amount?: number;
  rationale: string;
}): Promise<{ success: boolean; action: import("./types").PendingAction }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/waivers/propose-action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to propose waiver action");
  }
  return res.json();
}

