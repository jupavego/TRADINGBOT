/**
 * Papel de cada agente en la síntesis (T44) y filtros por tipo del río de decisión.
 * El papel y el peso vienen de la API (`/v2/agents`: `role`, `weight`; la síntesis trae el peso
 * efectivo con la penalización por correlación). Solo los «direccionales» con peso > 0 votan.
 */
import { esc } from './panels'
import type { AgentInfo, AgentRole, Synthesis } from './types'

export type Filter = 'todos' | AgentRole

// Respaldo si la API aún no envía el papel (mismo criterio que `eim/synthesis/params.py`).
const FALLBACK: Record<string, AgentRole> = { calendar: 'riesgo', regime: 'riesgo', arbitrage: 'carril', plan: 'derivado' }

export const FILTERS: [Filter, string, string][] = [
  ['todos', 'Todos', 'Todos los agentes'],
  ['direccional', 'Dirección', 'Votan en la síntesis: su sesgo suma a la proyección (peso × confianza)'],
  ['riesgo', 'Riesgo', 'No votan: el calendario reduce confianza y tamaño en ventana de evento; el régimen modula pesos'],
  ['derivado', 'Derivados', 'No votan: el plan deriva de estructura y niveles (evita el doble conteo)'],
  ['carril', 'Carril propio', 'Arbitraje: rendimiento propio, no suma a la dirección del precio'],
]

const KEY = 'eim.river.filter'

export function loadFilter(): Filter {
  try {
    const v = localStorage.getItem(KEY)
    if (v && FILTERS.some(([f]) => f === v)) return v as Filter
  } catch { /* almacenamiento no disponible */ }
  return 'todos'
}

export function saveFilter(f: Filter): void {
  try { localStorage.setItem(KEY, f) } catch { /* almacenamiento no disponible */ }
}

export function roleOf(id: string, infos: AgentInfo[]): AgentRole {
  return infos.find((i) => i.id === id)?.role ?? FALLBACK[id] ?? 'direccional'
}

/** Peso base efectivo (síntesis) o el de la API; null si su papel no vota. */
export function weightOf(id: string, infos: AgentInfo[], syn: Synthesis | null): number | null {
  if (roleOf(id, infos) !== 'direccional') return null
  const w = syn?.weights?.[id]
  if (w !== undefined) return w
  const i = infos.find((x) => x.id === id)
  return i?.weight ?? 1
}

export const votes = (id: string, infos: AgentInfo[], syn: Synthesis | null): boolean =>
  (weightOf(id, infos, syn) ?? 0) > 0

/** Etiqueta corta bajo el nodo: por qué no vota o con qué peso lo hace. */
export function roleTag(id: string, infos: AgentInfo[], syn: Synthesis | null): string {
  const role = roleOf(id, infos)
  if (role === 'riesgo') return id === 'calendar' ? 'riesgo · modula confianza y tamaño' : 'riesgo · no vota'
  if (role === 'derivado') return 'derivado · no vota'
  if (role === 'carril') return 'carril propio'
  const w = weightOf(id, infos, syn) ?? 1
  if (w <= 0) return 'peso 0 · sin aporte medido'
  return w < 0.999 ? `peso ${w.toFixed(2)}` : ''
}

export const matches = (f: Filter, id: string, infos: AgentInfo[]): boolean => f === 'todos' || roleOf(id, infos) === f

/** Botonera de filtros con el número de agentes de cada tipo. */
export function filterBar(f: Filter, ids: string[], infos: AgentInfo[]): string {
  const n = (x: Filter): number => (x === 'todos' ? ids.length : ids.filter((id) => roleOf(id, infos) === x).length)
  return '<span class="rfilt" role="group" aria-label="Filtrar agentes por tipo">' +
    FILTERS.map(([k, label, why]) => `<button type="button" data-filter="${k}" aria-pressed="${k === f}" title="${esc(why)}">` +
      `${esc(label)} <i>${n(k)}</i></button>`).join('') + '</span>'
}
