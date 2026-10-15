import type { AgentReport } from './types'

const LABEL: Record<string, string> = {
  structure: 'Estructura', vwap: 'VWAP', price_action: 'Price action', elliott: 'Elliott',
  ema: 'EMA / FRM', liquidations: 'Liquidaciones', seasonality: 'Estacionalidad', context: 'Contexto',
  derivatives: 'Derivados', levels: 'Niveles', microstructure: 'Microestructura', plan: 'Plan',
  regime: 'Régimen', technical: 'Técnico', calendar: 'Calendario',
}
export const agentName = (id: string): string => LABEL[id] ?? id

const STATUS: Record<string, string> = {
  ok: 'OK', degraded: 'Degradado', no_data: 'Sin datos', sin_ejecutar: 'Sin ejecutar',
}

export const esc = (s: unknown): string =>
  String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

const sgn = (n: number): string => (n > 0 ? '+' : '') + n.toFixed(2)


/** Última versión de cada agente a partir de reportes. */
export function latestPerAgent(reports: AgentReport[]): AgentReport[] {
  const m = new Map<string, AgentReport>()
  for (const r of reports) {
    const p = m.get(r.agent_id)
    if (!p || r.asof > p.asof) m.set(r.agent_id, r)
  }
  return [...m.values()]
}

export function renderJournal(el: HTMLElement, reports: AgentReport[]): void {
  if (!reports.length) { el.innerHTML = '<p class="muted">Sin reportes registrados todavía.</p>'; return }
  el.innerHTML = '<table class="log"><thead><tr><th>Hora (UTC)</th><th>Agente</th><th>Sesgo</th>' +
    '<th>Conf.</th><th>Estado</th><th>Evidencia</th></tr></thead><tbody>' +
    reports.map((r) => `<tr><td>${new Date(r.asof).toISOString().slice(0, 16).replace('T', ' ')}</td>` +
      `<td>${esc(agentName(r.agent_id))}</td><td class="num">${sgn(r.bias)}</td>` +
      `<td class="num">${Math.round(r.confidence * 100)}%</td>` +
      `<td><span class="chip" data-s="${esc(r.status)}">${esc(STATUS[r.status] ?? r.status)}</span></td>` +
      `<td class="muted">${esc(r.evidence[0] ?? '')}</td></tr>`).join('') + '</tbody></table>'
}
