/** Tipos y etiquetas de la trazabilidad de una decisión (T76). Todo sale de `/v2/obs/*` (solo lectura). */
export type Mark = 'limpia' | 'con_datos_obsoletos' | 'con_agente_critico_degradado' | 'con_error'

export const MARK_ES: Record<Mark, string> = {
  limpia: 'Limpia', con_datos_obsoletos: 'Con datos obsoletos',
  con_agente_critico_degradado: 'Con agente crítico degradado', con_error: 'Con error',
}
/** Icono además del color: la marca nunca depende solo del color. */
export const MARK_ICON: Record<Mark, string> = { limpia: '✔', con_datos_obsoletos: '◷', con_agente_critico_degradado: '▲', con_error: '✖' }
export const MARK_HINT: Record<Mark, string> = {
  limpia: 'Ningún dato viejo, agente crítico degradado ni error en esta decisión.',
  con_datos_obsoletos: 'Un dato llegó más viejo de lo aceptable (o con cobertura baja).',
  con_agente_critico_degradado: 'Un agente del que depende el riesgo no estaba en estado ok.',
  con_error: 'Algún paso falló y quedó registrado como error.',
}
export const OUTCOME_ES: Record<string, string> = {
  ejecutada: 'Ejecutada', orden_enviada: 'Orden enviada', orden_pedida: 'Orden pedida', aprobado: 'Aprobada, sin orden',
  vetado: 'Vetada', plan: 'Propuesta', sin_plan: 'Sin plan', sintesis: 'Sin plan', senales: 'Solo señales', datos: 'Solo datos',
}
export const MODE_ES: Record<string, string> = { ANALISIS: 'Análisis', SIMULADO: 'Simulado', TESTNET: 'Testnet', REAL: 'Real' }

export interface TraceRow {
  trace_id: string; symbol: string | null; timeframe: string | null; mode: string
  first_ms: number; last_ms: number; outcome: string; has_error: boolean; evidence: Mark | null
}
export interface TraceRef { type: string; id: string; hash?: string | null; params_version?: string | null }
export interface Step {
  n: number; event_id: string; component_id: string; title_es: string; kind: string; status: string
  ts_utc: number; duration_ms: number | null; text_es: string; causal: boolean
  finding: { cause: string; why: string } | null
  consumed: { source: string | null; age_min: number | null; coverage: number | null; refs: TraceRef[] }
  produced: { bias?: number; confidence?: number; warnings: string[]; refs: TraceRef[]; params_version: string | null }
}
export interface RiskCheck { rule: string; ok: boolean; detail: string }
export interface Explain {
  trace_id: string; partial: boolean; mark: Mark; outcome: string; headline_es: string; reasons_es: string[]
  decision: { symbol: string | null; timeframe: string | null; mode: string; first_ms: number; last_ms: number } | null
  findings: { event_id: string; cause: string; why: string; component_id: string; contaminates: boolean }[]
  steps: Step[]
  facts: {
    signal: { bias: number | null; confidence: number | null; agreement: number | null; text_es: string }
    decision: { state: string; risk: { approved: boolean; size: number | null; config_version: string | null; source: string; checks: RiskCheck[]; reasons: string[] } | null }
    order: { state: string; status: string | null; ts_utc: number | null }
  }
  agents: { component_id: string; title_es: string; status: string; bias: number | null; confidence: number | null; vs_synthesis: number | null; opposes: boolean }[]
}
export interface Quality {
  n_decisions: number; n_dirty: number; dirty_share: number | null; n_without_events: number
  by_mark: Record<Mark, number>; marks_es: Record<Mark, string>; note_es: string
  by_period: { start_ms: number; n: number; dirty: number; dirty_share: number | null }[]
  by_component: { component_id: string; n: number; share: number | null }[]
  by_cause: { cause: string; n: number; share: number | null }[]
}
export const CAUSE_ES: Record<string, string> = {
  error: 'Error en un paso', agente_critico_degradado: 'Agente crítico degradado',
  dato_obsoleto: 'Dato obsoleto', cobertura_baja: 'Cobertura baja', veto: 'Veto del riesgo',
  sin_plan: 'Sin plan', sin_sintesis: 'Sin síntesis', orden_rechazada: 'Orden rechazada', agente_degradado: 'Agente degradado',
}
export const STEP_ICON: Record<string, string> = { ok: '✔', degraded: '▲', error: '✖', no_data: '?', rejected: '✋' }
export const STEP_LABEL: Record<string, string> = { ok: 'Bien', degraded: 'Degradado', error: 'Error', no_data: 'Sin datos', rejected: 'Vetado' }
export const pct = (x: number | null | undefined): string => (x == null ? '—' : `${(x * 100).toLocaleString('es-CO', { maximumFractionDigits: 1 })} %`)
