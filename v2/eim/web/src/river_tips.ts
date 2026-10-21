import { roleOf, weightOf } from './agent_roles'
import { arbDetail } from './arb_view'
import { calendarDetail } from './calendar_ui'
import { agentName, esc } from './panels'
import { disagreeing, PCT_NOTE, shares, upDown } from './synth'
import { technicalDetail } from './technical_ui'
import type { AgentInfo, AgentReport, Synthesis } from './types'
import { bogIso } from './tz'

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

export const head = (title: string): string =>
  `<div class="tip-h"><b>${esc(title)}</b><button data-close aria-label="Cerrar">×</button></div>`

/** Barra 0..100 % teñida según la dirección del aporte. */
const pbar = (p: number, dir: number): string =>
  `<span class="tbar"><i style="width:${p}%;background:${dir > 0 ? 'var(--up)' : dir < 0 ? 'var(--down)' : 'var(--muted)'}"></i></span>`

const ev = (syn: Synthesis | null): string =>
  syn?.factors?.evento ? ` <b class="warn">Ahora: confianza ×${syn.factors.evento.toFixed(2)}.</b>` : ''

/** Por qué un agente no vota, según su papel (T44); '' si vota. */
export function whyNotVoting(id: string, infos: AgentInfo[], syn: Synthesis | null): string {
  const role = roleOf(id, infos)
  if (id === 'calendar') {
    return 'No suma al sesgo: en ventana de evento reduce la confianza de la síntesis (×0,75; ×0,5 con blackout) ' +
      'y el tamaño de la operación (×0,5); con blackout el motor de riesgo veta entradas nuevas.'
  }
  if (role === 'riesgo') return 'No vota: modula los pesos según el régimen.'
  if (role === 'carril') return 'Carril propio: su rendimiento no suma a la dirección del precio.'
  if (role === 'derivado') return 'No vota: deriva de estructura y niveles (evita el doble conteo).'
  if (role === 'contexto') return 'No vota: bots de terceros solo informan hasta superar la puerta de validación (T59).'
  if ((weightOf(id, infos, syn) ?? 1) <= 0) {
    return 'Peso 0: no aportó fuera de muestra (reports/agents_marginal.md); se muestra pero no mueve la síntesis.'
  }
  return ''
}

/** Aporte del agente a la proyección de la síntesis (o por qué no aporta). */
function share(id: string, syn: Synthesis | null, infos: AgentInfo[]): string {
  const why = whyNotVoting(id, infos, syn)
  if (why) return `<span class="muted">${esc(why)}</span>${id === 'calendar' ? ev(syn) : ''}`
  if (!syn || !(id in syn.contributions)) return '<span class="muted">fuera de la síntesis (sin datos)</span>'
  const s = shares(syn)?.find((x) => x.id === id)
  const w = weightOf(id, infos, syn) ?? 1
  const wt = w < 0.999 ? ` <span class="muted" title="Peso base × penalización por correlación con agentes que ya votan">· peso ${w.toFixed(2)}</span>` : ''
  if (!s || !s.dir) return `<b>0 %</b> <span class="muted">· neutral</span>${wt}`
  return `<b style="color:var(--${s.dir > 0 ? 'up' : 'down'})" title="${esc(PCT_NOTE)}">${s.dir > 0 ? '▲' : '▼'} ${s.pct} % ` +
    `${s.dir > 0 ? 'subida' : 'bajada'}</b>${pbar(s.pct, s.dir)}${wt}`
}

