import { LineStyle, type IPriceLine } from 'lightweight-charts'
import type { PriceChart } from './chart'
import { cssVar } from './theme'
import {
  amountFromNotional, MAX_LEVERAGE, simulate,
  type AmountUnit, type Outcome, type SimInput, type SimResult, type TargetMode,
} from './sim_calc'

/**
 * Simulador de operación sobre el gráfico (estilo panel de órdenes de Binance Futuros).
 * Solo calcula y dibuja líneas "sim": nunca envía órdenes. Modo: Simulado.
 */

type Pick = 'entry' | 'tp' | 'sl' | null
interface State extends Omit<SimInput, 'entry'> { limit: number | null; draw: boolean; open: boolean }

const KEY = 'eim.sim'
// Supuestos típicos de Binance (VIP 0, primer tramo); el usuario los ajusta en «Avanzado».
const MMR: Record<string, number> = { BTCUSDT: 0.004 }
const DEFAULT: State = {
  side: 'long', margin: 'cross', orderType: 'market', leverage: 30, amount: 0, unit: 'margin',
  tp: null, tpMode: 'price', sl: null, slMode: 'price', balance: 1000,
  makerFee: 0.0002, takerFee: 0.0005, mmr: 0.004, limit: null, draw: true, open: true,
}

const nf = (x: number, d = 2): string => x.toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d })
const usd = (x: number): string => `${x > 0 ? '+' : x < 0 ? '−' : ''}${nf(Math.abs(x))} USDT`
const pc = (x: number): string => `${x > 0 ? '+' : x < 0 ? '−' : ''}${nf(Math.abs(x * 100))} %`
const tone = (x: number): string => (x > 0 ? 'up' : x < 0 ? 'down' : 'flat')
const num = (v: string): number | null => {
  const n = Number(v.replace(',', '.'))
  return v.trim() === '' || !Number.isFinite(n) ? null : n
}

