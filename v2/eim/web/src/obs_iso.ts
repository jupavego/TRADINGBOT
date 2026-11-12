/** Vista «Isométrico» del mapa del sistema: cada etapa es una sala de trabajo con personalidad
 * propia y cada pieza del catálogo es un puesto. Los estados son los del mapa (`stateOf`), dichos en
 * tres colores: verde = funciona, rojo = falla, gris = sin información. Las líneas salen de las
 * conexiones declaradas entre etapas y cierran el ciclo de Validación a Datos. */
import './obs_iso.css'
import { compState } from './obs_graph'
import { P, pts, S, type Room } from './obs_iso_geo'
import { station, STRIP, themeOf, WALL_H } from './obs_iso_props'
import { esc, STATE_ICON, STATE_LABEL, type ObsComp, type ObsData, type ObsState } from './obs_types'

export type Tone = 'ok' | 'bad' | 'none' | 'plan'
const COLOR: Record<Tone, string> = { ok: '#12e58f', bad: '#ff3d5f', none: '#7d8aa6', plan: '#7d8aa6' }
const TONE_ES: Record<Tone, string> = { ok: 'funciona', bad: 'falla', none: 'sin información', plan: 'planeado' }

/** ▲ «datos incompletos» cuenta como falla salvo que el usuario diga lo contrario. */
export const isoIncFail = (): boolean => { try { return localStorage.getItem('eim.obs.iso.inc') !== '0' } catch { return true } }
export const setIsoIncFail = (v: boolean): void => { try { localStorage.setItem('eim.obs.iso.inc', v ? '1' : '0') } catch { /* sin almacenamiento */ } }

export function toneOf(st: ObsState, incFail: boolean): Tone {
  if (st === 'planeado') return 'plan'
  if (st === 'ok') return 'ok'
  if (st === 'degradado') return incFail ? 'bad' : 'ok'
  if (st === 'error' || st === 'obsoleto') return 'bad'
  return 'none'                                // sin_datos y pausado: no hay señal de que esté bien
}
const worstTone = (ts: Tone[]): Tone => { const t = ts.filter((x) => x !== 'plan'); return t.includes('bad') ? 'bad' : t.includes('ok') ? 'ok' : 'none' }

/** Posición (en unidades) de las siete salas, en el orden de la ruta, formando un anillo. */
const RING: [number, number][] = [[-9.4, 0.9], [-7.4, -5.6], [0.6, -6.9], [5.6, -5.0], [9.6, 0.6], [5.6, 5.8], [-3.9, 6.0]]
const posOf = (i: number, n: number): [number, number] => (n === RING.length ? RING[i]
  : [Math.cos(Math.PI + (i / n) * Math.PI * 2) * 9.4, Math.sin(Math.PI + (i / n) * Math.PI * 2) * 6.2])

interface Area extends Room { stage: string; i: number; list: ObsComp[]; slots: [number, number][]; k: number; tone: Tone }
interface Link { a: string; b: string; tone: Tone; n: number; label: string; main: boolean; fb?: boolean }

const ART_ES: Record<string, string> = {
  snapshot: 'fotografía del mercado', agent_report: 'opiniones', synthesis: 'opinión conjunta', plan: 'plan', proposal: 'propuesta',
  risk_decision: 'decisión de riesgo', order: 'orden', fill: 'llenado', paper_trade: 'operaciones en papel', forecast_set: 'escenarios',
  candles: 'velas', leader_board: 'líderes', hft_events: 'eventos HFT', arb_scan: 'oportunidades', risk_log: 'registro de riesgo',
  sim_trade: 'operaciones simuladas', backtest_result: 'resultado histórico', library_card: 'fichas', bot_signal: 'señales de bots',
}

const rank: Record<ObsState, number> = { error: 0, obsoleto: 1, degradado: 2, sin_datos: 3, pausado: 4, ok: 5, planeado: 6 }

function areas(d: ObsData, inc: boolean): Area[] {
  const st = d.graph.stages
  return st.map((stage, i) => {
    const list = d.comps.filter((c) => c.stage === stage).sort((a, b) => rank[compState(d, a)] - rank[compState(d, b)])
    const n = Math.max(list.length, 1), cols = Math.max(2, Math.ceil(Math.sqrt(n * 1.15))), rows = Math.max(2, Math.ceil(n / cols))
    const cell = n > 16 ? 0.72 : n > 6 ? 0.88 : 1.1, pad = 0.28
    const hu = (cols * cell) / 2 + pad, hv = (rows * cell + STRIP) / 2 + pad
    const slots: [number, number][] = []
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) slots.push([-hu + pad + cell * (c + 0.5), -hv + pad + STRIP + cell * (r + 0.5)])
    const [x, y] = posOf(i, st.length)
    return { stage, i, list, slots, k: cell / 1.1, cx: x * S, cy: y * S, hu, hv, tone: worstTone(list.map((c) => toneOf(compState(d, c), inc))) }
  })
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

