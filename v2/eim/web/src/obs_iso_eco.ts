/** Microecosistema de cada sala del mapa isométrico: los puestos no van en rejilla sino donde les toca según
 * cómo entra, se trabaja y sale la información. Todas las salas usan la misma gramática de zonas:
 *   · fondo (junto al ventanal)     → ENTRADAS: lo primero que recibe de fuera de la sala
 *   · pared izquierda               → VIGILANCIA / SOPORTE: lo que corre siempre o cuida a los demás
 *   · centro                        → TRABAJO: el cuerpo principal de la sala
 *   · lateral (derecha del centro)  → ARCHIVO / REGISTRO: lo que guarda o lleva cuentas
 *   · frente derecho                → CONSOLIDA Y SALE: el puesto principal (más grande) y la salida gruesa
 *   · frente izquierdo              → EN OBRA: lo planeado, translúcido, con cinta y conos
 * Cada sala solo declara qué pieza va en qué zona (`obs_iso_eco_specs`); lo desconocido cae en su zona por
 * defecto y lo planeado siempre en obra. En el piso van, quietos, los flujos internos del catálogo y las
 * salidas hacia otras salas por el borde abierto más cercano, con flechas pequeñas de sentido. Solo ordena y
 * decora: los estados salen de `compState` y las conexiones del catálogo. */
import { arrowsAlong, box, P, pts, type Room } from './obs_iso_geo'
import { continuo, SPECS, ZONES, type Zone } from './obs_iso_eco_specs'
import { art, STRIP } from './obs_iso_props'
import { esc, type ObsComp, type ObsEdge } from './obs_types'

export type { Zone } from './obs_iso_eco_specs'
export type EcoTone = 'ok' | 'bad' | 'none' | 'plan'
const COLOR: Record<EcoTone, string> = { ok: '#0fbf7a', bad: '#f0324f', none: '#8b95aa', plan: '#8b95aa' }
const OBRA_LABEL = 'En obra (planeado)'

export const hasEco = (stage: string): boolean => stage in SPECS

export function zoneOf(stage: string, c: ObsComp): Zone {
  const sp = SPECS[stage]
  if (c.built === 'planeado') return 'obra'
  for (const z of ZONES) if (sp.zones[z]?.ids?.includes(c.id)) return z
  for (const z of ZONES) if (sp.zones[z]?.pick?.(c)) return z
  return sp.fallback
}

/** Separaciones (unidades del piso). Mapa completo: denso. Sala ampliada: con sitio para el nombre de cada
 * puesto, que se abre hacia la izquierda (filas) o la derecha (pared izquierda) sin tapar al vecino. */
interface Mode { gu: number; gv: number; col: number; hub: number; board: number; gap: number; gapL: number; pad: number; padTop: number; padBot: number; kb: number; kh: number; f: number }
const BASE: Mode = { gu: 0.8, gv: 0.8, col: 0.8, hub: 1.05, board: 0.75, gap: 0.3, gapL: 0.3, pad: 0.35, padTop: 0.3, padBot: 0.35, kb: 0.8, kh: 1.15, f: 1 }
const FOCUS: Mode = { gu: 2.1, gv: 5.0, col: 2.1, hub: 2.7, board: 1.9, gap: 1.6, gapL: 3.6, pad: 1.0, padTop: 1.4, padBot: 1.6, kb: 1.36, kh: 1.95, f: 2.6 }
/** Proporción buscada (ancho / fondo) de cada zona: el fondo y el frente son filas; la pared izquierda, columna. */
const ASPECT: Record<Zone, number> = { back: 99, left: 0, center: 1.7, side: 0.6, hub: 99, obra: 3 }
const MAXROW: Record<Zone, number> = { back: 7, left: 99, center: 99, side: 99, hub: 4, obra: 4 }

type Box = [number, number, number, number]          // u0, v0, u1, v1 (coordenadas de la sala)
export interface EcoPlan {
  stage: string; hu: number; hv: number; slots: [number, number][]; ks: number[]; k: number; zones: Zone[]; f: number
  boxes: Partial<Record<Zone, Box>>; labels: Partial<Record<Zone, string>>; tints: Partial<Record<Zone, string>>; board: [number, number] | null
}

