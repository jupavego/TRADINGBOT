/** Grafo de ejecución de una traza (T76): solo lo que participó, en orden temporal (mismo lienzo que T75). */
import { defs } from './obs_graph'
import { esc } from './obs_types'
import { STEP_ICON, STEP_LABEL, type Step } from './obs_trace_types'

const NW = 176, NH = 64, GX = 36, GY = 30, PER_ROW = 5
const clip = (s: string, n: number): string => (s.length > n ? `${s.slice(0, n - 1)}…` : s)
const dur = (ms: number | null): string => (ms == null ? 'n/d' : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`)

const pos = (i: number): { x: number; y: number } => {
  const r = Math.floor(i / PER_ROW), c = i % PER_ROW
  return { x: (r % 2 ? PER_ROW - 1 - c : c) * (NW + GX), y: r * (NH + GY) }   // serpiente: la flecha nunca cruza
}

export function traceSvg(steps: Step[], sel: number): string {
  const rows = Math.max(1, Math.ceil(steps.length / PER_ROW))
  const w = Math.min(steps.length, PER_ROW) * (NW + GX) - GX, h = rows * (NH + GY) - GY
  const edges = steps.slice(1).map((s, i) => {
    const a = pos(i), b = pos(i + 1), prev = steps[i]
    const horiz = a.y === b.y
    const x1 = horiz ? (b.x > a.x ? a.x + NW : a.x) : a.x + NW / 2, y1 = horiz ? a.y + NH / 2 : a.y + NH
    const x2 = horiz ? (b.x > a.x ? b.x - 4 : b.x + NW + 4) : b.x + NW / 2, y2 = horiz ? b.y + NH / 2 : b.y - 4
    const cls = prev.causal && s.causal ? ' causal' : ''
    return `<path class="obs-edge${cls}" d="M${x1},${y1} L${x2},${y2}" marker-end="url(#obs-head)"><title>paso ${prev.n} → paso ${s.n}</title></path>`
  }).join('')
  const nodes = steps.map((s, i) => {
    const { x, y } = pos(i)
    const cls = `obs-node st-${s.status}${s.causal ? ' causal' : ''}${i === sel ? ' sel' : ''}`
    const sub = `${STEP_ICON[s.status] ?? '·'} ${STEP_LABEL[s.status] ?? s.status} · ${dur(s.duration_ms)}`
    return `<g class="obs-n obs-tn" data-step="${i}" tabindex="0" role="button" aria-label="${esc(`Paso ${s.n}: ${s.title_es}, ${STEP_LABEL[s.status] ?? s.status}${s.causal ? ', parte del camino causal' : ''}`)}">
      <title>${esc(s.text_es)}</title><rect class="${cls}" x="${x}" y="${y}" width="${NW}" height="${NH}" rx="${s.kind === 'signal' ? NH / 2 : 10}"/>
      <text class="obs-num" x="${x + 12}" y="${y + 18}">${s.n}${s.causal ? ' ⚑' : ''}</text>
      <text class="obs-t" x="${x + NW / 2}" y="${y + 33}" text-anchor="middle">${esc(clip(s.title_es, 24))}</text>
      <text class="obs-s" x="${x + NW / 2}" y="${y + 50}" text-anchor="middle">${esc(clip(sub, 30))}</text></g>`
  }).join('')
  return `<svg class="obs-svg stage" viewBox="-8 -8 ${w + 16} ${h + 16}" role="img" aria-label="Grafo de ejecución de la traza, ${steps.length} pasos en orden temporal">${defs()}${edges}${nodes}</svg>`
}
