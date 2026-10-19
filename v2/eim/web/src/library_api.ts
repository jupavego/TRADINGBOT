// T55: biblioteca (catálogo y consulta; la consulta solo informa)
import { base, type LibraryCard } from './api'

export interface LibBook {
  id: string; title: string; author: string; year: number | null; pages: number | null
  pages_with_text: number; index_status: string; cards_by_status: Record<string, number>
}
export interface LibCatalog {
  books: LibBook[]; cards_total: number; cards_by_status: Record<string, number>
  llm_enabled: boolean; label: string
}
export interface LibPoint { texto: string; fuente: string; tipo: 'ficha' | 'pasaje' }
export interface LibAnswer {
  status: 'ok' | 'degraded' | 'no_data'; reason: string | null; resumen: string
  puntos: LibPoint[]; relacion_con_escenarios: string; advertencias: string[]
  sources: Record<string, LibraryCard>; label: string
}

export async function fetchLibCatalog(): Promise<LibCatalog> {
  const r = await fetch(`${base()}/v2/library/catalog`)
  if (!r.ok) throw new Error(r.statusText)
  return (await r.json()) as LibCatalog
}

export async function askLibrary(question: string, scenario: string | null, state: string): Promise<LibAnswer> {
  const r = await fetch(`${base()}/v2/library/ask`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'X-EIM-Confirm': 'library-ask' },
    body: JSON.stringify({ question, scenario, state }),
  })
  if (!r.ok) throw new Error(r.statusText)
  return (await r.json()) as LibAnswer
}
