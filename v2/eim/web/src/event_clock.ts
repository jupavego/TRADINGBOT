/**
 * Calendario en la barra superior (T44): próximo evento de alto impacto con cuenta atrás.
 * Datos: último reporte del agente `calendar` (no direccional). Estados: normal, ventana de
 * evento (el tamaño se reduce ×0,5 y la confianza de la síntesis ×0,75) y blackout (sin
 * entradas nuevas: lo veta el motor de riesgo, T29). Clic → detalle del calendario en el río.
 */
import { esc } from './panels'
import { openAgent } from './river'
import type { AgentReport } from './types'

interface Ev { name: string; t_utc: number; impact: string; country: string; source?: string }
interface CalMetrics {
  next_high_impact?: Ev | null; window?: string | null; window_event?: Ev | null
  blackout?: boolean; blackout_reason?: string
}

let rep: AgentReport | null = null
let timer: number | undefined

const pad = (n: number): string => String(n).padStart(2, '0')
const utc = (t: number): string => new Date(t).toISOString().slice(5, 16).replace('T', ' ')

/** Cuenta atrás legible: «2 d 03 h 10 min» lejos, «hh:mm:ss» en las últimas 24 h. */
export function countdown(ms: number): string {
  const s = Math.max(0, Math.floor(Math.abs(ms) / 1000))
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60), sec = s % 60
  const txt = d ? `${d} d ${pad(h)} h ${pad(m)} min` : `${pad(h)}:${pad(m)}:${pad(sec)}`
  return ms >= 0 ? `en ${txt}` : `hace ${txt}`
}

function paint(el: HTMLElement): void {
  if (!rep || rep.status === 'no_data') {
    el.dataset.state = 'off'
    el.innerHTML = '<i>📅</i><span>Calendario sin datos</span>'
    el.title = rep?.evidence[0] ?? 'El agente de calendario aún no ha corrido: riesgo de evento desconocido.'
    return
  }
  const m = rep.metrics as CalMetrics
  const now = Date.now()
  const nx = m.next_high_impact ?? null
  const we = m.window_event ?? null
  if (m.blackout) {
    el.dataset.state = 'blackout'
    const e = we ?? nx
    el.innerHTML = `<i>⛔</i><span>Ventana de evento${e ? ` · ${esc(e.name)} ${countdown(e.t_utc - now)}` : ''}</span><b>sin entradas nuevas</b>`
    el.title = `${m.blackout_reason ?? ''}. El motor de riesgo veta entradas nuevas y la confianza de la síntesis se reduce.`
  } else if (m.window && we) {
    el.dataset.state = 'window'
    el.innerHTML = `<i>⚠</i><span>Ventana ${esc(m.window)}-evento · ${esc(we.name)} ${countdown(we.t_utc - now)}</span><b>tamaño ×0,5</b>`
    el.title = `Impacto ${we.impact}: volatilidad esperada. El riesgo por operación baja a la mitad y la confianza de la síntesis se reduce.`
  } else if (nx) {
    el.dataset.state = nx.t_utc - now < 3600_000 ? 'soon' : 'ok'
    el.innerHTML = `<i>📅</i><span>Próximo: ${esc(nx.name)} <small>${esc(nx.country)} · ${esc(nx.impact)}</small></span>` +
      `<b class="cd">${countdown(nx.t_utc - now)}</b>`
    el.title = `${nx.name} — ${utc(nx.t_utc)} UTC${nx.source ? ` · fuente ${nx.source}` : ''}. Clic: ver el calendario.`
  } else {
    el.dataset.state = 'ok'
    el.innerHTML = '<i>📅</i><span>Sin eventos de alto impacto en 7 días</span>'
    el.title = rep.evidence[0] ?? ''
  }
  if (rep.status === 'degraded') {
    el.dataset.degraded = '1'
    el.title += ` · Calendario degradado: ${rep.warnings.join(' · ')}`
  } else delete el.dataset.degraded
}

/** Fija el último reporte de `calendar` y refresca la cuenta atrás cada segundo. */
export function setCalendarClock(el: HTMLElement, r: AgentReport | undefined): void {
  rep = r ?? null
  el.hidden = false
  paint(el)
  if (timer === undefined) timer = window.setInterval(() => paint(el), 1000)
  el.onclick = () => openAgent('calendar')
}