function load(): State {
  try { return { ...DEFAULT, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') } } catch { return { ...DEFAULT } }
}

const seg = (k: string, opts: [string, string][], cls = ''): string =>
  `<div class="seg ${cls}" data-seg="${k}">${opts.map(([v, l]) => `<button type="button" data-v="${v}">${l}</button>`).join('')}</div>`
const modeSel = (k: string): string =>
  `<select data-k="${k}" aria-label="Unidad"><option value="price">Precio</option><option value="roe">ROE %</option><option value="move">% precio</option></select>`
const pickBtn = (k: Pick): string => `<button type="button" class="btn sim-pick" data-pick="${k}" title="Elegir el precio con un clic en el gráfico">⌖</button>`

const TEMPLATE = `
<div class="sim-head">
  <h3 class="sh">Simulador de operación</h3><span class="sim">Simulado · no envía órdenes</span>
  ${seg('margin', [['cross', 'Cruzado'], ['isolated', 'Aislado']])}
  <label class="sim-lev">Apal.<input data-k="leverage" type="number" min="1" max="${MAX_LEVERAGE}" step="1" class="num" />x
    <input data-k="leverage" type="range" min="1" max="${MAX_LEVERAGE}" step="1" aria-label="Apalancamiento" /></label>
  ${seg('orderType', [['market', 'Mercado'], ['limit', 'Límite']])}
  ${seg('side', [['long', 'Long'], ['short', 'Short']], 'sim-side')}
  <span class="spacer"></span>
  <label class="sim-chk"><input data-k="draw" type="checkbox" /> En gráfico</label>
  <button type="button" class="btn" data-act="reset">Limpiar</button>
  <button type="button" class="btn sim-fold" data-act="fold" aria-label="Plegar simulador"></button>
</div>
<div class="sim-body">
  <div class="sim-in">
    <label class="sim-f"><span>Saldo disp. (USDT)</span><input data-k="balance" inputmode="decimal" class="num" /></label>
    <label class="sim-f"><span>Precio de entrada <em data-x="entry-src"></em></span>
      <span class="sim-row"><input data-k="limit" inputmode="decimal" class="num" />${pickBtn('entry')}</span></label>
    <label class="sim-f sim-amt"><span>Monto</span>
      <span class="sim-row"><input data-k="amount" inputmode="decimal" class="num" placeholder="0" />
        <select data-k="unit" aria-label="Unidad del monto"><option value="margin">Margen USDT</option>
          <option value="notional">Tamaño USDT</option><option value="qty" data-x="base">BTC</option></select></span>
      <span class="sim-pcts"><input data-k="pct" type="range" min="0" max="100" step="1" value="0" aria-label="% del saldo" />
        <b data-x="pct">0 %</b></span></label>
    <label class="sim-f"><span>Take profit</span>
      <span class="sim-row"><input data-k="tp" inputmode="decimal" class="num" placeholder="—" />${modeSel('tpMode')}${pickBtn('tp')}</span></label>
    <label class="sim-f"><span>Stop loss</span>
      <span class="sim-row"><input data-k="sl" inputmode="decimal" class="num" placeholder="—" />${modeSel('slMode')}${pickBtn('sl')}</span></label>
  </div>
  <div class="sim-out" aria-live="polite"></div>
  <details class="sim-adv"><summary>Avanzado · comisiones y mantenimiento (supuestos)</summary>
    <label class="sim-f"><span>Maker %</span><input data-k="makerFee" inputmode="decimal" class="num" /></label>
    <label class="sim-f"><span>Taker %</span><input data-k="takerFee" inputmode="decimal" class="num" /></label>
    <label class="sim-f"><span>Margen mant. %</span><input data-k="mmr" inputmode="decimal" class="num" /></label>
    <p class="muted">Valores típicos de Binance (VIP 0, primer tramo). Ajústalos a tu cuenta: cambian la comisión y la liquidación.</p>
  </details>
  <div class="sim-warn"></div>
</div>`

const PCT_KEYS = new Set(['makerFee', 'takerFee', 'mmr'])

export class TradeSimulator {
  private s = load()
  private live: number | null = null
  private symbol = 'BTCUSDT'
  private pick: Pick = null
  private lines: IPriceLine[] = []

  constructor(private el: HTMLElement, private chart: PriceChart) {
    el.innerHTML = TEMPLATE
    el.addEventListener('input', (e) => this.onInput(e.target as HTMLInputElement))
    el.addEventListener('change', (e) => this.onInput(e.target as HTMLInputElement))
    el.addEventListener('click', (e) => this.onClick(e.target as HTMLElement))
    chart.chart.subscribeClick((p) => {
      if (!this.pick || !p.point) return
      const price = chart.series.coordinateToPrice(p.point.y)
      if (price === null) return
      const v = Math.round(price * 100) / 100
      if (this.pick === 'entry') { this.s.orderType = 'limit'; this.s.limit = v }
      else if (this.pick === 'tp') { this.s.tpMode = 'price'; this.s.tp = v }
      else { this.s.slMode = 'price'; this.s.sl = v }
      this.pick = null
      this.el.dataset.picking = 'false'
      this.save(); this.fill(); this.paint()
    })
    this.fill(); this.paint()
  }

  /** Cambio de activo: los precios de otro activo no aplican. */
  setSymbol(sym: string): void {
    if (sym === this.symbol) return
    this.symbol = sym; this.live = null; this.s.limit = null
    if (this.s.tpMode === 'price') this.s.tp = null
    if (this.s.slMode === 'price') this.s.sl = null
    this.s.mmr = MMR[sym] ?? this.s.mmr
    this.fill(); this.paint()
  }

  /** Carga una operación sugerida (orden límite) en el simulador y lo despliega. */
  apply(x: { side: 'long' | 'short'; entry: number; tp: number; sl: number; amount: number; leverage: number }): void {
    Object.assign(this.s, {
      side: x.side, orderType: 'limit', limit: x.entry, tp: x.tp, tpMode: 'price', sl: x.sl, slMode: 'price',
      amount: x.amount, unit: 'margin', leverage: x.leverage, open: true,
    })
    this.save(); this.fill(); this.paint()
    this.el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  /** Último precio en vivo (entrada a mercado). */
  setLast(price: number): void {
    this.live = price
    if (this.s.orderType === 'market') { this.paint(); this.setVal('limit', nf(price)) }
  }

  private entry(): number { return (this.s.orderType === 'market' ? this.live : this.s.limit ?? this.live) ?? 0 }
  private input(): SimInput { return { ...this.s, entry: this.entry() } }

  private q<T extends HTMLElement>(sel: string): T | null { return this.el.querySelector<T>(sel) }
  private setVal(k: string, v: string): void {
    this.el.querySelectorAll<HTMLInputElement>(`[data-k="${k}"]`).forEach((i) => {
      if (i.type === 'checkbox') i.checked = v === 'true'
      else if (document.activeElement !== i) i.value = v
    })
  }

  /** Vuelca el estado a los controles (sin pisar el campo que se está escribiendo). */
  private fill(): void {
    const s = this.s
    this.el.dataset.open = String(s.open)
    this.el.dataset.side = s.side
    this.el.querySelectorAll<HTMLElement>('[data-seg]').forEach((g) => g.querySelectorAll<HTMLButtonElement>('button')
      .forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === s[g.dataset.seg as 'side']))))
    this.setVal('leverage', String(s.leverage))
    this.setVal('balance', String(s.balance))
    this.setVal('limit', s.orderType === 'market' ? (this.live ? nf(this.live) : '') : s.limit === null ? '' : String(s.limit))
    this.setVal('amount', s.amount ? String(s.amount) : '')
    this.setVal('unit', s.unit)
    this.setVal('tp', s.tp === null ? '' : String(s.tp)); this.setVal('tpMode', s.tpMode)
    this.setVal('sl', s.sl === null ? '' : String(s.sl)); this.setVal('slMode', s.slMode)
    for (const k of PCT_KEYS) this.setVal(k, String(+(s[k as 'mmr'] * 100).toFixed(4)))
    this.setVal('draw', String(s.draw))
    const lim = this.q<HTMLInputElement>('[data-k="limit"]')!
    lim.readOnly = s.orderType === 'market'
    this.q('[data-x="entry-src"]')!.textContent = s.orderType === 'market' ? '· último (en vivo)' : '· límite'
    this.q('[data-x="base"]')!.textContent = this.symbol.replace(/USDT$/, '')
    this.el.querySelectorAll<HTMLElement>('[data-pick]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.pick === this.pick)))
    this.q<HTMLButtonElement>('.sim-fold')!.textContent = s.open ? 'Ocultar' : 'Mostrar'
  }

  private onInput(t: HTMLInputElement): void {
    const k = t.dataset.k
    if (!k) return
    const s = this.s
    if (k === 'draw') s.draw = t.checked
    else if (k === 'unit' || k === 'tpMode' || k === 'slMode') this.convert(k, t.value)
    else if (k === 'pct') {
      const r = simulate(this.input())
      const amt = amountFromNotional(r.maxNotional * Number(t.value) / 100, s.unit, this.entry(), s.leverage)
      s.amount = s.unit === 'qty' ? +amt.toFixed(4) : +amt.toFixed(2)
    } else if (k === 'leverage') s.leverage = Math.min(MAX_LEVERAGE, Math.max(1, Math.round(num(t.value) ?? 1)))
    else if (PCT_KEYS.has(k)) { const v = num(t.value); if (v !== null && v >= 0) s[k as 'mmr'] = v / 100 }
    else if (k === 'limit') { if (s.orderType === 'limit') s.limit = num(t.value) }
    else if (k === 'balance' || k === 'amount') s[k] = Math.max(0, num(t.value) ?? 0)
    else if (k === 'tp' || k === 'sl') s[k] = num(t.value)
    this.save(); this.fill(); this.paint()
  }

  /** Al cambiar de unidad se conserva la operación: se reexpresa el valor en la unidad nueva. */
  private convert(k: 'unit' | 'tpMode' | 'slMode', v: string): void {
    const s = this.s, e = this.entry()
    if (k === 'unit') {
      const r = simulate(this.input())
      s.unit = v as AmountUnit
      if (r.notional > 0) s.amount = +amountFromNotional(r.notional, s.unit, e, s.leverage).toFixed(s.unit === 'qty' ? 4 : 2)
      return
    }
    const kind = k === 'tpMode' ? 'tp' : 'sl'
    const o = simulate(this.input())[kind]
    s[k] = v as TargetMode
    if (!o || e <= 0) return
    const m = Math.abs(o.move)
    s[kind] = v === 'price' ? +o.price.toFixed(2) : +((v === 'roe' ? m * s.leverage : m) * 100).toFixed(2)
  }

  private onClick(t: HTMLElement): void {
    const b = t.closest<HTMLButtonElement>('button')
    if (!b) return
    const g = b.closest<HTMLElement>('[data-seg]')
    if (g) {
      const k = g.dataset.seg as 'side' | 'margin' | 'orderType'
      ;(this.s as unknown as Record<string, string>)[k] = b.dataset.v!
      if (k === 'orderType' && b.dataset.v === 'limit' && this.s.limit === null) this.s.limit = this.live
    } else if (b.dataset.pick) this.pick = this.pick === b.dataset.pick ? null : b.dataset.pick as Pick
    else if (b.dataset.act === 'fold') this.s.open = !this.s.open
    else if (b.dataset.act === 'reset') this.s = { ...DEFAULT, balance: this.s.balance, mmr: MMR[this.symbol] ?? DEFAULT.mmr }
    this.el.dataset.picking = String(this.pick !== null)
    this.save(); this.fill(); this.paint()
  }

  /** Guarda solo ante cambios del usuario (no en cada tick, para no pisar otras pestañas). */
  private save(): void {
    try { localStorage.setItem(KEY, JSON.stringify(this.s)) } catch { /* sin almacenamiento */ }
  }

  private paint(): void {
    const r = simulate(this.input())
    const used = r.maxNotional > 0 ? Math.min(100, (r.notional / r.maxNotional) * 100) : 0
    const pr = this.q<HTMLInputElement>('[data-k="pct"]')!
    if (document.activeElement !== pr) pr.value = String(Math.round(used))
    this.q('[data-x="pct"]')!.textContent = `${nf(used, 0)} % · máx ${nf(r.maxNotional, 0)} USDT`
    this.q('.sim-out')!.innerHTML = renderOut(r, this.s.leverage, this.symbol.replace(/USDT$/, ''), this.s.balance)
    const w = this.q('.sim-warn')!
    w.innerHTML = r.warnings.map((x) => `<span>⚠ ${x}</span>`).join('')
    this.drawLines(r)
  }

  private drawLines(r: SimResult): void {
    for (const l of this.lines) this.chart.series.removePriceLine(l)
    this.lines = []
    if (!this.s.draw || !r.ok) return
    const add = (price: number, color: string, title: string, style = LineStyle.Dashed): void => {
      this.lines.push(this.chart.series.createPriceLine({ price, color, title, lineWidth: 1, lineStyle: style, axisLabelVisible: true }))
    }
    if (this.s.orderType === 'limit') add(this.entry(), cssVar('--accent'), 'Entrada sim', LineStyle.Solid)
    if (r.tp) add(r.tp.price, cssVar('--up'), `TP sim ${usd(r.tp.net)}`)
    if (r.sl) add(r.sl.price, cssVar('--down'), `SL sim ${usd(r.sl.net)}`)
    if (r.liq) add(r.liq, cssVar('--warn'), 'Liq. sim (aprox.)', LineStyle.Dotted)
  }
}

function card(label: string, main: string, sub: string, t = ''): string {
  return `<div class="sim-card" data-t="${t}"><span>${label}</span><b class="num">${main}</b><small class="num">${sub}</small></div>`
}

function hit(label: string, o: Outcome | null, bal: number): string {
  if (!o) return card(label, '—', 'sin definir')
  return card(label, usd(o.net), `ROE ${pc(o.roe)} · precio ${nf(o.price)} (${pc(o.move)}) · saldo ${pc(o.net / bal)}`, tone(o.net))
}

function renderOut(r: SimResult, lev: number, base: string, bal: number): string {
  if (!r.ok) return `<p class="muted">Escribe un monto para ver la proyección a ${lev}x.</p>`
  const qd = base === 'BTC' ? 4 : 3
  return [
    card('Posición', `${nf(r.notional)} USDT`, `${nf(r.qty, qd)} ${base} · ${lev}x`),
    card('Costo (margen)', `${nf(r.margin)} USDT`, `comisión de entrada ${nf(r.entryFee)} USDT`),
    card('Liquidación aprox.', r.liq ? nf(r.liq) : '—', r.liqDist !== null ? `a ${nf(r.liqDist * 100)} % de la entrada` : 'sin precio de liquidación', 'warn'),
    hit('Si toca el take profit', r.tp, bal),
    hit('Si toca el stop loss', r.sl, bal),
    card('Riesgo : beneficio', r.rr ? `1 : ${nf(r.rr)}` : '—',
      r.tp && r.sl ? `comisiones ida y vuelta ${nf(r.tp.fees)} / ${nf(r.sl.fees)} USDT` : 'define TP y SL'),
  ].join('')
}
