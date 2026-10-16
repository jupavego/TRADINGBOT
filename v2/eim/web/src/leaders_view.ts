import { esc } from './panels'
import type { Board, Ci, Cohort, CopyStats, LeaderPosition, PositionChange, Scorecard, TradeStats, Verdict } from './leaders_types'

/** Piezas de la pestaña «Líderes» (T41): ranking, detalle por líder y cohortes. */
export const VERDICT: Record<Verdict, string> = { approved: 'Aprobado', watch: 'Vigilancia', rejected: 'Descartado' }
const KIND: Record<string, string> = { descarte: 'Descarte', vigilancia: 'Vigilancia', aprobado: 'Aprobado', aviso: 'Aviso' }

const nf = (x: number, d = 2): string => x.toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d })
export const f = (x: number | null | undefined, d = 2): string => (x == null ? '—' : nf(x, d))
export const usd = (x: number | null | undefined, d = 0): string => (x == null ? '—' : `${x > 0 ? '+' : ''}${nf(x, d)}`)
export const pct = (x: number | null | undefined, d = 1): string => (x == null ? '—' : `${nf(x * 100, d)} %`)
const spct = (x: number | null | undefined, d = 1): string => (x == null ? '—' : `${x > 0 ? '+' : ''}${nf(x * 100, d)} %`)
const dir = (x: number | null | undefined): string => (x == null || x === 0 ? 'flat' : x > 0 ? 'up' : 'down')
const ci = (c: Ci, d = 2): string => (c ? `[${nf(c[0], d)} ; ${nf(c[1], d)}]` : '')
const short = (a: string): string => `${a.slice(0, 6)}…${a.slice(-4)}`
export const utc = (t: number): string => new Date(t).toISOString().replace('T', ' ').slice(0, 16) + ' UTC'

function hold(ms: number | null): string {
  if (ms == null) return '—'
  const m = ms / 60_000
  return m < 90 ? `${nf(m, 0)} min` : m < 2880 ? `${nf(m / 60, 1)} h` : `${nf(m / 1440, 1)} d`
}

function sample(c: Scorecard): string {
  const p = c.portfolio
  return `<b>${c.all.n}</b> cerradas<small>adelante ${c.fwd.n} en ${nf(c.forward_days, 1)} d</small>` +
    `<small>${p ? `cartera ${nf(p.days, 0)} d` : 'sin cartera'}</small>`
}

function net(c: Scorecard): string {
  const a = c.all, p = c.portfolio
  return `<span data-dir="${dir(a.net)}"><b>${usd(a.net)}</b></span><small>${a.ret != null ? spct(a.ret, 2) + ' cuenta' : ''}</small>` +
    `<small>cartera ${p ? `${usd(p.pnl)} · TWR ${spct(p.twr)}` : '—'}</small>`
}

function risk(c: Scorecard): string {
  const a = c.all, dd = Math.max(a.max_dd ?? 0, c.portfolio?.max_dd ?? 0)
  return `<b>${dd ? pct(dd) : '—'}</b><small>FB ${f(a.profit_factor)} · G/P ${f(a.payoff)}</small>` +
    `<small>acierto ${pct(a.win_rate, 0)}</small>`
}

function edge(s: TradeStats, label: string): string {
  return `<b>${f(s.sharpe)}</b> <small>${label} ${ci(s.sharpe_ci)}</small>` +
    `<small>DSR ${f(s.dsr)}${s.sr0 != null ? ` · azar ${f(s.sr0)}` : ''}</small>`
}

function style(a: TradeStats): string {
  const top = a.top_asset ? `${esc(a.top_asset)} ${pct(a.top_asset_share, 0)}` : '—'
  return `<b>${top}</b><small>${a.n_assets} monedas · apal. ${f(a.lev_median, 0)}×</small>` +
    `<small>días + ${a.windows ? `${a.windows_pos}/${a.windows}` : '—'} · ${hold(a.hold_ms)}</small>`
}

function copyCell(cp: CopyStats | null): string {
  if (!cp) return '—'
  const lat = cp.latency_ms.p50
  return `<b>${lat != null ? `${nf(lat, 0)} ms` : '—'}</b><small>desliz. ${f(cp.slip_bps.p50, 1)} pb · ${cp.trades} op</small>` +
    `<small>seguidor ${usd(cp.follower_net)}${cp.retention != null ? ` (${pct(cp.retention, 0)})` : ''}</small>`
}

