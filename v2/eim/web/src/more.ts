/** Análisis portados del legado F7 (consumen `/v2/more/*`).
 *
 * T185: VWAP por periodos, liquidaciones, estacionalidad y multi-activo dejan de ser pestañas: son
 * la lupa de su esfera en el río (el mismo cálculo que el agente, con más detalle). Se abren en un
 * diálogo desde el detalle del agente («Ver en detalle»). Solo queda como pestaña la Bitácora de
 * trading, que es documental (analiza el archivo real de Binance que sube el usuario). El
 * backtest/VRM salió (lo vivo manda, T182). Al cerrar la lupa se liberan sus gráficos. */
import { esc } from './more_api'
import { disposeCharts, multiAssetView, vwapView, type Ctx } from './more_market'
import { bitacoraView, liquidationsView, seasonalityView } from './more_other'

/** ids de los paneles (`.tabbody`) en index.html; etiquetas solo como referencia. */
export const MORE_TABS: [string, string][] = [['t-tjournal', 'Bitácora de trading']]

type View = (el: HTMLElement, ctx: Ctx) => Promise<void>
/** Agente del río → título y vista de su lupa. */
export const LUPA: Record<string, [string, View]> = {
  vwap: ['VWAP por periodos', vwapView],
  liquidations: ['Liquidaciones', liquidationsView],
  seasonality: ['Estacionalidad', (el) => seasonalityView(el)],
  intermarket: ['Intermercado · multi-activo', (el) => multiAssetView(el)],
}
export const hasLupa = (id: string): boolean => id in LUPA

export class MoreTabs {
  private active: string | null = null
  private ctx: Ctx = { symbol: 'BTCUSDT', tf: '1h' }
  private lupaId: string | null = null

  constructor() {
    const dlg = document.getElementById('lupa') as HTMLDialogElement | null
    if (dlg) {
      dlg.addEventListener('click', (e) => {
        const r = dlg.getBoundingClientRect()   // clic en el fondo (fuera del recuadro) o en «×»
        const out = e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom
        if (out || (e.target as HTMLElement).closest('[data-lupa-close]')) dlg.close()
      })
      dlg.addEventListener('close', () => this.closeLupa())
    }
  }

  setContext(symbol: string, tf: string): void {
    this.ctx = { symbol, tf }
    if (this.active) void this.render(this.active)
    if (this.lupaId) void this.openLupa(this.lupaId)
  }

  /** Llamar en cada cambio de pestaña inferior (sea o no de este grupo). */
  show(tab: string): void {
    const mine = MORE_TABS.some(([id]) => id === tab)
    if (this.active && this.active !== tab) {
      const prev = document.getElementById(this.active)
      if (prev) prev.innerHTML = ''
    }
    this.active = mine ? tab : null
    if (mine) void this.render(tab)
  }

  /** Abre la lupa de un agente (si tiene) en el diálogo `#lupa`. */
  async openLupa(id: string): Promise<void> {
    const entry = LUPA[id]
    const dlg = document.getElementById('lupa') as HTMLDialogElement | null
    const body = document.getElementById('lupa-b')
    const title = document.getElementById('lupa-t')
    if (!entry || !dlg || !body || !title) return
    disposeCharts()
    this.lupaId = id
    title.textContent = `${entry[0]} · ${this.ctx.symbol} ${this.ctx.tf}`
    body.innerHTML = '<p class="muted">Cargando…</p>'
    if (!dlg.open) dlg.showModal()
    try {
      await entry[1](body, this.ctx)
    } catch (e) {
      if (this.lupaId === id) body.innerHTML = `<div class="alert bad">${esc((e as Error).message)}</div>`
    }
  }

  private closeLupa(): void {
    disposeCharts()
    this.lupaId = null
    const body = document.getElementById('lupa-b')
    if (body) body.innerHTML = ''
  }

  private async render(tab: string): Promise<void> {
    const body = document.getElementById(tab)
    if (!body) return
    body.innerHTML = '<p class="muted">Cargando…</p>'
    try {
      bitacoraView(body)
    } catch (e) {
      if (this.active === tab) body.innerHTML = `<div class="alert bad">${esc((e as Error).message)}</div>`
    }
  }
}
