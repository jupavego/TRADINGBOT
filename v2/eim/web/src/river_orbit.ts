/** Órbita de los agentes del río de decisión: cada agente es un satélite que gira despacio
 * alrededor de la esfera central sobre una elipse inclinada (arriba = detrás, abajo = delante).
 * La fase vive en el módulo y solo avanza mientras nada la detiene, así un re-renderizado del
 * río (datos nuevos, clic) deja cada satélite donde estaba. Se detiene con el puntero encima de
 * un agente (para tocarlo sin perseguirlo), con un detalle abierto, con el río fuera de pantalla
 * o con «reducir movimiento» activo. Un único bucle `requestAnimationFrame` busca los nodos
 * vigentes en cada cuadro y se apaga si el río desaparece. */

/** Semiejes de la órbita (unidades del viewBox) y duración de una vuelta completa. */
export const ORX = 460, ORY = 230
const PERIOD_S = 180

let phase = 0                 // radianes recorridos (persiste entre renderizados)
let last = 0                  // instante del cuadro anterior
let running = false
let hold = false              // puntero sobre un agente
let frozen = (): boolean => false
let orbitCenter: [number, number] = [0, 0]

export interface OrbitPos { x: number; y: number; s: number; o: number }

/** Posición del satélite `k` de `n` alrededor de (cx, cy): reparto uniforme en la elipse. */
export function orbitPos(k: number, n: number, cx: number, cy: number): OrbitPos {
  const a = phase + (k / Math.max(1, n)) * Math.PI * 2 + Math.PI / 2
  const depth = Math.sin(a) // +1 delante (abajo), −1 detrás (arriba)
  return {
    x: cx + ORX * Math.cos(a),
    y: cy + ORY * depth,
    s: 0.8 + 0.25 * (depth + 1) / 2,
    o: 0.6 + 0.4 * (depth + 1) / 2,
  }
}

export const orbitTransform = (p: OrbitPos): string =>
  `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) scale(${p.s.toFixed(3)})`

/** Marca si el puntero está sobre un agente (pausa la órbita mientras tanto). */
export function holdOrbit(on: boolean): void { hold = on }

/** Arranca (una sola vez) el bucle que mueve los `g.trib[data-k]` de `root`. `paused` se
 * consulta en cada cuadro (p. ej. hay un detalle abierto). */
export function animateOrbit(root: HTMLElement, cx: number, cy: number, paused: () => boolean): void {
  frozen = paused
  orbitCenter = [cx, cy]
  if (running || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  running = true
  last = performance.now()
  const loop = (now: number): void => {
    const nodes = root.querySelectorAll<SVGGElement>('g.trib[data-k]')
    if (!nodes.length || !document.contains(root)) { running = false; return }
    const dt = Math.min(0.1, (now - last) / 1000)
    last = now
    if (hold || frozen() || document.hidden || !root.offsetParent) { requestAnimationFrame(loop); return }
    phase = (phase + (dt * Math.PI * 2) / PERIOD_S) % (Math.PI * 2)
    const n = nodes.length
    nodes.forEach((g) => {
      const p = orbitPos(Number(g.dataset.k), n, orbitCenter[0], orbitCenter[1])
      g.setAttribute('transform', orbitTransform(p))
      g.style.opacity = p.o.toFixed(2)
    })
    requestAnimationFrame(loop)
  }
  requestAnimationFrame(loop)
}
