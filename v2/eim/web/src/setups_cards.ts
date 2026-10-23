import { esc } from './panels'
import type { Side } from './sim_calc'
import { bogIso } from './tz'

/**
 * Piezas HTML del panel «Operaciones sugeridas» (T50 + T122): tipos de `GET /v2/setups`, las tres
 * posiciones del ranking, el embudo de estados y las ideas pendientes de confirmación. Todo sale
 * de la respuesta real; un dato ausente se dice («—», «sin dato»), nunca se rellena.
 */

export interface Evidence {
  n_oos: number; mean_r: number | null; ci95: [number | null, number | null]; p_holm: number | null
  max_dd: number | null; win_rate: number | null; cost_r: number | null
  n_live: number | null; mean_live: number | null
}
export interface Setup {
  side: Side; kind: 'market' | 'limit'; entry: number; sl: number; tp: number; rr: number
  strategy: string; timeframe: string; version: string; id: string; reason: string; hours: number
  created_at: number; valid_until: number | null; state: string; evidence: Evidence
  symbol?: string; idea_id?: string
  context?: { conf: number; syn_bias: number; regime: string | null; htf: number }
  verdict?: string; verdict_reason?: string | null
}
interface Rule { kind: string; price?: number; until?: number | null; lo?: number; hi?: number; atr_k?: number; bias?: number; value?: number }
export interface Slot {
  rank: number; state: 'validada' | 'vacia'; index: number | null; message?: string
  order?: { rule: string; ci_low: number | null }
  success?: { win_rate: number | null; n: number; wins: number | null; ci95: number[] | null; calibrated: boolean; note: string }
  invalidation?: Rule[]; risks?: Rule[]; sim_status?: string | null
}
export interface Funnel {
  identified: number; analyzed: number; validated: number; ranked: number; pending: number
  discarded: number; unanalyzed: number; timeframes: string[]; reasons: { reason: string; n: number }[]
}
export type Status = 'ok' | 'sin_validadas' | 'sin_senal' | 'datos_viejos'
export interface SetupsView {
  mode: string; symbol: string; asof: number | null; now: number; criteria_version: string
  verdicts_asof: number | null; price: number | null; status: Status; message: string
  validation: { counts: Record<string, number>; validated: string[]; attempts: number }
  setups: Setup[]; watch?: Setup[]; ranking?: Slot[]; funnel?: Funnel; note: string; source: string
}

export const nf = (x: number, d = 2): string => x.toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d })
const sg = (x: number): string => (x > 0 ? '+' : x < 0 ? '−' : '')
export const usd = (x: number): string => `${sg(x)}${nf(Math.abs(x))} USDT`
export const pc = (x: number): string => `${sg(x)}${nf(Math.abs(x * 100))} %`
const pct0 = (x: number): string => `${Math.round(x * 100)} %`
const rr = (x: number | null): string => (x === null ? '—' : `${sg(x)}${nf(Math.abs(x), 3)} R`)
export const utc = (t: number): string => bogIso(t).slice(0, 16).replace('T', ' ') + ' COT'

const SIM: Record<string, string> = {
  PENDIENTE: 'orden simulada a la espera de llenado', ABIERTA: 'posición simulada abierta',
  CERRADA: 'cerrada en la simulación', CANCELADA: 'cancelada en la simulación', RECHAZADA: 'rechazada en la simulación',
}

function evidence(e: Evidence): string {
  const ci = e.ci95[0] === null || e.ci95[1] === null ? '—' : `[${rr(e.ci95[0])}, ${rr(e.ci95[1])}]`
  const live = e.n_live ? `n ${e.n_live}, R medio ${rr(e.mean_live)}` : 'sin operaciones aún'
  return '<dl class="su-ev"><dt>Fuera de muestra</dt>' +
    `<dd>n <b>${e.n_oos}</b> · R medio <b>${rr(e.mean_r)}</b> · IC95 % ${ci}</dd>` +
    `<dt>Contra el azar</dt><dd>p (Holm) <b>${e.p_holm === null ? '—' : nf(e.p_holm, 3)}</b></dd>` +
    `<dt>Riesgo y costos</dt><dd>DD máx. <b>${e.max_dd === null ? '—' : pct0(e.max_dd)}</b> · costo medio <b>${e.cost_r === null ? '—' : `${nf(e.cost_r, 2)} R`}</b></dd>` +
    `<dt>En vivo (simulado)</dt><dd>${live}</dd></dl>`
}

