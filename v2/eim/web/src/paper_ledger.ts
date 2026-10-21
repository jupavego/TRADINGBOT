/** Registro fijo del bróker simulado: lo que ocurrió en vivo, escrito una vez y sin recalcular. */
import { base } from './api'
import { esc, getPaper, nf, px, REASON, rr, side, tone, usd, utc } from './paper_fmt'

interface LedgerRow {
  scope: 'perfil' | 'sombra'; profile: string; symbol: string; sid: string; timeframe: string; side: number
  kind: string; exit_t: number; fill_t: number | null; fill: number | null; exit_price: number | null
  reason: string | null; pnl_usdt: number | null; r: number | null; net_frac: number | null
  fees: number | null; slip: number | null; leverage: number | null; rules_version: string | null
  mech_version: string; recorded_ms: number; retro: boolean
}
interface LedgerResp { counts: Record<string, number>; error: string; rows: LedgerRow[] }

const PAGE = 200

export class PaperLedger {
  private scope: '' | 'perfil' | 'sombra' = ''
  private limit = PAGE
  private symbol = 'BTCUSDT'
  private abort: AbortController | null = null

  constructor(private el: HTMLElement) {
    el.addEventListener('click', (e) => {
      const b = (e.target as HTMLElement).closest<HTMLButtonElement>('button')
      if (!b) return
      if (b.dataset.scope !== undefined) { this.scope = b.dataset.scope as typeof this.scope; this.limit = PAGE; void this.load() }
      else if (b.dataset.more) { this.limit += 400; void this.load() }
    })
  }

  show(ctx: { symbol: string }): Promise<void> { this.symbol = ctx.symbol; return this.load() }

  private async load(): Promise<void> {
    this.abort?.abort()
    const ac = this.abort = new AbortController()
    const q = `?symbol=${this.symbol}&limit=${this.limit}${this.scope ? `&scope=${this.scope}` : ''}`
    try {
      const j = await getPaper<LedgerResp>(`/ledger${q}`, ac.signal)
      this.paint(j)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') this.el.innerHTML = `<p class="muted">No se pudo leer el registro fijo: ${esc(String((e as Error).message))}</p>`
    }
  }

  private paint(j: LedgerResp): void {
    const n = (s: string): number => j.counts[`${s}:${this.symbol}`] ?? 0
    const btn = (s: '' | 'perfil' | 'sombra', t: string): string =>
      `<button class="btn" data-scope="${s}" aria-pressed="${this.scope === s}">${t}</button>`
    const csv = `${base()}/v2/paper/ledger.csv?symbol=${this.symbol}${this.scope ? `&scope=${this.scope}` : ''}`
    const head = `<div class="pp-filters">${btn('', 'Todas')} ${btn('perfil', `De los perfiles (${n('perfil')})`)} ${btn('sombra', `Sombra (${n('sombra')})`)} ` +
      `<a class="btn" href="${csv}" download>Exportar CSV</a>` +
      (j.error ? ` <span class="down">error al registrar: ${esc(j.error)}</span>` : '') + '</div>' +
      '<p class="muted pp-note">Solo adición: cada fila se escribe cuando la operación decidida en vivo se cierra y no se recalcula si cambian reglas o costos. ' +
      'Incluye la versión de reglas y de mecánica de costos con la que se produjo. «retro» = registrada más de 2 h después del cierre (al estrenar el libro).</p>'
    if (!j.rows.length) { this.el.innerHTML = head + '<p class="muted">Aún no hay operaciones en vivo cerradas en el registro.</p>'; return }
    const rows = j.rows.map((r) => {
      const win = (r.scope === 'perfil' ? r.pnl_usdt : r.r) ?? 0
      return `<tr title="reglas ${esc(r.rules_version ?? '—')} · mecánica ${esc(r.mech_version)}">` +
        `<td class="num">${r.fill_t ? utc(r.fill_t) : '—'}<br><small class="muted">→ ${utc(r.exit_t)}${r.retro ? ' · retro' : ''}</small></td>` +
        `<td>${esc(r.sid)}<br><small class="muted">${r.scope === 'perfil' ? esc(r.profile) : 'sombra'} · ${r.kind === 'limit' ? 'límite' : 'mercado'}</small></td>` +
        `<td>${side(r.side)}${r.leverage ? ` <small class="muted">${r.leverage}x</small>` : ''}</td>` +
        `<td class="num">${r.fill ? px(r.fill) : '—'} → ${r.exit_price ? px(r.exit_price) : '—'}</td>` +
        `<td>${REASON[r.reason ?? ''] ?? r.reason ?? '—'}</td>` +
        `<td class="num ${tone(win)}"><b>${r.scope === 'perfil' ? `${usd(r.pnl_usdt ?? 0)} USDT` : rr(r.r)}</b>` +
        `${r.scope === 'perfil' ? `<br><small>${rr(r.r)}</small>` : ''}</td>` +
        `<td class="num"><small>com. ${nf(r.fees ?? 0, 4)} · desl. ${nf(r.slip ?? 0, 4)}</small></td></tr>`
    }).join('')
    const more = j.rows.length >= this.limit ? `<button class="btn" data-more="1">Ver más</button>` : ''
    this.el.innerHTML = head + `<div class="pp-scroll"><table class="pp-t"><thead><tr><th>Entrada → salida (COT)</th><th>Estrategia</th><th>Lado</th>` +
      `<th>Precio</th><th>Motivo</th><th>Resultado</th><th>Costos</th></tr></thead><tbody>${rows}</tbody></table></div>${more}`
  }
}
