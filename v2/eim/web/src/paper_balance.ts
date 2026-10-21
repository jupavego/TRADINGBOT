/** Balance superior del bróker simulado: ganadas frente a perdidas (ponderado de todos los perfiles). */
import { PROFILE_VAR } from './paper_chart'
import { CAUSE, esc, nf, pct0, REASON, rr, usd } from './paper_fmt'
import type { BalanceSummary, BalanceWindow, PaperSummary } from './paper_types'

const FB: Record<string, [string, string]> = {
  funciono: ['✓', 'Funcionó'], no_funciono: ['✗', 'No funcionó'], mejorar: ['→', 'Mejorar'],
}

const reasons = (r: Record<string, number>): string =>
  Object.entries(r).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${REASON[k] ?? k} ${n}`).join(' · ') || '—'

function card(kind: 'win' | 'loss', w: BalanceWindow, v: PaperSummary): string {
  const a = w.all, half = kind === 'win' ? a.wins : a.losses
  const share = a.n ? half.n / a.n : null
  const rows = v.profiles.map((p) => {
    const s: BalanceSummary | undefined = w.profiles[p.id]
    const h = s ? (kind === 'win' ? s.wins : s.losses) : null
    const rate = s && s.n && h ? h.n / s.n : null
    return `<li><span class="pp-bal-p"><i style="background:var(${PROFILE_VAR[p.id] ?? '--accent'})"></i>${esc(p.name)}</span>` +
      `<span class="pp-bal-bar"><i style="width:${Math.round((rate ?? 0) * 100)}%"></i></span>` +
      `<b class="num">${h?.n ?? 0}</b><small class="num">${pct0(rate)} · ${usd(h?.usd ?? 0, 0)}</small></li>`
  }).join('')
  const title = kind === 'win' ? '▲ Ganadas' : '▼ Perdidas'
  return `<article class="pp-bal-card" data-k="${kind}"><h5>${title}</h5>` +
    `<p class="pp-bal-big"><b class="num">${nf(half.n, 0)}</b><span>de ${nf(a.n, 0)} operaciones · <b>${pct0(share)}</b></span></p>` +
    `<p class="pp-bal-sum num">${usd(half.usd, 0)} USDT <small>· media ${half.avg_usd === null ? '—' : usd(half.avg_usd)} USDT (${rr(half.avg_r)})</small></p>` +
    `<ul class="pp-bal-rows">${rows}</ul><small class="muted">Salidas: ${reasons(half.by_reason)}</small>` +
    (kind === 'loss' ? causes(a) : '') + '</article>'
}

/** Por qué se perdió (T48): reparto de las causas de las pérdidas del periodo. */
function causes(a: BalanceSummary): string {
  const xs = Object.entries(a.causes ?? {}).sort((x, y) => y[1] - x[1])
  const tot = xs.reduce((k, [, n]) => k + n, 0)
  if (!tot) return ''
  return `<p class="pp-bal-causes"><b>Por qué se perdió:</b> ${xs.map(([k, n]) =>
    `<span>${esc(CAUSE[k] ?? k)} <b class="num">${pct0(n / tot)}</b></span>`).join('')}</p>`
}

/** Acierto por temporalidad del periodo (ponderado de todos los perfiles). */
function byTf(w: BalanceWindow): string {
  const xs = Object.entries(w.timeframes ?? {}).filter(([, s]) => s.n)
  if (!xs.length) return ''
  return `<p class="pp-bal-tfs">${xs.map(([tf, s]) => `<span><b>${esc(tf)}</b> ${pct0(s.win_rate)} · ${s.n} ops</span>`).join('')}</p>`
}

function middle(w: BalanceWindow): string {
  const a = w.all
  const wr = a.win_rate, be = a.breakeven
  const ok = wr !== null && be !== null && wr >= be
  const wp = Math.round((wr ?? 0) * 100)
  const mark = be === null ? '' : `<i class="pp-bal-be" style="left:${Math.round(be * 100)}%" title="Acierto necesario para no perder"></i>`
  return `<div class="pp-bal-mid"><div class="pp-bal-split" role="img" aria-label="Ganadas ${wp} %, perdidas ${100 - wp} %">` +
    `<span data-k="win" style="flex-basis:${wp}%">${wp ? `${wp} %` : ''}</span><span data-k="loss" style="flex-basis:${100 - wp}%">${a.n ? `${100 - wp} %` : ''}</span>${mark}</div>` +
    `<p class="pp-bal-need ${ok ? 'up' : 'down'}">${ok ? '✓' : '✗'} Acierto ${pct0(wr)} · necesario ${pct0(be)}</p>` + byTf(w) +
    '<dl class="pp-bal-kv">' +
    `<dt>Ganancia media / pérdida media</dt><dd class="num">${a.payoff === null ? '—' : `${nf(a.payoff)} R`}</dd>` +
    `<dt>Esperanza por operación</dt><dd class="num">${rr(a.expectancy_r)}</dd>` +
    `<dt>Factor de beneficio</dt><dd class="num">${a.pf === null ? '—' : nf(a.pf)}</dd>` +
    `<dt>Neto (todos los perfiles)</dt><dd class="num ${a.net > 0 ? 'up' : a.net < 0 ? 'down' : ''}">${usd(a.net, 0)} USDT</dd>` +
    `<dt>Costos pagados</dt><dd class="num">${nf(a.costs, 0)} USDT</dd></dl></div>`
}

/** Sección completa; `period` = clave de `v.balance` (todo, 30d, 7d, 24h). */
export function balanceView(v: PaperSummary, period: string): string {
  const b = v.balance
  if (!b) return ''
  const w = b[period] ?? b.todo
  const chips = Object.entries(b).map(([k, x]) =>
    `<button type="button" class="pp-chip" data-bal="${k}" aria-pressed="${k === period}">${esc(x.label)} <small class="num">${x.all.n}</small></button>`).join('')
  const fb = w.feedback.map((f) => `<li data-k="${f.kind}"><b>${FB[f.kind][0]} ${FB[f.kind][1]}:</b> ${esc(f.text)}</li>`).join('')
  return `<div class="pp-bal-head"><h4 class="sh">Balance de operaciones · ponderado de los ${v.profiles.length} perfiles</h4>` +
    `<div class="pp-chips">${chips}</div>` +
    '<small class="muted">Cada operación cerrada pesa igual · ganada = PnL neto &gt; 0 después de comisiones, deslizamiento y funding</small></div>' +
    `<div class="pp-bal-grid">${card('win', w, v)}${middle(w)}${card('loss', w, v)}</div>` +
    `<ul class="pp-bal-fb">${fb}</ul>`
}
