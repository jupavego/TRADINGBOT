import {
  ColorType, createChart, createSeriesMarkers, LineSeries, LineStyle, MismatchDirection,
  type IChartApi, type IPriceLine, type ISeriesApi, type ISeriesMarkersPluginApi, type SeriesMarker,
  type Time, type UTCTimestamp,
} from 'lightweight-charts'
import { PriceChart } from './chart'
import { cssVar } from './theme'
import { esc, nf, pct, phaseLabel, rr, side, tone, utc } from './paper_fmt'
import type { PaperTrade, Position, ProfileView } from './paper_types'
import { chartTimeLocale } from './tz'

const sec = (t: number): UTCTimestamp => Math.floor(t / 1000) as UTCTimestamp
const MAX_MARKS = 400
/** Color de cada perfil: sigue a la entidad (orden fijo), nunca al ranking. */
export const PROFILE_VAR: Record<string, string> = { conservador: '--p1', moderado: '--p2', agresivo: '--p3', ppp_btcusdt: '--p4' }

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
      if (p.tp !== null) add(p.tp, cssVar('--up'), 'TP sim')
      add(p.sl, cssVar('--down'), p.ladder?.exit ? `SL dinámico (${phaseLabel(p.ladder.exit.phase)})`
        : p.ladder ? `SL dinámico (esc. ${p.ladder.level})` : 'SL sim')
      add(p.liq, cssVar('--warn'), 'Liq. sim', LineStyle.Dotted)
    }
  }

  destroy(): void { this.pc.destroy() }
}

/** Curvas de capital de todos los perfiles en un solo eje (USDT). Las curvas no llevan el nombre encima
 * (tapaba las líneas): el eje muestra solo el último valor y la leyenda lateral da nombre, valor y cambio
 * frente al capital inicial. Cursor sobre un perfil → resalta su curva; clic → la oculta o la muestra. */
export class EquityChart {
  private chart: IChartApi
  private series = new Map<string, ISeriesApi<'Line'>>()
  private names = new Map<string, string>()
  private initial = new Map<string, number>()
  private last = new Map<string, number>()
  private hidden = new Set<string>()
  private hot: string | null = null
  private base: { s: ISeriesApi<'Line'>; line: IPriceLine }[] = []
  private items = new Map<string, HTMLButtonElement>()

