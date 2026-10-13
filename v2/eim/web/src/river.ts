import { agentName, esc } from './panels'
import { simulateSynthesis } from './synth'
import type { AgentInfo, AgentReport } from './types'

const THRESH = 0.1 // |sesgo| mínimo para teñir de verde/rojo
const X0 = 235, XM = 600, XE = 880, YM = 170, H = 340

type Row = { id: string; bias: number; conf: number; live: boolean }

/** Color de un sesgo: gris (neutro) → verde/rojo según intensidad. */
const tint = (b: number, k = 1): string =>
  Math.abs(b) < THRESH
    ? 'var(--muted)'
    : `color-mix(in srgb, var(--${b > 0 ? 'up' : 'down'}) ${Math.round(Math.min(1, Math.abs(b) * k) * 45 + 55)}%, var(--panel))`

const sg = (b: number): string => (b > 0 ? '+' : '') + b.toFixed(2)

/** Partículas que recorren un trazado (`animateMotion`), desfasadas entre sí. */
function particles(pathId: string, n: number, dur: number, r: number, fill: string): string {
  return Array.from({ length: n }, (_, k) =>
    `<circle r="${r}" fill="${fill}" opacity=".85"><animateMotion dur="${dur.toFixed(1)}s" ` +
    `begin="-${((dur / n) * k).toFixed(2)}s" repeatCount="indefinite"><mpath href="#${pathId}"/></animateMotion></circle>`,
  ).join('')
}

/**
 * Río principal con un afluente por agente. Cada afluente lleva el color de su conclusión
 * (verde = compra, rojo = venta, gris = neutral) y al confluir tiñe el cauce según el sesgo
 * acumulado de los agentes que ya han desembocado. Grosor y velocidad = confianza.
 */
