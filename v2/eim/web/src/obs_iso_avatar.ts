/** Avatares del mapa isométrico (SV a la izquierda, JP a la derecha): una figura de pie cuya cabeza es
 * la esfera «red de nodos» principal de la interfaz (misma geometría de `river_sphere_mesh`), en azul y
 * quieta: se dibuja una vez como <symbol> en SVG y se reutiliza en los dos avatares. Solo decora. */
import { EDGES, FACETS, NODES, RINGS, type V3 } from './river_sphere_mesh'

const RGB = '64,140,255', HI = '170,205,255', R = 50          // radio de la esfera en el símbolo (unidades)
const AY = 0.12, AX = 0.333                                       // la misma pose que la esfera quieta del río

function rot([x, y, z]: V3): V3 {
  const cy = Math.cos(AY), sy = Math.sin(AY), cx = Math.cos(AX), sx = Math.sin(AX)
  const x1 = x * cy + z * sy, z1 = -x * sy + z * cy
  return [x1, y * cx - z1 * sx, y * sx + z1 * cx]
}
const px = (p: V3): [number, number] => { const k = 1 + p[2] * 0.12; return [p[0] * R * k, -p[1] * R * k] }
const f = (n: number): string => n.toFixed(1)

/** La esfera: halo, cuerpo, red (aristas traseras tenues y delanteras brillantes), facetas, nodos y órbitas. */
function sphere(): string {
  const P = NODES.map((n) => rot(n.p))
  const paths = ['', '', '', '']                                   // núcleo · trasera · media · delantera
  for (const [a, b] of EDGES) {
    const z = (P[a][2] + P[b][2]) / 2, inner = !NODES[a].shell || !NODES[b].shell
    const k = inner ? 0 : z <= 0 ? 1 : z < 0.5 ? 2 : 3, [x1, y1] = px(P[a]), [x2, y2] = px(P[b])
    paths[k] += `M${f(x1)} ${f(y1)}L${f(x2)} ${f(y2)}`
  }
  let fac = ''
  for (const t of FACETS) {
    const z = t.v.reduce((s, i) => s + P[i][2], 0) / 3
    if (z < 0) continue
    const q = t.v.map((i) => px(P[i]))
    fac += `<polygon points="${q.map((p) => `${f(p[0])},${f(p[1])}`).join(' ')}" fill="rgb(${t.lit ? HI : RGB})" opacity="${(t.lit ? 0.18 + 0.3 * z : 0.05 + 0.06 * z).toFixed(2)}"/>`
  }
  let dots = '', glow = ''
  NODES.forEach((n, i) => {
    const p = P[i], [x, y] = px(p)
    if (!n.shell) { dots += `<circle cx="${f(x)}" cy="${f(y)}" r=".7" fill="rgb(${HI})" opacity=".35"/>`; return }
    if (p[2] < 0) { dots += `<circle cx="${f(x)}" cy="${f(y)}" r=".5" fill="rgb(${RGB})" opacity="${(0.25 + 0.2 * (1 + p[2])).toFixed(2)}"/>`; return }
    const s = (0.5 + 0.7 * p[2]) * n.r * (n.hub ? 1.6 : 1)
    if (n.hub) glow += `<circle cx="${f(x)}" cy="${f(y)}" r="${f(s * 3.2)}" fill="url(#iso-av-dot)" opacity="${(0.5 + 0.5 * p[2]).toFixed(2)}"/>`
    dots += `<circle cx="${f(x)}" cy="${f(y)}" r="${f(s)}" fill="#eaf3ff" opacity="${(0.45 + 0.55 * p[2]).toFixed(2)}"/>`
  })
  const orbit = (front: boolean): string => RINGS.map((r) => r.pts.filter((p) => (p[2] > 0) === front)
    .map((p) => { const [x, y] = px(p); return `<rect x="${f(x - 0.6)}" y="${f(y - 0.6)}" width="1.2" height="1.2"/>` }).join('')).join('')
  return `<circle r="${R * 1.3}" fill="url(#iso-av-halo)"/><g fill="rgb(${HI})" opacity=".45">${orbit(false)}</g>`
    + `<circle r="${R}" fill="#06122e" opacity=".92"/><circle r="${R}" fill="url(#iso-av-body)"/>`
    + `<path d="${paths[0]}" stroke="rgb(${RGB})" stroke-width=".35" opacity=".25"/><path d="${paths[1]}" stroke="rgb(${RGB})" stroke-width=".4" opacity=".25"/>`
    + fac + `<path d="${paths[2]}" stroke="rgb(${RGB})" stroke-width=".55" opacity=".55"/><path d="${paths[3]}" stroke="rgb(${HI})" stroke-width=".7" opacity=".8"/>`
    + glow + dots + `<circle r="${R}" fill="none" stroke="rgb(${HI})" stroke-width="1.1" opacity=".75"/><g fill="rgb(${HI})">${orbit(true)}</g>`
}