/** Acierto observado fuera de muestra con su IC de Wilson: frecuencia, no probabilidad calibrada. */
function success(sl: Slot): string {
  const s = sl.success
  if (!s || s.win_rate === null) return '<p class="su-prob">Acierto fuera de muestra: <b>sin dato</b> (sin muestra).</p>'
  const ci = s.ci95 && s.ci95.length === 2 ? ` · IC95 % ${pct0(s.ci95[0])}–${pct0(s.ci95[1])}` : ''
  return `<p class="su-prob" title="${esc(s.note)}">Acierto fuera de muestra <b class="num">${pct0(s.win_rate)}</b>` +
    ` <span class="muted">(${s.wins}/${s.n}${ci}) · frecuencia simulada, no probabilidad calibrada</span></p>`
}

function context(s: Setup): string {
  const c = s.context
  if (!c) return ''
  const side = s.side === 'long' ? 1 : -1
  const syn = c.syn_bias === 0 ? 'neutral o sin dato'
    : `${sg(c.syn_bias)}${nf(Math.abs(c.syn_bias), 2)} (${c.syn_bias * side > 0 ? 'a favor' : 'en contra'})`
  const htf = c.htf > 0 ? 'a favor' : c.htf < 0 ? 'en contra' : 'sin dato o lateral'
  return '<p class="su-ctx"><span>Contexto del análisis</span> ' +
    `confianza de la estrategia <b>${pct0(c.conf)}</b> · síntesis de los agentes <b>${syn}</b> · ` +
    `régimen <b>${esc(c.regime ?? 'sin dato')}</b> · tendencia del marco mayor <b>${htf}</b></p>`
}

function ruleText(r: Rule): string {
  switch (r.kind) {
    case 'sl': return `el precio cruza el stop-loss (${nf(r.price!)})`
    case 'tp': return `el precio alcanza el objetivo (${nf(r.price!)})`
    case 'window': return r.until ? `la orden límite vence sin llenarse (${utc(r.until).slice(11)})` : 'la orden límite vence sin llenarse'
    case 'filled': return `el precio toca la entrada límite (${nf(r.price!)}): pasa a ser posición, ya no es oportunidad nueva`
    case 'drift': return `el precio sale de ${nf(r.lo!)}–${nf(r.hi!)} (±${nf(r.atr_k ?? 0.5, 1)} ATR de la entrada)`
    case 'htf_against': return 'va en contra de la tendencia del marco mayor'
    case 'synthesis_against': return `la síntesis de los agentes apuntaba en contra (${sg(r.bias ?? 0)}${nf(Math.abs(r.bias ?? 0), 2)})`
    case 'max_dd': return `drawdown máximo fuera de muestra ${pct0(r.value ?? 0)}`
    case 'no_live': return 'aún sin operaciones en vivo (simuladas) que la confirmen'
    default: return esc(r.kind)
  }
}

/** Tarjeta de una posición validada: niveles, acierto, evidencia, contexto, invalidación y estado. */
export function slotCard(sl: Slot, s: Setup, criteria: string, amount: string, out: string): string {
  const long = s.side === 'long', limit = s.kind === 'limit', i = sl.index!
  const mv = (x: number): string => pc((x - s.entry) / s.entry)
  const risk = Math.abs(s.entry - s.sl) / s.entry
  const sim = sl.sim_status ? SIM[sl.sim_status] ?? sl.sim_status.toLowerCase() : 'sin registro en la sombra del bróker'
  return `<article class="su-card" data-side="${s.side}" data-rank="${sl.rank}">` +
    `<header><b class="su-rank">#${sl.rank}</b><span class="su-side">${long ? 'LONG' : 'SHORT'}</span>` +
    `<span class="su-sym">${esc(s.symbol ?? 'BTCUSDT')}</span>` +
    '<span class="su-tag" data-ok="true">Validada · sugerida, no ejecutada</span>' +
    `<span class="muted su-h">${esc(s.strategy)} · ${esc(s.timeframe)} · ${esc(s.version)} · ~${Math.round(s.hours)} h máx.</span></header>` +
    '<div class="su-lv">' +
    `<div><span>Entrada (${limit ? 'límite' : 'mercado'})</span><b class="num">${nf(s.entry)}</b>` +
    `<small>${limit && s.valid_until ? `válida hasta ${utc(s.valid_until).slice(11)}` : 'precio de la última vela'}</small></div>` +
    `<div><span>Objetivo (TP)</span><b class="num up">${nf(s.tp)}</b><small>${mv(s.tp)}</small></div>` +
    `<div><span>Stop-loss</span><b class="num down">${nf(s.sl)}</b><small>${mv(s.sl)}</small></div></div>` +
    `<p class="su-stats">Riesgo <b>${nf(risk * 100)} %</b> del precio · R:B <b>1 : ${nf(s.rr)}</b> · decidida <b>${utc(s.created_at)}</b></p>` +
    success(sl) + evidence(s.evidence) + context(s) +
    `<p class="su-why"><span>Por qué</span> ${esc(s.reason)}</p>` +
    `<div class="su-rules"><span>Se invalida si</span><ul>${(sl.invalidation ?? []).map((r) => `<li>${ruleText(r)}</li>`).join('')}</ul></div>` +
    (sl.risks?.length ? `<div class="su-rules"><span>Riesgos</span><ul>${sl.risks.map((r) => `<li>${ruleText(r)}</li>`).join('')}</ul></div>` : '') +
    `<p class="su-val"><span>Validación</span> análisis: veredicto <b>VALIDADA</b> (${esc(criteria)}, ${esc(s.version)}) · bróker simulado: <b>${esc(sim)}</b></p>` +
    `<label class="su-amt"><span>Monto (margen USDT)</span><input data-amt="${i}" inputmode="decimal" class="num" value="${amount}" /></label>` +
    `<div class="su-out" data-out="${i}">${out}</div>` +
    `<button type="button" class="btn" data-apply="${i}">Cargar en el simulador</button></article>`
}

