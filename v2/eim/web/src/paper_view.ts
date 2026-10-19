/** Vista «Bróker simulado» (T47/T48): cuentas de papel por perfil en 15 m, 1 h y 4 h. */
import { fetchSnapshot, openStream, symbolPicker, type StreamHandle } from './api'
import { PaperArb } from './paper_arb'
import { balanceView } from './paper_balance'
import { EquityChart, PaperPriceChart } from './paper_chart'
import { esc, getPaper, PaperError, postPaper, px, usd } from './paper_fmt'
import { acctHtml, cardsHtml, covText, jobHtml, liveStrip } from './paper_head'
import { PaperJournal } from './paper_journal'
import { PaperLearn } from './paper_learn'
import { PaperLive } from './paper_live'
import { profilesTab } from './paper_profiles'
import { historyTable, ordersTable, paintMarks, positionsTable, type HistFilter } from './paper_tables'
import type { Job, PaperSummary, PaperTrade, ProfileView } from './paper_types'
import type { StreamMsg } from './types'

const TABS: [string, string][] = [['live', 'Señales en vivo'], ['pos', 'Posiciones'], ['ord', 'Órdenes abiertas'], ['hist', 'Historial'],
  ['log', 'Bitácora'], ['learn', 'Aprendizaje'], ['prof', 'Perfiles'], ['arb', 'Arbitraje']]
const POLL_MS = 60_000
const RETRY_MS = 8_000            // vista aún calculándose (503) o rehaciéndose: vuelve a pedirla pronto
const LIVE_MS = 15_000            // repinta la franja «en vivo» (hace X s)
const CHART_TFS = ['15m', '1h', '4h']
const KEY = 'eim.paper.v2'          // v2: la pestaña inicial pasa a «Señales en vivo» (T48c)

const TEMPLATE = `
<header class="pp-head">
  <h2 class="pp-title">Bróker simulado</h2>
  <span class="mode" data-mode="SIMULADO">Modo: Simulado · papel, sin órdenes reales</span>
  ${symbolPicker('data-k="symbol"')}
  <span class="pp-perp">Perpetuo USDT-M</span>
  <b class="price num" data-x="price">—</b>
  <span class="spacer"></span>
  <span class="pp-cov muted" data-x="cov"></span>
  <label class="pp-bt" title="Reconstruye las decisiones de días pasados para que el aprendizaje tenga historial; el servicio en vivo no lo necesita">Historial <select data-k="days"><option value="7">7 días</option><option value="30" selected>30 días</option>
    <option value="60">60 días</option><option value="90">90 días</option></select>
    <select data-k="bttf" aria-label="Temporalidades del backtest"><option value="">15m · 1h · 4h</option>
    <option>15m</option><option>1h</option><option>4h</option></select></label>
  <button class="btn" data-act="bt">Reconstruir historial (backtest)</button>
  <span class="pp-job" data-x="job"></span>
</header>
<div class="pp-livebar" data-x="live" aria-live="polite"></div>
<section class="pp-balance" data-x="bal" aria-label="Balance de operaciones ganadas y perdidas"></section>
<div class="pp-cards" data-x="cards" role="tablist" aria-label="Perfiles"></div>
<div class="pp-grid">
  <section class="pp-chart"><div class="pp-chart-h"><h4 class="sh">Velas · operaciones del perfil</h4>
    <div class="seg" data-x="ctf" role="group" aria-label="Temporalidad del gráfico">${CHART_TFS.map((t) => `<button type="button" data-ctf="${t}">${t}</button>`).join('')}</div>
    <small class="muted" data-x="src"></small></div>
    <div class="pp-pc" data-x="pc"></div></section>
  <aside class="pp-side">
    <div class="pp-acct" data-x="acct"></div>
    <h4 class="sh">Capital por perfil</h4><div class="pp-eqleg" data-x="eqleg"></div><div class="pp-eq" data-x="eq"></div>
  </aside>
</div>
<p class="alert" data-x="msg" role="status" hidden></p>
<nav class="tabs pp-tabs" role="tablist">${TABS.map(([id, t]) => `<button role="tab" data-t="${id}" aria-selected="${id === 'live'}">${t}<small data-n="${id}"></small></button>`).join('')}</nav>
<div class="pp-body" data-x="body"></div>`

