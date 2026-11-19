/** Recorrido de las líneas entre áreas del mapa completo (vista isométrica). Cada línea sale por un borde
 * abierto del frente del área de origen (derecho u = +hu, o izquierdo v = +hv: los del fondo tienen pared y
 * la tapan) y entra por un borde abierto del frente del área de destino. Entre ambos busca, en ángulo recto
 * sobre el piso, el camino más corto que no pase por ninguna sala ni por la franja que tapan sus paredes del
 * fondo, y que no se monte sobre otra línea ya trazada. Las líneas importantes se trazan primero y se
 * quedan con los mejores pasillos. Si no hay camino libre, la línea se marca `blocked` y se dibuja encima de
 * las salas para que nunca quede oculta. Solo geometría: no sabe de estados. */
import type { UVRect } from './obs_iso_lounge'

export type UV = [number, number]
export interface RoomUV { u: number; v: number; hu: number; hv: number }
export interface Route { way: UV[]; blocked: boolean }

const SHADOW = 1.5        // franja del piso que tapan las paredes del fondo (WALL_H = 1.3 y un poco de aire)
const MARGIN = 0.3        // aire frente a los bordes abiertos de otras salas
const STUB = 0.7          // tramo recto al salir y al entrar (lleva la punta de flecha)
const LANE = 0.38         // separación entre pasillos paralelos
const OFFS = [0, 0.6, -0.6, 1.2, -1.2, 1.8, -1.8]   // puertas sucesivas en un mismo borde, para no pisarse

const cross = (s: UVRect, o: UVRect): boolean => s[0] < o[2] && s[2] > o[0] && s[1] < o[3] && s[3] > o[1]
const segBox = (p: UV, q: UV): UVRect => [Math.min(p[0], q[0]), Math.min(p[1], q[1]), Math.max(p[0], q[0]), Math.max(p[1], q[1])]

/** Quita puntos repetidos y los intermedios de un mismo tramo recto. */
function simplify(w: UV[]): UV[] {
  const a = w.filter((p, i) => i === 0 || Math.abs(p[0] - w[i - 1][0]) + Math.abs(p[1] - w[i - 1][1]) > 1e-6)
  return a.filter((p, i) => {
    if (i === 0 || i === a.length - 1) return true
    const [o, q] = [a[i - 1], a[i + 1]]
    const between = (k: 0 | 1): boolean => (p[k] - o[k]) * (q[k] - p[k]) >= 0
    return !((o[0] === p[0] && p[0] === q[0] && between(1)) || (o[1] === p[1] && p[1] === q[1] && between(0)))
  })
}

/** Cuánto choca el tramo p→q con un tramo ya trazado c→e: montarse en paralelo cuesta mucho; cruzarse, poco. */
function clash(p: UV, q: UV, c: UV, e: UV): number {
  const hp = p[1] === q[1], hc = c[1] === e[1]
  if (hp === hc) {
    const k = hp ? 1 : 0, j = hp ? 0 : 1
    if (Math.abs(p[k] - c[k]) >= LANE * 0.8) return 0
    const ov = Math.min(Math.max(p[j], q[j]), Math.max(c[j], e[j])) - Math.max(Math.min(p[j], q[j]), Math.min(c[j], e[j]))
    return ov > 0 ? 12 * ov + 4 : 0
  }
  return cross(segBox(p, q), segBox(c, e)) ? 2.5 : 0
}

export class Router {
  private obst: UVRect[]
  private tight: UVRect[]
  private used: [UV, UV][] = []
  private ports = new Map<string, number>()
  private cu: number[] = []
  private cv: number[] = []

  constructor(private R: RoomUV[]) {
    this.obst = R.map((r): UVRect => [r.u - r.hu - SHADOW, r.v - r.hv - SHADOW, r.u + r.hu + MARGIN, r.v + r.hv + MARGIN])
    this.tight = R.map((r): UVRect => [r.u - r.hu - SHADOW, r.v - r.hv - SHADOW, r.u + r.hu, r.v + r.hv])
    for (const o of this.obst) for (let k = 0; k < 4; k++) {        // pasillos junto a cada sala, en carriles
      const l = 0.45 + k * LANE
      this.cu.push(o[0] - l, o[2] + l); this.cv.push(o[1] - l, o[3] + l)
    }
  }

  /** Puerta en un borde abierto del frente: 0 = derecho (u = +hu), 1 = izquierdo (v = +hv). */
  private port(i: number, side: 0 | 1): { p: UV; s: UV } {
    const r = this.R[i], n = this.ports.get(`${i}:${side}`) ?? 0, h = Math.max(0, (side === 0 ? r.hv : r.hu) - 0.45)
    const t = Math.max(-h, Math.min(h, OFFS[n % OFFS.length]))
    return side === 0 ? { p: [r.u + r.hu, r.v + t], s: [r.u + r.hu + STUB, r.v + t] }
      : { p: [r.u + t, r.v + r.hv], s: [r.u + t, r.v + r.hv + STUB] }
  }

  private mids(s: UV, t: UV): UV[][] {
    const out: UV[][] = [[[s[0], t[1]]], [[t[0], s[1]]]]
    for (const m of [...this.cu, (s[0] + t[0]) / 2]) out.push([[m, s[1]], [m, t[1]]])
    for (const m of [...this.cv, (s[1] + t[1]) / 2]) out.push([[s[0], m], [t[0], m]])
    return out
  }

  private score(w: UV[], a: number, b: number): [number, number] {
    let len = 0, hits = 0, pen = 0
    for (let i = 0; i + 1 < w.length; i++) {
      const p = w[i], q = w[i + 1], sb = segBox(p, q)
      len += Math.abs(q[0] - p[0]) + Math.abs(q[1] - p[1])
      for (let j = 0; j < this.R.length; j++) if (cross(sb, j === a || j === b ? this.tight[j] : this.obst[j])) hits++
      for (const [c, e] of this.used) pen += clash(p, q, c, e)
    }
    return [len + 0.6 * (w.length - 2) + 400 * hits + pen, hits]
  }

  /** Recorrido de la sala `a` a la sala `b` (índices de `R`), en coordenadas del piso común. */
  route(a: number, b: number): Route {
    let best: { way: UV[]; cost: number; hits: number; sa: 0 | 1; sb: 0 | 1 } | null = null
    for (const sa of [0, 1] as const) for (const sb of [0, 1] as const) {
      const A = this.port(a, sa), B = this.port(b, sb)
      for (const mid of this.mids(A.s, B.s)) {
        const way = simplify([A.p, A.s, ...mid, B.s, B.p]), [cost, hits] = this.score(way, a, b)
        if (!best || cost < best.cost) best = { way, cost, hits, sa, sb }
      }
    }
    const w = best!.way
    for (const [i, s] of [[a, best!.sa], [b, best!.sb]] as [number, 0 | 1][]) this.ports.set(`${i}:${s}`, (this.ports.get(`${i}:${s}`) ?? 0) + 1)
    for (let i = 0; i + 1 < w.length; i++) this.used.push([w[i], w[i + 1]])
    return { way: w, blocked: best!.hits > 0 }
  }
}
