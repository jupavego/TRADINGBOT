/** Pintura de la esfera del río: colores CSS → "r,g,b", destellos pre-renderizados y un «tinte»
 * bicolor (un color a la izquierda, otro a la derecha, fundidos en una franja horizontal) que se
 * aplica a trazos, rellenos y destellos; más capas estáticas (halo, cuerpo) cacheadas mientras
 * no cambien el reparto, la intensidad ni el tamaño. */

/** Tinte: "r,g,b" a la izquierda (`a`) y a la derecha (`b`), fundidos entre `x0` y `x1` (px). */
export interface Tint { a: string; b: string; x0: number; x1: number }
type Ctx = CanvasRenderingContext2D

/** Semiancho de la franja de fundido verde/rojo, en radios de la esfera. */
export const BAND = 0.4

/** Posición x (en radios, −1…1) que deja a su izquierda la fracción `f` del área del disco. */
export function areaSplit(f: number): number {
  let lo = -1, hi = 1
  for (let i = 0; i < 24; i++) {
    const x = (lo + hi) / 2
    if ((x * Math.sqrt(1 - x * x) + Math.asin(x) + Math.PI / 2) / Math.PI < f) lo = x
    else hi = x
  }
  return (lo + hi) / 2
}

const rgbCache = new Map<string, string>() // color CSS → "r,g,b"
const sprites = new Map<string, HTMLCanvasElement>() // "r,g,b" → destello
const layers = new Map<string, { key: string; cv: HTMLCanvasElement }>()

/** Color CSS (incl. `var()` / `color-mix`) → "r,g,b" resolviéndolo con el propio navegador. */
export function toRgb(css: string, host: HTMLElement): string {
  const key = css
  const hit = rgbCache.get(key)
  if (hit) return hit
  if (rgbCache.size > 64) rgbCache.clear()
  const probe = document.createElement('i')
  probe.style.color = css
  host.appendChild(probe)
  const computed = getComputedStyle(probe).color
  probe.remove()
  const c = document.createElement('canvas').getContext('2d')!
  c.fillStyle = computed
  c.fillRect(0, 0, 1, 1)
  const [r, g, b] = c.getImageData(0, 0, 1, 1).data
  rgbCache.set(key, `${r},${g},${b}`)
  return `${r},${g},${b}`
}

/** "r,g,b" mezclado `k` (0…1) hacia blanco (k > 0) o hacia negro (k < 0). */
export function shade(rgb: string, k: number): string {
  if (!k) return rgb
  return rgb.split(',').map((c) => Math.round(k > 0 ? +c + (255 - +c) * k : +c * (1 + k))).join(',')
}

/** Mezcla lineal de dos "r,g,b" (m = 0 → `a`, m = 1 → `b`). */
function mix(a: string, b: string, m: number): string {
  if (a === b || m <= 0) return a
  if (m >= 1) return b
  const B = b.split(',').map(Number)
  return a.split(',').map((c, i) => Math.round(+c + (B[i] - +c) * m)).join(',')
}

const frac = (t: Tint, x: number): number => (t.x1 > t.x0 ? Math.min(1, Math.max(0, (x - t.x0) / (t.x1 - t.x0))) : 0)

/** Color CSS del tinte en `x`, aclarado/oscurecido `k` y con alfa `al`. */
export function colorAt(t: Tint, x: number, k: number, al: number): string {
  return `rgba(${shade(mix(t.a, t.b, frac(t, x)), k)},${Math.max(0, al).toFixed(3)})`
}

/** Estilo opaco que sigue el tinte en horizontal (el alfa se da con `globalAlpha`). */
export function paint(g: Ctx, t: Tint, k: number): string | CanvasGradient {
  if (t.a === t.b) return `rgb(${shade(t.a, k)})`
  const grd = g.createLinearGradient(t.x0, 0, t.x1, 0)
  grd.addColorStop(0, `rgb(${shade(t.a, k)})`)
  grd.addColorStop(1, `rgb(${shade(t.b, k)})`)
  return grd
}

/** Destello pre-renderizado (núcleo blanco → color → transparente). */
function glow(rgb: string): HTMLCanvasElement {
  const hit = sprites.get(rgb)
  if (hit) return hit
  if (sprites.size > 40) sprites.clear()
  const c = document.createElement('canvas')
  c.width = c.height = 64
  const g = c.getContext('2d')!
  const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32)
  grd.addColorStop(0, 'rgba(255,255,255,1)')
  grd.addColorStop(0.14, `rgba(${rgb},.9)`)
  grd.addColorStop(0.4, `rgba(${rgb},.22)`)
  grd.addColorStop(1, `rgba(${rgb},0)`)
  g.fillStyle = grd
  g.fillRect(0, 0, 64, 64)
  sprites.set(rgb, c)
  return c
}

/** Destello del color del tinte en `x` (cuantizado en 10 pasos para reutilizar los sprites). */
export function glowAt(t: Tint, x: number): HTMLCanvasElement {
  return glow(mix(t.a, t.b, Math.round(frac(t, x) * 10) / 10))
}

/** Canvas de `w`×`h` px CSS con su contexto escalado a `dpr`. */
function surface(w: number, h: number, dpr: number): [HTMLCanvasElement, Ctx] {
  const cv = document.createElement('canvas')
  cv.width = Math.round(w * dpr)
  cv.height = Math.round(h * dpr)
  const g = cv.getContext('2d')!
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  return [cv, g]
}

/** Capa estática `name` pintada por `draw` con el tinte: cada color se enmascara con su rampa
 * de la franja y ambos se suman. Se recalcula solo si cambian `key`, el tinte o el tamaño. */
export function layer(name: string, key: string, t: Tint, w: number, h: number, dpr: number,
  draw: (g: Ctx, rgb: string) => void): HTMLCanvasElement {
  const full = `${key}|${t.a}|${t.b}|${t.x0.toFixed(1)}|${t.x1.toFixed(1)}|${w}x${h}@${dpr}`
  const hit = layers.get(name)
  if (hit?.key === full) return hit.cv
  const [out, og] = surface(w, h, dpr)
  if (t.a === t.b) draw(og, t.a)
  else {
    og.globalCompositeOperation = 'lighter'
    for (const [rgb, k] of [[t.a, 0], [t.b, 1]] as const) {
      const [tmp, tg] = surface(w, h, dpr)
      draw(tg, rgb)
      const mask = tg.createLinearGradient(t.x0, 0, t.x1, 0)
      mask.addColorStop(0, `rgba(0,0,0,${1 - k})`)
      mask.addColorStop(1, `rgba(0,0,0,${k})`)
      tg.globalCompositeOperation = 'destination-in'
      tg.fillStyle = mask
      tg.fillRect(0, 0, w, h)
      og.drawImage(tmp, 0, 0, w, h)
    }
  }
  layers.set(name, { key: full, cv: out })
  return out
}
