/** Contrato de `GET /v2/bots` (T60): el escuadrón de bots externos, solo lectura. */
export type SquadState = 'vota' | 'informa' | 'rechazado' | 'deshabilitado_seguridad' | 'cuarentena' | 'sin_puntuar'

export interface SquadDim { estado: string; criterios?: Record<string, { ok: boolean | null; detalle: string }>; [k: string]: unknown }

export interface SquadBot {
  key: string
  bot_id: string
  name: string
  strategy: string
  class: string | null
  lane: boolean
  stance: number
  confidence: number | null
  signal_status: string
  asof: number
  evidence: string[]
  state: SquadState
  votes: boolean
  weight: number
  publicable: boolean
  modulates: boolean
  version: string
  dimensions: Record<'rendimiento' | 'evidencia' | 'seguridad' | 'operativa', SquadDim> | null
  reasons: string[]
  coverage: number | null
}

export interface SquadSupport { up: number; down: number; flat: number; total: number }

export interface SquadPayload {
  symbol: string
  timeframe: string
  mode: string
  label: string
  bots: SquadBot[]
  disagreement: number | null
  support: SquadSupport
  scored_symbol: string | null
  scored_asof: number | null
  channels: { vote: boolean; confidence: boolean; second_opinion: boolean }
  quarantine: Record<string, { reason: string; since: number }>
}
