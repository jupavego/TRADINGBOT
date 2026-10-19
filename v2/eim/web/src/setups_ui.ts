import { base } from './api'
import { esc } from './panels'
import { simulate, type Side } from './sim_calc'

/**
 * Operaciones sugeridas intradía (T50): solo oportunidades de estrategias VALIDADAS por la puerta
 * de T49 (`GET /v2/setups`), con su evidencia fuera de muestra, o el estado vacío explícito con su
 * motivo. Siempre «Sugerida · no ejecutada»: oportunidad potencial de un bróker simulado, no una
 * orden ni una garantía. El monto lo escribe el usuario y se calcula con la calculadora del
 * simulador («Cargar en el simulador» solo rellena esa calculadora). Modo: Análisis.
 */

interface Evidence {
  n_oos: number; mean_r: number | null; ci95: [number | null, number | null]; p_holm: number | null
  max_dd: number | null; win_rate: number | null; cost_r: number | null
  n_live: number | null; mean_live: number | null
}
interface Setup {
  side: Side; kind: 'market' | 'limit'; entry: number; sl: number; tp: number; rr: number
  strategy: string; timeframe: string; version: string; id: string; reason: string; hours: number
  created_at: number; valid_until: number | null; state: string; evidence: Evidence
}
type Status = 'ok' | 'sin_validadas' | 'sin_senal' | 'datos_viejos'
interface SetupsView {
  mode: string; symbol: string; asof: number | null; criteria_version: string
  verdicts_asof: number | null; price: number | null; status: Status; message: string
  validation: { counts: Record<string, number>; validated: string[]; attempts: number }
  setups: Setup[]; note: string; source: string
}
export interface ApplySetup { side: Side; entry: number; tp: number; sl: number; amount: number; leverage: number }

const KEY = 'eim.setups'
const MMR: Record<string, number> = { BTCUSDT: 0.004, ETHUSDT: 0.005 }
const nf = (x: number, d = 2): string => x.toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d })
const sg = (x: number): string => (x > 0 ? '+' : x < 0 ? '−' : '')
const usd = (x: number): string => `${sg(x)}${nf(Math.abs(x))} USDT`
const pc = (x: number): string => `${sg(x)}${nf(Math.abs(x * 100))} %`
const pct0 = (x: number): string => `${Math.round(x * 100)} %`
const rr = (x: number | null): string => (x === null ? '—' : `${sg(x)}${nf(Math.abs(x), 3)} R`)
const utc = (t: number): string => new Date(t).toISOString().slice(0, 16).replace('T', ' ') + ' UTC'
const FEE = 0.0007 // comisión ida y vuelta supuesta (taker 0,05 % + maker 0,02 %)
const NO_GUARANTEE = 'Oportunidad potencial. Evidencia de un bróker simulado; no garantiza rentabilidad.'

interface Prefs { amounts: number[]; leverage: number }
function loadPrefs(): Prefs {
  try {
    const p = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<Prefs>
    return { amounts: p.amounts ?? [100, 100, 100], leverage: p.leverage ?? 10 }
  } catch { return { amounts: [100, 100, 100], leverage: 10 } }
}

export class SetupsPanel {
  private view: SetupsView | null = null
  private error = ''
  private symbol = 'BTCUSDT'
  private prefs = loadPrefs()
  private timer: number | undefined
  private abort: AbortController | null = null

  constructor(private el: HTMLElement, private onApply: (s: ApplySetup) => void) {
    el.addEventListener('input', (e) => this.onInput(e.target as HTMLInputElement))
    el.addEventListener('click', (e) => {
      if ((e.target as HTMLElement).closest('[data-open-paper]')) {
        document.getElementById('paper-btn')?.click(); return
      }
      const b = (e.target as HTMLElement).closest<HTMLButtonElement>('[data-apply]')
      const s = b && this.view?.setups[Number(b.dataset.apply)]
      if (s) this.onApply({ side: s.side, entry: r2(s.entry), tp: r2(s.tp), sl: r2(s.sl),
        amount: this.prefs.amounts[Number(b.dataset.apply)] ?? 0, leverage: this.prefs.leverage })
    })
    this.paint()
  }

  setSymbol(sym: string): void {
    if (sym !== this.symbol) { this.symbol = sym; this.view = null; this.paint() }
    void this.reload()
  }

