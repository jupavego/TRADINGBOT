import { fetchCopy, fetchLeaders } from './api'
import { copyBox, type CopyPayload } from './copy_view'
import type { LeadersPayload, Scorecard, Verdict } from './leaders_types'
import { cohortsBox, f, pct, rankingTable, usd, utc, VERDICT } from './leaders_view'
import { esc } from './panels'

/** Pestaña «Líderes» (T41): ranking de copy trading con métricas, intervalos y el porqué de
 *  cada veredicto (modo Análisis) y, aparte, la copia simulada en vivo (T42, modo Simulado). */
export class LeadersPanel {
  private data: LeadersPayload | null = null
  private copy: CopyPayload | null = null
  private copyErr = ''
  private err = ''
  private open = new Set<string>()
  private show: 'all' | Verdict = 'all'

  constructor(private readonly el: HTMLElement, private readonly tab: HTMLElement | null) {
    el.addEventListener('click', (e) => {
      const t = e.target as HTMLElement
      if (t.closest('#ld-reload')) { void this.reload(); return }
      const row = t.closest<HTMLElement>('tr.ld-row')
      if (row?.dataset.id) {
        const id = row.dataset.id
        if (this.open.has(id)) this.open.delete(id)
        else this.open.add(id)
        this.renderTable()
      }
    })
    el.addEventListener('input', (e) => {
      const t = e.target as HTMLSelectElement
      if (t.id !== 'ld-show') return
      this.show = t.value as 'all' | Verdict
      this.renderTable()
    })
    window.setInterval(() => { if (!this.el.hidden) void this.reload() }, 60_000)
  }

  async reload(): Promise<void> {
    try { this.data = await fetchLeaders(); this.err = '' }
    catch (e) { this.err = `No se pudo consultar el tablero: ${(e as Error).message}` }
    try { this.copy = await fetchCopy(); this.copyErr = '' }
    catch (e) { this.copyErr = `No se pudo consultar la copia simulada: ${(e as Error).message}` }
    this.paintTab()
    this.render()
  }

  /** Subcuentas desplegadas: se conservan al refrescar. */
  private openCopy(): Set<string> {
    return new Set([...this.el.querySelectorAll<HTMLElement>('details.cp-acc[open]')].map((d) => d.dataset.id ?? ''))
  }

  private paintTab(): void {
    const n = this.data?.board?.weights.length ?? 0
    if (this.tab) this.tab.textContent = n ? `Líderes (${n})` : 'Líderes'
  }

  private header(): string {
    const d = this.data, b = d?.board
    const when = b ? `Tablero ${utc(b.asof)} (hace ${Math.round(d?.age_s ?? 0)} s)` : 'sin tablero'
    return `<div class="scen-bar arb-head"><b>Líderes · copy trading</b>` +
      `<span class="mode" data-mode="ANALISIS">Modo: Análisis</span>` +
      `<span class="arb-label">${esc(d?.label ?? 'El rendimiento pasado no garantiza resultados futuros')}</span>` +
      `<span class="muted">${when}${b ? ` · ${b.leaders.length} líderes · selección corregida por ${b.n_trials} billeteras · ` +
        `fuente Hyperliquid (API pública oficial)` : ''}</span><button id="ld-reload">Actualizar</button></div>`
  }

  private signals(): string {
    const s = this.data?.signals ?? {}
    return '<div class="ld-signals">' + Object.entries(s).map(([sym, r]) => {
      const m = r.metrics as { n_approved?: number; net_exposure_usd?: number }
      const body = r.status === 'no_data'
        ? `<span class="muted">sin señal: ${esc(r.warnings[0] ?? '')}</span>`
        : `<span data-dir="${r.bias > 0 ? 'up' : r.bias < 0 ? 'down' : 'flat'}"><b>sesgo ${f(r.bias)}</b></span>` +
          `<span>confianza ${pct(r.confidence, 0)} · ${m.n_approved ?? 0} aprobados · exposición neta ${usd(m.net_exposure_usd)} USD</span>`
      return `<div class="ld-signal"><b>smart_money ${esc(sym)}</b>${body}</div>`
    }).join('') + '</div>'
  }

