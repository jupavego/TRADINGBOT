/** «Mapa del sistema» (T75): el flujo de trabajo del proyecto en tres niveles de zoom. Desde T122
 * vive en la mesa, justo debajo del Río de decisión (ya no es una pantalla aparte): consulta el
 * observatorio solo mientras está a la vista (pestaña visible y sección en pantalla). */
import { detailHtml } from './obs_detail'
import { compState, routeHtml, stageSentence, stageSvg } from './obs_graph'
import { glossarize, legendHtml, markTour, tourHtml, TOUR, tourSeen } from './obs_legend'
import { pulseNew, Story } from './obs_story'
import { TraceView } from './obs_trace_view'
import { ago, esc, loadObs, STATE_ICON, STATE_LABEL, type ObsData } from './obs_types'

const POLL_MS = 10_000
const MODE_ES: Record<string, string> = { ANALISIS: 'Análisis', SIMULADO: 'Simulado', TESTNET: 'Testnet', REAL: 'Real' }

const TEMPLATE = `
<header class="obs-head">
  <h3 class="sh">Mapa del sistema</h3>
  <span class="mode" data-x="mode">Modo: —</span>
  <span class="obs-age muted" data-x="age" aria-live="polite"></span>
  <span class="spacer"></span>
  <span class="obs-panes" role="group" aria-label="Qué ver">
    <button class="btn" data-act="pane-map" aria-pressed="true">Mapa</button>
    <button class="btn" data-act="pane-trace" aria-pressed="false" title="Elegir una decisión y ver qué ocurrió, paso a paso">Trazas y calidad</button></span>
  <button class="btn obs-replay-btn" data-act="replay" title="Reproduce despacio lo que pasó con la última vela">▶ Ver la última vela</button>
  <button class="btn" data-act="tour" aria-label="Recorrido guiado" title="Recorrido guiado">?</button>
</header>
<p class="obs-banner" data-x="banner" role="status" hidden></p>
<div class="obs-story" data-x="story" hidden aria-live="polite"></div>
<div class="obs-body">
  <div class="obs-main">
    <nav class="obs-crumb" data-x="crumb"></nav>
    <section class="obs-route" data-x="map" aria-label="Mapa"></section>
    <section class="obs-todo" data-x="todo" aria-label="Qué falta por construir"></section>
  </div>
  <aside class="obs-side">
    <div class="obs-legend-box" data-x="legend"></div>
    <div class="obs-detail" data-x="detail" aria-live="polite"><p class="muted">Pulsa una etapa o una pieza del mapa para ver su detalle.</p></div>
  </aside>
</div>
<section class="obs-traces" data-x="traces" aria-label="Trazas y calidad de la evidencia" hidden></section>
<div data-x="tour"></div>`

export class ObsView {
  private data: ObsData | null = null
  private stage: string | null = null
  private sel: string | null = null
  private timer = 0
  private open = false          // a la vista: sección en pantalla y pestaña visible
  private onScreen = false
  private loadedAt = 0          // última carga pedida (evita recargas al entrar y salir de la vista)
  private ctl: AbortController | null = null
  private story!: Story
  private tourStep = -1
  private built = false
  private traces!: TraceView

  constructor(private root: HTMLElement) {}

  private q = (k: string): HTMLElement => this.root.querySelector<HTMLElement>(`[data-x="${k}"]`)!

  /** Monta el mapa en la mesa y sondea el observatorio cada `POLL_MS` solo mientras se ve. */
  mount(): void {
    try { localStorage.removeItem('eim.obs.home') } catch { /* preferencia «Abrir al iniciar» retirada */ }
    if (!this.built) this.build()
    new IntersectionObserver((es) => {
      this.onScreen = es.some((e) => e.isIntersecting)
      this.sync()
    }).observe(this.root)
    document.addEventListener('visibilitychange', () => this.sync())
  }

  private sync(): void {
    const show = this.onScreen && !document.hidden
    if (show === this.open) return
    this.open = show
    clearInterval(this.timer)
    if (!show) return              // la carga en curso termina; solo se deja de sondear
    if (Date.now() - this.loadedAt >= POLL_MS) void this.reload()
    this.timer = window.setInterval(() => void this.reload(), POLL_MS)
    if (!tourSeen() && this.tourStep < 0) this.startTour()
  }

