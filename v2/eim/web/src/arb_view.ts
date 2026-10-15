import type { ArbAlert, ArbBasis, ArbFunding, ArbRow, ArbScanInfo, ArbStrategy } from './arb_types'
import { esc } from './panels'

export const STRATEGY: Record<ArbStrategy, string> = {
  funding_carry: 'Carry de funding', basis: 'Base / cash-and-carry',
  triangular: 'Triangular spot', related_perps: 'USDT-M vs USDC-M',
}
const RISK: [keyof ArbRow['risk'], string, string][] = [
  ['legging', 'P', 'Patas (ejecución no simultánea)'], ['basis', 'B', 'Base'],
  ['liquidation', 'L', 'Liquidación'], ['liquidity', 'Q', 'Liquidez (fracción del libro visible)'],
]
const SCAN: Record<string, string> = { ok: 'OK', degraded: 'Degradado', no_data: 'Sin datos' }

const num = (x: number, d = 2): string =>
  x.toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d })
export const usd = (x: number, d = 2): string => `${x > 0 ? '+' : ''}${num(x, d)}`
export const pct = (x: number | null | undefined, d = 2): string =>
  x == null ? '—' : `${x > 0 ? '+' : ''}${num(x * 100, d)} %`
const dir = (x: number): string => (x > 0 ? 'up' : x < 0 ? 'down' : 'flat')
export const utc = (t: number): string => new Date(t).toISOString().slice(11, 19) + ' UTC'

export function horizon(h: number): string {
  if (h <= 0) return 'instantáneo'
  return h >= 48 ? `${(h / 24).toFixed(0)} d` : `${h.toFixed(0)} h`
}

export function countdown(until: number, now: number): string {
  const s = Math.round((until - now) / 1000)
  return s >= 0 ? `vigente ${s} s` : 'precio caducado'
}

function riskCell(r: ArbRow): string {
  const notes = r.risk_notes ?? {}
  return '<div class="arb-risk">' + RISK.map(([k, l, name]) => {
    const v = r.risk[k]
    const lvl = v >= 0.66 ? 'hi' : v >= 0.33 ? 'mid' : 'lo'
    return `<span data-lvl="${lvl}" title="${esc(`${name}: ${v.toFixed(2)}${notes[k] ? ' — ' + notes[k] : ''}`)}">` +
      `${l}<i style="width:calc((100% - 12px) * ${v.toFixed(3)})"></i></span>`
  }).join('') + '</div>'
}

function costCell(r: ArbRow): string {
  const c = r.costs
  const parts = [['com.', c.fees], ['desl.', c.slippage], ['fund.', c.funding], ['prést.', c.borrow]]
    .filter(([, v]) => v !== 0).map(([k, v]) => `${k} ${num(v as number)}`).join(' · ')
  return `<b class="num">−${num(c.total)}</b><small>${esc(parts || 'sin costos')}</small>`
}

function stateCell(r: ArbRow): string {
  return r.selected
    ? `<span class="chip" data-s="ok">Seleccionada</span><small>${num(r.score ?? 0)} pb/día ajust.</small>`
    : `<span class="chip" data-s="no_data">Descartada</span><small>${esc(r.reason ?? '')}</small>`
}

function detailRow(r: ArbRow): string {
  const legs = r.legs.map((l) => `<tr><td>${esc(l.text)}</td><td class="num">${l.qty.toPrecision(6)}` +
    `${l.complete ? '' : ` <em class="arb-bad">(libro: ${l.filled.toPrecision(4)})</em>`}</td>` +
    `<td class="num">${num(l.vwap, l.vwap < 10 ? 6 : 2)}</td><td class="num">${num(l.mid, l.mid < 10 ? 6 : 2)}</td>` +
    `<td class="num">${(l.fee_rate * 100).toFixed(3)} %</td><td class="num">${num(l.fee)}</td>` +
    `<td class="num">${num(l.slippage)}</td><td class="num">${l.levels}</td></tr>`).join('')
  const notes = Object.entries(r.risk_notes ?? {}).map(([k, v]) => `<li><b>${esc(k)}</b>: ${esc(v)}</li>`).join('')
  const warns = r.warnings.map((w) => `<li>${esc(w)}</li>`).join('')
  return `<tr class="arb-detail"><td colspan="10">
    <table class="log"><thead><tr><th>Pata</th><th>Cantidad</th><th>VWAP</th><th>Medio</th><th>Comisión</th>` +
    `<th>USD com.</th><th>USD desl.</th><th>Niveles</th></tr></thead><tbody>${legs}</tbody></table>
    <ul class="arb-notes">${notes}${warns}</ul>
    <p class="muted">Fuente ${esc(r.source)} · bruto ${usd(r.gross)} − costos ${num(r.costs.total)} = neto ${usd(r.net)} USD (motor T38)</p></td></tr>`
}