export function rankingTable(b: Board, rows: Scorecard[], open: Set<string>): string {
  const head = '<tr><th>#</th><th>Líder</th><th>Estado</th><th>Muestra</th><th>Neto (capturado · cartera)</th>' +
    '<th>Caída máx. · FB · G/P</th><th>Sharpe/op adelante [IC]</th><th>Sharpe/op capturado [IC]</th>' +
    '<th>Activo · estilo</th><th>Copiabilidad</th><th>Calidad</th></tr>'
  const body = rows.map((c) => {
    const exp = open.has(c.leader_id)
    const main = `<tr class="ld-row" data-id="${esc(c.leader_id)}" data-v="${c.verdict}" aria-expanded="${exp}">` +
      `<td>${c.rank}</td><td><b title="${esc(c.address)}">${esc(c.label || short(c.address))}</b><small>${esc(c.origin)}</small></td>` +
      `<td><span class="ld-chip" data-v="${c.verdict}">${VERDICT[c.verdict]}</span><small>${esc(c.reasons[0]?.text ?? '')}</small></td>` +
      `<td>${sample(c)}</td><td>${net(c)}</td><td>${risk(c)}</td><td>${edge(c.fwd, 'IC')}</td><td>${edge(c.all, 'IC')}</td>` +
      `<td>${style(c.all)}</td><td>${copyCell(c.copyability)}</td><td><b>${f(c.quality)}</b></td></tr>`
    return main + (exp ? `<tr class="ld-detail"><td colspan="11">${detail(b, c)}</td></tr>` : '')
  }).join('')
  return `<div class="arb-scroll"><table class="log ld-table"><thead>${head}</thead><tbody>${body ||
    '<tr><td colspan="11" class="muted">Sin líderes con este filtro.</td></tr>'}</tbody></table></div>`
}

function positions(ps: LeaderPosition[], at: number | undefined): string {
  if (!ps.length) return '<p class="muted">Sin posiciones abiertas en la última foto.</p>'
  return `<table class="log"><thead><tr><th>Moneda</th><th>Lado</th><th>Tamaño</th><th>Entrada</th><th>Apal.</th>` +
    `<th>Liquidación</th><th>PnL latente</th></tr></thead><tbody>` + ps.map((p) =>
    `<tr><td>${esc(p.symbol)}</td><td data-dir="${p.side === 'long' ? 'up' : 'down'}">${p.side}</td><td>${f(p.size, 4)}</td>` +
    `<td>${f(p.entry, 2)}</td><td>${f(p.leverage, 0)}×</td><td>${f(p.liquidation_px, 2)}</td>` +
    `<td data-dir="${dir(p.unrealized_pnl)}">${usd(p.unrealized_pnl)}</td></tr>`).join('') +
    `</tbody></table>${at ? `<small class="muted">Foto ${utc(at)}</small>` : ''}`
}

function changes(cs: PositionChange[]): string {
  if (!cs.length) return '<p class="muted">Sin cambios en 1 h / 4 h / 24 h (o sin fotos tan viejas).</p>'
  return '<ul class="arb-notes">' + cs.map((c) =>
    `<li>${esc(c.symbol)} en ${nf(c.window_h, 0)} h: ${f(c.from_size, 4)} → ${f(c.to_size, 4)} ` +
    `(<span data-dir="${dir(c.to_size - c.from_size)}">${usd(c.to_size - c.from_size, 4)}</span>)</li>`).join('') + '</ul>'
}

function statsTable(c: Scorecard): string {
  const cols: [string, TradeStats][] = [['Adelante (aprueba)', c.fwd], ['Historial previo (preselecciona)', c.hist], ['Todo lo capturado', c.all]]
  const rows: [string, (s: TradeStats) => string][] = [
    ['Operaciones cerradas', (s) => `${s.n} (${s.n_partial} parciales fuera)`],
    ['Neto (comisiones y funding)', (s) => `${usd(s.net)} · com. ${usd(-s.fees)} · fund. ${usd(s.funding)}`],
    ['Neto medio por operación [IC]', (s) => `${usd(s.mean, 1)} ${ci(s.mean_ci, 1)}`],
    ['Factor de beneficio · G/P media', (s) => `${f(s.profit_factor)} · ${f(s.payoff)}`],
    ['Sharpe por operación [IC] · DSR', (s) => `${f(s.sharpe)} ${ci(s.sharpe_ci)} · ${f(s.dsr)}`],
    ['Caída máx. (sobre la cuenta)', (s) => pct(s.max_dd)],
    ['Promediado a la baja · martingala', (s) => `${pct(s.avg_down_share, 0)} · ×${f(s.martingale, 1)}`],
    ['Consistencia (días positivos)', (s) => (s.windows ? `${s.windows_pos}/${s.windows} · peor ${usd(s.worst_window)}` : '—')],
  ]
  return `<table class="log"><thead><tr><th></th>${cols.map(([l]) => `<th>${l}</th>`).join('')}</tr></thead><tbody>` +
    rows.map(([l, fn]) => `<tr><td>${l}</td>${cols.map(([, s]) => `<td>${fn(s)}</td>`).join('')}</tr>`).join('') + '</tbody></table>'
}

