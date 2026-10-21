/** Bitácora categorizada del bróker simulado: de la orden al cierre, con rechazos y aprendizaje. */
import { CAT_LABEL, CAUSE, day, esc, getPaper, hm, nf, px, rr, side, tone, usd } from './paper_fmt'
import type { PaperEvent } from './paper_types'

const CATS = ['orden', 'llenada', 'tp', 'be', 'sl', 'tiempo', 'cancelada', 'rechazada', 'aprendizaje', 'violacion']
const DEFAULT = new Set(CATS.filter((c) => c !== 'rechazada'))
const PAGE = 150
const STATE: Record<string, string> = {
  observacion: 'en observación', activa: 'activa', reforzada: 'reforzada', reducida: 'reducida', pausa: 'en pausa',
}

interface Ctx { symbol: string; names: Record<string, string>; profiles: { id: string; name: string }[] }

export class PaperJournal {
  private cats = new Set(DEFAULT)
  private profile = ''
  private strategy = ''
  private tf = ''
  private events: PaperEvent[] = []
  private counts: Record<string, number> = {}
  private total = 0
  private ctx: Ctx = { symbol: 'BTCUSDT', names: {}, profiles: [] }
  private abort: AbortController | null = null

  constructor(private el: HTMLElement) {
    el.addEventListener('click', (e) => {
      const b = (e.target as HTMLElement).closest<HTMLButtonElement>('button')
      if (!b) return
      if (b.dataset.cat) {
        if (this.cats.has(b.dataset.cat)) this.cats.delete(b.dataset.cat); else this.cats.add(b.dataset.cat)
        void this.load(false)
      } else if (b.dataset.more) void this.load(true)
    })
    el.addEventListener('change', (e) => {
      const s = e.target as HTMLSelectElement
      if (s.dataset.jf === 'profile') this.profile = s.value
      else if (s.dataset.jf === 'strategy') this.strategy = s.value
      else if (s.dataset.jf === 'tf') this.tf = s.value
      else return
      void this.load(false)
    })
  }

  /** Muestra la bitácora del perfil elegido arriba (se puede cambiar a «todos»). */
  async show(ctx: Ctx, profile: string): Promise<void> {
    this.ctx = ctx
    this.profile = profile
    await this.load(false)
  }

  private async load(more: boolean): Promise<void> {
    this.abort?.abort(); this.abort = new AbortController()
    if (!this.cats.size) { this.events = []; this.total = 0; this.paint(); return }
    const before = more && this.events.length ? `&before=${this.events[this.events.length - 1].t}` : ''
    const q = `/journal?symbol=${this.ctx.symbol}&limit=${PAGE}&cat=${[...this.cats].join(',')}` +
      (this.profile ? `&profile=${this.profile}` : '') + (this.strategy ? `&strategy=${this.strategy}` : '') + (this.tf ? `&tf=${this.tf}` : '') + before
    try {
      const r = await getPaper<{ counts: Record<string, number>; total: number; events: PaperEvent[] }>(q, this.abort.signal)
      this.events = more ? [...this.events, ...r.events] : r.events
      this.counts = r.counts
      this.total = more ? this.total : r.total
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      this.el.innerHTML = `<p class="alert bad">No se pudo cargar la bitácora: ${esc((e as Error).message)}</p>`
      return
    }
    this.paint()
  }

