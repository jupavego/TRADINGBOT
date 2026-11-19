/** Zoom y desplazamiento del mapa isométrico: la rueda del mouse acerca o aleja hacia el puntero y el
 * clic sostenido arrastra el mapa en cualquier dirección (también con zoom). Se hace cambiando el
 * `viewBox` del SVG, así que el dibujo sigue nítido. El encuadre se conserva entre los repintados del
 * sondeo; al cambiar de vista (mapa completo ↔ sala ampliada) vuelve al encuadre de esa vista.
 * Un arrastre no cuenta como clic: soltar tras mover no abre salas ni puestos. */
type Box = [number, number, number, number]

const DRAG_PX = 5           // a partir de aquí el gesto es arrastre, no clic
const ZMIN = 1 / 8          // acercamiento máximo: 8×
const ZMAX = 1.25           // alejamiento máximo: un poco más que el encuadre completo

export class IsoPan {
  private scope = ''
  private base: Box | null = null
  private cur: Box | null = null
  private drag: { x: number; y: number; box: Box; id: number; moved: boolean } | null = null
  private swallow = false

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

  /** Tras redibujar: guarda el encuadre original y, si seguimos en la misma vista, repone el zoom. */
  apply(scope: string): void {
    const svg = this.svg(); if (!svg) return
    const vb = (svg.getAttribute('viewBox') ?? '').split(/\s+/).map(Number)
    if (vb.length !== 4 || vb.some((n) => !Number.isFinite(n))) return
    const same = scope === this.scope && this.cur
    this.scope = scope; this.base = vb as Box
    if (!same) this.cur = [...this.base]
    this.set(this.cur!)
  }

  reset(): void { if (this.base) { this.cur = [...this.base]; this.set(this.cur) } }

  private set(b: Box): void {
    const svg = this.svg(), bs = this.base; if (!svg || !bs) return
    const w = Math.min(Math.max(b[2], bs[2] * ZMIN), bs[2] * ZMAX), h = w * (bs[3] / bs[2])
    const cx = Math.min(Math.max(b[0] + b[2] / 2, bs[0]), bs[0] + bs[2])   // el centro no sale del mapa
    const cy = Math.min(Math.max(b[1] + b[3] / 2, bs[1]), bs[1] + bs[3])
    this.cur = [cx - w / 2, cy - h / 2, w, h]
    svg.setAttribute('viewBox', this.cur.map((n) => n.toFixed(1)).join(' '))
    this.host.classList.toggle('iso-zoomed', Math.abs(w - bs[2]) > 1 || Math.abs(cx - bs[0] - bs[2] / 2) > 1 || Math.abs(cy - bs[1] - bs[3] / 2) > 1)
  }

  /** Punto del dibujo bajo el puntero (en unidades del viewBox). */
  private at(e: MouseEvent, b: Box): [number, number] {
    const r = this.svg()!.getBoundingClientRect(), k = Math.max(b[2] / r.width, b[3] / r.height)
    const ox = (r.width - b[2] / k) / 2, oy = (r.height - b[3] / k) / 2      // bandas de «meet»
    return [b[0] + (e.clientX - r.left - ox) * k, b[1] + (e.clientY - r.top - oy) * k]
  }

  private onWheel(e: WheelEvent): void {
    const b = this.cur; if (!b || !this.svg() || !(e.target as Element).closest('svg.iso-svg')) return
    e.preventDefault()
    const f = Math.exp(Math.max(-1, Math.min(1, e.deltaY / (e.deltaMode === 1 ? 3 : 100))) * 0.18), [px, py] = this.at(e, b)
    this.set([px - (px - b[0]) * f, py - (py - b[1]) * f, b[2] * f, b[3] * f])
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
      try { this.host.setPointerCapture(e.pointerId) } catch { /* sin captura: sigue funcionando dentro del mapa */ }
    }
    const r = this.svg()!.getBoundingClientRect(), k = Math.max(d.box[2] / r.width, d.box[3] / r.height)
    this.set([d.box[0] - dx * k, d.box[1] - dy * k, d.box[2], d.box[3]])
  }

  private onUp(e: PointerEvent): void {
    const d = this.drag; if (!d || e.pointerId !== d.id) return
    this.drag = null; this.host.classList.remove('iso-grabbing')
    if (d.moved) { this.swallow = true; setTimeout(() => { this.swallow = false }, 0) }
  }
}