/** Ubica los puestos de la sala (mapa completo, o ampliada con `focus`). */
export function ecoPlan(stage: string, list: ObsComp[], focus = false): EcoPlan {
  const m = focus ? FOCUS : BASE, sp = SPECS[stage]
  const by: Record<Zone, number[]> = { back: [], left: [], center: [], side: [], hub: [], obra: [] }
  list.forEach((c, i) => by[zoneOf(stage, c)].push(i))
  const rank = (z: Zone, id: string): number => { const r = sp.zones[z]?.ids?.indexOf(id) ?? -1; return r < 0 ? 999 : r }
  ZONES.forEach((z) => by[z].sort((a, b) => rank(z, list[a].id) - rank(z, list[b].id) || list[a].id.localeCompare(list[b].id)))
  // Tamaño de cada zona: columnas × filas con su separación
  const dims = {} as Record<Zone, { cols: number; w: number; h: number; su: number; sv: number }>
  for (const z of ZONES) {
    const n = by[z].length
    if (!n) { dims[z] = { cols: 0, w: 0, h: 0, su: 0, sv: 0 }; continue }
    const su = z === 'hub' ? m.hub : z === 'left' ? m.col : m.gu, sv = z === 'left' ? m.col : m.gv
    const cols = z === 'left' ? 1 : Math.min(n, MAXROW[z], Math.max(1, Math.round(Math.sqrt((n * ASPECT[z] * sv) / su))))
    dims[z] = { cols, w: cols * su + (z === 'hub' ? m.board : 0), h: Math.ceil(n / cols) * sv, su, sv }
  }
  const has = (z: Zone): boolean => dims[z].w > 0
  const band = (zs: Zone[]): [number, number] => {      // ancho y fondo de una banda de zonas lado a lado
    const on = zs.filter(has); return [on.reduce((s, z) => s + dims[z].w, 0) + Math.max(0, on.length - 1) * m.gap, Math.max(0, ...on.map((z) => dims[z].h))]
  }
  const [wb, hb] = band(['back']), [wm, hm] = band(['center', 'side']), [wf, hf] = band(['obra', 'hub'])
  const bands = [hb, hm, hf].filter((h) => h > 0)
  const colW = Math.max(wb, wm, wf), colH = bands.reduce((s, h) => s + h, 0) + Math.max(0, bands.length - 1) * m.gap
  const xB = has('left') ? dims.left.w + m.gapL : 0, W = xB + colW, H = Math.max(dims.left.h, colH)
  const hu = Math.max(focus ? 3.8 : 1.9, W / 2 + m.pad), hv = Math.max(focus ? 3.8 : 1.9, (H + STRIP + m.padTop + m.padBot + 0.78) / 2)
  const U = (x: number): number => -W / 2 + x, V = (y: number): number => -hv + STRIP + m.padTop + y
  // Origen de cada zona: fondo arriba a la derecha (ventanal), centro debajo, lateral a su derecha,
  // obra al frente a la izquierda y el puesto principal al frente a la derecha (sale corto al borde derecho).
  const org: Partial<Record<Zone, [number, number]>> = {}
  let y = 0
  if (has('left')) org.left = [0, 0]
  if (hb) { org.back = [xB + colW - wb, y]; y += hb + m.gap }
  if (hm) { if (has('center')) org.center = [xB, y]; if (has('side')) org.side = [xB + colW - dims.side.w, y]; y += hm + m.gap }
  if (hf) { if (has('obra')) org.obra = [xB, y]; if (has('hub')) org.hub = [xB + colW - dims.hub.w, y] }
  const slots: [number, number][] = new Array(list.length), ks: number[] = new Array(list.length), zones: Zone[] = new Array(list.length)
  const boxes: Partial<Record<Zone, Box>> = {}, labels: Partial<Record<Zone, string>> = {}, tints: Partial<Record<Zone, string>> = {}
  let board: [number, number] | null = null
  for (const z of ZONES) {
    const o = org[z], d = dims[z]
    if (!o) continue
    const extra = z === 'hub' ? m.board : 0
    boxes[z] = [U(o[0]), V(o[1]), U(o[0] + d.w), V(o[1] + d.h)]
    labels[z] = z === 'obra' ? OBRA_LABEL : sp.zones[z]?.label ?? ''
    const t = sp.zones[z]?.tint; if (t) tints[z] = t
    by[z].forEach((i, j) => {
      const c = j % d.cols, r = Math.floor(j / d.cols)
      slots[i] = [U(o[0] + extra + d.su * (c + 0.5)), V(o[1] + d.sv * (r + 0.5))]
      ks[i] = z === 'hub' && j === 0 ? m.kh : m.kb; zones[i] = z
    })
    if (z === 'hub') board = [U(o[0] + extra * 0.45), V(o[1] + d.sv * 0.5)]
  }
  return { stage, hu, hv, slots, ks, k: m.kb, zones, f: m.f, boxes, labels, tints, board }
}

