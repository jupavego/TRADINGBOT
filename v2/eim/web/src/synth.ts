import type { AgentReport } from './types'

const CONFLICT = 0.2 // |sesgo| mínimo para considerar que un agente "toma partido"

/** Hay desacuerdo si agentes con convicción apuntan en direcciones opuestas. */
export function disagreeing(reports: AgentReport[]): { up: string[]; down: string[] } | null {
  const act = reports.filter((r) => r.status !== 'no_data')
  const up = act.filter((r) => r.bias >= CONFLICT).map((r) => r.agent_id)
  const down = act.filter((r) => r.bias <= -CONFLICT).map((r) => r.agent_id)
  return up.length && down.length ? { up, down } : null
}
