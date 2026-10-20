/** Paneles de la traza (T76): hechos, «¿por qué (no) hubo operación?», agentes, reglas de riesgo y calidad. */
import { ago, esc } from './obs_types'
import { CAUSE_ES, MARK_ES, MARK_HINT, MARK_ICON, pct, type Explain, type Mark, type Quality, type Step } from './obs_trace_types'

const num = (x: number | null | undefined, d = 2): string => (x == null ? '—' : x.toLocaleString('es-CO', { maximumFractionDigits: d }))
const STATE_ES: Record<string, string> = { aprobada: 'Aprobada', vetada: 'Vetada', sin_decision: 'Sin decisión de riesgo' }
const ORDER_ES: Record<string, string> = { sin_orden: 'Sin orden', pedida: 'Orden pedida', enviada: 'Orden enviada', ejecutada: 'Ejecutada', con_error: 'Con error' }

export const markBadge = (m: Mark | null): string => m
  ? `<span class="obs-mark m-${m}" title="${esc(MARK_HINT[m])}">${MARK_ICON[m]} ${MARK_ES[m]}</span>`
  : '<span class="obs-mark m-none" title="Los eventos crudos ya se purgaron: no se puede calcular">? Sin eventos</span>'

/** Señal, decisión aprobada y orden: tres hechos distintos, nunca fundidos. */
export function factsHtml(x: Explain): string {
  const f = x.facts
  return `<div class="obs-facts">
    <div class="obs-fact"><h5>1 · Señal</h5><p>${esc(f.signal.text_es)}</p><small class="muted">Lo que opinaron los agentes.</small></div>
    <div class="obs-fact"><h5>2 · Decisión de riesgo</h5><p><b>${STATE_ES[f.decision.state] ?? f.decision.state}</b>${f.decision.risk?.size != null ? ` · tamaño ${num(f.decision.risk.size, 4)}` : ''}</p><small class="muted">Lo que autorizó o vetó el riesgo.</small></div>
    <div class="obs-fact"><h5>3 · Orden</h5><p><b>${ORDER_ES[f.order.state] ?? f.order.state}</b>${f.order.ts_utc ? ` · ${ago(f.order.ts_utc)}` : ''}</p><small class="muted">Lo que llegó al bróker.</small></div></div>`
}

/** «¿Por qué (no) hubo operación?»: solo motivos tal como los registró el sistema. */
export function whyHtml(x: Explain): string {
  const items = x.findings.map((f) => `<li class="${f.contaminates ? 'bad' : ''}"><b>${esc(CAUSE_ES[f.cause] ?? f.cause)}</b> · ${esc(f.why)}
      <small class="muted">(${esc(f.component_id)})</small></li>`).join('')
  return `<section class="obs-why"><h4>¿Por qué (no) hubo operación?</h4><p class="obs-head-es">${esc(x.headline_es)}</p>
    <ul class="obs-ul">${items || '<li class="muted">El sistema no registró ningún problema en esta traza.</li>'}</ul>
    <small class="muted">Motivos tal como los anotó el sistema; no los redacta ningún modelo de lenguaje.</small></section>`
}

export function agentsHtml(x: Explain): string {
  if (!x.agents.length) return ''
  const rows = x.agents.map((a) => `<tr class="${a.opposes ? 'opp' : ''}"><td>${esc(a.title_es)}</td><td>${num(a.bias)}</td><td>${num(a.confidence)}</td>
      <td>${a.vs_synthesis == null ? '—' : `${a.vs_synthesis > 0 ? '+' : ''}${num(a.vs_synthesis)}${a.opposes ? ' ✋ en contra' : ''}`}</td><td>${esc(a.status)}</td></tr>`).join('')
  return `<h4>Agentes frente a la síntesis</h4><table class="obs-tb"><thead><tr><th>Agente</th><th>Sesgo</th><th>Confianza</th><th>Diferencia</th><th>Estado</th></tr></thead><tbody>${rows}</tbody></table>`
}

export function riskHtml(x: Explain): string {
  const r = x.facts.decision.risk
  if (!r) return ''
  const rows = r.checks.map((c) => `<tr class="${c.ok ? '' : 'opp'}"><td>${c.ok ? '✔' : '✖'} ${esc(c.rule)}</td><td>${esc(c.detail)}</td></tr>`).join('')
  return `<h4>Reglas de riesgo evaluadas</h4>${rows ? `<table class="obs-tb"><tbody>${rows}</tbody></table>`
    : `<p class="muted">Sin el detalle de cada regla (${esc(r.source)}). ${r.reasons.map(esc).join('; ')}</p>`}
    <small class="muted">${r.approved ? 'Aprobada' : 'Vetada'} · config ${esc(r.config_version ?? '—')} · fuente: ${esc(r.source)}</small>`
}

