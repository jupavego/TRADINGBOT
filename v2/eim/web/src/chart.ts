import {
  CandlestickSeries, ColorType, CrosshairMode, createChart,
  type CandlestickData, type IChartApi, type ISeriesApi, type UTCTimestamp,
} from 'lightweight-charts'
import type { Candle } from './types'
import { cssVar } from './theme'

const toBar = (c: Candle): CandlestickData<UTCTimestamp> => ({
  time: Math.floor(c.t / 1000) as UTCTimestamp, open: c.o, high: c.h, low: c.l, close: c.c,
})

/** Gráfico de velas. El tiempo del contrato está en ms; Lightweight Charts usa segundos. */
export class PriceChart {
  readonly chart: IChartApi
  readonly series: ISeriesApi<'Candlestick'>

  constructor(el: HTMLElement) {
    this.chart = createChart(el, {
      autoSize: true,
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { timeVisible: true, secondsVisible: false, rightOffset: 6 },
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, fontFamily: 'inherit' },
    })
    this.series = this.chart.addSeries(CandlestickSeries, {})
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
    this.series.applyOptions({
      upColor: up, downColor: down, borderUpColor: up, borderDownColor: down,
      wickUpColor: up, wickDownColor: down,
    })
  }

  setData(candles: Candle[], forming: Candle | null): void {
    const last = candles.length ? candles[candles.length - 1].t : -1
    const all = forming && forming.t > last ? [...candles, forming] : candles
    this.series.setData(all.map(toBar))
    const n = all.length
    this.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 90), to: n + 6 })
  }

  /** Vela en formación o cierre: `update` reemplaza la barra del mismo tiempo o añade una nueva. */
  update(c: Candle): void { this.series.update(toBar(c)) }

  destroy(): void { this.chart.remove() }
}
