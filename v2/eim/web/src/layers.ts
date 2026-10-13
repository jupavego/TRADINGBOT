import type { IChartApi, ISeriesApi, ISeriesPrimitive, SeriesAttachedParameter, Time } from 'lightweight-charts'
import type { Overlay } from './types'
import { cssVar } from './theme'

export type LayerId = 'ninguna' | 'canal' | 'niveles' | 'plan' | 'vwap' | 'liq' | 'elliott' | 'escenarios'

export const LAYERS: { id: LayerId; label: string; on: boolean }[] = [
  { id: 'canal', label: 'Canal', on: true },
  { id: 'niveles', label: 'Niveles', on: true },
  { id: 'plan', label: 'Plan', on: true },
  { id: 'escenarios', label: 'Escenarios', on: true },
  { id: 'vwap', label: 'VWAP', on: false },
  { id: 'liq', label: 'Liquidaciones', on: false },
  { id: 'elliott', label: 'Elliott', on: false },
]

/** Capa a la que pertenece un overlay (por agente y tipo). */
export function layerOf(o: Overlay): LayerId {
  if (o.agent_id === 'vwap') return 'vwap'
  if (o.agent_id === 'liquidations') return 'liq'
  if (o.agent_id === 'elliott') return 'elliott'
  if (o.kind === 'channel' || o.kind === 'range') return 'canal'
  if (o.kind === 'trade_plan') return 'plan'
  return o.agent_id === 'levels' ? 'niveles' : 'ninguna' // otros agentes: sin capa propia aún
}

type Pt = [number, number]
const num = (v: unknown): number => Number(v)
const pts = (v: unknown): Pt[] => (Array.isArray(v) ? (v as Pt[]) : [])

/** Forma ya en píxeles, usada para dibujar y para el hover. */
interface Shape { ov: Overlay; kind: 'band' | 'line' | 'chan' | 'plan'; x0: number; x1: number; ys: number[]; ch?: [Pt, Pt, Pt, Pt] }

type Ctx = CanvasRenderingContext2D
interface Target { useMediaCoordinateSpace(f: (s: { context: Ctx; mediaSize: { width: number } }) => void): void }

/**
 * Motor de capas: guarda overlays por id, los reemplaza por agente al llegar nuevos
 * y los dibuja con una primitiva de Lightweight Charts (sin recrear series: sin parpadeo).
 */
export class LayerEngine implements ISeriesPrimitive<Time> {
  private store = new Map<string, Overlay>()
  private times: number[] = []        // ms de las velas, ascendente
  private enabled = new Set<LayerId>()
  private shapes: Shape[] = []
  private chart!: IChartApi
  private series!: ISeriesApi<'Candlestick'>
  private redraw: () => void = () => {}
  modeLabel = 'Análisis'

  constructor() { LAYERS.filter((l) => l.on).forEach((l) => this.enabled.add(l.id)) }

  attached(p: SeriesAttachedParameter<Time>): void {
    this.chart = p.chart as IChartApi
    this.series = p.series as ISeriesApi<'Candlestick'>
    this.redraw = p.requestUpdate
  }
  detached(): void { this.redraw = () => {} }

  isOn(id: LayerId): boolean { return this.enabled.has(id) }
  setEnabled(s: Iterable<LayerId>): void { this.enabled = new Set(s); this.redraw() }
  setTimes(ms: number[]): void { this.times = ms; this.redraw() }
  pushTime(ms: number): void {
    const last = this.times[this.times.length - 1]
    if (last === undefined || ms > last) this.times.push(ms)
    this.redraw()
  }
  requestRedraw(): void { this.redraw() }
  clear(): void { this.store.clear(); this.shapes = []; this.redraw() }

  /** Reemplaza los overlays de los agentes presentes; retira los que ya no vienen. */
  replace(overlays: Overlay[]): void {
    const agents = new Set(overlays.map((o) => o.agent_id))
    for (const [id, o] of this.store) if (agents.has(o.agent_id)) this.store.delete(id)
    for (const o of overlays) this.store.set(o.id, o)
    this.redraw()
  }

