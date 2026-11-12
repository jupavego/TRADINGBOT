import { collectorLabel, degradedLabel, noDataLabel } from './no_data_label'
import { orb } from './agent_orbs'
import { type Filter, matches, votes } from './agent_roles'
import type { ArbPayload } from './arb_types'
import { agentName, esc } from './panels'
import { core, hexPath, holoDefs } from './river_holo'
import { ARB_ID, arbSatellite, arbTip, SAT_R, setArbData } from './river_arb'
import { animateOrbit, holdOrbit, ORBIT_EXTENT, orbitPaths, orbitPos, orbitTransform } from './river_orbit'
import { animateSphere } from './river_sphere'
import { agentTip, CORE_ID, coreTip, sg, THRESH, tint, votesLine } from './river_tips'
import { PCT_NOTE, upDown } from './synth'
import { rememberOpenFamilies } from './technical_ui'
import type { AgentInfo, AgentReport, Synthesis } from './types'

const W = 1200, CX = W / 2, NR = 21, R = 104

let selected: string | null = null // agente con tooltip abierto
// Sin pestañas de filtro en el río: siempre se ven todos los agentes.
let filter: Filter = 'todos'
let ctx: { infos: AgentInfo[]; reports: AgentReport[]; synthesis: Synthesis | null; tf: string } = { infos: [], reports: [], synthesis: null, tf: '' }
let keyBound = false
let tip = ''
let sat = { x: 0, y: 0 } // posición del satélite de arbitraje en el último render

type Row = { id: string; bias: number; conf: number; live: boolean; votes: boolean; why: string; deg: string }

/**
 * Río de decisión holográfico, como un sistema solar: los agentes son planetas que orbitan despacio
 * la esfera central (`river_orbit`) en órbitas a distinta distancia, inclinación y tamaño; los de
 * opinión más decidida (|sesgo| × confianza) van en las órbitas cercanas y los sin datos en las
 * lejanas. Pasan por delante de la esfera en la mitad delantera (SVG `rfront` sobre el canvas) y
 * por detrás en la trasera. No se conectan con ella (sin haces) y su color es su sesgo. Fuera del agente solo queda su icono: nombre, sesgo, confianza
 * y el resto viven dentro, en el detalle que se abre al tocarlo (con el puntero encima la órbita
 * se detiene para que sea fácil acertar). Sin plataforma bajo la esfera.
 */
