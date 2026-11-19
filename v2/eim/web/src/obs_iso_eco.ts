/** Microecosistema de una sala del mapa isométrico: los puestos no van en rejilla sino donde les toca
 * según cómo sale la información. Empieza con «1. Datos»:
 *   · Ventanillas (fila del fondo, junto al ventanal que mira al mercado): fuentes externas que se consultan.
 *   · Monitoreo continuo (columna junto a la pared de pantallas): lo que escucha el mercado sin parar.
 *   · Archivo (centro): el almacén de velas, con su rack y su archivador.
 *   · Fotografía (puesto principal, más grande): junta todo y lo reparte por la salida grande.
 *   · En obra (frente): lo planeado, translúcido y con cinta.
 * En el piso van los flujos internos declarados (de quién recibe cada puesto, animados con el estado de
 * quien entrega) y las salidas laterales hacia otras salas por el borde más cercano. Solo ordena y decora:
 * los estados siguen saliendo de `compState`; las conexiones, del catálogo. */
import { box, P, pts, type Room } from './obs_iso_geo'
import { art, STRIP } from './obs_iso_props'
import { esc, type ObsComp, type ObsEdge } from './obs_types'

export type EcoTone = 'ok' | 'bad' | 'none' | 'plan'
export type Zone = 'fuente' | 'continuo' | 'archivo' | 'jefe' | 'obra'
const COLOR: Record<EcoTone, string> = { ok: '#0fbf7a', bad: '#f0324f', none: '#8b95aa', plan: '#8b95aa' }

/** Puestos ya ubicados: medio ancho de la sala, posición y tamaño de cada puesto (en el orden de `list`). */
export interface EcoPlan { hu: number; hv: number; slots: [number, number][]; ks: number[]; k: number; zones: Zone[]; f: number; uF0: number }

/** Lo que la sala necesita saber del resto del mapa para pintar flujos y salidas. */
export interface EcoCtx {
  list: ObsComp[]; edges: ObsEdge[]; tone: (id: string) => EcoTone; stageOf: (id: string) => string | undefined
  title: (stage: string) => string; stage: string; detail: boolean
}

const ZONE_OF: Record<string, Zone> = {
  'data.snapshot': 'jefe', 'data.store': 'archivo',
  'data.live_ticks': 'continuo', 'data.micro_collector': 'continuo', 'data.hft_collector': 'continuo', 'data.liq_collector': 'continuo',
}
/** Orden dentro de cada zona: las fuentes que salen directo a otras salas quedan cerca de su salida. */
const ORDER = ['data.binance_rest', 'data.liquidations', 'data.news', 'data.calendar', 'leaders.service', 'data.arb_market',
  'data.micro_collector', 'data.liq_collector', 'data.live_ticks', 'data.hft_collector']
const pos = (id: string): number => { const i = ORDER.indexOf(id); return i < 0 ? ORDER.length : i }

export function zoneOf(c: ObsComp): Zone {
  if (c.built === 'planeado') return 'obra'
  const z = ZONE_OF[c.id]
  if (z) return z
  if (c.kind === 'store') return 'archivo'
  return /continuo/i.test(c.cadence ?? '') ? 'continuo' : 'fuente'
}

export const hasEco = (stage: string): boolean => stage === 'datos'

const KB = 0.8, KJ = 1.18          // tamaño de un puesto y del puesto principal (mapa completo)

