import type { AgentReport, Synthesis } from './types'

const CONFLICT = 0.2 // |sesgo| mínimo para considerar que un agente "toma partido"

/** Aviso común: los porcentajes reparten el peso de los agentes, no son probabilidades. */
export const PCT_NOTE = 'Proyección estimada: reparto de las contribuciones de la síntesis (confianza × sesgo de cada ' +
  'agente en este marco temporal) entre subida y bajada. No es una probabilidad calibrada: el sistema aún no supera ' +
  'la puerta de edge (T27).'

/** Hay desacuerdo si agentes con convicción apuntan en direcciones opuestas. Con `syn`, solo
 *  cuentan los que votan en la síntesis (los no direccionales o con peso 0 no contradicen). */
export function disagreeing(reports: AgentReport[], syn?: Synthesis | null): { up: string[]; down: string[] } | null {
  const act = reports.filter((r) => r.status !== 'no_data' && (!syn || r.agent_id in syn.contributions))
  const up = act.filter((r) => r.bias >= CONFLICT).map((r) => r.agent_id)
  const down = act.filter((r) => r.bias <= -CONFLICT).map((r) => r.agent_id)
  return up.length && down.length ? { up, down } : null
}

export type Share = { id: string; dir: 1 | -1 | 0; pct: number }

/**
 * Aporte de cada agente a la proyección, en % enteros que suman exactamente 100 (resto mayor).
 * `dir` = dirección de su contribución; los neutrales aportan 0 %. Null si nadie toma partido.
 */
export function shares(syn: Synthesis | null): Share[] | null {
  if (!syn) return null
  const items = Object.entries(syn.contributions)
  const tot = items.reduce((a, [, c]) => a + Math.abs(c), 0)
  if (tot < 1e-9) return null
  const raw = items.map(([id, c]) => ({ id, dir: (c > 0 ? 1 : c < 0 ? -1 : 0) as Share['dir'], x: (Math.abs(c) / tot) * 100 }))
  const out = raw.map((r) => ({ id: r.id, dir: r.dir, pct: Math.floor(r.x) }))
  let left = 100 - out.reduce((a, r) => a + r.pct, 0)
  for (const k of raw.map((r, i) => [r.dir ? r.x - Math.floor(r.x) : -1, i] as const).sort((a, b) => b[0] - a[0]).map(([, i]) => i)) {
    if (left-- <= 0) break
    out[k].pct += 1
  }
  return out.sort((a, b) => b.pct - a.pct)
}

/** Proyección estimada de subida / bajada (%): suma de los aportes de cada dirección. */
export function upDown(syn: Synthesis | null): { up: number; down: number } | null {
  const s = shares(syn)
  if (!s) return null
  const up = s.filter((r) => r.dir > 0).reduce((a, r) => a + r.pct, 0)
  return { up, down: 100 - up }
}
