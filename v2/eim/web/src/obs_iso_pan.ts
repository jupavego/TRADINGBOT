/** Zoom y desplazamiento del mapa isométrico: la rueda del mouse acerca o aleja hacia el puntero y el
 * clic sostenido arrastra el mapa en cualquier dirección (también con zoom). El encuadre se conserva
 * entre los repintados del sondeo; al cambiar de vista (mapa completo ↔ sala ampliada) vuelve al
 * encuadre de esa vista. Un arrastre no cuenta como clic: soltar tras mover no abre salas ni puestos.
 * Fluidez: durante el gesto el mapa no se redibuja; se mueve y escala como una imagen en la GPU
 * (`transform` en `.iso-stage`, un cuadro por refresco de pantalla) y las animaciones se detienen
 * (`moving`). Al soltar (o 140 ms después de la última vuelta de rueda) el encuadre se fija en el
 * `viewBox` de los SVG, así el dibujo vuelve a quedar nítido. */
type Box = [number, number, number, number]

const DRAG_PX = 5           // a partir de aquí el gesto es arrastre, no clic
const ZMIN = 1 / 8          // acercamiento máximo: 8×
const ZMAX = 1.25           // alejamiento máximo: un poco más que el encuadre completo
const WHEEL_IDLE_MS = 140   // sin rueda durante este tiempo, el zoom se fija (redibujo nítido)

export class IsoPan {
  private scope = ''
  private base: Box | null = null
  private cur: Box | null = null          // encuadre pedido (durante el gesto va por delante del dibujo)
  private shown: Box | null = null        // encuadre que tienen los `viewBox` (último fijado)
  private rect: DOMRect | null = null     // caja del dibujo sin transformar, medida al empezar el gesto
  private drag: { x: number; y: number; box: Box; id: number; moved: boolean } | null = null
  private swallow = false
  private raf = 0
  private idle = 0
  /** `true` mientras dura un gesto de zoom o arrastre (el mapa no anima entretanto). */
  moving = false

  constructor(private host: HTMLElement) {
    host.addEventListener('wheel', (e) => this.onWheel(e), { passive: false })
    host.addEventListener('pointerdown', (e) => this.onDown(e))
    host.addEventListener('pointermove', (e) => this.onMove(e))
    host.addEventListener('pointerup', (e) => this.onUp(e))
    host.addEventListener('pointercancel', (e) => this.onUp(e))
    host.addEventListener('click', (e) => {   // fase de captura: el clic de fin de arrastre no llega a la vista
      if (this.swallow) { this.swallow = false; e.stopPropagation(); e.preventDefault() }
      else if ((e.target as Element).closest('[data-act="iso-reset"]')) { e.stopPropagation(); this.reset() }
    }, true)
    host.addEventListener('dblclick', (e) => { if (!(e.target as Element).closest('.obs-n')) this.reset() })
  }

  private svg = (): SVGSVGElement | null => this.host.querySelector<SVGSVGElement>('svg.iso-svg')
  /** Lo que se mueve durante el gesto: las capas apiladas del mapa, o el SVG único de la sala ampliada. */
  private stage = (): HTMLElement | SVGSVGElement | null =>
    this.host.querySelector<HTMLElement>('.iso-stage') ?? this.svg()

  /** Tras redibujar: guarda el encuadre original y, si seguimos en la misma vista, repone el zoom. */
  apply(scope: string): void {
    const svg = this.svg(); if (!svg) return
    const vb = (svg.getAttribute('viewBox') ?? '').split(/\s+/).map(Number)
    if (vb.length !== 4 || vb.some((n) => !Number.isFinite(n))) return
    const same = scope === this.scope && this.cur
    this.scope = scope; this.base = vb as Box
    if (!same) this.cur = [...this.base]
    this.clamp(this.cur!)
    this.commit()
  }

  reset(): void { if (this.base) { this.cur = [...this.base]; this.commit() } }

  /** Limita el encuadre pedido (zoom y centro dentro del mapa) y lo deja en `cur`. */
  private clamp(b: Box): void {
    const bs = this.base; if (!bs) return
    const w = Math.min(Math.max(b[2], bs[2] * ZMIN), bs[2] * ZMAX), h = w * (bs[3] / bs[2])
    const cx = Math.min(Math.max(b[0] + b[2] / 2, bs[0]), bs[0] + bs[2])   // el centro no sale del mapa
    const cy = Math.min(Math.max(b[1] + b[3] / 2, bs[1]), bs[1] + bs[3])
    this.cur = [cx - w / 2, cy - h / 2, w, h]
  }

  /** Pide un encuadre durante el gesto: se muestra en el próximo cuadro, sin redibujar el SVG. */
  private request(b: Box): void {
    this.clamp(b)
    if (!this.raf) this.raf = requestAnimationFrame(() => { this.raf = 0; this.preview() })
  }