export class PaperView {
  private symbol = 'BTCUSDT'
  private profile = 'moderado'
  private tab = 'live'
  private bal = 'todo'
  private ctf = '1h'
  private liveTimer: number | undefined
  private v: PaperSummary | null = null
  private trades: PaperTrade[] = []
  private price: number | null = null
  private focus: string | null = null
  private hist: HistFilter = { strategy: '', result: 'all', limit: 100 }
  private open = false
  private chart: PaperPriceChart | null = null
  private eq: EquityChart | null = null
  private stream: StreamHandle | null = null
  private timer: number | undefined
  private retry: number | undefined
  private journal: PaperJournal | null = null
  private learn: PaperLearn | null = null
  private live: PaperLive | null = null
  private arb: PaperArb | null = null
  private bodies: Record<string, HTMLElement> = {}

  constructor(private root: HTMLElement) {
    try { const s = JSON.parse(localStorage.getItem(KEY) ?? '{}'); this.profile = s.profile ?? this.profile; this.tab = s.tab ?? this.tab; this.bal = s.bal ?? this.bal; this.ctf = s.ctf ?? this.ctf } catch { /* sin almacenamiento */ }
  }

  private q<T extends HTMLElement>(k: string): T { return this.root.querySelector<T>(`[data-x="${k}"]`)! }
  private save(): void { try { localStorage.setItem(KEY, JSON.stringify({ profile: this.profile, tab: this.tab, bal: this.bal, ctf: this.ctf })) } catch { /* ignora */ } }

  private build(): void {
    this.root.innerHTML = TEMPLATE
    const body = this.q('body')
    for (const [id] of TABS) {
      const d = document.createElement('div'); d.className = 'pp-tab'; d.dataset.tab = id; d.hidden = id !== this.tab
      body.appendChild(d); this.bodies[id] = d
    }
    this.journal = new PaperJournal(this.bodies.log)
    this.learn = new PaperLearn(this.bodies.learn)
    this.live = new PaperLive(this.bodies.live)
    this.arb = new PaperArb(this.bodies.arb)
    this.chart = new PaperPriceChart(this.q('pc'))
    this.eq = new EquityChart(this.q('eq'), this.q('eqleg'))
    this.pickSymbol()
    this.root.addEventListener('click', (e) => this.onClick(e.target as HTMLElement))
    this.root.addEventListener('change', (e) => this.onChange(e.target as HTMLSelectElement))
    this.markTabs()
  }

  toggle(show: boolean, symbol?: string): void {
    this.open = show
    this.root.hidden = !show
    document.getElementById('app')!.dataset.view = show ? 'paper' : 'desk'
    if (!show) { this.stream?.close(); this.stream = null; clearInterval(this.timer); clearInterval(this.liveTimer); clearTimeout(this.retry); return }
    if (!this.chart) this.build()
    if (symbol && symbol !== this.symbol && !this.v) this.symbol = symbol
    this.pickSymbol()
    void this.loadAll()
    this.timer = window.setInterval(() => void this.reload(), POLL_MS)
    this.liveTimer = window.setInterval(() => { if (this.v) this.q('live').innerHTML = liveStrip(this.v) }, LIVE_MS)
  }

  private pickSymbol(): void {
    const sel = this.root.querySelector<HTMLSelectElement>('select[data-k="symbol"]')
    if (sel) sel.value = this.symbol
  }

  restyle(): void { this.chart?.restyle(); this.eq?.restyle(); if (this.v) this.paintAll() }

  private async loadAll(): Promise<void> {
    this.price = null; this.v = null; this.trades = []
    this.q('price').textContent = '—'
    this.q('body').dataset.loading = 'true'
    await this.loadChart()
    await this.reload()
  }

  /** Velas y flujo en vivo del marco del gráfico; no toca el resumen (se puede cambiar sin recargar). */
  private async loadChart(): Promise<void> {
    this.stream?.close()
    try {
      this.markCtf()
      const snap = await fetchSnapshot(this.symbol, this.ctf, 1500)
      this.chart!.pc.setData(snap.candles, snap.forming)
      const last = snap.forming ?? snap.candles[snap.candles.length - 1]
      if (last) this.setPrice(last.c)
      this.q('src').textContent = `velas: ${snap.sources.candles ?? 'almacén local'} · marcas: últimas 400`
    } catch (e) { this.q('src').textContent = `sin velas: ${(e as Error).message}` }
    this.stream = openStream(this.symbol, this.ctf, (m) => this.onMsg(m), () => {})
    if (this.v) this.paintChart()
  }