export function rowsTable(rows: ArbRow[], open: Set<string>, now: number): string {
  if (!rows.length) return '<p class="muted">Ninguna oportunidad con estos filtros.</p>'
  const head = '<tr><th>Estrategia</th><th>Patas</th><th>Bruto</th><th>Costos</th><th>Neto estimado</th>' +
    '<th>Anualizado</th><th>Capital</th><th>Riesgo</th><th>Vigencia</th><th>Estado</th></tr>'
  const body = rows.map((r) => {
    const tr = `<tr class="arb-row" data-id="${esc(r.id)}" data-sel="${r.selected}" aria-expanded="${open.has(r.id)}">` +
      `<td><b>${esc(STRATEGY[r.strategy])}</b><small>${esc(r.asset)} · ${esc(r.variant)}</small></td>` +
      `<td><small>${r.legs.map((l) => esc(l.text)).join('<br>')}</small></td>` +
      `<td class="num">${usd(r.gross)}</td><td>${costCell(r)}</td>` +
      `<td class="num" data-dir="${dir(r.net)}"><b>${usd(r.net)} USD</b><small>${usd(r.net_bps, 1)} pb</small></td>` +
      `<td class="num">${r.annualized == null ? '<small>instantáneo</small>' : pct(r.annualized)}</td>` +
      `<td class="num">${num(r.capital, 0)}</td><td>${riskCell(r)}</td>` +
      `<td><small>${horizon(r.horizon_h)}</small><small data-until="${r.valid_until}">${countdown(r.valid_until, now)}</small></td>` +
      `<td>${stateCell(r)}</td></tr>`
    return tr + (open.has(r.id) ? detailRow(r) : '')
  }).join('')
  return `<div class="arb-scroll"><table class="log arb-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>`
}

function spark(h: [number, number][]): string {
  if (!h.length) return '<span class="muted">sin histórico</span>'
  const w = 168, ht = 34, m = Math.max(...h.map(([, r]) => Math.abs(r)), 1e-9)
  const bw = w / h.length
  const bars = h.map(([t, r], i) => {
    const y = (Math.abs(r) / m) * (ht / 2 - 1)
    return `<rect x="${(i * bw + 0.5).toFixed(1)}" y="${(r >= 0 ? ht / 2 - y : ht / 2).toFixed(1)}" width="${Math.max(1, bw - 1).toFixed(1)}" ` +
      `height="${Math.max(0.5, y).toFixed(1)}" fill="var(--${r >= 0 ? 'up' : 'down'})"><title>${new Date(t).toISOString().slice(0, 16).replace('T', ' ')} UTC · ${(r * 100).toFixed(4)} %</title></rect>`
  }).join('')
  return `<svg class="arb-spark" width="${w}" height="${ht}" role="img" aria-label="Funding realizado">` +
    `<line x1="0" x2="${w}" y1="${ht / 2}" y2="${ht / 2}" stroke="var(--line)"/>${bars}</svg>`
}

export function fundingTable(f: Record<string, ArbFunding>, now: number): string {
  const rows = Object.values(f).map((x) => {
    if (x.predicted == null) return `<tr><td>${esc(x.symbol)}</td><td colspan="4" class="arb-bad">${esc(x.error ?? 'sin datos')}</td></tr>`
    const mins = x.next_funding_t ? Math.max(0, Math.round((x.next_funding_t - now) / 60000)) : null
    return `<tr><td><b>${esc(x.symbol)}</b><small>margen ${esc(x.margin)}</small></td>` +
      `<td class="num" data-dir="${dir(x.predicted)}">${pct(x.predicted, 4)}<small>/${x.interval_h} h · ${pct(x.predicted_annual, 1)} anual</small></td>` +
      `<td class="num">${mins == null ? '—' : `${Math.floor(mins / 60)} h ${mins % 60} min`}<small>${x.next_funding_t ? utc(x.next_funding_t) : ''}</small></td>` +
      `<td class="num">${pct(x.realized_mean, 4)}<small>n=${x.realized_n} · ${pct(x.realized_annual, 1)} anual</small></td>` +
      `<td>${spark(x.history)}</td></tr>`
  }).join('')
  return '<table class="log"><thead><tr><th>Perpetuo</th><th>Previsto (próx.)</th><th>Próxima liquidación</th>' +
    `<th>Realizado medio</th><th>Histórico corto</th></tr></thead><tbody>${rows}</tbody></table>`
}

