import { fetchArbitrage } from './api'
import { ArbExecPanel } from './arb_exec_ui'
import type { ArbMetrics, ArbPayload, ArbRow } from './arb_types'
import { alertsBox, basisTable, countdown, fundingTable, rowsTable, scansList, STRATEGY, utc } from './arb_view'
import { esc } from './panels'

type Show = 'all' | 'selected' | 'rejected'

/** Pestaña «Arbitraje» (T39): escáner de oportunidades netas de Binance (modo Análisis) y, arriba,
 * la ejecución automática en testnet (T45, modo Testnet), que el repintado del escáner conserva. */
export class ArbPanel {
  private readonly exec = new ArbExecPanel()
  private data: ArbPayload | null = null
  private err = ''
  private skew = 0 // hora del servidor − hora local (vigencias y edad)
  private open = new Set<string>()
  private f = { strategy: 'all', asset: 'all', show: 'all' as Show, minBps: '' }
  private seenAlerts = new Set<string>()

  constructor(private readonly el: HTMLElement, private readonly tab: HTMLElement | null,
    private readonly onData?: (p: ArbPayload) => void) {
    el.addEventListener('click', (e) => {
      const t = e.target as HTMLElement
      if (t.closest('#arb-reload')) { void this.reload(); return }
      const row = t.closest<HTMLElement>('tr.arb-row')
      if (row?.dataset.id) {
        const id = row.dataset.id
        if (this.open.has(id)) this.open.delete(id)
        else this.open.add(id)
        this.renderTable()
      }
    })
    el.addEventListener('input', (e) => {
      const t = e.target as HTMLInputElement | HTMLSelectElement
      if (!t.dataset.f) return
      ;(this.f as Record<string, string>)[t.dataset.f] = t.value
      this.renderTable()
    })
    window.setInterval(() => this.tick(), 1000)
  }

  private now(): number { return Date.now() + this.skew }

  async reload(): Promise<void> {
    try { this.push(await fetchArbitrage()); this.err = '' }
    catch (e) { this.err = `No se pudo consultar el escáner: ${(e as Error).message}`; this.render() }
  }

  /** Respuesta REST o mensaje WS `arbitrage`. */
  push(p: ArbPayload): void {
    this.data = p
    this.skew = p.now - Date.now()
    this.onData?.(p) // satélite del río de decisión
    this.paintTab()
    this.render()
  }

  private paintTab(): void {
    if (!this.tab || !this.data) return
    const active = this.data.alerts.filter((a) => a.active)
    this.tab.textContent = active.length ? `Arbitraje (${active.length})` : 'Arbitraje'
    this.tab.dataset.alert = String(active.length > 0)
    const fresh = active.filter((a) => !this.seenAlerts.has(a.key + a.since))
    fresh.forEach((a) => this.seenAlerts.add(a.key + a.since))
    if (fresh.length) {
      this.tab.classList.remove('flash'); void this.tab.offsetWidth; this.tab.classList.add('flash')
    }
  }

  private metrics(): ArbMetrics | null {
    const m = this.data?.report.metrics as unknown as ArbMetrics | undefined
    return m && 'funding' in m ? m : null
  }

  private filtered(): ArbRow[] {
    const { strategy, asset, show, minBps } = this.f
    const min = minBps === '' ? null : Number(minBps)
    return (this.data?.opportunities ?? []).filter((r) =>
      (strategy === 'all' || r.strategy === strategy) &&
      (asset === 'all' || r.asset === asset || (asset === 'cycles' && r.strategy === 'triangular')) &&
      (show === 'all' || (show === 'selected') === r.selected) &&
      (min == null || Number.isNaN(min) || r.net_bps >= min))
  }

  private header(): string {
    const d = this.data, m = this.metrics(), rep = d?.report
    const age = d?.scan_asof != null ? `<span data-asof="${d.scan_asof}">${this.ageText(d.scan_asof)}</span>` : 'sin escaneo'
    const conf = rep ? `${Math.round(rep.confidence * 100)} %` : '—'
    const cm = m?.cost_model
    return `<div class="scen-bar arb-head"><b>Arbitraje Binance</b>` +
      `<span class="mode" data-mode="ANALISIS">Modo: Análisis</span>` +
      `<span class="arb-label">${esc(d?.label ?? 'neto estimado, no garantizado')}</span>` +
      `<span class="muted">Fotografía ${d?.scan_asof != null ? utc(d.scan_asof) : '—'} (${age}) · confianza ${conf}` +
      `${m ? ` · ${m.quality.books} libros · fuente ${esc(m.sources.arb)}` : ''}` +
      `${cm ? ` · comisiones VIP ${cm.spot_vip}/${cm.futures_vip} ${cm.role}${cm.bnb_discount ? ' con BNB' : ''}` : ''}</span>` +
      `<button id="arb-reload">Actualizar</button></div>`
  }

  private ageText(t: number): string { return `hace ${Math.max(0, Math.round((this.now() - t) / 1000))} s` }

