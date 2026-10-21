import { base, setKillSwitch, SYMBOLS } from './api'
import { esc } from './panels'

/** Pestaña Operación (T31): servicio continuo, posición, P&L, riesgo usado, vetos, alertas,
 *  kill-switch e informes. Se refresca sola mientras está visible. Nunca dinero real. */

interface Used { value: number; limit: number; frac: number | null }
interface Pos { key: string; symbol: string; side: number; filled: number; avg_entry: number | null; sl: number; tp: number | null; last: number | null; upnl: number | null; risk: number | null; leverage: number; opened_at: number | null }
interface Alert { t: number; kind: string; level: string; title: string; detail: string; resolved: boolean }
interface Service {
  state: string; last_heartbeat: number | null; cycles: number; failures: number; consecutive_failures: number
  last_error: string; next_cycle_at: number | null; poll_s: number; timeframe: string; symbols: string[]
  last_cycle: { t: number; ok: boolean; errors: string[]; decisions: { symbol: string; approved: boolean | null; executed: boolean; reasons: string[] }[] } | null
}
interface Op {
  now: number; mode: string; execution_enabled: boolean; execution_error: string; service: Service | null
  positions: Pos[]; pnl: Record<string, number | string | null>; risk: Record<string, Used>
  vetoed: { t: number; symbol: string; side: number; reasons: string[] }[]
  alerts: Alert[]; active_alerts: string[]; alert_sink_errors: string[]
  kill_switch: { active: boolean; reason: string; by: string; since: number | null }
  reconciliation: { ok: boolean; t: number; issues: string[]; actions: string[] } | null
  reports: string[]
}

const MODE: Record<string, string> = { ANALISIS: 'Análisis', SIMULADO: 'Simulado', TESTNET: 'Testnet', REAL: 'Real' }
const STATE: Record<string, string> = { iniciando: 'Iniciando', operando: 'Operando', reintentando: 'Reintentando', detenido: 'Detenido' }
const RISK_LABEL: Record<string, string> = {
  open_risk: 'Riesgo abierto', daily_loss: 'Pérdida del día', weekly_loss: 'Pérdida de la semana',
  drawdown: 'Drawdown (kill-switch)', open_trades: 'Posiciones abiertas', consecutive_losses: 'Pérdidas seguidas',
}
const usd = (x: number | null | undefined): string =>
  x === null || x === undefined ? '—' : x.toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const pct = (x: number | null | undefined): string => (x === null || x === undefined ? '—' : `${(x * 100).toFixed(2)} %`)
