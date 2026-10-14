import { base, executePlan, setKillSwitch } from './api'
import { esc } from './panels'

/** Pestaña Plan: el plan vigente (T13) con el tamaño aprobado o los motivos del veto (T29). */

interface Check { rule: string; ok: boolean; detail: string }
interface Decision {
  approved: boolean; side: number; mode: string; size: number; notional: number; leverage: number
  margin: number; risk_amount: number; risk_frac: number; liquidation_price: number | null
  reasons: string[]; checks: Check[]; config_version: string; account_source: string; decided_at: number
}
interface PlanReq { symbol: string; side: number; entry: number; sl: number; tp: number[]; rr: number | null; plan_id: string }
interface Kill { active: boolean; reason: string; by: string; since: number | null }
interface RiskView {
  mode: string; plan: PlanReq | null; decision: Decision | null; detail?: string
  kill_switch: Kill; config: { version: string; risk_per_trade: number; max_leverage: number }
  account?: { equity: number; source: string }
}

const px = (x: number): string => x.toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const pct = (x: number): string => `${(x * 100).toFixed(2)} %`
interface Trade { key: string; symbol: string; side: number; qty: number; filled: number; avg_entry: number | null; sl: number; tp: number | null; status: string; exit_reason: string }
interface Exec {
  mode: string; enabled: boolean; error: string; trades: Trade[]
  reconciliation: { ok: boolean; t: number; issues: string[]; actions: string[] } | null
}

const MODE: Record<string, string> = { ANALISIS: 'Análisis', SIMULADO: 'Simulado', TESTNET: 'Testnet', REAL: 'Real' }

function killBox(k: Kill): string {
  return k.active
    ? `<div class="alert risk-kill" role="alert">⛔ Kill-switch ACTIVO (${esc(k.by)}): ${esc(k.reason)} — ` +
      'no se aceptan órdenes nuevas y se pide cierre ordenado. ' +
      '<button class="btn" data-kill="off">Desactivar (manual)</button></div>'
    : '<p class="muted">Kill-switch inactivo. <button class="btn" data-kill="on">Activar kill-switch</button></p>'
}

function execBox(x: Exec | null): string {
  if (!x) return ''
  if (!x.enabled) return x.error ? `<p class="muted">Ejecución: ${esc(x.error)}</p>` : ''
  const rec = x.reconciliation
  const recon = rec === null ? '<p class="muted">Reconciliación: aún no corre.</p>'
    : `<p class="${rec.ok ? 'muted' : 'alert bad'}">Reconciliación ${new Date(rec.t).toLocaleTimeString('es-CO')}: ` +
      (rec.ok ? 'libro interno = exchange' : esc([...rec.issues, ...rec.actions].join(' · '))) + '</p>'
  const rows = x.trades.slice(-5).reverse().map((t) =>
    `<tr><td>${esc(t.status)}</td><td>${t.side > 0 ? 'Largo' : 'Corto'} ${esc(t.symbol)}</td>` +
    `<td class="num">${t.filled}/${t.qty}</td><td>${t.avg_entry === null ? '—' : px(t.avg_entry)}</td>` +
    `<td>SL ${px(t.sl)} · TP ${t.tp === null ? '—' : px(t.tp)}</td><td class="muted">${esc(t.exit_reason)}</td></tr>`).join('')
  return '<h4>Operaciones en testnet</h4>' + recon +
    (rows ? `<table class="log"><tbody>${rows}</tbody></table>` : '<p class="muted">Sin operaciones enviadas.</p>')
}

