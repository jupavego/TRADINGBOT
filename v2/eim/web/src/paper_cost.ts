/** T143 (4): costo vivido del libro fijo, por operación y acumulado, y la puerta de marcos por costo. */
import { esc, nf } from './paper_fmt'
import type { CostBlock, CostPanel } from './paper_types'

const r3 = (x: number | null): string => (x === null ? '—' : `${nf(x, 3)} R`)

function row(label: string, b: CostBlock): string {
  return `<tr><th scope="row">${esc(label)}</th><td class="num">${b.n}</td><td class="num">${nf(b.cost_usdt, 0)}</td>` +
    `<td class="num">${b.cost_bps_mean === null ? '—' : nf(b.cost_bps_mean, 1)}</td><td class="num">${r3(b.cost_r_mean)}</td>` +
    `<td class="num">${b.cost_r_sum === null ? '—' : `${nf(b.cost_r_sum, 1)} R`}</td></tr>`
}

function gate(c: CostPanel): string {
  if (!c.timeframes?.length) return ''
  const xs = c.timeframes.map((t) =>
    `<li data-k="${t.admitted ? 'win' : 'loss'}"><b>${esc(t.timeframe)}</b> ${t.admitted ? 'opera' : 'no opera'} · ` +
    `costo ${r3(t.cost_r)} frente a un umbral de ${nf(t.max_cost_r, 2)} R <small class="muted">(${esc(t.source)})</small></li>`).join('')
  return `<p class="muted">Marcos: el que cuesta ${nf(c.timeframes[0].max_cost_r, 2)} R o más no opera en los perfiles; la sombra lo sigue midiendo y vuelve solo si abarata.</p>` +
    `<ul class="pp-bal-fb">${xs}</ul>`
}

export function costView(c: CostPanel | undefined): string {
  if (!c) return ''
  const a = c.all
  const body = a.n
    ? `<table class="pp-cost"><thead><tr><th></th><th>Ops</th><th>USDT</th><th>pb nocional</th><th>R por operación</th><th>R acumulado</th></tr></thead><tbody>` +
      row('Todas', a) + Object.entries(c.by_timeframe).map(([k, b]) => row(`Marco ${k}`, b)).join('') +
      Object.entries(c.by_kind).map(([k, b]) => row(`Entrada ${k}`, b)).join('') + '</tbody></table>'
    : '<p class="muted">Sin operaciones de perfil vividas todavía.</p>'
  const last = c.recent.length
    ? `<p class="muted">Última: ${esc(c.recent[0].profile)} · ${esc(c.recent[0].timeframe)} · ${esc(c.recent[0].kind)} → ${nf(c.recent[0].cost_usdt, 2)} USDT · ${r3(c.recent[0].cost_r)}</p>`
    : ''
  return `<section class="pp-cost-box"><h4 class="sh">Costo medido · comisiones + deslizamiento + funding</h4>${body}${last}` +
    `<small class="muted">Fuente: ${esc(c.source)}</small>${gate(c)}</section>`
}
