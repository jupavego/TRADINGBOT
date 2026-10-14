import { orb } from './agent_orbs'
import { calendarDetail } from './calendar_ui'
import { agentName, esc } from './panels'
import { core, hexPath, holoDefs, platform } from './river_holo'
import { animateSphere } from './river_sphere'
import { PCT_NOTE, upDown } from './synth'
import { rememberOpenFamilies, technicalDetail } from './technical_ui'
import type { AgentInfo, AgentReport, Synthesis } from './types'

const THRESH = 0.1 // |sesgo| mínimo para teñir de verde/rojo
const W = 1200, CX = W / 2, NR = 21, ROW = 52, R = 104, TOP = 54

let selected: string | null = null // agente con tooltip abierto
let ctx: { infos: AgentInfo[]; reports: AgentReport[]; synthesis: Synthesis | null; tf: string } = { infos: [], reports: [], synthesis: null, tf: '' }
let keyBound = false
let tip = ''

const STATUS: Record<string, string> = { ok: 'OK', degraded: 'Degradado', no_data: 'Sin datos' }
const fmt = (v: unknown): string =>
  typeof v === 'number' ? String(Math.round(v * 1e4) / 1e4)
    : typeof v === 'object' && v !== null ? JSON.stringify(v).slice(0, 80) : String(v)

