import { orb } from './agent_orbs'
import type { ArbMetrics, ArbPayload, ArbRow } from './arb_types'
import { horizon, num, pct, STRATEGY, usd } from './arb_view'
import { esc } from './panels'
import { head } from './river_tips'

/**
 * Satélite de arbitraje en el río de decisión: una esfera propia junto a la central, SIN haz
 * hacia ella (carril propio, T44: no suma a la proyección direccional). Su porcentaje es la
 * proyección propia del arbitraje: el rendimiento neto anualizado estimado de la mejor
 * oportunidad (▲ ganancia / ▼ pérdida), no la dirección del precio. Datos en vivo del escáner
 * (REST/WS `arbitrage`), no del cierre de vela.
 */

export const ARB_ID = 'arbitrage'
export const SAT_R = 24
const RISK: Record<string, string> = { legging: 'patas', basis: 'base', liquidation: 'liquidación', liquidity: 'liquidez' }

let data: ArbPayload | null = null
let skew = 0 // hora del servidor − hora local

export function setArbData(p: ArbPayload): void {
  data = p
  skew = p.now - Date.now()
}

interface Projection { dir: number; text: string; row: ArbRow; selected: number }

/** Mejor seleccionada; si ninguna pasa, la de mayor neto entre las seleccionables. */
export function projection(p: ArbPayload | null = data): Projection | null {
  if (!p || p.scan_asof == null || !p.opportunities.length) return null
  const sel = p.opportunities.filter((r) => r.selected)
  const pool = p.opportunities.filter((r) => r.reject_code !== 'informative')
  const row = sel[0] ?? [...(pool.length ? pool : p.opportunities)].sort((a, b) => b.net_bps - a.net_bps)[0]
  const text = row.annualized != null ? `${pct(row.annualized)} anual` : `${usd(row.net_bps, 1)} pb`
  return { dir: Math.sign(row.net), text, row, selected: sel.length }
}

const arrow = (d: number): string => (d > 0 ? '▲' : d < 0 ? '▼' : '•')

function colorOf(pr: Projection | null): string {
  if (!pr || !data || data.stale) return 'var(--muted)'
  return pr.dir > 0 ? 'var(--up)' : pr.dir < 0 ? 'var(--down)' : 'var(--holo)'
}

/** Esfera satélite en (x, y); las etiquetas quedan a su izquierda. */
export function arbSatellite(x: number, y: number, sel: boolean): string {
  const pr = projection()
  const col = colorOf(pr)
  const live = !!pr && !!data && !data.stale
  const lx = x - SAT_R - 16
  const value = pr ? `${arrow(pr.dir)} ${pr.text}` : 'sin datos'
  const sub = !data ? 'consultando el escáner…' : !pr ? 'escáner sin fotografía'
    : data.stale ? 'fotografía vieja' : 'neto estimado · no direccional'
  const hover = pr
    ? `Arbitraje: ${value} (neto estimado, no garantizado) · ${STRATEGY[pr.row.strategy]} ${pr.row.asset} · ` +
      `${pr.selected} seleccionadas · no suma a la proyección central · clic: detalle`
    : 'Arbitraje: sin fotografía del escáner'
  return `<g class="trib arb-sat${sel ? ' sel' : ''}" data-id="${ARB_ID}" tabindex="0" role="button" aria-label="Arbitraje: ver detalles">` +
    `<title>${esc(hover)}</title>` +
    `<circle cx="${x}" cy="${y}" r="${SAT_R + 8}" fill="none" stroke="${col}" stroke-width="1" stroke-dasharray="2 6" opacity=".8" class="hspin"/>` +
    `<circle cx="${x}" cy="${y}" r="${SAT_R + 15}" fill="none" stroke="${col}" stroke-width=".8" stroke-dasharray="1 10" opacity=".35"/>` +
    orb(ARB_ID, x, y, SAT_R, col, live, 990) +
    `<text x="${lx}" y="${y - 9}" text-anchor="end" class="rl">Arbitraje</text>` +
    `<text x="${lx}" y="${y + 10}" text-anchor="end" class="arb-pv" style="fill:${col}">${esc(value)}</text>` +
    `<text x="${lx}" y="${y + 25}" text-anchor="end" class="rv">${esc(sub)}</text></g>`
}

const ago = (t: number): string => `${Math.max(0, Math.round((Date.now() + skew - t) / 1000))} s`

