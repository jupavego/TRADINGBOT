/** Estado de la protección progresiva por perfil y por operación (T112). Todo es SIMULADO.
 *  El nivel protegido es un nivel del stop y el flotante no está realizado: ninguno es ganancia. */
import { PROFILE_VAR } from './paper_chart'
import { dur, esc, nf, pct, px, side, tone, usd, utc } from './paper_fmt'
import type { LadderStats, PaperSummary, PaperTrade, Position, ProfileView } from './paper_types'

/** Cinco estados de la escalera y, aparte, liquidación, salvaguarda e incidencia técnica. */
export const PSTATE: Record<string, { label: string; hint: string }> = {
  inicial: { label: 'Stop inicial', hint: 'Manda el SL de la idea y el flotante neto está en cero o en contra: el riesgo entero sigue en juego.' },
  inactiva: { label: 'Protección inactiva', hint: 'Flotante neto a favor pero por debajo del umbral de activación: aún manda el SL inicial.' },
  activa: { label: 'Protección activa', hint: 'El stop dinámico protege un nivel neto (escalón o BE+) y solo sube.' },
  cerrada_sl_inicial: { label: 'Cerrada por stop inicial', hint: 'Tocó el SL de la idea antes de activar la protección.' },
  cerrada_sl_dinamico: { label: 'Cerrada por stop dinámico', hint: 'Retrocedió hasta el stop movido por un escalón o por el BE+.' },
  liquidacion: { label: 'Liquidación', hint: 'El precio atravesó la liquidación (margen aislado): se pierde el margen entero.' },
  salvaguarda: { label: 'Cerrada por salvaguarda', hint: 'Cierre ordenado por el kill-switch independiente (T31).' },
  incidencia: { label: 'Incidencia técnica', hint: 'Dato no finito o estado inconsistente: la posición sigue abierta y no se inventa un cierre.' },
}
const OPEN_STATES = ['inicial', 'inactiva', 'activa', 'incidencia']
const MODE: Record<string, string> = { SIMULADO: 'Simulado', TESTNET: 'Testnet', ANALISIS: 'Análisis' }
const SOURCE: Record<string, string> = { inicial: 'SL inicial', escalon: 'escalón', be: 'BE+', recuperado: 'suelo recuperado' }

export const stateChip = (s: string): string =>
  s ? `<span class="pp-ps" data-ps="${s}" title="${esc(PSTATE[s].hint)}">${PSTATE[s].label}</span>` : ''

/** Estado de una posición abierta; «» si el perfil no usa escalera (sale por SL/TP/BE+/tiempo). */
export function posState(p: Position): string {
  const l = p.ladder
  if (!l) return ''
  if (p.protection_state === 'inconsistente' || l.state === 'incidencia' || l.state === 'inconsistente' || l.incident || p.liq_why) return 'incidencia'
  if (l.state === 'protegida') return 'activa'
  return l.float_usd > 0 ? 'inactiva' : 'inicial'
}

/** Estado de una operación terminada (motivo de cierre); «» si no salió por la escalera. */
export function tradeState(t: PaperTrade): string {
  if (t.reason === 'LIQUIDACION') return 'liquidacion'
  if (t.reason === 'SALVAGUARDA') return 'salvaguarda'
  if (!t.ladder) return ''
  return t.reason === 'SLD' ? 'cerrada_sl_dinamico' : t.reason === 'SL' ? 'cerrada_sl_inicial' : ''
}

/** Nivel protegido (o lo que falta para activarlo) de una posición abierta. */
export function levelText(p: Position): string {
  const l = p.ladder!
  if (l.level > 0) return `escalón ${l.level} · nivel ${nf(l.nominal_usd)} USDT netos <small class="muted">(nivel del stop, estimado; no es ganancia)</small>`
  if (l.stop_source === 'be') return 'BE+ (sin escalón)'
  const left = (l.first_usd ?? 0) - Math.max(l.max_float_usd ?? 0, 0)
  return l.first_usd === undefined ? 'sin protección aún' : `sin protección · faltan ${nf(Math.max(left, 0))} USDT netos de máximo`
}

/** Neto estimado si salta el stop vigente; ausente con una API anterior a T112. */
export function stopEstimate(p: Position): string {
  const x = p.ladder?.stop_est_usd
  return x === undefined ? '—' : `<b class="${tone(x)}">≈ ${usd(x)} USDT</b> <small class="muted">estimado</small>`
}

const exitsOf = (l: LadderStats): NonNullable<LadderStats['exits']> => l.exits ?? {
  stop_inicial: l.closed_initial_sl, stop_dinamico: l.closed_dynamic_sl, liquidacion: 0, salvaguarda: 0,
  incidencia_abierta: l.incidents, otros_motivos: 0, rechazados: 0,
}

