/** Vista «Isométrico» del mapa del sistema: cada etapa es una sala de trabajo con personalidad
 * propia y cada pieza del catálogo es un puesto. Los estados son los del mapa (`stateOf`), dichos en
 * tres colores: verde = funciona, rojo = falla, gris = sin información. Las líneas salen de las
 * conexiones declaradas entre etapas y cierran el ciclo de Validación a Datos. Todas las salas se apoyan
 * sobre un mismo piso gris claro de oficina; el nombre de cada área va pintado en su franja del frente y el
 * centro es un área común con salitas (obs_iso_lounge) que no pisa las pistas. Cada sala es un microecosistema
 * (obs_iso_eco): sus puestos van por zonas según cómo entra, se trabaja y sale la información. En el mapa completo
 * solo se ven las líneas entre áreas (las de dentro de cada sala aparecen al ampliarla): quietas, con grosor por
 * importancia, flechas de sentido y un recorrido (obs_iso_route) que no pasa por debajo de salas ni tarjetas. */
import './obs_iso.css'
import { compState } from './obs_graph'
import { arrowsAlong, endArrow, lineBoxes, P, pts, S, type Room } from './obs_iso_geo'
import { ART_DEFS } from './obs_iso_art'
import { artAsImages, buildArtImages } from './obs_iso_img'
import { ecoDraw, ecoExtra, ecoPlan, hasEco, type EcoCtx, type EcoPlan } from './obs_iso_eco'
import { focusLayout, nameTags } from './obs_iso_focus'
import { FLOOR, floorName, floorSlab, G, hitsAny, hitsRoom, separate, tiles, toUV } from './obs_iso_floor'
import { lounges, type UVRect } from './obs_iso_lounge'
import { NAME_STRIP, station, STRIP, themeOf, WALL_H } from './obs_iso_props'
import { Router, type Route } from './obs_iso_route'
import { esc, STATE_ICON, STATE_LABEL, type ObsComp, type ObsData, type ObsState } from './obs_types'

export type Tone = 'ok' | 'bad' | 'none' | 'plan'
const COLOR: Record<Tone, string> = { ok: '#0fbf7a', bad: '#f0324f', none: '#8b95aa', plan: '#8b95aa' }   // legibles sobre el piso blanco
const TONE_ES: Record<Tone, string> = { ok: 'funciona', bad: 'falla', none: 'sin información', plan: 'planeado' }
/** ▲ «datos incompletos» cuenta como falla salvo que el usuario diga lo contrario. */
export const isoIncFail = (): boolean => { try { return localStorage.getItem('eim.obs.iso.inc') !== '0' } catch { return true } }
export const setIsoIncFail = (v: boolean): void => { try { localStorage.setItem('eim.obs.iso.inc', v ? '1' : '0') } catch { /* sin almacenamiento */ } }

export function toneOf(st: ObsState, incFail: boolean): Tone {
  if (st === 'planeado') return 'plan'
  if (st === 'ok') return 'ok'
  if (st === 'degradado') return incFail ? 'bad' : 'ok'
  if (st === 'error' || st === 'obsoleto') return 'bad'
  return 'none'                                // sin_datos, pausado y en_espera: no hay señal de que esté bien
}
const worstTone = (ts: Tone[]): Tone => { const t = ts.filter((x) => x !== 'plan'); return t.includes('bad') ? 'bad' : t.includes('ok') ? 'ok' : 'none' }

/** Posición (en unidades) de las siete salas, en el orden de la ruta, formando un anillo. */
const RING: [number, number][] = [[-9.4, 0.9], [-8.7, -5.9], [0.6, -6.9], [6.3, -4.7], [9.6, 0.9], [5.6, 5.8], [-3.9, 6.0]]
const posOf = (i: number, n: number): [number, number] => (n === RING.length ? RING[i]
  : [Math.cos(Math.PI + (i / n) * Math.PI * 2) * 9.4, Math.sin(Math.PI + (i / n) * Math.PI * 2) * 6.2])