/** Cuerpo de pie, de frente, con traje oscuro y filos azules (los pies en y = 0, el cuello en y = -150). */
const BODY = `<ellipse cx="0" cy="0" rx="46" ry="15" fill="rgb(${RGB})" opacity=".18"/>`
  + '<path d="M-17,-58 L-19,-6 L-5,-6 L-2,-50 L2,-50 L5,-6 L19,-6 L17,-58 Z" fill="#14203f"/>'                 // piernas
  + '<path d="M-21,-7 h17 v6 h-20 z M4,-7 h17 l3,6 h-20 z" fill="#0b1226"/>'                                   // zapatos
  + '<path d="M-30,-140 Q0,-152 30,-140 L33,-96 L20,-56 L-20,-56 L-33,-96 Z" fill="#1a2a55"/>'                // torso
  + '<path d="M-29,-141 Q-41,-136 -43,-120 L-45,-66 L-35,-64 L-33,-112 Z M29,-141 Q41,-136 43,-120 L45,-66 L35,-64 L33,-112 Z" fill="#22356c"/>'   // brazos
  + `<path d="M-43,-120 L-45,-66 M43,-120 L45,-66" stroke="rgb(${RGB})" stroke-width="1.4" opacity=".8"/>`
  + '<circle cx="-40" cy="-60" r="5.5" fill="#9cc4ff"/><circle cx="40" cy="-60" r="5.5" fill="#9cc4ff"/>'      // manos
  + `<path d="M0,-148 L0,-60 M-30,-140 L-33,-96 L-20,-56 M30,-140 L33,-96 L20,-56" fill="none" stroke="rgb(${RGB})" stroke-width="1.6" opacity=".85"/>`
  + `<path d="M-14,-150 L0,-128 L14,-150" fill="none" stroke="rgb(${HI})" stroke-width="2"/>`
  + '<rect x="-7" y="-160" width="14" height="14" rx="4" fill="#1a2a55"/>'                                     // cuello

/** Definiciones compartidas (van dentro de <defs> del mapa). */
export function avatarDefs(): string {
  return `<radialGradient id="iso-av-halo"><stop offset=".68" stop-color="rgb(${RGB})" stop-opacity=".35"/><stop offset="1" stop-color="rgb(${RGB})" stop-opacity="0"/></radialGradient>`
    + `<radialGradient id="iso-av-body" cx=".4" cy=".37" r=".65"><stop offset="0" stop-color="rgb(${RGB})" stop-opacity=".08"/><stop offset=".75" stop-color="rgb(${RGB})" stop-opacity=".12"/><stop offset="1" stop-color="rgb(${HI})" stop-opacity=".4"/></radialGradient>`
    + `<radialGradient id="iso-av-dot"><stop offset="0" stop-color="rgb(${HI})" stop-opacity=".9"/><stop offset="1" stop-color="rgb(${RGB})" stop-opacity="0"/></radialGradient>`
    + `<symbol id="iso-av" viewBox="-70 -270 140 290" overflow="visible">${BODY}<g transform="translate(0,-208)">${sphere()}</g></symbol>`
}

/** Un avatar de `h` píxeles de alto con los pies en (x, y) y su nombre debajo. */
export function avatar(name: string, x: number, y: number, h = 190): string {
  const w = (h * 140) / 290, ny = y + 26
  return `<g class="iso-avatar" role="img" aria-label="${name}"><use href="#iso-av" x="${f(x - w / 2)}" y="${f(y - (h * 270) / 290)}" width="${f(w)}" height="${f(h)}"/>`
    + `<rect x="${f(x - 26)}" y="${f(ny - 14)}" width="52" height="24" rx="12" fill="#0a1146" stroke="rgb(${RGB})" stroke-width="1.5"/>`
    + `<text x="${f(x)}" y="${f(ny + 3)}" class="iso-av-name">${name}</text></g>`
}
