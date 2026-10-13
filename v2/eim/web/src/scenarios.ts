import type { ISeriesPrimitive, SeriesAttachedParameter, Time } from 'lightweight-charts'
import type { Candle, ForecastSet, Scenario, ScenarioId, TP } from './types'
import type { LayerEngine } from './layers'
import { cssVar } from './theme'

type Ctx = CanvasRenderingContext2D
interface Target { useMediaCoordinateSpace(f: (s: { context: Ctx; mediaSize: { width: number } }) => void): void }

export const SCEN_LABEL: Record<ScenarioId, string> = { bull: 'Alcista', neutral: 'Neutral', bear: 'Bajista' }
export const scenColor = (id: ScenarioId): string =>
  cssVar(id === 'bull' ? '--up' : id === 'bear' ? '--down' : '--neutral')

/**
 * Dibuja los tres escenarios (trayectoria mediana + banda + etiqueta de probabilidad)
 * o, en modo velas, la secuencia OHLC simulada del escenario elegido.
 * Cada trayectoria parte del último cierre real (`origin`).
 */
export class ScenarioLayer implements ISeriesPrimitive<Time> {
  private fs: ForecastSet | null = null
  private origin: { t: number; p: number } | null = null
  private redraw: () => void = () => {}
  selected: ScenarioId | null = null
  candlesMode = false

  constructor(private readonly eng: LayerEngine) {}

  attached(p: SeriesAttachedParameter<Time>): void { this.redraw = p.requestUpdate }
  detached(): void { this.redraw = () => {} }

  set(fs: ForecastSet | null, lastCandle: Candle | null): void {
    this.fs = fs
    this.origin = lastCandle ? { t: lastCandle.t, p: lastCandle.c } : null
    this.redraw()
  }
  setView(selected: ScenarioId | null, candles: boolean): void {
    this.selected = selected; this.candlesMode = candles; this.redraw()
  }
  requestRedraw(): void { this.redraw() }

  private pts(a: TP[]): [number, number][] | null {
    const o = this.origin
    const all: TP[] = o ? [[o.t, o.p], ...a] : a
    const out: [number, number][] = []
    for (const [t, p] of all) {
      const x = this.eng.x(t), y = this.eng.y(p)
      if (x == null || y == null) return null
      out.push([x, y])
    }
    return out
  }

  private band(ctx: Ctx, s: Scenario, col: string, alpha: number): void {
    const hi = this.pts(s.band_high), lo = this.pts(s.band_low)
    if (!hi || !lo) return
    ctx.globalAlpha = alpha; ctx.fillStyle = col
    ctx.beginPath(); hi.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
    for (const [x, y] of [...lo].reverse()) ctx.lineTo(x, y)
    ctx.closePath(); ctx.fill()
  }

  private line(ctx: Ctx, s: Scenario, col: string, alpha: number, w: number): void {
    const m = this.pts(s.path)
    if (!m) return
    ctx.globalAlpha = alpha; ctx.strokeStyle = col; ctx.lineWidth = w; ctx.setLineDash([])
    ctx.beginPath(); m.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke()
    const [x, y] = m[m.length - 1]
    const txt = `${SCEN_LABEL[s.id]} ${(s.probability * 100).toFixed(0)}%`
    const tw = ctx.measureText(txt).width + 10
    ctx.globalAlpha = Math.max(alpha, 0.5); ctx.fillStyle = col
    ctx.fillRect(x + 4, y - 8, tw, 16)
    ctx.fillStyle = cssVar('--panel'); ctx.fillText(txt, x + 9, y + 4)
  }

  private candles(ctx: Ctx, s: Scenario, col: string): void {
    const c0 = s.candles[0]
    if (!c0) return
    const step = s.candles.length > 1 ? s.candles[1].t - c0.t : 1
    const xa = this.eng.x(c0.t), xb = this.eng.x(c0.t + step)
    const w = Math.max(2, Math.abs((xb ?? 0) - (xa ?? 0)) * 0.6)
    const bg = cssVar('--panel')
    ctx.setLineDash([]); ctx.lineWidth = 1.2
    for (const c of s.candles) {
      const x = this.eng.x(c.t), yo = this.eng.y(c.o), yc = this.eng.y(c.c)
      const yh = this.eng.y(c.h), yl = this.eng.y(c.l)
      if (x == null || yo == null || yc == null || yh == null || yl == null) continue
      ctx.globalAlpha = 0.95; ctx.strokeStyle = col
      ctx.beginPath(); ctx.moveTo(x, yh); ctx.lineTo(x, yl); ctx.stroke()
      ctx.fillStyle = c.c >= c.o ? col : bg // cuerpo lleno = sube, hueco = baja
      const top = Math.min(yo, yc), h = Math.max(1.5, Math.abs(yo - yc))
      ctx.fillRect(x - w / 2, top, w, h); ctx.strokeRect(x - w / 2, top, w, h)
    }
    const last = s.candles[s.candles.length - 1]
    const x = this.eng.x(last.t), y = this.eng.y(last.h)
    if (x != null && y != null) {
      const txt = `${SCEN_LABEL[s.id]} · velas simuladas`
      const tw = ctx.measureText(txt).width + 10
      ctx.globalAlpha = 0.95; ctx.fillStyle = col; ctx.fillRect(x - tw, y - 24, tw, 16)
      ctx.fillStyle = cssVar('--panel'); ctx.fillText(txt, x - tw + 5, y - 12)
    }
  }

  private draw(ctx: Ctx): void {
    if (!this.fs || !this.eng.isOn('escenarios')) return
    ctx.save(); ctx.font = '11px system-ui, sans-serif'
    const sel = this.selected
    if (this.candlesMode) {
      const s = this.fs.scenarios.find((x) => x.id === (sel ?? 'neutral')) ?? this.fs.scenarios[0]
      this.band(ctx, s, scenColor(s.id), 0.08)
      this.candles(ctx, s, scenColor(s.id))
    } else {
      for (const s of this.fs.scenarios) {
        const dim = sel != null && sel !== s.id
        const col = scenColor(s.id)
        this.band(ctx, s, col, dim ? 0.04 : 0.14)
        this.line(ctx, s, col, dim ? 0.3 : 0.95, sel === s.id ? 3 : 2)
      }
    }
    ctx.restore()
  }

  paneViews(): { zOrder(): 'top'; renderer(): { draw(t: unknown): void } }[] {
    return [{
      zOrder: () => 'top' as const,
      renderer: () => ({
        draw: (t: unknown) => (t as Target).useMediaCoordinateSpace(({ context }) => this.draw(context)),
      }),
    }]
  }

  /** Datos que se están pintando (para verificar contra el contrato). */
  debug(): { start: { t: number; p: number } | null; probs: number[]; mode: string; selected: string | null } {
    return {
      start: this.origin, probs: this.fs?.scenarios.map((s) => s.probability) ?? [],
      mode: this.candlesMode ? 'velas' : 'trayectorias', selected: this.selected,
    }
  }
}