interface Area extends Room { stage: string; i: number; list: ObsComp[]; slots: [number, number][]; k: number; tone: Tone; ks?: number[]; eco?: EcoPlan }
interface Link { a: string; b: string; tone: Tone; n: number; label: string; main: boolean; fb?: boolean }
const ART_ES: Record<string, string> = {
  snapshot: 'fotografía del mercado', agent_report: 'opiniones', synthesis: 'opinión conjunta', plan: 'plan', proposal: 'propuesta',
  risk_decision: 'decisión de riesgo', order: 'orden', fill: 'llenado', paper_trade: 'operaciones en papel', forecast_set: 'escenarios',
  candles: 'velas', leader_board: 'líderes', hft_events: 'eventos HFT', arb_scan: 'oportunidades', risk_log: 'registro de riesgo',
  sim_trade: 'operaciones simuladas', backtest_result: 'resultado histórico', library_card: 'fichas', bot_signal: 'señales de bots',
}

const rank: Record<ObsState, number> = { error: 0, obsoleto: 1, degradado: 2, sin_datos: 3, pausado: 4, ok: 5, en_espera: 6, planeado: 7 }

function areas(d: ObsData, inc: boolean): Area[] {
  const st = d.graph.stages
  return separate(st.map((stage, i): Area => {
    const list = d.comps.filter((c) => c.stage === stage).sort((a, b) => rank[compState(d, a)] - rank[compState(d, b)])
    const n = Math.max(list.length, 1), cols = Math.max(2, Math.ceil(Math.sqrt(n * 1.15))), rows = Math.max(2, Math.ceil(n / cols))
    const cell = n > 16 ? 0.72 : n > 6 ? 0.88 : 1.1, pad = 0.28
    const hu = Math.max((cols * cell) / 2 + pad, 1.9), hv = (rows * cell + STRIP + NAME_STRIP) / 2 + pad
    const slots: [number, number][] = []
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) slots.push([-(cols * cell) / 2 + cell * (c + 0.5), -hv + pad + STRIP + cell * (r + 0.5)])
    const [x, y] = posOf(i, st.length), tone = worstTone(list.map((c) => toneOf(compState(d, c), inc)))
    if (hasEco(stage)) {                 // microecosistema: cada puesto donde le toca según cómo sale la información
      const eco = ecoPlan(stage, list)
      return { stage, i, list, slots: eco.slots, k: eco.k, ks: eco.ks, eco, cx: x * S, cy: y * S, hu: eco.hu, hv: eco.hv, tone }
    }
    return { stage, i, list, slots, k: cell / 1.1, cx: x * S, cy: y * S, hu, hv, tone }
  }))
}

function links(d: ObsData, inc: boolean, A: Area[]): Link[] {
  const by = new Map(d.comps.map((c) => [c.id, c])), now = d.graph.asof
  const seen = (s: string, t: string): boolean => d.graph.observed.some((o) => o.source === s && o.target === t && now - o.last_ms < 3 * 3600e3)
  type Group = { a: string; b: string; tones: Tone[]; arts: Map<string, number> }
  const m = new Map<string, Group>()
  for (const e of d.graph.edges) {
    const s = by.get(e.source), t = by.get(e.target)
    if (!s || !t || s.stage === t.stage) continue
    let tone: Tone = s.built === 'planeado' || t.built === 'planeado' ? 'plan' : toneOf(compState(d, s), inc)
    if (tone === 'none' && seen(e.source, e.target)) tone = 'ok'      // la conexión se vio pasar hace poco
    const key = `${s.stage}>${t.stage}`, g: Group = m.get(key) ?? { a: s.stage, b: t.stage, tones: [], arts: new Map<string, number>() }
    g.tones.push(tone); g.arts.set(e.artifact, (g.arts.get(e.artifact) ?? 0) + 1); m.set(key, g)
  }
  const idx = (s: string): number => d.graph.stages.indexOf(s)
  const out: Link[] = [...m.values()].map((g) => {
    const top = [...g.arts].sort((x, y) => y[1] - x[1])[0][0]
    return { a: g.a, b: g.b, tone: worstTone(g.tones), n: g.tones.length, label: ART_ES[top] ?? top, main: false }
  })
  out.forEach((l) => {
    const ia = idx(l.a), ib = idx(l.b)
    l.main = ib === ia + 1 || (ib === ia + 2 && !out.some((x) => idx(x.a) === ia && idx(x.b) === ia + 1))
  })
  const st = d.graph.stages, last = A[A.length - 1]
  if (st.length > 1) out.push({ a: st[st.length - 1], b: st[0], tone: last.tone, n: 0, label: 'aprendizaje → nuevo ciclo', main: false, fb: true })
  return out
}

