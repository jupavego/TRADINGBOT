/** Leyenda de «Capital por perfil»: es también el selector de perfil y resume cada cuenta en dos líneas
 * (sustituye a las tarjetas de perfil). Clic en el perfil → lo elige (velas, cuenta y pestañas lo siguen);
 * la línea de color → oculta o muestra su curva. */
import { esc, nf, pct0 } from './paper_fmt'
import type { ProfileView } from './paper_types'

/** Marco de un perfil; nombre, cifras y métricas se rellenan con `legendFill` y `EquityChart.paintLegend`. */
export function legendItem(id: string, name: string, colorVar: string): string {
  const n = esc(name)
  return `<div class="pp-eqi" data-eq="${esc(id)}" style="--pc:var(${colorVar})">` +
    `<button type="button" class="pp-eqv" data-eqv aria-pressed="true" aria-label="Curva de ${n} en el gráfico" title="Ocultar o mostrar la curva de ${n}"><i></i></button>` +
    `<button type="button" class="pp-eqs" data-prof="${esc(id)}" title="${n} · clic para ver sus velas, operaciones y cuenta">` +
    '<span class="pp-eqn"></span><b class="num" data-v title="Capital = saldo realizado + PnL no realizado"></b>' +
    '<small class="num" data-d title="Frente al capital inicial"></small><small class="pp-eqm muted"></small><small class="pp-eqm muted"></small></button></div>'
}

/** Nombre (con aviso de cuenta agotada) y las dos líneas de métricas que antes llevaban las tarjetas. */
export function legendFill(item: HTMLElement, p: ProfileView): void {
  item.querySelector('.pp-eqn')!.innerHTML = esc(p.name) +
    (p.exhausted ? ' <span class="pp-live down" title="Capital agotado: no abre más posiciones">agotada</span>' : '')
  const [a, b] = item.querySelectorAll('.pp-eqm')
  const ops = `${p.n_closed} ops${p.counts?.liquidations ? ` · ${p.counts.liquidations} liquidadas` : ''}`
  a.innerHTML = chunks([ops, `acierto ${pct0(p.win_rate)}`, `PF ${p.pf === null ? '—' : nf(p.pf)}`,
    `<span title="Máximo descenso de la curva de capital (equity), todo el periodo">DD máx. ${pct0(p.max_dd_pct)}</span>`])
  b.innerHTML = chunks([`${p.positions.length} abiertas`, `${p.orders.length} órdenes`,
    `riesgo ${nf(Number(p.params.risk_pct) * 100, 1)} %`, `hasta ${p.params.max_leverage}x`])
}

/** Cada dato en un bloque que no se parte: si no cabe, salta entero a la línea siguiente. */
const chunks = (xs: string[]): string => xs.map((x) => `<span>${x}</span>`).join(' · ')
