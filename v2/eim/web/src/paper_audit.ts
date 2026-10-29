/** Instantánea y alcance de la vista del bróker (T118): qué tramo se ve, su techo y lo que deja fuera. */
import { base } from './api'
import { esc, nf, utc } from './paper_fmt'
import type { PaperSummary, ScopeGap } from './paper_types'

const n0 = (x: number | undefined): string => nf(x ?? 0, 0)
const cap = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1)

function gapText(g: ScopeGap): string {
  if (g.kind === 'instantanea') {
    return `<b>${esc(g.name)}</b>: la instantánea <code>${esc(g.id ?? '')}</code> (${utc(g.computed ?? 0)} COT) ` +
      `contaba ${n0(g.n)} operaciones y esta vista cuenta ${n0(g.now)}: ${esc(g.why)}.`
  }
  const parts = [
    g.outside ? `no reproduce ${n0(g.outside)} (cerradas ${utc(g.from ?? 0)} → ${utc(g.to ?? 0)} COT)` : '',
    g.differ ? `reproduce ${n0(g.differ)} con otro PnL o motivo` : '',
  ].filter(Boolean)
  const what = parts.length ? parts.join(' y ') : `no coincide en número o capital (vista: ${n0(g.view_live)})`
  return `<b>${esc(g.name)}</b>: el libro fijo tiene ${n0(g.rows)} operaciones en vivo; esta vista ${what}. ${esc(cap(g.why))}.`
}

/** Franja de auditoría: identificador de la instantánea (enlace a la foto guardada), tramo, techo y huecos. */
export function scopeHtml(v: PaperSummary): string {
  const snap = v.snapshot, s = v.scope
  const id = snap?.id
    ? `Instantánea <a href="${base()}/v2/paper/snapshot/${snap.id}" target="_blank" rel="noopener" ` +
      `title="Abre la foto guardada de estas cifras: pedirla mañana devuelve exactamente lo mismo"><code>${snap.id}</code></a> ` +
      `· calculada ${utc(snap.computed)} COT`
    : `<span class="down">Sin instantánea: ${esc(snap?.error || 'la API aún no la publica (falta desplegar T118)')}</span>`
  if (!s) return `<p>${id}</p>`
  if (s.error) return `<p>${id}</p><p class="down">No se pudo calcular el alcance (${esc(s.error)}): no se sabe qué deja fuera esta vista.</p>`
  const o = s.origins
  const tramo = s.from && s.to
    ? `tramo de esta vista: decisiones ${utc(s.from)} → ${utc(s.to)} COT, ${n0(s.contexts)} velas ` +
      `(${n0(o.vivo)} en vivo · ${n0(o.backtest)} reconstruidas)`
    : 'tramo vacío: sin velas analizadas'
  const ceil = `<span title="${esc(s.ceiling_why)}">techo ${n0(s.ceiling)} cierres por perfil</span>`
  const head = `<p>${id} · ${tramo} · ${ceil}. Todas las cifras del panel son de este tramo, no de una historia mayor.</p>`
  if (s.complete) return head + '<p class="up">Abarca todo lo que este almacén y su libro fijo conocen.</p>'
  return `${head}<p class="warn">La vista NO abarca todo el historial conocido:</p><ul>${s.gaps.map((g) => `<li>${gapText(g)}</li>`).join('')}</ul>`
}

/** Encabezado del Historial cuando la lista es solo un tramo de las más recientes. */
export function histPart(total: number, shown: number, from: number | null): string {
  if (total <= shown) return ''
  return `<p class="warn pp-note">Lista parcial: las <b>${n0(shown)} más recientes</b> de ${n0(total)} cerradas` +
    `${from ? ` (desde ${utc(from)} COT)` : ''}. Las sumas de abajo son de ese tramo; el total del perfil está en su tarjeta.</p>`
}
