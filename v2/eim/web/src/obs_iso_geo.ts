/** Geometría isométrica de la vista «Isométrico» del mapa del sistema: proyección, cajas y paredes
 * como cadenas SVG (sin librería). Una unidad = `S` píxeles; z crece hacia arriba. */

export const S = 40

/** Proyección de (u, v, z) a pantalla, relativa al centro (cx, cy) de un área. */
export const P = (cx: number, cy: number, u: number, v: number, z = 0): [number, number] =>
  [cx + (u - v) * 0.866 * S, cy + (u + v) * 0.5 * S - z * S]

export const pts = (a: [number, number][]): string => a.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')

export interface Room { cx: number; cy: number; hu: number; hv: number }

/** Caja con tres caras visibles (arriba, izquierda, derecha). */
export function box(r: Room, u: number, v: number, w: number, d: number, h: number, z0: number,
  top: string, left: string, right: string, extra = ''): string {
  const { cx, cy } = r
  const A = P(cx, cy, u - w / 2, v - d / 2, z0 + h), B = P(cx, cy, u + w / 2, v - d / 2, z0 + h)
  const C = P(cx, cy, u + w / 2, v + d / 2, z0 + h), D = P(cx, cy, u - w / 2, v + d / 2, z0 + h)
  const B0 = P(cx, cy, u + w / 2, v - d / 2, z0), C0 = P(cx, cy, u + w / 2, v + d / 2, z0), D0 = P(cx, cy, u - w / 2, v + d / 2, z0)
  return `<polygon points="${pts([D, C, C0, D0])}" fill="${left}"${extra}/><polygon points="${pts([C, B, B0, C0])}" fill="${right}"${extra}/>`
    + `<polygon points="${pts([A, B, C, D])}" fill="${top}"${extra}/>`
}

/** Rectángulo plano pegado a la pared del fondo derecho (v = -hv): u0..u1 a lo ancho, z0..z1 a lo alto. */
export function onBackRight(r: Room, u0: number, u1: number, z0: number, z1: number, attrs: string): string {
  const v = -r.hv + 0.02
  return `<polygon points="${pts([P(r.cx, r.cy, u0, v, z0), P(r.cx, r.cy, u1, v, z0), P(r.cx, r.cy, u1, v, z1), P(r.cx, r.cy, u0, v, z1)])}" ${attrs}/>`
}

/** Rectángulo plano pegado a la pared del fondo izquierdo (u = -hu): v0..v1 a lo ancho, z0..z1 a lo alto. */
export function onBackLeft(r: Room, v0: number, v1: number, z0: number, z1: number, attrs: string): string {
  const u = -r.hu + 0.02
  return `<polygon points="${pts([P(r.cx, r.cy, u, v0, z0), P(r.cx, r.cy, u, v1, z0), P(r.cx, r.cy, u, v1, z1), P(r.cx, r.cy, u, v0, z1)])}" ${attrs}/>`
}

/** Punto sobre la pared derecha (para trazar curvas o texto encima de un tablero). */
export const onBR = (r: Room, u: number, z: number): [number, number] => P(r.cx, r.cy, u, -r.hv + 0.03, z)
export const onBL = (r: Room, v: number, z: number): [number, number] => P(r.cx, r.cy, -r.hu + 0.03, v, z)

/** Polilínea sobre la pared derecha a partir de pares (u, z). */
export const lineBR = (r: Room, uz: [number, number][], attrs: string): string =>
  `<polyline points="${pts(uz.map(([u, z]) => onBR(r, u, z)))}" fill="none" ${attrs}/>`
export const lineBL = (r: Room, vz: [number, number][], attrs: string): string =>
  `<polyline points="${pts(vz.map(([v, z]) => onBL(r, v, z)))}" fill="none" ${attrs}/>`

/** Flechas pequeñas y quietas a lo largo de un trazo en pantalla (sentido de la información), una cada
 * `every` px y siempre a medio tramo para no caer en las esquinas. Sustituye a las flechas que viajaban:
 * nada se mueve, así la capa no se repinta. */
export function arrowsAlong(sp: [number, number][], every: number, size: number, fill: string, cls = 'iso-arrow'): string {
  let out = ''
  for (let i = 0; i + 1 < sp.length; i++) {
    const [x0, y0] = sp[i], [x1, y1] = sp[i + 1], len = Math.hypot(x1 - x0, y1 - y0)
    if (len < size * 3) continue
    const n = Math.max(1, Math.floor(len / every)), c = (x1 - x0) / len, s = (y1 - y0) / len
    for (let j = 0; j < n; j++) {
      const t = (j + 0.5) / n, cx = x0 + (x1 - x0) * t, cy = y0 + (y1 - y0) * t
      const p = ([u, v]: [number, number]): string => `${(cx + u * c - v * s).toFixed(1)},${(cy + u * s + v * c).toFixed(1)}`
      out += `<polygon class="${cls}" points="${p([size, 0])} ${p([-size * 0.7, -size * 0.75])} ${p([-size * 0.35, 0])} ${p([-size * 0.7, size * 0.75])}" fill="${fill}"/>`
    }
  }
  return out
}
