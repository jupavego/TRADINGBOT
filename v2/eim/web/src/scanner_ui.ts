/** Pestaña «Escáner» (T94): oportunidades candidatas del escáner global. Modo ANÁLISIS.
 *
 * Vive en la barra superior, junto a la cantera y al mapa del sistema: abierta, la mesa se oculta
 * (views.ts). Lee la API de solo lectura `/v2/scanner/...` y se refresca sola cada 60 s mientras
 * está a la vista. Arriba, siempre: el modo y el aviso «candidata, no validada»; luego mercados
 * abiertos/cerrados, filtros (clase, mercado, horizonte, lado), las candidatas con sus tres
 * puntuaciones separadas y el universo puntuado; al pulsar una fila, el detalle con los agentes
 * que opinan y los que no (con su motivo), la proyección y la trazabilidad. */
import { fetchInstrument, fetchOpportunities, fetchUniverse, type InstrumentPayload, type Opportunity, type UniversePayload } from './scanner_api'
import { ALL, detail, filterOpps, filters, head, markets, matches, oppTable, universeTable, type Filters } from './scanner_render'
import { esc } from './panels'

export class ScannerPanelView {
  private u: UniversePayload | null = null
  private opps: Opportunity[] = []
  private err = ''
  private f: Filters = { cls: ALL, market: ALL, horizon: ALL, side: ALL }
  private card: InstrumentPayload | null = null
  private abort: AbortController | null = null

  constructor(private readonly el: HTMLElement) {
    el.addEventListener('click', (e) => {
      const t = e.target as HTMLElement
      if (t.closest('[data-sc-back]')) { this.card = null; this.render(); return }
      const r = t.closest<HTMLElement>('.sc-row')
      if (r?.dataset.id) void this.open(r.dataset.id)
    })
    el.addEventListener('keydown', (e) => {
      const r = (e.target as HTMLElement).closest<HTMLElement>('.sc-row')
      if (r?.dataset.id && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); void this.open(r.dataset.id) }
    })
    el.addEventListener('change', (e) => {
      const t = e.target as HTMLSelectElement
      const k = t.dataset.sc as keyof Filters | undefined
      if (k) { this.f = { ...this.f, [k]: t.value }; this.render() }
    })
    window.setInterval(() => { if (!this.el.hidden && !this.card) void this.reload() }, 60_000)
  }

  async reload(): Promise<void> {
    this.abort?.abort()
    const ac = new AbortController()
    this.abort = ac
    try {
      const [u, o] = await Promise.all([fetchUniverse(ac.signal), fetchOpportunities(ac.signal)])
      this.u = u
      this.opps = o.opportunities ?? []
      this.err = ''
    } catch (e) {
      if (ac.signal.aborted) return
      this.err = (e as Error).message
    }
    this.render()
  }

  private async open(id: string): Promise<void> {
    try {
      this.card = await fetchInstrument(id)
    } catch (e) {
      this.err = (e as Error).message
    }
    this.render()
    this.el.scrollIntoView({ block: 'start' })
  }

  /** Pinta con los datos ya cargados (también lo usa la verificación con datos renderizados). */
  show(u: UniversePayload, opps: Opportunity[]): void { this.u = u; this.opps = opps; this.err = ''; this.render() }

  render(): void {
    if (this.card) {
      const c = this.card
      this.el.innerHTML = detail(c.deep, c.opportunity, c.row, c.note)
      return
    }
    const u = this.u
    if (!u) {
      this.el.innerHTML = `<p class="${this.err ? 'sc-warn' : 'muted'}">${esc(this.err || 'Consultando el escáner…')}</p>`
      return
    }
    if (!u.available) {
      this.el.innerHTML = `<div class="sc-head"><div class="sc-title"><h3>Escáner global</h3><span class="sc-mode">Modo: Análisis</span>` +
        `<span class="sc-flag">⚠ ${esc(u.status_label)}</span></div><p class="sc-notice">${esc(u.notice)}</p>` +
        `<p class="sc-warn">${esc(u.reason ?? 'sin datos')}</p></div>`
      return
    }
    const rows = (u.rows ?? []).filter((r) => matches(r, this.f))
    const byId = new Map((u.rows ?? []).map((r) => [r.instrument_id, r]))
    const shown = filterOpps(this.opps, this.f)
    this.el.innerHTML = head(u, this.opps.length) +
      (this.err ? `<p class="sc-warn">${esc(this.err)} (se muestran los últimos datos)</p>` : '') +
      markets(u.markets ?? []) + filters(u, this.f) +
      `<h4>Candidatas <small>${shown.length} de ${this.opps.length} · en orden alfabético: el ranking global comparable llega con T95</small></h4>` +
      `<div class="sc-scroll">${oppTable([...shown].sort((a, b) => a.symbol.localeCompare(b.symbol)), byId)}</div>` +
      `<details class="sc-uni"><summary>Universo puntuado (${rows.length}) · cobertura por instrumento</summary>` +
      `<div class="sc-scroll">${universeTable(rows)}</div></details>`
  }
}
