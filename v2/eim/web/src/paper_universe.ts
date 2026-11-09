/** Universo oficial de la contabilidad (T144): qué cuenta como resultado, cuántas cuentan y por qué
 * quedan fuera las demás. Las cifras llegan ya filtradas por la API (`eim.paper.universe`): aquí no
 * se vuelve a decidir nada, solo se enseña la regla con la que se decidió. */
import { esc, nf, pct, pct0, usd, utc } from './paper_fmt'
import type { Accounting } from './paper_types'

const n0 = (x: number | undefined | null): string => nf(x ?? 0, 0)
const r2 = (x: number | null | undefined): string => (x === null || x === undefined ? '—' : x.toFixed(2))

/** Franja del universo oficial: la cifra que decide, su recuento y las `retro` aparte. */
export function universeHtml(a: Accounting | null | undefined): string {
  if (!a) return ''
  const d = a.declaration
  if (a.ok === false || !a.tally) {
    return `<p class="down">Universo oficial (${esc(d?.universe ?? 'T144')}) no disponible: ` +
      `${esc(a.error ?? 'el libro fijo no se pudo leer')}. No se publica cifra oficial.</p>`
  }
  const t = a.tally
  const out = t.n_total - t.n_counted
  const fuera = Object.entries(t.excluded)
    .map(([k, v]) => `<li><b>${esc(k)}</b> ${n0(v)}: ${esc(t.excluded_why[k] ?? k)}</li>`).join('')
  const dd = a.dd
  const retro = a.retro_excluded
  return `<details class="pp-universe"><summary><b>Universo oficial:</b> ` +
    `cuentan <b>${n0(t.n_counted)}</b> de ${n0(t.n_total)} operaciones del libro` +
    ` · acierto ${a.win_rate === null || a.win_rate === undefined ? '—' : pct0(a.win_rate)}` +
    ` · R medio ${r2(a.mean_r)} · PnL ${a.pnl_usdt === null || a.pnl_usdt === undefined ? '—' : usd(a.pnl_usdt)} USDT` +
    `</summary>` +
    `<p>${esc(d.label)}. ${esc(d.decided)}</p>` +
    `<p>Fuente: <code>${esc(d.source)}</code>` +
    (a.n && dd ? ` · drawdown ${nf(dd.usdt)} USDT${dd.pct === null ? '' : ` (${pct(-dd.pct)})`}; base: ${esc(dd.base)}` : '') +
    (a.floor_trades ? ` · ${n0(a.floor_trades)} entradas de suelo incluidas (las abrió el mínimo de apertura, no una señal)` : '') +
    `.</p>` +
    (out ? `<p class="warn">Quedan fuera ${n0(out)} de ${n0(t.n_total)}:</p><ul>${fuera}</ul>` : '<p class="up">No queda fuera ninguna operación del libro.</p>') +
    (retro && retro.n
      ? `<p class="warn"><b>${n0(retro.n)} operaciones <code>retro</code></b> no suman a ninguna cifra ` +
        `(PnL excluido ${usd(retro.pnl_excluded)} USDT, R ${r2(retro.total_r_excluded)}): ${esc(retro.why)}.</p>`
      : '') +
    `<p class="muted">La regla, dimensión a dimensión:</p><ul>` +
    d.rule.map((x) => `<li><b>${esc(x.dimension)}</b>: ${esc(x.regla)}</li>`).join('') + '</ul>' +
    (a.by_profile
      ? `<p class="muted">Por perfil (solo lo que cuenta):</p><ul>` +
        Object.entries(a.by_profile).map(([pid, b]) =>
          `<li><b>${esc(pid)}</b>: ${n0(b.n)} operaciones · acierto ${b.win_rate === null ? '—' : pct0(b.win_rate)}` +
          ` · R medio ${r2(b.mean_r)} · PnL ${usd(b.pnl_usdt)} USDT</li>`).join('') + '</ul>'
      : '') +
    (a.from_t && a.to_t ? `<p class="muted">Cierres de ${utc(a.from_t)} → ${utc(a.to_t)} COT.</p>` : '') +
    `</details>`
}
