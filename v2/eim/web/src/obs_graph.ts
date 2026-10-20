/** Dibujo del mapa (T75): nivel 1 «Ruta» y nivel 2 «Etapa» en SVG propio (sin librería). */
import { ago, esc, STATE_ICON, STATE_LABEL, stateOf, type ObsComp, type ObsData, type ObsState } from './obs_types'

const NW = 176, NH = 64, GX = 44, GY = 18

export const compState = (d: ObsData, c: ObsComp): ObsState => stateOf(c, d)

const count = (d: ObsData, list: ObsComp[]): Record<ObsState, number> => {
  const n = { ok: 0, degradado: 0, error: 0, obsoleto: 0, pausado: 0, sin_datos: 0, planeado: 0 } as Record<ObsState, number>
  for (const c of list) n[compState(d, c)]++
  return n
}

/** Peor estado de una etapa, para el color del bloque (ignora lo planeado). */
export function worst(n: Record<ObsState, number>): ObsState {
  for (const s of ['error', 'degradado', 'obsoleto', 'sin_datos', 'pausado'] as ObsState[]) if (n[s]) return s
  return n.ok ? 'ok' : 'planeado'
}

/** Frase del resumen de etapa, armada con los conteos reales. */
export function stageSentence(d: ObsData, stage: string): string {
  const list = d.comps.filter((c) => c.stage === stage)
  const built = list.filter((c) => c.built === 'construido')
  const n = count(d, list)
  if (!list.length) return 'Sin componentes.'
  const parts = [`${n.ok} de ${built.length} al día`]
  if (n.error) parts.push(`${n.error} con error`)
  if (n.degradado) parts.push(`${n.degradado} con datos incompletos`)
  if (n.obsoleto) parts.push(`${n.obsoleto} con dato viejo`)
  if (n.sin_datos) parts.push(`${n.sin_datos} sin datos recientes`)
  if (n.pausado) parts.push(`${n.pausado} en pausa`)
  if (n.planeado) parts.push(`${n.planeado} planeados`)
  return parts.join(', ')
}

const shapeOf = (c: ObsComp, x: number, y: number, cls: string): string => {
  if (c.kind === 'gate') return `<polygon class="${cls}" points="${x + 14},${y} ${x + NW - 14},${y} ${x + NW},${y + NH / 2} ${x + NW - 14},${y + NH} ${x + 14},${y + NH} ${x},${y + NH / 2}"/>`
  if (c.kind === 'agent') return `<rect class="${cls}" x="${x}" y="${y}" width="${NW}" height="${NH}" rx="${NH / 2}"/>`
  if (c.kind === 'store') return `<rect class="${cls}" x="${x}" y="${y}" width="${NW}" height="${NH}" rx="4"/><line class="obs-cap" x1="${x}" x2="${x + NW}" y1="${y + 10}" y2="${y + 10}"/>`
  return `<rect class="${cls}" x="${x}" y="${y}" width="${NW}" height="${NH}" rx="10"/>`
}

const clip = (s: string, n: number): string => (s.length > n ? `${s.slice(0, n - 1)}…` : s)

/** Un componente como grupo SVG clicable; etiqueta accesible con el estado en palabras. */
function node(d: ObsData, c: ObsComp, x: number, y: number, sel: string | null): string {
  const st = compState(d, c)
  const sub = c.built === 'planeado' ? `planeado · ${c.task}` : `${STATE_ICON[st]} ${STATE_LABEL[st]} · ${ago(c.last_event_ms)}`
  const cls = `obs-node st-${st}${c.id === sel ? ' sel' : ''}`
  return `<g class="obs-n" data-id="${esc(c.id)}" tabindex="0" role="button" aria-label="${esc(`${c.title_es}: ${STATE_LABEL[st]}`)}">
    <title>${esc(c.title_es)} — ${STATE_LABEL[st]}</title>${shapeOf(c, x, y, cls)}
    <text class="obs-t" x="${x + NW / 2}" y="${y + 27}" text-anchor="middle">${esc(clip(c.title_es, 24))}</text>
    <text class="obs-s" x="${x + NW / 2}" y="${y + 46}" text-anchor="middle">${esc(clip(sub, 30))}</text></g>`
}

export const defs = (): string =>
  '<defs><marker id="obs-head" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="obs-ah"/></marker></defs>'

/** Nivel 1: siete tarjetas (HTML, texto legible) que se parten en filas según el ancho. */
export function routeHtml(d: ObsData, sel: string | null): string {
  const n = d.graph.stages.length
  const cards = d.graph.stages.map((s, i) => {
    const list = d.comps.filter((c) => c.stage === s), cnt = count(d, list), w = worst(cnt)
    const dots = (['ok', 'degradado', 'error', 'obsoleto', 'sin_datos', 'pausado', 'planeado'] as ObsState[])
      .filter((k) => cnt[k]).map((k) => `<span class="obs-dot st-${k}" title="${STATE_LABEL[k]}">${STATE_ICON[k]} ${cnt[k]}</span>`).join('')
    return `<div class="obs-n obs-stage obs-card st-${w}${s === sel ? ' sel' : ''}" data-stage="${s}" tabindex="0" role="button"
        aria-label="${esc(`${d.graph.stage_titles_es[s]}: ${stageSentence(d, s)}`)}">
      <div class="obs-card-h"><span class="obs-num">${i + 1}</span><b>${esc(d.graph.stage_titles_es[s])}</b></div>
      <div class="obs-dots">${dots || '—'}</div><p class="obs-sent">${esc(stageSentence(d, s))}</p></div>${i < n - 1 ? '<span class="obs-rarrow" aria-hidden="true">➜</span>' : ''}`
  }).join('')
  return `<div class="obs-rt" role="group" aria-label="Ruta del sistema en ${n} etapas">${cards}</div>`
}

