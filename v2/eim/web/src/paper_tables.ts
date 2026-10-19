/** Tablas estilo exchange: posiciones, órdenes abiertas e historial (libro de operaciones). */
import { CAUSE, dur, esc, nf, pct, pct0, px, qty, REASON, rr, side, tone, usd, utc } from './paper_fmt'
import type { Order, PaperTrade, Position } from './paper_types'

type Names = Record<string, string>

const sideCell = (s: number, lev: number): string =>
  `<span class="pp-dir" data-side="${s > 0 ? 'long' : 'short'}">${side(s)}</span> <small class="muted">${lev}x · aislado</small>`
/** Nombre de la estrategia (sin el marco) + insignia del marco + «vivo» si se decidió en tiempo real. */
const stratCell = (sid: string, names: Names, origin: string, tf: string, floor = false): string =>
  `<b>${esc((names[sid] ?? sid).split(' · ')[0])}</b> <span class="pp-tfb">${esc(tf)}</span>` +
  (origin === 'vivo' ? ' <span class="pp-live">vivo</span>' : '') +
  (floor ? ' <span class="pp-live" title="Entró para cumplir el mínimo de operaciones abiertas del perfil (riesgo reducido)">mínimo</span>' : '')

/** PnL no realizado con un precio dado (el costo ya devengado se descuenta). */
export const upnlAt = (p: Position, price: number): number => p.side * p.qty * (price - p.entry) - p.cost_usd

export function positionsTable(ps: Position[], names: Names, sym: string, price: number | null, focus: string | null): string {
  if (!ps.length) return '<p class="muted">Sin posiciones abiertas en este perfil.</p>'
  const now = Date.now()
  const rows = ps.map((p) => {
    const mark = price ?? p.mark
    const u = upnlAt(p, mark)
    return `<tr data-pos="${esc(p.id)}" data-focus="${p.id === focus}">` +
      `<td>${stratCell(p.sid, names, p.origin, p.timeframe, p.floor)}<br>${sideCell(p.side, p.leverage)}</td>` +
      `<td class="num">${qty(p.qty, sym)}<br><small class="muted">${nf(p.qty * mark)} USDT</small></td>` +
      `<td class="num">${px(p.entry)}</td>` +
      `<td class="num" data-mark>${px(mark)}</td>` +
      `<td class="num warn">${px(p.liq)}</td>` +
      `<td class="num">${nf(p.margin)}<br><small class="muted">riesgo ${nf(p.risk_usd)} · peso ${nf(p.weight, 2)}</small></td>` +
      `<td class="num ${tone(u)}" data-upnl>${usd(u)} USDT<br><small>${pct(p.margin ? u / p.margin : null)}</small></td>` +
      `<td class="num"><span class="up">${px(p.tp)}</span> / <span class="down">${px(p.sl)}</span></td>` +
      `<td class="num">${utc(p.fill_t)}<br><small class="muted">hace ${dur(now - p.fill_t)}</small></td>` +
      `<td class="num">${utc(p.expire_t)}</td></tr>`
  }).join('')
  return `<div class="pp-scroll"><table class="pp-t"><thead><tr><th>Estrategia · lado</th><th>Tamaño</th><th>Entrada</th>` +
    `<th>Precio de marca</th><th>Liq. (aprox.)</th><th>Margen</th><th>PnL no realizado (ROE)</th><th>TP / SL</th>` +
    `<th>Abierta</th><th>Vence (por tiempo)</th></tr></thead><tbody>${rows}</tbody></table></div>` +
    '<p class="muted pp-note">Clic en una fila para ver su TP, SL y liquidación en el gráfico. Margen aislado; la liquidación es aproximada (sin importe de mantenimiento).</p>'
}

/** Actualiza en vivo la marca y el PnL sin rehacer la tabla. */
export function paintMarks(el: HTMLElement, ps: Position[], price: number): number {
  let total = 0
  for (const p of ps) {
    const u = upnlAt(p, price)
    total += u
    const row = el.querySelector<HTMLElement>(`tr[data-pos="${CSS.escape(p.id)}"]`)
    if (!row) continue
    row.querySelector('[data-mark]')!.textContent = px(price)
    const c = row.querySelector<HTMLElement>('[data-upnl]')!
    c.className = `num ${tone(u)}`
    c.innerHTML = `${usd(u)} USDT<br><small>${pct(p.margin ? u / p.margin : null)}</small>`
  }
  return total
}

