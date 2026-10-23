/** Contratos de `/v2/paper*` (bróker simulado, T47). Todo es SIMULADO. */

export interface Judgement { weight: number; state: string; state_label: string; m: number; se: number | null; n: number }

/** Estado de la protección progresiva (perfil PPP) de una posición abierta. */
export interface LadderPos {
  level: number; nominal_usd: number; max_float_usd: number | null; float_usd: number; stop: number
  initial_sl: number; state: string; incident: string; elapsed_ms: number
  stop_history: { t: number; level: number; nominal: number; stop: number; max_float: number; source?: string }[]
  /** Escalones de ESTA operación (con base R cada una tiene los suyos) y origen del stop vigente. */
  first_usd?: number; step_usd?: number; stop_source?: string
  /** Neto ESTIMADO si saltara ahora el stop vigente (T112); un hueco o el deslizamiento pueden dar otro. */
  stop_est_usd?: number
  /** Cerradas: neto del stop vigente con el deslizamiento esperado. */
  protected_est_usd?: number | null
  /** T110: suelo guardado adoptado tras un reinicio · motivo del estado inconsistente. */
  recovered?: Record<string, unknown> | null; inconsistent?: string | null
}
interface Slot {
  id: string; strategy: string; sid: string; timeframe: string; family: string; side: number; kind: string; t: number
  qty: number; sl: number; tp: number | null; leverage: number; margin: number; weight: number
  risk_usd: number; origin: string; why: string[]; floor?: boolean; conf?: number; rr?: number   // floor: entró por el mínimo de abiertas
}
export interface Position extends Slot {
  entry: number; mark: number; fill_t: number; expire_t: number | null; liq: number; ladder?: LadderPos
  cost_usd: number; upnl: number; roe: number | null; funding_assumed: boolean
  /** Motivo si la marca ya atravesó la liquidación (la posición debería estar cerrada); «» si no. */
  liq_why?: string
  /** T110: «inconsistente» (el diario no deja reconstruirla) o «recuperada» (suelo guardado adoptado). */
  protection_state?: string; protection_why?: string
}
export interface Order extends Slot { price: number; expire_t: number | null }

export interface LadderStats {
  n: number; reached: { level: number; nominal: number; reached: number }[]
  closed_initial_sl: number; closed_dynamic_sl: number
  avg_max_float_usd: number | null; avg_realized_usd: number | null
  avg_gap_max_vs_realized_usd: number | null; avg_realized_vs_protected_usd: number | null
  by_max_level: Record<string, { n: number; pnl: number; pullbacks: number }>
  by_side: Record<string, { n: number; pnl: number; wins: number }>
  avg_hours: number | null; duration: Record<string, number>; long_open_positions: number
  max_consecutive_losses: number; violations: number; incidents: number; note: string
  brake: { halted: boolean; until: number | null; reason: string; consecutive_losses: number; activations: { t: number; until: number; reason: string }[] }
  /** Escalones de referencia del perfil (USDT) y cómo se definen: `r` = fracción del riesgo de cada operación. */
  first_usd?: number; step_usd?: number; basis?: string; first_r?: number; step_r?: number; brake_on?: boolean
  /** Motivos de cierre por separado (T109); `otros_motivos` debe ser 0. */
  exits?: {
    stop_inicial: number; stop_dinamico: number; liquidacion: number; salvaguarda: number
    incidencia_abierta: number; otros_motivos: number; rechazados: number
  }
  contrary_signals?: number
  /** Último movimiento del stop por la protección (abiertas y cerradas, T112). */
  last_step?: { t: number; level: number; nominal_usd: number; source: string; id: string; sid: string; open: boolean } | null
  /** Últimas violaciones de reglas: cierres fuera de regla (no ejecutados) o auditados. */
  violations_recent?: { id: string; t: number; reasons: string[]; executed: boolean }[]
}