interface Pos { x: number; y: number }
/** Nivel 2: columnas por profundidad dentro de la etapa; las columnas largas se parten. */
export function stageLayout(d: ObsData, stage: string): { list: ObsComp[]; pos: Map<string, Pos>; w: number; h: number } {
  const list = d.comps.filter((c) => c.stage === stage)
  const ids = new Set(list.map((c) => c.id))
  const depth = new Map<string, number>()
  const dep = (c: ObsComp, seen: Set<string>): number => {
    if (depth.has(c.id)) return depth.get(c.id)!
    if (seen.has(c.id)) return 0
    seen.add(c.id)
    const ups = c.consumes.map((f) => list.find((x) => x.id === f.source)).filter((x): x is ObsComp => !!x && ids.has(x.id))
    const v = ups.length ? 1 + Math.max(...ups.map((u) => dep(u, seen))) : 0
    depth.set(c.id, v); return v
  }
  list.forEach((c) => dep(c, new Set()))
  const cols = new Map<number, ObsComp[]>()
  list.forEach((c) => { const k = depth.get(c.id)!; cols.set(k, [...(cols.get(k) ?? []), c]) })
  const maxCol = Math.max(0, ...cols.keys()), wrapRows = Math.min(Math.max(1, ...[...cols.values()].map((v) => v.length)), 8)
  const pos = new Map<string, Pos>()
  let extra = 0
  for (let k = 0; k <= maxCol; k++) {
    const v = cols.get(k) ?? []
    v.forEach((c, i) => pos.set(c.id, { x: (k + extra + Math.floor(i / wrapRows)) * (NW + GX), y: (i % wrapRows) * (NH + GY) }))
    extra += Math.max(0, Math.ceil(v.length / wrapRows) - 1)
  }
  return { list, pos, w: (maxCol + extra + 1) * (NW + GX) - GX, h: wrapRows * (NH + GY) - GY }
}

export function stageSvg(d: ObsData, stage: string, sel: string | null): string {
  const { list, pos, w, h } = stageLayout(d, stage)
  const dev = d.graph.deviations
  const planned = (id: string): boolean => d.comps.find((c) => c.id === id)?.built === 'planeado'
  const edges: string[] = []
  const draw = (s: string, t: string, art: string, cls: string): void => {
    const a = pos.get(s), b = pos.get(t)
    if (!a || !b) return
    const x1 = a.x + NW, y1 = a.y + NH / 2, x2 = b.x, y2 = b.y + NH / 2, mx = (x1 + x2) / 2
    const path = x2 <= x1
      ? `M${a.x + NW / 2},${a.y + NH} C${a.x + NW / 2},${a.y + NH + 30} ${b.x + NW / 2},${b.y - 30} ${b.x + NW / 2},${b.y}`
      : `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2 - 4},${y2}`
    edges.push(`<path class="obs-edge ${cls}${planned(s) || planned(t) ? ' planned' : ''}" data-s="${esc(s)}" data-t="${esc(t)}" d="${path}" marker-end="url(#obs-head)"><title>${esc(`${s} → ${t}: ${art}`)}</title></path>`)
  }
  for (const c of list) for (const f of c.consumes) {
    draw(f.source, c.id, f.artifact, dev.unseen.some((e) => e.source === f.source && e.target === c.id) ? 'unseen' : '')
  }
  for (const e of dev.undeclared) draw(e.source, e.target, 'vista y no declarada', 'undeclared')
  const nodes = list.map((c) => node(d, c, pos.get(c.id)!.x, pos.get(c.id)!.y, sel)).join('')
  return `<svg class="obs-svg stage" viewBox="-8 -24 ${w + 16} ${h + 44}" role="img" aria-label="Componentes de la etapa ${esc(d.graph.stage_titles_es[stage])}">${defs()}${edges.join('')}${nodes}</svg>`
}

/** Vecinos de un componente: de quién depende y a quién afecta (estructural). */
export function neighbours(d: ObsData, id: string): { from: { c: ObsComp; artifact: string }[]; to: { c: ObsComp; artifact: string }[] } {
  const by = new Map(d.comps.map((c) => [c.id, c]))
  const from = (by.get(id)?.consumes ?? []).flatMap((f) => (by.get(f.source) ? [{ c: by.get(f.source)!, artifact: f.artifact }] : []))
  const to = d.graph.edges.filter((e) => e.source === id).flatMap((e) => (by.get(e.target) ? [{ c: by.get(e.target)!, artifact: e.artifact }] : []))
  return { from, to }
}