function copyDetail(cp: CopyStats | null): string {
  if (!cp) return ''
  const ch = Object.entries(cp.latency_by_channel).map(([k, v]) => `${esc(k)} p50 ${f(v.p50, 0)} ms (n=${f(v.n, 0)})`).join(' · ')
  return `<p class="ld-copy">Seguidor: ve la ejecución con latencia p50 ${f(cp.latency_ms.p50, 0)} ms / p90 ${f(cp.latency_ms.p90, 0)} ms ` +
    `(${ch || 'sin ejecuciones en vivo'}) y su orden llega ${cp.delay_ms} ms después; compra al ask, vende al bid y paga comisión de tomador. ` +
    `Deslizamiento p50 ${f(cp.slip_bps.p50, 1)} pb / p90 ${f(cp.slip_bps.p90, 1)} pb en ${cp.quoted_fills} ejecuciones cotizadas ` +
    `(${Object.entries(cp.quote_src).map(([k, v]) => `${k} ${v}`).join(', ') || 'ninguna'}). ` +
    `En ${cp.trades} operaciones adelante: líder ${usd(cp.leader_net)} USD, seguidor ${usd(cp.follower_net)} USD` +
    `${cp.retention != null ? ` (retiene ${pct(cp.retention, 0)})` : ''}.</p>`
}

function detail(b: Board, c: Scorecard): string {
  const reasons = '<ul class="ld-reasons">' + c.reasons.map((r) =>
    `<li data-k="${r.kind}"><b>${KIND[r.kind] ?? r.kind}</b> ${esc(r.text)}</li>`).join('') + '</ul>'
  const pf = c.portfolio
  const port = pf ? `<p class="muted">Cartera (${nf(pf.days, 0)} d): PnL ${usd(pf.pnl)} USD · TWR ${spct(pf.twr)} · caída máx. ${pct(pf.max_dd)} · ` +
    `tramos + ${pf.windows_pos}/${pf.windows} · último mes ${usd(pf.month_pnl)} USD · cuenta ${usd(pf.account_value)} USD. Solo preselecciona.</p>` : ''
  return `<p class="muted">${esc(c.address)} · seguimiento adelante desde ${c.forward_start ? utc(c.forward_start) : '—'}` +
    ` · PnL latente ${usd(c.unrealized)} USD · evaluado ${utc(c.scored_at)}</p>${reasons}` +
    `<div class="arb-grid"><section><h4>Posiciones</h4>${positions(b.positions[c.leader_id] ?? [], b.positions_at[c.leader_id])}</section>` +
    `<section><h4>Cambios recientes</h4>${changes(b.changes[c.leader_id] ?? [])}</section></div>` +
    `<h4>Métricas por muestra</h4><div class="arb-scroll">${statsTable(c)}</div>${copyDetail(c.copyability)}${port}`
}

export function cohortsBox(co: Record<string, Cohort>): string {
  const order: Verdict[] = ['approved', 'watch', 'rejected']
  return '<div class="ld-cohorts">' + order.map((v) => {
    const x = co[v]
    if (!x) return ''
    return `<div class="ld-cohort" data-v="${v}"><b>${VERDICT[v]}</b>` +
      `<span>${x.leaders} líderes · ${x.trades} operaciones adelante</span>` +
      `<span data-dir="${dir(x.net)}">neto ${usd(x.net)} USD · ${f(x.mean_bps, 1)} pb/op · acierto ${pct(x.win_rate, 0)}</span></div>`
  }).join('') + '</div>'
}
