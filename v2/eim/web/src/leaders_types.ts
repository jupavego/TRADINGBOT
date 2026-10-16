import type { AgentReport } from './types'

/** Contratos de `GET /v2/leaders/board` (T41; ver eim/copytrading/). Cifras en USD. */
export type Verdict = 'approved' | 'watch' | 'rejected'
export type Ci = [number, number] | null

export interface TradeStats {
  n: number; n_open: number; n_partial: number; wins: number; losses: number
  win_rate: number | null; net: number; pnl: number; fees: number; funding: number
  ret: number | null; profit_factor: number | null; avg_win: number | null; avg_loss: number | null
  payoff: number | null; max_dd: number | null; mean: number | null; mean_ci: Ci
  mean_bps: number | null; sharpe: number | null; sharpe_ci: Ci; dsr: number | null; sr0: number | null
  days: number; hold_ms: number | null; n_assets: number; assets: Record<string, number>
  top_asset: string | null; top_asset_share: number | null; lev_median: number | null
  lev_max: number | null; avg_down_share: number | null; martingale: number | null
  windows: number; windows_pos: number; worst_window: number | null; taker_share: number | null
  liquidations: number
}

export interface PortfolioStats {
  days: number; account_value: number | null; pnl: number; twr: number | null; max_dd: number | null
  windows: number; windows_pos: number; month_pnl: number | null; month_twr: number | null
}

export interface CopyStats {
  delay_ms: number; live_fills: number; latency_ms: Record<string, number | null>
  latency_by_channel: Record<string, Record<string, number | null>>
  quoted_fills: number; stale_quotes: number; quote_src: Record<string, number>
  slip_bps: Record<string, number | null>; trades: number; unquoted_trades: number
  leader_net: number; follower_net: number; follower_fees: number; retention: number | null
  follower_mean: number | null; follower_bps: number | null; taker_share: number | null
}

export interface Reason { code: string; kind: 'descarte' | 'vigilancia' | 'aprobado' | 'aviso'; text: string }

export interface Scorecard {
  leader_id: string; address: string; label: string; origin: string; verdict: Verdict
  quality: number; reasons: Reason[]; all: TradeStats; hist: TradeStats; fwd: TradeStats
  portfolio: PortfolioStats | null; copyability: CopyStats | null; forward_start: number | null
  forward_days: number; account_value: number | null; unrealized: number | null
  n_positions: number; n_trials: number; scored_at: number; rank: number
}

export interface LeaderPosition {
  leader_id: string; symbol: string; side: 'long' | 'short'; size: number; entry: number
  leverage: number | null; liquidation_px: number | null; unrealized_pnl: number | null; observed_at: number
}

export interface PositionChange { symbol: string; window_h: number; from_size: number; to_size: number }

export interface Cohort {
  verdict: Verdict; leaders: number; trades: number; net: number; mean: number | null
  mean_bps: number | null; win_rate: number | null; since: number | null
}

export interface Board {
  asof: number; mode: string; label: string; n_trials: number; params: Record<string, number>
  leaders: Scorecard[]; positions: Record<string, LeaderPosition[]>; positions_at: Record<string, number>
  changes: Record<string, PositionChange[]>; cohorts: Record<string, Cohort>
  weights: { leader_id: string; quality: number }[]; errors: string[]
}

export interface LeadersPayload {
  type: 'leaders'; mode: string; label: string; now: number; board_asof: number | null
  age_s: number | null; stale: boolean; board: Board | null; signals: Record<string, AgentReport>
}
