/** Esfera 3D del río de decisión: poliedro de Goldberg (hexágonos + 12 pentágonos) que gira en
 * un `<canvas>` con profundidad (cara trasera tenue), iluminación, chispas y un anillo orbital.
 * Un único bucle `requestAnimationFrame` busca el canvas vigente en cada cuadro, así sobrevive a
 * los re-renderizados del río (que sustituyen el HTML) y se detiene si el canvas desaparece. */

type V3 = [number, number, number]

const norm = (v: V3): V3 => { const l = Math.hypot(...v); return [v[0] / l, v[1] / l, v[2] / l] }

/** Aristas del dual de una icosfera subdividida `level` veces (celdas hexagonales). */
function goldberg(level: number): { pts: V3[]; edges: [number, number][] } {
  const t = (1 + Math.sqrt(5)) / 2
  const vs: V3[] = ([[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
    [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]] as V3[]).map(norm)
  let fs: [number, number, number][] = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4],
    [11, 10, 2], [10, 7, 6], [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11],
    [6, 2, 10], [8, 6, 7], [9, 8, 1]]
  for (let s = 0; s < level; s++) {
    const cache = new Map<string, number>()
    const mid = (a: number, b: number): number => {
      const k = a < b ? `${a}_${b}` : `${b}_${a}`
      let i = cache.get(k)
      if (i === undefined) {
        i = vs.length
        vs.push(norm([(vs[a][0] + vs[b][0]) / 2, (vs[a][1] + vs[b][1]) / 2, (vs[a][2] + vs[b][2]) / 2]))
        cache.set(k, i)
      }
      return i
    }
    fs = fs.flatMap(([a, b, c]) => {
      const ab = mid(a, b), bc = mid(b, c), ca = mid(c, a)
      return [[a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]] as [number, number, number][]
    })
  }
  // Dual: un punto por cara (centroide) y una arista por cada par de caras que comparten lado.
  const pts = fs.map(([a, b, c]) => norm([vs[a][0] + vs[b][0] + vs[c][0], vs[a][1] + vs[b][1] + vs[c][1], vs[a][2] + vs[b][2] + vs[c][2]]))
  const side = new Map<string, number>()
  const edges: [number, number][] = []
  fs.forEach(([a, b, c], f) => {
    for (const [p, q] of [[a, b], [b, c], [c, a]]) {
      const k = p < q ? `${p}_${q}` : `${q}_${p}`
      const g = side.get(k)
      if (g === undefined) side.set(k, f)
      else edges.push([g, f])
    }
  })
  return { pts, edges }
}

const MESH = goldberg(2)
const ORBIT: V3[] = Array.from({ length: 96 }, (_, k) => [Math.cos((k / 96) * 2 * Math.PI) * 1.32, 0, Math.sin((k / 96) * 2 * Math.PI) * 1.32])
let running = false
let rgbCache: [string, string] = ['', '0,225,255']
const sparks = new Map<number, number>() // índice de vértice → instante de encendido

/** Color CSS (incl. `var()` / `color-mix`) → "r,g,b" resolviéndolo con el propio navegador. */
function toRgb(css: string, host: HTMLElement): string {
  if (rgbCache[0] === css) return rgbCache[1]
  const probe = document.createElement('i')
  probe.style.color = css
  host.appendChild(probe)
  const computed = getComputedStyle(probe).color
  probe.remove()
  const c = document.createElement('canvas').getContext('2d')!
  c.fillStyle = computed
  c.fillRect(0, 0, 1, 1)
  const [r, g, b] = c.getImageData(0, 0, 1, 1).data
  rgbCache = [css, `${r},${g},${b}`]
  return rgbCache[1]
}

function rotate([x, y, z]: V3, ay: number, ax: number): V3 {
  const cy = Math.cos(ay), sy = Math.sin(ay), cx = Math.cos(ax), sx = Math.sin(ax)
  const x1 = x * cy + z * sy, z1 = -x * sy + z * cy
  return [x1, y * cx - z1 * sx, y * sx + z1 * cx]
}

