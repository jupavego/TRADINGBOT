/** Leyenda siempre visible, glosario emergente y recorrido guiado de 5 pasos (T75). */
import { esc, STATE_ICON, STATE_LABEL, type ObsState } from './obs_types'

const HINT: Record<ObsState, string> = {
  ok: 'Emitió eventos a tiempo y sin fallos.', degradado: 'Funciona, pero con datos parciales.',
  error: 'Falló en su última ejecución.', obsoleto: 'Su última señal es más vieja de lo esperado.',
  pausado: 'Detenido a propósito.', sin_datos: 'Sin señales recientes: no se supone sano.',
  planeado: 'Previsto en el plan, aún sin código. No es una avería.',
}

export function legendHtml(): string {
  const st = (Object.keys(STATE_LABEL) as ObsState[]).map((s) =>
    `<li title="${esc(HINT[s])}"><i class="obs-sw st-${s}">${STATE_ICON[s]}</i>${STATE_LABEL[s]}</li>`).join('')
  return `<details class="obs-legend" open><summary>Cómo leer este mapa</summary>
    <ul class="obs-lg-states">${st}</ul>
    <p class="obs-lg-shapes"><b>Formas:</b> ◖▬◗ agente · ▭ servicio · ▭ con tapa: almacén · ⬡ puerta (riesgo)</p>
    <p><b>Flechas:</b> <span class="obs-lg-a solid"></span> declarada · <span class="obs-lg-a dev"></span> vista y no declarada ·
      <span class="obs-lg-a unseen"></span> declarada y nunca vista · <span class="obs-lg-a dash"></span> planeada (punteado)</p>
    <p class="muted">Pasa el cursor sobre cualquier palabra subrayada para ver qué significa.</p></details>`
}

/** Subraya, en los nodos de TEXTO de `el`, los términos del glosario (hover = definición). */
export function glossarize(el: HTMLElement, g: Record<string, string>): void {
  const terms = Object.keys(g).sort((x, y) => y.length - x.length)
  if (!terms.length) return
  const esc = (t: string): string => t.replace(/[.*+?^${}()|[\]\\/-]/g, '\\$&')
  const re = new RegExp(`(?<![\\wáéíóúñ])(${terms.map(esc).join('|')})(?![\\wáéíóúñ])`, 'i')
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  for (let n = walker.nextNode(); n; n = walker.nextNode()) nodes.push(n as Text)
  for (const t of nodes) {
    const m = re.exec(t.data)
    if (!m || t.parentElement?.closest('abbr,button,code')) continue
    const abbr = document.createElement('abbr')
    abbr.className = 'obs-gl'; abbr.textContent = m[1]
    abbr.title = g[Object.keys(g).find((k) => k.toLowerCase() === m[1].toLowerCase()) ?? ''] ?? ''
    const after = t.splitText(m.index)
    after.data = after.data.slice(m[1].length)
    t.parentNode!.insertBefore(abbr, after)
  }
}

export const TOUR: { sel: string; title: string; text: string }[] = [
  { sel: '.obs-route', title: '1 · La ruta', text: 'De izquierda a derecha, las 7 etapas por las que pasa cada vela: de los datos a la decisión y de ahí a la validación.' },
  { sel: '.obs-route .obs-node', title: '2 · El color y el icono', text: 'Cada bloque resume su estado: ✔ al día, ▲ degradado, ✖ error, ◷ dato viejo, ? sin datos. El color nunca va solo.' },
  { sel: '.obs-legend', title: '3 · La leyenda', text: 'Siempre a la vista: explica estados, formas y flechas. Lo punteado es lo planeado, no una avería.' },
  { sel: '.obs-detail', title: '4 · El detalle', text: 'Pulsa una etapa para ver sus piezas y una pieza para ver, en palabras simples, qué hizo por última vez.' },
  { sel: '.obs-replay-btn', title: '5 · Ver la última vela', text: 'Reproduce despacio lo que realmente pasó con la última vela. Sin actividad registrada, no inventa nada.' },
]
const KEY = 'eim.obs.tour.v1'
export const tourSeen = (): boolean => { try { return localStorage.getItem(KEY) === '1' } catch { return true } }
export const markTour = (): void => { try { localStorage.setItem(KEY, '1') } catch { /* sin almacenamiento */ } }

/** Muestra el paso `i` como globo fijo; devuelve el HTML del globo. */
export function tourHtml(i: number): string {
  const s = TOUR[i]
  return `<div class="obs-tour" role="dialog" aria-label="Recorrido guiado"><b>${esc(s.title)}</b><p>${esc(s.text)}</p>
    <div class="obs-tour-b"><button data-tour="skip">Saltar</button>${i > 0 ? '<button data-tour="prev">Atrás</button>' : ''}
    <button class="primary" data-tour="next">${i === TOUR.length - 1 ? 'Entendido' : 'Siguiente'}</button></div></div>`
}
