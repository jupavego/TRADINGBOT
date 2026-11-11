/** Panel «Biblioteca digital» (T158): referencias en línea, lo leído de cada una y su trazabilidad.
 * Solo informa: de dónde sale cada recomendación y qué aportó el conocimiento a las operaciones. */
import './library_digital.css'
import {
  fetchDigContradictions, fetchDigLearning, fetchDigOverview, fetchDigRef, fetchDigRefs,
  type DigConsensus, type DigLearning, type DigOverview, type DigRef, type DigRefBrief, type DigSummary,
} from './library_digital_api'
import { esc } from './panels'

const TAG = 'Biblioteca digital · complemento del análisis, no es una señal ni un veto'
const ACCESS: Record<string, string> = { abierto: 'Abierto', gratuito: 'Gratuito', vista_previa: 'Vista previa', suscripcion: 'Suscripción', desconocido: '¿?' }
const READ: Record<string, string> = { texto_completo: 'leído completo', resumen: 'leído el resumen', metadatos: 'solo metadatos' }
const AVAIL: Record<string, string> = { '': 'Toda disponibilidad', texto_completo: 'Texto completo legal', solo_resumen: 'Solo resumen', solo_metadatos: 'Solo metadatos' }
const KIND: Record<string, string> = { apoya: 'Apoya', objeta: 'Objeta', condiciona: 'Condiciona' }

const num = (x: number | null | undefined, d = 2): string => x == null ? '—' : x.toFixed(d).replace('.', ',')
const pct = (x: number | null | undefined): string => x == null ? '—' : `${Math.round(x * 100)} %`

export class DigitalPanel {
  private ov: DigOverview | null = null
  private refs: DigRefBrief[] = []
  private detail: DigRef | null = null
  private learn: DigLearning | null = null
  private contra: DigConsensus[] = []
  private filt = { q: '', category: '', availability: '' }

  constructor(private root: HTMLElement) {
    root.onclick = (e) => {
      const t = e.target as HTMLElement
      const cat = t.closest<HTMLElement>('[data-cat]')
      if (cat) { this.filt.category = this.filt.category === cat.dataset.cat ? '' : cat.dataset.cat!; void this.search() }
      const row = t.closest<HTMLElement>('[data-ref]')
      if (row && !t.closest('a')) void this.open(row.dataset.ref!)
      if (t.id === 'dig-go') void this.search()
      if (t.id === 'dig-close') { this.detail = null; this.paint() }
    }
    root.onkeydown = (e) => { if ((e.target as HTMLElement).id === 'dig-q' && e.key === 'Enter') void this.search() }
  }

  async reload(): Promise<void> {
    const [ov, refs, learn, contra] = await Promise.allSettled([
      fetchDigOverview(), fetchDigRefs(this.filt), fetchDigLearning(), fetchDigContradictions()])
    this.ov = ov.status === 'fulfilled' ? ov.value : null
    this.refs = refs.status === 'fulfilled' ? refs.value.refs : []
    this.learn = learn.status === 'fulfilled' ? learn.value : null
    this.contra = contra.status === 'fulfilled' ? contra.value.concepts : []
    this.paint()
  }

  private async search(): Promise<void> {
    this.filt.q = this.root.querySelector<HTMLInputElement>('#dig-q')?.value.trim() ?? ''
    this.filt.availability = this.root.querySelector<HTMLSelectElement>('#dig-av')?.value ?? ''
    try { this.refs = (await fetchDigRefs(this.filt)).refs } catch { this.refs = [] }
    this.paint()
  }

  private async open(id: string): Promise<void> {
    try { this.detail = await fetchDigRef(id) } catch { this.detail = null }
    this.paint()
    this.root.querySelector('.dig-detail')?.scrollIntoView({ block: 'nearest' })
  }

