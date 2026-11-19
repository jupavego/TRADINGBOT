/** Ficha del prospecto de la cantera (T171): teoría en una frase, variables, parámetros citados,
 * obras que lo respaldan o contradicen (T157) y su curva simulada con las operaciones. SIMULADO. */
import { fetchProspect, type ProspectCard } from './cantera_api'
import { esc } from './panels'
import { agentLabel, cot, num, pc, rr, usd } from './cantera_fmt'

const STANCE: Record<string, [string, string]> = {
  apoya: ['respalda', 'up'], objeta: ['contradice', 'down'], condiciona: ['matiza', 'warn'],
}
const EXIT: Record<string, string> = {
  atr_ladder: 'stop por ATR con la escalera vigente', rule_flip: 'salida por regla contraria',
  mean_target: 'objetivo en la media', time_stop: 'tiempo máximo',
}

/** Curva de capital realizada (al cierre de cada operación) con las operaciones marcadas. */
export function curveSvg(c: ProspectCard): string {
  const pts = c.equity_curve
  if (pts.length < 2) return '<p class="muted">Sin operaciones cerradas todavía: la curva empieza en el capital inicial.</p>'
  const W = 760, H = 200, P = 34
  const t0 = pts[0].t, t1 = Math.max(pts[pts.length - 1].t, t0 + 1)
  const ys = pts.map((p) => p.equity).concat(c.initial_equity)
  const lo = Math.min(...ys), hi = Math.max(...ys), span = Math.max(hi - lo, 1)
  const x = (t: number): number => P + ((t - t0) / (t1 - t0)) * (W - 2 * P)
  const y = (v: number): number => H - P + 8 - ((v - lo) / span) * (H - 2 * P)
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.equity).toFixed(1)}`).join(' ')
  const base = y(c.initial_equity).toFixed(1)
  const marks = c.trades.filter((t) => t.exit_t != null && t.status === 'CERRADA').map((t) => {
    const p = [...pts].reverse().find((q) => q.t <= (t.exit_t as number)) ?? pts[0]
    return `<circle cx="${x(t.exit_t as number).toFixed(1)}" cy="${y(p.equity).toFixed(1)}" r="3.2" data-s="${t.pnl_usd >= 0 ? 'up' : 'down'}">` +
      `<title>${t.side > 0 ? 'Largo' : 'Corto'} · ${cot(t.exit_t)} COT · ${rr(t.r)} · ${t.pnl_usd >= 0 ? '+' : '−'}${num(t.pnl_usd, 2)} USDT</title></circle>`
  }).join('')
  return `<svg class="ct-curve" viewBox="0 0 ${W} ${H}" role="img" aria-label="Curva de capital simulada de ${esc(c.id)}">` +
    `<line x1="${P}" x2="${W - P}" y1="${base}" y2="${base}" class="ct-base"/>` +
    `<text x="${P}" y="14" class="ct-ax">${usd(hi)}</text><text x="${P}" y="${H - 4}" class="ct-ax">${usd(lo)}</text>` +
    `<text x="${W - P}" y="${H - 4}" class="ct-ax" text-anchor="end">${cot(t1).slice(0, 10)}</text>` +
    `<path d="${line}" class="ct-line"/>${marks}</svg>` +
    '<p class="muted ct-sim">Curva simulada (cuenta propia de la cantera, realizada al cierre de cada operación).</p>'
}

function body(c: ProspectCard): string {
  const params = c.params.length ? c.params.map((p) => `<li><code>${esc(p.name)}</code> = <b>${esc(String(p.value))}</b><small>${esc(p.source ?? 'sin cita')}</small></li>`).join('')
    : '<li class="muted">Sin parámetros libres.</li>'
  const vars = c.variables.map((v) => `<li><code>${esc(v.name.replace('metrics.', ''))}</code>${v.note ? ` — ${esc(v.note)}` : ''}<small>${esc(v.source ?? '')}</small></li>`).join('')
  const works = c.literature.length ? c.literature.map((w) => {
    const [lab, t] = STANCE[w.stance ?? ''] ?? ['sin postura anotada', 'flat']
    return `<li><span class="ct-stance" data-t="${t}">${lab}</span> <code>${esc(w.id)}</code>` +
      `${w.concept ? ` <small>${esc(w.concept)}${w.consensus ? ` · consenso ${esc(w.consensus)}` : ''}</small>` : ''}</li>`
  }).join('') : '<li class="muted">Sin obras citadas.</li>'
  const trades = c.trades.slice(-60).reverse().map((t) => `<tr><td>${cot(t.t)}</td><td>${t.side > 0 ? 'Largo' : 'Corto'}${t.maker ? ' · maker' : ''}</td>` +
    `<td>${t.status === 'ABIERTA' ? 'abierta' : esc(t.reason)}</td><td class="num">${rr(t.r)}</td><td class="num">${rr(t.d_r)}</td>` +
    `<td class="num" data-t="${t.pnl_usd > 0 ? 'up' : t.pnl_usd < 0 ? 'down' : 'flat'}">${t.pnl_usd >= 0 ? '+' : '−'}${num(t.pnl_usd, 2)}</td></tr>`).join('')
  const last = c.equity_curve[c.equity_curve.length - 1]?.equity ?? c.initial_equity
  return `<div class="ct-card"><h3>${esc(c.name)} <small>${esc(c.id)} · ${esc(agentLabel(c.agent_id))}@${esc(c.agent_version)} · huella ${esc(c.fingerprint)}</small></h3>` +
    `<p class="ct-theory">${esc(c.theory ?? c.agent_theory ?? '')}</p>` +
    `<p><b>Regla:</b> ${esc(c.rule)}</p>` +
    `<p class="muted">Marco ${esc(c.timeframe)} · horizonte ${esc(c.horizon.replace('_', ' '))} · salida: ${esc(EXIT[c.exit_template] ?? c.exit_template)}` +
    `${c.max_bars ? ` (máx. ${c.max_bars} velas)` : ''} · ${c.role === 'base' ? 'perfil base (hermano simple)' : 'candidato'}` +
    `${c.opposite_of ? ` · teoría opuesta de <code>${esc(c.opposite_of)}</code>` : ''}</p>` +
    `<div class="ct-cols"><section><h4>Variables que lee</h4><ul>${vars}</ul></section>` +
    `<section><h4>Parámetros citados</h4><ul>${params}</ul></section>` +
    `<section><h4>Obras (T157)</h4><ul>${works}</ul></section></div>` +
    `<h4>Curva simulada <small>saldo ${usd(last, 2)} · ${pc((last / c.initial_equity - 1) * 100)} · ${c.trades_total} operaciones</small></h4>${curveSvg(c)}` +
    (trades ? `<div class="tablewrap"><table class="ct-trades"><thead><tr><th>Vela (COT)</th><th>Lado</th><th>Salida</th><th>R</th><th>d vs gemelos</th><th>P&amp;L USDT</th></tr></thead><tbody>${trades}</tbody></table></div>` : '') +
    `<p class="muted">Fuente: ${esc(c.source)} · cuenta <code>${esc(c.account)}</code></p></div>`
}

export class CanteraCard {
  private id: string | null = null
  private card: ProspectCard | null = null
  private err = ''
  private abort: AbortController | null = null

  constructor(private readonly onChange: () => void) {}

  get isOpen(): boolean { return this.id !== null }

  async open(id: string): Promise<void> {
    this.abort?.abort()
    const ac = (this.abort = new AbortController())
    this.id = id; this.card = null; this.err = ''
    this.onChange()
    try { this.card = await fetchProspect(id, ac.signal) }
    catch (e) { if (ac.signal.aborted) return; this.err = `No se pudo abrir la ficha: ${(e as Error).message}` }
    this.onChange()
  }

  close(): void { this.abort?.abort(); this.id = null; this.card = null; this.onChange() }

  html(): string {
    const back = '<button type="button" class="ct-back" data-ct-back>← Volver a la panorámica por agente</button>'
    if (!this.card) return back + `<p class="muted">${esc(this.err || `Abriendo la ficha de ${this.id}…`)}</p>`
    return back + body(this.card)
  }
}