export function basisTable(b: ArbBasis[]): string {
  const rows = b.map((x) => x.error
    ? `<tr><td>${esc(x.contract ?? x.asset)}</td><td colspan="4" class="arb-bad">${esc(x.error)}</td></tr>`
    : `<tr><td><b>${esc(x.contract ?? '')}</b><small>${x.kind === 'quarterly' ? 'trimestral' : 'perpetuo'}</small></td>` +
      `<td>${esc(x.vs ?? '')}</td><td class="num">${x.days == null ? '—' : x.days.toFixed(1)}</td>` +
      `<td class="num" data-dir="${dir(x.basis_bps ?? 0)}">${usd(x.basis_bps ?? 0, 1)} pb</td>` +
      `<td class="num">${x.annualized == null ? '<small>no converge</small>' : pct(x.annualized)}</td></tr>`).join('')
  return '<table class="log"><thead><tr><th>Contrato</th><th>Frente a</th><th>Días</th><th>Base (medios)</th>' +
    `<th>Anualizada</th></tr></thead><tbody>${rows}</tbody></table>`
}

export function scansList(s: ArbScanInfo[]): string {
  return s.map((x) => {
    const items = [...x.missing.map((m) => `falta ${m}`), ...x.warnings]
    return `<details class="arb-scan" data-k="scan-${x.strategy}"><summary><span class="chip" data-s="${x.status}">${SCAN[x.status]}</span> ` +
      `${esc(x.label)} · ${x.valued} valoradas</summary>${items.length ? `<ul>${items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : '<p class="muted">Sin avisos.</p>'}</details>`
  }).join('')
}

function alertLine(a: ArbAlert): string {
  return `<div class="arb-alert" data-active="${a.active}"><b>${a.active ? 'Alerta' : 'En observación'}</b> · ` +
    `${esc(STRATEGY[a.strategy])} ${esc(a.asset)} (${esc(a.variant)}) · ${esc(a.key.split('·').pop() ?? '')} · ` +
    `${num(a.score)} pb/día · neto ${usd(a.net_bps, 1)} pb${a.annualized == null ? '' : ` · ${pct(a.annualized)} anual`} · ` +
    `sostenida ${Math.round(a.held_s)} s</div>`
}

export function alertsBox(alerts: ArbAlert[], p: { min_score: number; hold_s: number }): string {
  const rule = `umbral ${num(p.min_score)} pb/día ajustados por riesgo, sostenido ${p.hold_s} s`
  if (!alerts.length) return `<p class="muted arb-rule">Sin alertas (${rule}).</p>`
  const active = alerts.filter((a) => a.active), watch = alerts.filter((a) => !a.active)
  const left = watch.length ? Math.max(0, Math.round(p.hold_s - Math.max(...watch.map((a) => a.held_s)))) : 0
  const w = watch.length
    ? `<details class="arb-watch" data-k="watch"><summary>${watch.length} en observación: superan el umbral, falta sostenerlo ` +
      `${left} s más</summary>${watch.map(alertLine).join('')}</details>` : ''
  const more = active.length > 3
    ? `<details class="arb-watch" data-k="more"><summary>${active.length - 3} alertas más</summary>` +
      `${active.slice(3).map(alertLine).join('')}</details>` : ''
  return `<div class="arb-alerts">${active.slice(0, 3).map(alertLine).join('')}${more}${w}` +
    `<p class="muted arb-rule">${rule}; neto estimado, no garantizado.</p></div>`
}

/** Detalle breve del agente en la columna de agentes; la tabla completa está en la pestaña. */
export function arbDetail(m: Record<string, unknown>): string {
  const best = (m.best as ArbRow[] | undefined)?.[0]
  const c = m.counts as { valued: number; selected: number; rejected: number } | undefined
  if (!c) return ''
  const b = best
    ? `<p>Mejor: <b>${esc(STRATEGY[best.strategy])} ${esc(best.asset)}</b> · ${usd(best.net)} USD (${usd(best.net_bps, 1)} pb` +
      `${best.annualized == null ? '' : `, ${pct(best.annualized)} anual`}) · ${esc(String(m.label ?? ''))}</p>`
    : '<p class="muted">Ninguna oportunidad supera costos y umbrales.</p>'
  return b + `<p class="muted">${c.valued} valoradas · ${c.selected} seleccionadas · ${c.rejected} descartadas · ` +
    'detalle en la pestaña «Arbitraje» (modo Análisis)</p>'
}
