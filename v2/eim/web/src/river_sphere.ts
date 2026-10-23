/** Esfera 3D del río de decisión al estilo «red de nodos»: cientos de nodos luminosos unidos a sus
 * vecinos, facetas triangulares translúcidas, destellos y cinturones orbitales de partículas.
 * Color = reparto subida/bajada (`data-up`): verde a la izquierda y rojo a la derecha, cada uno
 * con un área proporcional a su % y fundidos en degradado; sin señal → `data-color` (cian).
 * `data-fill` (ventaja del % mayor) aviva la intensidad. Un único bucle `requestAnimationFrame`
 * busca el canvas vigente en cada cuadro, así sobrevive a los re-renderizados del río (que
 * sustituyen el HTML) y se detiene si el canvas desaparece; mientras el río no está en pantalla
 * (desplazado u oculto por otra vista) no dibuja (T122). Geometría en `river_sphere_mesh`;
 * colores, destellos y capas estáticas en `river_sphere_paint`. */

import { DUST, EDGES, FACETS, NODES, RINGS, type V3 } from './river_sphere_mesh'
import { areaSplit, BAND, colorAt, glowAt, layer, paint, shade, toRgb, type Tint } from './river_sphere_paint'

type Ctx = CanvasRenderingContext2D

let running = false
let onScreen = true          // el río está a la vista (IntersectionObserver sobre su sección)
let watched: HTMLElement | null = null
const sparks = new Map<number, number>() // índice de nodo → instante de encendido

function rotate([x, y, z]: V3, ay: number, ax: number): V3 {
  const cy = Math.cos(ay), sy = Math.sin(ay), cx = Math.cos(ax), sx = Math.sin(ax)
  const x1 = x * cy + z * sy, z1 = -x * sy + z * cy
  return [x1, y * cx - z1 * sx, y * sx + z1 * cx]
}

function disc(g: Ctx, x: number, y: number, r: number, style: string | CanvasGradient): void {
  g.fillStyle = style
  g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill()
}

/** Tinte de la esfera: reparto subida (verde, izquierda) / bajada (rojo, derecha) como los % de
 * encima; la frontera deja a cada lado un área igual a su % y se funde en una franja. */
function tintOf(cv: HTMLCanvasElement, ox: number, R: number): Tint {
  const up = cv.dataset.up ? Number(cv.dataset.up) : NaN // vacío = sin señal
  if (up > 0 && up < 100) {
    const xb = ox + areaSplit(up / 100) * R, band = R * BAND
    return { a: toRgb('var(--up)', cv), b: toRgb('var(--down)', cv), x0: xb - band, x1: xb + band }
  }
  const one = toRgb(up >= 100 ? 'var(--up)' : up <= 0 ? 'var(--down)' : cv.dataset.color || '#22e1ff', cv)
  return { a: one, b: one, x0: 0, x1: 0 }
}

