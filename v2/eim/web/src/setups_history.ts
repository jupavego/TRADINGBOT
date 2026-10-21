import { base } from './api'
import { esc } from './panels'
import { bogIso } from './tz'

/**
 * Historial de sugerencias (T51): lo que el panel publicó, qué habría pasado con cada una en el
 * bróker simulado (`GET /v2/setups/history`), señal contra resultado por estrategia@marco@versión,
 * acierto real, R acumulado, tiempo sin sugerencias y versiones en revisión. Ninguna sugerencia
 * aparece como ejecutada: es la resolución simulada de una oportunidad potencial. Modo: Análisis.
 */

interface Resolution {
  state: string; reason?: string; fill_t?: number | null; exit_t?: number | null
  r?: number | null; mfe_r?: number; mae_r?: number; cause?: string | null
}
interface Row {
  id: string; vid: string; side: number; kind: string; entry: number; sl: number; tp: number
  published_ms: number; reason: string; state: string; executed: boolean; resolution: Resolution
}
interface Card {
  vid: string; published: number; closed: number; open: number; not_filled: number
  realized_mean_r: number | null; cum_r: number; hit_rate: number | null; last_n: number
  expected: { mean_r: number | null; ci95: [number | null, number | null] }
  against: 'dentro' | 'debajo' | 'encima' | 'sin_muestra'
  fill_real: number | null; fill_sim: number | null; fill_n: [number, number]; in_review: boolean
}
interface Gap { from: number; to: number; status: string; message: string }
interface History {
  now: number; note: string
  totals: { published: number; closed: number; cum_r: number; hit_rate: number | null; mean_r: number | null }
  scorecard: Card[]; published: Row[]; gaps: Gap[]
  gap_summary: { window_ms: number; ms_by_status: Record<string, number>; ms_total: number; intervals: number }
  in_review: { vid: string; since: number; mean_r: number; ci_low: number; n: number }[]
  watch?: { totals: History['totals']; scorecard: Card[]; published: Row[] }
}

const nf = (x: number, d = 2): string => x.toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d })
const sg = (x: number): string => (x > 0 ? '+' : x < 0 ? '−' : '')
const rr = (x: number | null | undefined): string => (x === null || x === undefined ? '—' : `${sg(x)}${nf(Math.abs(x), 2)} R`)
const pct0 = (x: number | null): string => (x === null ? '—' : `${Math.round(x * 100)} %`)
const utc = (t: number): string => bogIso(t).slice(5, 16).replace('T', ' ')
const hrs = (ms: number): string => `${nf(ms / 3_600_000, 1)} h`
const AGAINST: Record<string, string> = {
  dentro: 'dentro del IC95 % esperado', debajo: 'por debajo del IC95 % esperado',
  encima: 'por encima del IC95 % esperado', sin_muestra: 'aún sin muestra suficiente',
}
const STATE: Record<string, string> = {
  pendiente: 'pendiente', abierta: 'abierta (simulada)', cerrada: 'cerrada', no_llenada: 'no llenada',
  rechazada: 'rechazada', sin_datos: 'sin datos',
}
const GAP: Record<string, string> = {
  sin_validadas: 'sin operaciones validadas', sin_senal: 'validadas pero sin señal', datos_viejos: 'datos desactualizados',
}

export class SetupsHistory {
  private view: History | null = null
  private error = ''
  private symbol = 'BTCUSDT'
  private timer: number | undefined
  private abort: AbortController | null = null

  constructor(private el: HTMLElement) { this.paint() }

  setSymbol(sym: string): void {
    if (sym !== this.symbol) { this.symbol = sym; this.view = null; this.paint() }
    void this.reload()
  }

  soon(): void { clearTimeout(this.timer); this.timer = window.setTimeout(() => void this.reload(), 2500) }

  async reload(): Promise<void> {
    this.abort?.abort(); this.abort = new AbortController()
    try {
      const r = await fetch(`${base()}/v2/setups/history?symbol=${this.symbol}&limit=30`, { signal: this.abort.signal })
      if (!r.ok) throw new Error(String((await r.json().catch(() => ({}))).detail ?? r.statusText))
      this.view = await r.json() as History; this.error = ''
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      this.view = null; this.error = (e as Error).message
    }
    this.paint()
  }

  private card(c: Card): string {
    const [dec, simDec] = c.fill_n
    const ci = c.expected.ci95[0] === null || c.expected.ci95[1] === null
      ? '—' : `[${rr(c.expected.ci95[0])}, ${rr(c.expected.ci95[1])}]`
    return `<tr data-against="${c.against}"${c.in_review ? ' data-review="true"' : ''}>` +
      `<td><b>${esc(c.vid)}</b>${c.in_review ? ' <span class="su-tag" data-ok="false">en revisión</span>' : ''}</td>` +
      `<td class="num">${c.published}</td><td class="num">${c.closed}</td>` +
      `<td class="num">${rr(c.realized_mean_r)}</td><td class="num">${rr(c.expected.mean_r)} ${ci}</td>` +
      `<td>${AGAINST[c.against]}</td><td class="num">${pct0(c.hit_rate)}</td><td class="num">${rr(c.cum_r)}</td>` +
      `<td class="num">${pct0(c.fill_real)} (n ${dec}) / ${pct0(c.fill_sim)} (n ${simDec})</td></tr>`
  }

