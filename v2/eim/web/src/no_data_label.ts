/** Etiqueta honesta para un agente en `no_data`, leída del motivo que ya devuelve el agente:
 *  «recolector apagado» · «acumulando 7/24» · «sin datos» (nunca un verde ni un 0 inventado). */
export function noDataLabel(warnings: string[] = []): string {
  const w = warnings.join(' ')
  const acc = /\((\d+)\/(\d+) velas/.exec(w)
  if (acc) return `acumulando ${acc[1]}/${acc[2]}`
  if (/colector no corre|sin recolecci[oó]n/i.test(w)) return 'recolector apagado'
  return 'sin datos'
}
