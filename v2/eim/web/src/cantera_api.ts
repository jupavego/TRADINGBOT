/** Tipos y peticiones de la pestaña «Cantera» (T171). Solo lectura: nada de POST. */
import { base } from './api'

export type Stage = 'guarderia' | 'cantera' | 'promesa' | 'primer_equipo' | 'baja'

export interface VsReturn { id: string; net_return_pct: number | null; n?: number | null; diff_pct: number | null }
export interface VsRandom {
  twins_return_pct: number; diff_pct: number | null; d_mean_r: number | null
  d_lo: number | null; d_hi: number | null; k: number
}
export interface BuyHold {
  from_t: number; return_pct: number; r_long: number | null; r_short: number | null; basis: string
  own_by_side?: { largo: { n: number; r_sum: number }; corto: { n: number; r_sum: number } } | null
}
export interface Criterion { id: string; ok: boolean | null; motivo: string }
export interface Verdict {
  state: 'sin_muestra' | 'sin_ventaja' | 'estimable'; z: number; alpha: number; obs: number
  mintrl: number | null; remaining: number | null; days: number | null; rate_per_day?: number | null
  beyond_deadline?: boolean; deadline_days: number; motivo: string
}

export interface ProspectRow {
  id: string; agent_id: string; name: string | null; timeframe: string; band: string; unit: string
  theme: string; role: 'base' | 'candidato' | null; n_params: number; sibling: string | null
  generic: string | null; account: string | null; stage: Stage; stage_since_ms: number
  exit: { reason: string; at_ms: number; motivo: string } | null; reviews: number; criteria: Criterion[]
  net_return_pct: number | null; balance: number | null; max_drawdown_pct: number | null
  n: number; open: number; hit_rate: number | null; cost_paid_usd: number | null
  sample: { obs: number; min: number; unit: string; ok: boolean; label: string | null }
  vs: { sibling: VsReturn | null; random: VsRandom; buy_hold: BuyHold | null; generic: VsReturn | null }
  regime: { dominant: string | null; by: Record<string, { n: number; d_mean: number }> }
  r_net: { gross_r: number | null; d_raw: number | null; d_shrunk: number | null; shrink_weight: number | null; theme: string }
  early: { vol_r: number | null; max_dd_pct: number | null; dd_cap_pct: number | null; dd_used: number | null }
  verdict: Verdict
}

export interface CanteraPanel {
  source: string; accounting: string; mode: string; order: string
  coverage: { from_ms: number; to_ms: number; last_close_ms: number | null; days: number; closed: number }
  header: {
    false_promises: { mean: number; p_at_least_one: number; sims: number; m: number; q: number; reading: string }
    family_m: number; members: number; z_family: number; next_review_ms: number | null
    reviews_ms: number[]; deadline_ms: number; min_sample: number; stages: Record<Stage, number>
  }
  bands: { id: string; label: string; unit: string; count: number }[]
  agents: { agent_id: string; prospects: string[]; stages: Partial<Record<Stage, number>>
    generic: { account: string; net_return_pct: number | null; n: number | null }[] }[]
  prospects: ProspectRow[]
}

/** Ganadas frente a perdidas de un grupo de operaciones cerradas (como el balance del bróker). */
export interface CtHalf { n: number; usd: number; avg_usd: number | null; avg_r: number | null; by_reason: Record<string, number> }
export interface CtStats {
  n: number; wins: CtHalf; losses: CtHalf; win_rate: number | null; payoff: number | null
  breakeven: number | null; expectancy_r: number | null; pf: number | null; net: number; costs: number
}
export interface CtWindow {
  label: string; all: CtStats
  agents: Record<string, { n: number; wins: { n: number; usd: number }; losses: { n: number; usd: number } }>
  timeframes: Record<string, { n: number; win_rate: number | null }>
}
export interface CtAgentCurve {
  agent_id: string; accounts: number; initial: number; equity: number; return_pct: number; n: number
  curve: { t: number; equity: number; pct: number }[]
}
export interface CtBalance {
  mode: string; scope: string; rule: string; initial_per_account: number
  windows: Record<string, CtWindow>; agents: CtAgentCurve[]
}

export interface NurseryPayload {
  mode: string; enabled: boolean; reason?: string; label?: string; machine_off?: boolean
  balance?: CtBalance
  /** Espejo: foto del equipo que corre la cantera (con la cantera apagada en este equipo). */
  mirror?: { machine?: string; published_ms?: number; read_ms?: number | null; error?: string; waiting?: boolean }
  live?: { last_tick: number | null; error: string; blocked: string | null }
  prereg?: { version: string; sha256: string; alta_ms: number }
  panel?: CanteraPanel
}

export interface ProspectCard {
  mode: string; source: string; id: string; account: string; agent_id: string; agent_version: string
  name: string; role: string; theory: string | null; agent_theory: string | null; rule: string
  timeframe: string; exit_template: string; max_bars: number | null; horizon: string
  opposite_of: string | null; fingerprint: string
  variables: { name: string; source: string | null; note: string | null }[]
  params: { name: string; value: unknown; source: string | null }[]
  literature: { id: string; stance: string | null; concept: string | null; consensus: string | null }[]
  equity_curve: { t: number; equity: number }[]; initial_equity: number
  trades: { t: number; side: number; status: string; reason: string; fill_t: number | null; fill: number | null
    exit_t: number | null; exit: number | null; r: number | null; pnl_usd: number; d_r: number | null; maker: boolean }[]
  trades_total: number
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${base()}${path}`, { signal })
  if (!(r.headers.get('content-type') ?? '').includes('json')) throw new Error('la API no respondió (¿interfaz sin reiniciar?)')
  const body = await r.json().catch(() => ({ detail: r.statusText }))
  if (!r.ok) throw new Error(String((body as { detail?: string }).detail ?? r.statusText))
  return body as T
}

export const fetchNursery = (signal?: AbortSignal): Promise<NurseryPayload> => get('/v2/nursery', signal)
export const fetchProspect = (id: string, signal?: AbortSignal): Promise<ProspectCard> =>
  get(`/v2/nursery/prospect/${encodeURIComponent(id)}`, signal)
