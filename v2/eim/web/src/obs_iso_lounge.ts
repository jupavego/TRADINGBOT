/** Área común del mapa isométrico: salitas y zonas de estar en los huecos libres del piso central,
 * sin pisar las salas, las pistas de comunicación ni las etiquetas. Solo decora: no hay estados aquí. */
import { box, P, pts, S, type Room } from './obs_iso_geo'
import { art } from './obs_iso_props'

/** Rectángulo en coordenadas del piso común (u0, v0, u1, v1). */
export type UVRect = [number, number, number, number]

const O: Room = { cx: 0, cy: 0, hu: 0, hv: 0 }       // el piso común usa el origen de la vista
const G = (u: number, v: number, z = 0): [number, number] => P(0, 0, u, v, z)

/** Alfombra plana con borde. */
const rug = (u: number, v: number, w: number, d: number, fill: string, edge: string): string =>
  `<polygon points="${pts([G(u - w / 2, v - d / 2), G(u + w / 2, v - d / 2), G(u + w / 2, v + d / 2), G(u - w / 2, v + d / 2)])}" fill="${fill}" stroke="${edge}" stroke-width="2"/>`

interface Kind { hu: number; hv: number; draw: (u: number, v: number) => string }

/** Cuatro tipos de espacio, cada uno con su criterio: conversar, descansar, café y verde. */
const KINDS: Kind[] = [
  { hu: 1.15, hv: 0.9, draw: (u, v) => rug(u, v, 2.1, 1.6, '#d9cce8', '#b79fd6')     // salita de conversación
      + art('sofa_morado', G(u - 0.05, v - 0.45), 46) + art('planta_maceta', G(u + 0.85, v - 0.62), 35)
      + box(O, u, v + 0.15, 0.62, 0.42, 0.16, 0, '#f4f1ea', '#c9c2b4', '#ddd6c8') + art('cafe', G(u + 0.12, v + 0.1, 0.16), 12)
      + art('sillon', G(u - 0.75, v + 0.45), 35, 'piso', true) + art('sillon', G(u + 0.2, v + 0.78), 35) },
  { hu: 1.05, hv: 0.8, draw: (u, v) => rug(u, v, 1.9, 1.4, '#cfe3ea', '#8fbfd0')     // zona de descanso
      + art('sofa_blanco', G(u, v - 0.35), 46) + art('arbol_grande', G(u + 0.85, v - 0.5), 62)
      + box(O, u + 0.05, v + 0.35, 0.7, 0.4, 0.14, 0, '#5c4636', '#3d2e23', '#4b392c') + art('pizza', G(u + 0.05, v + 0.42, 0.14), 16) },
  { hu: 0.95, hv: 0.95, draw: (u, v) => art('cocineta', G(u + 0.2, v + 0.75), 78) + art('planta_mueble', G(u - 0.85, v + 0.6), 49) },   // rincón del café
  { hu: 0.7, hv: 0.6, draw: (u, v) => rug(u, v, 1.3, 1.0, '#d6ead2', '#9cc994')     // rincón verde
      + art('arbol_grande', G(u - 0.35, v - 0.2), 68) + art('sofa_corto', G(u + 0.2, v + 0.35), 32) + art('planta_maceta', G(u + 0.5, v - 0.25), 30) },
]

const hit = (a: UVRect, b: UVRect): boolean => a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1]
const screenBox = (r: UVRect, zTop: number): number[] => {
  const c = [G(r[0], r[1], zTop), G(r[2], r[1]), G(r[2], r[3]), G(r[0], r[3])]
  return [Math.min(...c.map((q) => q[0])), Math.min(...c.map((q) => q[1])), Math.max(...c.map((q) => q[0])), Math.max(...c.map((q) => q[1]))]
}

/** Coloca hasta `max` espacios dentro de `zone`, lo más cerca posible de su centro. `rooms` y
 * `tracks` (tramos de las pistas, ya ensanchados) son obstáculos; `labels` son cajas en pantalla. */
export function lounges(zone: UVRect, rooms: UVRect[], tracks: UVRect[], labels: number[][], max = 6): { svg: string; depth: number }[] {
  const busy = [...rooms.map((r): UVRect => [r[0] - 0.4, r[1] - 0.4, r[2] + 0.4, r[3] + 0.4]), ...tracks]
  const mu = (zone[0] + zone[2]) / 2, mv = (zone[1] + zone[3]) / 2, out: { svg: string; depth: number }[] = []
  const order = [0, 1, 2, 3, 0, 3, 1]                  // cada tipo una vez; luego se repiten salita y verde
  for (let n = 0; out.length < max && n < order.length; n++) {
    const k = KINDS[order[n]]
    let best: [number, number] | null = null, bd = Infinity
    for (let u = zone[0] + k.hu; u <= zone[2] - k.hu; u += 0.25) for (let v = zone[1] + k.hv; v <= zone[3] - k.hv; v += 0.25) {
      const r: UVRect = [u - k.hu, v - k.hv, u + k.hu, v + k.hv]
      if (busy.some((b) => hit(r, b))) continue
      const sb = screenBox(r, 1.3)
      if (labels.some((l) => sb[0] < l[2] && sb[2] > l[0] && sb[1] < l[3] && sb[3] > l[1])) continue
      const dd = Math.hypot(u - mu, v - mv)
      if (dd < bd) { bd = dd; best = [u, v] }
    }
    if (!best) continue
    const [u, v] = best
    busy.push([u - k.hu - 0.25, v - k.hv - 0.25, u + k.hu + 0.25, v + k.hv + 0.25])
    out.push({ svg: `<g class="iso-lounge">${k.draw(u, v)}</g>`, depth: G(u, v)[1] + k.hv * 0.5 * S })
  }
  return out
}
