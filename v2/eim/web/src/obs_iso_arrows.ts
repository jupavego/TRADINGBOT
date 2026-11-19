/** Flechas que viajan por las líneas del mapa isométrico (antes `<animateMotion>` de SMIL). SMIL
 * volvía a resolver toda la línea de tiempo del SVG en cada cuadro y era, por sí solo, la mayor parte
 * del lag del mapa en reposo. Aquí cada línea se muestrea una vez (puntos a lo largo del trazo) y en
 * cada cuadro del reloj compartido (`motion`) se reescribe la forma (`d`) de cada flecha ya girada y
 * en su sitio: misma velocidad, mismo desfase entre las flechas de una línea y orientadas según el
 * trazo. Cambiar la forma solo repinta; cambiar su `transform` obligaba a Chrome a recalcular las capas
 * de toda la página (miles de figuras del mapa) en cada cuadro. */

const SAMPLES = 160              // puntos por línea: de sobra para un movimiento continuo

interface Arrow { el: SVGElement; pts: Float32Array; dur: number; off: number; k: number }

/** Punta de flecha (apunta a +x), en unidades de `k`: igual que la de antes. */
const SHAPE: [number, number][] = [[-7, -5], [5, 0], [-7, 5], [-3.5, 0]]

export class IsoArrows {
  private t = 0                  // segundos de recorrido (solo avanza cuando el reloj avanza)
  private arrows: Arrow[] | null = null
  private svg: Element | null = null

  /** Muestrea las líneas de `svg` (la capa `.iso-fx`) y coloca cada flecha en su punto de partida. */
  private collect(svg: Element): void {
    this.svg = svg
    const cache = new Map<string, Float32Array>()
    this.arrows = [...svg.querySelectorAll<SVGElement>('.iso-dotm[data-path]')].flatMap((el) => {
      const id = el.dataset.path ?? ''
      let pts = cache.get(id)
      if (!pts) {
        const path = svg.querySelector<SVGPathElement>(`path[id="${CSS.escape(id)}"]`)
        if (!path) return []
        const len = path.getTotalLength()
        pts = new Float32Array(SAMPLES * 2)
        for (let i = 0; i < SAMPLES; i++) {
          const p = path.getPointAtLength((len * i) / (SAMPLES - 1))
          pts[2 * i] = p.x; pts[2 * i + 1] = p.y
        }
        cache.set(id, pts)
      }
      return [{ el, pts, dur: Number(el.dataset.dur) || 4, off: Number(el.dataset.off) || 0, k: Number(el.dataset.k) || 1 }]
    })
  }

  /** Avanza `dtMs` y recoloca las flechas de `svg` (vuelve a muestrear si el mapa se redibujó). */
  step(svg: Element, dtMs: number): void {
    if (svg !== this.svg || !this.arrows) this.collect(svg)
    this.t += dtMs / 1000
    for (const a of this.arrows!) {
      const f = (((this.t / a.dur + a.off) % 1) + 1) % 1, x = f * (SAMPLES - 1)
      const i = Math.min(SAMPLES - 2, Math.floor(x)), w = x - i, p = a.pts
      const x0 = p[2 * i], y0 = p[2 * i + 1], x1 = p[2 * i + 2], y1 = p[2 * i + 3]
      const ang = Math.atan2(y1 - y0, x1 - x0), c = Math.cos(ang) * a.k, s = Math.sin(ang) * a.k
      const cx = x0 + (x1 - x0) * w, cy = y0 + (y1 - y0) * w
      a.el.setAttribute('d', 'M' + SHAPE.map(([u, v]) => `${(cx + u * c - v * s).toFixed(1)},${(cy + u * s + v * c).toFixed(1)}`).join(' L') + ' Z')
    }
  }
}
