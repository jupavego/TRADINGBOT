/** T123: colas entre etapas — tope, política y lo descartado, siempre con su fuente y cobertura. */
import { ago, esc } from './obs_types'

export interface ObsQueueProc {
  process: string; ts_utc: number; status: string; stale: boolean; source: string | null; coverage: number | null
  occupancy: number | null; max_occupancy: number | null; dropped: number | null; held: number | null
  held_s: number | null; last_cause: string | null; last_ms: number | null; since_ms: number | null
}
export interface ObsQueue {
  id: string; component_id: string; title_es: string; why_es: string; capacity: number; unit: string
  per_key: boolean; policy: string; policy_es: string; measured: boolean; processes: ObsQueueProc[]
  no_data: boolean; no_data_reason: string | null; dropped: number | null; max_occupancy: number | null
}

const n = (x: number | null | undefined): string => (x == null ? '—' : x.toLocaleString('es-CO'))
const pct = (x: number | null): string => (x == null ? '—' : `${Math.round(x * 100)} %`)

function procHtml(q: ObsQueue, p: ObsQueueProc): string {
  const waits = p.held ? ` · el productor esperó ${n(p.held)} veces (${n(p.held_s)} s)` : ''
  const cause = p.last_cause ? ` · última causa ${ago(p.last_ms)}: ${esc(p.last_cause)}` : ''
  return `<li><b>${esc(p.process)}</b>: ${n(p.dropped)} descartados${waits} · ocupación máxima ${n(p.max_occupancy)} de ${n(q.capacity)}${cause}
    <br><small class="muted">Fuente: ${esc(p.source ?? '—')} · cobertura ${pct(p.coverage)} desde el arranque del proceso (${ago(p.since_ms)}) · informe ${ago(p.ts_utc)}${p.stale ? ' (viejo)' : ''}</small></li>`
}

export function queueHtml(q: ObsQueue): string {
  const tag = q.no_data ? 'sin datos' : q.dropped ? `${n(q.dropped)} descartados` : 'sin descartes'
  return `<li class="obs-q${q.dropped ? ' obs-q-drop' : ''}" data-queue="${esc(q.id)}"><b>${esc(q.title_es)}</b> <small>· ${tag}</small>
    <br><small class="muted">Tope ${n(q.capacity)} ${esc(q.unit)} · al llenarse ${esc(q.policy_es)}. ${esc(q.why_es)}</small>
    ${q.no_data_reason ? `<br><small class="muted">Sin cifra: ${esc(q.no_data_reason)}.</small>` : ''}
    ${q.processes.length ? `<ul class="obs-ul">${q.processes.map((p) => procHtml(q, p)).join('')}</ul>` : ''}</li>`
}

/** Resumen para la lista «Qué requiere atención»: cuántas descartan y cuántas no informan. */
export function queuesSummary(qs: ObsQueue[]): { drops: number; missing: number } {
  return { drops: qs.filter((q) => q.dropped).length, missing: qs.filter((q) => q.no_data && q.measured).length }
}