/** Ubica los puestos de la sala. `f` amplía todo (sala enfocada) dejando sitio a los nombres. */
export function ecoPlan(list: ObsComp[], f = 1, kf = 1): EcoPlan {
  const by: Record<Zone, number[]> = { fuente: [], continuo: [], archivo: [], jefe: [], obra: [] }
  list.forEach((c, i) => by[zoneOf(c)].push(i))
  ;(Object.keys(by) as Zone[]).forEach((z) => by[z].sort((a, b) => pos(list[a].id) - pos(list[b].id) || list[a].id.localeCompare(list[b].id)))
  const nF = by.fuente.length, nC = by.continuo.length
  const step = 0.8, uF0 = f > 1 ? -0.95 : -1.45, vF = -2.7 + STRIP + 0.4      // ampliada: la fila se aparta de la esquina
  const hu = Math.max(2.95, uF0 + Math.max(nF - 1, 0) * step + 0.55), hv = Math.max(2.7, 1.25 + (Math.max(nC, 4) - 1) * step / 2 + 0.2)
  const slots: [number, number][] = new Array(list.length), ks: number[] = new Array(list.length), zones: Zone[] = new Array(list.length)
  const put = (i: number, u: number, v: number, k: number, z: Zone): void => { slots[i] = [u * f, v * f]; ks[i] = k * kf; zones[i] = z }
  by.fuente.forEach((i, j) => put(i, uF0 + (j % 8) * step, vF + Math.floor(j / 8) * 0.85, KB, 'fuente'))
  const cStep = nC > 1 ? Math.min(step, (1.42 - vF) / (nC - 1)) : step
  by.continuo.forEach((i, j) => put(i, -hu + 0.55, vF + j * cStep, KB, 'continuo'))
  by.archivo.forEach((i, j) => put(i, -1.15 + j * 0.75, -0.3, KB, 'archivo'))
  by.jefe.forEach((i, j) => put(i, 0.95 + j * 0.9, 0.35 + j * 0.6, j ? KB : KJ, 'jefe'))
  by.obra.forEach((i, j) => put(i, -1.5 + (j % 3) * 0.7, 1.2 - Math.floor(j / 3) * 0.6, KB, 'obra'))
  return { hu: hu * f, hv: hv * f, slots, ks, k: KB * kf, zones, f, uF0 }
}

/* ---------------- dibujo ---------------- */
type UV = [number, number]
const at = (r: Room, u: number, v: number, z = 0): [number, number] => P(r.cx, r.cy, u, v, z)
const quad = (r: Room, u0: number, v0: number, u1: number, v1: number, attrs: string): string =>
  `<polygon points="${pts([at(r, u0, v0), at(r, u1, v0), at(r, u1, v1), at(r, u0, v1)])}" ${attrs}/>`
const pathD = (r: Room, uv: UV[]): string => `M${uv.map(([u, v]) => at(r, u, v)).map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' L')}`
/** Texto pintado en el piso, a lo largo del eje u (frente a una fila) o del eje v (junto a la pared izquierda). */
function floorText(r: Room, u: number, v: number, txt: string, fs: number, axis: 'u' | 'v', fill: string): string {
  const [x, y] = at(r, u, v), m = axis === 'u' ? '0.866 0.5 -0.866 0.5' : '0.866 -0.5 0.866 0.5'
  return `<text class="iso-zname" transform="matrix(${m} ${x.toFixed(1)} ${y.toFixed(1)})" font-size="${fs.toFixed(1)}" fill="${fill}">${esc(txt)}</text>`
}

/** Zonas pintadas en el piso con su nombre (el nombre solo en la sala enfocada, para no ensuciar el mapa). */
function zonesFloor(r: Room, pl: EcoPlan, accent: string, detail: boolean): string {
  const f = pl.f, hu = pl.hu / f, vF = -2.7 + STRIP + 0.4, s = (x: number): number => x * f
  const tint = (c: string, o = 0.09): string => `fill="${c}" fill-opacity="${o}" stroke="${c}" stroke-opacity=".55" stroke-width="1.3" stroke-dasharray="6 4"`
  let out = quad(r, s(pl.uF0 - 0.45), s(vF - 0.5), s(hu - 0.12), s(vF + 0.62), tint(accent))                     // ventanillas
    + quad(r, s(-hu + 0.12), s(vF - 0.5), s(-hu + 1.0), s(1.75), tint('#2ee6ff', 0.1))                       // monitoreo continuo
    + quad(r, s(-1.6), s(-0.78), s(-0.62), s(0.2), tint('#7d8aa6', 0.12))                                    // archivo
    + quad(r, s(-1.95), s(0.82), s(0.15), s(1.7), 'fill="#ffd23f" fill-opacity=".1" stroke="#e0a800" stroke-width="2.2" stroke-dasharray="7 5"')   // en obra
  const [jx, jy] = at(r, s(0.95), s(0.55))                                                                   // tapete del puesto principal
  out += `<ellipse cx="${jx.toFixed(1)}" cy="${jy.toFixed(1)}" rx="${(s(1.05) * 34.6).toFixed(1)}" ry="${(s(1.05) * 20).toFixed(1)}" fill="${accent}" fill-opacity=".13" stroke="${accent}" stroke-opacity=".7" stroke-width="2"/>`
    + `<ellipse cx="${jx.toFixed(1)}" cy="${jy.toFixed(1)}" rx="${(s(0.78) * 34.6).toFixed(1)}" ry="${(s(0.78) * 20).toFixed(1)}" fill="none" stroke="${accent}" stroke-opacity=".45" stroke-dasharray="3 5"/>`
  if (detail) {
    const fs = 10.5, ink = '#1d3b52'
    out += floorText(r, s(pl.uF0 - 0.4), s(vF - 0.3), 'VENTANILLAS · FUENTES EXTERNAS', fs, 'u', ink)
      + floorText(r, s(-hu + 0.3), s(1.6), 'MONITOREO CONTINUO', fs, 'v', ink)
      + floorText(r, s(-1.55), s(0.15), 'ARCHIVO', fs, 'u', ink)
      + floorText(r, s(-1.9), s(1.64), 'EN OBRA · VIDEO (PLANEADO)', fs, 'u', '#8a6a00')
      + floorText(r, s(0.35), s(1.5), 'FOTOGRAFÍA · REPARTO', fs, 'u', ink)
  }
  return out
}

