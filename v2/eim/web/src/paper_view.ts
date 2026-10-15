/** Vista «Bróker simulado» (T47): cuentas de papel por perfil, estilo panel de futuros. */
import { fetchSnapshot, openStream, SYMBOLS, type StreamHandle } from './api'
import { EquityChart, PaperPriceChart, PROFILE_VAR } from './paper_chart'
import { esc, getPaper, nf, pct, pct0, postPaper, px, usd, utc } from './paper_fmt'
import { PaperJournal } from './paper_journal'
import { PaperLearn } from './paper_learn'
import { profilesTab } from './paper_profiles'
import { historyTable, ordersTable, paintMarks, positionsTable, type HistFilter } from './paper_tables'
import type { Job, PaperSummary, PaperTrade, ProfileView } from './paper_types'
import type { StreamMsg } from './types'

const TABS: [string, string][] = [['pos', 'Posiciones'], ['ord', 'Órdenes abiertas'], ['hist', 'Historial'],
  ['log', 'Bitácora'], ['learn', 'Aprendizaje'], ['prof', 'Perfiles']]
const POLL_MS = 60_000
const KEY = 'eim.paper'

const TEMPLATE = `
<header class="pp-head">
  <h2 class="pp-title">Bróker simulado</h2>
  <span class="mode" data-mode="SIMULADO">Modo: Simulado · papel, sin órdenes reales</span>
  <select data-k="symbol" aria-label="Activo">${SYMBOLS.map((s) => `<option>${s}</option>`).join('')}</select>
  <span class="pp-perp">Perpetuo USDT-M</span>
  <b class="price num" data-x="price">—</b>
  <span class="spacer"></span>
  <span class="pp-cov muted" data-x="cov"></span>
  <label class="pp-bt">Backtest <select data-k="days"><option value="7">7 días</option><option value="30" selected>30 días</option>
    <option value="60">60 días</option><option value="90">90 días</option></select></label>
  <button class="btn" data-act="bt">Ejecutar</button>
  <span class="pp-job" data-x="job"></span>
</header>
<div class="pp-cards" data-x="cards" role="tablist" aria-label="Perfiles"></div>
<div class="pp-grid">
  <section class="pp-chart"><div class="pp-chart-h"><h4 class="sh">Velas 1 h · operaciones del perfil</h4><small class="muted" data-x="src"></small></div>
    <div class="pp-pc" data-x="pc"></div></section>
  <aside class="pp-side">
    <div class="pp-acct" data-x="acct"></div>
    <h4 class="sh">Capital por perfil</h4><div class="pp-eqleg" data-x="eqleg"></div><div class="pp-eq" data-x="eq"></div>
  </aside>
</div>
<nav class="tabs pp-tabs" role="tablist">${TABS.map(([id, t]) => `<button role="tab" data-t="${id}" aria-selected="${id === 'pos'}">${t}<small data-n="${id}"></small></button>`).join('')}</nav>
<div class="pp-body" data-x="body"></div>`

export class PaperView {
  private symbol = 'BTCUSDT'
  private profile = 'moderado'
  private tab = 'pos'
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
  private journal: PaperJournal | null = null
  private learn: PaperLearn | null = null
  private bodies: Record<string, HTMLElement> = {}

  constructor(private root: HTMLElement) {
    try { const s = JSON.parse(localStorage.getItem(KEY) ?? '{}'); this.profile = s.profile ?? this.profile; this.tab = s.tab ?? this.tab } catch { /* sin almacenamiento */ }
  }

  private q<T extends HTMLElement>(k: string): T { return this.root.querySelector<T>(`[data-x="${k}"]`)! }
  private save(): void { try { localStorage.setItem(KEY, JSON.stringify({ profile: this.profile, tab: this.tab })) } catch { /* ignora */ } }

  private build(): void {
    this.root.innerHTML = TEMPLATE
    const body = this.q('body')
    for (const [id] of TABS) {
      const d = document.createElement('div'); d.className = 'pp-tab'; d.dataset.tab = id; d.hidden = id !== this.tab
      body.appendChild(d); this.bodies[id] = d
    }
    this.journal = new PaperJournal(this.bodies.log)
    this.learn = new PaperLearn(this.bodies.learn)
    this.chart = new PaperPriceChart(this.q('pc'))
    this.eq = new EquityChart(this.q('eq'), this.q('eqleg'))
    this.root.querySelector<HTMLSelectElement>('[data-k="symbol"]')!.value = this.symbol
    this.root.addEventListener('click', (e) => this.onClick(e.target as HTMLElement))
    this.root.addEventListener('change', (e) => this.onChange(e.target as HTMLSelectElement))
    this.markTabs()
  }

