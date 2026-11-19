/** Pestaña «Mapa del sistema» de la barra superior (junto al modo). Con ella abierta, la mesa (río de
 * decisión, bróker simulado y pestañas inferiores) se oculta y el mapa ocupa la pantalla; al volver,
 * el mapa se oculta. Lo oculto deja de sondear y de animar solo (IntersectionObserver de `ObsView` y
 * de `motion`), así que nunca corren los dos a la vez: menos lag. El mapa no cambia en nada. */

const KEY = 'eim.view'            // la última vista elegida se recuerda entre visitas
const DESK = ['river', 'paper']   // secciones de la mesa, además de `.desk`

let btn: HTMLButtonElement | null = null

function setView(map: boolean): void {
  const obs = document.getElementById('obs')
  if (!obs || !btn) return
  obs.hidden = !map
  DESK.forEach((id) => { const el = document.getElementById(id); if (el) el.hidden = map })
  document.querySelectorAll<HTMLElement>('.desk').forEach((el) => { el.hidden = map })
  btn.setAttribute('aria-pressed', String(map))
  btn.textContent = map ? '← Volver a la mesa' : '🗺 Mapa del sistema'
  try { localStorage.setItem(KEY, map ? 'map' : 'desk') } catch { /* sin almacenamiento: solo esta visita */ }
  window.scrollTo({ top: 0 })
}

/** Vuelve a la mesa (p. ej. al pedir «ver la validación en el bróker simulado»). */
export function showDesk(): void { setView(false) }

export function setupViewTabs(): void {
  btn = document.getElementById('view-map') as HTMLButtonElement | null
  if (!btn) return
  btn.onclick = () => setView(btn!.getAttribute('aria-pressed') !== 'true')
  let saved = 'desk'
  try { saved = localStorage.getItem(KEY) ?? 'desk' } catch { /* mesa por defecto */ }
  setView(saved === 'map')
}