function stepCell(l: LadderStats, kind: 'first' | 'step'): string {
  const u = kind === 'first' ? l.first_usd : l.step_usd
  const r = kind === 'first' ? l.first_r : l.step_r
  if (u === undefined) return '—'
  const head = kind === 'first' ? `+${nf(u)} USDT netos` : `cada +${nf(u)} USDT`
  return l.basis === 'r'
    ? `${head}<br><small class="muted">${nf(r ?? 0, 4).replace(/,?0+$/, '')} R · con el riesgo de referencia; cada operación usa el suyo</small>`
    : `${head}<br><small class="muted">fijo en USDT</small>`
}

function lastStepCell(p: ProfileView, names: Record<string, string>): string {
  const s = p.ladder?.last_step
  if (s === undefined) {          // API anterior a T112: lo que se ve en las abiertas
    const top = Math.max(0, ...p.positions.map((x) => x.ladder?.level ?? 0))
    return top ? `escalón ${top} <small class="muted">(máximo entre las abiertas)</small>`
      : '—<br><small class="muted">la API en marcha aún no publica el último escalón (llega con T112)</small>'
  }
  if (!s) return 'ninguno todavía'
  const what = s.source === 'be' ? 'BE+' : s.source === 'recuperado' ? `suelo recuperado (escalón ${s.level})` : `escalón ${s.level}`
  return `${what} · nivel ${nf(s.nominal_usd)} USDT<br><small class="muted">${utc(s.t)} COT · ${esc((names[s.sid] ?? s.sid).split(' · ')[0])} · ` +
    `${s.open ? 'sigue abierta' : 'ya cerrada'}</small>`
}

function countsCell(p: ProfileView): string {
  const ss = p.positions.map(posState).filter(Boolean)
  if (!ss.length) return `0 de ${p.positions.length} abiertas`
  const act = ss.filter((s) => s === 'activa').length
  const by = OPEN_STATES.map((s) => [s, ss.filter((x) => x === s).length] as const).filter(([, n]) => n)
    .map(([s, n]) => `${stateChip(s)} ${n}`).join(' ')
  return `<b>${act}</b> de ${p.positions.length} abiertas<br><small>${by}</small>`
}

function profileTable(ps: ProfileView[], names: Record<string, string>): string {
  const row = (label: string, f: (p: ProfileView, l: LadderStats) => string): string =>
    `<tr><th>${label}</th>${ps.map((p) => `<td class="num">${p.ladder ? f(p, p.ladder) : '<span class="muted">sin escalera</span>'}</td>`).join('')}</tr>`
  const bad = (n: number): string => `<b class="${n ? 'down' : ''}">${n}</b>`
  const m = (x: number | null): string => (x === null ? '—' : `${usd(x)} USDT`)
  return `<div class="pp-scroll"><table class="pp-t pp-rules pp-prot"><thead><tr><th></th>${ps.map((p) =>
    `<th style="--pc:var(${PROFILE_VAR[p.id] ?? '--accent'})"><i class="pp-dot"></i>${esc(p.name)}</th>`).join('')}</tr></thead><tbody>` +
    row('Salida', (p) => (p.params.exit_mode === 'ladder' ? 'solo el stop (inicial o dinámico)' : 'SL / TP / BE+ / tiempo')) +
    row('Umbral de activación', (_, l) => stepCell(l, 'first')) +
    row('Incremento por escalón', (_, l) => stepCell(l, 'step')) +
    row('Con protección activa', (p) => countsCell(p)) +
    row('Último escalón alcanzado', (p) => lastStepCell(p, names)) +
    row('Cierres: stop inicial · dinámico', (_, l) => `${exitsOf(l).stop_inicial} · ${exitsOf(l).stop_dinamico}`) +
    row('Liquidaciones · salvaguarda', (_, l) => `${bad(exitsOf(l).liquidacion)} · ${exitsOf(l).salvaguarda}`) +
    row('Incidencias técnicas abiertas', (p, l) => bad(exitsOf(l).incidencia_abierta + (p.protection?.inconsistent ?? 0))) +
    row('Fuera de regla: otros motivos · rechazados', (_, l) => `${bad(exitsOf(l).otros_motivos)} · ${bad(exitsOf(l).rechazados)}`) +
    row('Violaciones de reglas', (p, l) => bad(p.counts?.violations ?? l.violations)) +
    row('Máximo flotante medio → realizado medio', (_, l) => `${m(l.avg_max_float_usd)} → ${m(l.avg_realized_usd)}`) +
    row('Realizado − protegido estimado (medio)', (_, l) => m(l.avg_realized_vs_protected_usd)) +
    '</tbody></table></div>'
}

