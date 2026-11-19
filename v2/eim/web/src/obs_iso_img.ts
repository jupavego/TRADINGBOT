/** Objetos del mapa isométrico como imágenes (rendimiento). Cada <use> de un <symbol> hacía que el
 * navegador clonara por dentro todas sus figuras: con ~250 objetos en el mapa eran ~42.000 figuras
 * ocultas que se volvían a recorrer al pintar, al rasterizar y al pasar el puntero (prueba de impacto).
 * Aquí cada símbolo se convierte una sola vez en un SVG independiente (URL `blob:`) y se coloca con
 * <image>: el navegador lo rasteriza una vez por tamaño y lo reutiliza, y para el puntero es un solo
 * rectángulo. El dibujo es el mismo vector (sigue nítido con zoom). Sin documento (pruebas en Node) o si
 * algo falla, se vuelve a <use> y el aspecto no cambia. */

const NS = 'http://www.w3.org/2000/svg'
const PAD = 0.1                     // margen alrededor del viewBox: lo que asoma del símbolo no se recorta
const urls = new Map<string, string>()
let built = false

/** Convierte cada <symbol> de `defs` (texto SVG) en una imagen independiente; se llama una sola vez. */
export function buildArtImages(defs: string): void {
  if (built || typeof document === 'undefined' || typeof URL?.createObjectURL !== 'function') return
  built = true
  try {
    const doc = new DOMParser().parseFromString(`<svg xmlns="${NS}"><defs>${defs}</defs></svg>`, 'image/svg+xml')
    if (doc.querySelector('parsererror')) return
    const byId = new Map<string, Element>()
    doc.querySelectorAll('[id]').forEach((e) => byId.set(e.id, e))
    doc.querySelectorAll('symbol[id]').forEach((s) => {
      const vb = (s.getAttribute('viewBox') ?? '').split(/[\s,]+/).map(Number)
      if (vb.length !== 4 || vb.some((n) => !Number.isFinite(n))) return
      const [x, y, w, h] = vb, body = s.innerHTML
      // degradados u otras definiciones que el símbolo usa pero viven fuera de él
      const extra = [...new Set([...body.matchAll(/url\(#([^)]+)\)/g)].map((m) => m[1]))]
        .map((id) => byId.get(id)).filter((e): e is Element => !!e && !s.contains(e)).map((e) => e.outerHTML).join('')
      const svg = `<svg xmlns="${NS}" viewBox="${x - w * PAD} ${y - h * PAD} ${w * (1 + 2 * PAD)} ${h * (1 + 2 * PAD)}">`
        + `${extra ? `<defs>${extra}</defs>` : ''}${body}</svg>`
      urls.set(s.id, URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' })))
    })
  } catch { urls.clear() }
}

/** `true` si los objetos ya se colocan como imágenes (no hace falta poner los <symbol> en la página). */
export const artAsImages = (): boolean => urls.size > 0

/** Coloca el símbolo `id` en la caja (x, y, w, h) del mismo modo que `<use href="#id" …>`. */
export function artTag(id: string, x: number, y: number, w: number, h: number, extra = ''): string {
  const f = (n: number): string => n.toFixed(1), u = urls.get(id)
  if (!u) return `<use href="#${id}" x="${f(x)}" y="${f(y)}" width="${f(w)}" height="${f(h)}"${extra}/>`
  return `<image class="iso-art" href="${u}" x="${f(x - w * PAD)}" y="${f(y - h * PAD)}" width="${f(w * (1 + 2 * PAD))}" height="${f(h * (1 + 2 * PAD))}"${extra}/>`
}