  private rows(): Scorecard[] {
    const all = this.data?.board?.leaders ?? []
    return this.show === 'all' ? all : all.filter((c) => c.verdict === this.show)
  }

  render(): void {
    const d = this.data, b = d?.board
    const err = this.err ? `<p class="scen-warn">${esc(this.err)}</p>` : ''
    if (!d) { this.el.innerHTML = this.header() + err + '<p class="muted">Consultando el tablero…</p>'; return }
    if (!b) {
      this.el.innerHTML = this.header() + err + this.signals() +
        '<p class="scen-warn">Sin tablero de líderes: arranca el vigilante con <code>python -m eim.leaders run</code> ' +
        '(desde <code>v2/</code>); evalúa a los líderes capturados cada 5 min y escribe <code>data/leaders/</code>.</p>' +
        copyBox(this.copy, this.copyErr, this.openCopy())
      return
    }
    const stale = d.stale ? `<p class="scen-warn">Tablero viejo (hace ${Math.round(d.age_s ?? 0)} s): el vigilante parece detenido; ` +
      'la señal <code>smart_money</code> queda sin datos.</p>' : ''
    const count = (v: Verdict): number => b.leaders.filter((c) => c.verdict === v).length
    const opt = (v: string, l: string): string => `<option value="${v}"${v === this.show ? ' selected' : ''}>${l}</option>`
    const p = b.params
    this.el.innerHTML = this.header() + err + stale + this.signals() +
      `<div id="ld-copy">${copyBox(this.copy, this.copyErr, this.openCopy())}</div>` +
      `<h4>¿Sirve el filtro? Rendimiento adelante por veredicto vigente al abrir</h4>${cohortsBox(b.cohorts)}` +
      `<div class="scen-bar"><label>Estado <select id="ld-show">${opt('all', `Todos (${b.leaders.length})`)}` +
      (['approved', 'watch', 'rejected'] as Verdict[]).map((v) => opt(v, `${VERDICT[v]} (${count(v)})`)).join('') +
      '</select></label><span class="muted">Clic en una fila: motivos, posiciones, cambios y métricas por muestra.</span></div>' +
      '<div id="ld-rows"></div>' +
      (b.errors.length ? `<p class="scen-warn">${b.errors.map(esc).join('<br>')}</p>` : '') +
      `<p class="muted arb-foot">Solo aprueba lo observado por nosotros hacia adelante: ≥ ${p.min_fwd_trades} operaciones cerradas y ` +
      `≥ ${p.min_fwd_days} d, Sharpe deflactado ≥ ${p.dsr_min} (corregido por ${b.n_trials} billeteras: la mejor de muchas parece buena por azar) ` +
      `y un seguidor con neto positivo (latencia medida + ${p.exec_delay_ms} ms, compra al ask, vende al bid, comisión de tomador ${pct(p.follower_taker_fee, 3)}). ` +
      `Intervalos al ${pct(p.ci_level, 0)} con Bonferroni por el número de billeteras. Lo histórico (cartera, historial previo) solo preselecciona. ` +
      `Descartes duros: muestra < ${p.min_hist_trades}, racha o un solo activo, martingala, promediado a la baja > ${pct(p.max_avg_down_share, 0)}, ` +
      `pérdidas latentes ocultas, liquidaciones, apalancamiento > ${p.max_leverage}×, caída > ${pct(p.max_drawdown, 0)}. ` +
      'Importes en USD (USDC). Modo Análisis: no se copia ninguna orden.</p>'
    this.renderTable()
  }

  private renderTable(): void {
    const box = this.el.querySelector<HTMLElement>('#ld-rows')
    const b = this.data?.board
    if (box && b) box.innerHTML = rankingTable(b, this.rows(), this.open)
  }
}