  private line(e: PaperEvent): string {
    const n = (this.ctx.names[e.sid] ?? e.strategy).split(' · ')[0]
    const prof = this.ctx.profiles.find((p) => p.id === e.profile)?.name ?? e.profile
    let detail = esc(e.text)
    if (e.cat === 'orden') {
      detail = `${e.kind === 'limit' ? 'Orden límite' : 'Orden a mercado'} <b>${side(e.side)}</b> ${nf(e.qty ?? 0, 4)} @ ${px(e.price ?? 0)} · ` +
        `${e.tp ? `TP ${px(e.tp)}` : 'sin TP'} · SL ${px(e.sl ?? 0)} · ${e.leverage}x · riesgo ${nf(e.risk_usd ?? 0)} USDT (peso ${nf(e.weight ?? 1)})`
    } else if (e.cat === 'llenada') {
      detail = `Llenada a ${px(e.price ?? 0)} · liquidación aprox. ${px(e.liq ?? 0)}`
    } else if (['tp', 'be', 'sl', 'tiempo'].includes(e.cat)) {
      detail = `Cierre a ${px(e.price ?? 0)} · <b class="${tone(e.pnl)}">${usd(e.pnl ?? 0)} USDT</b> (${rr(e.r ?? null)}) · capital ${nf(e.equity ?? 0)}` +
        (e.cause ? ` · <span class="pp-cause">pérdida: ${esc(CAUSE[e.cause] ?? e.cause)}</span>` : '')
    } else if (e.cat === 'aprendizaje' && e.context) {
      const [reg, lado] = e.context.split('|')
      detail = `Aprendizaje por contexto: <b>${esc(e.text)}</b> (${esc(reg)}, ${esc(lado)}) · expectativa ${rr(e.m ?? 0)} con ${e.n} operaciones en ese contexto`
    } else if (e.cat === 'aprendizaje') {
      const [a, b] = e.text.split(' → ')
      detail = `Retroalimentación: pasa de <i>${STATE[a] ?? a}</i> a <b>${STATE[b] ?? b}</b> · expectativa ${rr(e.m ?? 0)} con ${e.n} operaciones · peso ${nf(e.weight ?? 0)}`
    } else if (e.cat === 'rechazada') detail = `No se opera: ${esc(e.text)}`
    else if (e.cat === 'cancelada') detail = `Orden cancelada: ${esc(e.text)}`
    const why = e.why?.length ? `<small class="muted">${esc(e.why.join(' · '))}</small>` : ''
    return `<li data-cat="${e.cat}"><time class="num">${hm(e.t)}</time><span class="pp-chip" data-cat="${e.cat}">${CAT_LABEL[e.cat]}</span>` +
      `<span class="pp-prof" data-p="${esc(e.profile)}">${esc(prof)}</span><span class="pp-ev"><b>${esc(n)}</b> <span class="pp-tfb">${esc(e.timeframe)}</span>` +
      `${e.origin === 'vivo' ? ' <span class="pp-live">vivo</span>' : ''} · ${detail}${why}</span></li>`
  }

  private paint(): void {
    const chips = CATS.map((c) => `<button type="button" class="pp-chip" data-cat="${c}" aria-pressed="${this.cats.has(c)}">` +
      `${CAT_LABEL[c]} <small class="num">${this.counts[c] ?? 0}</small></button>`).join('')
    const profs = `<select data-jf="profile"><option value="">Todos los perfiles</option>` +
      this.ctx.profiles.map((p) => `<option value="${p.id}"${p.id === this.profile ? ' selected' : ''}>${esc(p.name)}</option>`).join('') + '</select>'
    const tfs = `<select data-jf="tf"><option value="">15m · 1h · 4h</option>` +
      ['15m', '1h', '4h'].map((t) => `<option${t === this.tf ? ' selected' : ''}>${t}</option>`).join('') + '</select>'
    const strats = `<select data-jf="strategy"><option value="">Todas las estrategias</option>` +
      Object.entries(this.ctx.names).filter(([id]) => !this.tf || id.endsWith(`@${this.tf}`)).sort((a, b) => a[1].localeCompare(b[1]))
        .map(([id, n]) => `<option value="${id}"${id === this.strategy ? ' selected' : ''}>${esc(n)}</option>`).join('') + '</select>'
    let body = ''
    let cur = ''
    for (const e of this.events) {
      const d = day(e.t)
      if (d !== cur) { body += `${cur ? '</ul>' : ''}<h5 class="pp-day">${d}</h5><ul class="pp-log">`; cur = d }
      body += this.line(e)
    }
    if (cur) body += '</ul>'
    const more = this.events.length < this.total ? `<button class="btn" data-more="1">Cargar ${Math.min(PAGE, this.total - this.events.length)} más (de ${this.total})</button>` : ''
    this.el.innerHTML = `<div class="pp-filters">${profs}${tfs}${strats}</div><div class="pp-chips">${chips}</div>` +
      (body || '<p class="muted">Sin eventos con estos filtros.</p>') + more +
      '<p class="muted pp-note">Horas en UTC. «Rechazada» = la idea existió pero el perfil no la tomó (filtros, cupo, margen o pausa por retroalimentación).</p>'
  }
}
