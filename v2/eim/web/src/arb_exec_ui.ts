import { base } from './api'
import { utc } from './arb_view'
import { esc } from './panels'

/** Fila de `GET /v2/arbitrage/execution` (T45). Cantidades en moneda base con signo. */
interface ExecPos {
  key: string; strategy: string; variant: string; asset: string; status: string; leverage: number
  created_at: number; opened_at: number | null; closed_at: number | null; exit_reason: string
  spot: number; futures: number; spot_symbol: string; futures_symbol: string; hedged: number; residual: number
  mark: number | null; liq_price: number | null; liq_move: number | null; margin_equity: number | null
  funding_expected: number; funding_received: number; funding_n: number; rebalances: number
  margin_added: number; incident_loss: number; pnl: number | null; net_bps: number | null; events: string[]
}
interface ExecDecision { strategy: string; variant: string; asset: string; approved: boolean; notional: number; net_bps: number; score: number; reasons: string[] }
interface ExecCycle { t: number; opened: string | null; skipped: string | null; actions: string[]; decisions: ExecDecision[] }
interface ExecPayload {
  mode: string; enabled: boolean; error: string; interval_s: number
  kill_switch: { active: boolean; reason: string }
  positions: ExecPos[]; last_cycle: ExecCycle | null
  reconciliation: { ok: boolean; connected: boolean; issues: string[]; actions: string[] } | null
  config: { version: string; strategies: string[]; max_notional_usd: number; max_leg_loss_bps: number } | null
  journal: { t: number; kind: string; msg?: string; key?: string; skipped?: string | null; opened?: string | null }[]
}

const STRAT: Record<string, string> = { funding_carry: 'Carry de funding', basis: 'Base trimestral' }
const ACTIVE = new Set(['PENDIENTE', 'ABIERTA', 'CERRANDO', 'DESCUBIERTA'])
const usd = (x: number | null | undefined, d = 2): string =>
  x == null ? '—' : `${x >= 0 ? '+' : '−'}${Math.abs(x).toLocaleString('es-CO', { maximumFractionDigits: d, minimumFractionDigits: d })}`
const qty = (x: number): string => `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(5)}`
const pct = (x: number | null): string => (x == null ? '—' : `${(x * 100).toFixed(1)} %`)

async function post(path: string, confirm: string): Promise<unknown> {
  const r = await fetch(`${base()}/v2/arbitrage/execution${path}`, { method: 'POST', headers: { 'X-EIM-Confirm': confirm } })
  const body = await r.json().catch(() => ({ detail: r.statusText }))
  if (!r.ok) throw new Error(String((body as { detail?: string }).detail ?? r.statusText))
  return body
}

/** Sección «Ejecución automática» de la pestaña Arbitraje (T45). Siempre modo Testnet. */
export class ArbExecPanel {
  readonly root = document.createElement('section')
  private data: ExecPayload | null = null
  private err = ''
  private busy = false

  constructor() {
    this.root.className = 'arb-exec'
    this.root.addEventListener('click', (e) => {
      const t = e.target as HTMLElement
      if (t.closest('#arbx-cycle')) void this.act(() => post('/cycle', 'arb-cycle'))
      else if (t.closest('#arbx-flatten')) {
        if (confirm('¿Cerrar TODOS los arbitrajes de testnet (ambas patas, a mercado si hace falta)?'))
          void this.act(() => post('/flatten', 'arb-flatten'))
      } else {
        const k = t.closest<HTMLElement>('[data-close]')?.dataset.close
        if (k && confirm('¿Cerrar este arbitraje (las dos patas)?'))
          void this.act(() => post(`/close?key=${encodeURIComponent(k)}`, 'arb-close'))
      }
    })
    void this.reload()
    window.setInterval(() => { if (this.root.isConnected && !this.root.closest('[hidden]')) void this.reload() }, 15_000)
  }

  async reload(): Promise<void> {
    try {
      const r = await fetch(`${base()}/v2/arbitrage/execution`)
      if (!r.ok) throw new Error(r.statusText)
      this.data = (await r.json()) as ExecPayload
      this.err = ''
    } catch (e) { this.err = `No se pudo consultar la ejecución: ${(e as Error).message}` }
    this.render()
  }

  private async act(fn: () => Promise<unknown>): Promise<void> {
    if (this.busy) return
    this.busy = true; this.render()
    try { await fn(); this.err = '' } catch (e) { this.err = (e as Error).message }
    this.busy = false
    await this.reload()
  }

  private head(d: ExecPayload | null): string {
    const ks = d?.kill_switch
    const state = !d ? '…' : d.enabled ? `activa · ciclo cada ${d.interval_s} s` : 'apagada'
    const dis = !d?.enabled || this.busy ? ' disabled' : ''
    return `<div class="scen-bar arb-head"><b>Ejecución automática</b>` +
      `<span class="mode" data-mode="TESTNET">Modo: Testnet</span>` +
      `<span class="muted">${esc(state)}${d?.config ? ` · ${esc(d.config.version)} · hasta ${d.config.max_notional_usd.toLocaleString('es-CO')} USD por arbitraje · tope por pata incompleta ${d.config.max_leg_loss_bps} pb` : ''}</span>` +
      (ks?.active ? `<span class="arb-kill">Kill-switch activo: ${esc(ks.reason)}</span>` : '') +
      `<button id="arbx-cycle"${dis}>${this.busy ? 'Ejecutando…' : 'Ejecutar ciclo'}</button>` +
      `<button id="arbx-flatten"${dis}>Cerrar todo</button></div>`
  }