/** Flujos internos (dentro de la sala) en ángulo recto sobre el piso: de las ventanillas bajan por v y luego
 * cruzan por u; del monitoreo cruzan primero por u. Un carril por conexión para que no se pisen. */
function innerFlows(r: Room, pl: EcoPlan, ctx: EcoCtx): string {
  const idx = new Map(ctx.list.map((c, i) => [c.id, i])), seen = new Set<string>(), f = pl.f
  let out = '', lane = 0
  for (const e of ctx.edges) {
    const a = idx.get(e.source), b = idx.get(e.target), key = `${e.source}>${e.target}`
    if (a == null || b == null || seen.has(key)) continue
    seen.add(key)
    const [ua, va] = pl.slots[a], [ub, vb] = pl.slots[b], o = ((lane++ % 5) - 2) * 0.05 * f
    const sv = va + 0.32 * pl.ks[a], vFirst = pl.zones[a] === 'fuente' || pl.zones[a] === 'obra'
    const way: UV[] = vFirst ? [[ua + o, sv], [ua + o, vb + o], [ub, vb + o]] : [[ua, sv + o], [ub + o, sv + o], [ub + o, vb]]
    const t = ctx.tone(e.source), plan = pl.zones[a] === 'obra' || pl.zones[b] === 'obra', tone: EcoTone = plan ? 'plan' : t
    const d = pathD(r, way), w = 2.2 * Math.sqrt(f)
    out += `<g class="iso-inner t-${tone}" fill="none"><title>${esc(`${ctx.list[a].title_es} → ${ctx.list[b].title_es} (${e.artifact})`)}</title>`
      + `<path d="${d}" stroke="#ffffff" stroke-width="${(w + 3).toFixed(1)}" opacity=".85"/><path d="${d}" stroke="${COLOR[tone]}" stroke-width="${w.toFixed(1)}" class="iso-flow"/></g>`
  }
  return out
}

/** Salidas laterales: cada puesto que entrega a otra sala sale por el borde abierto más cercano
 * (frente derecho o frente izquierdo) con una flecha; en la sala enfocada dice a qué salas va. */