  /** Recarga con un pequeño retraso para agrupar varios avisos seguidos (reportes nuevos). */
  soon(): void { clearTimeout(this.timer); this.timer = window.setTimeout(() => void this.reload(), 1500) }

  async reload(): Promise<void> {
    this.abort?.abort(); this.abort = new AbortController()
    try {
      const r = await fetch(`${base()}/v2/setups?symbol=${this.symbol}`, { signal: this.abort.signal })
      if (!r.ok) throw new Error(String((await r.json().catch(() => ({}))).detail ?? r.statusText))
      this.view = await r.json() as SetupsView; this.error = ''
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      this.view = null; this.error = (e as Error).message
    }
    this.paint()
  }

  private save(): void { try { localStorage.setItem(KEY, JSON.stringify(this.prefs)) } catch { /* ignora */ } }

  private onInput(t: HTMLInputElement): void {
    const v = Number(t.value.replace(',', '.'))
    if (t.dataset.k === 'lev') this.prefs.leverage = Math.min(125, Math.max(1, Math.round(v) || 1))
    else if (t.dataset.amt !== undefined) this.prefs.amounts[Number(t.dataset.amt)] = Math.max(0, v || 0)
    else return
    this.save()
    // solo se repintan los resultados: el campo que se escribe conserva el foco
    this.view?.setups.forEach((s, i) => {
      const box = this.el.querySelector(`[data-out="${i}"]`)
      if (box) box.innerHTML = this.outcome(s, i)
    })
  }

  private outcome(s: Setup, i: number): string {
    const amt = this.prefs.amounts[i] ?? 0
    const fee = FEE / 2
    const r = simulate({
      side: s.side, margin: 'isolated', orderType: s.kind, leverage: this.prefs.leverage, entry: s.entry,
      amount: amt, unit: 'margin', tp: s.tp, tpMode: 'price', sl: s.sl, slMode: 'price', balance: amt,
      makerFee: fee, takerFee: fee, mmr: MMR[this.symbol] ?? 0.005,
    })
    if (!r.ok || !r.tp || !r.sl) return '<p class="muted">Escribe el monto para ver el resultado.</p>'
    const liq = r.liq !== null && (s.side === 'long' ? r.liq >= s.sl : r.liq <= s.sl)
    return `<div class="su-res"><span>Si toca el TP</span><b class="num up">${usd(r.tp.net)}</b><small>ROE ${pc(r.tp.roe)}</small></div>` +
      `<div class="su-res"><span>Si toca el SL</span><b class="num down">${usd(r.sl.net)}</b><small>ROE ${pc(r.sl.roe)}</small></div>` +
      `<p class="muted su-pos">Posición ${nf(r.notional)} USDT · ${nf(r.qty, 4)} ${this.symbol.replace(/USDT$/, '')} · comisiones incluidas` +
      (r.liq ? ` · liq. aprox. ${nf(r.liq)}` : '') + '</p>' +
      (liq ? '<p class="su-warn">⚠ Con este apalancamiento te liquidarían antes del SL: bájalo.</p>' : '')
  }

  private evidence(e: Evidence): string {
    const ci = e.ci95[0] === null || e.ci95[1] === null ? '—' : `[${rr(e.ci95[0])}, ${rr(e.ci95[1])}]`
    const live = e.n_live ? `n ${e.n_live}, R medio ${rr(e.mean_live)}` : 'sin operaciones aún'
    return '<dl class="su-ev"><dt>Fuera de muestra</dt>' +
      `<dd>n <b>${e.n_oos}</b> · R medio <b>${rr(e.mean_r)}</b> · IC95 % ${ci}</dd>` +
      `<dt>Contra el azar</dt><dd>p (Holm) <b>${e.p_holm === null ? '—' : nf(e.p_holm, 3)}</b> · acierto <b>${e.win_rate === null ? '—' : pct0(e.win_rate)}</b></dd>` +
      `<dt>Riesgo y costos</dt><dd>DD máx. <b>${e.max_dd === null ? '—' : pct0(e.max_dd)}</b> · costo medio <b>${e.cost_r === null ? '—' : `${nf(e.cost_r, 2)} R`}</b></dd>` +
      `<dt>En vivo (simulado)</dt><dd>${live}</dd></dl>`
  }