  private kpis(o: DigOverview): string {
    const k = (v: string | number, l: string, t = ''): string => `<div class="kpi" title="${esc(t)}"><b>${v}</b><span>${l}</span></div>`
    return `<div class="kpi-row dig-kpis">${k(o.total_references, 'referencias', `${o.digital_total} digitales + ${o.local_books} libros locales`)}` +
      k(o.full_text, 'con texto completo legal', 'el registro da un enlace legal al texto completo') +
      k(o.partial, 'acceso parcial', 'solo resumen o metadatos') +
      k(`${o.read.texto_completo ?? 0} / ${o.read.resumen ?? 0}`, 'leídas: completas / resumen', 'lo que la investigación leyó de verdad') +
      k(o.pending_verification, 'pendientes de verificar') +
      k(`${o.stances_verified}/${o.stances}`, 'posturas comprobadas en el texto') +
      k(o.methods_identified, 'metodologías identificadas') + '</div>'
  }

  private cats(o: DigOverview): string {
    return '<div class="dig-cats">' + Object.entries(o.by_category).map(([c, v]) =>
      `<button data-cat="${c}" aria-pressed="${this.filt.category === c}"><b>${c}</b> ${esc(v.name)} <i>${v.n}</i></button>`).join('') + '</div>'
  }