export function renderRiver(el: HTMLElement, infos: AgentInfo[], reports: AgentReport[], synthesis: Synthesis | null, tf = ''): void {
  ctx = { infos, reports, synthesis, tf }
  rememberOpenFamilies(el)
  tip = ''
  el.onclick = (e) => {
    const t = e.target as HTMLElement
    if (t.closest('[data-open-arb]')) { // tooltip del satélite → pestaña «Arbitraje»
      document.getElementById('tab-arb')?.click()
      document.querySelector('.bottom')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
    if (t.closest('.tip') && !t.closest('[data-close]')) return // dentro del detalle (p. ej. abrir una familia)
    if (t.closest('[data-close]')) selected = null
    else {
      const g = t.closest<HTMLElement>('[data-id]')
      selected = g ? (selected === g.dataset.id ? null : g.dataset.id!) : t.closest('.tip') ? selected : null
    }
    renderRiver(el, ctx.infos, ctx.reports, ctx.synthesis, ctx.tf)
  }
  el.onpointerover = (e) => holdOrbit(!!(e.target as Element).closest('.trib'))
  el.onpointerleave = () => holdOrbit(false)
  if (!keyBound) {
    keyBound = true
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && selected) { selected = null; renderRiver(el, ctx.infos, ctx.reports, ctx.synthesis, ctx.tf) }
    })
  }
  const byId = new Map(reports.map((r) => [r.agent_id, r]))
  // arbitrage no va en las columnas: es el satélite de carril propio (sin haz hacia la síntesis)
  const all = [...new Set([...infos.map((i) => i.id), ...reports.map((r) => r.agent_id)])]
  if (!all.length) { el.innerHTML = ''; return }
  const ids = all.filter((id) => id !== ARB_ID && matches(filter, id, infos))
  const rows: Row[] = ids.map((id) => {
    const r = byId.get(id)
    const live = !!r && r.status !== 'no_data'
    return { id, bias: live ? r!.bias : 0, conf: live ? r!.confidence : 0, live, votes: votes(id, infos, synthesis), why: live ? '' : collectorLabel(id) || noDataLabel(r?.warnings), deg: live ? collectorLabel(id) || degradedLabel(r!.status, r!.warnings) : '' }
  }).sort((a, b) => b.bias - a.bias)
  const n = rows.length
  const showSat = filter === 'todos' || filter === 'carril'

  const live = rows.filter((r) => r.live)
  // Sistema solar: deja sitio a los % de subida/bajada sobre la esfera y al veredicto debajo.
  const cy = Math.max(ORBIT_EXTENT + 52, 1.42 * R + 80)
  let H = cy + ORBIT_EXTENT + 1.4 * NR + 84
  // Satélite de arbitraje: fijo abajo a la izquierda, fuera de la órbita (carril propio).
  sat = { x: 96, y: H - 62 }
  if (showSat) H = Math.max(H, sat.y + SAT_R + 30)

  const syn = synthesis
  const b = syn?.bias ?? 0
  const verdict = Math.abs(b) < THRESH ? 'Neutral' : b > 0 ? 'Sesgo de compra' : 'Sesgo de venta'
  const mainCol = tint(b, 1.8)
  const split = upDown(syn)
  // Color del porcentaje mayor, más intenso cuanto mayor es la ventaja (50/50 o sin señal → cian):
  // solo como respaldo sin señal. Esfera y haz se pintan con el reparto subida/bajada.
  const lead = split ? Math.max(split.up, split.down) : 50
  const fill = (lead - 50) / 50
  const rc = split && fill > 0
    ? `color-mix(in srgb, var(--${split.up > split.down ? 'up' : 'down'}) ${Math.round(25 + 75 * fill)}%, var(--holo))`
    : 'var(--holo)'

  // Planetas en dos capas: los de la mitad trasera bajo la esfera, los de la delantera sobre ella.
  const back: { d: number; svg: string }[] = [], front: typeof back = []
  const node = (r: Row, k: number): void => {
    const p = orbitPos(k, n, CX, cy)
    const col = r.live ? tint(r.bias) : 'var(--muted)'
    if (r.id === selected) {
      const pos = `left:${Math.min(80, Math.max(20, (p.x / W) * 100)).toFixed(1)}%;` +
        (p.y < H / 2 ? `top:${(((p.y + NR * p.s + 10) / H) * 100).toFixed(1)}%` : `bottom:${(((H - p.y + NR * p.s + 10) / H) * 100).toFixed(1)}%`)
      tip = `<div class="tip" style="${pos}" role="dialog">${agentTip(byId.get(r.id), r.id, synthesis, infos)}</div>`
    }
    const state = r.live ? `sesgo ${sg(r.bias)}, confianza ${Math.round(r.conf * 100)}%` : r.why
    const svg = `<g class="trib${r.id === selected ? ' sel' : ''}" data-id="${esc(r.id)}" data-k="${k}" transform="${orbitTransform(p)}" ` +
      `style="opacity:${p.o.toFixed(2)}" tabindex="0" role="button" aria-label="${esc(agentName(r.id))} (${esc(state)}): ver detalles">` +
      `<circle r="${NR + 4}" fill="none" stroke="${col}" stroke-width="1" stroke-dasharray="4 5" opacity=".7" class="hspin"/>` +
      orb(r.id, 0, 0, NR, r.live && Math.abs(r.bias) < THRESH ? 'var(--holo)' : col, r.live, k) +
      `<text y="${NR + 18}" text-anchor="middle" class="rname hov">${esc(agentName(r.id))}</text></g>`
    ;(p.front ? front : back).push({ d: p.depth, svg })
  }
  // Orden en las órbitas: de dentro hacia fuera, de la opinión más decidida a los sin datos.
  ;[...rows].sort((a, b) => Number(b.live) - Number(a.live) || Math.abs(b.bias) * b.conf - Math.abs(a.bias) * a.conf)
    .forEach((r, k) => node(r, k))
  const layer = (xs: typeof back): string => xs.sort((a, b) => a.d - b.d).map((x) => x.svg).join('')

  const ups = rows.filter((r) => r.live && r.bias >= THRESH).length
  const downs = rows.filter((r) => r.live && r.bias <= -THRESH).length
  const deco = [[48, 36, 15], [76, 62, 9], [W - 48, H - 70, 13], [W - 80, H - 46, 8]]
    .map(([x, y, s]) => `<path d="${hexPath(x, y, s)}" fill="none" stroke="var(--holo)" stroke-width="1.2" opacity=".45"/>`).join('')

  // Esfera 3D en un canvas superpuesto (cabe el anillo orbital: semilado 1.42·R).
  const S = 1.42 * R
  const pct = (v: number, of: number): string => `${((v / of) * 100).toFixed(3)}%`
  const sphere = `<canvas class="hsphere" aria-hidden="true" data-color="${esc(rc)}" data-up="${split ? split.up : ''}" data-fill="${fill.toFixed(3)}" style="left:${pct(CX - S, W)};` +
    `top:${pct(cy - S, H)};width:${pct(2 * S, W)};height:${pct(2 * S, H)}"></canvas>`
  if (selected === CORE_ID) tip = `<div class="tip tip-core" style="left:50%;top:2%" role="dialog">${coreTip(syn, reports, infos)}</div>`
  if (selected === ARB_ID && showSat) {
    tip = `<div class="tip tip-arb" style="left:${pct(Math.max(sat.x, 200), W)};bottom:${pct(H - sat.y + SAT_R + 18, H)}" role="dialog">${arbTip()}</div>`
  }
  el.style.setProperty('--rt', Math.abs(b) < THRESH ? 'transparent' : mainCol)
  el.innerHTML = `<div class="river-head"><h3>Río de decisión</h3></div>` +
    `<div class="rsvg"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(verdict)}: ${ups} agentes en verde, ${downs} en rojo">` +
    `<defs>${holoDefs(rc, split ? split.up : null, CX, R)}</defs>` +
    core(CX, cy, R, cy + 1.6 * R) + deco +
    orbitPaths(CX, cy) + `<g class="orbit-back">${layer(back)}</g>` +
    (showSat ? arbSatellite(sat.x, sat.y, selected === ARB_ID) : '') +
    `<text x="${CX}" y="${H - 34}" text-anchor="middle" class="rbig" style="fill:${mainCol}">${esc(verdict)}</text>` +
    `<text x="${CX}" y="${H - 12}" text-anchor="middle" class="rv">sesgo ${syn ? sg(b) : '—'} · confianza ${syn ? Math.round(syn.confidence * 100) : 0}% · ` +
    `acuerdo ${syn ? Math.round(syn.agreement * 100) : 0}% · ` +
    (votesLine(syn, true) ? `${votesLine(syn, true)} · ` : '') +
    (filter === 'carril' ? 'arbitraje: carril propio, no suma a la síntesis'
      : `${live.length} de ${n} agentes con datos${filter === 'todos' ? '' : ' (filtro activo)'}`) + '</text>' +
    `</svg>${sphere}<svg class="rfront" viewBox="0 0 ${W} ${H}"><g class="orbit-front">${layer(front)}</g></svg>` +
    `<div class="rcore${selected === CORE_ID ? ' sel' : ''}" data-id="${CORE_ID}" role="button" tabindex="0" ` +
    `aria-label="Síntesis: ver detalles" style="left:${pct(CX, W)};top:${pct(cy - 1.42 * R - 6, H)}" title="${esc(PCT_NOTE)}">` +
    (split
      ? `<b class="pu${split.up > split.down ? ' lead' : ''}" style="color:${tint(1)}">▲ ${split.up}%<i>subida</i></b>` +
        `<b class="pd${split.down > split.up ? ' lead' : ''}" style="color:${tint(-1)}">▼ ${split.down}%<i>bajada</i></b>`
      : '<b>—<i>sin señal</i></b>') +
    `<small>proyección estimada${tf ? ` · ${esc(tf)}` : ''} · clic: síntesis</small>` +
    `</div>${tip}</div>`
  animateSphere(el)
  animateOrbit(el, CX, cy, () => selected !== null && selected !== CORE_ID)
}

/** Escaneo nuevo de arbitraje (REST/WS): repinta solo el satélite y su tooltip, sin reiniciar
 * la animación de la esfera central. */
export function refreshArbitrage(el: HTMLElement, p: ArbPayload): void {
  setArbData(p)
  const g = el.querySelector('g.arb-sat')
  if (!g) return // el río aún no se dibujó: tomará el dato en su próximo render
  g.outerHTML = arbSatellite(sat.x, sat.y, selected === ARB_ID)
  const t = el.querySelector('.tip-arb')
  if (t) t.innerHTML = arbTip()
}

/** Abre el detalle de un agente en el río (p. ej. desde el reloj de eventos de la barra
 * superior). */
export function openAgent(id: string): void {
  const el = document.getElementById('river')
  if (!el) return
  selected = id
  renderRiver(el, ctx.infos, ctx.reports, ctx.synthesis, ctx.tf)
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