/** Grosor por importancia: cuantas más conexiones declaradas lleva entre las dos áreas, más gruesa; la ruta
 * principal suma un punto y el cierre del ciclo tiene grosor fijo. */
const widthOf = (l: Link): number => (l.fb ? 5 : Math.min(9, 2.6 + 1.7 * Math.log2(1 + l.n)) + (l.main ? 1 : 0))
type XY = [number, number]

/** Línea entre dos áreas sobre su recorrido: borde gris, cuerpo blanco, halo, trazo de color con el grosor de su
 * importancia, flechas de sentido más anchas que el trazo (con borde blanco, se leen sobre él) y punta al entrar.
 * Quieta: nada corre ni se repinta. Lo que falla se dice con el color. */
function drawLink(l: Link, r: Route): { svg: string; sp: XY[]; w: number } {
  const sp = r.way.map(([u, v]) => G(u, v)), dPath = `M${sp.map((q) => `${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(' L')}`
  const c = COLOR[l.tone], w = widthOf(l), cls = `iso-link t-${l.tone}${l.main || l.fb ? ' main' : ''}`
  const body = `<path d="${dPath}" stroke="#aeb8c8" stroke-width="${(w + 9).toFixed(1)}" opacity=".9"/><path d="${dPath}" stroke="#ffffff" stroke-width="${(w + 5).toFixed(1)}"/>`
    + `<path d="${dPath}" stroke="${c}" stroke-width="${(w + 12).toFixed(1)}" class="iso-halo"/><path d="${dPath}" stroke="${c}" stroke-width="${w.toFixed(1)}" class="iso-flow"/>`
    + arrowsAlong(sp, 85, w * 0.9 + 4, c, 'iso-arrow iso-larrow') + endArrow(sp, w * 1.3 + 7, c)
  const tip = l.fb ? 'Cierre del ciclo: el catálogo aún no declara una conexión directa; toma el estado de la última etapa.'
    : `${l.n} conexiones declaradas · entrega: ${l.label} · ${TONE_ES[l.tone]}`
  return { svg: `<g class="${cls}" fill="none"><title>${esc(`${l.a} → ${l.b}: ${tip}`)}</title>${body}</g>`, sp, w }
}

/** Etiqueta de lo que entrega la línea: junto a su tramo más largo, sin tapar ninguna línea, sala ni tarjeta. */
function linkLabel(l: Link, sp: XY[], free: (r: number[]) => boolean, taken: number[][]): string {
  const c = COLOR[l.tone], txt = `${l.label} ➜`, tw = txt.length * 6 + 16
  const segs = sp.slice(0, -1).map((p, i) => ({ i, len: Math.hypot(sp[i + 1][0] - p[0], sp[i + 1][1] - p[1]) })).sort((x, y) => y.len - x.len)
  const spots = segs.flatMap(({ i }) => [0.5, 0.3, 0.7].flatMap((q) => [24, -24, 36, -36, 50, -50, 70, -70, 110, -110]
    .map((o): XY => [sp[i][0] + (sp[i + 1][0] - sp[i][0]) * q, sp[i][1] + (sp[i + 1][1] - sp[i][1]) * q + o])))
  const [cx0, cy0] = spots[0], ring = Array.from({ length: 400 }, (_, n): XY => [cx0 + ((n % 20) - 10) * 24, cy0 + (Math.floor(n / 20) - 10) * 14])
    .sort((p, q) => Math.hypot(p[0] - cx0, p[1] - cy0) - Math.hypot(q[0] - cx0, q[1] - cy0))      // si no cabe junto a la línea, lo más cerca
  const [lx, ly] = [...spots, ...ring].find(([x, y]) => free([x - tw / 2, y - 11, x + tw / 2, y + 11])) ?? spots[0]
  taken.push([lx - tw / 2, ly - 11, lx + tw / 2, ly + 11])
  return `<g class="iso-flab"><rect x="${(lx - tw / 2).toFixed(1)}" y="${(ly - 10).toFixed(1)}" width="${tw}" height="19" rx="9" stroke="${c}"/><text x="${lx.toFixed(1)}" y="${(ly + 3.5).toFixed(1)}">${esc(txt)}</text></g>`
}

function drawArea(d: ObsData, a: Area, inc: boolean, stage: string | null, sel: string | null, avoid?: (r: number[]) => boolean): [string, string, number[]] {
  const th = themeOf(a.stage), { cx, cy, hu, hv } = a, c = COLOR[a.tone]
  const p = (u: number, v: number, z = 0): [number, number] => P(cx, cy, u, v, z)
  const A0 = p(-hu, -hv), B = p(hu, -hv), C = p(hu, hv), D = p(-hu, hv)
  const AH = p(-hu, -hv, WALL_H), BH = p(hu, -hv, WALL_H), DH = p(-hu, hv, WALL_H)
  const [gu, gv] = toUV(cx, cy)        // el mismo piso que el resto: solo tapa las pistas que pasan por debajo
  let s = `<polygon points="${pts([A0, B, C, D])}" fill="${FLOOR}" class="iso-floor"/><g class="iso-tiles">${tiles(gu - hu, gv - hv, gu + hu, gv + hv)}</g>`
    + floorName(a, d.graph.stage_titles_es[a.stage] ?? a.stage, th.accent)
  s += `<polygon points="${pts([A0, D, DH, AH])}" fill="${th.wallL}"/><polygon points="${pts([A0, B, BH, AH])}" fill="${th.wallR}"/>`
    + `<polyline points="${pts([DH, AH, BH])}" fill="none" stroke="${th.accent}" stroke-width="4"/>`
    + `<line x1="${A0[0]}" y1="${A0[1]}" x2="${AH[0]}" y2="${AH[1]}" stroke="#9aa3b3" opacity=".6"/>`
    + th.walls(a) + th.props(a)
  const items: { svg: string; depth: number }[] = []
  let top = ''
  if (a.eco) {                         // piso con zonas, flujos internos y salidas; mobiliario ordenado con los puestos
    const by = new Map(d.comps.map((x) => [x.id, x]))
    const ctx: EcoCtx = { list: a.list, edges: d.graph.edges, stage: a.stage, detail: a.eco.f > 1,
      tone: (id) => { const x = by.get(id); return x ? toneOf(compState(d, x), inc) : 'none' },
      stageOf: (id) => by.get(id)?.stage, title: (st) => d.graph.stage_titles_es[st] ?? st }
    const eco = ecoDraw(a, a.eco, ctx, th.accent)
    s += eco.floor; items.push(...eco.props); top = eco.top
  }
  s += `<polyline points="${pts([D, C, B])}" fill="none" stroke="${c}" stroke-width="${stage === a.stage ? 5 : 3.5}" class="iso-edge t-${a.tone}"/>`
  a.list.forEach((comp, i) => items.push({ svg: person(d, a, comp, a.slots[i], inc, th.shirt, th.accent, sel, i), depth: a.slots[i][0] + a.slots[i][1] }))
  for (const it of items.sort((x, y) => x.depth - y.depth)) s += it.svg
  s += top                             // placas de zonas y salidas (sala ampliada): encima de los puestos
  const dim = stage && stage !== a.stage ? ' iso-dim' : ''
  const room = `<g class="obs-n iso-area${dim}${stage === a.stage ? ' sel' : ''}" data-stage="${esc(a.stage)}" role="button" tabindex="0"
    aria-label="${esc(`${d.graph.stage_titles_es[a.stage]} (${th.room}): ${TONE_ES[a.tone]}`)}">${s}</g>`
  const [tag, bounds] = label(d, a, th.room, inc, dim, avoid)
  return [room, tag, bounds]
}

function person(d: ObsData, a: Area, comp: ObsComp, [u, v]: [number, number], inc: boolean, shirt: string, accent: string, sel: string | null, n: number): string {
  const st = compState(d, comp), tone = toneOf(st, inc), c = COLOR[tone], plan = tone === 'plan', k = a.ks?.[n] ?? a.k
  const f = P(a.cx, a.cy, u, v + 0.22 * k, 0.001), bz = P(a.cx, a.cy, u, v + 0.22 * k, 1.12 * k), hd = P(a.cx, a.cy, u, v + 0.22 * k, 0.86 * k)
  const floor = plan ? `<ellipse cx="${f[0]}" cy="${f[1]}" rx="${20 * k}" ry="${10 * k}" fill="none" stroke="#9aa6d6" stroke-dasharray="3 3"/>`
    : `<ellipse cx="${f[0]}" cy="${f[1]}" rx="${20 * k}" ry="${10 * k}" fill="${c}" class="${tone === 'bad' ? 'iso-pulse' : 'iso-glow'}"/>`
  const beacon = plan ? '' : `<line x1="${hd[0]}" y1="${hd[1] - 6 * k}" x2="${bz[0]}" y2="${bz[1] + 3}" stroke="${c}" opacity=".5"/><circle cx="${bz[0]}" cy="${bz[1]}" r="${3.6 * k + 0.6}" fill="${c}" class="iso-beacon"/>`
  const ring = comp.id === sel ? `<ellipse cx="${f[0]}" cy="${f[1]}" rx="${26 * k}" ry="${13 * k}" fill="none" stroke="var(--accent, #22e1ff)" stroke-width="2.5"/>` : ''
  return `<g class="obs-n iso-person${plan ? ' plan' : ''}" data-id="${esc(comp.id)}" role="button" tabindex="0" aria-label="${esc(`${comp.title_es}: ${STATE_LABEL[st]}`)}">
    <title>${esc(`${comp.title_es} — ${STATE_ICON[st]} ${STATE_LABEL[st]} (${comp.id} · ${comp.task})`)}</title>${ring}${floor}${station(a, u, v, k, comp.kind, shirt, accent, plan ? '#9aa6d6' : c, n)}${a.eco ? ecoExtra(a, a.eco, n, comp) : ''}${beacon}</g>`
}

function label(d: ObsData, a: Area, room: string, inc: boolean, dim: string, avoid?: (r: number[]) => boolean): [string, number[]] {
  const cnt: Partial<Record<ObsState, number>> = {}
  a.list.forEach((c) => { const s = compState(d, c); cnt[s] = (cnt[s] ?? 0) + 1 })
  const order: ObsState[] = ['ok', 'degradado', 'obsoleto', 'error', 'sin_datos', 'pausado', 'en_espera', 'planeado']
  const icons = order.filter((s) => cnt[s]).map((s) => `<tspan fill="${s === 'planeado' ? '#9aa6d6' : COLOR[toneOf(s, inc)]}">${STATE_ICON[s]}${cnt[s]}</tspan>`).join('  ')
  const plain = order.filter((s) => cnt[s]).map((s) => `${STATE_ICON[s]}${cnt[s]}`).join('  ')
  const name = `${a.i + 1}  ${d.graph.stage_titles_es[a.stage] ?? a.stage}`, c = COLOR[a.tone]
  const w = Math.max(name.length * 7.6, room.length * 6.3, plain.length * 6.6) + 34, { cx, cy, hu, hv } = a
  let x: number, y: number, stem = ''
  const [, sy] = posOf(a.i, d.graph.stages.length)
  // Arriba si la sala está en la fila de arriba o es una sala ampliada con microecosistema (así no choca con sus salidas).
  if (sy < -1 || (a.eco?.f ?? 1) > 1) { const tp = P(cx, cy, -hu, -hv, WALL_H); x = tp[0]; y = tp[1] - 52; stem = `<line x1="${x}" y1="${y + 30}" x2="${tp[0]}" y2="${tp[1] - 3}" stroke="${c}" stroke-dasharray="2 3" opacity=".6"/>` }
  else if (sy > 1) { const f = P(cx, cy, hu, hv, -0.38); x = cx; y = f[1] + 34 }
  else if (cx < 0) { const f = P(cx, cy, -hu, hv, -0.38); x = f[0] + 40 - w / 2; y = f[1] + 50 }
  else { const f = P(cx, cy, hu, -hv, -0.38); x = f[0] - 40 + w / 2; y = f[1] + 50 }
  if (avoid?.([x - w / 2, y - 24, x + w / 2, y + 32])) {          // ocupado: prueba los cuatro costados de la sala
    const tp = P(cx, cy, -hu, -hv, WALL_H), bt = P(cx, cy, hu, hv, -0.38), lf = P(cx, cy, -hu, hv, -0.38), rt = P(cx, cy, hu, -hv, -0.38)
    const c2 = ([[tp[0], tp[1] - 52], [bt[0], bt[1] + 34], [lf[0] - w / 2 - 10, lf[1]], [rt[0] + w / 2 + 10, rt[1]], [tp[0], tp[1] - 110], [bt[0], bt[1] + 92]] as [number, number][])
      .find(([px, py]) => !avoid([px - w / 2, py - 24, px + w / 2, py + 32]))
    if (c2) { [x, y] = c2; stem = '' }
  }
  return [`<g class="obs-n iso-label${dim}" data-stage="${esc(a.stage)}">${stem}<rect x="${(x - w / 2).toFixed(1)}" y="${(y - 22).toFixed(1)}" width="${w.toFixed(1)}" height="52" rx="10" stroke="${c}"/>
    <circle cx="${(x - w / 2 + 14).toFixed(1)}" cy="${(y - 8).toFixed(1)}" r="4.5" fill="${c}"/>
    <text class="iso-l1" x="${(x - w / 2 + 26).toFixed(1)}" y="${(y - 4).toFixed(1)}">${esc(name)}</text>
    <text class="iso-l2" x="${(x - w / 2 + 26).toFixed(1)}" y="${(y + 9).toFixed(1)}">${esc(room)}</text>
    <text class="iso-l3" x="${(x - w / 2 + 26).toFixed(1)}" y="${(y + 22).toFixed(1)}">${icons}</text></g>`, [x - w / 2, y - 24, x + w / 2, y + 32]]
}

/** Clave de repintado: si nada visible cambió no se rehace el SVG (las animaciones no saltan). */
export function isoKey(d: ObsData, stage: string | null, sel: string | null): string {
  return [isoIncFail(), stage, sel, d.graph.stages.join(','), d.comps.map((c) => `${c.id}:${compState(d, c)}`).join('|'),
    d.graph.observed.map((o) => `${o.source}>${o.target}`).join('|')].join('#')
}

/** Prepara una vez los objetos del mapa como imágenes reutilizables (obs_iso_img); si no se puede, quedan
 * como <symbol> en la página y cada redibujo los usa con <use>. */
export function ensureIsoDefs(): void {
  if (typeof document === 'undefined' || document.getElementById('iso-shared-defs')) return
  const defs = ART_DEFS, box = document.createElement('div')
  buildArtImages(defs)
  box.innerHTML = `<svg id="iso-shared-defs" aria-hidden="true" focusable="false" width="0" height="0"
    style="position:absolute;width:0;height:0;overflow:hidden"><defs>${artAsImages() ? '' : defs}</defs></svg>`
  document.body.appendChild(box.firstElementChild!)
}

const legendBar = (inc: boolean): string => `<div class="iso-legend"><span><i class="t-ok"></i>Funciona</span><span><i class="t-bad"></i>Falla (✖ error · ◷ dato viejo${inc ? ' · ▲ incompleto' : ''})</span>
      <span><i class="t-none"></i>Sin información (? sin datos · ❚❚ pausa · ◌ en espera)</span><span class="muted">Puesto translúcido = planeado · Línea más gruesa = más conexiones entre áreas</span>
      <label><input type="checkbox" data-act="iso-inc"${inc ? ' checked' : ''}> ▲ cuenta como falla</label></div>`

/** Sala con microecosistema, ampliada: las mismas zonas, más separadas para que quepan los nombres. */
function ecoFocus(a: Area): Area {
  const eco = ecoPlan(a.stage, a.list, true)
  return { ...a, eco, slots: eco.slots, ks: eco.ks, k: eco.k, hu: eco.hu, hv: eco.hv }
}

/** Sala enfocada: solo esa área, ampliada y centrada en todo el espacio del mapa; el resto se oculta
 * hasta pulsar «← Ruta completa». */
function focusHtml(d: ObsData, a0: Area, inc: boolean, sel: string | null): string {
  const a = a0.eco ? ecoFocus(a0) : focusLayout(a0), [room, tag, b] = drawArea(d, a, inc, a.stage, sel), [floor] = floorSlab([a]), e = (a.hu + a.hv) * S
  const names = nameTags(a, a.list.map((c, i) => { const st = compState(d, c), t = toneOf(st, inc)
    const z = a.eco?.zones[i], side = !z ? undefined : z === 'left' ? 'r' as const : 'l' as const
    return { id: c.id, name: c.title_es, color: t === 'plan' ? '#9aa6d6' : COLOR[t], side, tip: `${c.title_es} — ${STATE_ICON[st]} ${STATE_LABEL[st]} · pulsa para ver su información` } }), sel)
  const mx = a.eco ? 200 : 60                  // las placas de salida quedan fuera de la sala, a los lados
  const x0 = Math.min(b[0], a.cx - e * 0.866) - mx, x1 = Math.max(b[2], a.cx + e * 0.866) + mx
  const y0 = Math.min(b[1], a.cy - e * 0.5 - WALL_H * S) - 28, y1 = Math.max(b[3], a.cy + e * 0.5 + 0.4 * S) + 28
  return `<div class="iso-wrap iso-focus"><button class="iso-back" data-home title="Volver al mapa con todas las áreas">← Ruta completa</button>
    <svg class="iso-svg" viewBox="${x0.toFixed(0)} ${y0.toFixed(0)} ${(x1 - x0).toFixed(0)} ${(y1 - y0).toFixed(0)}" role="img" aria-label="${esc(`Área ${d.graph.stage_titles_es[a.stage] ?? a.stage} ampliada`)}">
      ${floor}<g>${room}</g><g class="iso-tags">${names}</g><g>${tag}</g></svg>${legendBar(inc)}</div>`
}

/** El mapa completo como HTML (SVG + leyenda con el ajuste de «datos incompletos»); con una etapa elegida, solo esa sala. */
export function isoHtml(d: ObsData, stage: string | null, sel: string | null): string {
  ensureIsoDefs()
  const inc = isoIncFail(), A = areas(d, inc), focus = stage ? A.find((a) => a.stage === stage) : undefined
  if (focus) return focusHtml(d, focus, inc, sel)
  const L = links(d, inc, A), uvs = A.map((a) => toUV(a.cx, a.cy)), at = new Map(A.map((a, i) => [a.stage, i]))
  const router = new Router(A.map((a, i) => ({ u: uvs[i][0], v: uvs[i][1], hu: a.hu, hv: a.hv })))
  const prio = (l: Link): number => (l.main || l.fb ? 1000 : 0) + l.n           // las importantes eligen pasillo primero
  const labs: string[] = [], taken: number[][] = [], tracks: UVRect[] = [], wayUV: [number, number][] = []
  const drawn = [...L].sort((x, y) => prio(y) - prio(x)).map((l) => {
    const r = router.route(at.get(l.a)!, at.get(l.b)!)
    for (let q = 0; q + 1 < r.way.length; q++) {             // tramos ocupados: el área común no los pisa
      const [p1, p2] = [r.way[q], r.way[q + 1]], m = 0.42
      tracks.push([Math.min(p1[0], p2[0]) - m, Math.min(p1[1], p2[1]) - m, Math.max(p1[0], p2[0]) + m, Math.max(p1[1], p2[1]) + m])
    }
    wayUV.push(...r.way)
    return { l, r, ...drawLink(l, r) }
  })
  const onLines = drawn.flatMap((x) => lineBoxes(x.sp, x.w))
  const free = (r: number[]): boolean => !hitsAny(taken, r) && !hitsAny(onLines, r) && !hitsRoom(A, r, WALL_H)
  drawn.filter((x) => x.l.main || x.l.fb).forEach((x) => labs.push(linkLabel(x.l, x.sp, free, taken)))
  // Las importantes van encima de las demás; las que no hallaron pasillo libre, encima de las salas.
  const under = drawn.filter((x) => !x.r.blocked).reverse().map((x) => x.svg), over = drawn.filter((x) => x.r.blocked).reverse().map((x) => x.svg)
  // El piso abarca también los recorridos que rodean las salas por fuera.
  const wu = wayUV.map((q) => q[0]), wv = wayUV.map((q) => q[1]), [gu0, gv0, gu1, gv1] = [Math.min(...wu), Math.min(...wv), Math.max(...wu), Math.max(...wv)]
  const [gx, gy] = G((gu0 + gu1) / 2, (gv0 + gv1) / 2), span: Room = { cx: gx, cy: gy, hu: (gu1 - gu0) / 2, hv: (gv1 - gv0) / 2 }
  const [floor] = floorSlab(wayUV.length ? [...A, span] : A)        // el piso sigue más allá del encuadre: se enfoca en las salas
  const items: { svg: string; depth: number }[] = [], tags: string[] = [], boxes: number[][] = [], xs: number[] = [], ys: number[] = []
  A.forEach((a) => {
    const avoid = (r: number[]): boolean => hitsAny([...boxes, ...taken, ...onLines], r) || hitsRoom(A, r, WALL_H)    // tarjeta en sitio libre, sin tapar líneas
    const [r, t, b] = drawArea(d, a, inc, stage, sel, avoid); items.push({ svg: r, depth: a.cy }); tags.push(t); boxes.push(b)
    xs.push(b[0], b[2], a.cx - (a.hu + a.hv) * 0.866 * S, a.cx + (a.hu + a.hv) * 0.866 * S)
    ys.push(b[1], b[3], a.cy - (a.hu + a.hv) * 0.5 * S - WALL_H * S, a.cy + (a.hu + a.hv) * 0.5 * S + 0.4 * S)
  })
  const roomUV = A.map((a, i): UVRect => [uvs[i][0] - a.hu, uvs[i][1] - a.hv, uvs[i][0] + a.hu, uvs[i][1] + a.hv])
  const zone: UVRect = [Math.min(...uvs.map((q) => q[0])), Math.min(...uvs.map((q) => q[1])), Math.max(...uvs.map((q) => q[0])), Math.max(...uvs.map((q) => q[1]))]
  items.push(...lounges(zone, roomUV, tracks, [...boxes, ...taken, ...onLines]))   // área común en los huecos, sin tapar líneas
  const rooms = items.sort((x, y) => x.depth - y.depth).map((x) => x.svg)
  for (const q of wayUV) { const [x, y] = G(q[0], q[1]); xs.push(x - 14, x + 14); ys.push(y - 14, y + 14) }   // las líneas caben en el encuadre
  const pad = 16; xs.push(Math.min(...xs) - pad, Math.max(...xs) + pad); ys.push(Math.min(...ys) - pad, Math.max(...ys) + pad)
  const x0 = Math.min(...xs), y0 = Math.min(...ys), vw = Math.max(...xs) - x0, vh = Math.max(...ys) - y0
  // Dos capas con el mismo encuadre (piso con las líneas quietas · salas): las líneas ya no se mueven, así
  // que solo la capa de las salas tiene parpadeos (a saltos, con el reloj compartido).
  const vb = `viewBox="${x0.toFixed(0)} ${y0.toFixed(0)} ${vw.toFixed(0)} ${vh.toFixed(0)}"`
  return `<div class="iso-wrap"><div class="iso-stage">
    <svg class="iso-svg iso-base" ${vb} aria-hidden="true">${floor}<g class="iso-lines">${under.join('')}</g></svg>
    <svg class="iso-svg iso-layer iso-top" ${vb} role="img" aria-label="Mapa isométrico: ${d.graph.stages.length} etapas como salas de trabajo">
      <g>${rooms.join('')}</g><g class="iso-lines">${over.join('')}</g><g>${tags.join('')}</g><g class="iso-flabs">${labs.join('')}</g></svg></div>
    ${legendBar(inc)}</div>`
}
