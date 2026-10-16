/** Geometría determinista de la esfera «red de nodos» del río (semilla fija; se calcula una vez):
 * nodos sobre la superficie y en un núcleo interior, aristas a los vecinos más próximos,
 * facetas triangulares, anillos orbitales de puntos y polvo flotante. */

export type V3 = [number, number, number]
export interface Node { p: V3; r: number; hub: boolean; ph: number; shell: boolean }
export interface Facet { v: [number, number, number]; lit: boolean; ph: number }
export interface Ring { pts: V3[]; speed: number }

/** PRNG determinista (mulberry32): la misma esfera en cada carga. */
function rng(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const rnd = rng(20261016)
const norm = (v: V3): V3 => { const l = Math.hypot(...v); return [v[0] / l, v[1] / l, v[2] / l] }
const dist = (a: V3, b: V3): number => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])
const scale = (v: V3, k: number): V3 => [v[0] * k, v[1] * k, v[2] * k]
const dir = (): V3 => {
  const y = rnd() * 2 - 1, a = rnd() * Math.PI * 2, r = Math.sqrt(1 - y * y)
  return [r * Math.cos(a), y, r * Math.sin(a)]
}

const SHELL = 420, CORE = 46

/** Nodos: espiral de Fibonacci con ruido (red irregular) + un núcleo interior disperso. */
export const NODES: Node[] = [
  ...Array.from({ length: SHELL }, (_, i): Node => {
    const y = 1 - (2 * (i + 0.5)) / SHELL, r = Math.sqrt(1 - y * y), a = i * Math.PI * (3 - Math.sqrt(5))
    const j = (): number => (rnd() - 0.5) * 0.08
    const p = norm([r * Math.cos(a) + j(), y + j(), r * Math.sin(a) + j()])
    const hub = rnd() < 0.12
    return { p, r: hub ? 1.5 + rnd() : 0.7 + rnd() * 0.6, hub, ph: rnd() * 6.3, shell: true }
  }),
  ...Array.from({ length: CORE }, (): Node =>
    ({ p: scale(dir(), 0.4 + rnd() * 0.45), r: 0.6 + rnd() * 0.5, hub: rnd() < 0.12, ph: rnd() * 6.3, shell: false })),
]

/** Une cada nodo con sus vecinos más próximos (la superficie solo consigo misma); sin duplicados. */
function link(): [number, number][] {
  const seen = new Set<number>(), out: [number, number][] = []
  NODES.forEach((n, i) => {
    const k = n.shell ? 5 : 3, maxD = n.shell ? 0.3 : 0.55
    NODES.map((m, j) => [j, dist(n.p, m.p)] as const)
      .filter(([j, d]) => j !== i && d < maxD && (!n.shell || NODES[j].shell))
      .sort((a, b) => a[1] - b[1]).slice(0, k)
      .forEach(([j]) => {
        const a = Math.min(i, j), b = Math.max(i, j)
        if (!seen.has(a * 1000 + b)) { seen.add(a * 1000 + b); out.push([a, b]) }
      })
  })
  return out
}

export const EDGES = link()

/** Facetas: triángulos de la red (tres nodos de superficie unidos entre sí); se rellena ~1 de 5. */
function facets(): Facet[] {
  const adj = NODES.map(() => new Set<number>())
  for (const [a, b] of EDGES) { adj[a].add(b); adj[b].add(a) }
  const out: Facet[] = []
  for (const [a, b] of EDGES) {
    if (!NODES[a].shell || !NODES[b].shell) continue
    for (const c of adj[a]) {
      if (c > b && adj[b].has(c) && NODES[c].shell && rnd() < 0.2) out.push({ v: [a, b, c], lit: rnd() < 0.2, ph: rnd() * 6.3 })
    }
  }
  return out
}

export const FACETS = facets()

/** Anillo de `n` puntos de radio `r`, inclinado `tilt` (rad sobre el plano de visión) y girado `roll`. */
function ring(r: number, tilt: number, roll: number, n: number, speed: number): Ring {
  const ct = Math.cos(tilt), st = Math.sin(tilt), cr = Math.cos(roll), sr = Math.sin(roll)
  const pts = Array.from({ length: n }, (_, k): V3 => {
    const a = (k / n) * Math.PI * 2, x = Math.cos(a) * r, z0 = Math.sin(a) * r
    const y = -z0 * st, z = z0 * ct
    return [x * cr - y * sr, x * sr + y * cr, z]
  })
  return { pts, speed }
}

/** Órbitas de partículas casi de canto, como cinturones alrededor de la esfera. */
export const RINGS: Ring[] = [ring(1.2, 0.3, -0.16, 150, 0.09), ring(1.3, 0.2, 0.12, 130, -0.06), ring(1.36, 0.42, -0.4, 100, 0.045)]

/** Polvo: partículas sueltas en una corteza alrededor de la esfera. */
export const DUST = Array.from({ length: 70 }, () => ({ p: scale(dir(), 1.06 + rnd() * 0.22), s: 1 + rnd() * 1.4, ph: rnd() * 6.3 }))

