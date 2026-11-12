/** Órbitas de los agentes del río de decisión, al estilo de un sistema solar: la esfera central es
 * el sol y cada agente un planeta. Hay varias órbitas a distinta distancia, cada una con su
 * inclinación (unas suben por un lado y bajan por el otro) y un leve desplazamiento vertical; las
 * cercanas giran más rápido que las lejanas y cada planeta tiene su propio tamaño. En la mitad
 * delantera pasan por delante de la esfera y en la trasera por detrás (capa `front`/`back`).
 * La fase vive en el módulo y solo avanza mientras nada la detiene, así un re-renderizado del
 * río deja cada planeta donde estaba. Se detiene con el puntero encima de un agente, con un
 * detalle abierto, con el río fuera de pantalla o con «reducir movimiento». Un único bucle
 * `requestAnimationFrame` busca los nodos vigentes en cada cuadro y se apaga si el río desaparece. */

interface Orbit { rx: number; ry: number; roll: number; dy: number; period: number }

/** Órbitas de dentro hacia fuera (unidades del viewBox; periodo en segundos por vuelta). */
const ORBITS: Orbit[] = [
  { rx: 205, ry: 92, roll: -0.13, dy: -8, period: 150 },
  { rx: 275, ry: 104, roll: 0.1, dy: 12, period: 195 },
  { rx: 340, ry: 150, roll: -0.05, dy: -14, period: 240 },
  { rx: 405, ry: 128, roll: 0.13, dy: 8, period: 285 },
  { rx: 470, ry: 176, roll: -0.08, dy: 4, period: 330 },
]
/** Tamaño propio de cada planeta (se reparte en ciclo). */
const SIZES = [1.2, 0.8, 1.0, 0.9, 1.3, 0.75, 1.1, 0.85]

/** Media altura que ocupa el sistema (para dimensionar el río). */
export const ORBIT_EXTENT = Math.max(...ORBITS.map((o) =>
  Math.hypot(o.rx * Math.sin(o.roll), o.ry * Math.cos(o.roll)) + Math.abs(o.dy)))

/** Trayectorias tenues de las órbitas (SVG estático, bajo los planetas). */
export function orbitPaths(cx: number, cy: number): string {
  return '<g class="orbit-paths">' + ORBITS.map((o) => {
    const y = cy + o.dy
    return `<ellipse cx="${cx}" cy="${y.toFixed(1)}" rx="${o.rx}" ry="${o.ry}" ` +
      `transform="rotate(${((o.roll * 180) / Math.PI).toFixed(2)} ${cx} ${y.toFixed(1)})"/>`
  }).join('') + '</g>'
}

let t = 0                     // segundos de órbita transcurridos (persiste entre renderizados)
let last = 0
let running = false
let hold = false              // puntero sobre un agente
let frozen = (): boolean => false
let center: [number, number] = [0, 0]

export interface OrbitPos { x: number; y: number; s: number; o: number; front: boolean; depth: number }

/** Posición del planeta `k` de `n` alrededor de (cx, cy). Los agentes llenan las órbitas de
 * dentro hacia fuera por tramos (el `k` más bajo, la órbita más cercana) y, dentro de cada una,
 * quedan separados por igual (con un desfase propio por órbita). */
export function orbitPos(k: number, n: number, cx: number, cy: number): OrbitPos {
  const L = ORBITS.length
  const i = Math.min(L - 1, Math.floor((k * L) / Math.max(1, n))), o = ORBITS[i]
  const first = Math.ceil((i * n) / L)
  const per = Math.ceil(((i + 1) * n) / L) - first // planetas en esta órbita
  const slot = k - first
  const a = (t / o.period) * Math.PI * 2 + (slot / Math.max(1, per)) * Math.PI * 2 + i * 2.39996
  const ex = o.rx * Math.cos(a), ey = o.ry * Math.sin(a)
  const depth = Math.sin(a) // +1 delante (abajo), −1 detrás (arriba)
  const size = SIZES[k % SIZES.length]
  return {
    x: cx + ex * Math.cos(o.roll) - ey * Math.sin(o.roll),
    y: cy + o.dy + ex * Math.sin(o.roll) + ey * Math.cos(o.roll),
    s: size * (0.82 + 0.26 * (depth + 1) / 2),
    o: 0.62 + 0.38 * (depth + 1) / 2,
    front: depth > 0,
    depth,
  }
}

export const orbitTransform = (p: OrbitPos): string =>
  `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) scale(${p.s.toFixed(3)})`

/** Marca si el puntero está sobre un agente (pausa la órbita mientras tanto). */
export function holdOrbit(on: boolean): void { hold = on }

/** Arranca (una sola vez) el bucle que mueve los `g.trib[data-k]` de `root` entre las capas
 * `g.orbit-back` (bajo la esfera) y `g.orbit-front` (sobre ella), ordenados por profundidad.
 * `paused` se consulta en cada cuadro (p. ej. hay un detalle abierto). */
export function animateOrbit(root: HTMLElement, cx: number, cy: number, paused: () => boolean): void {
  frozen = paused
  center = [cx, cy]
  if (running || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  running = true
  last = performance.now()
  const loop = (now: number): void => {
    const back = root.querySelector('g.orbit-back'), front = root.querySelector('g.orbit-front')
    if (!back || !front || !document.contains(root)) { running = false; return }
    const dt = Math.min(0.1, (now - last) / 1000)
    last = now
    if (!(hold || frozen() || document.hidden || !root.offsetParent)) {
      t += dt
      place(root, back, front)
    }
    requestAnimationFrame(loop)
  }
  requestAnimationFrame(loop)
}

function place(root: HTMLElement, back: Element, front: Element): void {
  const nodes = [...root.querySelectorAll<SVGGElement>('g.trib[data-k]')]
  const n = nodes.length
  const at = nodes.map((g) => ({ g, p: orbitPos(Number(g.dataset.k), n, center[0], center[1]) }))
  for (const { g, p } of at) {
    g.setAttribute('transform', orbitTransform(p))
    g.style.opacity = p.o.toFixed(2)
  }
  // capa y orden de pintado (los más cercanos encima); solo se toca el DOM si cambian
  for (const [layer, isFront] of [[back, false], [front, true]] as const) {
    const want = at.filter((a) => a.p.front === isFront).sort((a, b) => a.p.depth - b.p.depth).map((a) => a.g)
    const have = [...layer.children]
    if (want.length !== have.length || want.some((g, k) => have[k] !== g)) want.forEach((g) => layer.appendChild(g))
  }
}
