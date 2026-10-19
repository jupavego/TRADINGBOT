/** Panel «Biblioteca» (T55): catálogo, pregunta a la literatura y respuesta con citas. Solo informa. */
import { askLibrary, fetchLibCatalog, type LibAnswer, type LibCatalog } from './library_api'
import { esc } from './panels'

const TAG = 'Contexto bibliográfico · no es una recomendación'
const SCENARIOS: Record<string, string> = { '': 'Sin escenario', bull: 'Alcista', neutral: 'Neutral', bear: 'Bajista' }

function citeOf(a: LibAnswer, src: string): string {
  const c = a.sources[src]
  if (c) {
    const ct = c.citations[0]
    return `${esc(c.title)} — ${esc(ct?.author ?? '')}, ${esc(ct?.chapter ?? '')}, p. ${ct?.pages.join('–') ?? '?'} (archivo)`
  }
  const [book, page] = src.split('#')
  return `${esc(book)}, p. ${esc(page ?? '?')} (archivo)`
}

export class LibraryPanel {
  private cat: LibCatalog | null = null
  private answer = ''
  private busy = false

  constructor(private root: HTMLElement, private mode: () => string) {
    root.onclick = (e) => {
      const b = (e.target as HTMLElement).closest('button')
      if (!b) return
      if (b.id === 'lib-ask') void this.ask(false)
      if (b.id === 'lib-ask-sc') void this.ask(true)
    }
    this.paint()
  }

  async reload(): Promise<void> {
    try { this.cat = await fetchLibCatalog() } catch { this.cat = null }
    const q = this.root.querySelector<HTMLInputElement>('#lib-q')?.value ?? ''
    const sc = this.root.querySelector<HTMLSelectElement>('#lib-sc')?.value ?? ''
    this.paint(q, sc)
  }

  private async ask(forScenario: boolean): Promise<void> {
    const q = this.root.querySelector<HTMLInputElement>('#lib-q')!
    const sc = this.root.querySelector<HTMLSelectElement>('#lib-sc')!.value
    const scenario = sc || (forScenario ? 'neutral' : '')
    const question = q.value.trim() || (forScenario
      ? `¿Qué dice la literatura sobre el escenario ${SCENARIOS[scenario].toLowerCase()} en la situación actual?` : '')
    if (!question || this.busy) return
    const keep = q.value
    this.busy = true
    this.answer = '<p class="meta">Consultando la biblioteca…</p>'
    this.paint(keep, sc)
    try {
      this.answer = this.renderAnswer(await askLibrary(question, scenario || null, ''))
    } catch (e) {
      this.answer = `<p class="meta">No se pudo consultar (${esc(String(e))}).</p>`
    }
    this.busy = false
    this.paint(keep, sc)
  }

  private renderAnswer(a: LibAnswer): string {
    if (a.status === 'no_data') return `<p class="meta lib-nodata">Sin datos: ${esc(a.reason ?? 'sin motivo')}</p>`
    const pts = a.puntos.map((p) =>
      `<li>${esc(p.texto)} <span class="muted">— ${citeOf(a, p.fuente)}</span></li>`).join('')
    const warn = a.advertencias.map((w) => `<li>${esc(w)}</li>`).join('')
    return `<div class="lib-answer" data-status="${a.status}"><p>${esc(a.resumen)}</p>` +
      (pts ? `<ul class="lit-list">${pts}</ul>` : `<p class="meta">${esc(a.reason ?? '')}</p>`) +
      (a.relacion_con_escenarios ? `<p class="meta">Escenarios: ${esc(a.relacion_con_escenarios)}</p>` : '') +
      (warn ? `<ul class="lit-list lib-warn">${warn}</ul>` : '') + '</div>'
  }

  private paint(q = '', sc = ''): void {
    const c = this.cat
    const states = (m: Record<string, number>): string =>
      Object.entries(m).map(([s, n]) => `${n} ${esc(s)}`).join(', ') || '—'
    const rows = c ? c.books.map((b) => `<tr><td>${esc(b.title)}<br><span class="muted">${esc(b.author)}${b.year ? ` (${b.year})` : ''}</span></td>` +
      `<td>${b.pages_with_text}/${b.pages ?? '?'}${b.index_status === 'sin_ingerir' ? ' <span class="muted">sin ingerir</span>' : ''}</td>` +
      `<td>${states(b.cards_by_status)}</td></tr>`).join('') : ''
    const dis = c?.llm_enabled ? '' : ' disabled'
    const opts = Object.entries(SCENARIOS).map(([k, v]) => `<option value="${k}"${k === sc ? ' selected' : ''}>${v}</option>`).join('')
    this.root.innerHTML = `<div class="lib"><h4>Biblioteca</h4>` +
      `<p class="meta">${esc(this.mode())} · ${TAG}</p>` +
      (c ? `<table class="lib-cat"><thead><tr><th>Libro</th><th>Págs. con texto</th><th>Fichas por estado</th></tr></thead><tbody>${rows}</tbody></table>` +
        `<p class="meta">${c.cards_total} fichas · ${states(c.cards_by_status)}</p>`
        : '<p class="meta">Catálogo no disponible.</p>') +
      `<div class="lib-form"><input id="lib-q" type="text" maxlength="400" placeholder="¿Qué dice la literatura sobre…?" value="${esc(q)}"${dis}>` +
      `<select id="lib-sc"${dis}>${opts}</select>` +
      `<button id="lib-ask"${dis}>Preguntar</button>` +
      `<button id="lib-ask-sc"${dis}>Preguntar por el escenario</button></div>` +
      (dis ? '<p class="meta">Consulta apagada: define EIM_LIBRARY_LLM=1 y ANTHROPIC_API_KEY y reinicia la API.</p>' : '') +
      `<div class="lib-out">${this.answer}</div><p class="meta lit-tag">${TAG}</p></div>`
  }
}
