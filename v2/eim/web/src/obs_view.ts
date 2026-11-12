/** «Mapa del sistema» (T75): el flujo de trabajo del proyecto en tres niveles de zoom. Desde T122
 * vive en la mesa, justo debajo del Río de decisión (ya no es una pantalla aparte): consulta el
 * observatorio solo mientras está a la vista (pestaña visible y sección en pantalla).
 * Tablero de control en vivo: solo el mapa isométrico, sondeo cada 5 s (el ritmo del indexador)
 * y la edad del último evento corre cada segundo. El flujo termina en el bróker simulado, que
 * está justo debajo; el modo lo dice la barra superior. Trazas, tarjetas, la reproducción de la
 * última vela y el recorrido guiado se retiraron de esta vista. */
import { detailHtml } from './obs_detail'
import { isoHtml, isoIncFail, isoKey, setIsoIncFail } from './obs_iso'
import { queueHtml, queuesSummary } from './obs_queues'
import { compState, routeHtml, stageSentence, stageSvg } from './obs_graph'
import { glossarize, legendHtml } from './obs_legend'
import { pulseNew } from './obs_story'
import { ago, esc, loadObs, STATE_ICON, STATE_LABEL, type ObsData } from './obs_types'

type MapView = 'route' | 'iso'

const POLL_MS = 5_000          // = cadencia del indexador del observatorio (T73)
const TICK_MS = 1_000          // la edad del último evento avanza sola entre sondeos
const STALE_S = 180            // sin eventos en 3 min el encabezado lo dice en rojo

const TEMPLATE = `
<header class="obs-head">
  <h3 class="sh">Mapa del sistema</h3>
  <span class="obs-age muted" data-x="age" aria-live="off"></span>
  <span class="spacer"></span>
  <span class="obs-panes" role="group" aria-label="Qué ver">
    <button class="btn" aria-pressed="true" title="El flujo de la vela hasta el bróker simulado, en vivo">Mapa</button></span>
  <span class="obs-views" role="group" aria-label="Cómo dibujar el mapa">
    <button class="btn" aria-pressed="true" title="Cada etapa como una sala de trabajo y cada pieza como un puesto">Isométrico</button></span>
</header>
<p class="obs-banner" data-x="banner" role="status" hidden></p>
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
`

