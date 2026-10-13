import type { AgentReport, Synthesis } from './types'

const CONFLICT = 0.2 // |sesgo| mínimo para considerar que un agente "toma partido"

/**
 * Síntesis SIMULADA en el navegador (hasta T20): sesgo ponderado por confianza,
 * solo con agentes en estado ok/degradado. No es la síntesis real del sistema.
 */
export function simulateSynthesis(reports: AgentReport[]): Synthesis | null {
  const used = reports.filter((r) => r.status !== 'no_data')
  const w = used.map((r) => r.confidence * (r.status === 'degraded' ? 0.5 : 1))
  const total = w.reduce((a, b) => a + b, 0)
  if (!used.length || total <= 0) return null
  const bias = used.reduce((s, r, i) => s + w[i] * r.bias, 0) / total
  const variance = used.reduce((s, r, i) => s + w[i] * (r.bias - bias) ** 2, 0) / total
  const contributions: Record<string, number> = {}
  used.forEach((r, i) => { contributions[r.agent_id] = (w[i] * r.bias) / total })
  const confidence = used.reduce((s, r) => s + r.confidence, 0) / used.length
  const agreement = Math.max(0, 1 - Math.sqrt(variance))
  const dir = bias > 0.1 ? 'alcista' : bias < -0.1 ? 'bajista' : 'neutral'
  return {
    bias, confidence, agreement, contributions, simulated: true,
    thesis: `Sesgo combinado ${dir} (${bias.toFixed(2)}) con ${used.length} agentes.`,
  }
}

/** Hay desacuerdo si agentes con convicción apuntan en direcciones opuestas. */
export function disagreeing(reports: AgentReport[]): { up: string[]; down: string[] } | null {
  const act = reports.filter((r) => r.status !== 'no_data')
  const up = act.filter((r) => r.bias >= CONFLICT).map((r) => r.agent_id)
  const down = act.filter((r) => r.bias <= -CONFLICT).map((r) => r.agent_id)
  return up.length && down.length ? { up, down } : null
}
