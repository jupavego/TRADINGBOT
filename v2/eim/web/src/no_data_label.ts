/** Etiqueta honesta de cada esfera sin datos o degradada, leída del motivo que ya devuelve el
 *  agente (nunca un verde ni un 0 inventado). T120: ninguna esfera dice «sin datos» a secas; si el
 *  motivo no tiene etiqueta propia se muestra su primera frase. El estado de un recolector
 *  (apagado, sin datos recientes, disco bajo, unidad ausente) no se deduce aquí: llega de
 *  `GET /v2/micro/status`, la misma tabla que usan el vigilante y el RUNBOOK
 *  (`eim/data/collectors/health.py::LABELS`). */

type Rule = [RegExp, (m: RegExpExecArray) => string]

const NO_DATA: Rule[] = [
  [/\((\d+)\/(\d+) velas/, (m) => `acumulando ${m[1]}/${m[2]}`],
  [/colector no corre|sin recolecci[oó]n/i, () => 'recolector apagado'],
  [/velas recientes/i, () => 'sin datos recientes'],
  [/sin motor de contexto/i, () => 'sin motor de contexto'],
  [/motor de contexto calculando/i, () => 'motor calculando'],
  [/motor de contexto ca[ií]do/i, () => 'motor de contexto caído'],
  [/titulares insuficientes \((\d+)\/(\d+)\)/, (m) => `titulares ${m[1]}/${m[2]}`],
  [/ning[uú]n l[ií]der aprobado/i, () => 'sin líderes aprobados'],
  [/cierres mensuales insuficientes: (\d+) < (\d+)/, (m) => `historia corta (${m[1]}/${m[2]} meses)`],
  [/open interest ausente/i, () => 'sin open interest'],
]

/** Primera frase de un motivo, corta: «sin datos» solo si el agente no dio ninguno. */
function firstReason(warnings: string[]): string {
  const w = warnings.find((x) => x.trim())
  if (!w) return 'sin datos'
  const head = w.split(/[:;(]/)[0].trim()
  return head.length > 38 ? `${head.slice(0, 37)}…` : head
}

export function noDataLabel(warnings: string[] = []): string {
  const w = warnings.join(' ')
  for (const [re, f] of NO_DATA) {
    const m = re.exec(w)
    if (m) return f(m)
  }
  return firstReason(warnings)
}

/** Agente con datos pero degradado (p. ej. huecos de secuencia en la recolección). */
export function degradedLabel(status?: string, warnings: string[] = []): string {
  if (status !== 'degraded') return ''
  const w = warnings.join(' ')
  if (/huecos/i.test(w)) return 'degradado por huecos'
  if (/sin catalizadores/i.test(w)) return 'sin catalizadores con fuente'
  return 'degradado'
}

/** Estado del recolector de cada agente que depende de uno (T120), tal como lo da la API. */
export type CollectorState = { state: string; label: string; reason: string; age_s: number | null }
const collectors = new Map<string, CollectorState>()

export function setCollectorState(agentId: string, st: CollectorState | null): void {
  if (st) collectors.set(agentId, st)
  else collectors.delete(agentId)
}

/** Etiqueta del recolector si NO está capturando (manda sobre lo que diga el agente); '' si sí. */
export function collectorLabel(agentId: string): string {
  const st = collectors.get(agentId)
  return st && st.state !== 'capturando' ? st.label : ''
}