export function renderRiver(el: HTMLElement, infos: AgentInfo[], reports: AgentReport[]): void {
  const byId = new Map(reports.map((r) => [r.agent_id, r]))
  const ids = [...new Set([...infos.map((i) => i.id), ...reports.map((r) => r.agent_id)])]
  const rows: Row[] = ids.map((id) => {
    const r = byId.get(id)
    const live = !!r && r.status !== 'no_data'
    return { id, bias: live ? r!.bias : 0, conf: live ? r!.confidence : 0, live }
  }).sort((a, b) => b.bias - a.bias)
  const n = rows.length
  if (!n) { el.innerHTML = ''; return }

  const gap = (H - 70) / Math.max(1, n - 1)
  const ys = rows.map((_, i) => (n === 1 ? YM : 35 + i * gap))
  const cx = rows.map((_, i) => XM + 25 + (i * (XE - XM - 90)) / Math.max(1, n - 1))
  let sw = 0, sb = 0
  const stops: string[] = ['']
  const defs: string[] = []
  const tribs = rows.map((r, i) => {
    if (r.live) { sw += r.conf; sb += r.conf * r.bias }
    const cum = sw > 0 ? sb / sw : 0
    stops.push(`<stop offset="${((cx[i] - XM) / (XE - XM)).toFixed(3)}" style="stop-color:${tint(cum, 1.8)}"/>`)
    const w = r.live ? 5 + r.conf * 15 : 2.5
    const col = r.live ? tint(r.bias) : 'var(--line)'
    const d = `M${X0} ${ys[i]} C${X0 + (cx[i] - X0) * 0.55} ${ys[i]} ${cx[i] - 150} ${YM} ${cx[i]} ${YM}`
    defs.push(`<linearGradient id="rg${i}" gradientUnits="userSpaceOnUse" x1="${X0}" y1="0" x2="${cx[i]}" y2="0">` +
      `<stop offset="0" style="stop-color:${col}" stop-opacity=".35"/><stop offset=".6" style="stop-color:${col}" stop-opacity=".95"/>` +
      `<stop offset="1" style="stop-color:${col}"/></linearGradient>`)
    const pw = 20 + Math.max(agentName(r.id).length * 7.4 + 78, 138)
    const val = r.live ? sg(r.bias) : '—'
    return `<g class="trib">` +
      (r.live ? `<path d="${d}" fill="none" stroke="${col}" stroke-width="${w + 8}" stroke-linecap="round" opacity=".28" filter="url(#rblur)"/>` : '') +
      `<path id="rp${i}" d="${d}" fill="none" stroke="url(#rg${i})" stroke-width="${w.toFixed(1)}" stroke-linecap="round"` +
      `${r.live ? '' : ' stroke-dasharray="3 8"'}/>` +
      (r.live ? particles(`rp${i}`, 2 + Math.round(r.conf * 2), 7 - 3.5 * r.conf, Math.max(1.6, w * 0.16), '#fff') : '') +
      `<rect x="${X0 - pw - 6}" y="${ys[i] - 14}" width="${pw}" height="28" rx="14" class="pill${r.live ? '' : ' off'}"/>` +
      `<circle cx="${X0 - pw + 10}" cy="${ys[i]}" r="4.5" fill="${col}"/>` +
      `<text x="${X0 - pw + 22}" y="${ys[i] + 4.5}" class="rl">${esc(agentName(r.id))}</text>` +
      `<text x="${X0 - 18}" y="${ys[i] + 4.5}" text-anchor="end" class="rvv" style="fill:${r.live ? col : 'var(--muted)'}">${val}</text>` +
      `<circle cx="${X0}" cy="${ys[i]}" r="${(w / 2 + 3).toFixed(1)}" fill="${col}" class="node"/>` +
      `<circle cx="${cx[i]}" cy="${YM}" r="${(w / 2 + 2).toFixed(1)}" class="conf" style="stroke:${col}"/></g>`
  }).join('')

  const ups = rows.filter((r) => r.live && r.bias >= THRESH).length
  const downs = rows.filter((r) => r.live && r.bias <= -THRESH).length
  const flat = rows.filter((r) => r.live).length - ups - downs
  const syn = simulateSynthesis(reports)
  const b = syn?.bias ?? 0
  const verdict = Math.abs(b) < THRESH ? 'Neutral' : b > 0 ? 'Sesgo de compra' : 'Sesgo de venta'
  const mainW = 28 + Math.min(1, sw / Math.max(1, n)) * 30
  const mainCol = tint(b, 1.8)
  const first = rows.findIndex((r) => r.live)
  stops[0] = `<stop offset="0" style="stop-color:${first >= 0 ? tint(rows[first].bias) : 'var(--line)'}" stop-opacity="0"/>`
  stops.push(`<stop offset="1" style="stop-color:${mainCol}"/>`)
  const main = `M${XM - 40} ${YM} L${XE + 40} ${YM}`

  el.style.setProperty('--rt', Math.abs(b) < THRESH ? 'transparent' : tint(b, 1.8))
  el.innerHTML = `<div class="river-head"><h3>Río de decisión <span class="sim">simulada · hasta T20</span></h3>` +
    `<span class="chips"><i class="c up">${ups} compra</i><i class="c flat">${flat} neutral</i><i class="c down">${downs} venta</i></span></div>` +
    `<svg viewBox="0 0 1200 ${H}" role="img" aria-label="${esc(verdict)}: ${ups} agentes en verde, ${downs} en rojo">` +
    `<defs><filter id="rblur" x="-30%" y="-120%" width="160%" height="340%"><feGaussianBlur stdDeviation="9"/></filter>` +
    `<linearGradient id="rv" gradientUnits="userSpaceOnUse" x1="${XM}" y1="0" x2="${XE}" y2="0">${stops.join('')}</linearGradient>${defs.join('')}</defs>` +
    `<path d="${main}" stroke="url(#rv)" stroke-width="${mainW + 16}" stroke-linecap="round" fill="none" opacity=".45" filter="url(#rblur)"/>` +
    `<path d="${main}" stroke="url(#rv)" stroke-width="${mainW.toFixed(1)}" stroke-linecap="round" fill="none"/>` +
    `<path d="M${XM - 30} ${YM - mainW * 0.22} L${XE + 30} ${YM - mainW * 0.22}" stroke="#fff" stroke-opacity=".28" stroke-width="3" stroke-linecap="round" fill="none"/>` +
    tribs +
    `<path id="rmain" d="${main}" fill="none" stroke="none"/>` +
    particles('rmain', 6, 4.5, 2.4, '#fff') +
    `<text x="${XE + 85}" y="${YM - 4}" class="rbig" style="fill:${mainCol}" filter="url(#rblur)" opacity=".55" aria-hidden="true">${esc(verdict)}</text>` +
    `<text x="${XE + 85}" y="${YM - 4}" class="rbig" style="fill:${mainCol}">${esc(verdict)}</text>` +
    `<text x="${XE + 85}" y="${YM + 24}" class="rv">${syn ? sg(b) : '—'} · acuerdo ${syn ? Math.round(syn.agreement * 100) : 0}%</text></svg>`
}
