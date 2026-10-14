import { avatar } from './avatars'
import { calendarDetail, calendarVerdict } from './calendar_ui'
import { disagreeing } from './synth'
import { rememberOpenFamilies, technicalDetail } from './technical_ui'
import type { AgentInfo, AgentReport, Synthesis } from './types'

const LABEL: Record<string, string> = {
  structure: 'Estructura', vwap: 'VWAP', price_action: 'Price action', elliott: 'Elliott',
  ema: 'EMA / FRM', liquidations: 'Liquidaciones', seasonality: 'Estacionalidad', context: 'Contexto',
  derivatives: 'Derivados', levels: 'Niveles', microstructure: 'Microestructura', plan: 'Plan',
  regime: 'Régimen', technical: 'Técnico', calendar: 'Calendario',
}
export const agentName = (id: string): string => LABEL[id] ?? id

const STATUS: Record<string, string> = {
  ok: 'OK', degraded: 'Degradado', no_data: 'Sin datos', sin_ejecutar: 'Sin ejecutar',
}

export const esc = (s: unknown): string =>
  String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

const sgn = (n: number): string => (n > 0 ? '+' : '') + n.toFixed(2)

/** Barra −1..+1 con el origen al centro; verde si sube, rojo si baja. */
function biasBar(b: number): string {
  const pct = Math.min(1, Math.abs(b)) * 50
  const side = b >= 0 ? 'left:50%;background:var(--up)' : 'right:50%;background:var(--down)'
  return `<span class="bar" role="img" aria-label="sesgo ${sgn(b)}">` +
    `<i style="${side};width:${pct}%"></i></span>`
}

const fmtMetric = (v: unknown): string =>
  typeof v === 'number' ? String(Math.round(v * 1e4) / 1e4)
    : typeof v === 'object' && v !== null ? JSON.stringify(v).slice(0, 120) : String(v)

