export interface ChatRequest {
  message: string;
  week?: number;
  draft_id?: string;
  session_id?: string;
}

export interface ChatResponse {
  success: boolean;
  response: string;
  session_id?: string;
  user_message_id?: string;
  gm_message_id?: string;
  timestamp?: string;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message?: string | null;
}

export interface RateLimitBudget {
  rpm_used: number;
  rpm_limit: number;
  rpm_remaining: number;
  rpd_used: number;
  rpd_limit: number;
  rpd_remaining: number;
  tpm_used: number;
  tpm_limit: number;
}

export interface BudgetStatus {
  timestamp: string;
  gemini: RateLimitBudget;
  groq: RateLimitBudget;
}

export interface Transaction {
  id?: number;
  espn_transaction_id: string;
  type: string;
  impact_tier: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  details: {
    type?: string;
    team?: string;
    items?: Array<{
      player?: string;
      action?: string;
      to_team?: string;
      from_team?: string;
    }>;
    [key: string]: unknown;
  };
  agent_analysis?: string | null;
  timestamp: string;
}

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
  espn_auth: {
    valid: boolean;
    status: string;
    message: string;
  };
  cache_metrics: {
    hit_rate_pct: number;
    hits: number;
    misses: number;
    total_calls: number;
    tokens_saved: number;
  };
}

export interface AgentBriefing {
  id: number;
  briefing_type: string;
  urgency: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  title: string;
  content: string;
  structured_data?: Record<string, any>;
  action_items?: Array<{ type: string; label: string; [key: string]: any }>;
  source_agent: string;
  read: boolean;
  notified_discord?: boolean;
  notified_sse?: boolean;
  created_at: string;
}

export interface PendingAction {
  id: number;
  action_type: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXECUTED" | "FAILED" | "EXPIRED";
  urgency: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  confidence_score: number;
  title: string;
  description: string;
  rationale: string;
  payload: Record<string, any>;
  source_agent: string;
  expires_at: string | null;
  executed_at?: string | null;
  execution_result?: Record<string, any> | null;
  created_at: string;
}

export interface TrackingJob {
  job_id: string;
  player_name: string;
  focus_areas: string[];
  frequency_minutes: number;
  duration_hours: number;
  reason: string;
  source: string;
  custom_query?: string | null;
  status: "ACTIVE" | "CANCELLED" | "EXPIRED";
  created_at: string;
  expires_at: string;
  last_run_at?: string | null;
  next_run_at?: string | null;
  run_count: number;
  history?: Array<{
    timestamp: string;
    event: string;
    frequency_minutes?: number;
    reason?: string;
  }>;
}

export interface PowerRankingItem {
  rank: number;
  team_id: number;
  team_name: string;
  wins: number;
  losses: number;
  points_for: number;
  power_score: number;
  tier: string;
}

export interface SeasonStrategy {
  current_record: string;
  playoff_probability_pct: number;
  bye_week_crunches: Array<{ week: number; impact: string }>;
  playoff_schedule_grade: string;
  strategic_directives: string[];
  updated_at: string;
}

export interface RosterPlayer {
  id: string;
  name: string;
  position: string;
  nfl_team: string;
  injury_status: string;
  projected_points: number;
  projected_avg?: number;
  weekly_projected_points?: number;
  percent_owned?: number;
  percent_started?: number;
  lineup_slot: string;
  is_starter?: boolean;
  is_optimal_swap?: boolean;
}

export interface LineupRecommendation {
  action: "SWAP" | "KEEP" | "ALERT";
  player_in?: string;
  player_out?: string;
  slot?: string;
  delta?: number;
  reason: string;
}

export interface TacticalPillar {
  title: string;
  content: string;
}

export interface TacticalRationale {
  headline: string;
  summary: string;
  pillars: TacticalPillar[];
  contingencies?: string[];
}

export interface TeamRosterResponse {
  team_id: number;
  team_name: string;
  owner: string;
  wins: number;
  losses: number;
  points_for: number;
  count: number;
  current_week?: number;
  current_starters?: RosterPlayer[];
  current_bench?: RosterPlayer[];
  optimal_starters?: RosterPlayer[];
  optimal_bench?: RosterPlayer[];
  current_projected_total?: number;
  optimal_projected_total?: number;
  delta_vs_current?: number;
  recommendations?: LineupRecommendation[];
  tactical_rationale?: TacticalRationale;
  players: RosterPlayer[];
}

