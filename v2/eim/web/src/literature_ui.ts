/** «Lo que dice la literatura» (T53): apoyos y contradicciones citadas por escenario. */
import { fetchCard, type LibraryCard } from './api'
import { esc } from './panels'
import type { AgentReport, ScenarioId } from './types'

interface Support { supports: string[]; contradicts: string[]; net: number; rules_evaluated: number; label: string }
interface Hit { card_id: string; cite: string; label: string; direction: number }

const cache = new Map<string, LibraryCard | null>()

/** Pide las fichas que aún no se conocen; `done` se llama al llegar alguna. */
export function loadCards(ids: string[], done: () => void): void {
  for (const id of ids) {
    if (cache.has(id)) continue
    cache.set(id, null)
    fetchCard(id).then((c) => { cache.set(id, c); done() }).catch(() => { /* queda el id */ })
  }
}

function line(id: string, hits: Hit[], mark: string): string {
  const h = hits.find((x) => x.card_id === id)
  const c = cache.get(id)
  const cite = h?.cite ?? (c ? `${c.citations[0]?.author} (${c.citations[0]?.year})` : '')
  return `<li data-card="${esc(id)}">${mark} ${esc(c?.title ?? h?.label ?? id)} <span class="muted">— ${esc(cite)}</span></li>`
}

export function literatureSection(sid: ScenarioId, r: AgentReport | undefined, done: () => void): string {
  const tag = 'Apoyo bibliográfico · no es una señal validada'
  const ss = (r?.metrics?.scenario_support as Record<string, Support> | undefined)?.[sid]
  if (!r || r.status === 'no_data' || !ss) {
    return `<div class="lit"><h5>Lo que dice la literatura</h5><p class="meta">Sin datos de reglas todavía.</p><p class="meta lit-tag">${tag}</p></div>`
  }
  const hits = (r.metrics.hits as Hit[]) ?? []
  loadCards([...ss.supports, ...ss.contradicts], done)
  const items = [...ss.supports.map((i) => line(i, hits, '✔')), ...ss.contradicts.map((i) => line(i, hits, '✖'))]
  return `<div class="lit"><h5>Lo que dice la literatura</h5>` +
    (items.length ? `<ul class="lit-list">${items.join('')}</ul>` : '<p class="meta">Ninguna regla activa ahora a favor ni en contra.</p>') +
    `<p class="meta">neto ${ss.net >= 0 ? '+' : ''}${ss.net.toFixed(2)} · ${ss.rules_evaluated} reglas evaluadas</p>` +
    `<p class="meta lit-tag">${tag}</p></div>`
}
