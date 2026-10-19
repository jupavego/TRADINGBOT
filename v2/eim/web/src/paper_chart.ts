import {
  ColorType, createChart, createSeriesMarkers, LineSeries, LineStyle,
  type IChartApi, type IPriceLine, type ISeriesApi, type ISeriesMarkersPluginApi, type SeriesMarker,
  type Time, type UTCTimestamp,
} from 'lightweight-charts'
import { PriceChart } from './chart'
import { cssVar } from './theme'
import { esc, nf, rr, side } from './paper_fmt'
import type { PaperTrade, Position, ProfileView } from './paper_types'

const sec = (t: number): UTCTimestamp => Math.floor(t / 1000) as UTCTimestamp
const MAX_MARKS = 400
/** Color de cada perfil: sigue a la entidad (orden fijo), nunca al ranking. */
export const PROFILE_VAR: Record<string, string> = { conservador: '--p1', moderado: '--p2', agresivo: '--p3' }

/** Velas de 1 h con entradas/salidas del perfil elegido y líneas de las posiciones abiertas. */
export class PaperPriceChart {
  readonly pc: PriceChart
  private marks: ISeriesMarkersPluginApi<Time>
  private lines: IPriceLine[] = []

  constructor(el: HTMLElement) {
    this.pc = new PriceChart(el)
    this.marks = createSeriesMarkers(this.pc.series, [])
  }

  setTrades(trades: PaperTrade[], open: Position[]): void {
    const up = cssVar('--up'), down = cssVar('--down'), muted = cssVar('--muted')
    const ms: SeriesMarker<UTCTimestamp>[] = []
    for (const t of trades.slice(0, MAX_MARKS)) {
      const long = t.side > 0
      ms.push({ time: sec(t.fill_t), position: long ? 'belowBar' : 'aboveBar', shape: long ? 'arrowUp' : 'arrowDown', color: long ? up : down, text: '' })
      ms.push({
        time: sec(t.exit_t), position: long ? 'aboveBar' : 'belowBar', shape: 'circle',
        color: t.pnl > 0 ? up : t.reason === 'SL' ? down : muted, text: `${t.reason} ${rr(t.r, 1)}`,
      })
    }
    for (const p of open) {
      ms.push({ time: sec(p.fill_t), position: p.side > 0 ? 'belowBar' : 'aboveBar', shape: p.side > 0 ? 'arrowUp' : 'arrowDown', color: cssVar('--accent'), text: `abierta ${p.timeframe}${p.floor ? ' · mín.' : ''}` })
    }
    ms.sort((a, b) => (a.time as number) - (b.time as number))
    this.marks.setMarkers(ms)
  }

  /** Líneas de entrada de las abiertas; TP/SL/liq. solo de la posición enfocada. */
  setLines(open: Position[], focus: string | null): void {
    for (const l of this.lines) this.pc.series.removePriceLine(l)
    this.lines = []
    const add = (price: number, color: string, title: string, style = LineStyle.Dashed): void => {
      this.lines.push(this.pc.series.createPriceLine({ price, color, title, lineWidth: 1, lineStyle: style, axisLabelVisible: true }))
    }
    for (const p of open) {
      const on = p.id === focus
      add(p.entry, cssVar('--accent'), `${side(p.side)} ${p.timeframe} ${on ? '' : p.strategy}`.trim(), on ? LineStyle.Solid : LineStyle.Dotted)
      if (!on) continue
      add(p.tp, cssVar('--up'), 'TP sim')
      add(p.sl, cssVar('--down'), 'SL sim')
      add(p.liq, cssVar('--warn'), 'Liq. sim', LineStyle.Dotted)
    }
  }

  restyle(): void { this.pc.restyle() }
  destroy(): void { this.pc.destroy() }
}

/** Curvas de capital de los 3 perfiles: un solo eje (USDT), leyenda con valor y etiqueta directa. */
export class EquityChart {
  private chart: IChartApi
  private series = new Map<string, ISeriesApi<'Line'>>()
  private names = new Map<string, string>()
  private last = new Map<string, number>()

  constructor(el: HTMLElement, private legend: HTMLElement) {
    this.chart = createChart(el, {
      autoSize: true, handleScale: false, handleScroll: false,
      timeScale: { timeVisible: true, secondsVisible: false, borderVisible: false },
      rightPriceScale: { borderVisible: false },
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, fontFamily: 'inherit', fontSize: 11 },
      crosshair: { horzLine: { visible: false, labelVisible: false } },
    })
    this.chart.subscribeCrosshairMove((p) => {
      const vals = new Map<string, number>()
      for (const [id, s] of this.series) {
        const d = p.time !== undefined ? p.seriesData.get(s) as { value?: number } | undefined : undefined
        vals.set(id, d?.value ?? this.last.get(id) ?? NaN)
      }
      this.paintLegend(vals, p.time !== undefined ? Number(p.time) * 1000 : null)
    })
    this.restyle()
  }

  set(profiles: ProfileView[]): void {
    for (const p of profiles) {
      let s = this.series.get(p.id)
      if (!s) {
        s = this.chart.addSeries(LineSeries, { lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: p.name })
        this.series.set(p.id, s)
      }
      s.applyOptions({ color: cssVar(PROFILE_VAR[p.id] ?? '--accent') })
      const pts = dedupe(p.curve)
      s.setData(pts.map(([t, v]) => ({ time: sec(t), value: v })))
      this.names.set(p.id, p.name)
      this.last.set(p.id, pts.length ? pts[pts.length - 1][1] : p.equity)
    }
    this.chart.timeScale().fitContent()
    this.paintLegend(this.last, null)
  }

  private paintLegend(vals: Map<string, number>, t: number | null): void {
    this.legend.innerHTML = [...this.names].map(([id, name]) =>
      `<span><i style="background:var(${PROFILE_VAR[id] ?? '--accent'})"></i>${esc(name)} <b class="num">${Number.isFinite(vals.get(id)) ? nf(vals.get(id)!) : '—'}</b></span>`).join('') +
      `<small class="muted">${t ? new Date(t).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' : 'capital realizado + no realizado (USDT)'}</small>`
  }

  restyle(): void {
    this.chart.applyOptions({
      layout: { textColor: cssVar('--muted') },
      grid: { vertLines: { visible: false }, horzLines: { color: cssVar('--grid') } },
    })
    for (const [id, s] of this.series) s.applyOptions({ color: cssVar(PROFILE_VAR[id] ?? '--accent') })
  }

  destroy(): void { this.chart.remove() }
}

/** Lightweight Charts exige tiempos estrictamente crecientes: se queda el último por segundo. */
function dedupe(curve: [number, number][]): [number, number][] {
  const out: [number, number][] = []
  for (const [t, v] of curve) {
    const s = Math.floor(t / 1000)
    if (out.length && Math.floor(out[out.length - 1][0] / 1000) >= s) out[out.length - 1] = [out[out.length - 1][0], v]
    else out.push([t, v])
  }
  return out
}