function body(v: RiskView, x: Exec | null): string {
  const testnet = v.mode === 'TESTNET'
  const head = `<p class="muted"><b>Modo: ${esc(MODE[v.mode] ?? v.mode)}</b> — el motor de riesgo ` +
    `decide el tamaño; ${testnet ? 'órdenes solo en la testnet de Binance (sin dinero real)' : 'sin órdenes reales'}. Configuración ${esc(v.config.version)} · riesgo por operación ` +
    `${pct(v.config.risk_per_trade)} · apalancamiento máx. ${v.config.max_leverage}×.</p>`
  if (!v.plan || !v.decision) return head + killBox(v.kill_switch) + `<p class="muted">${esc(v.detail ?? 'Sin plan vigente.')}</p>` + execBox(x)
  const p = v.plan, d = v.decision
  const plan = `<table class="metrics risk-plan"><tr><td>Plan</td><td>${p.side > 0 ? 'Largo' : 'Corto'} ${esc(p.symbol)}</td></tr>` +
    `<tr><td>Entrada</td><td>${px(p.entry)}</td></tr><tr><td>Stop loss</td><td>${px(p.sl)}</td></tr>` +
    p.tp.map((t, i) => `<tr><td>TP${i + 1}</td><td>${px(t)}</td></tr>`).join('') +
    `<tr><td>R:R</td><td>${p.rr === null ? '—' : p.rr.toFixed(2)}</td></tr></table>`
  const verdict = d.approved
    ? `<div class="risk-ok" data-ok="true"><b>✔ Aprobado</b> · tamaño <b class="num">${d.size.toPrecision(4)}</b> ` +
      `(nocional ${px(d.notional)} USDT) · ${d.leverage.toFixed(0)}× aislado · margen ${px(d.margin)} · ` +
      `riesgo hasta SL ${px(d.risk_amount)} (${pct(d.risk_frac)}) · liquidación ${d.liquidation_price === null ? '—' : px(d.liquidation_price)}` +
      (d.reasons.length ? `<ul class="warn">${d.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>` : '') +
      (testnet && x?.enabled ? '<p><button class="btn" data-exec="go">Ejecutar en testnet</button></p>' : '') + '</div>'
    : `<div class="risk-ok" data-ok="false"><b>✖ Vetado</b> por el motor de riesgo:` +
      `<ul class="warn">${d.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul></div>`
  const checks = '<details><summary>Reglas evaluadas</summary><table class="log"><tbody>' +
    d.checks.map((c) => `<tr><td>${c.ok ? '✔' : '✖'}</td><td>${esc(c.rule)}</td><td class="muted">${esc(c.detail)}</td></tr>`).join('') +
    `</tbody></table><p class="muted">Cuenta: ${esc(d.account_source)}` +
    (v.account ? ` · capital ${px(v.account.equity)} USDT` : '') + '</p></details>'
  return head + killBox(v.kill_switch) + `<div class="risk-grid">${plan}${verdict}</div>` + checks + execBox(x)
}

export class RiskPanel {
  constructor(private el: HTMLElement, private ctx: () => { symbol: string; tf: string }) {
    el.addEventListener('click', (e) => {
      const go = (e.target as HTMLElement).closest<HTMLButtonElement>('button[data-exec]')
      if (go) {
        const { symbol, tf } = this.ctx()
        if (!confirm(`¿Enviar el plan aprobado de ${symbol} a la testnet? El riesgo se reevalúa en el servidor.`)) return
        go.disabled = true
        executePlan(symbol, tf)
          .then((r) => { if (!r.executed) alert('El motor de riesgo ya no aprueba el plan: no se envió.') })
          .catch((err: Error) => alert(`No se pudo ejecutar: ${err.message}`))
          .finally(() => this.reload())
        return
      }
      const b = (e.target as HTMLElement).closest<HTMLButtonElement>('button[data-kill]')
      if (!b) return
      const on = b.dataset.kill === 'on'
      if (on && !confirm('¿Activar el kill-switch? Bloquea nuevas órdenes hasta desactivarlo a mano.')) return
      setKillSwitch(on, on ? 'activado desde la interfaz' : 'desactivado desde la interfaz')
        .then(() => this.reload())
        .catch((err: Error) => alert(`No se pudo cambiar el kill-switch: ${err.message}. ` +
          'Verifica el estado antes de seguir.'))
    })
  }

  /** En reproducción la decisión de riesgo no se reconstruye: se dice explícitamente. */
  replayNote(): void {
    this.el.innerHTML = '<p class="muted">Reproducción: la decisión de riesgo solo se calcula en vivo ' +
      '(consulta el registro en <code>/v2/risk/decisions</code>). Vuelve a en vivo para verla.</p>'
  }

  async reload(): Promise<void> {
    const { symbol, tf } = this.ctx()
    try {
      const [r, e] = await Promise.all([fetch(`${base()}/v2/risk?symbol=${symbol}&tf=${tf}`),
        fetch(`${base()}/v2/execution`).catch(() => null)])
      if (!r.ok) throw new Error(r.statusText)
      const x = e?.ok ? (await e.json()) as Exec : null
      this.el.innerHTML = body((await r.json()) as RiskView, x)
    } catch (e) {
      this.el.innerHTML = `<p class="muted">No se pudo consultar el motor de riesgo: ${esc((e as Error).message)}</p>`
    }
  }
}
