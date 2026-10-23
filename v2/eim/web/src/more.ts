/** Vista "Más análisis": pestañas portadas del legado F7 (consumen `/v2/more/*`). */
import { esc } from './more_api'
import { backtestView, disposeCharts, multiAssetView, vwapView, type Ctx } from './more_market'
import { bitacoraView, liquidationsView, seasonalityView } from './more_other'

const TABS: [string, string][] = [
  ['backtest', 'Backtest / VRM'], ['vwap', 'VWAP por periodos'], ['multi', 'Multi-activo'],
  ['liq', 'Liquidaciones'], ['season', 'Estacionalidad'], ['journal', 'Bitácora de trading'],
]

export class MoreView {
  private tab = 'backtest'
  private ctx: Ctx = { symbol: 'BTCUSDT', tf: '1h' }
  private open = false

  constructor(private root: HTMLElement) {
    root.innerHTML = `<nav class="tabs" id="more-tabs">${TABS.map(([id, t]) =>
      `<button data-t="${id}" aria-selected="${id === this.tab}">${esc(t)}</button>`).join('')}</nav>
      <div id="more-body" class="more-body"></div>`
    root.querySelector<HTMLElement>('#more-tabs')!.onclick = (e) => {
      const b = (e.target as HTMLElement).closest('button')
      if (!b) return
      this.tab = b.dataset.t!
      root.querySelectorAll('#more-tabs button').forEach((x) => x.setAttribute('aria-selected', String(x === b)))
      void this.render()
    }
  }

  setContext(symbol: string, tf: string): void {
    this.ctx = { symbol, tf }
    if (this.open) void this.render()
  }

  toggle(show: boolean): void {
    this.open = show
    this.root.hidden = !show
    document.getElementById('app')!.dataset.view = show ? 'more' : 'desk'
    if (show) void this.render(); else disposeCharts()
  }

  private async render(): Promise<void> {
    const body = this.root.querySelector<HTMLElement>('#more-body')!
    const mine = this.tab
    disposeCharts()
    body.innerHTML = '<p class="muted">Cargando…</p>'
    try {
      if (mine === 'backtest') await backtestView(body, this.ctx)
      else if (mine === 'vwap') await vwapView(body, this.ctx)
      else if (mine === 'multi') await multiAssetView(body)
      else if (mine === 'liq') await liquidationsView(body, this.ctx)
      else if (mine === 'season') await seasonalityView(body)
      else bitacoraView(body)
    } catch (e) {
      body.innerHTML = `<div class="alert bad">${esc((e as Error).message)}</div>`
    }
  }
}