function exits(r: Room, pl: EcoPlan, ctx: EcoCtx): string {
  const idx = new Map(ctx.list.map((c, i) => [c.id, i])), outs = new Map<number, Set<string>>()
  for (const e of ctx.edges) {
    const a = idx.get(e.source), st = ctx.stageOf(e.target)
    if (a == null || !st || st === ctx.stage) continue
    ;(outs.get(a) ?? outs.set(a, new Set()).get(a)!).add(st)
  }
  let out = '', chips = ''
  const placed: number[][] = []                       // etiquetas ya puestas: la siguiente que choque se aparta
  const ordered = [...outs].sort((x, y) => pl.slots[x[0]][1] - pl.slots[y[0]][1] || pl.slots[x[0]][0] - pl.slots[y[0]][0])
  ordered.forEach(([i, stages], n) => {
    const [u, v] = pl.slots[i], k = pl.ks[i], plan = pl.zones[i] === 'obra', main = pl.zones[i] === 'jefe'
    const tone: EcoTone = plan ? 'plan' : ctx.tone(ctx.list[i].id), c = COLOR[tone]
    const toRight = main || pl.hu - u <= pl.hv - v, lv = v + 0.3 * k + (main ? 0 : ((n % 3) - 1) * 0.06 * pl.f)
    const way: UV[] = toRight ? [[u, lv], [pl.hu + 0.05, lv]] : [[u + 0.12 * pl.f, v + 0.3 * k], [u + 0.12 * pl.f, pl.hv + 0.05]]
    const w = (main ? 5 : 2.4) * Math.sqrt(pl.f), d = pathD(r, way), end = way[1]
    const names = [...stages].map((s) => ctx.title(s).split(/ \/ | y /)[0])
    out += `<g class="iso-inner t-${tone}${main ? ' main' : ''}" fill="none"><title>${esc(`${ctx.list[i].title_es} → ${names.join(', ')}`)}</title>`
      + `<path d="${d}" stroke="#ffffff" stroke-width="${(w + 3).toFixed(1)}" opacity=".85"/><path d="${d}" stroke="${c}" stroke-width="${w.toFixed(1)}" class="iso-flow"/></g>`
    const a = 0.2 * pl.f * (main ? 1.3 : 1), [eu, ev] = end                       // flecha en el borde
    const tri: UV[] = toRight ? [[eu + a, ev], [eu - a * 0.4, ev - a * 0.7], [eu - a * 0.4, ev + a * 0.7]] : [[eu, ev + a], [eu - a * 0.7, ev - a * 0.4], [eu + a * 0.7, ev - a * 0.4]]
    out += `<polygon points="${pts(tri.map(([p, q]) => at(r, p, q)))}" fill="${c}" stroke="#fff" stroke-width="1"/>`
    if (ctx.detail) {
      const [x, y0] = at(r, eu + (toRight ? 0.45 * pl.f : 0), ev + (toRight ? 0 : 0.45 * pl.f)), txt = `→ ${names.slice(0, 3).join(' · ')}${names.length > 3 ? ' …' : ''}`
      const tw = txt.length * 6.3 + 16, x0 = toRight ? x - 4 : x - tw + 8
      let y = y0
      const hit = (yy: number): boolean => placed.some((q) => x0 < q[2] && x0 + tw > q[0] && yy - 11 < q[3] && yy + 11 > q[1])
      for (let g = 0; g < 8 && hit(y); g++) y += 23
      placed.push([x0, y - 11, x0 + tw, y + 11])
      chips += `<g class="iso-exit"><rect x="${x0.toFixed(1)}" y="${(y - 10).toFixed(1)}" width="${tw.toFixed(1)}" height="20" rx="10" stroke="${c}"/>`
        + `<text x="${(x0 + tw / 2).toFixed(1)}" y="${(y + 4).toFixed(1)}">${esc(txt)}</text></g>`
    }
  })
  return out + chips
}

/** Mobiliario con profundidad (se ordena junto con los puestos): rack y archivador del archivo, tablero del
 * puesto principal, conos de la obra y plantas. `depth` = u + v del punto de apoyo. */