  private onMsg(m: StreamMsg): void {
    if (m.type !== 'tick' || m.symbol !== this.symbol || m.timeframe !== this.ctf) return
    this.chart?.pc.update(m.candle)
    this.setPrice(m.candle.c)
  }

  private setPrice(p: number): void {
    const el = this.q('price')
    if (this.price !== null && p !== this.price) el.dataset.dir = p > this.price ? 'up' : 'down'
    this.price = p
    el.textContent = px(p)
    const pv = this.prof()
    if (!pv) return
    const u = paintMarks(this.bodies.pos, pv.positions, p)
    const live = this.root.querySelector<HTMLElement>('[data-x="upnl-live"]')
    if (live) { live.textContent = `${usd(u)} USDT`; live.className = `num ${u > 0 ? 'up' : u < 0 ? 'down' : ''}` }
  }

  private prof(): ProfileView | undefined { return this.v?.profiles.find((p) => p.id === this.profile) }

  async reload(): Promise<void> {
    if (!this.open) return
    clearTimeout(this.retry)
    const msg = this.q('msg')
    try {
      const [v, t] = await Promise.all([
        getPaper<PaperSummary>(`?symbol=${this.symbol}`),
        getPaper<{ trades: PaperTrade[] }>(`/trades?symbol=${this.symbol}&profile=${this.profile}&limit=2000`),
      ])
      this.v = v; this.trades = t.trades
      if (!v.profiles.some((p) => p.id === this.profile)) this.profile = v.profiles[0]?.id ?? this.profile
    } catch (e) {
      // Aviso en su propia franja (reemplazar el cuerpo borraba las pestañas); reintenta pronto
      const busy = e instanceof PaperError && e.status === 503
      this.retry = window.setTimeout(() => void this.reload(), RETRY_MS)
      msg.className = busy ? 'alert' : 'alert bad'
      msg.textContent = busy ? (e as Error).message : `No se pudo cargar el bróker simulado: ${(e as Error).message}`
      msg.hidden = false
      return
    }
    msg.hidden = true
    delete this.q('body').dataset.loading
    this.paintAll()
    if (this.v?.view?.refreshing) this.retry = window.setTimeout(() => void this.reload(), RETRY_MS)
  }

  private paintAll(): void {
    const v = this.v!
    this.q('cov').textContent = covText(v)
    this.q('live').innerHTML = liveStrip(v)
    this.paintJob(v.job)
    this.q('bal').innerHTML = balanceView(v, this.bal)
    this.q('cards').innerHTML = cardsHtml(v, this.profile)
    const pv = this.prof()
    this.q('acct').innerHTML = pv ? acctHtml(pv) : ''
    this.eq!.set(v.profiles)
    this.paintChart()
    this.paintTab()
  }

  /** Marcas de cierres del marco del gráfico; las posiciones abiertas se dibujan de TODOS los marcos
   (rotuladas con el suyo): el precio es el mismo y así ninguna queda fuera de la vista. */
  private paintChart(): void {
    const pv = this.prof()
    const open = pv?.positions ?? []
    this.chart!.setTrades(this.trades.filter((t) => t.timeframe === this.ctf), open)
    if (!this.focus || !open.some((p) => p.id === this.focus)) this.focus = open[0]?.id ?? null
    this.chart!.setLines(open, this.focus)
  }

