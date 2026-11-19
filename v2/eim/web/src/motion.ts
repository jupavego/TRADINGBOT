/** Reloj de animación compartido (rendimiento). Las animaciones CSS y SMIL de un SVG repintan TODO
 * el SVG en cada cuadro de la pantalla (60 por segundo) aunque solo se mueva una línea; en el mapa del
 * sistema y en el río eso era el grueso del lag. Aquí cada «pista» (un elemento raíz) congela sus
 * animaciones con CSS (`.motion-stepped`) y este reloj las avanza a mano a un ritmo propio (24 o 12
 * cuadros por segundo), todas en el mismo cuadro. La pista solo avanza si está en pantalla, con la
 * pestaña visible, sin desplazamiento de la página en curso y sin que su `hold()` la detenga
 * (p. ej. mientras se arrastra el mapa): así nada se repinta mientras el usuario se mueve. */

const TICK_MS = 1000 / 24 - 2        // margen para no saltarse cuadros de una pantalla de 60 Hz
const SCROLL_IDLE_MS = 160           // tras el último evento de desplazamiento, la página «se quedó quieta»

export interface MotionOpts {
  /** Ritmo de la pista en cuadros por segundo (≤ 24). */
  fps?: number
  /** Mientras devuelva `true`, la pista no avanza ni repinta (p. ej. arrastre del mapa). */
  hold?: () => boolean
  /** Se llama en cada cuadro de la pista con los ms transcurridos (p. ej. mover los planetas). */
  onTick?: (dtMs: number) => void
  /** Solo para animaciones a saltos (`steps()`): [periodo, fase] en ms. El tiempo se redondea a
   * `fase + k·periodo` y la pista solo toca sus animaciones cuando cambia `k`: el SVG se redibuja
   * únicamente en los instantes en que el parpadeo cambia, no en cada cuadro. */
  quant?: [number, number]
}

interface Track {
  root: Element
  every: number
  acc: number
  t: number                          // tiempo propio de la pista (ms), solo corre mientras avanza
  lastQ: number                      // último instante redondeado aplicado (pistas con `quant`)
  visible: boolean
  opts: MotionOpts
  anims: CSSAnimation[] | null       // lista en caché; null = hay que volver a leerla
  smil: SVGSVGElement[]
  base: WeakMap<Animation, number>
  svgBase: WeakMap<SVGSVGElement, number>
  io: IntersectionObserver
  mo: MutationObserver
}

const tracks = new Map<Element, Track>()
const frameCbs = new Set<(now: number) => void>()
let raf = 0
let last = 0
let scrolling = false
let scrollTimer = 0

/** `true` mientras la página se está desplazando (y un instante después). */
export const isScrolling = (): boolean => scrolling

if (typeof window !== 'undefined') {
  window.addEventListener('scroll', () => {
    scrolling = true
    clearTimeout(scrollTimer)
    scrollTimer = window.setTimeout(() => { scrolling = false }, SCROLL_IDLE_MS)
  }, { passive: true, capture: true })
}

function ensureLoop(): void {
  if (!raf && (tracks.size || frameCbs.size)) raf = requestAnimationFrame(loop)
}

function loop(now: number): void {
  raf = 0
  if (now - last >= TICK_MS) {
    const dt = last ? Math.min(100, now - last) : 0   // tras una pausa larga no hay salto
    last = now
    if (!document.hidden && !scrolling) {
      frameCbs.forEach((cb) => cb(now))
      tracks.forEach((tr) => step(tr, dt))
    }
  }
  ensureLoop()
}

function collect(tr: Track): void {
  tr.anims = tr.root.getAnimations({ subtree: true })
    .filter((a): a is CSSAnimation => typeof CSSAnimation !== 'undefined' && a instanceof CSSAnimation)
  const svgs = tr.root instanceof SVGSVGElement ? [tr.root] : [...tr.root.querySelectorAll('svg')]
  tr.smil = svgs.filter((s) => s.querySelector('animate, animateMotion, animateTransform') !== null)
}

function step(tr: Track, dt: number): void {
  if (!tr.root.isConnected) { release(tr.root); return }
  if (!tr.visible || tr.opts.hold?.()) return
  tr.acc += dt
  if (tr.acc < tr.every) return
  const d = tr.acc
  tr.acc = 0
  tr.t += d
  tr.opts.onTick?.(d)
  if (!tr.anims) { collect(tr); tr.lastQ = NaN }
  const q = tr.opts.quant
  const now = q ? q[1] + Math.floor((tr.t - q[1]) / q[0]) * q[0] : tr.t
  if (q && (now === tr.lastQ || now < 0)) return     // el parpadeo no cambia: nada que redibujar
  tr.lastQ = now
  for (const a of tr.anims!) {
    let b = tr.base.get(a)
    if (b === undefined) { b = Number(a.currentTime ?? 0) - tr.t; tr.base.set(a, b) }  // conserva retrasos y desfases
    a.currentTime = now + b
  }
  for (const s of tr.smil) {
    let b = tr.svgBase.get(s)
    if (b === undefined) { s.pauseAnimations(); b = s.getCurrentTime() * 1000 - tr.t; tr.svgBase.set(s, b) }
    s.setCurrentTime((now + b) / 1000)
  }
}

/** Pone `root` bajo el reloj compartido (o actualiza sus opciones si ya lo estaba). */
export function stepMotion(root: Element, opts: MotionOpts = {}): void {
  const every = 1000 / Math.min(24, Math.max(1, opts.fps ?? 24)) - 2
  const had = tracks.get(root)
  if (had) { had.opts = opts; had.every = every; had.anims = null; had.lastQ = NaN; return }
  root.classList.add('motion-stepped')
  const tr: Track = {
    root, every, acc: 0, t: 0, lastQ: NaN, visible: true, opts, anims: null, smil: [],
    base: new WeakMap(), svgBase: new WeakMap(),
    io: new IntersectionObserver((es) => { tr.visible = es.some((e) => e.isIntersecting) }),
    mo: new MutationObserver(() => { tr.anims = null }),
  }
  tr.io.observe(root)
  // nodos nuevos o clases nuevas pueden traer animaciones nuevas: se vuelve a leer la lista
  tr.mo.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] })
  tracks.set(root, tr)
  ensureLoop()
}

/** Saca `root` del reloj (sus animaciones quedan congeladas donde estaban). */
export function release(root: Element): void {
  const tr = tracks.get(root)
  if (!tr) return
  tr.io.disconnect(); tr.mo.disconnect()
  tracks.delete(root)
}

/** Llama `cb` en cada cuadro del reloj (24 por segundo) mientras la página está quieta y visible;
 * devuelve la función que lo da de baja. Para dibujos en canvas que deben ir al mismo ritmo. */
export function onMotionFrame(cb: (now: number) => void): () => void {
  frameCbs.add(cb)
  ensureLoop()
  return () => { frameCbs.delete(cb) }
}