function props(r: Room, pl: EcoPlan): { svg: string; depth: number }[] {
  const f = pl.f, s = (x: number): number => x * f, hu = pl.hu / f, hv = pl.hv / f, out: { svg: string; depth: number }[] = []
  const add = (u: number, v: number, svg: string): void => { out.push({ svg, depth: s(u) + s(v) }) }
  // Archivo: archivador y estante bajos detrás del almacén (los racks del fondo siguen junto al ventanal)
  const kf = pl.k / KB
  add(-0.75, -0.8, art('archivador', at(r, s(-0.75), s(-0.8)), 30 * kf))
  add(-1.55, -0.75, art('estante', at(r, s(-1.55), s(-0.75)), 20 * kf))
  // Tablero del puesto principal: pantalla de pie detrás, con la «fotografía» (barras y curva) encendida
  const bu = 0.05, bv = 0.75, bw = 0.62, bh = 0.42, z0 = 0.3
  const sc = (du: number, z: number): [number, number] => at(r, s(bu + du), s(bv), s(z))
  let board = box(r, s(bu), s(bv), s(0.08), s(0.08), s(z0), 0, '#9aa7bf', '#6b7891', '#7d8aa3')
  board += `<polygon points="${pts([sc(-bw / 2, z0), sc(bw / 2, z0), sc(bw / 2, z0 + bh), sc(-bw / 2, z0 + bh)])}" fill="#061a2c" stroke="#12a9d6" stroke-width="1.6"/>`
  board += [0.08, 0.2, 0.14, 0.27, 0.22].map((h, j) => { const x = -bw / 2 + 0.08 + j * 0.105
    return `<polygon points="${pts([sc(x, z0 + 0.06), sc(x + 0.06, z0 + 0.06), sc(x + 0.06, z0 + 0.06 + h), sc(x, z0 + 0.06 + h)])}" fill="#2ee6ff" opacity=".75"/>` }).join('')
  board += `<polyline points="${pts([sc(-0.27, z0 + 0.2), sc(-0.12, z0 + 0.29), sc(0.02, z0 + 0.25), sc(0.15, z0 + 0.36), sc(0.27, z0 + 0.34)])}" fill="none" stroke="#12e58f" stroke-width="${(1.8 * Math.sqrt(f)).toFixed(1)}"/>`
  add(bu, bv, board)
  // Obra: conos naranjas en las esquinas de la cinta
  for (const [u, v] of [[-1.85, 0.92], [0.05, 1.6]] as UV[]) {
    const b = at(r, s(u), s(v)), t = at(r, s(u), s(v), s(0.32)), w = 7 * Math.sqrt(f)
    add(u, v, `<polygon points="${pts([[b[0] - w, b[1]], [b[0] + w, b[1]], t])}" fill="#ff8a1f" stroke="#c45f00" stroke-width="1"/><rect x="${(b[0] - w * 0.55).toFixed(1)}" y="${(b[1] - s(0.13) * 40).toFixed(1)}" width="${(w * 1.1).toFixed(1)}" height="${(2.2 * Math.sqrt(f)).toFixed(1)}" fill="#fff"/>`)
  }
  // Verde: planta entre las ventanillas y el archivo, planta alta en la esquina de salida
  add(-0.25, -0.75, art('planta', at(r, s(-0.25), s(-0.75)), s(26)))
  add(hu - 0.35, hv - 1.25, art('planta_alta', at(r, s(hu - 0.35), s(hv - 1.25)), s(46)))
  return out
}

/** Detalles de cada puesto según su ritmo: lo continuo tiene un ecualizador que alterna sus barras; el
 * puesto principal, dos monitores más. Lo planeado no lleva nada. */
export function ecoExtra(r: Room, pl: EcoPlan, i: number, c: ObsComp): string {
  const [u, v] = pl.slots[i], k = pl.ks[i], dv = v - 0.18 * k, z = zoneOf(c)
  if (z === 'jefe') return [-0.3, 0.38].map((du) => art('monitor', at(r, u + du * k, dv - 0.02 * k, 0.26 * k), 15 * k)).join('')
  if (z === 'continuo') {
    const b = at(r, u - 0.24 * k, dv, 0.27 * k)
    return [6, 9, 4].map((h, j) => `<rect x="${(b[0] + j * 3.2 * k).toFixed(1)}" y="${(b[1] - h * k).toFixed(1)}" width="${(2.2 * k).toFixed(1)}" height="${(h * k).toFixed(1)}" fill="#2ee6ff" class="iso-eq"${j % 2 ? ' style="animation-delay:-0.8s"' : ''}/>`).join('')
  }
  return ''
}

/** Todo lo que la sala pinta además de los puestos: piso (zonas, flujos, salidas) y mobiliario con profundidad. */
export function ecoDraw(r: Room, pl: EcoPlan, ctx: EcoCtx, accent: string): { floor: string; props: { svg: string; depth: number }[] } {
  return { floor: zonesFloor(r, pl, accent, ctx.detail) + innerFlows(r, pl, ctx) + exits(r, pl, ctx), props: props(r, pl) }
}
