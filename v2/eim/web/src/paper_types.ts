/** Contratos de `/v2/paper*` (bróker simulado, T47). Todo es SIMULADO. */

export interface Judgement { weight: number; state: string; state_label: string; m: number; se: number | null; n: number }

interface Slot {
  id: string; strategy: string; sid: string; timeframe: string; family: string; side: number; kind: string; t: number
  qty: number; sl: number; tp: number; leverage: number; margin: number; weight: number
  risk_usd: number; origin: string; why: string[]
}
export interface Position extends Slot {
  entry: number; mark: number; fill_t: number; expire_t: number; liq: number
  cost_usd: number; upnl: number; roe: number | null; funding_assumed: boolean
}
export interface Order extends Slot { price: number; expire_t: number | null }

export interface ProfileView {
  id: string; name: string; description: string; params: Record<string, unknown>
  initial: number; balance: number; equity: number; upnl: number; realized: number; return_pct: number
  margin_used: number; reserved: number; available: number
  n_closed: number; win_rate: number | null; pf: number | null; avg_r: number | null
  best: number | null; worst: number | null; fees: number; funding: number; slip: number
  max_dd_pct: number; positions: Position[]; orders: Order[]; curve: [number, number][]
  by_strategy: Record<string, { n: number; pnl: number; wins: number }>
  weights: Record<string, Judgement>; events_n: number
}

export interface StrategyRow {
  id: string; base: string; timeframe: string; name: string; family: string; description: string
  n: number; open: number; pending: number; cancelled: number; rejected: number
  fill_rate: number | null; win_rate: number | null; mean_r: number | null; median_r: number | null
  sum_r: number; pf: number | null; max_dd_r: number; last10_r: number | null
  mfe_r: number | null; mae_r: number | null; hold_h: number | null
  p: number | null; p_holm: number | null; vs_control: number | null
  by_side: Record<string, { n: number; mean_r: number }>
  by_regime: Record<string, { n: number; mean_r: number }>
  by_reason: Record<string, number>; by_cause: Record<string, number>
  by_context: Record<string, { n: number; mean_r: number; state: string }>; curve: [number, number][]
  judgement: Judgement; origin_live: number
}

interface BalanceHalf { n: number; usd: number; avg_usd: number | null; avg_r: number | null; by_reason: Record<string, number> }
export interface BalanceSummary {
  n: number; wins: BalanceHalf; losses: BalanceHalf; win_rate: number | null; net: number; pf: number | null
  payoff: number | null; breakeven: number | null; expectancy_usd: number | null; expectancy_r: number | null
  costs: number; cost_flips: number; causes: Record<string, number>; long_wr: { n: number; win_rate: number | null }; short_wr: { n: number; win_rate: number | null }
}
export interface BalanceWindow {
  label: string; since: number | null; all: BalanceSummary; profiles: Record<string, BalanceSummary>
  timeframes: Record<string, BalanceSummary>
  feedback: { kind: 'funciono' | 'no_funciono' | 'mejorar'; text: string }[]
}

export interface Insight { tone: 'good' | 'bad' | 'warn' | 'info'; text: string }

export interface Job { state: string; symbol: string; tf: string; done: number; total: number; saved: number; error: string; started: number | null; finished: number | null }

export interface PaperSummary {
  mode: string; symbol: string; timeframe: string; path_tf: string; now: number; mark: number | null
  timeframes: string[]; causes: Record<string, string>
  tf_stats: { timeframe: string; n: number; win_rate: number; mean_r: number; sum_r: number }[]
  coverage: {
    from: number | null; to: number | null; contexts: number; origins: Record<string, number>; ideas: number; simulated: number
    timeframes: Record<string, { contexts: number; from: number | null; to: number | null; origins: Record<string, number> }>
  }
  sources: { candles: string | null; funding: string; funding_last: number | null; costs: string }
  families: Record<string, string>; profiles: ProfileView[]; strategies: StrategyRow[]
  family_stats: { family: string; n: number; sum_r: number; mean_r: number | null; strategies: number }[]
  insights: Insight[]; job: Job; live: { last_tick: number | null; started: number | null; error: string }
  balance: Record<string, BalanceWindow>
}

export interface PaperTrade {
  id: string; profile: string; strategy: string; sid: string; timeframe: string; cause: string | null
  family: string; side: number; kind: string
  t: number; fill_t: number; exit_t: number; fill: number; exit: number; sl: number; tp: number
  qty: number; notional: number; leverage: number; margin: number; reason: string
  pnl: number; r: number | null; roe: number | null; fees: number; slip: number; funding: number
  funding_assumed: boolean; weight: number; origin: string; regime: string | null; why: string[]
}

export interface PaperEvent {
  t: number; cat: string; profile: string; strategy: string; sid: string; timeframe: string; family: string; idea: string
  cause?: string | null; context?: string
  side: number; kind: string; text: string; origin: string
  price?: number; qty?: number; leverage?: number; margin?: number; sl?: number; tp?: number
  weight?: number; risk_usd?: number; pnl?: number; r?: number | null; equity?: number; liq?: number
  m?: number; n?: number; why?: string[]
}

export interface ShadowIdea {
  id: string; strategy: string; sid: string; timeframe: string; cause: string | null; t: number; side: number; kind: string; entry: number; sl: number; tp: number
  rr: number; conf: number; why: string[]; status: string; reason: string; fill_t: number | null
  fill: number | null; exit_t: number | null; exit: number | null; r: number | null
  mfe_r: number; mae_r: number; origin: string; regime: string | null
}