export interface ProfileView {
  id: string; name: string; description: string; params: Record<string, unknown>
  /** balance = realizado · equity = balance + upnl · return_pct SIEMPRE sobre equity (T107). */
  initial: number; balance: number; equity: number; upnl: number; realized: number; return_pct: number
  return_base?: string
  /** Cuenta agotada: capital realizado ≤ `min_equity`; deja de abrir y no se recarga. */
  exhausted?: boolean; exhausted_t?: number | null; min_equity?: number
  /** Drawdown con su base y ventana declaradas (acotado a 100 % por construcción). */
  dd?: { pct: number; base: string; from: number | null; to: number | null }
  /** Procedencia del recuento de operaciones: origen, ventana y alcance. */
  counts?: {
    closed: number; by_origin: Record<string, number>; liquidations: number; violations: number
    from: number | null; to: number | null; scope: string
  }
  margin_used: number; reserved: number; available: number
  n_closed: number; win_rate: number | null; pf: number | null; avg_r: number | null
  best: number | null; worst: number | null; fees: number; funding: number; slip: number
  max_dd_pct: number; positions: Position[]; orders: Order[]; curve: [number, number][]
  by_strategy: Record<string, { n: number; pnl: number; wins: number }>
  weights: Record<string, Judgement>; events_n: number; ladder?: LadderStats
  /** T110: diario de la protección verificado y operaciones inconsistentes o recuperadas. */
  protection?: { verified: unknown; inconsistent: number; recovered: number }
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
  /** Frescura de la vista: con un backtest largo se entrega la última calculada mientras se rehace. */
  view?: { computed: number; stale: boolean; refreshing: boolean; error: string }
}

export interface PaperTrade {
  id: string; profile: string; strategy: string; sid: string; timeframe: string; cause: string | null
  family: string; side: number; kind: string
  t: number; fill_t: number; exit_t: number; fill: number; exit: number; sl: number; tp: number
  qty: number; notional: number; leverage: number; margin: number; reason: string
  pnl: number; r: number | null; roe: number | null; fees: number; slip: number; funding: number
  funding_assumed: boolean; weight: number; floor?: boolean; origin: string; regime: string | null; why: string[]
  ladder?: LadderPos
}

export interface PaperEvent {
  t: number; cat: string; profile: string; strategy: string; sid: string; timeframe: string; family: string; idea: string
  cause?: string | null; context?: string
  side: number; kind: string; text: string; origin: string
  price?: number; qty?: number; leverage?: number; margin?: number; sl?: number; tp?: number
  weight?: number; risk_usd?: number; pnl?: number; r?: number | null; equity?: number; liq?: number
  m?: number; n?: number; why?: string[]
  /** Motivo exacto del cierre (SL, SLD, LIQUIDACION, SALVAGUARDA…) o del cierre rechazado. */
  reason?: string
}

export interface ShadowIdea {
  id: string; strategy: string; sid: string; timeframe: string; cause: string | null; t: number; side: number; kind: string; entry: number; sl: number; tp: number
  rr: number; conf: number; why: string[]; status: string; reason: string; fill_t: number | null
  fill: number | null; exit_t: number | null; exit: number | null; r: number | null
  mfe_r: number; mae_r: number; origin: string; regime: string | null
}

/** Señales en vivo (T48c): decisión en tiempo real + estado en la sombra + qué hizo cada perfil. */
export interface ProfileAction { action: string; label: string; text: string; pnl?: number | null; r?: number | null }
export interface LiveDecision extends ShadowIdea { mark: number | null; profiles: Record<string, ProfileAction> }
export interface LiveFeed {
  mode: string; total: number; candles_total: number
  candles: { timeframe: string; t: number; signals: number }[]
  status: Record<string, number>
  profiles: Record<string, { actions: Record<string, number>; taken: number; top_reasons: [string, number][] }>
  decisions: LiveDecision[]
  live: { last_tick: number | null; started: number | null; error: string }
}
