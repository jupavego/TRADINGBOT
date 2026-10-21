/** Etiqueta honesta de la esfera de Microestructura (y de cualquier agente sin datos), leída del
 *  motivo que ya devuelve el agente: «recolector apagado» · «acumulando 7/24» · «sin datos recientes»
 *  · «degradado por huecos» (nunca un verde ni un 0 inventado). */
export function noDataLabel(warnings: string[] = []): string {
  const w = warnings.join(' ')
  const acc = /\((\d+)\/(\d+) velas/.exec(w)
  if (acc) return `acumulando ${acc[1]}/${acc[2]}`
  if (/colector no corre|sin recolecci[oó]n/i.test(w)) return 'recolector apagado'
  if (/velas recientes/i.test(w)) return 'sin datos recientes'
  return 'sin datos'
}

/** Agente con datos pero degradado (p. ej. huecos de secuencia en la recolección). */
export function degradedLabel(status?: string, warnings: string[] = []): string {
  if (status !== 'degraded') return ''
  return /huecos/i.test(warnings.join(' ')) ? 'degradado por huecos' : 'degradado'
}