  // --- tiempo → píxel (extrapola más allá de la última vela) ---
  x(tMs: number): number | null {
    const ts = this.times
    if (ts.length < 2) return null
    const step = ts[ts.length - 1] - ts[ts.length - 2]
    let idx: number
    if (tMs >= ts[ts.length - 1]) idx = ts.length - 1 + (tMs - ts[ts.length - 1]) / step
    else if (tMs <= ts[0]) idx = (tMs - ts[0]) / step
    else {
      let lo = 0, hi = ts.length - 1
      while (hi - lo > 1) { const m = (lo + hi) >> 1; if (ts[m] <= tMs) lo = m; else hi = m }
      idx = lo + (tMs - ts[lo]) / (ts[hi] - ts[lo])
    }
    return this.chart.timeScale().logicalToCoordinate(idx as never)
  }
  y(p: number): number | null { return this.series.priceToCoordinate(p) }

  private build(width: number): void {
    const out: Shape[] = []
    for (const ov of this.store.values()) {
      if (!this.enabled.has(layerOf(ov))) continue
      const g = ov.geometry
      const xa = this.x(ov.t_from)
      const xb = ov.t_to == null ? width : this.x(ov.t_to)
      if (xa == null || xb == null) continue
      const x0 = Math.max(0, xa), x1 = Math.min(width, xb)
      if (ov.kind === 'zone') {
        const a = this.y(num(g.p_high)), b = this.y(num(g.p_low))
        if (a != null && b != null) out.push({ ov, kind: 'band', x0, x1, ys: [a, b] })
      } else if (ov.kind === 'level') {
        const a = this.y(num(g.p))
        if (a != null) out.push({ ov, kind: 'line', x0, x1, ys: [a] })
      } else if (ov.kind === 'channel' || ov.kind === 'range') {
        const u = pts(g.upper), l = pts(g.lower)
        if (u.length < 2 || l.length < 2) continue
        const px = (p: Pt): Pt | null => {
          const X = this.x(p[0]), Y = this.y(p[1])
          return X == null || Y == null ? null : [X, Y]
        }
        const c = [px(u[0]), px(u[1]), px(l[1]), px(l[0])]
        if (c.every((q) => q)) out.push({ ov, kind: 'chan', x0, x1, ys: [], ch: c as [Pt, Pt, Pt, Pt] })
      } else if (ov.kind === 'trade_plan') {
        const ys = [num(g.entry), num(g.sl), ...(g.tp as number[]).map(num)].map((p) => this.y(p))
        if (ys.every((v) => v != null)) out.push({ ov, kind: 'plan', x0, x1, ys: ys as number[] })
      }
    }
    this.shapes = out
  }

  private draw(ctx: Ctx, w: number, top: boolean): void {
    if (!this.chart) return
    this.build(w)
    const up = cssVar('--up'), down = cssVar('--down'), accent = cssVar('--accent')
    const text = cssVar('--text'), panel = cssVar('--panel')
    ctx.save()
    ctx.font = '11px system-ui, sans-serif'
    for (const s of this.shapes) {
      if ((s.kind === 'plan') !== top) continue
      const g = s.ov.geometry
      if (s.kind === 'band') {
        const col = g.role === 'soporte' ? up : down
        const y = Math.min(...s.ys), h = Math.max(2, Math.abs(s.ys[1] - s.ys[0]))
        ctx.globalAlpha = 0.14; ctx.fillStyle = col; ctx.fillRect(s.x0, y, s.x1 - s.x0, h)
        ctx.globalAlpha = 0.55; ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.strokeRect(s.x0, y, s.x1 - s.x0, h)
        ctx.globalAlpha = 1; ctx.fillStyle = col; ctx.fillText(s.ov.label, s.x0 + 6, y - 3)
      } else if (s.kind === 'line') {
        ctx.globalAlpha = 0.7; ctx.strokeStyle = accent; ctx.setLineDash([4, 4])
        ctx.beginPath(); ctx.moveTo(s.x0, s.ys[0]); ctx.lineTo(s.x1, s.ys[0]); ctx.stroke()
        ctx.setLineDash([])
      } else if (s.kind === 'chan' && s.ch) {
        const [u0, u1, l1, l0] = s.ch
        ctx.globalAlpha = 0.07; ctx.fillStyle = accent
        ctx.beginPath(); ctx.moveTo(...u0); ctx.lineTo(...u1); ctx.lineTo(...l1); ctx.lineTo(...l0)
        ctx.closePath(); ctx.fill()
        ctx.globalAlpha = 0.85; ctx.strokeStyle = accent; ctx.lineWidth = 1.5
        if (g.state && g.state !== 'INSIDE') ctx.setLineDash([6, 4])
        ctx.beginPath(); ctx.moveTo(...u0); ctx.lineTo(...u1); ctx.moveTo(...l0); ctx.lineTo(...l1); ctx.stroke()
        ctx.setLineDash([])
      } else if (s.kind === 'plan') {
        this.drawPlan(ctx, s, { up, down, accent, text, panel })
      }
    }
    ctx.restore()
  }