function openTable(ps: ProfileView[], names: Record<string, string>, price: number | null): string {
  const rows = ps.flatMap((p) => p.positions.filter((x) => x.ladder).map((x) => ({ p, x })))
  if (!rows.length) {
    const n = ps.filter((p) => p.ladder).length
    return `<p class="muted">Ninguna operación abierta ahora en los ${n} perfiles con escalera: no hay protección que seguir. Los estados aparecen aquí en cuanto se llene una orden.</p>`
  }
  const now = Date.now()
  const body = rows.map(({ p, x }) => {
    const l = x.ladder!
    const st = posState(x)
    const mark = price ?? x.mark
    const why = x.protection_why || l.incident || x.liq_why || l.inconsistent || ''
    return `<tr data-ps-row="${st}"><td><span class="pp-pname" style="--pc:var(${PROFILE_VAR[p.id] ?? '--accent'})">${esc(p.name)}</span><br>` +
      `<b>${esc((names[x.sid] ?? x.sid).split(' · ')[0])}</b> <span class="pp-tfb">${esc(x.timeframe)}</span> · <span class="pp-dir" data-side="${x.side > 0 ? 'long' : 'short'}">${side(x.side)}</span></td>` +
      `<td>${stateChip(st)}${why ? `<br><small class="warn">${esc(why)}</small>` : ''}${x.protection_state === 'recuperada' ? '<br><small class="muted">suelo recuperado tras reinicio</small>' : ''}</td>` +
      `<td class="num">${levelText(x)}</td>` +
      `<td class="num"><span class="down">${px(l.stop)}</span> <small class="muted">${SOURCE[l.stop_source ?? (l.level ? 'escalon' : 'inicial')] ?? esc(l.stop_source ?? '')}</small>` +
      `<br><small class="muted">${pct((l.stop - mark) / mark)} del precio · entrada ${px(x.entry)}</small></td>` +
      `<td class="num">${l.max_float_usd === null ? '—' : `${usd(l.max_float_usd)} USDT`}</td>` +
      `<td class="num ${tone(l.float_usd)}">${usd(l.float_usd)} USDT<br><small class="muted">no realizado</small></td>` +
      `<td class="num">${stopEstimate(x)}</td>` +
      `<td class="num">hace ${dur(now - x.fill_t)}</td></tr>`
  }).join('')
  return `<div class="pp-scroll"><table class="pp-t pp-prot-ops"><thead><tr><th>Perfil · operación</th><th>Estado</th><th>Nivel protegido</th>` +
    `<th>Stop dinámico vigente</th><th>Máximo flotante neto</th><th>Flotante neto actual</th><th>Neto si salta el stop</th><th>Abierta</th></tr></thead>` +
    `<tbody>${body}</tbody></table></div>`
}

function violationsBox(ps: ProfileView[]): string {
  const all = ps.flatMap((p) => (p.ladder?.violations_recent ?? []).map((v) => ({ p, v })))
  const total = ps.reduce((a, p) => a + (p.counts?.violations ?? p.ladder?.violations ?? 0), 0)
  if (!total) return '<p class="pp-prot-ok">Sin violaciones de reglas en ningún perfil: ningún cierre fuera del stop, la liquidación o la salvaguarda.</p>'
  const items = all.sort((a, b) => b.v.t - a.v.t).map(({ p, v }) =>
    `<li><time class="num">${utc(v.t)}</time> <b>${esc(p.name)}</b> · ${esc(v.reasons.join('; '))} · ` +
    `${v.executed ? 'cierre por el stop con historial anómalo: se contabilizó y se audita' : '<b>no se ejecutó</b>: la posición siguió abierta con su stop'}</li>`).join('')
  return `<div class="alert bad pp-viol" role="alert"><b>⚠ ${total} violación(es) de reglas</b> (últimas por perfil abajo; todas en la Bitácora, filtro «Violación de reglas»).` +
    `<ul>${items}</ul></div>`
}

/** Bloque «Protección por perfil» de la pestaña «Perfiles». */
export function protectionPanel(v: PaperSummary, price: number | null): string {
  const ps = v.profiles.filter((p) => p.ladder || p.params.exit_mode === 'ladder')
  if (!ps.length) return ''
  const names = Object.fromEntries(v.strategies.map((s) => [s.id, s.name]))
  const real = ps.some((p) => (p.params.ladder as { real_money?: boolean } | undefined)?.real_money)
  const legend = Object.keys(PSTATE).map(stateChip).join(' ')
  return `<section class="pp-protect"><div class="pp-prot-h"><h4 class="sh">Protección por perfil</h4>` +
    `<span class="mode" data-mode="${esc(v.mode)}">Modo: ${esc(MODE[v.mode] ?? v.mode)}</span>` +
    (real ? '<b class="down">⚠ un perfil declara dinero real: revisar la configuración</b>'
      : '<span class="pp-noreal">Dinero real deshabilitado: ninguna orden sale al exchange</span>') + '</div>' +
    `<p class="pp-legend"><small class="muted">Estados (pasa el cursor para ver qué significa cada uno):</small> ${legend}</p>` +
    violationsBox(ps) + profileTable(ps, names) +
    `<h4 class="sh">Operaciones abiertas · estado de su protección</h4>${openTable(ps, names, price)}` +
    `<p class="muted pp-note">«Neto si salta el stop» es una <b>estimación</b>: comisiones, el deslizamiento reservado al fijar el stop y el funding devengado. ` +
    'Un hueco de precio, el deslizamiento real o la latencia pueden dar otro resultado (ver «Realizado − protegido estimado»). ' +
    'Ni el nivel protegido ni el flotante son ganancia: solo lo cerrado se realiza. El flotante es neto a la marca de la última vela, con el costo de salida.</p></section>'
}
