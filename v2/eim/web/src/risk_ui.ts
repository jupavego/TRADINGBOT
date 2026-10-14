import { esc } from './panels'

/** Pestaña Plan: el plan vigente (T13) con el tamaño aprobado o los motivos del veto (T29). */

const base = (): string =>
  (import.meta.env.VITE_API_URL as string | undefined) ?? `http://${location.hostname}:8000`

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
const MODE: Record<string, string> = { ANALISIS: 'Análisis', SIMULADO: 'Simulado', TESTNET: 'Testnet', REAL: 'Real' }

function killBox(k: Kill): string {
  return k.active
    ? `<div class="alert risk-kill" role="alert">⛔ Kill-switch ACTIVO (${esc(k.by)}): ${esc(k.reason)} — ` +
      'no se aceptan órdenes nuevas y se pide cierre ordenado. ' +
      '<button class="btn" data-kill="off">Desactivar (manual)</button></div>'
    : '<p class="muted">Kill-switch inactivo. <button class="btn" data-kill="on">Activar kill-switch</button></p>'
}

function body(v: RiskView): string {
  const head = `<p class="muted"><b>Modo: ${esc(MODE[v.mode] ?? v.mode)}</b> — el motor de riesgo ` +
    `decide el tamaño; sin órdenes reales. Configuración ${esc(v.config.version)} · riesgo por operación ` +
    `${pct(v.config.risk_per_trade)} · apalancamiento máx. ${v.config.max_leverage}×.</p>`
  if (!v.plan || !v.decision) return head + killBox(v.kill_switch) + `<p class="muted">${esc(v.detail ?? 'Sin plan vigente.')}</p>`
  const p = v.plan, d = v.decision
  const plan = `<table class="metrics risk-plan"><tr><td>Plan</td><td>${p.side > 0 ? 'Largo' : 'Corto'} ${esc(p.symbol)}</td></tr>` +
    `<tr><td>Entrada</td><td>${px(p.entry)}</td></tr><tr><td>Stop loss</td><td>${px(p.sl)}</td></tr>` +
    p.tp.map((t, i) => `<tr><td>TP${i + 1}</td><td>${px(t)}</td></tr>`).join('') +
    `<tr><td>R:R</td><td>${p.rr === null ? '—' : p.rr.toFixed(2)}</td></tr></table>`
  const verdict = d.approved
    ? `<div class="risk-ok" data-ok="true"><b>✔ Aprobado</b> · tamaño <b class="num">${d.size.toPrecision(4)}</b> ` +
      `(nocional ${px(d.notional)} USDT) · ${d.leverage.toFixed(0)}× aislado · margen ${px(d.margin)} · ` +
      `riesgo hasta SL ${px(d.risk_amount)} (${pct(d.risk_frac)}) · liquidación ${d.liquidation_price === null ? '—' : px(d.liquidation_price)}` +
      (d.reasons.length ? `<ul class="warn">${d.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>` : '') + '</div>'
    : `<div class="risk-ok" data-ok="false"><b>✖ Vetado</b> por el motor de riesgo:` +
      `<ul class="warn">${d.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul></div>`
  const checks = '<details><summary>Reglas evaluadas</summary><table class="log"><tbody>' +
    d.checks.map((c) => `<tr><td>${c.ok ? '✔' : '✖'}</td><td>${esc(c.rule)}</td><td class="muted">${esc(c.detail)}</td></tr>`).join('') +
    `</tbody></table><p class="muted">Cuenta: ${esc(d.account_source)}` +
    (v.account ? ` · capital ${px(v.account.equity)} USDT` : '') + '</p></details>'
  return head + killBox(v.kill_switch) + `<div class="risk-grid">${plan}${verdict}</div>` + checks
}

export class RiskPanel {
  constructor(private el: HTMLElement, private ctx: () => { symbol: string; tf: string }) {
    el.addEventListener('click', (e) => {
      const b = (e.target as HTMLElement).closest<HTMLButtonElement>('button[data-kill]')
      if (!b) return
      const on = b.dataset.kill === 'on'
      if (on && !confirm('¿Activar el kill-switch? Bloquea nuevas órdenes hasta desactivarlo a mano.')) return
      const q = on ? '?reason=' + encodeURIComponent('activado desde la interfaz') : ''
      void fetch(`${base()}/v2/risk/kill-switch/${on ? 'activate' : 'deactivate'}${q}`, { method: 'POST' })
        .then(() => this.reload())
    })
  }

  async reload(): Promise<void> {
    const { symbol, tf } = this.ctx()
    try {
      const r = await fetch(`${base()}/v2/risk?symbol=${symbol}&tf=${tf}`)
      if (!r.ok) throw new Error(r.statusText)
      this.el.innerHTML = body((await r.json()) as RiskView)
    } catch (e) {
      this.el.innerHTML = `<p class="muted">No se pudo consultar el motor de riesgo: ${esc((e as Error).message)}</p>`
    }
  }
}
