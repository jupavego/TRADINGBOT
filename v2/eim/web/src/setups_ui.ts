import { base } from './api'
import { esc } from './panels'
import { emptySlot, funnelHtml, nf, pc, slotCard, usd, utc, watchHtml, type Setup, type SetupsView, type Slot } from './setups_cards'
import { simulate, type Side } from './sim_calc'

/**
 * Operaciones sugeridas intradía (T50 · T122): siempre tres posiciones para BTCUSDT, ordenadas
 * por la evidencia validada (`GET /v2/setups` → `ranking`). Solo oportunidades de estrategias
 * VALIDADAS por la puerta de T49 ocupan una posición; las demás quedan vacías con su motivo y las
 * ideas en observación se listan aparte como «pendientes de confirmación». El embudo dice qué pasó
 * con cada idea de la última vela. Siempre «Sugerida · no ejecutada»: oportunidad potencial de un
 * bróker simulado, no una orden ni una garantía. Modo: Análisis.
 *
 * Actualización: al llegar reportes nuevos (`soon`) y cada minuto con la pestaña visible; solo se
 * repinta la zona cuyo contenido cambió y nunca mientras se escribe un monto.
 */

export interface ApplySetup { side: Side; entry: number; tp: number; sl: number; amount: number; leverage: number }

const KEY = 'eim.setups'
const POLL_MS = 60_000           // el bróker simulado sondea cada ~1 min
const MMR: Record<string, number> = { BTCUSDT: 0.004 }
const FEE = 0.0007 // comisión ida y vuelta supuesta (taker 0,05 % + maker 0,02 %)
const NO_GUARANTEE = 'Oportunidad potencial. Evidencia de un bróker simulado; no garantiza rentabilidad.'
const STATUS_TONE: Record<string, string> = { ok: 'ok', sin_validadas: 'warn', sin_senal: 'warn', datos_viejos: 'bad' }

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
  private sig = ''               // huella de lo pintado en el cuerpo (posiciones, embudo, pendientes)
  private deferred = false       // repintado aplazado mientras el usuario escribe un monto
  private watchOpen = false

  constructor(private el: HTMLElement, private onApply: (s: ApplySetup) => void) {
    el.innerHTML = '<div data-z="head"></div><div data-z="body"></div><div data-z="foot"></div>'
    el.addEventListener('input', (e) => this.onInput(e.target as HTMLInputElement))
    el.addEventListener('focusout', () => { if (this.deferred) window.setTimeout(() => this.paint(), 0) })
    el.addEventListener('toggle', (e) => {
      const d = e.target as HTMLElement
      if (d.classList.contains('su-watchbox')) this.watchOpen = (d as HTMLDetailsElement).open
    }, true)
    el.addEventListener('click', (e) => {
      if ((e.target as HTMLElement).closest('[data-open-paper]')) {
        document.getElementById('paper-btn')?.click(); return
      }
      const b = (e.target as HTMLElement).closest<HTMLButtonElement>('[data-apply]')
      const s = b && this.view?.setups[Number(b.dataset.apply)]
      if (s) this.onApply({ side: s.side, entry: r2(s.entry), tp: r2(s.tp), sl: r2(s.sl),
        amount: this.prefs.amounts[Number(b.dataset.apply)] ?? 0, leverage: this.prefs.leverage })
    })
    this.paintHead()
    this.paint()
    window.setInterval(() => { if (!document.hidden) void this.reload() }, POLL_MS)
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

  private z = (k: string): HTMLElement => this.el.querySelector<HTMLElement>(`[data-z="${k}"]`)!

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

  /** Posiciones de respaldo si la API aún no envía `ranking`: las validadas y el resto vacías. */
  private slots(v: SetupsView): Slot[] {
    if (v.ranking?.length) return v.ranking
    return [0, 1, 2].map((k) => (k < v.setups.length
      ? { rank: k + 1, state: 'validada', index: k }
      : { rank: k + 1, state: 'vacia', index: null, message: v.message }) as Slot)
  }

  private statusLine(v: SetupsView): string {
    const n = v.setups.length
    const head = n >= 3 ? 'Tres oportunidades validadas, de mayor a menor evidencia'
      : n ? `Solo ${n} de 3 posiciones con oportunidad validada` : 'Sin operaciones validadas para sugerir'
    return `<p class="su-status" data-tone="${STATUS_TONE[v.status] ?? 'warn'}"><b>${head}.</b> ${esc(v.message)}` +
      (n ? '' : ' <button type="button" class="obs-link" data-open-paper>Ver la validación en «Bróker simulado»</button>') + '</p>'
  }

  private body(v: SetupsView): string {
    const slots = this.slots(v)
    const rule = slots.find((s) => s.order)?.order?.rule
    return this.statusLine(v) + funnelHtml(v.funnel) +
      `<div class="su-grid su-slots">${slots.map((sl) => (sl.state === 'validada' && sl.index !== null && v.setups[sl.index]
        ? slotCard(sl, v.setups[sl.index], v.criteria_version, String(this.prefs.amounts[sl.index] ?? ''), this.outcome(v.setups[sl.index], sl.index))
        : emptySlot(sl))).join('')}</div>` +
      `<p class="muted su-rule">Orden de las posiciones: ${esc(rule ?? 'límite inferior del IC95 % del R medio fuera de muestra (mayor primero)')}. ` +
      'Es una puntuación de evidencia del sistema; el acierto mostrado es una frecuencia observada en simulación, no una probabilidad calibrada.</p>' +
      watchHtml(v, this.watchOpen)
  }

  private paintHead(): void {
    this.z('head').innerHTML = '<div class="su-head"><h3 class="sh">Operaciones sugeridas intradía</h3>' +
      '<span class="su-sym">BTCUSDT</span><span class="sim">Análisis · no es una orden</span>' +
      '<span class="muted">top 3 · solo estrategias validadas · marcos 15 m y 1 h · tenencia ≤ 36 h</span>' +
      '<span class="spacer"></span>' +
      `<label class="su-lev">Apalancamiento <input data-k="lev" type="number" min="1" max="125" class="num" value="${this.prefs.leverage}" />x</label></div>`
  }

  private paint(): void {
    const v = this.view
    const active = document.activeElement
    if (active instanceof HTMLInputElement && this.z('body').contains(active)) { this.deferred = true; return }
    this.deferred = false
    const body = this.error ? `<p class="muted">No se pudieron cargar las sugerencias: ${esc(this.error)}</p>`
      : !v ? '<p class="muted">Cargando sugerencias validadas…</p>' : this.body(v)
    // la hora de la consulta cambia siempre: no entra en la huella del cuerpo
    if (body !== this.sig) { this.z('body').innerHTML = body; this.sig = body }
    this.z('foot').innerHTML = v
      ? `<p class="muted su-foot">${NO_GUARANTEE} ` +
        (v.price !== null ? `Precio ${nf(v.price)} · ` : '') +
        (v.asof ? `bróker al ${utc(v.asof)} · ` : '') +
        (v.verdicts_asof ? `veredictos al ${utc(v.verdicts_asof)} (${esc(v.criteria_version)}) · ` : '') +
        `fuente ${esc(v.source)} · comisión ida y vuelta supuesta ${nf(FEE * 100, 2)} % · consultado ${utc(v.now).slice(11)}.</p>`
      : `<p class="muted su-foot">${NO_GUARANTEE}</p>`
  }
}

const r2 = (x: number): number => Math.round(x * 100) / 100