  private card(s: Setup, i: number): string {
    const long = s.side === 'long'
    const mv = (x: number): string => pc((x - s.entry) / s.entry)
    const risk = Math.abs(s.entry - s.sl) / s.entry
    const limit = s.kind === 'limit'
    return `<article class="su-card" data-side="${s.side}">` +
      `<header><b class="su-rank">#${i + 1}</b><span class="su-side">${long ? 'LONG' : 'SHORT'}</span>` +
      '<span class="su-tag" data-ok="false">Sugerida · no ejecutada</span>' +
      `<span class="muted su-h">${esc(s.strategy)} · ${esc(s.timeframe)} · ${esc(s.version)} · ~${Math.round(s.hours)} h máx.</span></header>` +
      '<div class="su-lv">' +
      `<div><span>Entrada (${limit ? 'límite' : 'mercado'})</span><b class="num">${nf(s.entry)}</b>` +
      `<small>${limit && s.valid_until ? `válida hasta ${utc(s.valid_until).slice(11)}` : 'precio de la última vela'}</small></div>` +
      `<div><span>Take profit</span><b class="num up">${nf(s.tp)}</b><small>${mv(s.tp)}</small></div>` +
      `<div><span>Stop loss</span><b class="num down">${nf(s.sl)}</b><small>${mv(s.sl)}</small></div></div>` +
      `<p class="su-stats">Riesgo <b>${nf(risk * 100)} %</b> del precio · R:B <b>1 : ${nf(s.rr)}</b> · decidida <b>${utc(s.created_at)}</b></p>` +
      this.evidence(s.evidence) +
      `<p class="su-why"><span>Por qué</span> ${esc(s.reason)}</p>` +
      `<label class="su-amt"><span>Monto (margen USDT)</span><input data-amt="${i}" inputmode="decimal" class="num" value="${this.prefs.amounts[i] ?? ''}" /></label>` +
      `<div class="su-out" data-out="${i}">${this.outcome(s, i)}</div>` +
      `<button type="button" class="btn" data-apply="${i}">Cargar en el simulador</button></article>`
  }

  private empty(v: SetupsView): string {
    return '<div class="su-empty"><b>Sin operaciones validadas para sugerir</b>' +
      `<p class="muted">Motivo: ${esc(v.message)}</p>` +
      '<p class="muted">Una estrategia solo se sugiere cuando supera los criterios de validación fuera de muestra (R medio neto con IC95 % sobre 0, contra el azar, drawdown, estabilidad y costos). «Ninguna validada» es un resultado válido.</p>' +
      '<button type="button" class="btn" data-open-paper>Ver validación en «Bróker simulado»</button></div>'
  }

  private paint(): void {
    const v = this.view
    const head = '<div class="su-head"><h3 class="sh">Operaciones sugeridas intradía</h3>' +
      '<span class="sim">Análisis · no es una orden</span>' +
      `<span class="muted">${v ? `solo estrategias validadas · marcos 15 m y 1 h · tenencia ≤ 36 h` : 'solo estrategias validadas'}</span>` +
      '<span class="spacer"></span>' +
      `<label class="su-lev">Apalancamiento <input data-k="lev" type="number" min="1" max="125" class="num" value="${this.prefs.leverage}" />x</label></div>`
    let body: string
    if (this.error) body = `<p class="muted">No se pudieron cargar las sugerencias: ${esc(this.error)}</p>`
    else if (!v) body = '<p class="muted">Cargando sugerencias validadas…</p>'
    else if (!v.setups.length) body = this.empty(v)
    else body = `<div class="su-grid">${v.setups.map((s, i) => this.card(s, i)).join('')}</div>`
    const foot = v
      ? `<p class="muted su-foot">${NO_GUARANTEE} ` +
        (v.price !== null ? `Precio ${nf(v.price)} · ` : '') +
        (v.asof ? `bróker al ${utc(v.asof)} · ` : '') +
        (v.verdicts_asof ? `veredictos al ${utc(v.verdicts_asof)} (${esc(v.criteria_version)}) · ` : '') +
        `fuente ${esc(v.source)} · comisión ida y vuelta supuesta ${nf(FEE * 100, 2)} %.</p>`
      : `<p class="muted su-foot">${NO_GUARANTEE}</p>`
    this.el.innerHTML = head + body + foot
  }
}

const r2 = (x: number): number => Math.round(x * 100) / 100
