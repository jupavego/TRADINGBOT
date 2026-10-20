/** Nivel 3 (T75): panel de detalle de un componente y «En palabras simples» con plantillas. */
import { neighbours, compState } from './obs_graph'
import { ago, esc, getObs, STATE_ICON, STATE_LABEL, type ObsComp, type ObsData, type ObsEvent } from './obs_types'

const biasWord = (b: number): string =>
  Math.abs(b) < 0.1 ? 'neutral' : `${Math.abs(b) < 0.4 ? 'ligeramente ' : ''}${b > 0 ? 'alcista' : 'bajista'}`
const num = (x: unknown, d = 2): string => (typeof x === 'number' ? x.toLocaleString('es-CO', { maximumFractionDigits: d }) : '—')

/** Frase armada SOLO con datos del último evento (jamás texto libre de un LLM). */
export function plainWords(c: ObsComp, e: ObsEvent | undefined): string {
  if (c.built === 'planeado') return `Aún no existe: está planeado en la tarea ${c.task}. No es una avería.`
  if (!e) return 'Aún no hay actividad registrada de este componente.'
  const t = ago(e.ts_utc), det = e.detail ?? {}
  const src = e.source ? ` de ${esc(e.source)}` : ''
  const cov = e.coverage !== null && e.coverage !== undefined ? `, cobertura ${Math.round(e.coverage * 100)} %` : ''
  switch (e.kind) {
    case 'data_fetch': return `Recibió datos${src} ${t}${cov}${det.age_min != null ? `; el dato más nuevo tiene ${num(det.age_min, 0)} min` : ''}.`
    case 'signal': return e.status === 'error'
      ? `Intentó analizar ${t} y falló; el ciclo siguió sin su opinión.`
      : `Recibió el snapshot ${t} y concluyó: ${biasWord(Number(det.bias))}, confianza ${num(det.confidence)}${e.status === 'degraded' ? ' (con datos incompletos)' : ''}.`
    case 'synthesis': return `Juntó las opiniones ${t} y concluyó: ${biasWord(Number(det.bias))}, confianza ${num(det.confidence)}.`
    case 'forecast': return `Proyectó escenarios ${t} (${det.engine ?? 'motor'}, ${det.horizon_bars ?? '—'} velas hacia adelante).`
    case 'plan': return e.status === 'no_data' ? `${t}: no hubo plan (no había una operación clara).`
      : `Propuso ${t} una operación ${det.side ?? ''} con relación riesgo/beneficio ${num(det.rr)}.`
    case 'risk_decision': return e.status === 'rejected'
      ? `Vetó el plan ${t}. El veto no es un error: protege el capital.` : `Aprobó el plan ${t}.`
    case 'order_intent': case 'order_sent': case 'fill': return `Último movimiento de la orden: ${e.kind.replace('_', ' ')} ${t}.`
    case 'heartbeat': return `Dio señal de vida ${t}${det.state ? ` (estado: ${esc(det.state)})` : ''}.`
    default: return `Último evento: ${e.kind} ${t}, estado ${e.status}.`
  }
}

const li = (c: ObsComp, art: string, d: ObsData): string =>
  `<li><button class="obs-link" data-goto="${esc(c.id)}">${esc(c.title_es)}</button> <small class="muted">${esc(art)} · ${STATE_ICON[compState(d, c)]}</small></li>`

export async function detailHtml(d: ObsData, id: string, signal?: AbortSignal): Promise<string> {
  const c = d.comps.find((x) => x.id === id)
  if (!c) return ''
  const st = compState(d, c), nb = neighbours(d, id)
  let evs: ObsEvent[] = [], errs: { run_id: string; error: string | null; started_ms: number | null; trace_id: string | null }[] = []
  if (c.built === 'construido') {
    try {
      evs = (await getObs<{ items: ObsEvent[] }>(`events?component_id=${encodeURIComponent(id)}&limit=6`, signal)).items
      errs = (await getObs<{ items: typeof errs }>(`runs?component_id=${encodeURIComponent(id)}&status=error&limit=3`, signal)).items
    } catch { /* el panel sigue con lo que hay */ }
  }
  const last = evs[0]
  const refs = (last ? [...last.inputs.map((r) => `entra: ${r.type} ${r.id}`), ...last.outputs.map((r) => `sale: ${r.type} ${r.id}`)] : []).slice(0, 6)
  const trace = last?.trace_id
  return `<header class="obs-dh"><span class="obs-badge st-${st}">${STATE_ICON[st]} ${STATE_LABEL[st]}</span>
      <h3>${esc(c.title_es)}</h3><button class="obs-x" data-close aria-label="Cerrar detalle">×</button></header>
    <p class="obs-explain">${esc(c.explain_es)}</p>
    <section class="obs-simple"><h4>En palabras simples</h4><p>${plainWords(c, last)}</p></section>
    <dl class="obs-dl"><dt>Tipo</dt><dd>${esc(c.kind)}${c.version ? ` · versión ${esc(c.version)}` : ''}</dd>
      <dt>Proceso</dt><dd>${esc(c.process)}</dd><dt>Cadencia</dt><dd>${esc(c.cadence)}</dd>
      <dt>Último evento</dt><dd>${ago(c.last_event_ms)}${last?.source ? ` · fuente ${esc(last.source)}` : ''}</dd>
      <dt>Construido en</dt><dd>${esc(c.task)} (${c.built})</dd></dl>
    <h4>De quién depende</h4><ul class="obs-ul">${nb.from.map((x) => li(x.c, x.artifact, d)).join('') || '<li class="muted">De nadie (es una fuente).</li>'}</ul>
    <h4>A quién afecta</h4><ul class="obs-ul">${nb.to.map((x) => li(x.c, x.artifact, d)).join('') || '<li class="muted">A nadie más (es un destino).</li>'}</ul>
    ${refs.length ? `<h4>Últimas entradas y salidas <small class="muted">(referencias)</small></h4><ul class="obs-ul">${refs.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
    ${errs.length ? `<h4>Últimos errores</h4><ul class="obs-ul">${errs.map((r) => `<li>${ago(r.started_ms)} · ${esc(r.error ?? 'sin mensaje')}</li>`).join('')}</ul>` : ''}
    <p class="obs-links">${trace ? `<span title="Se verá completa con T76">Traza: <code>${esc(trace)}</code></span>` : ''}
      ${c.kind === 'agent' ? '<small class="muted">Su tarjeta está en la mesa, pestaña «Escenarios».</small>' : ''}</p>`
}