  private list(): string {
    if (!this.refs.length) return '<p class="meta">Ninguna obra coincide.</p>'
    return `<table class="lib-cat dig-list"><thead><tr><th>Obra</th><th>Cat.</th><th>Acceso</th><th>Leído</th><th></th></tr></thead><tbody>` +
      this.refs.map((r) => `<tr data-ref="${esc(r.id)}" class="${this.detail?.id === r.id ? 'sel' : ''}">` +
        `<td>${esc(r.title)}<br><span class="muted">${esc(r.authors.slice(0, 3).join(', '))}${r.authors.length > 3 ? ' et al.' : ''} (${r.year ?? 's. f.'})</span></td>` +
        `<td>${esc(r.category)}</td><td><span class="dig-acc" data-a="${esc(r.access)}">${ACCESS[r.access] ?? esc(r.access)}</span></td>` +
        `<td class="muted">${READ[r.read] ?? esc(r.read)}</td>` +
        `<td>${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">Fuente ↗</a>` : ''}</td></tr>`).join('') +
      `</tbody></table><p class="meta">${this.refs.length} obras</p>`
  }

  private detailHtml(d: DigRef): string {
    const c = d.card
    const ok = new Set(c?.stances_verified ?? [])
    const stances = d.stances.map((s) => `<li><b>${KIND[s.kind] ?? esc(s.kind)}</b> · ${esc(s.concept)} · <i>${esc(s.level.replace('_', ' '))}</i> ` +
      `<span class="dig-ver" data-ok="${ok.has(s.concept)}">${ok.has(s.concept) ? 'comprobada en el texto' : 'pendiente de comprobar'}</span><br>${esc(s.summary)}` +
      (s.conditions ? ` <span class="muted">(${esc(s.conditions)})</span>` : '') + '</li>').join('')
    const frag = (xs: { text: string; where: string }[]): string => xs.map((f) =>
      `<li>«${esc(f.text)}» <span class="muted">— ${READ[f.where] ?? esc(f.where)}</span></li>`).join('')
    return `<div class="dig-detail"><button id="dig-close" class="dig-x" aria-label="Cerrar">×</button>` +
      `<h5>${esc(d.title)}</h5><p class="meta">${esc(d.authors.join(', '))} · ${d.year ?? 's. f.'} · ${esc(d.venue ?? d.publisher ?? '')} · ` +
      `${ACCESS[d.access] ?? esc(d.access)} · fiabilidad ${esc(d.reliability)} · verificada ${esc(d.verified_at ?? '—')}</p>` +
      `<p>${esc(d.description)} <span class="muted">(curado)</span></p>` +
      `<p class="meta">Metodologías: ${esc(d.methods.join('; ') || '—')} · Estudiado en: ${esc(d.markets.join(', ') || 'teoría o método')}</p>` +
      `<p class="meta">En el bot: ${esc(d.application)}</p>` +
      (d.related_strategies.length ? `<p class="meta">Estrategias relacionadas: ${d.related_strategies.map(esc).join(', ')}</p>` : '') +
      (stances ? `<h6>Posturas</h6><ul class="lit-list">${stances}</ul>` : '') +
      (c?.findings.length ? `<h6>Lo que dice el texto (${READ[c.coverage]})</h6><ul class="lit-list">${frag(c.findings)}</ul>` : '') +
      (c?.limitations.length ? `<h6>Limitaciones</h6><ul class="lit-list">${frag(c.limitations)}</ul>` : '') +
      (!c || c.coverage === 'metadatos' ? '<p class="meta">No se pudo leer el texto: solo hay metadatos; nada de esta obra se presenta como leído.</p>' : '') +
      `<p class="meta">${d.url ? `<a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">Página oficial ↗</a>` : ''}` +
      `${d.oa_url && d.oa_url !== d.url ? ` · <a href="${esc(d.oa_url)}" target="_blank" rel="noopener noreferrer">Texto legal ↗</a>` : ''}</p></div>`
  }

  private trace(): string {
    const l = this.learn
    if (!l) return '<p class="meta">Sin libro del bróker disponible.</p>'
    const row = (name: string, s: DigSummary): string => `<tr><td>${name}</td><td>${s.n}</td><td>${num(s.mean_r, 3)}</td>` +
      `<td>${s.ci_low == null ? '—' : `${num(s.ci_low)} … ${num(s.ci_high)}`}</td><td>${pct(s.win_rate)}</td></tr>`
    const tr = l.traces.map((t) => `<li>${esc(t.operacion.profile)} · ${esc(t.estrategia.strategy)} ${t.operacion.side > 0 ? '▲' : '▼'} → ` +
      `literatura ${t.literatura.stance > 0 ? 'a favor' : t.literatura.stance < 0 ? 'en contra' : 'sin postura'}` +
      (t.literatura.sources.length ? ` (${t.literatura.sources.slice(0, 2).map(esc).join('; ')})` : '') +
      ` → ${t.resultado.r == null ? '—' : `${num(t.resultado.r)} R`}</li>`).join('')
    return `<table class="lib-cat"><thead><tr><th>Operaciones</th><th>n</th><th>R medio</th><th>IC 95 %</th><th>Acierto</th></tr></thead><tbody>` +
      row('Respaldadas por la literatura', l.backed) + row('Sin postura', l.neutral) + row('Contradichas', l.contradicted) +
      `</tbody></table><p class="meta">${esc(l.verdict)}</p>` + (tr ? `<ul class="lit-list">${tr}</ul>` : '')
  }

  paint(): void {
    const o = this.ov
    if (!o) { this.root.innerHTML = '<div class="dig"><h4>Biblioteca digital</h4><p class="meta">No disponible.</p></div>'; return }
    const av = Object.entries(AVAIL).map(([v, l]) =>
      `<option value="${v}"${v === this.filt.availability ? ' selected' : ''}>${l}</option>`).join('')
    const res = o.recent_research.slice(0, 3).map((r) => `<li>${esc(r.at.slice(0, 16).replace('T', ' '))} · ${r.n} obras · ` +
      `${Object.entries(r.coverage).map(([k, v]) => `${v} ${READ[k] ?? k}`).join(', ')} · ${r.stances_verified} posturas comprobadas</li>`).join('')
    const con = this.contra.slice(0, 4).map((c) => `<li><b>${esc(c.name)}</b>: ${esc(c.verdict)} (neto ${num(c.net)}). ${esc(c.explanation[0] ?? '')}</li>`).join('')
    this.root.innerHTML = `<div class="dig"><h4>Biblioteca digital</h4><p class="meta">${esc(o.mode)} · ${TAG}</p>` +
      this.kpis(o) + this.cats(o) +
      `<div class="lib-form"><input id="dig-q" type="search" maxlength="120" placeholder="Título, autor o tema (p. ej. momentum, Kelly, funding)" value="${esc(this.filt.q)}">` +
      `<select id="dig-av">${av}</select><button id="dig-go">Buscar</button></div>` +
      (this.detail ? this.detailHtml(this.detail) : '') + this.list() +
      `<details class="dig-sec" open><summary>Trazabilidad: operaciones del bróker y literatura</summary>${this.trace()}</details>` +
      `<details class="dig-sec"><summary>Contradicciones entre fuentes (${o.contradictions})</summary><ul class="lit-list">${con || '<li>Ninguna.</li>'}</ul></details>` +
      `<details class="dig-sec"><summary>Últimas investigaciones</summary><ul class="lit-list">${res || '<li>Aún ninguna en este equipo.</li>'}</ul></details>` +
      `<p class="meta lit-tag">${TAG}</p></div>`
  }
}