export interface PlayerComparisonResponse {
  player_a: RosterPlayer;
  player_b: RosterPlayer;
  target_slot?: string;
  recommended_start: string;
  recommended_id: string;
  projected_delta: number;
  verdict: string;
}

export interface TeamStanding {
  team_id: number;
  team_name: string;
  owner: string;
  wins: number;
  losses: number;
  ties: number;
  points_for: number;
  standing: number;
}

export interface LeagueStandingsResponse {
  league_name: string;
  season: number;
  standings: TeamStanding[];
}

export interface SyncResult {
  success: boolean;
  synced_teams?: number;
  error?: string;
}

export interface DraftPlayerProjection {
  id: string;
  name: string;
  position: string;
  nfl_team: string;
  projected_points: number;
  projected_avg: number;
  vorp: number;
  rostered_by: string | null;
  is_available: boolean;
  injury_status: string;
  stats?: Record<string, unknown>;
}

export interface DraftProjectionsResponse {
  season: number;
  scoring_format: string;
  count: number;
  baselines: Record<string, number>;
  players: DraftPlayerProjection[];
}

export interface LiveDraftStatus {
  is_live: boolean;
  status?: string;
  draft_order_finalized?: boolean;
  current_pick: number;
  active_round?: number;
  pick_in_round?: number;
  active_team_slot?: number;
  is_user_turn: boolean;
  next_user_pick?: number;
  picks_until_turn?: number;
  drafted_count: number;
  drafted_players: string[];
  keeper?: {
    player_name: string;
    position: string;
    nfl_team: string;
    round_cost: number;
    team_name?: string;
    [key: string]: unknown;
  };
  message?: string;
}

export interface DraftRecommendation {
  id: string;
  name: string;
  position: string;
  nfl_team: string;
  consensus_proj: number;
  projected_avg: number;
  espn_proj: number;
  sleeper_proj: number;
  adp: number | null;
  vorp: number;
  draft_grade: string;
  composite_score: number;
  sentiment_tag: string;
  injury_status: string;
  rationale: string;
}

export interface DraftRecommendationsResponse {
  draft_phase?: string;
  header_title?: string;
  active_pick?: number | null;
  active_round?: number | null;
  pick_in_round?: number | null;
  on_the_clock_team?: number | null;
  is_user_on_clock: boolean;
  next_user_pick?: number | null;
  picks_until_turn?: number;
  keeper?: {
    player_name: string;
    position: string;
    nfl_team: string;
    round_cost: number;
    team_name?: string;
    [key: string]: unknown;
  };
  user_roster_allocation: Record<string, number>;
  recommendations: DraftRecommendation[];
}

export interface DraftPoolPlayer {
  id: string;
  name: string;
  position: string;
  nfl_team: string;
  consensus_proj: number;
  projected_avg: number;
  espn_proj: number;
  sleeper_proj: number;
  adp: number | null;
  consensus_adp: number | null;
  sleeper_adp: number | null;
  espn_adp: number | null;
  yahoo_adp: number | null;
  vorp: number;
  is_available: boolean;
  rostered_by?: string | null;
  is_keeper?: boolean;
  keeper_team?: string | null;
  keeper_round?: number | null;
  injury_status: string;
  injury_notes?: string | null;
  sentiment_tag: string;
  sentiment_score: number;
}

export interface DraftPlayersResponse {
  page: number;
  page_size: number;
  total_pages: number;
  total_matches: number;
  count: number;
  baselines: Record<string, number>;
  players: DraftPoolPlayer[];
}