/* ---------------- dibujo ---------------- */
type UV = [number, number]
export interface EcoCtx {
  list: ObsComp[]; edges: ObsEdge[]; tone: (id: string) => EcoTone; stageOf: (id: string) => string | undefined
  title: (stage: string) => string; stage: string; detail: boolean
}
const at = (r: Room, u: number, v: number, z = 0): [number, number] => P(r.cx, r.cy, u, v, z)
const quad = (r: Room, [u0, v0, u1, v1]: Box, attrs: string): string =>
  `<polygon points="${pts([at(r, u0, v0), at(r, u1, v0), at(r, u1, v1), at(r, u0, v1)])}" ${attrs}/>`
const pathD = (sp: [number, number][]): string => `M${sp.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' L')}`
const grow = (b: Box, g: number): Box => [b[0] - g, b[1] - g, b[2] + g, b[3] + g]

/** Zonas pintadas en el piso (tinte y borde punteado); obra con cinta amarilla; el puesto principal, borde lleno. */
function zonesFloor(r: Room, pl: EcoPlan, accent: string): string {
  let out = ''
  for (const z of ZONES) {
    const b = pl.boxes[z]; if (!b) continue
    const e = grow(b, 0.18 * pl.f)
    if (z === 'obra') { out += quad(r, e, 'fill="#ffd23f" fill-opacity=".1" stroke="#e0a800" stroke-width="2.2" stroke-dasharray="7 5"'); continue }
    const c = pl.tints[z] ?? accent, hub = z === 'hub'
    out += quad(r, e, `fill="${c}" fill-opacity="${hub ? 0.16 : 0.09}" stroke="${c}" stroke-opacity=".55" stroke-width="${hub ? 2 : 1.3}"${hub ? '' : ' stroke-dasharray="6 4"'}`)
  }
  return out
}

/** Nombre de cada zona (solo en la sala ampliada): placa pequeña en la capa de arriba. Se prueba alrededor de la
 * zona (esquinas y bordes) y se queda en el primer sitio libre de figuras, de nombres de puestos (cuelgan bajo
 * los pies hacia su lado) y de las otras placas. */
function zoneTags(r: Room, pl: EcoPlan, ctx: EcoCtx, accent: string): string {
  type Rect = [number, number, number, number]
  const busy: Rect[] = pl.slots.map(([u, v], i) => { const k = pl.ks[i], [x, y] = at(r, u, v + 0.22 * k); return [x - 24 * k, y - 50 * k, x + 24 * k, y + 8] })
  pl.slots.forEach(([u, v], i) => {                       // nombre de cada puesto (como en obs_iso_focus.nameTags)
    const k = pl.ks[i], [x, y] = at(r, u, v + 0.22 * k), w = Math.min(ctx.list[i].title_es.length, 24) * 7 + 26
    const x0 = pl.zones[i] === 'left' ? x - 18 : x - w + 18; busy.push([x0, y + 12, x0 + w, y + 36])
  })
  const hit = (a: Rect): boolean => busy.some((b) => a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1])
  let out = ''
  for (const z of ZONES) {
    const b = pl.boxes[z], txt = (pl.labels[z] ?? '').toLocaleUpperCase('es'); if (!b || !txt) continue
    const e = grow(b, 0.18 * pl.f), c = z === 'obra' ? '#e0a800' : pl.tints[z] ?? accent, w = txt.length * 6.4 + 18
    const mu = (e[0] + e[2]) / 2, mv = (e[1] + e[3]) / 2
    const cands: [number, number][] = [[e[0], e[1]], [e[2], e[1]], [e[0], e[3]], [mu, e[1]], [e[0], mv], [e[2], mv], [mu, e[3]], [e[2], e[3]]]
    let best: Rect | null = null
    for (const [u, v] of cands) for (const dy of [-6, -24, 14]) {
      const [x, y] = at(r, u, v), cand: Rect = [x - w / 2, y + dy - 9, x + w / 2, y + dy + 9]
      if (!hit(cand)) { best = cand; break }
    }
    if (!best) continue                                    // sin sitio libre: mejor sin placa que tapando a alguien
    busy.push(best)
    out += `<g class="iso-ztag"><rect x="${best[0].toFixed(1)}" y="${best[1].toFixed(1)}" width="${w.toFixed(1)}" height="18" rx="4" stroke="${c}"/>`
      + `<text x="${((best[0] + best[2]) / 2).toFixed(1)}" y="${(best[1] + 12.5).toFixed(1)}">${esc(txt)}</text></g>`
  }
  return out
}

