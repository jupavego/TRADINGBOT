import { base } from './api'
import { esc } from './panels'
import { simulate, type Side } from './sim_calc'

/**
 * Operaciones sugeridas (intradía, 4 h – 36 h): las 3 mejor valoradas por el backend
 * (`GET /v2/setups`, marco 1 h) con entrada límite, TP y SL. El monto lo escribe el usuario y
 * se calcula la ganancia/pérdida con la misma calculadora del simulador. Modo: Análisis.
 */

interface Setup {
  side: Side; entry: number; sl: number; tp: number; rr: number
  p_fill: number; p_tp: number; ev_r: number; confluence: number; score: number; hours: number
  entry_basis: string; sl_basis: string; tp_basis: string; aligned: boolean
}
interface SetupsView {
  mode: string; asof: number; close: number; horizon_hours: [number, number]; fill_hours: number
  fee_rate: number; bias: number | null; confidence: number | null; source: string
  setups: Setup[]; note: string
}
export interface ApplySetup { side: Side; entry: number; tp: number; sl: number; amount: number; leverage: number }

const TF = '1h' // base del análisis intradía, independiente del marco del gráfico
const KEY = 'eim.setups'
const MMR: Record<string, number> = { BTCUSDT: 0.004, ETHUSDT: 0.005 }
const nf = (x: number, d = 2): string => x.toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d })
const sg = (x: number): string => (x > 0 ? '+' : x < 0 ? '−' : '')
const usd = (x: number): string => `${sg(x)}${nf(Math.abs(x))} USDT`
const pc = (x: number): string => `${sg(x)}${nf(Math.abs(x * 100))} %`
const pct0 = (x: number): string => `${Math.round(x * 100)} %`

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
      const r = await fetch(`${base()}/v2/setups?symbol=${this.symbol}&tf=${TF}`, { signal: this.abort.signal })
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
    const fee = (this.view?.fee_rate ?? 0.0007) / 2
    const r = simulate({
      side: s.side, margin: 'isolated', orderType: 'limit', leverage: this.prefs.leverage, entry: s.entry,
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

  private card(s: Setup, i: number): string {
    const long = s.side === 'long'
    const mv = (x: number): string => pc((x - s.entry) / s.entry)
    return `<article class="su-card" data-side="${s.side}">` +
      `<header><b class="su-rank">#${i + 1}</b><span class="su-side">${long ? 'LONG' : 'SHORT'}</span>` +
      `<span class="su-tag" data-ok="${s.aligned}">${s.aligned ? 'a favor de los agentes' : 'contra el sesgo'}</span>` +
      `<span class="muted su-h">~${Math.round(s.hours)} h</span></header>` +
      '<div class="su-lv">' +
      `<div><span>Entrada (límite)</span><b class="num">${nf(s.entry)}</b><small title="${esc(s.entry_basis)}">${esc(s.entry_basis)}</small></div>` +
      `<div><span>Take profit</span><b class="num up">${nf(s.tp)}</b><small>${mv(s.tp)} · ${esc(s.tp_basis)}</small></div>` +
      `<div><span>Stop loss</span><b class="num down">${nf(s.sl)}</b><small>${mv(s.sl)} · ${esc(s.sl_basis)}</small></div></div>` +
      `<p class="su-stats">R:B <b>1 : ${nf(s.rr)}</b> · llenado en ${this.view?.fill_hours ?? 12} h <b>${pct0(s.p_fill)}</b> · ` +
      `TP antes que SL <b>${pct0(s.p_tp)}</b> · confluencia <b>${s.confluence}</b> agente(s)</p>` +
      `<label class="su-amt"><span>Monto (margen USDT)</span><input data-amt="${i}" inputmode="decimal" class="num" value="${this.prefs.amounts[i] ?? ''}" /></label>` +
      `<div class="su-out" data-out="${i}">${this.outcome(s, i)}</div>` +
      `<button type="button" class="btn" data-apply="${i}">Cargar en el simulador</button></article>`
  }

  private paint(): void {
    const v = this.view
    const head = '<div class="su-head"><h3 class="sh">Operaciones sugeridas · intradía</h3>' +
      '<span class="sim">Análisis · no es una orden</span>' +
      `<span class="muted">${v ? `TP/SL para ${v.horizon_hours[0]} h – ${v.horizon_hours[1]} h · base ${TF}` : `base ${TF}`}</span>` +
      '<span class="spacer"></span>' +
      `<label class="su-lev">Apalancamiento <input data-k="lev" type="number" min="1" max="125" class="num" value="${this.prefs.leverage}" />x</label></div>`
    let body: string
    if (this.error) body = `<p class="muted">No se pudieron calcular las sugerencias: ${esc(this.error)}</p>`
    else if (!v) body = '<p class="muted">Calculando sugerencias…</p>'
    else if (!v.setups.length) body = '<p class="muted">Ninguna operación cumple ahora los requisitos (R:B ≥ 1,2 y resolución en 4–36 h).</p>'
    else body = `<div class="su-grid">${v.setups.map((s, i) => this.card(s, i)).join('')}</div>`
    const foot = v
      ? `<p class="muted su-foot">${esc(v.note)} Precio ${nf(v.close)} · ${new Date(v.asof).toISOString().slice(0, 16).replace('T', ' ')} UTC · fuente ${esc(v.source)}` +
        ` · comisión ida y vuelta supuesta ${nf(v.fee_rate * 100, 2)} %.</p>`
      : ''
    this.el.innerHTML = head + body + foot
  }
}

const r2 = (x: number): number => Math.round(x * 100) / 100