  private cycle(c: ExecCycle | null): string {
    if (!c) return '<p class="muted">Aún no hay ciclos en este proceso.</p>'
    const dec = c.decisions.map((x) =>
      `<li data-ok="${x.approved}">${x.approved ? 'Aprobada' : 'Vetada'} · ${esc(STRAT[x.strategy] ?? x.strategy)} ${esc(x.asset)} ` +
      `(${x.net_bps.toFixed(1)} pb netos estimados, puntuación ${x.score.toFixed(2)})` +
      `${x.reasons.length ? `<small>${x.reasons.map(esc).join(' · ')}</small>` : ''}</li>`).join('')
    return `<p class="arbx-cycle">Último ciclo ${utc(c.t)}: ${c.opened ? '<b>abrió un arbitraje</b>' : esc(c.skipped ?? 'sin cambios')}` +
      `${c.actions.length ? ` · ${c.actions.map(esc).join(' · ')}` : ''}</p>${dec ? `<ul class="arbx-dec">${dec}</ul>` : ''}`
  }

  private table(rows: ExecPos[]): string {
    if (!rows.length) return '<p class="muted">Sin arbitrajes en testnet.</p>'
    const tr = rows.map((p) => {
      const live = ACTIVE.has(p.status)
      const fund = `${usd(p.funding_received, 4)} <small>esperado ${usd(p.funding_expected, 4)} · ${p.funding_n} pagos</small>`
      const marg = `${p.margin_equity == null ? '—' : usd(p.margin_equity)} <small>liquidación a ${pct(p.liq_move)}${p.liq_price ? ` (${p.liq_price.toLocaleString('es-CO', { maximumFractionDigits: 0 })})` : ''}</small>`
      return `<tr data-status="${esc(p.status)}"><td><b>${esc(STRAT[p.strategy] ?? p.strategy)} ${esc(p.asset)}</b><small>${esc(p.variant)} · ×${p.leverage}</small>` +
        `<small>${p.opened_at ? `abierta ${utc(p.opened_at)}` : `creada ${utc(p.created_at)}`}${p.closed_at ? ` · cerrada ${utc(p.closed_at)}` : ''}</small></td>` +
        `<td><b>${esc(p.status)}</b>${p.exit_reason ? `<small>${esc(p.exit_reason)}</small>` : ''}</td>` +
        `<td class="num">spot ${qty(p.spot)}<small>${esc(p.spot_symbol)}</small>futuros ${qty(p.futures)}<small>${esc(p.futures_symbol)} · neto ${qty(p.residual)}</small></td>` +
        `<td class="num">${fund}</td><td class="num">${marg}</td>` +
        `<td class="num">${p.rebalances}<small>${p.margin_added ? `+${p.margin_added.toFixed(2)} USDT` : ''}</small></td>` +
        `<td class="num">${p.incident_loss ? usd(-p.incident_loss) : '—'}</td>` +
        `<td class="num" data-dir="${(p.pnl ?? 0) >= 0 ? 'up' : 'down'}"><b>${usd(p.pnl)}</b></td>` +
        `<td>${live ? `<button data-close="${esc(p.key)}"${this.busy ? ' disabled' : ''}>Cerrar</button>` : ''}</td></tr>`
    }).join('')
    return '<div class="arb-scroll"><table class="arb-table arbx-table"><thead><tr><th>Arbitraje</th><th>Estado</th><th>Patas (base)</th>' +
      '<th>Funding real</th><th>Margen del corto</th><th>Rebal.</th><th>Pata incompleta</th><th>Resultado USD</th><th></th></tr></thead>' +
      `<tbody>${tr}</tbody></table></div>`
  }

  render(): void {
    const d = this.data
    const err = this.err || d?.error ? `<p class="scen-warn">${esc(this.err || d?.error || '')}</p>` : ''
    const off = d && !d.enabled
      ? '<p class="muted">Ejecución apagada. Para activarla en testnet: <code>EIM_ARB_EXECUTION=testnet</code> con claves de testnet ' +
        'spot y futuros (sin permiso de retiro) y reiniciar la API.</p>' : ''
    const rec = d?.reconciliation
    const recon = rec ? `<p class="muted">Reconciliación: ${rec.connected ? (rec.ok ? 'sin diferencias' : esc(rec.issues.join(' · ') || 'con avisos')) : 'sin conexión con el exchange'}</p>` : ''
    const journal = d?.journal.length
      ? `<details class="arb-watch" data-k="arbx-log"><summary>Bitácora (${d.journal.length} eventos recientes)</summary><ul class="arbx-log">` +
        d.journal.slice(0, 60).map((e) => `<li>${utc(e.t)} · <b>${esc(e.kind)}</b> ${esc(e.msg ?? e.skipped ?? (e.opened ? `abrió ${e.opened}` : ''))}</li>`).join('') +
        '</ul></details>' : ''
    const open = this.root.querySelector<HTMLDetailsElement>('details[data-k="arbx-log"]')?.open
    this.root.innerHTML = this.head(d) + err + off + (d?.enabled ? this.cycle(d.last_cycle) : '') +
      this.table(d?.positions ?? []) + recon + journal +
      '<p class="muted arb-foot">Solo testnet: precios y fills de la testnet de Binance (no del mercado real). Resultado = patas a precio ' +
      'medio de la testnet + funding cobrado, sin comisiones de futuros. Si la segunda pata falla se deshace la primera; el kill-switch es el ' +
      'mismo del carril direccional.</p>'
    const det = this.root.querySelector<HTMLDetailsElement>('details[data-k="arbx-log"]')
    if (det && open) det.open = true
  }
}
