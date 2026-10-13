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
