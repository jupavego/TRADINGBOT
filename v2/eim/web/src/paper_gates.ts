/** T212: la puerta del marco mayor, a la vista. Dirección vigente, cuándo giró, cuánto lleva así
 * y a qué distancia está del extremo reciente. Es análisis: no abre ni cierra nada. */
import { dur, esc, nf, usd, utc } from './paper_fmt'
import type { HtfGate } from './paper_types'

const ARROW: Record<number, string> = { 1: '▲', [-1]: '▼', 0: '·' }
const KIND: Record<string, string> = { min: 'mínimo', max: 'máximo' }

function row(g: HtfGate): string {
  const k = g.dir > 0 ? 'win' : g.dir < 0 ? 'loss' : 'flat'
  const head = `<b>${esc(g.timeframe)}</b> <span class="pp-gate-dir" data-k="${k}">${ARROW[g.dir] ?? '·'} ${esc(g.label)}</span>`
  if (g.dir === 0 || g.since_t === null || g.hours === null) {
    return `<li data-k="flat">${head} <small class="muted">sin dirección todavía: faltan velas de ${esc(g.htf)} para la EMA de ${g.slow}</small></li>`
  }
  const since = `desde hace <b>${dur(g.hours * 3_600_000)}</b> <small class="muted">(giró el ${utc(g.since_t)} COT)</small>`
  const dist = g.move_pct === null || g.extreme_kind === null ? ''
    : ` · precio <b>${usd(g.move_pct, 1)} %</b> frente al ${KIND[g.extreme_kind] ?? g.extreme_kind}` +
      ` de ${nf(g.thresholds.window_h / 24, 0)} d${g.extreme_px === null ? '' : ` (${nf(g.extreme_px, 0)})`}`
  const b = g.blocked
  const off = b && b.n
    ? ` · dejó fuera <b>${b.ideas}</b> idea${b.ideas === 1 ? '' : 's'} en ${nf(b.window_h, 0)} h` +
      ` <span class="muted">(${b.n} rechazos: ${b.long} largos, ${b.short} cortos` +
      `${b.live < b.n ? `; ${b.live} en vivo` : ''})</span>`
    : ''
  const warn = g.disagrees && g.against_pct !== null
    ? ` <span class="warn">⚠ lleva ${nf(g.against_pct, 1)} % en contra (umbral ${nf(g.thresholds.disagree_pct, 0)} % y ${nf(g.thresholds.disagree_h, 0)} h)</span>`
    : ''
  return `<li data-k="${k}">${head} <small>${since}${dist}${off}</small>${warn}</li>`
}

/** Franja completa; vacía si la API todavía no publica las puertas (versión anterior). */
export function gatesView(gs: HtfGate[] | undefined): string {
  if (!gs || !gs.length) return ''
  const who = gs.find((g) => g.enforced_by.length)?.enforced_by ?? []
  const note = who.length
    ? `Los perfiles ${who.map((p) => esc(p)).join(', ')} solo abren a favor de esta dirección (veto «contra la tendencia del marco mayor»).`
    : 'Ningún perfil está exigiendo esta dirección ahora mismo.'
  return `<h4 class="sh">Puerta del marco mayor · qué lado deja operar</h4>` +
    `<ul class="pp-gates-l">${gs.map(row).join('')}</ul>` +
    `<small class="muted">${note} Es análisis: no abre ni cierra nada. ` +
    `Cada marco mira su marco mayor (EMA rápida frente a lenta) en la última vela cerrada.</small>`
}
