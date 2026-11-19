/** Piso común del mapa isométrico: baldosas, losa bajo todas las salas, nombre pintado de cada área y la
 * separación de las salas para que ninguna pise a otra cuando su microecosistema la hace crecer. */
import { NAME_STRIP } from './obs_iso_props'
import { P, pts, S, type Room } from './obs_iso_geo'
import { esc } from './obs_types'

/** Coordenadas del piso común: la vista entera comparte un solo plano (U, V) en unidades. */
export const toUV = (x: number, y: number): [number, number] => [(x / (0.866 * S) + y / (0.5 * S)) / 2, (y / (0.5 * S) - x / (0.866 * S)) / 2]
export const G = (u: number, v: number, z = 0): [number, number] => P(0, 0, u, v, z)

/** Separa salas que se pisan (con un pasillo de `gap` unidades para las pistas): cada par que se solapa se aparta
 * por el eje de menor choque, alejándose del centro del mapa, hasta que no quede ninguno. Mantiene el anillo.
 * Cada sala ocupa también, hacia el fondo, lo que tapan sus paredes (`wall`): así la de delante no cubre a la otra. */
export function separate<T extends Room>(A: T[], gap = 1.1, wall = 1.5): T[] {
  const uv = A.map((a) => toUV(a.cx, a.cy))
  const mu = uv.reduce((s, q) => s + q[0], 0) / uv.length, mv = uv.reduce((s, q) => s + q[1], 0) / uv.length
  for (let it = 0; it < 60; it++) {
    let moved = false
    for (let i = 0; i < A.length; i++) for (let j = i + 1; j < A.length; j++) {
      const du = uv[j][0] - uv[i][0], dv = uv[j][1] - uv[i][1]
      const span = (c: number, h: number): [number, number] => [c - h - wall, c + h]       // con la franja de las paredes
      const over = (ax: 0 | 1, hi: number, hj: number): number => { const a = span(uv[i][ax], hi), b = span(uv[j][ax], hj); return Math.min(a[1], b[1]) - Math.max(a[0], b[0]) + gap }
      const ou = over(0, A[i].hu, A[j].hu), ov = over(1, A[i].hv, A[j].hv)
      if (ou <= 0 || ov <= 0) continue
      moved = true
      const axis = ou < ov ? 0 : 1, push = (axis === 0 ? ou : ov) / 2 + 0.02
      const s = (axis === 0 ? du : dv) || ((axis === 0 ? uv[j][0] + uv[i][0] - 2 * mu : uv[j][1] + uv[i][1] - 2 * mv) >= 0 ? 1 : -1)
      uv[i][axis] -= Math.sign(s) * push; uv[j][axis] += Math.sign(s) * push
    }
    if (!moved) break
  }
  return A.map((a, i) => { const [x, y] = G(uv[i][0], uv[i][1]); return { ...a, cx: x, cy: y } })
}

/** Líneas de baldosa del piso común entre (u0, v0) y (u1, v1), en coordenadas globales: así el piso
 * se ve continuo aunque una sala lo vuelva a pintar encima (para tapar las pistas que pasan por debajo). */
export function tiles(u0: number, v0: number, u1: number, v1: number): string {
  let s = ''
  for (let u = Math.ceil(u0); u < u1; u++) { const p1 = G(u, v0), p2 = G(u, v1); s += `<line x1="${p1[0].toFixed(1)}" y1="${p1[1].toFixed(1)}" x2="${p2[0].toFixed(1)}" y2="${p2[1].toFixed(1)}"/>` }
  for (let v = Math.ceil(v0); v < v1; v++) { const p1 = G(u0, v), p2 = G(u1, v); s += `<line x1="${p1[0].toFixed(1)}" y1="${p1[1].toFixed(1)}" x2="${p2[0].toFixed(1)}" y2="${p2[1].toFixed(1)}"/>` }
  return s
}

export const FLOOR = '#d8dce3'           // gris claro: el mismo en todo el piso, dentro y fuera de las salas