  constructor(el: HTMLElement, private legend: HTMLElement) {
    this.chart = createChart(el, {
      autoSize: true, handleScale: false, handleScroll: false,
      localization: chartTimeLocale.localization,
      // Sin desplazamiento: al cambiar de tamaño se conserva el tramo completo (no se queda arrinconado).
      timeScale: { timeVisible: true, secondsVisible: false, borderVisible: false, lockVisibleTimeRangeOnResize: true, ...chartTimeLocale.timeScale },
      rightPriceScale: { borderVisible: false },
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, fontFamily: 'inherit', fontSize: 11 },
      crosshair: { horzLine: { visible: false, labelVisible: false } },
    })
    this.chart.subscribeCrosshairMove((p) => {
      const vals = new Map<string, number>()
      // Cada curva da su último valor conocido en ese instante (no el actual: sus puntos no coinciden en el tiempo).
      const at = p.time !== undefined && p.logical !== undefined ? Math.round(p.logical) : null
      for (const [id, s] of this.series) {
        const d = at !== null ? s.dataByIndex(at, MismatchDirection.NearestLeft) as { value?: number } | null : null
        vals.set(id, at !== null ? d?.value ?? NaN : this.last.get(id) ?? NaN)
      }
      this.paintLegend(vals, p.time !== undefined ? Number(p.time) * 1000 : null)
    })
    const pick = (e: Event): string | null => (e.target as HTMLElement).closest<HTMLElement>('[data-eq]')?.dataset.eq ?? null
    legend.addEventListener('click', (e) => { const id = pick(e); if (id) this.toggle(id) })
    legend.addEventListener('mouseover', (e) => this.setHot(pick(e)))
    legend.addEventListener('focusin', (e) => this.setHot(pick(e)))
    legend.addEventListener('mouseleave', () => this.setHot(null))
    legend.addEventListener('focusout', () => this.setHot(null))
    this.applyColors()
  }

  set(profiles: ProfileView[]): void {
    const ids = new Set(profiles.map((p) => p.id))
    this.clearBase()
    for (const [id, s] of this.series) {
      if (ids.has(id)) continue
      this.chart.removeSeries(s)
      for (const m of [this.series, this.names, this.initial, this.last]) m.delete(id)
      this.hidden.delete(id)
    }
    for (const p of profiles) {
      let s = this.series.get(p.id)
      if (!s) {
        s = this.chart.addSeries(LineSeries, { lineWidth: 2, priceLineVisible: false, lastValueVisible: true })
        this.series.set(p.id, s)
      }
      const pts = dedupe(p.curve)
      s.setData(pts.map(([t, v]) => ({ time: sec(t), value: v })))
      this.names.set(p.id, p.name)
      this.initial.set(p.id, p.initial)
      this.last.set(p.id, pts.length ? pts[pts.length - 1][1] : p.equity)
    }
    this.style()
    this.chart.timeScale().fitContent()
    this.paintLegend(this.last, null)
  }

  /** Oculta o muestra una curva; siempre queda al menos una a la vista. */
  private toggle(id: string): void {
    if (this.hidden.has(id)) this.hidden.delete(id)
    else if (this.series.size - this.hidden.size > 1) this.hidden.add(id)
    this.style()
    this.marks()
  }

  private setHot(id: string | null): void {
    if (id === this.hot) return
    this.hot = id
    this.style()
    this.marks()
  }

  /** Visibilidad, grosor y atenuación de cada curva según la leyenda. */
  private style(): void {
    const hot = this.hot !== null && !this.hidden.has(this.hot) ? this.hot : null // resaltar una oculta no atenúa al resto
    for (const [id, s] of this.series) {
      const c = cssVar(PROFILE_VAR[id] ?? '--accent')
      const dim = hot !== null && hot !== id
      s.applyOptions({ visible: !this.hidden.has(id), color: dim ? fade(c) : c, lineWidth: hot === id ? 3 : 2 })
    }
    this.clearBase()
    // Capital inicial: una línea punteada por valor distinto, colgada de una curva visible.
    const seen = new Set<number>()
    for (const [id, s] of this.series) {
      const ini = this.initial.get(id)
      if (this.hidden.has(id) || ini === undefined || !(ini > 0) || seen.has(ini)) continue
      seen.add(ini)
      this.base.push({ s, line: s.createPriceLine({
        price: ini, color: cssVar('--muted'), lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '',
      }) })
    }
  }

  private clearBase(): void {
    for (const { s, line } of this.base) s.removePriceLine(line)
    this.base = []
  }

  /** Crea los botones de la leyenda solo cuando cambian los perfiles (conserva el foco entre refrescos). */
  private ensureItems(): void {
    if ([...this.items.keys()].join() === [...this.names.keys()].join()) return
    this.legend.innerHTML = [...this.names].map(([id, name]) =>
      `<button type="button" class="pp-eqi" data-eq="${esc(id)}" style="--pc:var(${PROFILE_VAR[id] ?? '--accent'})"` +
      ` title="${esc(name)} · clic para ocultar o mostrar su curva"><i></i><span>${esc(name)}</span>` +
      '<b class="num"></b><small class="num"></small></button>').join('') + '<small class="muted pp-eqt"></small>'
    this.items = new Map([...this.legend.querySelectorAll<HTMLButtonElement>('[data-eq]')].map((b) => [b.dataset.eq!, b]))
  }

  private marks(): void {
    for (const [id, b] of this.items) {
      b.setAttribute('aria-pressed', String(!this.hidden.has(id)))
      b.dataset.hot = String(this.hot === id)
    }
  }

  private paintLegend(vals: Map<string, number>, t: number | null): void {
    if (!this.names.size) return // el gráfico emite eventos del cursor antes de recibir datos
    this.ensureItems()
    for (const [id, b] of this.items) {
      const v = vals.get(id) ?? NaN, ini = this.initial.get(id) ?? NaN
      const d = Number.isFinite(v) && ini > 0 ? v / ini - 1 : null
      b.querySelector('b')!.textContent = Number.isFinite(v) ? nf(v) : '—'
      const s = b.querySelector('small')!
      s.textContent = pct(d)
      s.className = `num ${tone(d)}`
    }
    this.marks()
    this.legend.querySelector('.pp-eqt')!.textContent = t ? `${utc(t)} COT` : 'último valor de cada curva'
  }

  private applyColors(): void {
    this.chart.applyOptions({
      layout: { textColor: cssVar('--muted') },
      grid: { vertLines: { visible: false }, horzLines: { color: cssVar('--grid') } },
    })
  }

  destroy(): void { this.chart.remove() }
}

/** Color atenuado para las curvas que no están resaltadas (hex de 6 dígitos + alfa). */
const fade = (c: string): string => (/^#[0-9a-f]{6}$/i.test(c) ? `${c}4d` : c)

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
