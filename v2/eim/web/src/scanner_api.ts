/** Tipos y peticiones de la pestaña «Escáner» (T94; ranking y multiplicidad de T95). Solo lectura:
 * nada de POST. Modo ANÁLISIS. */
import { base } from './api'

export type MarketState = 'abierto' | 'cerrado' | 'sin_calendario'

export interface Head {
  mode: 'ANALISIS'; available: boolean; status_label: string; notice: string
  generated_at?: number; reason?: string
}

export interface UniverseRow {
  instrument_id: string; symbol: string; label: string; asset_class: string; market: string
  state: MarketState; rank: number; score: number | null; quality: number | null
  last_t: number | null; deep: boolean; n_bars: number | null; opportunity_id: string | null
}
export interface MarketRow { market: string; asset_class: string; n: number; abierto: number; cerrado: number; sin_calendario: number }
export interface DeepSummary { run_id: string; asof: number; n_shortlist: number; n_opportunities: number; reasons: Record<string, number> }

export interface UniversePayload extends Head {
  run_id?: string; asof?: number; timeframe?: string; exclusions?: Record<string, number>
  notes?: Record<string, number>; n_scored?: number; markets?: MarketRow[]; rows?: UniverseRow[]
  deep?: DeepSummary | null
}

export interface AgentVote {
  agent_id: string; version: string; status: 'ok' | 'degraded' | 'no_data'; bias: number
  confidence: number; votes: boolean; warnings: string[]; eligibility: string
}
export interface ScenarioEnd { p: number; median_end: number; band_end: [number, number]; invalidation: number | null }
export interface ForecastBrief {
  engine: string; horizon_bars: number; label: string; warnings: string[]
  scenarios: Record<'bull' | 'neutral' | 'bear', ScenarioEnd>
}
export interface Opportunity {
  opportunity_id: string; version: string; status: 'candidata_no_validada'; mode: 'ANALISIS'
  run_id: string; instrument_id: string; symbol: string; asset_class: string; market: string
  timeframe: string; side: 'largo' | 'corto'; asof: number; horizon_bars: number; horizon_ms: number
  valid_until: number; input_hash: string; source: string
  input_ref: { store: string; symbol: string; timeframe: string; n_bars: number; cut: number; first_t: number; last_t: number }
  coverage: { n_bars?: number; span_days?: number; volume?: string; fields?: string[] }
  agents: AgentVote[]
  synthesis: { bias: number; confidence: number; agreement: number; contributions: Record<string, number> }
  forecast: ForecastBrief
  scores: { signal_quality: number; viability: number; risk_cost: number; components: Record<string, number | null>; notes: string[] }
  versions: Record<string, string>; warnings: string[]
}
export interface Multiplicity {
  attempt_key: string; n_family: number; n_obs: number; n_matured: number; p_raw: number | null
  p_holm: number; q_bh: number; dsr: number | null; verdict: string; validation: string
}
export interface Normalized {
  sigma_h: number | null; gross: number | null; cost: number | null; net: number | null
  edge_sigma: number | null; edge_r: number | null; r_source: string; uncertainty_sigma: number | null
  scores: Record<'quality' | 'viability' | 'risk' | 'edge', number | null>; comparable: boolean; notes: string[]
}
export interface RankRow {
  opportunity_id: string; instrument_id: string; symbol: string; side: 'largo' | 'corto'
  priority: number | null; position: number | null; above_threshold: boolean
  cluster_id: string | null; representative: boolean; normalized: Normalized; multiplicity: Multiplicity
}
export interface ClusterMember { opportunity_id: string; instrument_id: string; symbol: string; side: 'largo' | 'corto'; rho_to_rep: number | null; link: string }
export interface Cluster {
  cluster_id: string; representative: string; members: ClusterMember[]
  exposure: { n: number; largo: number; corto: number; same_direction: number; hedging: number; mean_abs_rho: number; effective_bets: number }
}
export interface Threshold {
  status: 'vigente' | 'desactualizado' | 'sin_placebo'; value: number | null; reason: string
  replicas?: number | null; alpha?: number | null; fdr_estimate?: number | null
  false_per_pass?: number | null; p_global?: number | null; computed_at?: string | null
}
export interface Ranking {
  available: boolean; error?: string; reason?: string
  weights?: { values: Record<string, number>; calibrated: boolean; source: string; fingerprint: string }
  threshold?: Threshold
  family?: { prior: number; prior_source: string; scanner: number; total: number; alpha: number; min_obs: number; observations: number; matured: number }
  n_comparable?: number; n_above?: number; n_groups?: number; rows?: RankRow[]; clusters?: Cluster[]
}
export interface ShadowRow { opportunity_id: string; instrument_id: string; symbol: string; reason: string }
export interface OpportunitiesPayload extends Head { deep?: DeepSummary | null; opportunities: Opportunity[]; ranking?: Ranking; shadow?: ShadowRow[] }

