/** Análisis portados del legado F7 (consumen `/v2/more/*`). Antes vivían en la vista aparte
 * «Más análisis»; ahora son pestañas de la mesa, junto a Escenarios, Calibración, Plan…
 * Solo se pinta la pestaña activa: al salir se vacía y se liberan sus gráficos. */
import { esc } from './more_api'
import { backtestView, disposeCharts, multiAssetView, vwapView, type Ctx } from './more_market'
import { bitacoraView, liquidationsView, seasonalityView } from './more_other'

/** ids de los paneles (`.tabbody`) en index.html; etiquetas solo como referencia. */
export const MORE_TABS: [string, string][] = [
  ['t-bt', 'Backtest / VRM'], ['t-vwap', 'VWAP por periodos'], ['t-multi', 'Multi-activo'],
  ['t-liq', 'Liquidaciones'], ['t-season', 'Estacionalidad'], ['t-tjournal', 'Bitácora de trading'],
]

export class MoreTabs {
  private active: string | null = null
  private ctx: Ctx = { symbol: 'BTCUSDT', tf: '1h' }

  setContext(symbol: string, tf: string): void {
    this.ctx = { symbol, tf }
    if (this.active) void this.render(this.active)
  }

  /** Llamar en cada cambio de pestaña inferior (sea o no de este grupo). */
  show(tab: string): void {
    const mine = MORE_TABS.some(([id]) => id === tab)
    if (this.active && this.active !== tab) {
      disposeCharts()
      const prev = document.getElementById(this.active)
      if (prev) prev.innerHTML = ''
    }
    this.active = mine ? tab : null
    if (mine) void this.render(tab)
  }

  private async render(tab: string): Promise<void> {
    const body = document.getElementById(tab)
    if (!body) return
    disposeCharts()
    body.innerHTML = '<p class="muted">Cargando…</p>'
    try {
      if (tab === 't-bt') await backtestView(body, this.ctx)
      else if (tab === 't-vwap') await vwapView(body, this.ctx)
      else if (tab === 't-multi') await multiAssetView(body)
      else if (tab === 't-liq') await liquidationsView(body, this.ctx)
      else if (tab === 't-season') await seasonalityView(body)
      else bitacoraView(body)
    } catch (e) {
      if (this.active === tab) body.innerHTML = `<div class="alert bad">${esc((e as Error).message)}</div>`
    }
  }
}