function metricRows(m: Record<string, unknown>): string {
  const rows = Object.entries(m).slice(0, 12)
    .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(fmtMetric(v))}</td></tr>`).join('')
  return rows ? `<table class="metrics">${rows}</table>` : ''
}

const verdict = (b: number): string => {
  const a = Math.abs(b)
  if (a < 0.1) return 'Neutral'
  const f = a < 0.35 ? 'leve' : a < 0.65 ? 'moderado' : 'fuerte'
  return `${b > 0 ? 'Alcista' : 'Bajista'} ${f}`
}
const tone = (b: number): string => (b > 0.1 ? 'up' : b < -0.1 ? 'down' : 'flat')

/** Velocímetro semicircular −1..+1 (rojo → neutro → verde) con aguja. */
function gauge(b: number): string {
  const th = Math.PI - ((Math.max(-1, Math.min(1, b)) + 1) / 2) * Math.PI
  const x = 100 + 68 * Math.cos(th), y = 100 - 68 * Math.sin(th)
  return `<svg class="gauge" viewBox="0 0 200 118" role="img" aria-label="sesgo combinado ${sgn(b)}">` +
    '<defs><linearGradient id="gg"><stop offset="0" stop-color="var(--down)"/>' +
    '<stop offset=".5" stop-color="var(--grid)"/><stop offset="1" stop-color="var(--up)"/></linearGradient></defs>' +
    '<path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="url(#gg)" stroke-width="14" stroke-linecap="round"/>' +
    `<line x1="100" y1="100" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="var(--text)" stroke-width="3" stroke-linecap="round"/>` +
    '<circle cx="100" cy="100" r="6" fill="var(--text)"/>' +
    '<text x="20" y="116" class="gt">Bajista</text><text x="180" y="116" class="gt" text-anchor="end">Alcista</text></svg>'
}

/** Anillo de porcentaje (confianza / acuerdo). */
function ring(p: number, label: string): string {
  const c = 2 * Math.PI * 17
  return `<span class="ring" title="${esc(label)}"><svg viewBox="0 0 44 44"><circle cx="22" cy="22" r="17" class="rb"/>` +
    `<circle cx="22" cy="22" r="17" class="rf" stroke-dasharray="${(c * p).toFixed(1)} ${c.toFixed(1)}"/></svg>` +
    `<b>${Math.round(p * 100)}</b></span>`
}

function detail(r: AgentReport): string {
  if (r.agent_id === 'technical') return technicalDetail(r.metrics)
  if (r.agent_id === 'calendar') return calendarDetail(r.metrics)
  return metricRows(r.metrics)
}

function tile(r: AgentReport | null, info: AgentInfo, open: boolean): string {
  const status = r?.status ?? info.status
  const chip = `<span class="chip" data-s="${esc(status)}">${esc(STATUS[status] ?? status)}</span>`
  const id = esc(info.id)
  if (!r || r.status === 'no_data') {
    const why = r?.warnings[0] ?? 'Aún sin reporte; se actualiza al cerrar la próxima vela.'
    return `<details class="tile idle" data-id="${id}" data-t="flat"><summary>${avatar(info.id)}<span class="aname">${esc(agentName(info.id))}</span>${chip}</summary>` +
      `<p class="muted">${esc(why)}</p></details>`
  }
  const mix = Math.round(Math.min(1, Math.abs(r.bias)) * 38)
  const tint = tone(r.bias) === 'flat' ? 'var(--panel)'
    : `color-mix(in srgb, var(--${tone(r.bias)}) ${mix}%, var(--panel))`
  const ev = r.evidence.slice(0, 3).map((e) => `<li>${esc(e)}</li>`).join('')
  const warns = r.warnings.map((w) => `<li>${esc(w)}</li>`).join('')
  return `<details class="tile" data-id="${id}" data-t="${tone(r.bias)}" style="background:${tint}"${open ? ' open' : ''}>` +
    `<summary>${avatar(r.agent_id)}<span class="aname">${esc(agentName(r.agent_id))}</span>${chip}` +
    `<span class="big num">${sgn(r.bias)}</span>${ring(r.confidence, 'confianza')}</summary>` +
    `<div class="vd">${r.agent_id === 'calendar' ? calendarVerdict(r.metrics) : verdict(r.bias)} · confianza ${Math.round(r.confidence * 100)}%</div>` +
    `<ul class="ev">${ev || '<li class="muted">Sin evidencia.</li>'}</ul>` +
    `<div class="more">${biasBar(r.bias)}${warns ? `<ul class="warn">${warns}</ul>` : ''}` +
    `${detail(r)}<p class="muted">v${esc(r.version)} · horizonte ${r.horizon_bars} velas</p></div></details>`
}

function synthesis(reports: AgentReport[], syn: Synthesis | null): string {
  const head = '<section class="hero"><h3>Síntesis</h3>'
  if (!syn) return `${head}<p class="muted">Sin reportes todavía: se calcula al haber agentes con datos.</p></section>`
  const dis = disagreeing(reports)
  const contrib = Object.entries(syn.contributions).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .map(([id, c]) => `<tr><td>${esc(agentName(id))}</td><td>${biasBar(c)}</td><td class="num">${sgn(c)}</td></tr>`).join('')
  return head + `<div class="hero-main">${gauge(syn.bias)}<div class="hero-num" data-t="${tone(syn.bias)}">` +
    `<b class="num">${sgn(syn.bias)}</b><span>${verdict(syn.bias)}</span></div></div>` +
    `<div class="kpis"><div>${ring(syn.confidence, 'confianza')}<span>Confianza</span></div>` +
    `<div>${ring(syn.agreement, 'acuerdo')}<span>Acuerdo</span></div></div>` +
    (dis ? '<div class="alert" role="alert">⚠ Los agentes se contradicen: ' +
      `<b>${dis.up.map(agentName).join(', ')}</b> (alcista) vs <b>${dis.down.map(agentName).join(', ')}</b> (bajista)</div>` : '') +
    (syn.thesis ? `<p class="thesis">${esc(syn.thesis)}</p>` : '') +
    `<div class="hero-contrib"><h4>Contribución por agente</h4><table class="contrib">${contrib}</table></div></section>`
}

/** Pinta la columna derecha: síntesis + mosaicos. Conserva los mosaicos expandidos. */
export function renderSide(el: HTMLElement, synEl: HTMLElement, infos: AgentInfo[], reports: AgentReport[], syn: Synthesis | null): void {
  const opened = new Set(
    [...el.querySelectorAll<HTMLDetailsElement>('details.tile[open]')].map((d) => d.dataset.id),
  )
  rememberOpenFamilies(el)
  const byId = new Map(reports.map((r) => [r.agent_id, r]))
  const ids = new Set(infos.map((i) => i.id))
  const all = [...infos, ...reports.filter((r) => !ids.has(r.agent_id)).map((r): AgentInfo => ({
    id: r.agent_id, version: r.version, last_asof: r.asof, status: r.status,
    bias: r.bias, confidence: r.confidence,
  }))]
  const tiles = all.map((i) => tile(byId.get(i.id) ?? null, i, opened.has(i.id))).join('')
  synEl.innerHTML = synthesis(reports, syn)
  el.innerHTML = '<h3 class="sh">Agentes</h3>' +
    `<div class="tiles">${tiles || '<p class="muted">Sin agentes registrados.</p>'}</div>`
}

/** Última versión de cada agente a partir de reportes. */
export function latestPerAgent(reports: AgentReport[]): AgentReport[] {
  const m = new Map<string, AgentReport>()
  for (const r of reports) {
    const p = m.get(r.agent_id)
    if (!p || r.asof > p.asof) m.set(r.agent_id, r)
  }
  return [...m.values()]
}

export function renderJournal(el: HTMLElement, reports: AgentReport[]): void {
  if (!reports.length) { el.innerHTML = '<p class="muted">Sin reportes registrados todavía.</p>'; return }
  el.innerHTML = '<table class="log"><thead><tr><th>Hora (UTC)</th><th>Agente</th><th>Sesgo</th>' +
    '<th>Conf.</th><th>Estado</th><th>Evidencia</th></tr></thead><tbody>' +
    reports.map((r) => `<tr><td>${new Date(r.asof).toISOString().slice(0, 16).replace('T', ' ')}</td>` +
      `<td>${esc(agentName(r.agent_id))}</td><td class="num">${sgn(r.bias)}</td>` +
      `<td class="num">${Math.round(r.confidence * 100)}%</td>` +
      `<td><span class="chip" data-s="${esc(r.status)}">${esc(STATUS[r.status] ?? r.status)}</span></td>` +
      `<td class="muted">${esc(r.evidence[0] ?? '')}</td></tr>`).join('') + '</tbody></table>'
}
