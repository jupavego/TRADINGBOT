/** «Trazas y calidad» (T76): elegir una vela/decisión y ver lo que realmente ocurrió, paso a paso. */
import { agentsHtml, factsHtml, markBadge, qualityHtml, riskHtml, stepHtml, whyHtml } from './obs_trace_panels'
import { traceSvg } from './obs_trace_graph'
import { MODE_ES, OUTCOME_ES, type Explain, type Quality, type TraceRow } from './obs_trace_types'
import { ago, esc, getObs } from './obs_types'

const DAY = 86_400_000
const FILTERS = `
<label>Marco <select data-f="timeframe"><option value="">Todos</option><option>15m</option><option>1h</option><option>4h</option></select></label>
<label>Resultado <select data-f="outcome"><option value="">Todos</option><option value="plan">Propuesta</option><option value="vetado">Vetada</option>
  <option value="sin_plan">Sin plan</option><option value="aprobado">Aprobada, sin orden</option><option value="ejecutada">Ejecutada</option>
  <option value="orden_enviada">Orden enviada</option><option value="error">Con error</option></select></label>
<label>Modo <select data-f="mode"><option value="">Todos</option><option value="ANALISIS">Análisis</option><option value="SIMULADO">Simulado</option><option value="TESTNET">Testnet</option></select></label>
<label>Símbolo <input data-f="symbol" size="8" placeholder="BTCUSDT" aria-label="Símbolo"></label>`

const TEMPLATE = `
<div class="obs-tr-grid">
  <aside class="obs-tr-side">
    <h3>Elige una decisión</h3>
    <div class="obs-filters">${FILTERS}</div>
    <ul class="obs-tr-list" data-x="list" aria-live="polite"></ul>
    <details class="obs-quality" open><summary>Calidad de la evidencia</summary>
      <label>Periodo <select data-x="qperiod"><option value="1">Últimas 24 h</option><option value="7" selected>Últimos 7 días</option><option value="30">Últimos 30 días</option></select></label>
      <div data-x="quality"><p class="muted">Cargando…</p></div></details>
  </aside>
  <section class="obs-tr-main" data-x="detail"><p class="muted">Elige una vela de la lista para ver, paso a paso, lo que el sistema hizo con ella.</p></section>
</div>`

export class TraceView {
  private rows: TraceRow[] = []
  private cur: Explain | null = null
  private step = 0
  private selId: string | null = null
  private built = false

  constructor(private root: HTMLElement, private onMap: (traceId: string) => void) {}

  private q = (k: string): HTMLElement => this.root.querySelector<HTMLElement>(`[data-x="${k}"]`)!
  private f = (k: string): string => this.root.querySelector<HTMLInputElement>(`[data-f="${k}"]`)!.value.trim()

  show(): void {
    if (!this.built) this.build()
    void this.loadList()
    void this.loadQuality()
  }

