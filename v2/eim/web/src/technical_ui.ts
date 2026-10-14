/** Detalle del agente `technical` (T35): régimen, marcos y familias desplegables con el voto
 *  de cada indicador. Mismo patrón de mosaico de T10; las familias abiertas se conservan. */

interface Rule { id: string; vote: number | null; info: string; duplicate_of: string | null }
interface Family { vote: number | null; weight: number; clusters: string[][]; rules: Rule[] }
interface Frame { bias: number; source: string; bars: number }
interface Metrics {
  families?: Record<string, Family>
  regime?: { label: string; adx: number | null; width_pct: number | null }
  frames?: Record<string, Frame>
  mtf_agreement?: number | null
  family_agreement?: number
  no_vote?: Record<string, string>
  source?: string
}

const FAM: Record<string, string> = {
  tendencia: 'Tendencia', momentum: 'Momentum', volatilidad: 'Volatilidad', volumen: 'Volumen', flujo: 'Flujo',
}
const openFams = new Set<string>()

const esc = (s: unknown): string => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
const sgn = (n: number): string => (n > 0 ? '+' : '') + n.toFixed(2)

function bar(b: number | null): string {
  if (b === null) return '<span class="bar" aria-label="sin dato"></span>'
  const pct = Math.min(1, Math.abs(b)) * 50
  const side = b >= 0 ? 'left:50%;background:var(--up)' : 'right:50%;background:var(--down)'
  return `<span class="bar" role="img" aria-label="voto ${sgn(b)}"><i style="${side};width:${pct}%"></i></span>`
}

/** Recuerda qué familias estaban abiertas antes de repintar los mosaicos. */
export function rememberOpenFamilies(root: HTMLElement): void {
  openFams.clear()
  root.querySelectorAll<HTMLDetailsElement>('details.fam[open]').forEach((d) => openFams.add(d.dataset.fam ?? ''))
}

function family(key: string, f: Family): string {
  const groups = f.clusters.filter((g) => g.length > 1).map((g) => g.join(' ≈ '))
  const rows = f.rules.map((r) => `<tr><td>${esc(r.id)}</td><td>${bar(r.vote)}</td>` +
    `<td class="num">${r.vote === null ? 'n/d' : sgn(r.vote)}</td>` +
    `<td class="muted">${esc(r.duplicate_of ? `duplicado de ${r.duplicate_of}` : r.info)}</td></tr>`).join('')
  const v = f.vote === null ? '<span class="muted">sin datos</span>' : `<b class="num">${sgn(f.vote)}</b>`
  return `<details class="fam" data-fam="${esc(key)}"${openFams.has(key) ? ' open' : ''}>` +
    `<summary><span>${esc(FAM[key] ?? key)}</span>${bar(f.vote)}${v}<span class="muted">peso ${f.weight}</span></summary>` +
    (groups.length ? `<p class="muted">Cuentan como uno (correlados): ${esc(groups.join('; '))}</p>` : '') +
    `<table class="metrics fam-t">${rows}</table></details>`
}

export function technicalDetail(m: Metrics): string {
  const reg = m.regime
  const regTxt = reg ? `Régimen <b>${esc(reg.label)}</b> · ADX ${reg.adx ?? 'n/d'} · ancho BOLL p${reg.width_pct === null ? 'n/d' : Math.round(reg.width_pct * 100)}` : ''
  const frames = Object.entries(m.frames ?? {}).map(([tf, f]) =>
    `<span class="tf" title="${esc(f.source)} · ${f.bars} velas">${esc(tf)} <b class="num">${sgn(f.bias)}</b></span>`).join('')
  const agree = m.mtf_agreement == null ? 'acuerdo entre marcos no medido' : `acuerdo ${Math.round(m.mtf_agreement * 100)}%`
  const fams = Object.entries(m.families ?? {}).map(([k, f]) => family(k, f)).join('')
  const nv = Object.entries(m.no_vote ?? {}).map(([k, why]) => `${esc(k)}: ${esc(why)}`).join(' · ')
  return `<div class="tech"><p>${regTxt}</p><p class="tfs">${frames} <span class="muted">${agree}</span></p>` +
    `${fams}${nv ? `<p class="muted">No votan — ${nv}</p>` : ''}</div>`
}