function draw(cv: HTMLCanvasElement, now: number, still: boolean): void {
  const dpr = window.devicePixelRatio || 1
  const w = cv.clientWidth, h = cv.clientHeight
  if (!w || !h) return
  if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr) }
  const g = cv.getContext('2d')!
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.clearRect(0, 0, w, h)
  const rgb = toRgb(cv.dataset.color || '#22e1ff', cv)
  const t = still ? 0.6 : now / 1000
  const R = Math.min(w, h) / 2 / 1.42, ox = w / 2, oy = h / 2
  const ay = t * 0.32, ax = 0.38 + Math.sin(t * 0.21) * 0.12
  const P = MESH.pts.map((p) => rotate(p, ay, ax))
  const px = (p: V3): [number, number] => { const k = 1 + p[2] * 0.12; return [ox + p[0] * R * k, oy - p[1] * R * k] }

  // Cuerpo de vidrio: casi transparente en el centro y más luminoso en el borde (fresnel),
  // con un reflejo especular arriba a la izquierda; deja ver la cara trasera y el haz.
  const body = g.createRadialGradient(ox, oy, R * 0.2, ox, oy, R)
  const fill = Math.min(1, Math.max(0, Number(cv.dataset.fill) || 0)) // ventaja del % mayor (0…1)
  body.addColorStop(0, `rgba(${rgb},${(0.12 * fill).toFixed(3)})`)
  body.addColorStop(0.7, `rgba(${rgb},${(0.04 + 0.14 * fill).toFixed(3)})`)
  body.addColorStop(1, `rgba(${rgb},${(0.22 + 0.3 * fill).toFixed(3)})`)
  g.fillStyle = body
  g.beginPath(); g.arc(ox, oy, R, 0, Math.PI * 2); g.fill()
  const spec = g.createRadialGradient(ox - R * 0.42, oy - R * 0.45, 0, ox - R * 0.42, oy - R * 0.45, R * 0.45)
  spec.addColorStop(0, 'rgba(255,255,255,.18)'); spec.addColorStop(1, 'rgba(255,255,255,0)')
  g.fillStyle = spec
  g.beginPath(); g.arc(ox, oy, R, 0, Math.PI * 2); g.fill()

  // Aristas: primero las traseras (tenues), luego las delanteras (brillo y grosor según z).
  for (const front of [false, true]) {
    for (const [a, b] of MESH.edges) {
      const z = (P[a][2] + P[b][2]) / 2
      if ((z > 0) !== front) continue
      const [x1, y1] = px(P[a]), [x2, y2] = px(P[b])
      g.strokeStyle = `rgba(${rgb},${front ? (0.35 + z * 0.6).toFixed(2) : (0.14 + (1 + z) * 0.12).toFixed(2)})`
      g.lineWidth = front ? 0.7 + z * 1.1 : 0.6
      g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke()
    }
  }
  // Chispas: celdas delanteras que se encienden y se apagan.
  if (!still && Math.random() < 0.08) sparks.set(Math.floor(Math.random() * P.length), now)
  g.shadowColor = `rgb(${rgb})`; g.shadowBlur = 10
  for (const [i, t0] of sparks) {
    const life = (now - t0) / 900
    if (life > 1) { sparks.delete(i); continue }
    if (P[i][2] < 0.1) continue
    const [x, y] = px(P[i])
    g.fillStyle = `rgba(255,255,255,${(Math.sin(life * Math.PI) * 0.95).toFixed(2)})`
    g.beginPath(); g.arc(x, y, 1.6 + P[i][2] * 1.6, 0, Math.PI * 2); g.fill()
  }
  // Anillo orbital inclinado con un satélite; la mitad trasera queda detrás de la esfera.
  const O = ORBIT.map((p) => rotate(rotate(p, t * 0.5, 0), 0, 1.15))
  for (const front of [false, true]) {
    g.beginPath()
    O.forEach((p, k) => {
      if ((p[2] > 0) !== front) return
      const [x, y] = px(p)
      const prev = O[(k + O.length - 1) % O.length]
      if ((prev[2] > 0) !== front) g.moveTo(x, y); else g.lineTo(x, y)
    })
    g.strokeStyle = `rgba(${rgb},${front ? 0.8 : 0.2})`; g.lineWidth = front ? 1.4 : 0.8
    g.shadowBlur = front ? 8 : 0
    g.stroke()
  }
  const sat = O[Math.floor((t * 14) % O.length)]
  const [sx, sy] = px(sat)
  g.shadowBlur = 14; g.fillStyle = `rgba(255,255,255,${sat[2] > 0 ? 1 : 0.3})`
  g.beginPath(); g.arc(sx, sy, sat[2] > 0 ? 3 : 2, 0, Math.PI * 2); g.fill()
  g.shadowBlur = 0
  // Contorno brillante.
  g.strokeStyle = `rgba(${rgb},.9)`; g.lineWidth = 1.5
  g.beginPath(); g.arc(ox, oy, R, 0, Math.PI * 2); g.stroke()
}

/** Arranca (una sola vez) el bucle que anima el canvas `.hsphere` dentro de `root`. */
export function animateSphere(root: HTMLElement): void {
  const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const first = root.querySelector<HTMLCanvasElement>('canvas.hsphere')
  if (first && still) { draw(first, 0, true); return }
  if (running) return
  running = true
  const loop = (now: number): void => {
    const cv = root.querySelector<HTMLCanvasElement>('canvas.hsphere')
    if (!cv || !document.contains(cv)) { running = false; return }
    draw(cv, now, false)
    requestAnimationFrame(loop)
  }
  requestAnimationFrame(loop)
}
