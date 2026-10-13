import { disagreeing, simulateSynthesis } from './synth'
import type { AgentInfo, AgentReport } from './types'

const LABEL: Record<string, string> = {
  structure: 'Estructura', vwap: 'VWAP', price_action: 'Price action', elliott: 'Elliott',
  ema: 'EMA / FRM', liquidations: 'Liquidaciones', seasonality: 'Estacionalidad', context: 'Contexto',
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

function card(r: AgentReport | null, info: AgentInfo, open: boolean): string {
  const status = r?.status ?? info.status
  const head = `<span class="aname">${esc(agentName(info.id))}</span>` +
    `<span class="chip" data-s="${esc(status)}">${esc(STATUS[status] ?? status)}</span>`
  if (!r) {
    return `<details class="card" data-id="${esc(info.id)}"><summary>${head}</summary>` +
      '<p class="muted">Aún sin reporte; se actualiza al cerrar la próxima vela.</p></details>'
  }
  const ev = r.evidence.slice(0, 3).map((e) => `<li>${esc(e)}</li>`).join('')
  const warns = r.warnings.map((w) => `<li>${esc(w)}</li>`).join('')
  return `<details class="card" data-id="${esc(r.agent_id)}"${open ? ' open' : ''}>` +
    `<summary>${head}</summary>` +
    `<div class="row">${biasBar(r.bias)}<b class="num">${sgn(r.bias)}</b>` +
    `<span class="muted">conf. ${Math.round(r.confidence * 100)}%</span></div>` +
    `<ul class="ev">${ev || '<li class="muted">Sin evidencia.</li>'}</ul>` +
    `<div class="more">${warns ? `<ul class="warn">${warns}</ul>` : ''}` +
    `${metricRows(r.metrics)}<p class="muted">v${esc(r.version)} · horizonte ${r.horizon_bars} velas</p></div>` +
    '</details>'
}

/** Pinta la columna derecha: síntesis + tarjetas. Conserva las tarjetas expandidas. */
export function renderSide(el: HTMLElement, infos: AgentInfo[], reports: AgentReport[]): void {
  const opened = new Set(
    [...el.querySelectorAll<HTMLDetailsElement>('details.card[open]')].map((d) => d.dataset.id),
  )
  const byId = new Map(reports.map((r) => [r.agent_id, r]))
  const ids = new Set(infos.map((i) => i.id))
  const all = [...infos, ...reports.filter((r) => !ids.has(r.agent_id)).map((r): AgentInfo => ({
    id: r.agent_id, version: r.version, last_asof: r.asof, status: r.status,
    bias: r.bias, confidence: r.confidence,
  }))]
  const syn = simulateSynthesis(reports)
  const dis = disagreeing(reports)
  const cards = all.map((i) => card(byId.get(i.id) ?? null, i, opened.has(i.id))).join('')
  const synBody = syn
    ? `<div class="row">${biasBar(syn.bias)}<b class="num">${sgn(syn.bias)}</b>` +
      `<span class="muted">conf. ${Math.round(syn.confidence * 100)}%</span></div>` +
      `<p class="muted">Acuerdo entre agentes: <b>${Math.round(syn.agreement * 100)}%</b></p>` +
      (dis ? '<div class="alert" role="alert">⚠ Desacuerdo: ' +
        `${dis.up.map(agentName).join(', ')} (alcista) vs ${dis.down.map(agentName).join(', ')} (bajista)</div>` : '') +
      `<table class="contrib">${Object.entries(syn.contributions)
        .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
        .map(([id, c]) => `<tr><td>${esc(agentName(id))}</td><td>${biasBar(c)}</td>` +
          `<td class="num">${sgn(c)}</td></tr>`).join('')}</table>`
    : '<p class="muted">Sin reportes todavía: se calcula al haber agentes con datos.</p>'
  el.innerHTML = '<section class="syn"><h3>Síntesis <span class="sim">simulada · hasta T20</span></h3>' +
    `${synBody}</section><h3>Agentes</h3>${cards || '<p class="muted">Sin agentes registrados.</p>'}`
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