  toggle(show: boolean, symbol?: string): void {
    this.open = show
    this.root.hidden = !show
    document.getElementById('app')!.dataset.view = show ? 'paper' : 'desk'
    if (!show) { this.stream?.close(); this.stream = null; clearInterval(this.timer); return }
    if (!this.chart) this.build()
    if (symbol && symbol !== this.symbol && !this.v) this.symbol = symbol
    this.root.querySelector<HTMLSelectElement>('[data-k="symbol"]')!.value = this.symbol
    void this.loadAll()
    this.timer = window.setInterval(() => void this.reload(), POLL_MS)
  }

  restyle(): void { this.chart?.restyle(); this.eq?.restyle(); if (this.v) this.paintAll() }

  private async loadAll(): Promise<void> {
    this.stream?.close()
    this.price = null; this.v = null; this.trades = []
    this.q('price').textContent = '—'
    this.q('body').dataset.loading = 'true'
    try {
      const snap = await fetchSnapshot(this.symbol, '1h', 1500)
      this.chart!.pc.setData(snap.candles, snap.forming)
      const last = snap.forming ?? snap.candles[snap.candles.length - 1]
      if (last) this.setPrice(last.c)
      this.q('src').textContent = `velas: ${snap.sources.candles ?? 'almacén local'} · marcas: últimas 400`
    } catch (e) { this.q('src').textContent = `sin velas: ${(e as Error).message}` }
    this.stream = openStream(this.symbol, '1h', (m) => this.onMsg(m), () => {})
    await this.reload()
  }

  private onMsg(m: StreamMsg): void {
    if (m.type !== 'tick' || m.symbol !== this.symbol) return
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
    try {
      const [v, t] = await Promise.all([
        getPaper<PaperSummary>(`?symbol=${this.symbol}`),
        getPaper<{ trades: PaperTrade[] }>(`/trades?symbol=${this.symbol}&profile=${this.profile}&limit=2000`),
      ])
      this.v = v; this.trades = t.trades
      if (!v.profiles.some((p) => p.id === this.profile)) this.profile = v.profiles[0]?.id ?? this.profile
    } catch (e) {
      this.q('body').innerHTML = `<p class="alert bad">No se pudo cargar el bróker simulado: ${esc((e as Error).message)}</p>`
      return
    }
    delete this.q('body').dataset.loading
    this.paintAll()
  }

  private paintAll(): void {
    const v = this.v!
    const c = v.coverage
    this.q('cov').textContent = c.contexts
      ? `${c.contexts} velas analizadas (${c.origins.vivo ?? 0} en vivo · ${c.origins.backtest ?? 0} reconstruidas) · ${utc(c.from!)} → ${utc(c.to!)} UTC`
      : 'sin velas analizadas: ejecuta un backtest'
    this.paintJob(v.job)
    this.paintCards()
    this.paintAcct()
    this.eq!.set(v.profiles)
    const pv = this.prof()
    this.chart!.setTrades(this.trades, pv?.positions ?? [])
    if (pv && (!this.focus || !pv.positions.some((p) => p.id === this.focus))) this.focus = pv.positions[0]?.id ?? null
    this.chart!.setLines(pv?.positions ?? [], this.focus)
    this.paintTab()
  }

