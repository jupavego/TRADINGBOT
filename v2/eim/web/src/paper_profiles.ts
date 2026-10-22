/** Pestaña «Perfiles»: reglas de cada perfil y qué estrategias le dan o le quitan dinero. */
import { esc, nf, pct, pct0, usd } from './paper_fmt'
import type { PaperSummary, ProfileView } from './paper_types'

const num = (p: ProfileView, k: string): number => Number(p.params[k])
const fb = (p: ProfileView, k: string): number => Number((p.params.feedback as Record<string, number>)[k])

export function profilesTab(v: PaperSummary): string {
  const ps = v.profiles
  const names = Object.fromEntries(v.strategies.map((s) => [s.id, s.name]))
  const row = (label: string, f: (p: ProfileView) => string): string =>
    `<tr><th>${label}</th>${ps.map((p) => `<td class="num">${f(p)}</td>`).join('')}</tr>`
  const fams = (p: ProfileView): string => ((p.params.families as string[]) ?? [])
    .map((f) => esc(v.families[f] ?? f)).sort().join('<br>')
  const rules = `<table class="pp-t pp-rules"><thead><tr><th></th>${ps.map((p) => `<th>${esc(p.name)}</th>`).join('')}</tr></thead><tbody>` +
    row('Capital inicial', (p) => `${nf(p.initial, 0)} USDT`) +
    row('Recarga', (p) => (num(p, 'refill_below') > 0 ? `si el saldo baja del ${pct0(num(p, 'refill_below'))}, hasta el inicial` : 'no')) +
    row('Riesgo por operación', (p) => `${nf(num(p, 'risk_pct') * 100, 1)} % × peso`) +
    row('Apalancamiento máx.', (p) => `${num(p, 'max_leverage')}x (liq. ≥ ${nf(num(p, 'liq_buffer'), 0)}× dist. SL)`) +
    row('Abiertas a la vez', (p) => String(num(p, 'max_open'))) +
    row('Confianza mínima', (p) => pct0(num(p, 'min_conf'))) +
    row('R:B mínimo', (p) => nf(num(p, 'min_rr'))) +
    row('A favor de la síntesis', (p) => (p.params.follow_synthesis ? 'obligatorio' : 'no')) +
    row('Cobertura (largo y corto)', (p) => (p.params.allow_hedge ? 'sí' : 'no')) +
    row('Familias', fams) +
    row('Muestra para decidir', (p) => `${fb(p, 'n_min')} operaciones`) +
    row('Peso (mín.–máx.)', (p) => `${nf(fb(p, 'w_min'))}–${nf(fb(p, 'w_max'))} · ganancia ${nf(fb(p, 'gain'), 1)}`) +
    row('Memoria (vida media)', (p) => `${nf(fb(p, 'half_life'), 0)} operaciones`) +
    row('Pausa si', (p) => `exp. + ${nf(fb(p, 'z_pause'), 1)}·EE < 0`) +
    row('Opera lo pausado', (p) => (p.params.trade_paused ? `sí, con peso ${nf(fb(p, 'w_min'))}` : 'no')) +
    '</tbody></table>'
  const res = `<table class="pp-t pp-rules"><thead><tr><th></th>${ps.map((p) => `<th>${esc(p.name)}</th>`).join('')}</tr></thead><tbody>` +
    row('Rentabilidad (sobre lo aportado)', (p) => `<span class="${p.return_pct >= 0 ? 'up' : 'down'}">${pct(p.return_pct)}</span>`) +
    row('Recargas · inyectado', (p) => (p.refills ? `${p.refills} · ${nf(p.injected, 0)} USDT` : '0')) +
    row('Drawdown máx. (sin recargas)', (p) => pct(-p.max_dd_pct)) +
    row('Operaciones · acierto', (p) => `${p.n_closed} · ${pct0(p.win_rate)}`) +
    row('R medio', (p) => (p.avg_r === null ? '—' : nf(p.avg_r))) +
    row('Estrategias en pausa', (p) => String(states(p, v, 'pausa'))) +
    row('Reforzadas', (p) => String(states(p, v, 'reforzada'))) +
    row('Más le aporta', (p) => top(p, names, 1)) +
    row('Más le resta', (p) => top(p, names, -1)) +
    '</tbody></table>'
  return `<div class="pp-two"><section class="pp-scroll"><h4 class="sh">Reglas</h4>${rules}</section>` +
    `<section class="pp-scroll"><h4 class="sh">Resultado</h4>${res}</section></div>` +
    `<p class="muted pp-note">Los tres perfiles reciben las mismas ideas; cambian el filtro, el tamaño y cuánto confían en lo aprendido. ` +
    `${esc(v.sources.costs)}. Funding: ${esc(v.sources.funding)}. El tamaño usa el capital realizado en el momento de la señal.</p>`
}

/** Estrategias en un estado, solo de las familias que el perfil opera. */
function states(p: ProfileView, v: PaperSummary, state: string): number {
  const fams = new Set((p.params.families as string[]) ?? [])
  return v.strategies.filter((s) => fams.has(s.family) && p.weights[s.id]?.state === state).length
}

function top(p: ProfileView, names: Record<string, string>, dir: 1 | -1): string {
  const xs = Object.entries(p.by_strategy).filter(([, b]) => b.pnl * dir > 0)
    .sort((a, b) => (b[1].pnl - a[1].pnl) * dir).slice(0, 3)
  return xs.length ? xs.map(([id, b]) => `${esc(names[id] ?? id)} <small>${usd(b.pnl, 0)}</small>`).join('<br>') : '—'
}