/** Coordenadas del piso común: la vista entera comparte un solo plano (U, V) en unidades. */
const toUV = (x: number, y: number): [number, number] => [(x / (0.866 * S) + y / (0.5 * S)) / 2, (y / (0.5 * S) - x / (0.866 * S)) / 2]
const G = (u: number, v: number, z = 0): [number, number] => P(0, 0, u, v, z)
const sgn = (x: number): number => (x >= 0 ? 1 : -1)

/** Pista sobre el piso entre dos salas: sale por el borde de la de origen, gira en ángulo recto
 * siguiendo los ejes del piso y entra por el borde de la de destino, con flechas de sentido. */
function drawLink(l: Link, A: Area[], i: number, focus: string | null, motion: boolean, mid: [number, number], taken: number[][]): [string, string] {
  const a = A.find((x) => x.stage === l.a)!, b = A.find((x) => x.stage === l.b)!
  const [ua, va] = toUV(a.cx, a.cy), [ub, vb] = toUV(b.cx, b.cy)
  const o = l.main || l.fb ? 0 : ((i % 3) - 1) * 0.32                       // carriles para no pisarse
  const far = (u: number, v: number): number => Math.hypot(u - mid[0], v - mid[1])
  const uFirst = (far(ub, va) >= far(ua, vb)) === (l.main || !!l.fb)          // las principales rodean; las demás cruzan
  const su = sgn(ub - ua), sv = sgn(vb - va)
  const way: [number, number][] = uFirst
    ? [[ua + su * (a.hu + 0.15), va + o], [ub + o, va + o], [ub + o, vb - sv * (b.hv + 0.3)]]
    : [[ua + o, va + sv * (a.hv + 0.15)], [ua + o, vb + o], [ub - su * (b.hu + 0.3), vb + o]]
  const sp = way.map(([u, v]) => G(u, v))
  const dPath = `M${sp.map((q) => `${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(' L')}`, id = `iso-l${i}`, c = COLOR[l.tone]
  const on = !focus || l.a === focus || l.b === focus, w = l.fb ? 6 : l.main ? 5 : 2.6
  const cls = `iso-link t-${l.tone}${l.main || l.fb ? ' main' : ''}${on ? '' : ' iso-dim'}${!l.main && !l.fb && focus && on ? ' focus' : ''}`
  let parts = `<path d="${dPath}" stroke="#020414" stroke-width="${w + 8}" opacity=".7"/><path d="${dPath}" stroke="${c}" stroke-width="${w + 12}" class="iso-halo"/>`
    + `<path id="${id}" d="${dPath}" stroke="${c}" stroke-width="${w * 0.55}" opacity=".45"/>`
    + `<path d="${dPath}" stroke="${c}" stroke-width="${w}" class="iso-flow" marker-end="url(#iso-ah-${l.tone})"/>`
  if (motion && l.tone !== 'none' && l.tone !== 'plan') {
    const n = l.fb ? 6 : l.main ? 4 : 2, dur = l.tone === 'bad' ? 8 : 4, k = l.main || l.fb ? 1.25 : 0.85
    for (let q = 0; q < n; q++) parts += `<path d="M${-7 * k},${-5 * k} L${5 * k},0 L${-7 * k},${5 * k} L${-3.5 * k},0 Z" fill="${c}" class="iso-dotm">`
      + `<animateMotion dur="${dur}s" repeatCount="indefinite" rotate="auto" begin="${(-q * dur / n).toFixed(2)}s"><mpath href="#${id}"/></animateMotion></path>`
  }
  const tip = l.fb ? 'Cierre del ciclo: el catálogo aún no declara una conexión directa; toma el estado de la última etapa.'
    : `${l.n} conexiones declaradas · entrega: ${l.label} · ${TONE_ES[l.tone]}`
  const g = `<g class="${cls}" fill="none"><title>${esc(`${l.a} → ${l.b}: ${tip}`)}</title>${parts}</g>`
  let lab = ''
  if (l.main || l.fb || (focus && on)) {
    const seg = Math.hypot(sp[1][0] - sp[0][0], sp[1][1] - sp[0][1]) >= Math.hypot(sp[2][0] - sp[1][0], sp[2][1] - sp[1][1]) ? 0 : 1
    const lx = (sp[seg][0] + sp[seg + 1][0]) / 2, txt = `${l.label} ➜`, tw = txt.length * 6 + 16
    let ly = (sp[seg][1] + sp[seg + 1][1]) / 2
    const hit = (y: number): boolean => taken.some((r) => lx - tw / 2 < r[2] && lx + tw / 2 > r[0] && y - 11 < r[3] && y + 11 > r[1])
    for (let k = 0; k < 6 && hit(ly); k++) ly += 22           // etiquetas que chocan se apartan hacia abajo
    taken.push([lx - tw / 2, ly - 11, lx + tw / 2, ly + 11])
    lab = `<g class="iso-flab${on ? '' : ' iso-dim'}"><rect x="${(lx - tw / 2).toFixed(1)}" y="${(ly - 10).toFixed(1)}" width="${tw}" height="19" rx="9" stroke="${c}"/><text x="${lx.toFixed(1)}" y="${(ly + 3.5).toFixed(1)}">${esc(txt)}</text></g>`
  }
  return [g, lab]
}

/** Piso común bajo todas las salas: una sola losa con baldosas, en vez de islas separadas. */
function floorSlab(A: Area[]): [string, number[]] {
  const uv = A.flatMap((a) => { const [u, v] = toUV(a.cx, a.cy); return [[u - a.hu, v - a.hv], [u + a.hu, v + a.hv]] })
  const m = 1.4, u0 = Math.floor(Math.min(...uv.map((q) => q[0])) - m), u1 = Math.ceil(Math.max(...uv.map((q) => q[0])) + m)
  const v0 = Math.floor(Math.min(...uv.map((q) => q[1])) - m), v1 = Math.ceil(Math.max(...uv.map((q) => q[1])) + m), t = 0.5
  const [a0, b, c, d] = [G(u0, v0), G(u1, v0), G(u1, v1), G(u0, v1)], [b0, c0, d0] = [G(u1, v0, -t), G(u1, v1, -t), G(u0, v1, -t)]
  let s = `<polygon points="${pts([d, c, c0, d0])}" fill="#0b1650"/><polygon points="${pts([c, b, b0, c0])}" fill="#081040"/>`
    + `<polygon points="${pts([a0, b, c, d])}" fill="#0d1a55" class="iso-ground"/>`
  for (let u = u0 + 1; u < u1; u++) { const p1 = G(u, v0), p2 = G(u, v1); s += `<line x1="${p1[0]}" y1="${p1[1]}" x2="${p2[0]}" y2="${p2[1]}"/>` }
  for (let v = v0 + 1; v < v1; v++) { const p1 = G(u0, v), p2 = G(u1, v); s += `<line x1="${p1[0]}" y1="${p1[1]}" x2="${p2[0]}" y2="${p2[1]}"/>` }
  s += `<polyline points="${pts([d0, c0, b0])}" fill="none" stroke="#22e1ff" stroke-width="2" opacity=".55"/><polyline points="${pts([d, a0, b])}" fill="none" stroke="#22e1ff" stroke-width="1" opacity=".35"/>`
  const xs = [a0, b, c, d, b0, c0, d0].map((q) => q[0]), ys = [a0, b, c, d, b0, c0, d0].map((q) => q[1])
  return [`<g class="iso-tiles">${s}</g>`, [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]]
}

function drawArea(d: ObsData, a: Area, inc: boolean, stage: string | null, sel: string | null): [string, string, number[]] {
  const th = themeOf(a.stage), { cx, cy, hu, hv } = a, c = COLOR[a.tone]
  const p = (u: number, v: number, z = 0): [number, number] => P(cx, cy, u, v, z)
  const A0 = p(-hu, -hv), B = p(hu, -hv), C = p(hu, hv), D = p(-hu, hv)
  const AH = p(-hu, -hv, WALL_H), BH = p(hu, -hv, WALL_H), DH = p(-hu, hv, WALL_H)
  let s = `<polygon points="${pts([A0, B, C, D])}" fill="${c}" class="iso-glow"/><polygon points="${pts([A0, B, C, D])}" fill="${th.floor}" class="iso-floor"/>`
  for (let q = 1; q < 6; q++) {
    const f = q / 6, a1 = p(-hu + 2 * hu * f, -hv), a2 = p(-hu + 2 * hu * f, hv), b1 = p(-hu, -hv + 2 * hv * f), b2 = p(hu, -hv + 2 * hv * f)
    s += `<line x1="${a1[0]}" y1="${a1[1]}" x2="${a2[0]}" y2="${a2[1]}" stroke="${th.grid}" opacity=".12"/><line x1="${b1[0]}" y1="${b1[1]}" x2="${b2[0]}" y2="${b2[1]}" stroke="${th.grid}" opacity=".12"/>`
  }
  s += `<polygon points="${pts([A0, D, DH, AH])}" fill="${th.wallL}"/><polygon points="${pts([A0, B, BH, AH])}" fill="${th.wallR}"/>`
    + `<polyline points="${pts([DH, AH, BH])}" fill="none" stroke="${th.accent}" stroke-width="2" opacity=".8"/>`
    + `<line x1="${A0[0]}" y1="${A0[1]}" x2="${AH[0]}" y2="${AH[1]}" stroke="#000" opacity=".25"/>`
    + th.walls(a) + th.props(a)
  s += `<polyline points="${pts([D, C, B])}" fill="none" stroke="${c}" stroke-width="${stage === a.stage ? 5 : 3.5}" class="iso-edge t-${a.tone}"/>`
  const items = a.list.map((comp, i) => ({ comp, i, depth: a.slots[i][0] + a.slots[i][1] })).sort((x, y) => x.depth - y.depth)
  for (const { comp, i } of items) s += person(d, a, comp, a.slots[i], inc, th.shirt, th.accent, sel)
  const dim = stage && stage !== a.stage ? ' iso-dim' : ''
  const room = `<g class="obs-n iso-area${dim}${stage === a.stage ? ' sel' : ''}" data-stage="${esc(a.stage)}" role="button" tabindex="0"
    aria-label="${esc(`${d.graph.stage_titles_es[a.stage]} (${th.room}): ${TONE_ES[a.tone]}`)}">${s}</g>`
  const [tag, bounds] = label(d, a, th.room, inc, dim)
  return [room, tag, bounds]
}

function person(d: ObsData, a: Area, comp: ObsComp, [u, v]: [number, number], inc: boolean, shirt: string, accent: string, sel: string | null): string {
  const st = compState(d, comp), tone = toneOf(st, inc), c = COLOR[tone], plan = tone === 'plan', k = a.k
  const f = P(a.cx, a.cy, u, v + 0.22 * k, 0.001), bz = P(a.cx, a.cy, u, v + 0.22 * k, 1.0 * k), hd = P(a.cx, a.cy, u, v + 0.22 * k, 0.66 * k)
  const floor = plan ? `<ellipse cx="${f[0]}" cy="${f[1]}" rx="${20 * k}" ry="${10 * k}" fill="none" stroke="#9aa6d6" stroke-dasharray="3 3"/>`
    : `<ellipse cx="${f[0]}" cy="${f[1]}" rx="${20 * k}" ry="${10 * k}" fill="${c}" class="iso-pulse"/>`
  const beacon = plan ? '' : `<line x1="${hd[0]}" y1="${hd[1] - 6 * k}" x2="${bz[0]}" y2="${bz[1] + 3}" stroke="${c}" opacity=".5"/><circle cx="${bz[0]}" cy="${bz[1]}" r="${3.6 * k + 0.6}" fill="${c}" class="iso-beacon"/>`
  const ring = comp.id === sel ? `<ellipse cx="${f[0]}" cy="${f[1]}" rx="${26 * k}" ry="${13 * k}" fill="none" stroke="var(--accent, #22e1ff)" stroke-width="2.5"/>` : ''
  return `<g class="obs-n iso-person${plan ? ' plan' : ''}" data-id="${esc(comp.id)}" role="button" tabindex="0" aria-label="${esc(`${comp.title_es}: ${STATE_LABEL[st]}`)}">
    <title>${esc(`${comp.title_es} — ${STATE_ICON[st]} ${STATE_LABEL[st]} (${comp.id} · ${comp.task})`)}</title>${ring}${floor}${station(a, u, v, k, comp.kind, shirt, accent, plan ? '#9aa6d6' : c)}${beacon}</g>`
}

function label(d: ObsData, a: Area, room: string, inc: boolean, dim: string): [string, number[]] {
  const cnt: Partial<Record<ObsState, number>> = {}
  a.list.forEach((c) => { const s = compState(d, c); cnt[s] = (cnt[s] ?? 0) + 1 })
  const order: ObsState[] = ['ok', 'degradado', 'obsoleto', 'error', 'sin_datos', 'pausado', 'planeado']
  const icons = order.filter((s) => cnt[s]).map((s) => `<tspan fill="${s === 'planeado' ? '#9aa6d6' : COLOR[toneOf(s, inc)]}">${STATE_ICON[s]}${cnt[s]}</tspan>`).join('  ')
  const plain = order.filter((s) => cnt[s]).map((s) => `${STATE_ICON[s]}${cnt[s]}`).join('  ')
  const name = `${a.i + 1}  ${d.graph.stage_titles_es[a.stage] ?? a.stage}`, c = COLOR[a.tone]
  const w = Math.max(name.length * 7.6, room.length * 6.3, plain.length * 6.6) + 34, { cx, cy, hu, hv } = a
  let x: number, y: number, stem = ''
  const [, sy] = posOf(a.i, d.graph.stages.length)
  if (sy < -1) { const tp = P(cx, cy, -hu, -hv, WALL_H); x = tp[0]; y = tp[1] - 52; stem = `<line x1="${x}" y1="${y + 30}" x2="${tp[0]}" y2="${tp[1] - 3}" stroke="${c}" stroke-dasharray="2 3" opacity=".6"/>` }
  else if (sy > 1) { const f = P(cx, cy, hu, hv, -0.38); x = cx; y = f[1] + 34 }
  else if (cx < 0) { const f = P(cx, cy, -hu, hv, -0.38); x = f[0] + 40 - w / 2; y = f[1] + 50 }
  else { const f = P(cx, cy, hu, -hv, -0.38); x = f[0] - 40 + w / 2; y = f[1] + 50 }
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

/** El mapa completo como HTML (SVG + leyenda con el ajuste de «datos incompletos»). */
export function isoHtml(d: ObsData, stage: string | null, sel: string | null): string {
  const inc = isoIncFail(), A = areas(d, inc), L = links(d, inc, A)
  const motion = !(typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  const lines: string[] = [], labs: string[] = [], taken: number[][] = [], uvs = A.map((a) => toUV(a.cx, a.cy))
  const mid: [number, number] = [uvs.reduce((t, q) => t + q[0], 0) / uvs.length, uvs.reduce((t, q) => t + q[1], 0) / uvs.length]
  L.map((l, i) => ({ l, i })).sort((x, y) => Number(x.l.main || !!x.l.fb) - Number(y.l.main || !!y.l.fb))
    .forEach(({ l, i }) => { const [g, lab] = drawLink(l, A, i, stage, motion, mid, taken); lines.push(g); labs.push(lab) })
  const [floor] = floorSlab(A)        // el piso sigue más allá del encuadre: se enfoca en las salas
  const marks = (Object.keys(COLOR) as Tone[]).map((t) => `<marker id="iso-ah-${t}" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="${COLOR[t]}"/></marker>`).join('')
  const rooms: string[] = [], tags: string[] = [], xs: number[] = [], ys: number[] = []
  A.slice().sort((x, y) => x.cy - y.cy).forEach((a) => {
    const [r, t, b] = drawArea(d, a, inc, stage, sel); rooms.push(r); tags.push(t)
    xs.push(b[0], b[2], a.cx - (a.hu + a.hv) * 0.866 * S, a.cx + (a.hu + a.hv) * 0.866 * S)
    ys.push(b[1], b[3], a.cy - (a.hu + a.hv) * 0.5 * S - WALL_H * S, a.cy + (a.hu + a.hv) * 0.5 * S + 0.4 * S)
  })
  const pad = 16; xs.push(Math.min(...xs) - pad, Math.max(...xs) + pad); ys.push(Math.min(...ys) - pad, Math.max(...ys) + pad)
  const x0 = Math.min(...xs), y0 = Math.min(...ys), vw = Math.max(...xs) - x0, vh = Math.max(...ys) - y0
  return `<div class="iso-wrap">
    <svg class="iso-svg" viewBox="${x0.toFixed(0)} ${y0.toFixed(0)} ${vw.toFixed(0)} ${vh.toFixed(0)}" role="img" aria-label="Mapa isométrico: ${d.graph.stages.length} etapas como salas de trabajo">
      <defs>${marks}</defs>${floor}<g class="iso-lines">${lines.join('')}</g><g>${rooms.join('')}</g><g>${tags.join('')}</g><g class="iso-flabs">${labs.join('')}</g></svg>
    <div class="iso-legend"><span><i class="t-ok"></i>Funciona</span><span><i class="t-bad"></i>Falla (✖ error · ◷ dato viejo${inc ? ' · ▲ incompleto' : ''})</span>
      <span><i class="t-none"></i>Sin información (? sin datos · ❚❚ pausa)</span><span class="muted">Puesto translúcido = planeado</span>
      <label><input type="checkbox" data-act="iso-inc"${inc ? ' checked' : ''}> ▲ cuenta como falla</label></div></div>`
}
