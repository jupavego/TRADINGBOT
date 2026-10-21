/** Pestaña «Perfiles»: reglas de cada perfil y qué estrategias le dan o le quitan dinero. */
import { esc, nf, pct, pct0, usd, utc } from './paper_fmt'
import type { LadderStats, PaperSummary, ProfileView } from './paper_types'

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
    row('Riesgo por operación', (p) => `${nf(num(p, 'risk_pct') * 100, 1)} % × peso`) +
    row('Apalancamiento máx.', (p) => `${num(p, 'max_leverage')}x (liq. ≥ ${nf(num(p, 'liq_buffer'), 0)}× dist. SL)`) +
    row('Abiertas a la vez', (p) => String(num(p, 'max_open'))) +
    row('Confianza mínima', (p) => pct0(num(p, 'min_conf'))) +
    row('R:B mínimo', (p) => nf(num(p, 'min_rr'))) +
    row('A favor de la síntesis', (p) => (p.params.follow_synthesis ? 'obligatorio' : 'no')) +
    row('Cobertura (largo y corto)', (p) => (p.params.allow_hedge ? 'sí' : 'no')) +
    row('Salida', (p) => (p.params.exit_mode === 'ladder' ? 'SL por escalones, sin TP ni tiempo' : 'SL / TP / BE+ / tiempo')) +
    row('Familias', fams) +
    row('Muestra para decidir', (p) => `${fb(p, 'n_min')} operaciones`) +
    row('Peso (mín.–máx.)', (p) => `${nf(fb(p, 'w_min'))}–${nf(fb(p, 'w_max'))} · ganancia ${nf(fb(p, 'gain'), 1)}`) +
    row('Memoria (vida media)', (p) => `${nf(fb(p, 'half_life'), 0)} operaciones`) +
    row('Pausa si', (p) => `exp. + ${nf(fb(p, 'z_pause'), 1)}·EE < 0`) +
    '</tbody></table>'
  const res = `<table class="pp-t pp-rules"><thead><tr><th></th>${ps.map((p) => `<th>${esc(p.name)}</th>`).join('')}</tr></thead><tbody>` +
    row('Rentabilidad', (p) => `<span class="${p.return_pct >= 0 ? 'up' : 'down'}">${pct(p.return_pct)}</span>`) +
    row('Drawdown máx.', (p) => pct(-p.max_dd_pct)) +
    row('Operaciones · acierto', (p) => `${p.n_closed} · ${pct0(p.win_rate)}`) +
    row('R medio', (p) => (p.avg_r === null ? '—' : nf(p.avg_r))) +
    row('Estrategias en pausa', (p) => String(states(p, v, 'pausa'))) +
    row('Reforzadas', (p) => String(states(p, v, 'reforzada'))) +
    row('Más le aporta', (p) => top(p, names, 1)) +
    row('Más le resta', (p) => top(p, names, -1)) +
    '</tbody></table>'
  return `<div class="pp-two"><section class="pp-scroll"><h4 class="sh">Reglas</h4>${rules}</section>` +
    `<section class="pp-scroll"><h4 class="sh">Resultado</h4>${res}</section></div>` +
    ladderPanel(ps) +
    `<p class="muted pp-note">Los perfiles reciben las mismas ideas; cambian el filtro, el tamaño y cuánto confían en lo aprendido. ` +
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

/** Protección progresiva (perfil PPP): escalones alcanzados, retrocesos y ganancia capturada. */
function ladderPanel(ps: ProfileView[]): string {
  return ps.filter((p) => p.ladder).map((p) => {
    const l = p.ladder as LadderStats
    const lp = p.params.ladder as { first_usdt: number; step_usdt: number }
    const reached = l.reached.map((r) => `<span class="chip">+${nf(r.nominal, 0)}: ${r.reached}</span>`).join(' ') || '—'
    const lv = Object.entries(l.by_max_level).sort((a, b) => Number(a[0]) - Number(b[0]))
      .map(([k, b]) => `<tr><td>${Number(k) ? `escalón ${k}` : 'sin protección'}</td><td class="num">${b.n}</td><td class="num">${b.pullbacks}</td><td class="num">${usd(b.pnl, 2)}</td></tr>`).join('')
    const m = (x: number | null): string => (x === null ? '—' : `${usd(x, 2)} USDT`)
    return `<h4 class="sh">Protección progresiva · ${esc(p.name)}</h4>` +
      `<p class="muted">SL inicial por riesgo; al llegar a +${nf(lp.first_usdt, 0)} USDT netos se activa la protección y sube un escalón por cada +${nf(lp.step_usdt, 0)}. ` +
      `Sin TP final ni cierre por tiempo: solo cierra el SL vigente. Los tiempos son analíticos.</p>` +
      `<p>Operaciones que alcanzaron cada nivel: ${reached}</p>` +
      `<p>Cierres: SL inicial <b>${l.closed_initial_sl}</b> · SL dinámico <b>${l.closed_dynamic_sl}</b> · pérdidas seguidas máx. ${l.max_consecutive_losses} · ` +
      `abiertas hace ≥ 24 h: ${l.long_open_positions} · violaciones de reglas: <b class="${l.violations ? 'down' : ''}">${l.violations}</b> · incidencias: ${l.incidents}</p>` +
      `<p>Máximo flotante medio ${m(l.avg_max_float_usd)} · realizado medio ${m(l.avg_realized_usd)} · diferencia (lo que se devolvió) ${m(l.avg_gap_max_vs_realized_usd)} · ` +
      `realizado − protegido estimado ${m(l.avg_realized_vs_protected_usd)}</p>` +
      `<p>Freno de entradas: ${l.brake.halted ? `<b class="down">en pausa hasta ${utc(l.brake.until ?? 0)} COT · ${esc(l.brake.reason)}</b>` : 'inactivo'} · ` +
      `pérdidas seguidas ahora ${l.brake.consecutive_losses} · activaciones ${l.brake.activations.length} (solo frena entradas nuevas; nunca cierra posiciones)</p>` +
      `<table class="pp-t"><thead><tr><th>Máximo escalón</th><th>Ops</th><th>Retrocesos al SL</th><th>Neto</th></tr></thead><tbody>${lv}</tbody></table>` +
      `<p class="muted pp-note">${esc(l.note)} Simulado: sin dinero real.</p>`
  }).join('')
}
