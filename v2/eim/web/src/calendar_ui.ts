import { bogIso } from './tz'
/** Detalle del agente `calendar` (T36): riesgo de evento, no direccional. Lista los próximos
 *  eventos (impacto medio/alto), la ventana activa, la sorpresa y el estado de cada fuente. */

interface Ev { id: string; name: string; t_utc: number; impact: string; country: string; minutes: number; source: string }
interface Recent extends Ev { actual: number | null; previous: number | null; revised: number | null; unit: string }
interface Src { present: boolean; age_h?: number; fresh?: boolean; known_until?: number }
interface Surprise { event: string; actual: number | null; forecast: number | null; z: number | null; note: string }
interface Metrics {
  upcoming?: Ev[]; recent?: Recent[]; window?: string | null; window_event?: Ev | null
  blackout?: boolean; blackout_reason?: string; surprise?: Surprise | null
  sources?: Record<string, Src>; source?: string
}

const esc = (s: unknown): string => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
const utc = (t: number): string => bogIso(t).slice(5, 16).replace('T', ' ')
const IMP: Record<string, string> = { alto: 'Alto', medio: 'Medio', bajo: 'Bajo' }
const SRC: Record<string, string> = { fed_fomc: 'Fed (FOMC)', bls: 'BLS', bea: 'BEA' }

function dur(min: number): string {
  const m = Math.abs(min), d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60)
  const txt = d ? `${d} d ${h} h` : h ? `${h} h ${m % 60} min` : `${m} min`
  return min >= 0 ? `en ${txt}` : `hace ${txt}`
}
const num = (v: number | null): string => (v === null ? 'n/d' : String(Math.round(v * 1000) / 1000))

export function calendarDetail(m: Metrics): string {
  const row = (e: Ev, extra = ''): string =>
    `<tr><td class="num">${utc(e.t_utc)}</td><td><span class="imp" data-i="${esc(e.impact)}">${esc(IMP[e.impact] ?? e.impact)}</span></td>` +
    `<td title="${esc(e.source)}">${esc(e.name)} <span class="muted">${esc(e.country)}</span></td>` +
    `<td class="muted">${dur(e.minutes)}${extra}</td></tr>`
  const up = (m.upcoming ?? []).map((e) => row(e)).join('')
  const rec = (m.recent ?? []).map((e) => row(e, e.actual === null ? ''
    : ` · real ${num(e.actual)} (ant. ${num(e.previous)}${e.revised === null ? '' : `, rev. ${num(e.revised)}`}) ${esc(e.unit)}`)).join('')
  const win = m.blackout ? `<p class="alert" role="alert">${esc(m.blackout_reason ?? '')}</p>`
    : m.window && m.window_event ? `<p>Ventana ${esc(m.window)}-evento: ${esc(m.window_event.name)}</p>` : ''
  const s = m.surprise
  const sur = s ? `<p class="muted">Sorpresa ${esc(s.event)}: ${s.z === null ? 'n/d' : `z ${num(s.z)}`} — ${esc(s.note)}</p>` : ''
  const srcs = Object.entries(m.sources ?? {}).map(([k, v]) => {
    const st = !v.present ? 'sin datos' : v.fresh ? `hace ${v.age_h} h` : `obsoleta (${v.age_h} h)`
    return `<span class="tf" data-ok="${v.present && v.fresh ? 1 : 0}" title="${v.known_until ? `conocido hasta ${utc(v.known_until)} COT` : ''}">${esc(SRC[k] ?? k)} · ${esc(st)}</span>`
  }).join('')
  return `<div class="cal">${win}<h4>Próximos eventos (COT)</h4>` +
    (up ? `<table class="metrics evt-t">${up}</table>` : '<p class="muted">Sin eventos de impacto medio/alto en los próximos 7 días.</p>') +
    (rec ? `<h4>Últimas 24 h</h4><table class="metrics evt-t">${rec}</table>` : '') + sur +
    `<p class="tfs">${srcs}</p><p class="muted">Consenso no disponible (fuentes oficiales gratuitas). Sin sesgo direccional.</p></div>`
}