  private markCtf(): void {
    this.q('ctf').querySelectorAll<HTMLButtonElement>('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.ctf === this.ctf)))
  }

  private paintJob(j: Job): void {
    const run = j.state === 'corriendo'
    this.root.querySelector<HTMLButtonElement>('[data-act="bt"]')!.textContent = run ? 'Detener' : 'Reconstruir historial (backtest)'
    this.q('job').innerHTML = jobHtml(j)
    if (run) { clearTimeout(this.jobTimer); this.jobTimer = window.setTimeout(() => void this.pollJob(), 3000) }
  }

  private jobTimer: number | undefined
  private async pollJob(): Promise<void> {
    try {
      const s = await getPaper<{ job: Job }>('/status')
      if (s.job.state === 'corriendo') { this.paintJob(s.job); return }
      await this.reload()
    } catch { /* reintenta en el próximo ciclo */ }
  }

  private markTabs(): void {
    this.root.querySelectorAll<HTMLButtonElement>('.pp-tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.t === this.tab)))
    for (const [id, el] of Object.entries(this.bodies)) el.hidden = id !== this.tab
  }

  private paintTab(): void {
    if (!this.v) return
    const v = this.v, p = this.prof()
    const names = Object.fromEntries(v.strategies.map((s) => [s.id, s.name]))
    const n = (id: string, x: number | string): void => { this.root.querySelector(`[data-n="${id}"]`)!.textContent = ` ${x}` }
    n('pos', p?.positions.length ?? 0); n('ord', p ? p.orders.length + 2 * p.positions.length : 0); n('hist', this.trades.length); n('log', p?.events_n ?? '')
    n('learn', ''); n('prof', ''); n('live', ''); n('arb', '')
    if (this.tab === 'arb') { void this.arb!.show(); return }   // T45: no depende del perfil
    if (!p) return
    if (this.tab === 'live') void this.live!.show({ symbol: this.symbol, names, profiles: v.profiles })
    else if (this.tab === 'pos') this.bodies.pos.innerHTML = positionsTable(p.positions, names, this.symbol, this.price, this.focus)
    else if (this.tab === 'ord') this.bodies.ord.innerHTML = ordersTable(p.orders, names, this.symbol, p.positions, this.price)
    else if (this.tab === 'hist') this.bodies.hist.innerHTML = historyTable(this.trades, names, this.symbol, this.hist)
    else if (this.tab === 'log') void this.journal!.show({ symbol: this.symbol, names, profiles: v.profiles }, this.profile)
    else if (this.tab === 'learn') this.learn!.show(v, this.profile)
    else this.bodies.prof.innerHTML = profilesTab(v)
  }

  private onClick(t: HTMLElement): void {
    const bal = t.closest<HTMLElement>('[data-bal]')
    if (bal && this.v) { this.bal = bal.dataset.bal!; this.save(); this.q('bal').innerHTML = balanceView(this.v, this.bal); return }
    const card = t.closest<HTMLElement>('[data-prof]')
    if (card) { this.profile = card.dataset.prof!; this.focus = null; this.save(); void this.reload(); return }
    const tab = t.closest<HTMLElement>('.pp-tabs button')
    if (tab) { this.tab = tab.dataset.t!; this.save(); this.markTabs(); this.paintTab(); return }
    const ctf = t.closest<HTMLElement>('[data-ctf]')
    if (ctf) { this.ctf = ctf.dataset.ctf!; this.focus = null; this.save(); void this.loadChart(); return }
    const pos = t.closest<HTMLElement>('tr[data-pos]')
    if (pos) {
      this.focus = pos.dataset.pos!
      this.chart!.setLines(this.prof()?.positions ?? [], this.focus)
      this.bodies.pos.querySelectorAll<HTMLElement>('tr[data-pos]').forEach((r) => { r.dataset.focus = String(r.dataset.pos === this.focus) })
      return
    }
    if (t.closest('[data-more="hist"]')) { this.hist.limit += 200; this.paintTab(); return }
    if (t.closest('[data-act="bt"]')) void this.backtest()
  }

  private onChange(s: HTMLSelectElement): void {
    if (s.dataset.k === 'symbol') { this.symbol = s.value; void this.loadAll(); return }
    if (s.dataset.hf) {
      (this.hist as unknown as Record<string, string>)[s.dataset.hf] = s.value
      this.hist.limit = 100; this.paintTab()
    }
  }

  private async backtest(): Promise<void> {
    const job = this.v?.job
    try {
      if (job?.state === 'corriendo') { this.paintJob(await postPaper<Job>('/backtest/stop')); return }
      const days = this.root.querySelector<HTMLSelectElement>('[data-k="days"]')!.value
      const tf = this.root.querySelector<HTMLSelectElement>('[data-k="bttf"]')!.value
      this.paintJob(await postPaper<Job>(`/backtest?symbol=${this.symbol}&days=${days}${tf ? `&tf=${tf}` : ''}`))
      if (this.v) this.v.job.state = 'corriendo'
    } catch (e) { this.q('job').innerHTML = `<span class="down">${esc((e as Error).message)}</span>` }
  }
}