  private paintJob(j: Job): void {
    const el = this.q('job')
    const run = j.state === 'corriendo'
    this.root.querySelector<HTMLButtonElement>('[data-act="bt"]')!.textContent = run ? 'Detener' : 'Ejecutar'
    el.innerHTML = run ? `<progress max="${j.total || 1}" value="${j.done}"></progress> ${j.done}/${j.total || '…'} velas`
      : j.state === 'error' ? `<span class="down">error: ${esc(j.error)}</span>`
        : j.state === 'terminado' ? `<span class="muted">último: +${j.saved} velas</span>` : ''
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

  private paintCards(): void {
    this.q('cards').innerHTML = this.v!.profiles.map((p) => {
      const ret = p.return_pct
      return `<button class="pp-card" role="tab" data-prof="${p.id}" aria-selected="${p.id === this.profile}" style="--pc:var(${PROFILE_VAR[p.id] ?? '--accent'})">` +
        `<span class="pp-card-h"><i></i>${esc(p.name)}</span>` +
        `<b class="num">${nf(p.equity)} <small>USDT</small></b>` +
        `<span class="num ${ret > 0 ? 'up' : ret < 0 ? 'down' : ''}">${pct(ret)}</span>` +
        `<small class="muted">${p.n_closed} ops · acierto ${pct0(p.win_rate)} · PF ${p.pf === null ? '—' : nf(p.pf)} · DD máx. ${pct0(p.max_dd_pct)}</small>` +
        `<small class="muted">${p.positions.length} abiertas · ${p.orders.length} órdenes · riesgo ${nf(Number(p.params.risk_pct) * 100, 1)} % · hasta ${p.params.max_leverage}x</small></button>`
    }).join('')
  }

  private paintAcct(): void {
    const p = this.prof()
    if (!p) { this.q('acct').innerHTML = ''; return }
    const row = (k: string, v: string, cls = ''): string => `<div><span>${k}</span><b class="num ${cls}">${v}</b></div>`
    const t = (x: number): string => (x > 0 ? 'up' : x < 0 ? 'down' : '')
    this.q('acct').innerHTML = `<h4 class="sh">Cuenta · ${esc(p.name)}</h4><div class="pp-kv">` +
      row('Capital (equity)', `${nf(p.equity)} USDT`) + row('Saldo de la cartera', `${nf(p.balance)} USDT`) +
      `<div><span>PnL no realizado</span><b class="num ${t(p.upnl)}" data-x="upnl-live">${usd(p.upnl)} USDT</b></div>` +
      row('PnL realizado', `${usd(p.realized)} USDT`, t(p.realized)) +
      row('Margen en uso', `${nf(p.margin_used)} USDT`) + row('Margen reservado (órdenes)', `${nf(p.reserved)} USDT`) +
      row('Disponible', `${nf(p.available)} USDT`) + row('Capital inicial', `${nf(p.initial)} USDT`) +
      row('Comisiones · desliz.', `${nf(p.fees)} · ${nf(p.slip)}`) + row('Funding pagado (− cobrado)', `${usd(p.funding)} USDT`) +
      row('Mejor / peor', `${p.best === null ? '—' : usd(p.best)} / ${p.worst === null ? '—' : usd(p.worst)}`) +
      `</div><p class="muted pp-note">${esc(p.description)}</p>`
  }

  private markTabs(): void {
    this.root.querySelectorAll<HTMLButtonElement>('.pp-tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.t === this.tab)))
    for (const [id, el] of Object.entries(this.bodies)) el.hidden = id !== this.tab
  }

  private paintTab(): void {
    const v = this.v!, p = this.prof()
    const names = Object.fromEntries(v.strategies.map((s) => [s.id, s.name]))
    const n = (id: string, x: number | string): void => { this.root.querySelector(`[data-n="${id}"]`)!.textContent = ` ${x}` }
    n('pos', p?.positions.length ?? 0); n('ord', p?.orders.length ?? 0); n('hist', this.trades.length); n('log', p?.events_n ?? '')
    n('learn', ''); n('prof', '')
    if (!p) return
    if (this.tab === 'pos') this.bodies.pos.innerHTML = positionsTable(p.positions, names, this.symbol, this.price, this.focus)
    else if (this.tab === 'ord') this.bodies.ord.innerHTML = ordersTable(p.orders, names, this.symbol)
    else if (this.tab === 'hist') this.bodies.hist.innerHTML = historyTable(this.trades, names, this.symbol, this.hist)
    else if (this.tab === 'log') void this.journal!.show({ symbol: this.symbol, names, profiles: v.profiles }, this.profile)
    else if (this.tab === 'learn') this.learn!.show(v, this.profile)
    else this.bodies.prof.innerHTML = profilesTab(v)
  }

  private onClick(t: HTMLElement): void {
    const card = t.closest<HTMLElement>('[data-prof]')
    if (card) { this.profile = card.dataset.prof!; this.focus = null; this.save(); void this.reload(); return }
    const tab = t.closest<HTMLElement>('.pp-tabs button')
    if (tab) { this.tab = tab.dataset.t!; this.save(); this.markTabs(); this.paintTab(); return }
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
      this.paintJob(await postPaper<Job>(`/backtest?symbol=${this.symbol}&days=${days}`))
      if (this.v) this.v.job.state = 'corriendo'
    } catch (e) { this.q('job').innerHTML = `<span class="down">${esc((e as Error).message)}</span>` }
  }
}