export function stepHtml(s: Step, total: number): string {
  const c = s.consumed, p = s.produced
  const eat = [c.source ? `fuente ${esc(c.source)}` : '', c.age_min != null ? `antigüedad ${num(c.age_min, 0)} min` : '',
    c.coverage != null ? `cobertura ${pct(c.coverage)}` : '', ...c.refs.slice(0, 3).map((r) => `${esc(r.type)} ${esc(r.id)}${r.hash ? ` #${esc(r.hash.slice(0, 8))}` : ''}`)].filter(Boolean)
  const out = [p.bias != null ? `sesgo ${num(p.bias)}` : '', p.confidence != null ? `confianza ${num(p.confidence)}` : '',
    p.params_version ? `versión de parámetros ${esc(p.params_version)}` : '', ...p.warnings.map((w) => `⚠ ${esc(w)}`),
    ...p.refs.slice(0, 3).map((r) => `${esc(r.type)} ${esc(r.id)}${r.hash ? ` #${esc(r.hash.slice(0, 8))}` : ''}`)].filter(Boolean)
  return `<p class="obs-step-t"><b>Paso ${s.n} de ${total}</b> · ${esc(s.title_es)}${s.causal ? ' <span class="obs-flag">⚑ camino causal</span>' : ''}</p>
    <p>${esc(s.text_es)}</p>
    <dl class="obs-dl"><dt>Consumió</dt><dd>${eat.join(' · ') || 'nada registrado'}</dd><dt>Produjo</dt><dd>${out.join(' · ') || 'nada registrado'}</dd>
      <dt>Hora</dt><dd>${ago(s.ts_utc)}</dd></dl>${s.finding ? `<p class="obs-find">${esc(CAUSE_ES[s.finding.cause] ?? s.finding.cause)}: ${esc(s.finding.why)}</p>` : ''}`
}

export function qualityHtml(q: Quality | null): string {
  if (!q) return '<p class="muted">No se pudo leer el informe de calidad.</p>'
  if (!q.n_decisions) return `<p class="muted">No hay decisiones con eventos en este periodo${q.n_without_events ? ` (${q.n_without_events} con eventos ya purgados)` : ''}.</p>`
  const bar = (n: number, tot: number, cls: string): string => `<span class="obs-bar ${cls}" style="width:${Math.max(2, (100 * n) / (tot || 1))}%"></span>`
  const marks = (Object.keys(MARK_ES) as Mark[]).map((m) => `<li>${markBadge(m)} ${q.by_mark[m]} <small class="muted">(${pct(q.by_mark[m] / q.n_decisions)})</small>${bar(q.by_mark[m], q.n_decisions, `m-${m}`)}</li>`).join('')
  const rows = q.by_period.map((p) => `<tr><td>${new Date(p.start_ms).toISOString().slice(0, 13).replace('T', ' ')} h</td><td>${p.dirty} de ${p.n}</td><td>${pct(p.dirty_share)}${bar(p.dirty, p.n, 'm-con_error')}</td></tr>`).join('')
  return `<p class="obs-q-head"><b>${q.n_dirty} de ${q.n_decisions}</b> decisiones (${pct(q.dirty_share)}) tienen evidencia contaminada.</p>
    <ul class="obs-q-marks">${marks}</ul>
    <div class="obs-q-cols"><div><h5>Por causa</h5><ul class="obs-ul">${q.by_cause.map((c) => `<li>${esc(CAUSE_ES[c.cause] ?? c.cause)}: ${c.n} (${pct(c.share)})</li>`).join('') || '<li class="muted">Ninguna</li>'}</ul></div>
      <div><h5>Por componente</h5><ul class="obs-ul">${q.by_component.map((c) => `<li>${esc(c.component_id)}: ${c.n} (${pct(c.share)})</li>`).join('') || '<li class="muted">Ninguno</li>'}</ul></div></div>
    <h5>Por periodo</h5><table class="obs-tb"><tbody>${rows}</tbody></table>
    <small class="muted">${esc(q.note_es)}${q.n_without_events ? ` ${q.n_without_events} decisiones con eventos purgados no cuentan.` : ''}</small>`
}