const hhmm = (t: number | null): string => (t === null ? '—' : new Date(t).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Bogota' }))
const ago = (now: number, t: number | null): string => (t === null ? 'nunca' : `hace ${Math.max(0, Math.round((now - t) / 1000))} s`)

function service(o: Op): string {
  const s = o.service
  if (!s) {
    return '<div class="alert">Servicio de operación apagado. Arráncalo desde <code>v2/</code> con ' +
      '<code>python -m eim.operation run</code> (paper) — reinicio automático, latido y registro incluidos.' +
      (o.execution_error ? ` Ejecución: ${esc(o.execution_error)}` : '') + '</div>'
  }
  const stale = s.last_heartbeat === null || o.now - s.last_heartbeat > Math.max(180, 4 * s.poll_s) * 1000
  const lc = s.last_cycle
  return `<table class="metrics op-svc" data-state="${esc(s.state)}"><tbody>` +
    `<tr><td>Estado</td><td><b class="op-state">${esc(STATE[s.state] ?? s.state)}</b>${stale ? ' · <span class="bad">latido atrasado</span>' : ''}</td></tr>` +
    `<tr><td>Latido</td><td>${ago(o.now, s.last_heartbeat)}</td></tr>` +
    `<tr><td>Ciclos / fallos</td><td>${s.cycles} / ${s.failures}${s.consecutive_failures ? ` (${s.consecutive_failures} seguidos)` : ''}</td></tr>` +
    `<tr><td>Marco · símbolos</td><td>${esc(s.timeframe)} · ${esc(s.symbols.join(', '))}</td></tr>` +
    `<tr><td>Próximo ciclo</td><td>${hhmm(s.next_cycle_at)}</td></tr>` +
    (lc ? `<tr><td>Último ciclo</td><td>${lc.ok ? '✔' : '✖'} ${hhmm(lc.t)}</td></tr>` : '') +
    '</tbody></table>' +
    (s.last_error ? `<p class="alert bad">Último error: ${esc(s.last_error)}</p>` : '')
}

function kill(o: Op): string {
  const k = o.kill_switch
  return k.active
    ? `<div class="alert risk-kill op-kill" role="alert">⛔ Kill-switch ACTIVO desde ${hhmm(k.since)} (${esc(k.by)}): ${esc(k.reason)}. ` +
      'Sin órdenes nuevas; el servicio cierra las posiciones de forma ordenada. ' +
      '<button class="btn" data-kill="off">Desactivar (manual)</button></div>'
    : '<div class="op-kill"><button class="btn op-kill-btn" data-kill="on">⛔ Activar kill-switch</button> ' +
      '<span class="muted">bloquea órdenes nuevas y cierra todo; solo se desactiva a mano.</span></div>'
}

function positions(o: Op): string {
  if (!o.execution_enabled) return '<p class="muted">Sin broker: no hay posiciones (EIM_EXECUTION=paper o testnet).</p>'
  if (!o.positions.length) return '<p class="muted">Sin posiciones abiertas.</p>'
  return '<table class="log"><thead><tr><th>Posición</th><th>Cant.</th><th>Entrada</th><th>Último</th><th>SL · TP</th><th>P&L no realizado</th><th>Riesgo</th></tr></thead><tbody>' +
    o.positions.map((p) => `<tr><td>${p.side > 0 ? 'Largo' : 'Corto'} ${esc(p.symbol)} ${p.leverage}×</td>` +
      `<td class="num">${p.filled}</td><td>${usd(p.avg_entry)}</td><td>${usd(p.last)}</td>` +
      `<td>${usd(p.sl)} · ${usd(p.tp)}</td><td class="num" data-sign="${Math.sign(p.upnl ?? 0)}">${usd(p.upnl)}</td>` +
      `<td>${usd(p.risk)}</td></tr>`).join('') + '</tbody></table>'
}

function pnl(o: Op): string {
  const p = o.pnl
  if (!o.execution_enabled || !('equity' in p)) return p.error ? `<p class="alert bad">${esc(String(p.error))}</p>` : ''
  const n = (k: string): number | null => (typeof p[k] === 'number' ? (p[k] as number) : null)
  return '<table class="metrics op-pnl"><tbody>' +
    `<tr><td>Capital (${esc(MODE[o.mode] ?? o.mode)})</td><td>${usd(n('equity'))} USDT</td></tr>` +
    `<tr><td>Desde el inicio</td><td>${pct(n('total_return'))} (base ${usd(n('start_equity'))})</td></tr>` +
    `<tr><td>Hoy · semana</td><td>${usd(n('day_change'))} · ${usd(n('week_change'))}</td></tr>` +
    `<tr><td>Realizado bruto (${n('n_closed') ?? 0} cerradas)</td><td>${usd(n('realized_gross'))}</td></tr>` +
    `<tr><td>No realizado</td><td>${usd(n('unrealized'))}</td></tr>` +
    `<tr><td>Drawdown desde el pico</td><td>${pct(n('drawdown'))}</td></tr>` +
    `</tbody></table><p class="muted">Fuente: ${esc(String(p.source ?? ''))}</p>`
}

function risk(o: Op): string {
  const rows = Object.entries(o.risk)
  if (!rows.length) return ''
  return '<table class="metrics op-risk"><tbody>' + rows.map(([k, u]) => {
    const f = Math.min(1, Math.max(0, u.frac ?? 0))
    const lvl = f >= 1 ? 'bad' : f >= 0.66 ? 'warn' : 'ok'
    const fmt = k === 'open_trades' || k === 'consecutive_losses' ? (x: number) => String(x) : pct
    return `<tr><td>${esc(RISK_LABEL[k] ?? k)}</td><td><meter min="0" max="1" low="0.66" high="0.99" optimum="0" value="${f}" data-lvl="${lvl}"></meter> ` +
      `${fmt(u.value)} / ${fmt(u.limit)}</td></tr>`
  }).join('') + '</tbody></table>'
}

function alerts(o: Op): string {
  const head = o.active_alerts.length
    ? `<p class="alert bad">Activas: ${esc(o.active_alerts.join(', '))}</p>` : '<p class="muted">Sin alertas activas.</p>'
  const sink = o.alert_sink_errors.length ? `<p class="muted">Aviso local con errores: ${esc(o.alert_sink_errors.at(-1) ?? '')}</p>` : ''
  const list = o.alerts.slice(0, 15).map((a) => `<tr data-level="${esc(a.level)}"><td>${hhmm(a.t)}</td>` +
    `<td>${a.resolved ? '✔' : a.level === 'critical' ? '⛔' : a.level === 'warn' ? '⚠' : 'ℹ'}</td>` +
    `<td>${esc(a.title)}</td><td class="muted">${esc(a.detail)}</td></tr>`).join('')
  return head + sink + (list ? `<table class="log op-alerts"><tbody>${list}</tbody></table>` : '')
}

const inFocus = (sym: string): boolean => (SYMBOLS as readonly string[]).includes(sym)

function vetoed(o: Op): string {
  const vs = o.vetoed.filter((v) => inFocus(v.symbol))   // solo el activo en foco
  if (!vs.length) return '<p class="muted">Sin vetos en los últimos 7 días.</p>'
  return '<table class="log"><tbody>' + vs.slice(0, 10).map((v) =>
    `<tr><td>${hhmm(v.t)}</td><td>${v.side > 0 ? 'Largo' : 'Corto'} ${esc(v.symbol)}</td>` +
    `<td class="muted">${esc(v.reasons.join(' · '))}</td></tr>`).join('') + '</tbody></table>'
}

function reports(o: Op): string {
  const list = o.reports.slice().reverse().map((n) => `<li><button class="link" data-report="${esc(n)}">${esc(n)}</button></li>`).join('')
  return `<p>${o.service ? '<button class="btn" data-mkreport="1">Generar informe de la semana en curso</button>' : ''}</p>` +
    (list ? `<ul class="op-reports">${list}</ul>` : '<p class="muted">Aún no hay informes (el semanal sale cada domingo 7:00 p. m., hora de Bogotá).</p>') +
    '<pre class="op-report" hidden></pre>'
}

function body(o: Op): string {
  const rec = o.reconciliation
  return `<p class="muted"><b>Modo: ${esc(MODE[o.mode] ?? o.mode)}</b> — ` +
    (o.mode === 'TESTNET' ? 'órdenes en la testnet de Binance' : 'papel con el simulador (SimBroker)') +
    '; sin dinero real. La decisión de pasar a capital real la toma el usuario por escrito.</p>' +
    kill(o) +
    `<div class="op-grid"><section><h4>Servicio</h4>${service(o)}` +
    (rec ? `<p class="${rec.ok ? 'muted' : 'alert bad'}">Reconciliación ${hhmm(rec.t)}: ${rec.ok ? 'libro = broker' : esc([...rec.issues, ...rec.actions].join(' · '))}</p>` : '') +
    `</section><section><h4>P&L</h4>${pnl(o)}</section><section><h4>Riesgo usado</h4>${risk(o) || '<p class="muted">—</p>'}</section></div>` +
    `<h4>Posiciones</h4>${positions(o)}<h4>Alertas</h4>${alerts(o)}` +
    `<h4>Decisiones vetadas</h4>${vetoed(o)}<h4>Informes</h4>${reports(o)}`
}

async function post(url: string, confirmHeader: string): Promise<unknown> {
  const r = await fetch(url, { method: 'POST', headers: { 'X-EIM-Confirm': confirmHeader } })
  const b = await r.json().catch(() => ({ detail: r.statusText }))
  if (!r.ok) throw new Error(String((b as { detail?: string }).detail ?? r.statusText))
  return b
}

export class OperationPanel {
  private timer: number | undefined

  constructor(private el: HTMLElement, every_ms = 15_000) {
    el.addEventListener('click', (e) => void this.onClick(e))
    this.timer = window.setInterval(() => { if (!el.hidden) void this.reload() }, every_ms)
  }

  private async onClick(e: Event): Promise<void> {
    const t = e.target as HTMLElement
    const k = t.closest<HTMLButtonElement>('button[data-kill]')
    if (k) {
      const on = k.dataset.kill === 'on'
      if (on && !confirm('¿Activar el kill-switch? Bloquea órdenes nuevas y cierra las posiciones. Solo se desactiva a mano.')) return
      try { await setKillSwitch(on, on ? 'activado desde el panel Operación' : 'desactivado desde el panel Operación') } catch (err) {
        alert(`No se pudo cambiar el kill-switch: ${(err as Error).message}. Verifica el estado antes de seguir.`)
      }
      return this.reload()
    }
    if (t.closest('button[data-mkreport]')) {
      try { await post(`${base()}/v2/operation/report`, 'report') } catch (err) { alert(`No se pudo generar: ${(err as Error).message}`) }
      return this.reload()
    }
    const r = t.closest<HTMLButtonElement>('button[data-report]')
    if (r) {
      const pre = this.el.querySelector<HTMLElement>('.op-report')!
      const res = await fetch(`${base()}/v2/operation/report?name=${encodeURIComponent(r.dataset.report!)}`)
      pre.textContent = res.ok ? ((await res.json()) as { markdown: string }).markdown : `No se pudo leer: ${res.statusText}`
      pre.hidden = false
    }
  }

  async reload(): Promise<void> {
    try {
      const r = await fetch(`${base()}/v2/operation`)
      if (!r.ok) throw new Error(r.statusText)
      const open = this.el.querySelector<HTMLElement>('.op-report')
      const keep = open && !open.hidden ? open.textContent : null
      this.el.innerHTML = body((await r.json()) as Op)
      if (keep) { const p = this.el.querySelector<HTMLElement>('.op-report')!; p.textContent = keep; p.hidden = false }
    } catch (e) {
      this.el.innerHTML = `<p class="alert bad">No se pudo consultar la operación: ${esc((e as Error).message)}</p>`
    }
  }

  stop(): void { clearInterval(this.timer) }
}