  private build(): void {
    this.built = true
    this.root.innerHTML = TEMPLATE
    this.q('legend').innerHTML = legendHtml()
    this.story = new Story(this.q('story'), this.root, () => this.data)
    this.traces = new TraceView(this.q('traces'), (id) => { this.pane('map'); void this.story.start(id) })
    this.root.addEventListener('click', (e) => this.onClick(e))
    this.root.addEventListener('keydown', (e) => {
      if ((e.key === 'Enter' || e.key === ' ') && (e.target as HTMLElement).closest('.obs-n')) { e.preventDefault(); this.onClick(e) }
    })
  }

  private onClick(e: Event): void {
    const t = e.target as HTMLElement
    const act = t.closest<HTMLElement>('[data-act]')?.dataset.act
    if (act === 'replay') { this.pane('map'); void this.story.start(); return }
    if (act === 'pane-map') { this.pane('map'); return }
    if (act === 'pane-trace') { this.pane('trace'); return }
    if (act === 'tour') { this.startTour(); return }
    if (t.closest('[data-story="stop"]')) { this.story.stop(); return }
    const tour = t.closest<HTMLElement>('[data-tour]')?.dataset.tour
    if (tour) { this.stepTour(tour); return }
    if (t.closest('[data-close]')) { this.sel = null; this.paintDetail(); this.paintMap(); return }
    if (t.closest('[data-home]')) { this.stage = null; this.sel = null; this.paint(); return }
    const tr = t.closest<HTMLElement>('[data-open-trace]')?.dataset.openTrace
    if (tr) { this.pane('trace'); void this.traces.open(tr); return }
    const go = t.closest<HTMLElement>('[data-goto]')?.dataset.goto
    const node = t.closest<HTMLElement>('.obs-n')
    const id = go ?? node?.dataset.id
    if (id) {
      const c = this.data?.comps.find((x) => x.id === id)
      if (c) { this.stage = c.stage; this.sel = id; this.paint() }
    } else if (node?.dataset.stage) {
      this.stage = node.dataset.stage; this.sel = null; this.paint()
    }
  }

