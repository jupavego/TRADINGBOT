import {
  CandlestickSeries, ColorType, CrosshairMode, createChart,
  type CandlestickData, type IChartApi, type ISeriesApi, type UTCTimestamp,
} from 'lightweight-charts'
import type { Candle } from './types'
import { cssVar } from './theme'
import { LayerEngine } from './layers'
import { ScenarioLayer } from './scenarios'
import { chartTimeLocale } from './tz'

const toBar = (c: Candle): CandlestickData<UTCTimestamp> => ({
  time: Math.floor(c.t / 1000) as UTCTimestamp, open: c.o, high: c.h, low: c.l, close: c.c,
})

/** Gráfico de velas. El tiempo del contrato está en ms; Lightweight Charts usa segundos. */
export class PriceChart {
  readonly chart: IChartApi
  readonly series: ISeriesApi<'Candlestick'>
  readonly layers = new LayerEngine()
  readonly scen = new ScenarioLayer(this.layers)
  private lastT = -1
  private count = 0

  constructor(el: HTMLElement) {
    this.chart = createChart(el, {
      autoSize: true,
      crosshair: { mode: CrosshairMode.Normal },
      localization: chartTimeLocale.localization,
      timeScale: { timeVisible: true, secondsVisible: false, rightOffset: 6, ...chartTimeLocale.timeScale },
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, fontFamily: 'inherit' },
    })
    this.series = this.chart.addSeries(CandlestickSeries, {})
    this.series.attachPrimitive(this.layers)
    this.series.attachPrimitive(this.scen)
    this.restyle()
  }

  /** Relee los tokens CSS (se llama al cambiar de tema). */
  restyle(): void {
    const up = cssVar('--up'), down = cssVar('--down')
    this.chart.applyOptions({
      layout: { textColor: cssVar('--muted') },
      grid: { vertLines: { color: cssVar('--grid') }, horzLines: { color: cssVar('--grid') } },
      rightPriceScale: { borderColor: cssVar('--line') },
      timeScale: { borderColor: cssVar('--line') },
    })
    this.layers.requestRedraw(); this.scen.requestRedraw()
    this.series.applyOptions({
      upColor: up, downColor: down, borderUpColor: up, borderDownColor: down,
      wickUpColor: up, wickDownColor: down,
    })
  }

  setData(candles: Candle[], forming: Candle | null): void {
    const last = candles.length ? candles[candles.length - 1].t : -1
    const all = forming && forming.t > last ? [...candles, forming] : candles
    this.series.setData(all.map(toBar))
    this.layers.setTimes(all.map((c) => c.t))
    this.scen.requestRedraw()
    this.lastT = all.length ? all[all.length - 1].t : -1
    const n = this.count = all.length
    this.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 90), to: n + 6 })
  }

  /** Vela en formación o cierre: `update` reemplaza la barra del mismo tiempo o añade una nueva. */
  update(c: Candle): void {
    this.series.update(toBar(c))
    if (c.t > this.lastT) { this.lastT = c.t; this.layers.pushTime(c.t) }
  }

  /** Deja espacio a la derecha para ver la proyección de `h` velas. */
  makeRoom(h: number): void {
    const n = this.count
    if (n) this.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 90), to: n + h + 3 })
  }

  destroy(): void { this.chart.remove() }
}