/* T102: salud multiactivo, despliegue gradual y recorrido de una candidata. */
export type HealthState = 'ok' | 'degradado' | 'error' | 'obsoleto' | 'sin_datos' | 'pausado' | 'planeado'
export interface HealthClass {
  asset_class: string; label: string; plan: string; task: string; note: string; state: HealthState; alerting: boolean
  n_scored: number; n_excluded: number | null; coverage: number | null; exclusions: Record<string, number>
  quality_mean: number | null; quality_incomplete: number; stale_rows: number
  markets: { abierto: number; cerrado: number; sin_calendario: number }
  candidates: number; above_threshold: number; reasons: string[]
}
export interface HealthProvider {
  name: string; used: boolean; classes: string[]; level: number; license: string; delay_ms: number | null
  rate_limit_per_min: number | null; usage_share: number | null; usage_note: string; errors: number; state: HealthState
}
export interface RolloutUnit { kind: 'class' | 'agent'; id: string; level: string; active: boolean; reason: string; next: string[] }
export interface HealthPayload {
  mode: 'ANALISIS'; notice: string; overall: HealthState; generated_at: number; checked_at?: number | null; note?: string
  view: { state: HealthState; age_h: number | null; asof: number | null; timeframe: string }
  watching: { classes: string[]; n_instruments: number }
  classes: HealthClass[]; providers: HealthProvider[]; blind_spots: string[]
  scanner: {
    state: HealthState; reasons: string[]; failed_jobs: number
    budget: { ms_per_instrument: number | null; budget_ms: number; within_budget: boolean | null; deep_ms_total: number; deep_ms_per_instrument: number; max_procs: number }
    ranking: { available: boolean; threshold_status: string | null; n_above: number | null; family_total: number | null; matured: number | null }
  }
  alerts_active?: Record<string, number> | null
  rollout?: { units: Record<string, RolloutUnit>; levels: string[] } | null
  observability?: { events: number; build_ms?: number; emit_ms?: number; within?: boolean } | null
}
export interface TraceStep { key: string; title: string; status: string; summary: string; detail: Record<string, unknown> }
export interface CandidateTrace extends Head { trace_id: string; instrument_id: string; symbol: string; asset_class: string; timeframe: string; steps: TraceStep[] }

export interface RanAgent { agent_id: string; version: string; status: string; bias: number; confidence: number; warnings: string[]; eligibility: string }
export interface DeepDetail {
  instrument_id: string; symbol: string; timeframe: string; asof: number; input_hash: string
  coverage: { n_bars: number; span_days: number; volume: string; taker_flow: boolean; fields: string[] }
  ran: RanAgent[]; skipped: { agent_id: string; version: string; reason: string }[]
  synthesis: { bias: number; confidence: number; agreement: number; thesis: string } | null
  forecast: ForecastBrief | null; reason: string; warnings: string[]; elapsed_ms: number
  state: MarketState; opportunity_id: string | null
}
export interface InstrumentPayload extends Head {
  row: UniverseRow | null; deep: DeepDetail | null; opportunity: Opportunity | null; note: string | null
  rank?: RankRow | null
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${base()}${path}`, { signal })
  if (!(r.headers.get('content-type') ?? '').includes('json')) throw new Error('la API no respondió (¿interfaz sin reiniciar?)')
  const body = await r.json().catch(() => ({ detail: r.statusText }))
  if (!r.ok) throw new Error(String((body as { detail?: string }).detail ?? r.statusText))
  return body as T
}

export const fetchUniverse = (signal?: AbortSignal): Promise<UniversePayload> => get('/v2/scanner/universe', signal)
export const fetchOpportunities = (signal?: AbortSignal): Promise<OpportunitiesPayload> => get('/v2/scanner/opportunities', signal)
export const fetchInstrument = (id: string, signal?: AbortSignal): Promise<InstrumentPayload> =>
  get(`/v2/scanner/instrument/${encodeURIComponent(id)}`, signal)
export const fetchHealth = (signal?: AbortSignal): Promise<HealthPayload> => get('/v2/scanner/health', signal)
export const fetchTrace = (id: string, signal?: AbortSignal): Promise<CandidateTrace> =>
  get(`/v2/scanner/trace/${encodeURIComponent(id)}`, signal)