function draw(cv: HTMLCanvasElement, now: number, still: boolean): void {
  const dpr = window.devicePixelRatio || 1
  const w = cv.clientWidth, h = cv.clientHeight
  if (!w || !h) return
  if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr) }
  const g = cv.getContext('2d')!
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.globalCompositeOperation = 'source-over'
  g.globalAlpha = 1
  g.clearRect(0, 0, w, h)
  const fill = Math.min(1, Math.max(0, Number(cv.dataset.fill) || 0)) // ventaja del % mayor (0…1)
  const t = still ? 0.6 : now / 1000
  const R = Math.min(w, h) / 2 / 1.42, ox = w / 2, oy = h / 2
  const ay = t * 0.2, ax = 0.32 + Math.sin(t * 0.21) * 0.1
  const P = NODES.map((n) => rotate(n.p, ay, ax))
  const px = (p: V3): [number, number] => { const k = 1 + p[2] * 0.12; return [ox + p[0] * R * k, oy - p[1] * R * k] }
  const tint = tintOf(cv, ox, R)
  const solid = paint(g, tint, 0), bright = paint(g, tint, 0.5) // el alfa va en globalAlpha
  const sprite = (x: number, y: number, s: number, a: number): void => {
    g.globalAlpha = Math.max(0, Math.min(1, a))
    g.drawImage(glowAt(tint, x), x - s, y - s, 2 * s, 2 * s)
  }
  const flare = (x: number, y: number, l: number, a: number): void => { // cruz de luz
    g.globalAlpha = Math.max(0, Math.min(1, a))
    g.strokeStyle = bright; g.lineWidth = 0.8
    g.beginPath()
    g.moveTo(x - l, y); g.lineTo(x + l, y); g.moveTo(x, y - l); g.lineTo(x, y + l)
    g.stroke()
  }
  const blit = (name: string, paintLayer: (c: Ctx, rgb: string) => void): void => {
    g.globalAlpha = 1
    g.drawImage(layer(name, `${fill.toFixed(3)}|${R.toFixed(1)}`, tint, w, h, dpr, paintLayer), 0, 0, w, h)
  }

  // Halo exterior (capa estática).
  blit('halo', (c, rgb) => {
    const halo = c.createRadialGradient(ox, oy, R * 0.9, ox, oy, R * 1.3)
    halo.addColorStop(0, `rgba(${rgb},${(0.22 + 0.18 * fill).toFixed(3)})`)
    halo.addColorStop(1, `rgba(${rgb},0)`)
    disc(c, ox, oy, R * 1.3, halo)
  })
  orbitals(false)

  // Cuerpo (capa estática): interior profundo y opaco a medias, más luminoso hacia el borde.
  blit('body', (c, rgb) => {
    disc(c, ox, oy, R, `rgba(${shade(rgb, -0.82)},.72)`)
    const body = c.createRadialGradient(ox - R * 0.2, oy - R * 0.25, R * 0.1, ox, oy, R)
    body.addColorStop(0, `rgba(${rgb},${(0.04 + 0.06 * fill).toFixed(3)})`)
    body.addColorStop(0.75, `rgba(${rgb},${(0.07 + 0.08 * fill).toFixed(3)})`)
    body.addColorStop(1, `rgba(${rgb},${(0.24 + 0.18 * fill).toFixed(3)})`)
    disc(c, ox, oy, R, body)
    const rim = c.createRadialGradient(ox, oy, R * 0.86, ox, oy, R)
    rim.addColorStop(0, `rgba(${rgb},0)`)
    rim.addColorStop(1, `rgba(${shade(rgb, 0.5)},${(0.16 + 0.14 * fill).toFixed(3)})`)
    disc(c, ox, oy, R, rim)
  })
  g.globalCompositeOperation = 'lighter'
  for (const i of [11, 97, 203]) { // nebulosas internas que giran con la red
    const [x, y] = px(P[i])
    const neb = g.createRadialGradient(x, y, 0, x, y, R * 0.6)
    neb.addColorStop(0, colorAt(tint, x, 0, 0.09 + 0.07 * fill))
    neb.addColorStop(1, colorAt(tint, x, 0, 0))
    disc(g, ox, oy, R, neb)
  }

  // Red: aristas del núcleo y traseras (tenues), facetas, y aristas delanteras por brillo.
  const strokes: Path2D[] = Array.from({ length: 6 }, () => new Path2D())
  for (const [a, b] of EDGES) {
    const z = (P[a][2] + P[b][2]) / 2
    const inner = !NODES[a].shell || !NODES[b].shell
    const k = inner ? 0 : z <= 0 ? 1 : 2 + Math.min(3, Math.floor(z * 4))
    const [x1, y1] = px(P[a]), [x2, y2] = px(P[b])
    strokes[k].moveTo(x1, y1); strokes[k].lineTo(x2, y2)
  }
  const edge = (k: number, a: number, lw: number): void => {
    g.globalAlpha = Math.min(1, a * (0.85 + 0.3 * fill))
    g.strokeStyle = k > 3 ? bright : solid
    g.lineWidth = lw
    g.stroke(strokes[k])
  }
  edge(0, 0.2, 0.5); edge(1, 0.2, 0.55)
  // Facetas: veladura tenue; las «encendidas» son esquirlas de luz que nacen en un vértice.
  for (const f of FACETS) {
    const [a, b, c] = f.v.map((i) => px(P[i]))
    const z = f.v.reduce((s, i) => s + P[i][2], 0) / 3
    if (z < -0.3 || (f.lit && z < 0)) continue
    const depth = (0.35 + 0.65 * Math.max(0, z)) * (0.8 + 0.4 * fill)
    if (f.lit) {
      const pulse = 0.5 + 0.5 * Math.sin(t * 0.9 + f.ph), mx = (b[0] + c[0]) / 2
      const shard = g.createLinearGradient(a[0], a[1], mx, (b[1] + c[1]) / 2)
      shard.addColorStop(0, colorAt(tint, a[0], 0.5, (0.25 + 0.55 * pulse) * depth))
      shard.addColorStop(1, colorAt(tint, mx, 0, 0.04 * depth))
      g.globalAlpha = 1
      g.fillStyle = shard
    } else {
      g.globalAlpha = 0.06 * depth
      g.fillStyle = solid
    }
    g.beginPath()
    g.moveTo(...a); g.lineTo(...b); g.lineTo(...c)
    g.closePath(); g.fill()
  }
  for (let k = 2; k < 6; k++) edge(k, 0.28 + 0.16 * (k - 2), 0.5 + 0.2 * (k - 2))

  // Nodos: los traseros como puntos tenues; los delanteros con destello, más grandes los «hubs».
  g.fillStyle = solid
  NODES.forEach((n, i) => {
    const p = P[i], [x, y] = px(p)
    if (!n.shell) { sprite(x, y, 3 * n.r, 0.35); return }
    if (p[2] < 0) {
      g.globalAlpha = 0.3 + 0.2 * (1 + p[2])
      g.fillRect(x - 0.6, y - 0.6, 1.2, 1.2)
      return
    }
    const tw = n.hub ? 0.75 + 0.25 * Math.sin(t * 1.6 + n.ph) : 1
    sprite(x, y, (2.2 + 2.6 * p[2]) * n.r * (n.hub ? 2 : 1) * tw, 0.35 + 0.65 * p[2])
    if (n.hub && p[2] > 0.35 && tw > 0.9) flare(x, y, 5 + 7 * p[2], (tw - 0.9) * 8 * p[2])
  })
  // Chispas: nodos delanteros que se encienden y se apagan.
  if (!still && Math.random() < 0.06 + 0.08 * fill) sparks.set(Math.floor(Math.random() * NODES.length), now)
  for (const [i, t0] of sparks) {
    const life = (now - t0) / 1100
    if (life > 1) { sparks.delete(i); continue }
    if (P[i][2] < 0.1 || !NODES[i].shell) continue
    const [x, y] = px(P[i]), a = Math.sin(life * Math.PI)
    sprite(x, y, 9 + 6 * P[i][2], a)
    flare(x, y, 10 + 8 * P[i][2], a)
  }

  // Contorno luminoso y mitad delantera de las órbitas.
  g.globalCompositeOperation = 'source-over'
  g.globalAlpha = 0.75
  g.strokeStyle = bright; g.lineWidth = 1.1
  g.beginPath(); g.arc(ox, oy, R, 0, Math.PI * 2); g.stroke()
  orbitals(true)
  g.globalAlpha = 1

  /** Cinturones orbitales (un cometa de brillo recorre cada uno) y polvo; mitad trasera o delantera. */
  function orbitals(front: boolean): void {
    g.globalCompositeOperation = 'lighter'
    g.fillStyle = bright
    for (const r of RINGS) {
      const n = r.pts.length
      r.pts.forEach((p, k) => {
        if ((p[2] > 0) !== front) return
        const head = (((k / n - t * r.speed) % 1) + 1) % 1
        const a = (0.3 + 0.7 * head ** 6) * (front ? 1 : 0.55)
        const [x, y] = px(p)
        if (head > 0.975) { sprite(x, y, 7, a); return }
        g.globalAlpha = a
        g.fillRect(x - 0.8, y - 0.8, 1.6, 1.6)
      })
    }
    g.fillStyle = solid
    for (const d of DUST) {
      const p = rotate(d.p, ay * 0.6, ax)
      if ((p[2] > 0) !== front) continue
      const [x, y] = px(p)
      g.globalAlpha = Math.max(0, (0.3 + 0.4 * p[2]) * (0.55 + 0.45 * Math.sin(t * 1.3 + d.ph)) * (front ? 1 : 0.5))
      g.fillRect(x - d.s / 2, y - d.s / 2, d.s, d.s)
    }
    g.globalCompositeOperation = 'source-over'
    g.globalAlpha = 1
  }
}

/** Arranca (una sola vez) el bucle que anima el canvas `.hsphere` dentro de `root`. */
export function animateSphere(root: HTMLElement): void {
  const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const first = root.querySelector<HTMLCanvasElement>('canvas.hsphere')
  if (first && still) { draw(first, 0, true); return }
  if (running) return
  running = true
  if (watched !== root) {
    watched = root
    new IntersectionObserver((es) => { onScreen = es.some((e) => e.isIntersecting) }).observe(root)
  }
  const loop = (now: number): void => {
    const cv = root.querySelector<HTMLCanvasElement>('canvas.hsphere')
    if (!cv || !document.contains(cv)) { running = false; return }
    if (onScreen) draw(cv, now, false)
    requestAnimationFrame(loop)
  }
  requestAnimationFrame(loop)
}