  /** Alterna entre el mapa (T75) y las trazas con su calidad de evidencia (T76). */
  private pane(which: 'map' | 'trace'): void {
    this.root.dataset.pane = which
    this.root.querySelectorAll<HTMLElement>('[data-act^="pane-"]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.act === `pane-${which}`)))
    this.q('traces').hidden = which !== 'trace'
    this.root.querySelector<HTMLElement>('.obs-body')!.hidden = which === 'trace'
    if (which === 'trace') { this.story.stop(); this.traces.show() }
  }

  async reload(): Promise<void> {
    this.loadedAt = Date.now()
    this.ctl?.abort()
    this.ctl = new AbortController()
    const next = await loadObs(this.ctl.signal)
    if (!next) return
    const prev = this.data
    this.data = next
    this.paint()
    pulseNew(this.root, prev, next)
  }

  private paint(): void {
    const d = this.data
    if (!d) return
    this.paintHead(d)
    this.paintMap()
    this.paintDetail()
    this.paintTodo(d)
  }

  private paintHead(d: ObsData): void {
    const g = d.graph
    const banner = this.q('banner')
    if (d.failed || !g) {
      banner.hidden = false
      banner.textContent = 'El observatorio no responde: ningún estado se da por sano; todo aparece «sin datos» hasta que vuelva.'
      banner.dataset.tone = 'error'
    } else if (d.health && !d.health.ok) {
      banner.hidden = false
      banner.textContent = `El observatorio avisa: ${d.health.problems.join(' · ')}`
      banner.dataset.tone = 'warn'
    } else banner.hidden = true
    const m = g?.mode ?? null
    this.q('mode').textContent = `Modo: ${m ? MODE_ES[m] ?? m : 'sin eventos'}`
    this.q('mode').dataset.mode = m ?? ''
    this.q('age').textContent = g?.last_event_age_s == null ? 'Último evento: ninguno registrado'
      : `Último evento ${ago(Date.now() - g.last_event_age_s * 1000)}${g.index_lag_s != null ? ` · indexador al día hace ${Math.round(g.index_lag_s)} s` : ''}`
  }

  private paintMap(): void {
    const d = this.data
    if (!d?.graph) { this.q('map').innerHTML = '<p class="muted">Sin conexión con el observatorio.</p>'; this.q('crumb').innerHTML = ''; return }
    const crumb = this.q('crumb'), map = this.q('map')
    if (!this.stage) {
      crumb.innerHTML = '<b>Ruta completa</b> · pulsa una etapa para ver sus piezas'
      map.innerHTML = routeHtml(d, null)
      return
    }
    const g = d.graph
    crumb.innerHTML = `<button class="obs-link" data-home>← Ruta completa</button> / <b>${esc(g.stage_titles_es[this.stage])}</b>
      <span class="muted">${esc(g.stage_explain_es[this.stage] ?? '')} ${esc(stageSentence(d, this.stage))}.</span>`
    glossarize(crumb, g.glossary)
    map.innerHTML = stageSvg(d, this.stage, this.sel)
  }

  private paintDetail(): void {
    const box = this.q('detail'), d = this.data
    if (!d?.graph || !this.sel) {
      if (d?.graph && this.stage) box.innerHTML = `<h3>${esc(d.graph.stage_titles_es[this.stage])}</h3><p>${esc(d.graph.stage_explain_es[this.stage] ?? '')}</p><p class="muted">Pulsa una pieza para ver su detalle.</p>`
      else box.innerHTML = '<p class="muted">Pulsa una etapa o una pieza del mapa para ver su detalle.</p>'
      return
    }
    const id = this.sel
    void detailHtml(d, id).then((h) => {
      if (this.sel !== id) return
      box.innerHTML = h
      glossarize(box, d.graph.glossary)
    })
  }

  /** «Qué falta por construir» y desvíos estructurales: lo planeado nunca se confunde con una avería. */
  private paintTodo(d: ObsData): void {
    if (!d.graph) { this.q('todo').innerHTML = ''; return }
    const planned = d.comps.filter((c) => c.built === 'planeado')
    const byTask = new Map<string, string[]>()
    planned.forEach((c) => byTask.set(c.task, [...(byTask.get(c.task) ?? []), c.title_es]))
    const dev = d.graph.deviations
    const bad = d.comps.filter((c) => ['error', 'degradado', 'obsoleto', 'sin_datos'].includes(compState(d, c)))
    // en la mesa (T122) las listas empiezan plegadas y conservan lo que el usuario abre entre sondeos
    const was = [...this.q('todo').querySelectorAll('details')].map((x) => (x.open ? ' open' : ''))
    const [o1, o2, o3] = [was[0] ?? '', was[1] ?? '', was[2] ?? '']
    this.q('todo').innerHTML = `
      <details${o1}><summary>Qué requiere atención (${bad.length})</summary><ul class="obs-ul">${bad.slice(0, 12).map((c) => `<li><button class="obs-link" data-goto="${esc(c.id)}">${esc(c.title_es)}</button>
        <small>${STATE_ICON[compState(d, c)]} ${STATE_LABEL[compState(d, c)]}</small></li>`).join('') || '<li class="muted">Nada: todo lo construido reporta al día.</li>'}</ul></details>
      <details${o2}><summary>Qué falta por construir (${planned.length})</summary><ul class="obs-ul">${[...byTask].sort().map(([t, n]) => `<li><b>${esc(t)}</b> · ${esc(n.join(', '))}</li>`).join('')}</ul>
        <small class="muted">Línea punteada en el mapa = planeado.</small></details>
      <details${o3}><summary>Desvíos entre lo declarado y lo observado (${dev.undeclared.length + dev.unseen.length})</summary><ul class="obs-ul">
        ${dev.undeclared.map((e) => `<li>Vista y no declarada: ${esc(e.source)} → ${esc(e.target)}</li>`).join('')}
        ${dev.unseen.slice(0, 10).map((e) => `<li>Declarada y nunca vista: ${esc(e.source)} → ${esc(e.target)}</li>`).join('')}
        ${dev.undeclared.length + dev.unseen.length ? '' : '<li class="muted">Ninguno detectado con las trazas disponibles.</li>'}</ul></details>`
  }

  // --- recorrido guiado ---
  private startTour(): void { this.tourStep = 0; this.paintTour() }
  private stepTour(a: string): void {
    if (a === 'skip') { this.tourStep = -1; markTour() } else if (a === 'prev') this.tourStep = Math.max(0, this.tourStep - 1)
    else if (++this.tourStep >= TOUR.length) { this.tourStep = -1; markTour() }
    this.paintTour()
  }
  private paintTour(): void {
    this.root.querySelectorAll('.tour-hl').forEach((e) => e.classList.remove('tour-hl'))
    const box = this.q('tour')
    if (this.tourStep < 0) { box.innerHTML = ''; return }
    box.innerHTML = tourHtml(this.tourStep)
    this.root.querySelector(TOUR[this.tourStep].sel)?.classList.add('tour-hl')
  }
}
