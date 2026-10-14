import { disagreeing, PCT_NOTE, shares, upDown } from './synth'
import type { AgentReport, Synthesis } from './types'

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

const verdict = (b: number): string => {
  const a = Math.abs(b)
  if (a < 0.1) return 'Neutral'
  const f = a < 0.35 ? 'leve' : a < 0.65 ? 'moderado' : 'fuerte'
  return `${b > 0 ? 'Alcista' : 'Bajista'} ${f}`
}
const tone = (b: number): string => (b > 0.1 ? 'up' : b < -0.1 ? 'down' : 'flat')

/** Barra 0..100 % teñida según la dirección del aporte. */
const pctBar = (p: number, t: string): string =>
  `<span class="bar pbar" role="img" aria-label="${p}%"><i style="left:0;width:${p}%;background:${t === 'flat' ? 'var(--muted)' : `var(--${t})`}"></i></span>`

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

function synthesis(reports: AgentReport[], syn: Synthesis | null): string {
  const head = '<section class="hero"><h3>Síntesis</h3>'
  if (!syn) return `${head}<p class="muted">Sin reportes todavía: se calcula al haber agentes con datos.</p></section>`
  const dis = disagreeing(reports)
  const sh = shares(syn)
  const ud = upDown(syn)
  const ids = new Set(sh?.map((r) => r.id))
  const rows = [...(sh ?? []), ...Object.keys(syn.contributions).filter((id) => !ids.has(id))
    .map((id) => ({ id, dir: 0 as const, pct: 0 }))]
  const contrib = rows.map((r) => {
    const t = r.dir > 0 ? 'up' : r.dir < 0 ? 'down' : 'flat'
    const lbl = r.dir > 0 ? `▲ ${r.pct}% subida` : r.dir < 0 ? `▼ ${r.pct}% bajada` : '0% · neutral'
    return `<tr><td>${esc(agentName(r.id))}</td><td>${pctBar(r.pct, t)}</td>` +
      `<td class="num pct" data-t="${t}">${lbl}</td></tr>`
  }).join('')
  const lead = ud && (ud.up > ud.down ? 'up' : ud.down > ud.up ? 'down' : 'flat')
  return head + `<div class="hero-main">${gauge(syn.bias)}<div class="hero-num" data-t="${tone(syn.bias)}" title="${esc(PCT_NOTE)}">` +
    (ud
      ? `<b class="num pctb${lead === 'up' ? ' lead' : ''}" data-t="up" style="color:var(--up)">▲ ${ud.up}%<i>subida</i></b>` +
        `<b class="num pctb${lead === 'down' ? ' lead' : ''}" data-t="down" style="color:var(--down)">▼ ${ud.down}%<i>bajada</i></b>`
      : '<b class="num">—</b>') +
    `<span>${verdict(syn.bias)} · sesgo ${sgn(syn.bias)}</span><small class="muted">proyección estimada por los agentes</small></div></div>` +
    `<div class="kpis"><div>${ring(syn.confidence, 'confianza')}<span>Confianza</span></div>` +
    `<div>${ring(syn.agreement, 'acuerdo')}<span>Acuerdo</span></div></div>` +
    (dis ? '<div class="alert" role="alert">⚠ Los agentes se contradicen: ' +
      `<b>${dis.up.map(agentName).join(', ')}</b> (alcista) vs <b>${dis.down.map(agentName).join(', ')}</b> (bajista)</div>` : '') +
    (syn.thesis ? `<p class="thesis">${esc(syn.thesis)}</p>` : '') +
    `<div class="hero-contrib"><h4 title="${esc(PCT_NOTE)}">Aporte de cada agente a la proyección <span class="muted">(suma 100 %)</span></h4>` +
    `<table class="contrib">${contrib}</table></div></section>`
}

/** Pinta la síntesis (los agentes viven alrededor de la esfera del río). */
export function renderSynth(synEl: HTMLElement, reports: AgentReport[], syn: Synthesis | null): void {
  synEl.innerHTML = synthesis(reports, syn)
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
