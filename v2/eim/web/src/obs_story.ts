/** «Ver la última vela» y pulsos en vivo (T75): solo animan eventos REALES de la traza. */
import { plainWords } from './obs_detail'
import { ago, esc, getObs, type ObsComp, type ObsData, type ObsEvent } from './obs_types'

export const STEP_MS = 1400
const PULSE_MS = 1600

/** Marca un nodo/etapa/flecha con un pulso temporal. */
export function pulse(root: HTMLElement, c: ObsComp): void {
  const sel = [`[data-id="${CSS.escape(c.id)}"]`, `[data-stage="${CSS.escape(c.stage)}"]`, `.obs-edge[data-t="${CSS.escape(c.id)}"]`]
  root.querySelectorAll(sel.join(',')).forEach((el) => {
    el.classList.add('pulse')
    window.setTimeout(() => el.classList.remove('pulse'), PULSE_MS)
  })
}

/** Compara dos cargas y pulsa los componentes cuyo último evento es nuevo (dato real). */
export function pulseNew(root: HTMLElement, prev: ObsData | null, next: ObsData): void {
  if (!prev) return
  const old = new Map(prev.comps.map((c) => [c.id, c.last_event_ms ?? 0]))
  next.comps.forEach((c) => { if ((c.last_event_ms ?? 0) > (old.get(c.id) ?? 0)) pulse(root, c) })
}

export class Story {
  private timer = 0
  private run = 0
  constructor(private box: HTMLElement, private root: HTMLElement, private data: () => ObsData | null) {}

  get playing(): boolean { return this.run > 0 }

  stop(): void { this.run = 0; clearTimeout(this.timer); this.box.hidden = true; this.root.querySelectorAll('.playing').forEach((e) => e.classList.remove('playing')) }

  async start(traceId?: string): Promise<void> {
    this.stop()
    const id = ++this.run + 1000 * Date.now()
    this.run = id
    this.box.hidden = false
    this.box.innerHTML = '<p>Buscando la última traza registrada…</p>'
    let events: ObsEvent[] = []
    try {
      let tid = traceId           // T76: una traza elegida en «Trazas y calidad»
      if (!tid) {
        const t = await getObs<{ items: { trace_id: string }[] }>('traces?limit=1')
        if (!t.items.length) { this.empty(); return }
        tid = t.items[0].trace_id
      }
      const full = await getObs<{ events: ObsEvent[] }>(`traces/${encodeURIComponent(tid)}`)
      events = full.events.filter((e) => e.kind !== 'run_start' && e.kind !== 'run_end')
    } catch { this.box.innerHTML = '<p>No se pudo leer la traza (el observatorio no responde). No se muestra nada inventado.</p>'; return }
    if (!events.length) { this.empty(); return }
    const step = (i: number): void => {
      if (this.run !== id) return
      const d = this.data(), e = events[i]
      if (!d || !e) { this.box.innerHTML += '<p class="muted">Fin de la reproducción.</p>'; this.run = 0; return }
      const c = d.comps.find((x) => x.id === e.component_id)
      this.root.querySelectorAll('.playing').forEach((el) => el.classList.remove('playing'))
      if (c) {
        this.root.querySelectorAll(`[data-id="${CSS.escape(c.id)}"],[data-stage="${CSS.escape(c.stage)}"]`).forEach((el) => el.classList.add('playing'))
        pulse(this.root, c)
      }
      this.box.innerHTML = `<p class="obs-step"><b>Paso ${i + 1} de ${events.length}</b> · ${esc(c?.title_es ?? e.component_id)}
        <small class="muted">(${ago(e.ts_utc)}, tardó ${e.duration_ms != null ? `${Math.round(e.duration_ms)} ms` : 'n/d'})</small></p>
        <p>${c ? plainWords(c, e) : esc(e.kind)}</p><button class="btn" data-story="stop">Detener</button>`
      this.timer = window.setTimeout(() => step(i + 1), STEP_MS)
    }
    step(0)
  }

  private empty(): void {
    this.box.innerHTML = '<p>Aún no hay actividad registrada: cuando cierre una vela y el sistema la procese, podrás verla aquí.</p>'
  }
}
