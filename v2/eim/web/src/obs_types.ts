/** Tipos, estados y peticiones del Observatorio (T75). Todo sale de `/v2/obs/*` (solo lectura). */
import { base } from './api'

export type ObsState = 'ok' | 'degradado' | 'error' | 'obsoleto' | 'pausado' | 'sin_datos' | 'planeado'

export interface ObsComp {
  id: string; layer: string; stage: string; kind: string; process: string; version: string | null
  cadence: string; cadence_s: number | null; consumes: { source: string; artifact: string }[]
  produces: string[]; built: 'construido' | 'planeado'; task: string; title_es: string; explain_es: string
  last_event_ms: number | null; last_status: string | null; n_events: number; age_s: number | null
  stale_after_s: number | null; no_data: boolean
}
export interface ObsEdge { source: string; target: string; artifact: string }
export interface ObsGraph {
  edges: ObsEdge[]; stages: string[]; stage_titles_es: Record<string, string>
  stage_explain_es: Record<string, string>; glossary: Record<string, string>
  observed: { source: string; target: string; n: number; last_ms: number }[]
  deviations: { undeclared: { source: string; target: string }[]; unseen: { source: string; target: string }[] }
  mode: string | null; last_event_age_s: number | null; index_lag_s: number | null; asof: number
}
export interface ObsHealth { ok: boolean; problems: string[]; index_lag_s: number | null; last_event_age_s: number | null }
export interface ObsEvent {
  event_id: string; ts_utc: number; component_id: string; kind: string; status: string
  run_id: string; parent_run_id: string | null; trace_id: string | null; duration_ms: number | null
  source: string | null; coverage: number | null; detail: Record<string, unknown>
  inputs: { type: string; id: string }[]; outputs: { type: string; id: string }[]
}
export interface ObsData {
  comps: ObsComp[]; graph: ObsGraph; health: ObsHealth | null
  paused: Set<string>; recent: Map<string, ObsEvent[]>; failed: boolean
}

export const STATE_LABEL: Record<ObsState, string> = {
  ok: 'Al día', degradado: 'Degradado', error: 'Error', obsoleto: 'Dato viejo',
  pausado: 'Pausado', sin_datos: 'Sin datos', planeado: 'Planeado',
}
/** Forma + icono además del color: el color nunca es la única señal. */
export const STATE_ICON: Record<ObsState, string> = {
  ok: '✔', degradado: '▲', error: '✖', obsoleto: '◷', pausado: '❚❚', sin_datos: '?', planeado: '…',
}
export const STATE_ORDER: ObsState[] = ['error', 'degradado', 'obsoleto', 'sin_datos', 'pausado', 'ok', 'planeado']

export const esc = (s: unknown): string => String(s ?? '').replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`)

/** Estado de un componente, sin suponerlo sano: sin telemetría reciente = «sin datos». */
export function stateOf(c: ObsComp, d: { failed: boolean; paused: Set<string> }): ObsState {
  if (c.built === 'planeado') return 'planeado'
  if (d.failed || c.n_events === 0 || c.last_event_ms === null) return 'sin_datos'
  if (d.paused.has(c.id)) return 'pausado'
  if (c.no_data) return 'obsoleto'
  if (c.last_status === 'error') return 'error'
  if (c.last_status === 'degraded') return 'degradado'
  if (c.last_status === 'no_data') return 'sin_datos'
  return 'ok'            // `rejected` (veto) no es un fallo
}

export function ago(ms: number | null | undefined, now = Date.now()): string {
  if (ms === null || ms === undefined) return 'nunca'
  const s = Math.max(0, Math.round((now - ms) / 1000))
  if (s < 90) return `hace ${s} s`
  if (s < 5400) return `hace ${Math.round(s / 60)} min`
  if (s < 172800) return `hace ${Math.round(s / 3600)} h`
  return `hace ${Math.round(s / 86400)} d`
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${base()}/v2/obs/${path}`, { signal })
  if (!r.ok) throw new Error(`${path}: ${r.status}`)
  return r.json() as Promise<T>
}
export const getObs = get

/** Carga todo; si el observatorio falla devuelve `failed: true` y los estados caen a «sin datos». */
export async function loadObs(signal?: AbortSignal): Promise<ObsData | null> {
  try {
    const [c, graph, health, hb] = await Promise.all([
      get<{ items: ObsComp[] }>('components', signal), get<ObsGraph>('graph', signal),
      get<ObsHealth>('health', signal).catch(() => null),
      get<{ items: ObsEvent[] }>('events?kind=heartbeat&limit=300', signal).catch(() => ({ items: [] as ObsEvent[] }))])
    const seen = new Set<string>(), paused = new Set<string>()
    for (const e of hb.items) {           // más reciente primero
      if (seen.has(e.component_id)) continue
      seen.add(e.component_id)
      if (['pausado', 'paused'].includes(String(e.detail?.state))) paused.add(e.component_id)
    }
    const lag = graph.index_lag_s
    const failed = health !== null && !health.ok && lag !== null && lag > 120
    return { comps: c.items, graph, health, paused, recent: new Map(), failed }
  } catch (e) {
    if ((e as Error).name === 'AbortError') return null
    return { comps: [], graph: null as unknown as ObsGraph, health: null, paused: new Set(), recent: new Map(), failed: true }
  }
}
