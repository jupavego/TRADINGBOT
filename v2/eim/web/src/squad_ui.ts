import { fetchSquad } from './api'
import { ago } from './obs_types'
import { esc } from './panels'
import type { OutOfCycleBot, ScoreFreshness, SquadBot, SquadDim, SquadPayload, SquadState, SquadSupport } from './squad_types'
import { bogIso } from './tz'

const STATE: Record<SquadState, [string, string]> = {
  vota: ['vota', 'Su aporte al núcleo fue medido (T59): suma a la síntesis con su peso medido'],
  informa: ['informa', 'Se ve, pero no mueve el sesgo'],
  rechazado: ['rechazado', 'La puerta de edge (T49) lo rechaza y no aporta al núcleo'],
  deshabilitado_seguridad: ['deshabilitado', 'Seguridad no habilitada o sin aprobación: no entra aunque rinda'],
  cuarentena: ['cuarentena', 'Degradado mientras votaba: sin voto hasta reactivarlo a mano'],
  sin_puntuar: ['sin puntuar', 'Aún sin puntuación de T59: se ve, no vota'],
}
const DIMS = ['rendimiento', 'evidencia', 'seguridad', 'operativa'] as const

const stance = (x: number): string => (x > 0 ? 'alcista +1' : x < 0 ? 'bajista −1' : 'neutral 0')
const cot = (t: number | null): string => (t == null ? '—' : bogIso(t).slice(0, 16).replace('T', ' ') + ' COT')

/** De cuándo es la puntuación T59 y, si el recálculo falló o no avanza, por qué (T119). */
export function freshness(f: ScoreFreshness | null, symbol: string | null): string {
  if (!f || f.state === 'sin_medicion') return `<p class="muted meta">Sin puntuación T59 todavía${f?.reason ? `: ${esc(f.reason)}` : ''}.</p>`
  const when = `datos hasta ${cot(f.asof)}, calculada ${ago(f.computed)}`
  if (f.state === 'vigente') return `<p class="muted meta">Puntuación T59 medida en ${esc(symbol ?? '')}: ${when}.</p>`
  const why = f.state === 'fallida'
    ? `El último recálculo (${cot(f.last_attempt)}) falló: ${esc(f.reason)}.`
    : `La puntuación no avanza: ${esc(f.reason)}.`
  return `<p class="sq-warn" data-state="${f.state}" role="status">${why} Se muestra la medición anterior de ${esc(symbol ?? '')} (${when}); no es la actual.</p>`
}

const offRow = (b: OutOfCycleBot): string =>
  `<li><b>${esc(b.name)}</b> <small>clase ${esc(b.class)}</small> — ${esc(b.reason)}</li>`
const tone = (e: string): string => (e === 'cumple' ? 'up' : e === 'no cumple' || e === 'degradada' ? 'down' : 'warn')

function dim(name: string, d: SquadDim | undefined): string {
  if (!d) return `<span class="sq-dim" data-t="warn" title="sin puntuar">${name}: —</span>`
  const why = d.criterios ? Object.entries(d.criterios).map(([k, v]) => `${k}: ${v.detalle}`).join('\n') : ''
  return `<span class="sq-dim" data-t="${tone(d.estado)}" title="${esc(why)}">${name}: ${esc(d.estado)}</span>`
}

function row(b: SquadBot): string {
  const [label, tip] = STATE[b.state] ?? [b.state, '']
  const conf = b.confidence == null ? 'sin confianza propia' : `confianza ${(b.confidence * 100).toFixed(0)}%`
  const dims = DIMS.map((k) => dim(k, b.dimensions?.[k])).join('')
  return `<tr class="sq-row" data-state="${b.state}" data-live="${b.live === false ? 0 : 1}"><td><b>${esc(b.name)}</b><small>${esc(b.strategy)} · clase ${esc(b.class ?? '?')}</small></td>` +
    `<td><span class="sq-stance" data-s="${Math.sign(b.stance)}">${esc(stance(b.stance))}</span><small>${conf}` +
    `${b.signal_status !== 'ok' ? ` · señal ${esc(b.signal_status)}` : ''}</small>` +
    `${b.live === false ? `<small class="warn">sin señal reciente (${cot(b.asof)})</small>` : ''}</td>` +
    `<td><span class="sq-state" data-state="${b.state}" title="${esc(tip)}">${esc(label)}</span>` +
    `${b.publicable ? ' <span class="sq-pub" title="Validada por la puerta T49">publicable</span>' : ''}` +
    `${b.votes ? `<small>peso medido ${b.weight.toFixed(2)}</small>` : ''}</td>` +
    `<td class="sq-dims">${dims}</td><td><small title="${esc(b.version)}">${esc(b.version.slice(0, 12))}…</small>` +
    `<small>${esc((b.reasons[0] ?? '').slice(0, 160))}</small></td></tr>`
}

