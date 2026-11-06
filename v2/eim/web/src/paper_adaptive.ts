/** Salida adaptativa por perfil y por operación (T135). Todo es SIMULADO.
 *  El bloque no aparece mientras ningún perfil la use, que es la situación de hoy: T134 no aprobó
 *  ninguna salida. El stop y el neto si salta son estimaciones del simulador, no ganancia. */
import { PROFILE_VAR } from './paper_chart'
import { dur, esc, nf, pct, phaseLabel, px, side, tone, usd } from './paper_fmt'
import type { AdaptiveStats, PaperSummary, Position, ProfileView } from './paper_types'

const MODE: Record<string, string> = { SIMULADO: 'Simulado', TESTNET: 'Testnet', ANALISIS: 'Análisis' }

/** La política del perfil y de dónde salen sus rasgos: fuente y cobertura reales, a la vista. */
function policyLine(p: ProfileView, a: AdaptiveStats): string {
  const info = a.feature_info ?? {}
  const cover = info.coverage?.sigma_abs
  const src = info.source?.sigma_abs ?? 'sin dato de la fuente'
  return `<li><span class="pp-pname" style="--pc:var(${PROFILE_VAR[p.id] ?? '--accent'})">${esc(p.name)}</span> · ` +
    `<b>${esc(a.policy)}</b> <small class="muted">versión ${esc(a.version)} · rasgos ${esc(a.features)}</small><br>` +
    `<small class="muted" title="${esc(src)}">σ ${esc(info.sigma ?? '—')} · cobertura ${cover === undefined ? '—' : `${nf(cover * 100, 1)} %`} · ` +
    `señales contrarias que solo informaron: ${a.contrary_signals}</small></li>`
}

function positionRow(p: ProfileView, x: Position, names: Record<string, string>, price: number | null): string {
  const l = x.ladder!
  const e = l.exit!
  const mark = price ?? x.mark
  const why = x.protection_why || l.incident || x.liq_why || l.inconsistent || ''
  return `<tr><td><span class="pp-pname" style="--pc:var(${PROFILE_VAR[p.id] ?? '--accent'})">${esc(p.name)}</span><br>` +
    `<b>${esc((names[x.sid] ?? x.sid).split(' · ')[0])}</b> <span class="pp-tfb">${esc(x.timeframe)}</span> · ` +
    `<span class="pp-dir" data-side="${x.side > 0 ? 'long' : 'short'}">${side(x.side)}</span></td>` +
    `<td><b>${esc(phaseLabel(e.phase))}</b>${why ? `<br><small class="warn">${esc(why)}</small>` : ''}</td>` +
    `<td class="num"><span class="down">${px(l.stop)}</span><br><small class="muted">${pct((l.stop - mark) / mark)} del precio · entrada ${px(x.entry)}</small></td>` +
    `<td>${esc(e.motive)}<br><small class="muted">fuente ${esc(e.source)}</small></td>` +
    `<td class="num ${tone(l.float_usd)}">${usd(l.float_usd)} USDT<br><small class="muted">no realizado</small></td>` +
    `<td class="num">${l.stop_est_usd === undefined ? '—' : `<b class="${tone(l.stop_est_usd)}">≈ ${usd(l.stop_est_usd)} USDT</b> <small class="muted">estimado</small>`}</td>` +
    `<td class="num">hace ${dur(Date.now() - x.fill_t)}</td></tr>`
}

/** Bloque «Salida adaptativa» de la pestaña «Perfiles»: modo, fase, stop vigente y su motivo. */
export function adaptivePanel(v: PaperSummary, price: number | null): string {
  const ps = v.profiles.filter((p) => p.adaptive)
  if (!ps.length) return ''
  const names = Object.fromEntries(v.strategies.map((s) => [s.id, s.name]))
  const rows = ps.flatMap((p) => p.positions.filter((x) => x.ladder?.exit).map((x) => positionRow(p, x, names, price)))
  const open = rows.length
    ? `<div class="pp-scroll"><table class="pp-t pp-prot-ops"><thead><tr><th>Perfil · operación</th><th>Fase</th><th>Stop vigente</th>` +
      `<th>Por qué está ahí</th><th>Flotante neto</th><th>Neto si salta el stop</th><th>Abierta</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`
    : '<p class="muted">Ninguna operación abierta con salida adaptativa. La fase y el stop aparecen aquí en cuanto se llene una orden.</p>'
  return `<section class="pp-protect"><div class="pp-prot-h"><h4 class="sh">Salida adaptativa</h4>` +
    `<span class="mode" data-mode="${esc(v.mode)}">Modo: ${esc(MODE[v.mode] ?? v.mode)}</span></div>` +
    `<ul class="pp-note">${ps.map((p) => policyLine(p, p.adaptive!)).join('')}</ul>${open}</section>`
}