/** Trazo quieto con borde blanco y flechas pequeñas de sentido. */
function still(sp: [number, number][], w: number, c: string, arrow: string, f: number, big = false): string {
  const d = pathD(sp)
  return `<path d="${d}" stroke="#ffffff" stroke-width="${(w + 3).toFixed(1)}" opacity=".85"/><path d="${d}" stroke="${c}" stroke-width="${w.toFixed(1)}" class="iso-flow"/>`
    + arrowsAlong(sp, 70 * f, (big ? 4.2 : 3.2) * Math.sqrt(f), arrow)
}

/** Flujos internos (dentro de la sala) en ángulo recto sobre el piso: desde filas bajan por v y cruzan por u;
 * desde la pared izquierda cruzan primero por u. Un carril por conexión para que no se pisen. */
function innerFlows(r: Room, pl: EcoPlan, ctx: EcoCtx): string {
  const idx = new Map(ctx.list.map((c, i) => [c.id, i])), seen = new Set<string>(), f = pl.f
  let out = '', lane = 0
  for (const e of ctx.edges) {
    const a = idx.get(e.source), b = idx.get(e.target), key = `${e.source}>${e.target}`
    if (a == null || b == null || a === b || seen.has(key)) continue
    seen.add(key)
    const [ua, va] = pl.slots[a], [ub, vb] = pl.slots[b], o = ((lane++ % 5) - 2) * 0.05 * f
    const sv = va + 0.32 * pl.ks[a], uFirst = pl.zones[a] === 'left'
    const way: UV[] = uFirst ? [[ua, sv + o], [ub + o, sv + o], [ub + o, vb]] : [[ua + o, sv], [ua + o, vb + o], [ub, vb + o]]
    const plan = pl.zones[a] === 'obra' || pl.zones[b] === 'obra', tone: EcoTone = plan ? 'plan' : ctx.tone(e.source)
    out += `<g class="iso-inner t-${tone}" fill="none"><title>${esc(`${ctx.list[a].title_es} → ${ctx.list[b].title_es} (${e.artifact})`)}</title>`
      + still(way.map(([u, v]) => at(r, u, v)), 2.2 * Math.sqrt(f), COLOR[tone], COLOR[tone], f) + '</g>'
  }
  return out
}

/** Salidas hacia otras salas: el puesto principal sale por el borde derecho; los demás por el borde abierto más
 * cercano (derecho o izquierdo del frente). En la sala ampliada, una placa dice a qué salas va cada una. */