/** Eje −1..+1 con un punto por bot: de un vistazo, quién discrepa de quién. */
function spread(bots: SquadBot[], dis: number | null): string {
  const dots = bots.filter((b) => b.signal_status === 'ok' && !b.lane && b.live !== false).map((b) =>
    `<i class="sq-dot" data-s="${Math.sign(b.stance)}" style="left:${((b.stance + 1) / 2) * 100}%" title="${esc(b.name)} · ${esc(b.strategy)}: ${esc(stance(b.stance))}"></i>`).join('')
  const txt = dis == null ? 'Se necesitan al menos 2 bots con señal válida para medir la discrepancia.'
    : `Discrepancia (desv. de posturas): ${dis.toFixed(2)} — ${dis >= 0.8 ? 'bots enfrentados' : dis < 0.3 ? 'bots alineados' : 'opiniones mixtas'}`
  return `<div class="sq-spread"><div class="sq-axis" role="img" aria-label="${esc(txt)}"><span>−1 bajista</span><span>0</span><span>+1 alcista</span>${dots}</div><p class="muted meta">${esc(txt)}</p></div>`
}

export const supportText = (s: SquadSupport | null, k: 'up' | 'down' | 'flat'): string =>
  s && s.total ? `Escuadrón: ${s[k]} de ${s.total} bots apoyan este escenario (señal externa, no cambia la probabilidad)` : ''

/** Pestaña «Escuadrón» (T60): bots externos con su concepto de cuatro dimensiones y su estado. */
export class SquadPanel {
  private data: SquadPayload | null = null
  private err = ''
  private abort: AbortController | null = null
  support: SquadSupport | null = null

  constructor(private readonly el: HTMLElement, private readonly ctx: () => { symbol: string; tf: string },
    private readonly onData: () => void = () => {}) {
    el.addEventListener('click', (e) => { if ((e.target as HTMLElement).closest('#sq-reload')) void this.reload() })
    window.setInterval(() => { if (!this.el.hidden) void this.reload() }, 60_000)
  }

  async reload(): Promise<void> {
    this.abort?.abort()
    const ac = (this.abort = new AbortController())
    const { symbol, tf } = this.ctx()
    try { this.data = await fetchSquad(symbol, tf, ac.signal); this.err = '' }
    catch (e) { if (ac.signal.aborted) return; this.err = `No se pudo consultar el escuadrón: ${(e as Error).message}` }
    this.support = this.data?.support ?? null
    this.render()
    this.onData()
  }

  private render(): void {
    const d = this.data
    const head = `<div class="scen-bar arb-head"><b>Escuadrón de bots</b><span class="sq-tag">${esc(d?.label ?? 'Señal de un bot externo · no es una operación')}</span>` +
      `<span class="mode-tag">${esc(d?.mode ?? 'ANÁLISIS')}</span><button id="sq-reload">Actualizar</button></div>`
    if (!d) { this.el.innerHTML = head + `<p class="muted">${esc(this.err || 'Consultando el escuadrón…')}</p>`; return }
    const norm = d.bots.filter((b) => !b.lane), lane = d.bots.filter((b) => b.lane)
    const table = (bs: SquadBot[]): string => `<div class="tablewrap"><table class="sq-table"><thead><tr><th>Bot y estrategia</th><th>Postura</th><th>Estado</th><th>Cuatro dimensiones</th><th>Versión y motivo</th></tr></thead><tbody>${bs.map(row).join('')}</tbody></table></div>`
    const ch = d.channels
    const off = d.out_of_cycle ?? []
    this.el.innerHTML = head + freshness(d.scorecard ?? null, d.scored_symbol) +
      `<p class="muted meta">Votan: ${ch.vote ? 'sí' : 'ninguno'} · modulan confianza: ${ch.confidence ? 'sí' : 'no'} · segunda opinión por escenario: sí. Ningún bot pide tamaño, apalancamiento ni órdenes.</p>` +
      (d.bots.length ? spread(d.bots, d.disagreement) : '<p class="muted">Aún no hay señales de bots para este par y marco (se producen al cierre de vela).</p>') +
      (norm.length ? table(norm) : '') +
      (lane.length ? `<h4>Carril propio (clase L)</h4><p class="muted meta">Nunca suman a la dirección del precio.</p>${table(lane)}` : '') +
      (off.length ? `<h4>Fuera del ciclo en este equipo</h4><p class="muted meta">No opinan en vivo: no cuentan en la discrepancia ni en el apoyo.</p><ul class="sq-off">${off.map(offRow).join('')}</ul>` : '')
  }
}