  private begin(): void {
    if (this.moving) return
    const st = this.stage(); if (!st) return
    this.moving = true
    this.rect = st.getBoundingClientRect()    // aún sin transformar: el encuadre fijado es el que se ve
    st.style.transformOrigin = '0 0'
    st.style.willChange = 'transform'          // capa propia solo mientras dura el gesto
  }

  /** Escala de unidades del dibujo por píxel y bandas de «meet» (el SVG conserva su proporción). */
  private fit(b: Box, r: DOMRect): { k: number; ox: number; oy: number } {
    const k = Math.max(b[2] / r.width, b[3] / r.height)
    return { k, ox: (r.width - b[2] / k) / 2, oy: (r.height - b[3] / k) / 2 }
  }

  /** Muestra `cur` moviendo y escalando lo ya dibujado con `shown` (transformación de la GPU). */
  private preview(): void {
    const st = this.stage(), a = this.shown, b = this.cur, r = this.rect
    if (!st || !a || !b || !r || !this.moving) return
    const fa = this.fit(a, r), fb = this.fit(b, r), s = fa.k / fb.k
    const tx = fa.ox * (1 - s) + (a[0] - b[0]) / fb.k, ty = fa.oy * (1 - s) + (a[1] - b[1]) / fb.k
    st.style.transform = `translate(${tx.toFixed(2)}px, ${ty.toFixed(2)}px) scale(${s.toFixed(5)})`
  }

  /** Fija `cur` en el `viewBox` de todas las capas y quita la transformación (dibujo nítido). */
  private commit(): void {
    cancelAnimationFrame(this.raf); this.raf = 0
    clearTimeout(this.idle)
    const b = this.cur, bs = this.base; if (!b || !bs) return
    const vb = b.map((n) => n.toFixed(1)).join(' ')
    this.host.querySelectorAll<SVGSVGElement>('svg.iso-svg').forEach((s) => s.setAttribute('viewBox', vb))
    const st = this.stage()
    if (st) { st.style.transform = ''; st.style.willChange = '' }
    this.shown = [...b]
    this.moving = false
    this.rect = null
    const cx = b[0] + b[2] / 2, cy = b[1] + b[3] / 2
    this.host.classList.toggle('iso-zoomed', Math.abs(b[2] - bs[2]) > 1 || Math.abs(cx - bs[0] - bs[2] / 2) > 1 || Math.abs(cy - bs[1] - bs[3] / 2) > 1)
  }

  /** Punto del dibujo bajo el puntero (en unidades del encuadre `b`, el que se ve ahora). */
  private at(e: MouseEvent, b: Box): [number, number] {
    const r = this.rect ?? this.stage()!.getBoundingClientRect(), { k, ox, oy } = this.fit(b, r)
    return [b[0] + (e.clientX - r.left - ox) * k, b[1] + (e.clientY - r.top - oy) * k]
  }

  private onWheel(e: WheelEvent): void {
    const b = this.cur; if (!b || !this.svg() || !(e.target as Element).closest('svg.iso-svg')) return
    e.preventDefault()
    this.begin()
    const f = Math.exp(Math.max(-1, Math.min(1, e.deltaY / (e.deltaMode === 1 ? 3 : 100))) * 0.18), [px, py] = this.at(e, b)
    this.request([px - (px - b[0]) * f, py - (py - b[1]) * f, b[2] * f, b[3] * f])
    clearTimeout(this.idle)
    if (!this.drag?.moved) this.idle = window.setTimeout(() => this.commit(), WHEEL_IDLE_MS)
  }

  private onDown(e: PointerEvent): void {
    if (e.button !== 0 || !this.cur || !(e.target as Element).closest('svg.iso-svg')) return
    this.drag = { x: e.clientX, y: e.clientY, box: [...this.cur], id: e.pointerId, moved: false }
  }

  private onMove(e: PointerEvent): void {
    const d = this.drag; if (!d || e.pointerId !== d.id) return
    const dx = e.clientX - d.x, dy = e.clientY - d.y
    if (!d.moved) {
      if (Math.hypot(dx, dy) < DRAG_PX) return
      d.moved = true; this.host.classList.add('iso-grabbing')
      d.box = [...this.cur!]                   // por si la rueda cambió el encuadre antes de arrastrar
      try { this.host.setPointerCapture(e.pointerId) } catch { /* sin captura: sigue funcionando dentro del mapa */ }
    }
    this.begin()
    const r = this.rect; if (!r) return
    const k = this.fit(d.box, r).k
    this.request([d.box[0] - dx * k, d.box[1] - dy * k, d.box[2], d.box[3]])
  }

  private onUp(e: PointerEvent): void {
    const d = this.drag; if (!d || e.pointerId !== d.id) return
    this.drag = null; this.host.classList.remove('iso-grabbing')
    if (d.moved) {
      this.commit()
      this.swallow = true; setTimeout(() => { this.swallow = false }, 0)
    }
  }
}
