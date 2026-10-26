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
  /** false: su última postura tiene más de 3 velas; no cuenta en discrepancia ni apoyo (T119) */
  live: boolean
}

export interface SquadSupport { up: number; down: number; flat: number; total: number }

/** De cuándo es la puntuación T59 que se muestra y cómo fue el último recálculo (T119). */
export interface ScoreFreshness {
  state: 'vigente' | 'fallida' | 'vieja' | 'sin_medicion'
  reason: string
  asof: number | null
  computed: number | null
  last_attempt: number | null
  last_ok: number | null
  stale_after_ms: number
}

/** Bot utilizable que este equipo no lanza en el ciclo (solo histórico, sin entorno, carril). */
export interface OutOfCycleBot { bot_id: string; name: string; class: string; reason: string }

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
  out_of_cycle: OutOfCycleBot[]
  quarantine: Record<string, { reason: string; since: number }>
  scorecard: ScoreFreshness | null
}