export class ObsView {
  private data: ObsData | null = null
  private stage: string | null = null
  private sel: string | null = null
  private timer = 0
  private open = false          // a la vista: sección en pantalla y pestaña visible
  private onScreen = false
  private loadedAt = 0          // última carga pedida (evita recargas al entrar y salir de la vista)
  private ctl: AbortController | null = null
  private built = false
  private view: MapView = 'iso'
  private tick = 0
  private ageBase: { age: number; at: number } | null = null   // edad del último evento al cargar
  private isoLast = ''          // clave del último dibujo isométrico (no se rehace si nada cambió)

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
    clearInterval(this.tick)
    if (!show) return              // la carga en curso termina; solo se deja de sondear
    if (Date.now() - this.loadedAt >= POLL_MS) void this.reload()
    this.timer = window.setInterval(() => void this.reload(), POLL_MS)
    this.tick = window.setInterval(() => this.paintAge(), TICK_MS)
  }

  private build(): void {
    this.built = true
    this.root.innerHTML = TEMPLATE
    this.q('legend').innerHTML = legendHtml()
    try { localStorage.removeItem('eim.obs.view') } catch { /* la vista «Tarjetas» se retiró */ }
    this.setView('iso')
    this.root.addEventListener('click', (e) => this.onClick(e))
    this.root.addEventListener('keydown', (e) => {
      if ((e.key === 'Enter' || e.key === ' ') && (e.target as HTMLElement).closest('.obs-n')) { e.preventDefault(); this.onClick(e) }
    })
  }

  private onClick(e: Event): void {
    const t = e.target as HTMLElement
    const act = t.closest<HTMLElement>('[data-act]')?.dataset.act
    if (act === 'iso-inc') { setIsoIncFail(!isoIncFail()); this.paintMap(); return }
    if (t.closest('[data-close]')) { this.sel = null; this.paintDetail(); this.paintMap(); return }
    if (t.closest('[data-home]')) { this.stage = null; this.sel = null; this.paint(); return }
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

  /** Fija el dibujo del mapa (hoy solo «Isométrico»; las tarjetas de T75 quedan en el código). */
  private setView(v: MapView): void {
    this.view = v
    this.isoLast = ''
    this.root.dataset.view = v   // en «Isométrico» la leyenda y el detalle flotan dentro del diagrama (obs_iso.css)
    this.root.querySelector('.obs-legend')?.toggleAttribute('open', v === 'route')
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
    this.ageBase = g?.last_event_age_s == null ? null : { age: g.last_event_age_s, at: Date.now() }
    this.paintAge()
  }

  /** «Último evento hace N s», avanzando cada segundo; en rojo si el sistema lleva callado. */
  private paintAge(): void {
    const el = this.q('age'), b = this.ageBase
    if (!this.data) return
    if (!b) { el.textContent = 'Último evento: ninguno registrado'; el.dataset.tone = 'error'; return }
    const age = b.age + (Date.now() - b.at) / 1000
    el.textContent = `Último evento ${ago(Date.now() - age * 1000)}`
    el.dataset.tone = age > STALE_S ? 'error' : ''
  }

  private paintMap(): void {
    const d = this.data
    if (!d?.graph) { this.q('map').innerHTML = '<p class="muted">Sin conexión con el observatorio.</p>'; this.q('crumb').innerHTML = ''; return }
    const crumb = this.q('crumb'), map = this.q('map'), iso = this.view === 'iso'
    if (iso) {                    // se rehace solo si cambió algo visible: las animaciones no saltan en cada sondeo
      const k = isoKey(d, this.stage, this.sel)
      if (k !== this.isoLast || !map.querySelector('.iso-wrap')) { map.innerHTML = isoHtml(d, this.stage, this.sel); this.isoLast = k }
    }
    if (!this.stage) {
      crumb.innerHTML = `<b>Ruta completa</b> · pulsa ${iso ? 'una sala o un puesto' : 'una etapa para ver sus piezas'}`
      if (!iso) map.innerHTML = routeHtml(d, null)
      return
    }
    const g = d.graph
    crumb.innerHTML = `<button class="obs-link" data-home>← Ruta completa</button> / <b>${esc(g.stage_titles_es[this.stage])}</b>
      <span class="muted">${esc(g.stage_explain_es[this.stage] ?? '')} ${esc(stageSentence(d, this.stage))}.</span>`
    glossarize(crumb, g.glossary)
    if (!iso) map.innerHTML = stageSvg(d, this.stage, this.sel)
  }

  private paintDetail(): void {
    const box = this.q('detail'), d = this.data
    if (!d?.graph || !this.sel) {
      if (d?.graph && this.stage) box.innerHTML = `<h3>${esc(d.graph.stage_titles_es[this.stage])}</h3><p>${esc(d.graph.stage_explain_es[this.stage] ?? '')}</p><p class="muted">Pulsa una pieza para ver su detalle.</p>`
        + (this.view === 'iso' ? `<ul class="obs-piece-list">${d.comps.filter((c) => c.stage === this.stage).map((c) => `<li>${STATE_ICON[compState(d, c)]} <button class="obs-link" data-goto="${esc(c.id)}">${esc(c.title_es)}</button> <small class="muted">${STATE_LABEL[compState(d, c)]}</small></li>`).join('')}</ul>` : '')
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
    const [o1, o2, o3, o4] = [was[0] ?? '', was[1] ?? '', was[2] ?? '', was[3] ?? '']
    const qs = d.queues ?? [], qsum = queuesSummary(qs)
    this.q('todo').innerHTML = `
      <details${o1}><summary>Qué requiere atención (${bad.length})</summary><ul class="obs-ul">${bad.slice(0, 12).map((c) => `<li><button class="obs-link" data-goto="${esc(c.id)}">${esc(c.title_es)}</button>
        <small>${STATE_ICON[compState(d, c)]} ${STATE_LABEL[compState(d, c)]}</small></li>`).join('') || '<li class="muted">Nada: todo lo construido reporta al día.</li>'}</ul></details>
      <details${o2}><summary>Qué falta por construir (${planned.length})</summary><ul class="obs-ul">${[...byTask].sort().map(([t, n]) => `<li><b>${esc(t)}</b> · ${esc(n.join(', '))}</li>`).join('')}</ul>
        <small class="muted">Línea punteada en el mapa = planeado.</small></details>
      <details${o3}><summary>Desvíos entre lo declarado y lo observado (${dev.undeclared.length + dev.unseen.length})</summary><ul class="obs-ul">
        ${dev.undeclared.map((e) => `<li>Vista y no declarada: ${esc(e.source)} → ${esc(e.target)}</li>`).join('')}
        ${dev.unseen.slice(0, 10).map((e) => `<li>Declarada y nunca vista: ${esc(e.source)} → ${esc(e.target)}</li>`).join('')}
        ${dev.undeclared.length + dev.unseen.length ? '' : '<li class="muted">Ninguno detectado con las trazas disponibles.</li>'}</ul></details>
      <details${o4} data-x="queues"><summary>Colas entre etapas (${d.queues ? `${qsum.drops} con descartes · ${qsum.missing} sin informe` : 'sin respuesta'})</summary>
        <ul class="obs-ul">${qs.map(queueHtml).join('') || '<li class="muted">El observatorio no devolvió las colas.</li>'}</ul></details>`
  }
}