/** Posición sin oportunidad validada: se dice por qué; nunca se rellena con otra idea. */
export function emptySlot(sl: Slot): string {
  return `<article class="su-card su-slot-empty" data-rank="${sl.rank}"><header><b class="su-rank">#${sl.rank}</b>` +
    '<span class="su-tag" data-ok="false">Sin oportunidad validada</span></header>' +
    `<p class="muted">${esc(sl.message ?? '')}</p></article>`
}

/** Embudo de la última vela cerrada: identificadas → analizadas → validadas → en el ranking. */
export function funnelHtml(f: Funnel | undefined): string {
  if (!f) return ''
  const step = (n: number, label: string, k: string): string => `<span class="su-step" data-k="${k}"><b class="num">${n}</b> ${label}</span>`
  const why = f.reasons.length
    ? `<details class="su-disc"><summary>Por qué se descartaron (${f.discarded})</summary><ul>${f.reasons.map((r) => `<li>${esc(r.reason)} · <b>${r.n}</b></li>`).join('')}</ul></details>`
    : ''
  return `<div class="su-funnel" aria-label="Estado de las oportunidades de la última vela cerrada">` +
    `<span class="muted">Última vela cerrada (${f.timeframes.join(' · ')}):</span>` +
    step(f.identified, 'identificadas', 'identified') + '<i>→</i>' + step(f.analyzed, 'analizadas', 'analyzed') + '<i>→</i>' +
    step(f.validated, 'validadas por la simulación', 'validated') + '<i>→</i>' + step(f.ranked, 'en el ranking', 'ranked') +
    '<i>·</i>' + step(f.pending, 'pendientes de confirmación', 'pending') + '<i>·</i>' + step(f.discarded, 'descartadas', 'discarded') +
    (f.unanalyzed ? '<i>·</i>' + step(f.unanalyzed, 'sin veredicto aún', 'unanalyzed') : '') + '</div>' + why
}

/** Idea EN OBSERVACIÓN (pendiente de confirmación): sin validar, sin monto ni «cargar». */
function watchCard(s: Setup): string {
  const mv = (x: number): string => pc((x - s.entry) / s.entry)
  return `<article class="su-card su-watch" data-side="${s.side}"><header>` +
    `<span class="su-side">${s.side === 'long' ? 'LONG' : 'SHORT'}</span>` +
    '<span class="su-tag" data-ok="false">Pendiente de confirmación · NO validada</span>' +
    `<span class="muted su-h">${esc(s.strategy)} · ${esc(s.timeframe)} · ${esc(s.version)}</span></header>` +
    '<div class="su-lv">' +
    `<div><span>Entrada (${s.kind === 'limit' ? 'límite' : 'mercado'})</span><b class="num">${nf(s.entry)}</b></div>` +
    `<div><span>Objetivo (TP)</span><b class="num up">${nf(s.tp)}</b><small>${mv(s.tp)}</small></div>` +
    `<div><span>Stop-loss</span><b class="num down">${nf(s.sl)}</b><small>${mv(s.sl)}</small></div></div>` +
    `<p class="su-stats">R:B <b>1 : ${nf(s.rr)}</b> · fuera de muestra n <b>${s.evidence.n_oos}</b> · R medio <b>${rr(s.evidence.mean_r)}</b> · decidida <b>${utc(s.created_at)}</b></p>` +
    `<p class="muted">Falta: ${esc(s.verdict_reason ?? 'evidencia suficiente')}</p>` +
    `<p class="su-why"><span>Por qué</span> ${esc(s.reason)}</p></article>`
}

export function watchHtml(v: SetupsView, open: boolean): string {
  if (!v.watch?.length) return ''
  return `<details class="su-watchbox"${open ? ' open' : ''}><summary class="sh">Pendientes de confirmación (${v.watch.length}) ` +
    '<span class="muted">· en observación, aún sin evidencia suficiente · no son sugerencias ni ocupan posiciones del ranking</span></summary>' +
    `<div class="su-grid">${v.watch.map((s) => watchCard(s)).join('')}</div></details>`
}