function exits(r: Room, pl: EcoPlan, ctx: EcoCtx): [string, string] {
  const idx = new Map(ctx.list.map((c, i) => [c.id, i])), outs = new Map<number, Set<string>>()
  for (const e of ctx.edges) {
    const a = idx.get(e.source), st = ctx.stageOf(e.target)
    if (a == null || !st || st === ctx.stage) continue
    ;(outs.get(a) ?? outs.set(a, new Set()).get(a)!).add(st)
  }
  let out = '', chips = ''
  const placed: number[][] = [], said = new Set<string>()      // una placa por destino y borde
  const ordered = [...outs].sort((x, y) => pl.slots[x[0]][1] - pl.slots[y[0]][1] || pl.slots[x[0]][0] - pl.slots[y[0]][0])
  ordered.forEach(([i, stages], n) => {
    const [u, v] = pl.slots[i], k = pl.ks[i], plan = pl.zones[i] === 'obra', main = pl.zones[i] === 'hub'
    const tone: EcoTone = plan ? 'plan' : ctx.tone(ctx.list[i].id), c = COLOR[tone]
    const toRight = main || pl.hu - u <= pl.hv - v, lv = v + 0.3 * k + (main ? 0 : ((n % 3) - 1) * 0.06 * pl.f)
    const way: UV[] = toRight ? [[u, lv], [pl.hu + 0.05, lv]] : [[u + 0.12 * pl.f, v + 0.3 * k], [u + 0.12 * pl.f, pl.hv + 0.05]]
    const names = [...stages].map((s) => ctx.title(s).split(/ \/ | y /)[0]), end = way[1]
    out += `<g class="iso-inner t-${tone}${main ? ' main' : ''}" fill="none"><title>${esc(`${ctx.list[i].title_es} → ${names.join(', ')}`)}</title>`
      + still(way.map(([p, q]) => at(r, p, q)), (main ? 4.5 : 2.4) * Math.sqrt(pl.f), c, main ? '#ffffff' : c, pl.f, main) + '</g>'
    const a = 0.2 * pl.f * (main ? 1.3 : 1), [eu, ev] = end                       // flecha en el borde
    const tri: UV[] = toRight ? [[eu + a, ev], [eu - a * 0.4, ev - a * 0.7], [eu - a * 0.4, ev + a * 0.7]] : [[eu, ev + a], [eu - a * 0.7, ev - a * 0.4], [eu + a * 0.7, ev - a * 0.4]]
    out += `<polygon points="${pts(tri.map(([p, q]) => at(r, p, q)))}" fill="${c}" stroke="#fff" stroke-width="1"/>`
    if (!ctx.detail) return
    const [x, y0] = at(r, eu + (toRight ? 0.45 * pl.f : 0), ev + (toRight ? 0 : 0.45 * pl.f)), txt = `→ ${names.slice(0, 3).join(' · ')}${names.length > 3 ? ' …' : ''}`
    const tw = txt.length * 6.3 + 16, x0 = toRight ? x - 4 : x - tw + 8, key = `${toRight}|${txt}`
    if (said.has(key)) return
    said.add(key)
    let y = y0
    const hit = (yy: number): boolean => placed.some((q) => x0 < q[2] && x0 + tw > q[0] && yy - 11 < q[3] && yy + 11 > q[1])
    for (let g = 0; g < 12 && hit(y); g++) y += 23
    placed.push([x0, y - 11, x0 + tw, y + 11])
    chips += `<g class="iso-exit"><rect x="${x0.toFixed(1)}" y="${(y - 10).toFixed(1)}" width="${tw.toFixed(1)}" height="20" rx="10" stroke="${c}"/>`
      + `<text x="${(x0 + tw / 2).toFixed(1)}" y="${(y + 4).toFixed(1)}">${esc(txt)}</text></g>`
  })
  return [out, chips]
}

/** Mobiliario con profundidad (se ordena junto con los puestos): tablero del puesto principal, conos de la obra
 * y plantas en las esquinas libres del frente. `depth` = u + v del punto de apoyo. */