  private filters(): string {
    const rows = this.data?.opportunities ?? []
    const assets = [...new Set(rows.filter((r) => r.strategy !== 'triangular').map((r) => r.asset))].sort()
    const opt = (v: string, l: string, cur: string): string =>
      `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(l)}</option>`
    const f = this.f
    return `<div class="scen-bar arb-filters">` +
      `<label>Estrategia <select data-f="strategy">${opt('all', 'Todas', f.strategy)}` +
      Object.entries(STRATEGY).map(([k, l]) => opt(k, l, f.strategy)).join('') + '</select></label>' +
      `<label>Activo <select data-f="asset">${opt('all', 'Todos', f.asset)}` +
      assets.map((a) => opt(a, a, f.asset)).join('') + opt('cycles', 'Ciclos triangulares', f.asset) + '</select></label>' +
      `<label>Estado <select data-f="show">${opt('all', 'Todas', f.show)}${opt('selected', 'Seleccionadas', f.show)}` +
      `${opt('rejected', 'Descartadas', f.show)}</select></label>` +
      `<label>Neto mín. (pb) <input data-f="minBps" type="number" step="1" value="${esc(f.minBps)}" placeholder="—"></label>` +
      `<span id="arb-count" class="muted"></span></div>`
  }

  render(): void {
    const d = this.data, m = this.metrics()
    const err = this.err ? `<p class="scen-warn">${esc(this.err)}</p>` : ''
    if (!d) {
      this.el.innerHTML = '<div id="arb-exec-slot"></div>' + this.header() + err + '<p class="muted">Consultando el escáner…</p>'
      this.mountExec()
      return
    }
    const rep = d.report
    const stale = d.stale && d.scan_asof != null
      ? `<p class="scen-warn">Fotografía vieja (${this.ageText(d.scan_asof)}): las cifras ya no son operables.</p>` : ''
    const warn = rep.status !== 'ok' && rep.warnings.length
      ? `<details class="arb-warn" data-k="warn"><summary>${rep.status === 'no_data' ? 'Sin datos' : 'Degradado'}: ${esc(rep.warnings[0])}</summary>` +
        `<ul>${rep.warnings.slice(1).map((w) => `<li>${esc(w)}</li>`).join('')}</ul></details>` : ''
    const notional = m ? m.notional_usd.toLocaleString('es-CO') : '—'
    // un mensaje WS nuevo no debe cerrar lo desplegado ni quitar el foco del filtro
    const opened = new Set([...this.el.querySelectorAll<HTMLDetailsElement>('details[open][data-k]')].map((x) => x.dataset.k))
    const focus = (document.activeElement as HTMLElement | null)?.dataset?.f
    this.el.innerHTML = '<div id="arb-exec-slot"></div>' + this.header() + err + stale + warn +
      alertsBox(d.alerts, d.alert_params) +
      (m ? `<p class="arb-ev">${rep.evidence.slice(1).map((e) => esc(e)).join('<br>')}</p>` : '') +
      this.filters() + '<div id="arb-rows"></div>' +
      (m ? `<div class="arb-grid"><section><h4>Funding por perpetuo</h4>${fundingTable(m.funding, this.now())}</section>` +
        `<section><h4>Base anualizada</h4>${basisTable(m.basis)}</section></div>` +
        `<h4>Estrategias</h4><div class="arb-scans">${scansList(m.scans)}</div>` : '') +
      `<p class="muted arb-foot">Importes en USD para ${notional} USD de nocional por oportunidad. Neto = bruto − comisiones − ` +
      'deslizamiento (VWAP recorriendo el libro) − funding − préstamo, según el motor T38. Clic en una fila para ver ' +
      'patas y riesgos. Modo Análisis: no se envía ninguna orden.</p>'
    this.el.querySelectorAll<HTMLDetailsElement>('details[data-k]').forEach((x) => { x.open = opened.has(x.dataset.k) })
    if (focus) this.el.querySelector<HTMLElement>(`[data-f="${focus}"]`)?.focus()
    this.mountExec()
    this.renderTable()
  }

  /** La sección de ejecución es un nodo propio: se reinserta, no se repinta con el escáner. */
  private mountExec(): void {
    this.el.querySelector('#arb-exec-slot')?.replaceWith(this.exec.root)
  }

  private renderTable(): void {
    const box = this.el.querySelector<HTMLElement>('#arb-rows')
    if (!box || !this.data) return
    const rows = this.filtered()
    box.innerHTML = rowsTable(rows, this.open, this.now())
    const c = this.el.querySelector('#arb-count')
    if (c) c.textContent = `${rows.length} de ${this.data.opportunities.length}`
  }

  private tick(): void {
    if (!this.data || this.el.hidden) return
    const now = this.now()
    this.el.querySelectorAll<HTMLElement>('[data-until]').forEach((n) => {
      n.textContent = countdown(Number(n.dataset.until), now)
      n.dataset.expired = String(Number(n.dataset.until) < now)
    })
    this.el.querySelectorAll<HTMLElement>('[data-asof]').forEach((n) => { n.textContent = this.ageText(Number(n.dataset.asof)) })
  }
}
