import { arbDetail } from './arb_view'
import { calendarDetail } from './calendar_ui'
import { agentName, esc } from './panels'
import { disagreeing, PCT_NOTE, shares, upDown } from './synth'
import { technicalDetail } from './technical_ui'
import type { AgentReport, Synthesis } from './types'

/**
 * Contenido de los tooltips del río. La síntesis ya no tiene apartado propio: su información
 * vive aquí, compacta — el aporte de cada agente en su tooltip y el resumen global (veredicto,
 * confianza, acuerdo, tesis, contradicciones y reparto de aportes) en el de la esfera central.
 */

export const THRESH = 0.1 // |sesgo| mínimo para teñir de verde/rojo
export const CORE_ID = '__core'

const STATUS: Record<string, string> = { ok: 'OK', degraded: 'Degradado', no_data: 'Sin datos' }
const fmt = (v: unknown): string =>
  typeof v === 'number' ? String(Math.round(v * 1e4) / 1e4)
    : typeof v === 'object' && v !== null ? JSON.stringify(v).slice(0, 80) : String(v)

export const sg = (b: number): string => (b > 0 ? '+' : '') + b.toFixed(2)

/** Color de un sesgo: gris (neutro) → verde/rojo según intensidad. */
export const tint = (b: number, k = 1): string =>
  Math.abs(b) < THRESH
    ? 'var(--muted)'
    : `color-mix(in srgb, var(--${b > 0 ? 'up' : 'down'}) ${Math.round(Math.min(1, Math.abs(b) * k) * 45 + 55)}%, var(--panel))`

const verdict = (b: number): string => {
  const a = Math.abs(b)
  if (a < THRESH) return 'Neutral'
  return `${b > 0 ? 'Alcista' : 'Bajista'} ${a < 0.35 ? 'leve' : a < 0.65 ? 'moderado' : 'fuerte'}`
}

const head = (title: string): string =>
  `<div class="tip-h"><b>${esc(title)}</b><button data-close aria-label="Cerrar">×</button></div>`

/** Barra 0..100 % teñida según la dirección del aporte. */
const pbar = (p: number, dir: number): string =>
  `<span class="tbar"><i style="width:${p}%;background:${dir > 0 ? 'var(--up)' : dir < 0 ? 'var(--down)' : 'var(--muted)'}"></i></span>`

/** Aporte del agente a la proyección de la síntesis (o por qué no aporta). */
function share(id: string, syn: Synthesis | null): string {
  if (id === 'calendar' || id === 'arbitrage') return '<span class="muted">no direccional (no suma a la proyección)</span>'
  if (!syn || !(id in syn.contributions)) return '<span class="muted">fuera de la síntesis</span>'
  const s = shares(syn)?.find((x) => x.id === id)
  if (!s || !s.dir) return '<b>0 %</b> <span class="muted">· neutral</span>'
  return `<b style="color:var(--${s.dir > 0 ? 'up' : 'down'})" title="${esc(PCT_NOTE)}">${s.dir > 0 ? '▲' : '▼'} ${s.pct} % ` +
    `${s.dir > 0 ? 'subida' : 'bajada'}</b>${pbar(s.pct, s.dir)}`
}

/** Tooltip de un agente: su último reporte + su aporte a la proyección. */
export function agentTip(r: AgentReport | undefined, id: string, syn: Synthesis | null): string {
  if (!r) return `${head(agentName(id))}<p class="muted">Aún sin reporte: se ejecuta al cerrar la próxima vela.</p>`
  const dir = Math.abs(r.bias) < THRESH ? 'Neutral' : r.bias > 0 ? 'Compra' : 'Venta'
  const ev = r.evidence.slice(0, 4).map((e) => `<li>${esc(e)}</li>`).join('')
  const wn = r.warnings.map((w) => `<li>${esc(w)}</li>`).join('')
  const mt = Object.entries(r.metrics).slice(0, 6)
    .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(fmt(v))}</td></tr>`).join('')
  return head(agentName(id)) +
    `<div class="tip-k"><span class="chip" data-s="${esc(r.status)}">${esc(STATUS[r.status] ?? r.status)}</span>` +
    `<b style="color:${tint(r.bias)}">${dir} ${sg(r.bias)}</b><span class="muted">confianza ${Math.round(r.confidence * 100)}% · ${r.horizon_bars} velas</span></div>` +
    `<div class="tip-share"><span class="muted">Aporte a la proyección</span>${share(id, syn)}</div>` +
    (ev ? `<ul class="ev">${ev}</ul>` : '') + (wn ? `<ul class="warn">${wn}</ul>` : '') +
    (r.agent_id === 'technical' ? technicalDetail(r.metrics) : r.agent_id === 'calendar' ? calendarDetail(r.metrics)
      : r.agent_id === 'arbitrage' ? arbDetail(r.metrics) : mt ? `<table class="metrics">${mt}</table>` : '') +
    `<p class="muted">v${esc(r.version)} · ${new Date(r.asof).toISOString().slice(0, 16).replace('T', ' ')} UTC</p>`
}

/** Tooltip de la esfera central: el resumen que antes ocupaba el apartado «Síntesis». */
export function coreTip(syn: Synthesis | null, reports: AgentReport[]): string {
  if (!syn) return `${head('Síntesis')}<p class="muted">Sin reportes todavía: se calcula al haber agentes con datos.</p>`
  const ud = upDown(syn)
  const dis = disagreeing(reports)
  const sh = shares(syn) ?? []
  const ids = new Set(sh.map((s) => s.id))
  const rows = [...sh, ...Object.keys(syn.contributions).filter((id) => !ids.has(id)).map((id) => ({ id, dir: 0, pct: 0 }))]
  const list = rows.map((s) => `<tr><td>${esc(agentName(s.id))}</td><td>${pbar(s.pct, s.dir)}</td>` +
    `<td class="num" style="color:${s.dir > 0 ? 'var(--up)' : s.dir < 0 ? 'var(--down)' : 'var(--muted)'}">` +
    `${s.dir > 0 ? '▲' : s.dir < 0 ? '▼' : ''} ${s.pct} %</td></tr>`).join('')
  return head('Síntesis') +
    `<div class="tip-k"><b style="color:${tint(syn.bias, 1.8)}">${verdict(syn.bias)} · sesgo ${sg(syn.bias)}</b>` +
    (ud ? `<span><b style="color:var(--up)">▲ ${ud.up} %</b> / <b style="color:var(--down)">▼ ${ud.down} %</b></span>` : '') + '</div>' +
    `<div class="tip-k"><span>Confianza <b>${Math.round(syn.confidence * 100)} %</b></span>` +
    `<span>Acuerdo <b>${Math.round(syn.agreement * 100)} %</b></span></div>` +
    (dis ? '<p class="tip-alert">⚠ Los agentes se contradicen: ' +
      `<b>${dis.up.map(agentName).join(', ')}</b> (alcista) vs <b>${dis.down.map(agentName).join(', ')}</b> (bajista)</p>` : '') +
    (syn.thesis ? `<p>${esc(syn.thesis)}</p>` : '') +
    (list ? `<p class="muted">Aporte de cada agente a la proyección (suma 100 %)</p><table class="metrics tip-sh">${list}</table>` : '') +
    `<p class="muted">${esc(PCT_NOTE)}</p>`
}