function props(r: Room, pl: EcoPlan): { svg: string; depth: number }[] {
  const f = pl.f, kf = pl.k / BASE.kb, out: { svg: string; depth: number }[] = []
  const add = (u: number, v: number, svg: string): void => { out.push({ svg, depth: u + v }) }
  if (pl.board) {                         // tablero de pie junto al puesto principal, con barras encendidas
    const [bu, bv] = pl.board, bw = 0.62 * kf, bh = 0.42 * kf, z0 = 0.3 * kf
    const sc = (du: number, z: number): [number, number] => at(r, bu + du, bv, z)
    let s = box(r, bu, bv, 0.08 * kf, 0.08 * kf, z0, 0, '#9aa7bf', '#6b7891', '#7d8aa3')
    s += `<polygon points="${pts([sc(-bw / 2, z0), sc(bw / 2, z0), sc(bw / 2, z0 + bh), sc(-bw / 2, z0 + bh)])}" fill="#061a2c" stroke="#12a9d6" stroke-width="1.6"/>`
    s += [0.2, 0.48, 0.34, 0.65, 0.52].map((h, j) => { const x = -bw / 2 + bw * (0.13 + j * 0.17), z1 = z0 + 0.05 * kf, hh = h * bh * 0.8
      return `<polygon points="${pts([sc(x, z1), sc(x + bw * 0.1, z1), sc(x + bw * 0.1, z1 + hh), sc(x, z1 + hh)])}" fill="#2ee6ff" opacity=".75"/>` }).join('')
    add(bu, bv, s)
  }
  const ob = pl.boxes.obra
  if (ob) for (const [u, v] of [[ob[0] - 0.12 * f, ob[1] - 0.12 * f], [ob[2] + 0.12 * f, ob[3] + 0.12 * f]] as UV[]) {
    const b = at(r, u, v), t = at(r, u, v, 0.32 * kf), w = 7 * kf
    add(u, v, `<polygon points="${pts([[b[0] - w, b[1]], [b[0] + w, b[1]], t])}" fill="#ff8a1f" stroke="#c45f00" stroke-width="1"/><rect x="${(b[0] - w * 0.55).toFixed(1)}" y="${(b[1] - 0.13 * kf * 40).toFixed(1)}" width="${(w * 1.1).toFixed(1)}" height="${(2.2 * kf).toFixed(1)}" fill="#fff"/>`)
  }
  const free = (u: number, v: number): boolean => !Object.values(pl.boxes).some((b) => b && u > b[0] - 0.6 * f && u < b[2] + 0.6 * f && v > b[1] - 0.6 * f && v < b[3] + 0.6 * f)
  const vF = pl.hv - 0.78 - 0.45 * f
  for (const [u, v, name, h] of [[pl.hu - 0.4 * f, vF, 'planta_alta', 44], [-pl.hu + 0.45 * f, vF, 'arbol', 34]] as [number, number, string, number][])
    if (free(u, v)) add(u, v, art(name, at(r, u, v), h * kf))
  return out
}

/** Detalles de cada puesto según su ritmo: lo continuo tiene un ecualizador que alterna sus barras (a saltos,
 * con el reloj de la sala); el puesto principal, dos monitores más. */
export function ecoExtra(r: Room, pl: EcoPlan, i: number, c: ObsComp): string {
  const [u, v] = pl.slots[i], k = pl.ks[i], dv = v - 0.18 * k
  if (pl.zones[i] === 'hub' && k > pl.k) return [-0.3, 0.38].map((du) => art('monitor', at(r, u + du * k, dv - 0.02 * k, 0.26 * k), 15 * k)).join('')
  if (c.built !== 'planeado' && continuo(c)) {
    const b = at(r, u - 0.24 * k, dv, 0.27 * k)
    return [6, 9, 4].map((h, j) => `<rect x="${(b[0] + j * 3.2 * k).toFixed(1)}" y="${(b[1] - h * k).toFixed(1)}" width="${(2.2 * k).toFixed(1)}" height="${(h * k).toFixed(1)}" fill="#2ee6ff" class="iso-eq"${j % 2 ? ' style="animation-delay:-0.8s"' : ''}/>`).join('')
  }
  return ''
}

/** Lo que la sala pinta además de los puestos: piso (zonas, flujos, salidas), mobiliario con profundidad y,
 * aparte, las placas de salidas y de zonas (capa de arriba, solo en la sala ampliada). */
export function ecoDraw(r: Room, pl: EcoPlan, ctx: EcoCtx, accent: string): { floor: string; props: { svg: string; depth: number }[]; top: string } {
  const [ex, chips] = exits(r, pl, ctx)
  return { floor: zonesFloor(r, pl, accent) + innerFlows(r, pl, ctx) + ex, props: props(r, pl), top: ctx.detail ? chips + zoneTags(r, pl, ctx, accent) : '' }
}
