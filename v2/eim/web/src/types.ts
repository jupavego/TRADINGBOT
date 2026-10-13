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
