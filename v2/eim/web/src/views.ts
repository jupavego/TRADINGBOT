/** Pestañas de la barra superior (junto al modo): «Cantera» y «Mapa del sistema». Con una abierta,
 * la mesa (río de decisión, bróker simulado y pestañas inferiores) se oculta y esa vista ocupa la
 * pantalla; al volver a pulsarla se regresa a la mesa. Lo oculto deja de sondear y de animar solo
 * (IntersectionObserver de `ObsView` y de `motion`; la cantera solo se refresca a la vista), así
 * que nunca corren dos a la vez: menos lag. Cada vista elegida avisa con `eim:view`. */

const KEY = 'eim.view'            // la última vista elegida se recuerda entre visitas
const DESK = ['river', 'paper']   // secciones de la mesa, además de `.desk`

type View = 'desk' | 'map' | 'cantera'
/** Vista → [botón, sección, texto del botón cerrado]. */
const TABS: Record<Exclude<View, 'desk'>, [string, string, string]> = {
  cantera: ['view-cantera', 'cantera', '🌱 Cantera'],
  map: ['view-map', 'obs', '🗺 Mapa del sistema'],
}

let current: View = 'desk'

function setView(view: View): void {
  current = view
  for (const [v, [btnId, secId, label]] of Object.entries(TABS)) {
    const on = v === view
    const sec = document.getElementById(secId)
    const btn = document.getElementById(btnId)
    if (sec) sec.hidden = !on
    if (btn) {
      btn.setAttribute('aria-pressed', String(on))
      btn.textContent = on ? '← Volver a la mesa' : label
    }
  }
  const desk = view === 'desk'
  DESK.forEach((id) => { const el = document.getElementById(id); if (el) el.hidden = !desk })
  document.querySelectorAll<HTMLElement>('.desk').forEach((el) => { el.hidden = !desk })
  try { localStorage.setItem(KEY, view) } catch { /* sin almacenamiento: solo esta visita */ }
  window.scrollTo({ top: 0 })
  window.dispatchEvent(new CustomEvent<View>('eim:view', { detail: view }))
}

/** Vuelve a la mesa (p. ej. al pedir «ver la validación en el bróker simulado»). */
export function showDesk(): void { setView('desk') }

export function setupViewTabs(): void {
  for (const [v, [btnId]] of Object.entries(TABS) as [View, [string, string, string]][]) {
    const btn = document.getElementById(btnId)
    if (btn) btn.onclick = () => setView(current === v ? 'desk' : v)
  }
  let saved = 'desk'
  try { saved = localStorage.getItem(KEY) ?? 'desk' } catch { /* mesa por defecto */ }
  setView(saved === 'map' || saved === 'cantera' ? saved : 'desk')
}