/** Contenido del tooltip de un agente a partir de su último reporte. */
function tipHtml(r: AgentReport | undefined, id: string): string {
  const head = `<div class="tip-h"><b>${esc(agentName(id))}</b><button data-close aria-label="Cerrar">×</button></div>`
  if (!r) return `${head}<p class="muted">Aún sin reporte: se ejecuta al cerrar la próxima vela.</p>`
  const dir = Math.abs(r.bias) < THRESH ? 'Neutral' : r.bias > 0 ? 'Compra' : 'Venta'
  const ev = r.evidence.slice(0, 4).map((e) => `<li>${esc(e)}</li>`).join('')
  const wn = r.warnings.map((w) => `<li>${esc(w)}</li>`).join('')
  const mt = Object.entries(r.metrics).slice(0, 6)
    .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(fmt(v))}</td></tr>`).join('')
  return head +
    `<div class="tip-k"><span class="chip" data-s="${esc(r.status)}">${esc(STATUS[r.status] ?? r.status)}</span>` +
    `<b style="color:${tint(r.bias)}">${dir} ${sg(r.bias)}</b><span class="muted">confianza ${Math.round(r.confidence * 100)}% · ${r.horizon_bars} velas</span></div>` +
    (ev ? `<ul class="ev">${ev}</ul>` : '') + (wn ? `<ul class="warn">${wn}</ul>` : '') +
    (r.agent_id === 'technical' ? technicalDetail(r.metrics) : r.agent_id === 'calendar' ? calendarDetail(r.metrics)
      : mt ? `<table class="metrics">${mt}</table>` : '') +
    `<p class="muted">v${esc(r.version)} · ${new Date(r.asof).toISOString().slice(0, 16).replace('T', ' ')} UTC</p>`
}

type Row = { id: string; bias: number; conf: number; live: boolean }

/** Color de un sesgo: gris (neutro) → verde/rojo según intensidad. */
const tint = (b: number, k = 1): string =>
  Math.abs(b) < THRESH
    ? 'var(--muted)'
    : `color-mix(in srgb, var(--${b > 0 ? 'up' : 'down'}) ${Math.round(Math.min(1, Math.abs(b) * k) * 45 + 55)}%, var(--panel))`

const sg = (b: number): string => (b > 0 ? '+' : '') + b.toFixed(2)

/** Pulsos de luz (cabeza brillante + estela) que recorren un haz hasta la esfera. */
function pulses(pathId: string, n: number, dur: number, r: number, col: string): string {
  // `begin` negativo = la animación ya va por ese punto; la estela va unos instantes por detrás.
  const motion = (t: number): string =>
    `<animateMotion dur="${dur.toFixed(1)}s" begin="${(-t).toFixed(2)}s" repeatCount="indefinite"><mpath href="#${pathId}"/></animateMotion>`
  return Array.from({ length: n }, (_, k) => {
    const t = (dur / n) * k + dur
    return `<circle r="${(r * 2.4).toFixed(1)}" fill="${col}" opacity=".35" filter="url(#rblur)">${motion(t)}</circle>` +
      [0.04, 0.08, 0.12].map((lag, j) =>
        `<circle r="${(r * (0.85 - j * 0.2)).toFixed(1)}" fill="${col}" opacity="${(0.6 - j * 0.17).toFixed(2)}">${motion(t - lag * dur)}</circle>`).join('') +
      `<circle r="${r.toFixed(1)}" fill="#fff">${motion(t)}</circle>`
  }).join('')
}

/**
 * Río de decisión holográfico (formato horizontal). Un nodo por agente en dos columnas: a la
 * izquierda los más alcistas, a la derecha los más bajistas; los extremos quedan arriba. De cada
 * nodo sale un haz con pulsos de luz que viajan hasta la esfera central, cuyo color es el sesgo
 * de la síntesis. Grosor, número y velocidad de los pulsos = confianza; discontinuo = sin datos.
 * Las etiquetas viven en columnas de ancho fijo separadas `ROW`: nunca se solapan.
 */
export function renderRiver(el: HTMLElement, infos: AgentInfo[], reports: AgentReport[], synthesis: Synthesis | null, tf = ''): void {
  ctx = { infos, reports, synthesis, tf }
  rememberOpenFamilies(el)
  tip = ''
  el.onclick = (e) => {
    const t = e.target as HTMLElement
    if (t.closest('.tip') && !t.closest('[data-close]')) return // dentro del detalle (p. ej. abrir una familia)
    if (t.closest('[data-close]')) selected = null
    else {
      const g = t.closest<HTMLElement>('[data-id]')
      selected = g ? (selected === g.dataset.id ? null : g.dataset.id!) : t.closest('.tip') ? selected : null
    }
    renderRiver(el, ctx.infos, ctx.reports, ctx.synthesis, ctx.tf)
  }
  if (!keyBound) {
    keyBound = true
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && selected) { selected = null; renderRiver(el, ctx.infos, ctx.reports, ctx.synthesis, ctx.tf) }
    })
  }
  const byId = new Map(reports.map((r) => [r.agent_id, r]))
  const ids = [...new Set([...infos.map((i) => i.id), ...reports.map((r) => r.agent_id)])]
  const rows: Row[] = ids.map((id) => {
    const r = byId.get(id)
    const live = !!r && r.status !== 'no_data'
    return { id, bias: live ? r!.bias : 0, conf: live ? r!.confidence : 0, live }
  }).sort((a, b) => b.bias - a.bias)
  const n = rows.length
  if (!n) { el.innerHTML = ''; return }

  // Columnas equilibradas: mitad alcista a la izquierda, mitad bajista a la derecha (invertida
  // para que el más bajista quede arriba). Los agentes sin datos completan la columna más corta.
  const live = rows.filter((r) => r.live), dead = rows.filter((r) => !r.live)
  const half = Math.ceil(live.length / 2)
  const left = live.slice(0, half), right = live.slice(half).reverse()
  dead.forEach((r) => (left.length <= right.length ? left : right).push(r))
  const per = Math.max(left.length, right.length, 1)
  const colH = (per - 1) * ROW
  const H = Math.max(460, TOP + colH + 60)
  const py = H - 98
  const cy = Math.min(Math.max(TOP + R + 8, TOP + colH / 2), py - R - 30)

  const syn = synthesis
  const b = syn?.bias ?? 0
  const verdict = Math.abs(b) < THRESH ? 'Neutral' : b > 0 ? 'Sesgo de compra' : 'Sesgo de venta'
  const mainCol = tint(b, 1.8)
  const split = upDown(syn)
  // Color de la esfera (y del haz/plataforma): el del porcentaje mayor, más intenso cuanto
  // mayor es la ventaja; 50/50 o sin señal → cian neutro.
  const lead = split ? Math.max(split.up, split.down) : 50
  const fill = (lead - 50) / 50
  const rc = split && fill > 0
    ? `color-mix(in srgb, var(--${split.up > split.down ? 'up' : 'down'}) ${Math.round(25 + 75 * fill)}%, var(--holo))`
    : 'var(--holo)'

  const node = (r: Row, k: number, col0: Row[], isLeft: boolean): string => {
    const y = TOP + k * ROW + ((per - col0.length) * ROW) / 2
    const s = isLeft ? 1 : -1
    const nx = isLeft ? 52 : W - 52
    const col = r.live ? tint(r.bias) : 'var(--muted)'
    const w = r.live ? 2 + r.conf * 5 : 1.5
    // Haz: tramo horizontal, codo y diagonal hasta la superficie de la esfera.
    const a = Math.max(-1.05, Math.min(1.05, ((y - cy) / Math.max(colH / 2, ROW)) * 1.05))
    const tx = (CX - s * R * Math.cos(a)).toFixed(1), ty = (cy + R * Math.sin(a)).toFixed(1)
    const x0 = nx + s * 196, xk = nx + s * 262
    const d = `M${x0} ${y} L${xk} ${y} L${tx} ${ty}`
    const i = rows.indexOf(r)
    if (r.id === selected) {
      const pos = `left:${Math.min(80, Math.max(20, (nx / W) * 100 + s * 14)).toFixed(1)}%;` +
        (y < H / 2 ? `top:${(((y + NR + 10) / H) * 100).toFixed(1)}%` : `bottom:${(((H - y + NR + 10) / H) * 100).toFixed(1)}%`)
      tip = `<div class="tip" style="${pos}" role="dialog">${tipHtml(byId.get(r.id), r.id)}</div>`
    }
    const lx = nx + s * (NR + 11), anchor = isLeft ? 'start' : 'end'
    const bw = 92, bx = isLeft ? lx : lx - bw
    const pct = r.live ? `${Math.round(r.conf * 100)}%` : 'sin datos'
    return `<g class="trib${r.id === selected ? ' sel' : ''}" data-id="${esc(r.id)}" tabindex="0" role="button" aria-label="${esc(agentName(r.id))}: ver detalles">` +
      (r.live ? `<path d="${d}" fill="none" stroke="${col}" stroke-width="${w + 7}" stroke-linejoin="round" opacity=".28" filter="url(#rblur)"/>` : '') +
      `<path id="rp${i}" d="${d}" fill="none" stroke="${col}" stroke-width="${w.toFixed(1)}" stroke-linejoin="round" opacity="${r.live ? 0.85 : 0.5}"` +
      `${r.live ? ' class="hflow"' : ' stroke-dasharray="3 7"'}/>` +
      `<circle cx="${x0}" cy="${y}" r="3" fill="${col}"/>` +
      (r.live ? pulses(`rp${i}`, 1 + Math.round(r.conf * 3), 4.8 - 2.2 * r.conf, 1.8 + r.conf * 1.4, col) : '') +
      `<circle cx="${tx}" cy="${ty}" r="${(w / 2 + 2).toFixed(1)}" fill="${col}" opacity=".9"/>` +
      `<circle cx="${nx}" cy="${y}" r="${NR + 4}" fill="none" stroke="${col}" stroke-width="1" stroke-dasharray="4 5" opacity=".7" class="hspin"/>` +
      orb(r.id, nx, y, NR, r.live && Math.abs(r.bias) < THRESH ? 'var(--holo)' : col, r.live, i) +
      `<text x="${lx}" y="${y - 5}" text-anchor="${anchor}" class="rl">${esc(agentName(r.id))}` +
      `<tspan dx="6" class="rvv" style="fill:${col}">${r.live ? sg(r.bias) : '—'}</tspan></text>` +
      `<rect x="${bx}" y="${y + 4}" width="${bw}" height="3" rx="1.5" class="cbar"/>` +
      (r.live ? `<rect x="${(isLeft ? bx : bx + bw * (1 - r.conf)).toFixed(1)}" y="${y + 4}" width="${(bw * r.conf).toFixed(1)}" height="3" rx="1.5" fill="${col}"/>` : '') +
      `<text x="${isLeft ? bx + bw + 6 : bx - 6}" y="${y + 13}" text-anchor="${anchor}" class="rv">${pct}</text></g>`
  }

  const ups = rows.filter((r) => r.live && r.bias >= THRESH).length
  const downs = rows.filter((r) => r.live && r.bias <= -THRESH).length
  const flat = live.length - ups - downs
  const deco = [[CX - 330, 36, 15], [CX - 302, 62, 9], [CX + 332, py - 4, 13], [CX + 300, py + 20, 8]]
    .map(([x, y, s]) => `<path d="${hexPath(x, y, s)}" fill="none" stroke="var(--holo)" stroke-width="1.2" opacity=".45"/>`).join('')

  // Esfera 3D en un canvas superpuesto (cabe el anillo orbital: semilado 1.42·R).
  const S = 1.42 * R
  const pct = (v: number, of: number): string => `${((v / of) * 100).toFixed(3)}%`
  const sphere = `<canvas class="hsphere" aria-hidden="true" data-color="${esc(rc)}" data-fill="${fill.toFixed(3)}" style="left:${pct(CX - S, W)};` +
    `top:${pct(cy - S, H)};width:${pct(2 * S, W)};height:${pct(2 * S, H)}"></canvas>`
  el.style.setProperty('--rt', Math.abs(b) < THRESH ? 'transparent' : mainCol)
  el.innerHTML = `<div class="river-head"><h3>Río de decisión</h3>` +
    `<span class="chips"><i class="c up">${ups} compra</i><i class="c flat">${flat} neutral</i><i class="c down">${downs} venta</i></span></div>` +
    `<div class="rsvg"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(verdict)}: ${ups} agentes en verde, ${downs} en rojo">` +
    `<defs>${holoDefs(rc)}</defs>` +
    platform(CX, py, rc) + core(CX, cy, R, py, rc) + deco +
    left.map((r, k) => node(r, k, left, true)).join('') + right.map((r, k) => node(r, k, right, false)).join('') +
    `<text x="${CX}" y="${H - 34}" text-anchor="middle" class="rbig" style="fill:${mainCol}">${esc(verdict)}</text>` +
    `<text x="${CX}" y="${H - 12}" text-anchor="middle" class="rv">sesgo ${syn ? sg(b) : '—'} · acuerdo ${syn ? Math.round(syn.agreement * 100) : 0}% · ` +
    `${live.length} de ${n} agentes con datos</text>` +
    `</svg>${sphere}<div class="rcore" style="left:${pct(CX, W)};top:${pct(cy, H)}" title="${esc(PCT_NOTE)}">` +
    (split
      ? `<b class="pu${split.up > split.down ? ' lead' : ''}" style="color:${tint(1)}">▲ ${split.up}%<i>subida</i></b>` +
        `<b class="pd${split.down > split.up ? ' lead' : ''}" style="color:${tint(-1)}">▼ ${split.down}%<i>bajada</i></b>`
      : '<b>—<i>sin señal</i></b>') +
    `<small>proyección estimada${tf ? ` · ${esc(tf)}` : ''}</small>` +
    `</div>${tip}</div>`
  animateSphere(el)
}