/** Tooltip del satélite: proyección propia, mejor oportunidad con desglose, funding y base. */
export function arbTip(): string {
  const p = data
  if (!p) return head('Arbitraje') + '<p class="muted">Consultando el escáner…</p>'
  const pr = projection(p)
  const m = p.report.metrics as unknown as ArbMetrics
  const st = p.report.status
  const chips = `<div class="tip-k"><span class="chip" data-s="${esc(st)}">${st === 'ok' ? 'OK' : st === 'degraded' ? 'Degradado' : 'Sin datos'}</span>` +
    `<span class="muted">Modo Análisis · confianza ${Math.round(p.report.confidence * 100)} %` +
    `${p.scan_asof != null ? ` · fotografía hace ${ago(p.scan_asof)}` : ''}</span></div>`
  if (!pr) return head('Arbitraje') + chips + `<p class="muted">${esc(p.report.warnings[0] ?? 'Sin oportunidades valoradas.')}</p>`
  const r = pr.row, c = r.costs, col = colorOf(pr)
  const costs = [['com.', c.fees], ['desl.', c.slippage], ['fund.', c.funding], ['prést.', c.borrow]]
    .filter(([, v]) => v !== 0).map(([k, v]) => `${k} ${num(v as number)}`).join(' · ')
  const risk = (Object.entries(r.risk) as [string, number][]).sort((a, b) => b[1] - a[1])[0]
  const syms = r.id.split('·').pop() ?? ''
  const why = Object.entries(m.rejected_by_code ?? {}).map(([k, v]) => `${k === 'informative' ? 'informativas' : k === 'below_min' ? 'bajo el mínimo' : k} ${v}`).join(', ')
  const fund = Object.values(m.funding ?? {}).filter((f) => f.predicted != null && f.margin === 'USDT')
    .map((f) => `${esc(f.symbol)} ${pct(f.predicted, 4)}/${f.interval_h} h (${pct(f.predicted_annual, 1)} anual)`).join(' · ')
  const next = Object.values(m.funding ?? {}).find((f) => f.next_funding_t)?.next_funding_t
  const mins = next ? Math.max(0, Math.round((next - Date.now() - skew) / 60000)) : null
  const basis = (m.basis ?? []).filter((b) => b.kind === 'quarterly' && b.annualized != null)
    .map((b) => `${esc(b.contract ?? '')} ${pct(b.annualized)}`).join(' · ')
  const act = p.alerts.filter((a) => a.active).length, watch = p.alerts.length - act
  return head('Arbitraje · carril propio') + chips +
    `<div class="tip-share"><span class="muted">Proyección propia (neto anual)</span>` +
    `<b style="color:${col}">${arrow(pr.dir)} ${esc(pr.text)}</b></div>` +
    '<p class="muted">Rendimiento estimado de la mejor oportunidad, no dirección del precio: suma 0 % a la proyección central.</p>' +
    `<p><b>${esc(STRATEGY[r.strategy])} ${esc(r.asset)}</b> · ${esc(r.variant)}<br><span class="muted">${esc(syms)}</span></p>` +
    '<table class="metrics">' +
    `<tr><td>Bruto</td><td class="num">${usd(r.gross)} USD</td></tr>` +
    `<tr><td>Costos</td><td class="num">−${num(c.total)} USD <span class="muted">(${esc(costs)})</span></td></tr>` +
    `<tr><td>Neto estimado</td><td class="num" style="color:${col}">${usd(r.net)} USD · ${usd(r.net_bps, 1)} pb</td></tr>` +
    `<tr><td>Capital · horizonte</td><td class="num">${Math.round(r.capital).toLocaleString('es-CO')} USD · ${horizon(r.horizon_h)}</td></tr>` +
    `<tr><td>Riesgo mayor</td><td class="num">${esc(RISK[risk[0]] ?? risk[0])} ${num(risk[1])} <span class="muted">(0–1)</span></td></tr></table>` +
    `<p class="muted">${m.counts ? `${m.counts.valued} valoradas · ${m.counts.selected} seleccionadas · ${m.counts.rejected} descartadas` : ''}` +
    `${why ? ` (${esc(why)})` : ''}</p>` +
    (fund ? `<p>Funding previsto: ${fund}${mins != null ? ` · próxima liquidación en ${Math.floor(mins / 60)} h ${mins % 60} min` : ''}</p>` : '') +
    (basis ? `<p>Base trimestral anualizada: ${basis}</p>` : '') +
    `<p>${act ? `<b style="color:var(--up)">${act} alerta(s) activa(s)</b>` : 'Sin alertas activas'}` +
    `${watch ? ` · ${watch} en observación` : ''} <span class="muted">(umbral ${p.alert_params.min_score} pb/día, ${p.alert_params.hold_s} s)</span></p>` +
    `<p class="muted">${esc(p.label)}. </p><button class="btn tip-btn" data-open-arb>Ver tabla completa</button>`
}
