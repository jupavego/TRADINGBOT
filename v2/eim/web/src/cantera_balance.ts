/** Cantera: balance de operaciones ganadas frente a perdidas, con la misma cara que el del bróker
 * simulado (`paper_balance.ts`), pero por agente y con la contabilidad aparte de la cantera. */
import type { CtBalance, CtStats, CtWindow } from './cantera_api'
import { agentLabel } from './cantera_fmt'
import { esc, nf, pct0, REASON, rr, usd } from './paper_fmt'

/** Color categórico estable por agente (mismo color en el balance y en la curva de capital). */
const PALETTE = ['#3987e5', '#d95926', '#199e70', '#9b72e0', '#e0b030', '#e05a9a', '#30b8c8',
  '#8fbf3a', '#c87a3a', '#6a7fd8', '#d04848', '#3ac090', '#b07ad0', '#a0a0a0']
export function agentColor(id: string, ids: string[]): string {
  const i = ids.indexOf(id)
  return PALETTE[(i < 0 ? ids.length : i) % PALETTE.length]
}

const reasons = (r: Record<string, number>): string =>
  Object.entries(r).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${REASON[k] ?? k} ${n}`).join(' · ') || '—'

function card(kind: 'win' | 'loss', w: CtWindow, ids: string[]): string {
  const a = w.all, half = kind === 'win' ? a.wins : a.losses
  const share = a.n ? half.n / a.n : null
  const rows = ids.map((id) => {
    const s = w.agents[id]
    const h = s ? (kind === 'win' ? s.wins : s.losses) : null
    const rate = s && s.n && h ? h.n / s.n : null
    return `<li><span class="pp-bal-p" title="${esc(agentLabel(id))}"><i style="background:${agentColor(id, ids)}"></i>${esc(agentLabel(id))}</span>` +
      `<span class="pp-bal-bar"><i style="width:${Math.round((rate ?? 0) * 100)}%"></i></span>` +
      `<b class="num">${h?.n ?? 0}</b><small class="num">${pct0(rate)} · ${usd(h?.usd ?? 0, 0)}</small></li>`
  }).join('')
  const title = kind === 'win' ? '▲ Ganadas' : '▼ Perdidas'
  return `<article class="pp-bal-card" data-k="${kind}"><h5>${title}</h5>` +
    `<p class="pp-bal-big"><b class="num">${nf(half.n, 0)}</b><span>de ${nf(a.n, 0)} operaciones · <b>${pct0(share)}</b></span></p>` +
    `<p class="pp-bal-sum num">${usd(half.usd, 0)} USDT <small>· media ${half.avg_usd === null ? '—' : usd(half.avg_usd)} USDT (${rr(half.avg_r)})</small></p>` +
    `<ul class="pp-bal-rows ct-bal-rows">${rows}</ul><small class="muted">Salidas: ${reasons(half.by_reason)}</small></article>`
}

function byTf(w: CtWindow): string {
  const xs = Object.entries(w.timeframes ?? {}).filter(([, s]) => s.n)
  if (!xs.length) return ''
  return `<p class="pp-bal-tfs">${xs.map(([tf, s]) => `<span><b>${esc(tf)}</b> ${pct0(s.win_rate)} · ${s.n} ops</span>`).join('')}</p>`
}

function middle(w: CtWindow): string {
  const a: CtStats = w.all
  const wr = a.win_rate, be = a.breakeven
  const ok = wr !== null && be !== null && wr >= be
  const wp = Math.round((wr ?? 0) * 100)
  const mark = be === null ? '' : `<i class="pp-bal-be" style="left:${Math.round(be * 100)}%" title="Acierto necesario para no perder"></i>`
  return `<div class="pp-bal-mid"><div class="pp-bal-split" role="img" aria-label="Ganadas ${wp} %, perdidas ${100 - wp} %">` +
    `<span data-k="win" style="flex-basis:${a.n ? wp : 50}%">${a.n && wp ? `${wp} %` : ''}</span>` +
    `<span data-k="loss" style="flex-basis:${a.n ? 100 - wp : 50}%">${a.n ? `${100 - wp} %` : ''}</span>${mark}</div>` +
    `<p class="pp-bal-need ${ok ? 'up' : 'down'}">${a.n ? `${ok ? '✓' : '✗'} Acierto ${pct0(wr)} · necesario ${pct0(be)}` : 'Aún sin operaciones cerradas en este periodo'}</p>` + byTf(w) +
    '<dl class="pp-bal-kv">' +
    `<dt>Ganancia media / pérdida media</dt><dd class="num">${a.payoff === null ? '—' : `${nf(a.payoff)} R`}</dd>` +
    `<dt>Esperanza por operación</dt><dd class="num">${rr(a.expectancy_r)}</dd>` +
    `<dt>Factor de beneficio</dt><dd class="num">${a.pf === null ? '—' : nf(a.pf)}</dd>` +
    `<dt>Neto (todos los prospectos)</dt><dd class="num ${a.net > 0 ? 'up' : a.net < 0 ? 'down' : ''}">${usd(a.net, 0)} USDT</dd>` +
    `<dt>Costos pagados</dt><dd class="num">${nf(a.costs, 0)} USDT</dd></dl></div>`
}

/** Sección completa; `period` = clave de la ventana (todo, 30d, 7d, 24h). */
export function canteraBalanceView(b: CtBalance, period: string): string {
  const w = b.windows[period] ?? b.windows.todo
  const ids = b.agents.map((a) => a.agent_id)
  const chips = Object.entries(b.windows).map(([k, x]) =>
    `<button type="button" class="pp-chip" data-ct-bal="${k}" aria-pressed="${k === period}">${esc(x.label)} <small class="num">${x.all.n}</small></button>`).join('')
  return `<div class="pp-bal-head"><h4 class="sh">Balance de operaciones · ${ids.length} agentes, ${b.agents.reduce((k, a) => k + a.accounts, 0)} prospectos</h4>` +
    `<div class="pp-chips">${chips}</div>` +
    `<small class="muted">Cada operación cerrada pesa igual · ${esc(b.rule)} · ${esc(b.scope)}</small></div>` +
    `<div class="pp-bal-grid">${card('win', w, ids)}${middle(w)}${card('loss', w, ids)}</div>`
}