  private row(r: Row): string {
    const x = r.resolution
    const res = x.state === 'cerrada' ? `${STATE.cerrada} ${esc(x.reason ?? '')} · ${rr(x.r)}` +
      (x.cause ? ` · ${esc(x.cause)}` : '') : (STATE[x.state] ?? esc(x.state))
    return `<tr><td>${utc(r.published_ms)}</td><td><b>${esc(r.vid)}</b></td>` +
      `<td>${r.side > 0 ? 'LONG' : 'SHORT'}</td><td class="num">${nf(r.entry)} / ${nf(r.sl)} / ${nf(r.tp)}</td>` +
      `<td>${res}</td><td class="muted">${r.executed ? 'ejecutada' : 'sugerida · no ejecutada'}</td></tr>`
  }

  /** Ideas en observación registradas y resueltas en simulado: no validadas, solo para seguirlas. */
  private watch(v: History): string {
    const w = v.watch
    if (!w || !w.totals.published) return ''
    const t = w.totals
    const rows = w.published.map((r) => this.row(r).replace('sugerida · no ejecutada', 'observación · no validada'))
    return '<h4 class="sh su-wh">Ideas en observación <span class="muted">· no validadas, resolución simulada</span></h4>' +
      `<p class="su-stats">Registradas <b>${t.published}</b> · cerradas <b>${t.closed}</b> · acierto <b>${pct0(t.hit_rate)}</b> · ` +
      `R acumulado <b>${rr(t.cum_r)}</b> · R medio <b>${rr(t.mean_r)}</b></p>` +
      '<div class="su-tbl"><table><thead><tr><th>Registrada (COT)</th><th>Versión</th><th>Lado</th>' +
      `<th>Entrada / SL / TP</th><th>Resolución simulada</th><th>Estado</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`
  }

  private paint(): void {
    const v = this.view
    const head = '<div class="su-head"><h3 class="sh">Historial de sugerencias</h3>' +
      '<span class="sim">Análisis · resolución simulada, nada se ejecutó</span></div>'
    let body: string
    if (this.error) body = `<p class="muted">No se pudo cargar el historial: ${esc(this.error)}</p>`
    else if (!v) body = '<p class="muted">Cargando historial…</p>'
    else {
      const t = v.totals, g = v.gap_summary
      const gaps = Object.entries(g.ms_by_status).map(([k, ms]) => `${GAP[k] ?? k} ${hrs(ms)}`).join(' · ')
      const kpi = `<p class="su-stats">Publicadas <b>${t.published}</b> · resueltas (cerradas) <b>${t.closed}</b> · ` +
        `acierto real <b>${pct0(t.hit_rate)}</b> · R acumulado <b>${rr(t.cum_r)}</b> · ` +
        `tiempo sin sugerencias (7 d observados) <b>${hrs(g.ms_total)}</b>${gaps ? ` — ${gaps}` : ''}</p>`
      const rev = v.in_review.length
        ? `<p class="su-warn">En revisión (excluidas del panel hasta un veredicto nuevo): ${v.in_review.map((x) =>
          `${esc(x.vid)} (R medio ${rr(x.mean_r)} de las últimas ${x.n} < límite ${rr(x.ci_low)})`).join('; ')}</p>`
        : '<p class="muted">Ninguna versión en revisión.</p>'
      const score = v.scorecard.length
        ? '<div class="su-tbl"><table><thead><tr><th>Versión</th><th>Publ.</th><th>Cerr.</th><th>R realizado</th>' +
          '<th>R esperado (IC95 %)</th><th>Señal contra resultado</th><th>Acierto</th><th>R acum.</th>' +
          `<th>Llenado real / simulado</th></tr></thead><tbody>${v.scorecard.map((c) => this.card(c)).join('')}</tbody></table></div>`
        : '<p class="muted">Aún no se publicó ninguna sugerencia: el panel dijo «Sin operaciones validadas» (o sin señal) y esos intervalos quedan registrados.</p>'
      const list = v.published.length
        ? '<div class="su-tbl"><table><thead><tr><th>Publicada (COT)</th><th>Versión</th><th>Lado</th>' +
          `<th>Entrada / SL / TP</th><th>Resolución simulada</th><th>Estado</th></tr></thead><tbody>${v.published.map((r) => this.row(r)).join('')}</tbody></table></div>`
        : ''
      const lastGap = v.gaps.length
        ? `<p class="muted">Último intervalo sin sugerencia: ${utc(v.gaps[v.gaps.length - 1].from)} → ${utc(v.gaps[v.gaps.length - 1].to)} COT · ${esc(GAP[v.gaps[v.gaps.length - 1].status] ?? v.gaps[v.gaps.length - 1].status)} · ${esc(v.gaps[v.gaps.length - 1].message)}</p>`
        : ''
      body = kpi + rev + score + list + lastGap + this.watch(v)
    }
    this.el.innerHTML = head + body +
      `<p class="muted su-foot">${v ? esc(v.note) : ''} Cada sugerencia se registra la primera vez que se publica y se resuelve con el motor del bróker simulado sobre las velas posteriores, sin anticipación.</p>`
  }
}