/** Piso común bajo todas las salas: una sola losa gris clara de oficina, en vez de islas separadas. */
export function floorSlab(A: Room[]): [string, number[]] {
  const uv = A.flatMap((a) => { const [u, v] = toUV(a.cx, a.cy); return [[u - a.hu, v - a.hv], [u + a.hu, v + a.hv]] })
  const m = 1.4, u0 = Math.floor(Math.min(...uv.map((q) => q[0])) - m), u1 = Math.ceil(Math.max(...uv.map((q) => q[0])) + m)
  const v0 = Math.floor(Math.min(...uv.map((q) => q[1])) - m), v1 = Math.ceil(Math.max(...uv.map((q) => q[1])) + m), t = 0.45
  const [a0, b, c, d] = [G(u0, v0), G(u1, v0), G(u1, v1), G(u0, v1)], [b0, c0, d0] = [G(u1, v0, -t), G(u1, v1, -t), G(u0, v1, -t)]
  const s = `<polygon points="${pts([d, c, c0, d0])}" fill="#bfc6d1"/><polygon points="${pts([c, b, b0, c0])}" fill="#a5aebc"/>`
    + `<polygon points="${pts([a0, b, c, d])}" fill="${FLOOR}" class="iso-ground"/>${tiles(u0, v0, u1, v1)}`
    + `<polyline points="${pts([d, c, b])}" fill="none" stroke="#e6e9ee" stroke-width="2"/>`
  const xs = [a0, b, c, d, b0, c0, d0].map((q) => q[0]), ys = [a0, b, c, d, b0, c0, d0].map((q) => q[1])
  return [`<g class="iso-tiles">${s}</g>`, [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]]
}

/** Nombre del área pintado en el piso, en la franja del frente («1. DATOS»), siguiendo el eje u. */
export function floorName(a: Room & { i: number }, title: string, accent: string): string {
  const { cx, cy, hu, hv } = a, vMid = hv - 0.22 - NAME_STRIP / 2, txt = `${a.i + 1}. ${title.split(/ \/ | y /)[0].toLocaleUpperCase('es')}`
  const avail = (2 * hu - 0.4) * S, fs = Math.min(0.5 * S, avail / (txt.length * 0.7))
  const [ox, oy] = P(cx, cy, 0, vMid)
  const fr = [P(cx, cy, -hu + 0.12, hv - 0.18 - NAME_STRIP), P(cx, cy, hu - 0.12, hv - 0.18 - NAME_STRIP), P(cx, cy, hu - 0.12, hv - 0.18), P(cx, cy, -hu + 0.12, hv - 0.18)]
  return `<polygon points="${pts(fr)}" fill="${accent}" fill-opacity=".07" stroke="${accent}" stroke-opacity=".55" stroke-width="1.5"/>`
    + `<text class="iso-fname" transform="matrix(0.866 0.5 -0.866 0.5 ${ox.toFixed(1)} ${oy.toFixed(1)})" y="${(fs * 0.36).toFixed(1)}" font-size="${fs.toFixed(1)}" fill="#111111">${esc(txt)}</text>`
}

type Rect = number[]                 // x0, y0, x1, y1 en pantalla
/** Silueta de una sala en pantalla: el piso y la franja que tapan sus paredes del fondo (`wallH` unidades). */
function shape(a: Room, wallH: number): [number, number][] {
  const p = (u: number, v: number, z = 0): [number, number] => P(a.cx, a.cy, u, v, z), { hu, hv } = a
  return [p(-hu, hv, wallH), p(-hu, -hv, wallH), p(hu, -hv, wallH), p(hu, -hv), p(hu, hv), p(-hu, hv)]
}
function inside(poly: [number, number][], x: number, y: number): boolean {
  let c = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j]
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c
  }
  return c
}
/** ¿La caja toca alguna sala (piso o paredes)? Para que tarjetas y etiquetas busquen sitio libre. */
export function hitsRoom(A: Room[], r: Rect, wallH: number): boolean {
  const xs = [r[0], (r[0] + r[2]) / 2, r[2]], ys = [r[1], (r[1] + r[3]) / 2, r[3]]
  return A.some((a) => { const s = shape(a, wallH)
    return xs.some((x) => ys.some((y) => inside(s, x, y))) || s.some(([x, y]) => x > r[0] && x < r[2] && y > r[1] && y < r[3]) })
}
export const hitsAny = (boxes: Rect[], r: Rect): boolean => boxes.some((b) => r[0] < b[2] && r[2] > b[0] && r[1] < b[3] && r[3] > b[1])