/** Tooltip de un agente: su último reporte + su aporte a la proyección. */
export function agentTip(r: AgentReport | undefined, id: string, syn: Synthesis | null, infos: AgentInfo[] = []): string {
  if (!r) return `${head(agentName(id))}<p class="muted">Aún sin reporte: se ejecuta al cerrar la próxima vela.</p>`
  const dir = Math.abs(r.bias) < THRESH ? 'Neutral' : r.bias > 0 ? 'Compra' : 'Venta'
  const ev = r.evidence.slice(0, 4).map((e) => `<li>${esc(e)}</li>`).join('')
  const wn = r.warnings.map((w) => `<li>${esc(w)}</li>`).join('')
  const mt = Object.entries(r.metrics).slice(0, 6)
    .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(fmt(v))}</td></tr>`).join('')
  return head(agentName(id)) +
    `<div class="tip-k"><span class="chip" data-s="${esc(r.status)}">${esc(STATUS[r.status] ?? r.status)}</span>` +
    `<b style="color:${tint(r.bias)}">${dir} ${sg(r.bias)}</b><span class="muted">confianza ${Math.round(r.confidence * 100)}% · ${r.horizon_bars} velas</span></div>` +
    `<div class="tip-share"><span class="muted">Aporte a la proyección</span>${share(id, syn, infos)}</div>` +
    (ev ? `<ul class="ev">${ev}</ul>` : '') + (wn ? `<ul class="warn">${wn}</ul>` : '') +
    (r.agent_id === 'technical' ? technicalDetail(r.metrics) : r.agent_id === 'calendar' ? calendarDetail(r.metrics)
      : r.agent_id === 'arbitrage' ? arbDetail(r.metrics) : mt ? `<table class="metrics">${mt}</table>` : '') +
    `<p class="muted">v${esc(r.version)} · ${bogIso(r.asof).slice(0, 16).replace('T', ' ')} COT</p>`
}

/** Tooltip de la esfera central: el resumen que antes ocupaba el apartado «Síntesis». */
export function coreTip(syn: Synthesis | null, reports: AgentReport[], infos: AgentInfo[] = []): string {
  if (!syn) return `${head('Síntesis')}<p class="muted">Sin reportes todavía: se calcula al haber agentes con datos.</p>`
  const ud = upDown(syn)
  const dis = disagreeing(reports, syn)
  const sh = shares(syn) ?? []
  const ids = new Set(sh.map((s) => s.id))
  const rows = [...sh, ...Object.keys(syn.contributions).filter((id) => !ids.has(id)).map((id) => ({ id, dir: 0, pct: 0 }))]
  const wt = (id: string): string => {
    const w = syn.weights?.[id]
    return w === undefined ? '' : w.toFixed(2)
  }
  const list = rows.map((s) => `<tr><td>${esc(agentName(s.id))}</td><td>${pbar(s.pct, s.dir)}</td>` +
    `<td class="num" style="color:${s.dir > 0 ? 'var(--up)' : s.dir < 0 ? 'var(--down)' : 'var(--muted)'}">` +
    `${s.dir > 0 ? '▲' : s.dir < 0 ? '▼' : ''} ${s.pct} %</td><td class="num muted" title="peso efectivo">${wt(s.id)}</td></tr>`).join('')
  // Agentes a la vista que no votan (papel o peso 0), con el motivo (T44)
  const seen = [...new Set([...infos.map((i) => i.id), ...reports.map((r) => r.agent_id)])]
  const mute = seen.filter((id) => !(id in syn.contributions) && whyNotVoting(id, infos, syn))
  const muted = mute.length ? '<p class="muted">No votan: ' + mute.map((id) =>
    `<span title="${esc(whyNotVoting(id, infos, syn))}">${esc(agentName(id))}</span>`).join(' · ') + '</p>' : ''
  const F: Record<string, string> = { desacuerdo: 'desacuerdo', evento: 'ventana de evento (calendario)' }
  const fac = Object.entries(syn.factors ?? {})
  const facs = fac.length ? `<p class="tip-alert">Confianza ${fac.map(([k, v]) => `×${v.toFixed(2)} por ${esc(F[k] ?? k)}`).join(' · ')}</p>` : ''
  return head('Síntesis') +
    `<div class="tip-k"><b style="color:${tint(syn.bias, 1.8)}">${verdict(syn.bias)} · sesgo ${sg(syn.bias)}</b>` +
    (ud ? `<span><b style="color:var(--up)">▲ ${ud.up} %</b> / <b style="color:var(--down)">▼ ${ud.down} %</b></span>` : '') + '</div>' +
    `<div class="tip-k"><span>Confianza <b>${Math.round(syn.confidence * 100)} %</b></span>` +
    `<span>Acuerdo <b>${Math.round(syn.agreement * 100)} %</b></span></div>` +
    (dis ? '<p class="tip-alert">⚠ Los agentes se contradicen: ' +
      `<b>${dis.up.map(agentName).join(', ')}</b> (alcista) vs <b>${dis.down.map(agentName).join(', ')}</b> (bajista)</p>` : '') +
    facs + (syn.thesis ? `<p>${esc(syn.thesis)}</p>` : '') +
    (list ? `<p class="muted">Aporte de cada agente a la proyección (suma 100 %) · peso efectivo</p><table class="metrics tip-sh">${list}</table>` : '') +
    muted +
    `<p class="muted">${esc(PCT_NOTE)}</p>`
}
