/** Tipos escritos a mano a partir de PLAN/CONTRATOS.md (solo lo que usa la UI base). */

export interface Candle { t: number; o: number; h: number; l: number; c: number; v: number }

export interface Snapshot {
  symbol: string
  timeframe: string
  candles: Candle[]
  forming: Candle | null
  asof: number
  sources: Record<string, string>
  coverage: Record<string, [number, number]>
}

export type OverlayKind = 'zone' | 'level' | 'channel' | 'range' | 'trade_plan' | 'marker'

export interface Overlay {
  id: string
  agent_id: string
  kind: OverlayKind
  t_from: number
  t_to: number | null
  geometry: Record<string, unknown>
  label: string
  confidence: number
  evidence: string[]
  valid_until: number | null
}

export type Mode = 'ANALISIS' | 'SIMULADO' | 'TESTNET' | 'REAL'

export type StreamState = 'connecting' | 'up' | 'down'

export type StreamMsg =
  | { type: 'status'; state: StreamState; detail?: string; source?: string }
  | { type: 'tick'; symbol: string; timeframe: string; candle: Candle; closed: boolean; source: string }
  | { type: 'reports'; symbol: string; timeframe: string; asof: number; reports: unknown[]; overlays: Overlay[] }
  | { type: 'error'; detail: string }
  | { type: 'forecast'; forecast: ForecastSet }
  | { type: 'forecast_error'; detail: string }
  | { type: 'heartbeat'; t: number }

export type AgentStatus = 'ok' | 'degraded' | 'no_data'

export interface AgentReport {
  agent_id: string
  version: string
  asof: number
  bias: number
  confidence: number
  horizon_bars: number
  evidence: string[]
  metrics: Record<string, unknown>
  warnings: string[]
  overlays: Overlay[]
  status: AgentStatus
}

export interface AgentInfo {
  id: string
  version: string
  last_asof: number | null
  status: AgentStatus | 'sin_ejecutar'
  bias: number | null
  confidence: number | null
}

export interface Synthesis {
  bias: number
  confidence: number
  agreement: number
  contributions: Record<string, number>
  thesis: string
  /** true mientras no exista la síntesis real (T20): calculada en el navegador. */
  simulated: boolean
}

/** Operación del libro simulado (siempre mode=SIMULADO). Tiempos en ms. */
export interface Trade {
  id: string
  plan_id: string
  side: 1 | -1
  entry_t: number
  entry: number
  sl0: number
  tp1: number
  tp2: number | null
  status: 'ABIERTA' | 'SL' | 'TP1' | 'TP2' | 'INVALIDADO' | 'EXPIRADO'
  exit_t: number | null
  exit: number | null
  r: number | null
  fees_r: number | null
  funding_r: number | null
  mode: string
  evidence: string[]
  funding_source: string
}

export interface Decision {
  asof: number
  plan_id: string | null
  action: string
  bias: number
  confidence: number
  evidence: string[]
  mode: string
}

export interface Replay {
  asof: number
  mode: string
  candles: Candle[]
  reports: AgentReport[]
  overlays: Overlay[]
  trades: Trade[]
}

export type ScenarioId = 'bull' | 'neutral' | 'bear'
export type TP = [number, number]

/** Escenario del contrato (PLAN/CONTRATOS.md). Las velas son SIMULADAS. */
export interface Scenario {
  id: ScenarioId
  probability: number
  path: TP[]
  band_low: TP[]
  band_high: TP[]
  candles: Candle[]
  invalidation: { level: number; level_low?: number; condition: string }
  narrative: string
  n_paths: number
  engine: string
}

export interface ForecastSet {
  symbol: string
  timeframe: string
  made_at: number
  horizon_bars: number
  scenarios: Scenario[]
  engine: string
  baseline_engine: string
  warnings: string[]
}
