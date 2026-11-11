// T151–T158: biblioteca digital (solo lectura; complemento, no señal)
import { base } from './api'

export interface DigOverview {
  digital_total: number; digital_verified: number; pending_verification: number
  full_text: number; partial: number; by_access: Record<string, number>
  by_category: Record<string, { name: string; n: number }>
  cards: number; read: Record<string, number>; stances: number; stances_verified: number
  methods_identified: number; top_methods: [string, number][]
  local_books: number; local_cards: number; total_references: number
  recent_research: { at: string; n: number; full: boolean; coverage: Record<string, number>; stances_verified: number }[]
  recent_traces: DigTrace[]; contradictions: number; concepts: number; mode: string; label: string
}
export interface DigRefBrief {
  id: string; title: string; authors: string[]; year: number | null; category: string
  category_name: string; access: string; availability: string; reliability: string
  url: string | null; oa_url: string | null; concept_names: string[]
  related_strategies: string[]; read: string
}
export interface DigStance { concept: string; kind: string; level: string; summary: string; conditions: string }
export interface DigFragment { text: string; where: string }
export interface DigRef extends DigRefBrief {
  venue: string | null; publisher: string | null; doc_type: string | null; description: string
  methods: string[]; application: string; markets: string[]; verified_at: string | null
  stances: DigStance[]; problem: string | null
  card: { coverage: string; findings: DigFragment[]; limitations: DigFragment[]; level: string
          stances_verified: string[]; stances_pending: string[]; operational_rules: string[] } | null
}
export interface DigSummary { n: number; mean_r: number | null; win_rate: number | null; ci_low: number | null; ci_high: number | null; enough: boolean }
export interface DigTrace {
  ledger_id: string; operacion: { profile: string; side: number; timeframe: string }
  estrategia: { strategy: string }; literatura: { stance: number; sources: string[]; entry_verdicts: Record<string, string> }
  resultado: { r: number | null; won: boolean | null }; conclusion: string
}
export interface DigLearning {
  n_traces: number; min_n: number; backed: DigSummary; neutral: DigSummary; contradicted: DigSummary
  verdict: string; traces: DigTrace[]
  concepts: { concept: string; by_verdict: Record<string, DigSummary>; useful: string }[]
}
export interface DigConsensus { concept: string; name: string; verdict: string; net: number; explanation: string[] }

async function get<T>(path: string, params: Record<string, string> = {}): Promise<T> {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '')).toString()
  const r = await fetch(`${base()}/v2/library/digital${path}${q ? `?${q}` : ''}`)
  if (!r.ok) throw new Error(r.statusText)
  return (await r.json()) as T
}

export const fetchDigOverview = () => get<DigOverview>('/overview')
export const fetchDigRefs = (p: Record<string, string>) => get<{ refs: DigRefBrief[]; n: number }>('/refs', p)
export const fetchDigRef = (id: string) => get<DigRef>(`/refs/${encodeURIComponent(id)}`)
export const fetchDigLearning = () => get<DigLearning>('/learning', { traces: '8' })
export const fetchDigContradictions = () => get<{ concepts: DigConsensus[] }>('/contradictions')