  private drawPlan(ctx: Ctx, s: Shape, c: Record<'up' | 'down' | 'accent' | 'text' | 'panel', string>): void {
    const g = s.ov.geometry
    const prices = [num(g.entry), num(g.sl), ...(g.tp as number[]).map(num)]
    const names = ['Entrada', 'SL', ...prices.slice(2).map((_, i) => `TP${i + 1}`)]
    const cols = [c.accent, c.down, ...prices.slice(2).map(() => c.up)]
    ctx.lineWidth = 1.5
    s.ys.forEach((y, i) => {
      ctx.globalAlpha = 0.9; ctx.strokeStyle = cols[i]; ctx.fillStyle = cols[i]
      ctx.setLineDash(i === 0 ? [] : [6, 4])
      ctx.beginPath(); ctx.moveTo(s.x0, y); ctx.lineTo(s.x1, y); ctx.stroke(); ctx.setLineDash([])
      const txt = `${names[i]} ${prices[i].toLocaleString('es-CO', { maximumFractionDigits: 2 })}`
      const tw = ctx.measureText(txt).width + 10
      const lx = Math.max(s.x0 + 4, s.x1 - tw - 70)
      ctx.fillRect(lx, y - 8, tw, 16)
      ctx.fillStyle = c.panel; ctx.fillText(txt, lx + 5, y + 4)
    })
    const head = `${g.side === 'long' ? 'Largo' : 'Corto'} · R:R ${num(g.rr).toFixed(2)} · Propuesta · ${this.modeLabel}`
    const tw = ctx.measureText(head).width + 12
    const hy = Math.max(2, Math.min(...s.ys) - 24)
    ctx.globalAlpha = 0.95; ctx.fillStyle = c.panel; ctx.strokeStyle = c.accent; ctx.lineWidth = 1
    ctx.fillRect(s.x0 + 6, hy, tw, 18); ctx.strokeRect(s.x0 + 6, hy, tw, 18)
    ctx.fillStyle = c.text; ctx.fillText(head, s.x0 + 12, hy + 13)
  }

  paneViews(): { zOrder(): 'bottom' | 'top'; renderer(): { draw(t: unknown): void } }[] {
    const view = (top: boolean) => ({
      zOrder: () => (top ? ('top' as const) : ('bottom' as const)),
      renderer: () => ({
        draw: (target: unknown) =>
          (target as Target).useMediaCoordinateSpace(({ context, mediaSize }) =>
            this.draw(context, mediaSize.width, top)),
      }),
    })
    return [view(false), view(true)]
  }

  /** Objeto bajo el cursor (píxeles del panel), o null. Prioriza plan y zonas. */
  hit(px: number, py: number): Overlay | null {
    const order = ['plan', 'band', 'line', 'chan']
    const cand = this.shapes.filter((s) => px >= s.x0 - 2 && px <= s.x1 + 2)
      .sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind))
    for (const s of cand) {
      if (s.kind === 'plan' && s.ys.some((y) => Math.abs(y - py) < 6)) return s.ov
      if (s.kind === 'band' && py >= Math.min(...s.ys) - 2 && py <= Math.max(...s.ys) + 2) return s.ov
      if (s.kind === 'line' && Math.abs(s.ys[0] - py) < 6) return s.ov
      if (s.kind === 'chan' && s.ch) {
        const [u0, u1, l1, l0] = s.ch
        const at = (a: Pt, b: Pt): number => a[1] + ((b[1] - a[1]) * (px - a[0])) / (b[0] - a[0] || 1)
        if (Math.abs(at(u0, u1) - py) < 7 || Math.abs(at(l0, l1) - py) < 7) return s.ov
      }
    }
    return null
  }

  /** Coordenadas calculadas, para verificar contra los precios del overlay. */
  debugShapes(): { id: string; ys: number[]; x0: number; x1: number; ch?: Pt[] }[] {
    return this.shapes.map((s) => ({ id: s.ov.id, ys: s.ys, x0: s.x0, x1: s.x1, ch: s.ch }))
  }
  debugCoord(p: number): number | null { return this.y(p) }
}