  private build(): void {
    this.built = true
    this.root.innerHTML = TEMPLATE
    this.root.addEventListener('change', (e) => {
      const t = e.target as HTMLElement
      if (t.matches('[data-f]')) void this.loadList()
      if (t.matches('[data-x="qperiod"]')) void this.loadQuality()
    })
    this.root.addEventListener('click', (e) => this.onClick(e.target as HTMLElement))
    this.root.addEventListener('keydown', (e) => {
      const n = (e.target as HTMLElement).closest<HTMLElement>('.obs-tn')
      if (n && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); this.pick(Number(n.dataset.step)) }
    })
  }

  private onClick(t: HTMLElement): void {
    const row = t.closest<HTMLElement>('[data-trace]')
    if (row) { void this.open(row.dataset.trace!); return }
    const node = t.closest<HTMLElement>('.obs-tn')
    if (node) { this.pick(Number(node.dataset.step)); return }
    const li = t.closest<HTMLElement>('[data-pick]')
    if (li) { this.pick(Number(li.dataset.pick)); return }
    const act = t.closest<HTMLElement>('[data-tact]')?.dataset.tact
    const n = this.cur?.steps.length ?? 0
    if (act === 'prev') this.pick(Math.max(0, this.step - 1))
    else if (act === 'next') this.pick(Math.min(n - 1, this.step + 1))
    else if (act === 'map' && this.selId) this.onMap(this.selId)
    else if (act === 'desk' && this.cur?.decision) {
      const d = this.cur.decision
      window.dispatchEvent(new CustomEvent('eim:replay', { detail: { symbol: d.symbol, timeframe: d.timeframe, ts: d.last_ms } }))
    }
  }

  async loadList(): Promise<void> {
    const p = new URLSearchParams({ limit: '40' })
    for (const k of ['timeframe', 'mode', 'symbol']) if (this.f(k)) p.set(k, k === 'symbol' ? this.f(k).toUpperCase() : this.f(k))
    const o = this.f('outcome')
    if (o === 'error') p.set('has_error', 'true'); else if (o) p.set('outcome', o)
    const ul = this.q('list')
    try {
      this.rows = (await getObs<{ items: TraceRow[] }>(`traces?${p}`)).items
    } catch { ul.innerHTML = '<li class="muted">El observatorio no responde: no se puede listar nada.</li>'; return }
    ul.innerHTML = this.rows.map((r) => `<li><button class="obs-tr-row${r.trace_id === this.selId ? ' sel' : ''}" data-trace="${esc(r.trace_id)}">
        <span><b>${esc(r.symbol ?? '—')}</b> ${esc(r.timeframe ?? '')} · ${esc(MODE_ES[r.mode] ?? r.mode)}</span>
        <span>${esc(OUTCOME_ES[r.outcome] ?? r.outcome)}${r.has_error ? ' ✖' : ''}</span>
        <small class="muted">${ago(r.last_ms)}</small>${markBadge(r.evidence)}</button></li>`).join('') || '<li class="muted">Ninguna traza con esos filtros (¿aún no cierra una vela?).</li>'
  }

  async loadQuality(): Promise<void> {
    const days = Number(this.root.querySelector<HTMLSelectElement>('[data-x="qperiod"]')?.value ?? 7)
    const bucket = days <= 1 ? 'hora' : 'dia'
    let q: Quality | null = null
    try { q = await getObs<Quality>(`quality?desde=${Date.now() - days * DAY}&hasta=${Date.now()}&bucket=${bucket}`) } catch { /* se informa abajo */ }
    this.q('quality').innerHTML = qualityHtml(q)
  }

  async open(id: string): Promise<void> {
    this.selId = id
    this.root.querySelectorAll('.obs-tr-row').forEach((b) => b.classList.toggle('sel', (b as HTMLElement).dataset.trace === id))
    const box = this.q('detail')
    box.innerHTML = '<p class="muted">Reconstruyendo la traza…</p>'
    try { this.cur = await getObs<Explain>(`traces/${encodeURIComponent(id)}/explain`) } catch {
      box.innerHTML = '<p>No se pudo leer esta traza (¿purgada o el observatorio no responde?). No se muestra nada inventado.</p>'; return
    }
    this.step = 0
    this.paint()
  }

  private pick(i: number): void {
    if (!this.cur?.steps.length) return
    this.step = i
    this.paintStep()
  }

  private paint(): void {
    const x = this.cur
    if (!x) return
    const d = x.decision
    const box = this.q('detail')
    if (!x.steps.length) {
      box.innerHTML = `<h3>${esc(d?.symbol ?? '')} ${esc(d?.timeframe ?? '')}</h3>${markBadge(null)}<p>Los eventos crudos de esta traza ya se purgaron (se conservan 30 días); queda solo el resumen: ${esc(OUTCOME_ES[x.outcome] ?? x.outcome)}.</p>`
      return
    }
    box.innerHTML = `<header class="obs-tr-h"><h3>${esc(d?.symbol ?? '')} ${esc(d?.timeframe ?? '')} · ${esc(MODE_ES[d?.mode ?? ''] ?? d?.mode ?? '')}</h3>
        ${markBadge(x.mark)}<span class="muted">${ago(d?.last_ms)}</span><span class="spacer"></span>
        <button class="btn" data-tact="map" title="Reproduce esta traza en el mapa del sistema">Ver en el mapa</button>
        <button class="btn" data-tact="desk" title="Abre la mesa con el deslizador de reproducción en ese instante">Abrir en la mesa en ese instante</button></header>
      ${whyHtml(x)}${factsHtml(x)}
      <div class="obs-tr-graph" data-x="graph"></div>
      <section class="obs-story-box"><div class="obs-tr-nav"><button class="btn" data-tact="prev">◀ Anterior</button><button class="btn" data-tact="next">Siguiente ▶</button>
        <span class="muted">Usa también las flechas del teclado en los nodos.</span></div><div data-x="step" aria-live="polite"></div>
        <ol class="obs-relato" data-x="relato"></ol></section>${agentsHtml(x)}${riskHtml(x)}`
    this.paintStep()
  }

  private paintStep(): void {
    const x = this.cur
    if (!x) return
    this.q('graph').innerHTML = traceSvg(x.steps, this.step)
    this.q('step').innerHTML = stepHtml(x.steps[this.step], x.steps.length)
    this.q('relato').innerHTML = x.steps.map((s, i) => `<li data-pick="${i}" class="${i === this.step ? 'cur' : ''}${s.causal ? ' causal' : ''}" tabindex="0">${esc(s.text_es)}</li>`).join('')
  }
}
