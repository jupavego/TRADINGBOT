import type { Overlay } from './types'
import { LAYERS, type LayerId, type LayerEngine } from './layers'

const KEY = 'eim.layers'

function load(): Set<LayerId> {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) ?? 'null')
    if (Array.isArray(s)) return new Set(s as LayerId[])
  } catch { /* sin almacenamiento */ }
  return new Set(LAYERS.filter((l) => l.on).map((l) => l.id))
}

/** Fila de capas activables; el estado se recuerda en localStorage. */
export function mountLayerBar(el: HTMLElement, engine: LayerEngine): void {
  const on = load()
  engine.setEnabled(on)
  el.innerHTML = LAYERS.map((l) =>
    `<button data-l="${l.id}" aria-pressed="${on.has(l.id)}">${l.label}</button>`).join('')
  el.onclick = (e) => {
    const b = (e.target as HTMLElement).closest('button')
    if (!b) return
    const id = b.dataset.l as LayerId
    if (on.has(id)) on.delete(id); else on.add(id)
    b.setAttribute('aria-pressed', String(on.has(id)))
    try { localStorage.setItem(KEY, JSON.stringify([...on])) } catch { /* ignora */ }
    engine.setEnabled(on)
  }
}

const esc = (s: string): string => s.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`)

/** Tarjeta de evidencia: agente, confianza y "por qué existe". */
export function showCard(card: HTMLElement, o: Overlay | null, x: number, y: number, w: number): void {
  if (!o) { card.hidden = true; return }
  card.innerHTML = `<b>${esc(o.label)}</b><div class="muted">${esc(o.agent_id)} · confianza ` +
    `${(o.confidence * 100).toFixed(0)}%</div><ul>${o.evidence.map((e) => `<li>${esc(e)}</li>`).join('')}</ul>`
  card.hidden = false
  const cw = card.offsetWidth
  card.style.left = `${Math.max(4, Math.min(x + 14, w - cw - 4))}px`
  card.style.top = `${Math.max(4, y + 14)}px`
}
