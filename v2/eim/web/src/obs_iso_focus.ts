/** Sala enfocada del mapa isométrico: al ampliar un área, los puestos se reparten en filas horizontales
 * de pantalla, alternadas, con hueco para que el nombre de cada analista quepa debajo de su puesto sin
 * pisar a los vecinos. El nombre es un botón: al pulsarlo se abre el detalle de esa pieza. */
import { NAME_STRIP, STRIP } from './obs_iso_props'
import { P, S, type Room } from './obs_iso_geo'
import { esc } from './obs_types'

const COLW = 196          // px entre puestos de una misma fila (cabe un nombre de ~24 letras)
const ROWH = 108          // px entre filas: figura + nombre sin tocar la fila siguiente
const MAXC = 24           // nombres más largos se recortan con «…» (el completo va en el título)
export const FOCUS_K = 1.45   // puestos más grandes que en el mapa completo

interface Layout extends Room { slots: [number, number][]; k: number; list: unknown[] }

/** Puestos candidatos en rejilla de pantalla (filas alternadas) dentro de una sala de medio ancho hu × hv. */
function grid(hu: number, hv: number): { uv: [number, number]; X: number; Y: number; dist: number }[] {
  const m = 0.9, top = STRIP + 1.25, bot = NAME_STRIP + 0.95, vc = (top - bot) / 2, out = []
  const R = Math.ceil(((hu + hv) * 0.5 * S) / ROWH), C = Math.ceil(((hu + hv) * 0.866 * S) / COLW) + 1
  for (let r = -R; r <= R; r++) for (let c = -C; c <= C; c++) {
    const Y = r * ROWH, X = c * COLW + (Math.abs(r) % 2 ? COLW / 2 : 0)
    const dd = X / (0.866 * S), s = Y / (0.5 * S), u = (s + dd) / 2, v = (s - dd) / 2
    if (Math.abs(u) <= hu - m && v >= -hv + top && v <= hv - bot) out.push({ uv: [u, v] as [number, number], X, Y, dist: Math.hypot(u, (v - vc) * 1.2) })
  }
  return out
}

/** Misma sala con puestos en rejilla de pantalla: prueba varias proporciones y se queda con la más
 * pequeña donde caben todos, para que puestos y nombres se vean lo más grandes posible. */
export function focusLayout<T extends Layout>(a: T): T {
  const n = Math.max(a.list.length, 1)
  let best: { hu: number; hv: number; slots: [number, number][] } | null = null
  for (const ratio of [0.8, 1, 1.25, 1.5, 1.8]) for (let h = 2.5; h < 40; h += 0.25) {
    const hu = h * ratio, hv = h
    if (best && hu + hv >= best.hu + best.hv) break
    const cand = grid(hu, hv)
    if (cand.length < n) continue
    const pick = cand.sort((x, y) => x.dist - y.dist).slice(0, n).sort((x, y) => x.Y - y.Y || x.X - y.X)
    best = { hu, hv, slots: pick.map((p) => p.uv) }
    break
  }
  return best ? { ...a, ...best, k: FOCUS_K } : a
}

/** `side`: hacia dónde se abre el nombre desde los pies del puesto ('l' izquierda, 'r' derecha; por defecto centrado),
 * para que en filas diagonales no tape al vecino de al lado. */
export interface Tag { id: string; name: string; color: string; tip: string; side?: 'l' | 'r' }

/** Nombre de cada puesto, debajo de sus pies; va en la capa de arriba para que nada lo tape. */
export function nameTags(a: Layout, tags: Tag[], sel: string | null): string {
  return tags.map((t, i) => {
    const [u, v] = a.slots[i], f = P(a.cx, a.cy, u, v + 0.22 * a.k, 0)
    const txt = t.name.length > MAXC ? `${t.name.slice(0, MAXC - 1)}…` : t.name, w = txt.length * 7 + 26, y = f[1] + 24
    const x0 = t.side === 'l' ? f[0] - w + 18 : t.side === 'r' ? f[0] - 18 : f[0] - w / 2
    return `<g class="obs-n iso-tag${t.id === sel ? ' sel' : ''}" data-id="${esc(t.id)}" role="button" tabindex="0" aria-label="${esc(t.tip)}"><title>${esc(t.tip)}</title>`
      + `<rect x="${x0.toFixed(1)}" y="${(y - 11).toFixed(1)}" width="${w.toFixed(1)}" height="22" rx="11" stroke="${t.color}"/>`
      + `<circle cx="${(x0 + 11).toFixed(1)}" cy="${y.toFixed(1)}" r="3.6" fill="${t.color}"/>`
      + `<text x="${(x0 + w / 2 + 6).toFixed(1)}" y="${(y + 4).toFixed(1)}">${esc(txt)}</text></g>`
  }).join('')
}