export function ordersTable(os: Order[], names: Names, sym: string): string {
  if (!os.length) return '<p class="muted">Sin órdenes pendientes.</p>'
  const rows = os.map((o) => `<tr><td>${stratCell(o.sid, names, o.origin, o.timeframe, o.floor)}</td>` +
    `<td>${o.kind === 'limit' ? 'Límite' : 'Mercado'}</td><td>${sideCell(o.side, o.leverage)}</td>` +
    `<td class="num">${o.kind === 'limit' ? px(o.price) : 'a la apertura'}</td><td class="num">${qty(o.qty, sym)}</td>` +
    `<td class="num"><span class="up">${px(o.tp)}</span> / <span class="down">${px(o.sl)}</span></td>` +
    `<td class="num">${nf(o.margin)}</td><td class="num">${utc(o.t)}</td>` +
    `<td class="num">${o.expire_t ? utc(o.expire_t) : '—'}</td></tr>`).join('')
  return `<div class="pp-scroll"><table class="pp-t"><thead><tr><th>Estrategia</th><th>Tipo</th><th>Lado</th><th>Precio</th>` +
    `<th>Cantidad</th><th>TP / SL</th><th>Margen reservado</th><th>Colocada</th><th>Vence</th></tr></thead><tbody>${rows}</tbody></table></div>`
}

export interface HistFilter { strategy: string; result: 'all' | 'win' | 'loss'; limit: number }

export function historyTable(ts: PaperTrade[], names: Names, sym: string, f: HistFilter): string {
  const sel = ts.filter((t) => (f.strategy === '' || t.sid === f.strategy) &&
    (f.result === 'all' || (f.result === 'win' ? t.pnl > 0 : t.pnl <= 0)))
  const pnl = sel.reduce((a, t) => a + t.pnl, 0)
  const wins = sel.filter((t) => t.pnl > 0)
  const gain = wins.reduce((a, t) => a + t.pnl, 0), loss = -sel.filter((t) => t.pnl < 0).reduce((a, t) => a + t.pnl, 0)
  const opts = [...new Set(ts.map((t) => t.sid))].sort((a, b) => (names[a] ?? a).localeCompare(names[b] ?? b))
  const head = `<div class="pp-filters"><label>Estrategia <select data-hf="strategy"><option value="">Todas</option>` +
    opts.map((s) => `<option value="${esc(s)}"${s === f.strategy ? ' selected' : ''}>${esc(names[s] ?? s)}</option>`).join('') +
    `</select></label><label>Resultado <select data-hf="result"><option value="all">Todas</option>` +
    `<option value="win"${f.result === 'win' ? ' selected' : ''}>Ganadoras</option><option value="loss"${f.result === 'loss' ? ' selected' : ''}>Perdedoras</option></select></label>` +
    `<span class="pp-sum">${sel.length} operaciones · acierto ${pct0(sel.length ? wins.length / sel.length : null)} · ` +
    `PnL <b class="${tone(pnl)}">${usd(pnl)} USDT</b> · PF ${loss > 0 ? nf(gain / loss) : '—'}</span></div>`
  if (!sel.length) return head + '<p class="muted">Sin operaciones cerradas con este filtro.</p>'
  const rows = sel.slice(0, f.limit).map((t) => `<tr title="${esc(t.why.join(' · '))}">` +
    `<td class="num">${utc(t.fill_t)}<br><small class="muted">→ ${utc(t.exit_t)}</small></td>` +
    `<td>${stratCell(t.sid, names, t.origin, t.timeframe, t.floor)}<br><small class="muted">${t.kind === 'limit' ? 'límite' : 'mercado'}${t.regime ? ` · ${esc(t.regime)}` : ''}</small></td>` +
    `<td>${sideCell(t.side, t.leverage)}</td>` +
    `<td class="num">${px(t.fill)} → ${px(t.exit)}<br><small class="muted">${qty(t.qty, sym)}</small></td>` +
    `<td><span class="pp-reason" data-r="${t.reason}">${REASON[t.reason] ?? t.reason}</span>` +
    (t.cause ? `<br><small class="muted">${esc(CAUSE[t.cause] ?? t.cause)}</small>` : '') + '</td>' +
    `<td class="num ${tone(t.pnl)}"><b>${usd(t.pnl)}</b><br><small>${rr(t.r)} · ROE ${pct(t.roe, 1)}</small></td>` +
    `<td class="num"><small>com. ${nf(t.fees)} · desl. ${nf(t.slip)}<br>funding ${usd(t.funding)}${t.funding_assumed ? '*' : ''}</small></td>` +
    `<td class="num">${dur(t.exit_t - t.fill_t)}</td></tr>`).join('')
  const more = sel.length > f.limit ? `<button class="btn" data-more="hist">Ver ${Math.min(200, sel.length - f.limit)} más</button>` : ''
  return head + `<div class="pp-scroll"><table class="pp-t"><thead><tr><th>Entrada → salida (UTC)</th><th>Estrategia</th><th>Lado</th>` +
    `<th>Precio</th><th>Motivo</th><th>PnL neto (USDT)</th><th>Costos</th><th>Duración</th></tr></thead><tbody>${rows}</tbody></table></div>` +
    more + '<p class="muted pp-note">PnL neto de comisiones, deslizamiento y funding. * funding supuesto donde faltaba el dato real. Pasa el cursor por una fila para ver por qué se abrió.</p>'
}