export interface PlayerScoutingDossier {
  player: {
    id: string;
    name: string;
    position: string;
    nfl_team: string;
    status: string;
    injury_status: string;
    injury_notes?: string | null;
    bye_week?: number;
    sentiment_tag: string;
    sentiment_score: number;
  };
  consensus: {
    points: number;
    avg: number;
    floor: number;
    ceiling: number;
    adp?: number | null;
    pass_yds?: number;
    rush_yds?: number;
    rec_yds?: number;
    rec?: number;
  };
  sources: {
    espn: {
      points: number;
      avg: number;
      adp?: number | null;
      stats?: Record<string, unknown>;
      season_outlook?: string | null;
    };
    sleeper: {
      points: number;
      avg: number;
      adp?: number | null;
      injury_body_part?: string | null;
      stats?: Record<string, unknown>;
    };
    yahoo: {
      adp?: number | null;
      status?: string | null;
      injury_note?: string | null;
      percent_drafted?: string | null;
    };
  };
  variance: {
    points_delta: number;
    adp_spread?: number;
    agreement_rating: string;
  };
  recent_news: Array<{
    headline?: string;
    text: string;
    source: string;
    tag?: string;
    timestamp?: string;
  }>;
}

export interface WaiverWatchlistPlayer {
  name: string;
  espn_id: string | null;
  position: string;
  nfl_team: string;
  projected_points: number;
  consensus_proj: number;
  vorp: number;
  injury_status: string;
  injury_notes: string;
  rostered_by: string;
  is_available: boolean;
}

export interface WaiverWatchlistResponse {
  watchlist: WaiverWatchlistPlayer[];
  count: number;
}

// ── Trade Package & Target Acquisition Types ─────────────────────

export interface TradePackage {
  package_type: string; // 1_FOR_1_SWAP | 2_FOR_1_CONSOLIDATION | 2_FOR_2_REBALANCE
  title: string;
  players_sent: string[];
  players_received: string[];
  target_team_id?: number;
  target_team_name: string;
  target_owner: string;
  opponent_hole_fixed?: string;
  opponent_weekly_delta: number;
  cooper_weekly_delta?: number;
  net_trade_equity: number;
  consolidation_bonus?: number;
  verdict: string;
  rationale: string;
  negotiation_pitch?: string;
  pitch?: string;
}

export interface AcquireTradeResponse {
  status: "PACKAGES_FOUND" | "FREE_AGENT" | "ALREADY_OWNED" | "NOT_FOUND";
  message?: string;
  target_player?: {
    name: string;
    position: string;
    team: string;
    projected_ppg: number;
    ros_trade_value: number;
    is_star?: boolean;
  };
  target_owner?: {
    espn_team_id: number;
    team_name: string;
    owner_name: string;
    weakest_position: string;
    weakest_starter?: {
      name: string;
      position: string;
      projected_ppg: number;
    };
    weak_starter_ppg: number;
  };
  packages: TradePackage[];
  count: number;
}

export interface TeamNeedsMatrixItem {
  espn_team_id: number;
  team_name: string;
  owner_name: string;
  position_needs: Record<string, string>;
  weakest_position: string;
  strongest_position: string;
  weakest_starter?: {
    name: string;
    position: string;
    projected_ppg: number;
  };
}

export interface TeamNeedsMatrix {
  league_size: number;
  teams: TeamNeedsMatrixItem[];
}

// ── Waiver Pickup & Cut Advice Types ─────────────────────────────

export interface WaiverCutCandidate {
  name: string;
  position: string;
  team: string;
  espn_id: string;
  projected_ppg: number;
  ros_trade_value: number;
  injury_status: string;
  droppability_score: number;
  is_injured: boolean;
}

export interface WaiverAdviceResponse {
  target_player: {
    name: string;
    position: string;
    team: string;
    projected_ppg: number;
    ros_trade_value: number;
    injury_status: string;
  };
  verdict: "STRONG ADD" | "SPECULATIVE STASH" | "PASS";
  verdict_badge: string;
  zero_cost_ir_stash: boolean;
  ir_recommendation?: {
    eligible_player: string;
    injury_status: string;
    current_slot: string;
    target_slot: string;
    instructions: string;
  } | null;
  primary_cut_candidate?: WaiverCutCandidate | null;
  secondary_cut_candidate?: WaiverCutCandidate | null;
  net_weekly_delta: number;
  net_ros_delta: number;
  rationale: string;
  bench_slots_total: number;
  action_payload?: {
    action_type: string;
    add_player_name?: string;
    add_player_id?: string;
    drop_player_name?: string | null;
    drop_player_id?: string | null;
    ir_player_name?: string | null;
    ir_player_id?: string | null;
  };
}

