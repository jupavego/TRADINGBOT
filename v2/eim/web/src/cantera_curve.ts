/** Cantera: capital por agente (suma de las cuentas de sus prospectos), en % frente a su capital
 * inicial. Es la pieza «Capital por perfil» del bróker, dibujada en SVG propio: sin el gráfico de
 * TradingView (pedido del usuario, 2026-11-20). Clic en un agente de la leyenda oculta o muestra
 * su curva. Capital realizado, al cierre de cada operación. */
import type { CtBalance } from './cantera_api'
import { agentColor } from './cantera_balance'
import { agentLabel, cot } from './cantera_fmt'
import { esc, nf, usd } from './paper_fmt'

const W = 1000, H = 260

function ticks(lo: number, hi: number): number[] {
  const span = hi - lo || 1
  const raw = span / 4
  const p = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((k) => k * p).find((s) => s >= raw) ?? raw
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v * 1e6) / 1e6)
  return out
}

export function canteraCurveView(b: CtBalance, hidden: Set<string>): string {
  const ids = b.agents.map((a) => a.agent_id)
  const shown = b.agents.filter((a) => !hidden.has(a.agent_id))
  const pts = shown.flatMap((a) => a.curve)
  const legend = b.agents.map((a) => {
    const off = hidden.has(a.agent_id)
    const cls = a.return_pct > 0 ? 'up' : a.return_pct < 0 ? 'down' : ''
    return `<button type="button" class="ct-leg" data-ct-agent="${esc(a.agent_id)}" aria-pressed="${!off}" ` +
      `title="${esc(`${agentLabel(a.agent_id)}: ${a.accounts} prospectos · capital ${usd(a.equity, 0)} de ${nf(a.initial, 0)} USDT · ${a.n} operaciones cerradas`)}">` +
      `<i style="background:${agentColor(a.agent_id, ids)}"></i><span>${esc(agentLabel(a.agent_id))}</span>` +
      `<b class="num ${cls}">${a.return_pct > 0 ? '+' : ''}${nf(a.return_pct, 2)} %</b><small>${a.n} op.</small></button>`
  }).join('')
  if (!pts.length) {
    return `<div class="ct-eqrow"><div class="ct-eq ct-eq-empty"><p class="muted">Elige al menos un agente para ver su curva.</p></div>` +
      `<div class="ct-eqleg" role="group" aria-label="Agentes">${legend}</div></div>`
  }
  const t0 = Math.min(...pts.map((p) => p.t)), t1 = Math.max(...pts.map((p) => p.t))
  let lo = Math.min(0, ...pts.map((p) => p.pct)), hi = Math.max(0, ...pts.map((p) => p.pct))
  if (hi - lo < 0.5) { lo -= 0.25; hi += 0.25 }
  const pad = (hi - lo) * 0.08
  lo -= pad; hi += pad
  const x = (t: number): number => (t1 === t0 ? W : ((t - t0) / (t1 - t0)) * W)
  const y = (v: number): number => H - ((v - lo) / (hi - lo)) * H
  const lines = shown.map((a) => {
    // escalón: el capital realizado cambia solo al cierre de cada operación
    let d = ''
    a.curve.forEach((p, i) => {
      d += i === 0 ? `M${x(p.t).toFixed(1)},${y(p.pct).toFixed(1)}` : `H${x(p.t).toFixed(1)}V${y(p.pct).toFixed(1)}`
    })
    return `<path d="${d}" fill="none" stroke="${agentColor(a.agent_id, ids)}" stroke-width="2" vector-effect="non-scaling-stroke"><title>${esc(agentLabel(a.agent_id))}</title></path>`
  }).join('')
  const grid = ticks(lo, hi).map((v) =>
    `<line x1="0" x2="${W}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" class="${v === 0 ? 'ct-eq-zero' : 'ct-eq-grid'}" vector-effect="non-scaling-stroke"/>`).join('')
  const labels = ticks(lo, hi).map((v) =>
    `<span class="ct-eq-y" style="top:${((y(v) / H) * 100).toFixed(2)}%">${v > 0 ? '+' : ''}${nf(v, Math.abs(v) < 1 && v !== 0 ? 2 : 1)} %</span>`).join('')
  return `<div class="ct-eqrow"><div class="ct-eq"><div class="ct-eq-plot"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" ` +
    `aria-label="Capital por agente en porcentaje frente a su capital inicial">${grid}${lines}</svg>${labels}</div>` +
    `<span class="ct-eq-x" data-k="a">${cot(t0)}</span><span class="ct-eq-x" data-k="b">${cot(t1)} COT</span></div>` +
    `<div class="ct-eqleg" role="group" aria-label="Agentes: ocultar o mostrar su curva">${legend}</div></div>`
}
