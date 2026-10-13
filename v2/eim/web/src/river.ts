import { agentName, esc } from './panels'
import { simulateSynthesis } from './synth'
import type { AgentInfo, AgentReport } from './types'

const THRESH = 0.1 // |sesgo| mínimo para teñir de verde/rojo
const H = 380, YM = 190, GX = 40, XE = 900, NR = 19, TOP = 62

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
 * Río principal con un nodo (círculo) por agente. Los nodos alcistas van arriba y los bajistas
 * abajo; de cada uno baja/sube un arroyo que desemboca en un punto distinto a lo largo del
 * cauce, tiñéndolo según el sesgo acumulado de los agentes que ya han confluido.
 * Grosor y velocidad del arroyo = confianza.
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

  // arriba: sesgo >= 0; abajo: negativos. Los sin datos van al lado con menos nodos.
  const side: boolean[] = rows.map((r) => (r.live ? r.bias >= 0 : false))
  const topCount = rows.filter((r, i) => r.live && side[i]).length
  const botCount = rows.filter((r, i) => r.live && !side[i]).length
  rows.forEach((r, i) => { if (!r.live) side[i] = topCount <= botCount })

  const px0 = 80, pxN = XE - 150
  const px = rows.map((_, i) => (n === 1 ? px0 : px0 + (i * (pxN - px0)) / (n - 1)))
  const tot = rows.reduce((a, r) => a + r.conf, 0)
  const mainW = 64 + Math.min(1, tot / Math.max(1, n)) * 34
  const yTop = TOP, yBot = H - TOP
  const yEnd = side.map((up) => (up ? YM - mainW * 0.22 : YM + mainW * 0.22))

  let sw = 0, sb = 0
  const stops: string[] = ['']
  const defs: string[] = []
  const tribs = rows.map((r, i) => {
    if (r.live) { sw += r.conf; sb += r.conf * r.bias }
    const cum = sw > 0 ? sb / sw : 0
    const x1 = px[i] + 95
    stops.push(`<stop offset="${((x1 - GX) / (XE - GX)).toFixed(3)}" style="stop-color:${tint(cum, 1.8)}"/>`)
    const up = side[i]
    const cy = up ? yTop : yBot
    const y0 = up ? cy + NR : cy - NR
    const w = r.live ? 6 + r.conf * 14 : 2.5
    const col = r.live ? tint(r.bias) : 'var(--line)'
    const d = `M${px[i]} ${y0} C${px[i]} ${yEnd[i]} ${px[i] + 25} ${yEnd[i]} ${x1} ${yEnd[i]}`
    defs.push(`<linearGradient id="rg${i}" gradientUnits="userSpaceOnUse" x1="0" y1="${y0}" x2="0" y2="${yEnd[i]}">` +
      `<stop offset="0" style="stop-color:${col}"/><stop offset=".55" style="stop-color:${col}" stop-opacity=".95"/>` +
      `<stop offset="1" style="stop-color:${col}"/></linearGradient>`)
    const lblY = up ? cy - NR - 9 : cy + NR + 17
    const val = r.live ? sg(r.bias) : '—'
    return `<g class="trib">` +
      (r.live ? `<path d="${d}" fill="none" stroke="${col}" stroke-width="${w + 8}" stroke-linecap="round" opacity=".28" filter="url(#rblur)"/>` : '') +
      `<path id="rp${i}" d="${d}" fill="none" stroke="${r.live ? `url(#rg${i})` : col}" stroke-width="${w.toFixed(1)}" stroke-linecap="round"` +
      `${r.live ? '' : ' stroke-dasharray="3 8"'}/>` +
      (r.live ? particles(`rp${i}`, 2 + Math.round(r.conf * 2), 7 - 3.5 * r.conf, Math.max(1.6, w * 0.16), '#fff') : '') +
      `<circle cx="${x1}" cy="${yEnd[i]}" r="${(w / 2 + 2).toFixed(1)}" class="conf" style="stroke:${col}"/>` +
      (r.live ? `<circle cx="${px[i]}" cy="${cy}" r="${NR + 7}" fill="${col}" opacity=".22" filter="url(#rblur)"/>` : '') +
      `<circle cx="${px[i]}" cy="${cy}" r="${NR}" class="anode${r.live ? '' : ' off'}" style="stroke:${col}"/>` +
      `<text x="${px[i]}" y="${cy + 4}" text-anchor="middle" class="rvv" style="fill:${r.live ? col : 'var(--muted)'}">${val}</text>` +
      `<text x="${px[i]}" y="${lblY}" text-anchor="middle" class="rl">${esc(agentName(r.id))}</text></g>`
  }).join('')

  const ups = rows.filter((r) => r.live && r.bias >= THRESH).length
  const downs = rows.filter((r) => r.live && r.bias <= -THRESH).length
  const flat = rows.filter((r) => r.live).length - ups - downs
  const syn = simulateSynthesis(reports)
  const b = syn?.bias ?? 0
  const verdict = Math.abs(b) < THRESH ? 'Neutral' : b > 0 ? 'Sesgo de compra' : 'Sesgo de venta'
  const mainCol = tint(b, 1.8)
  const first = rows.findIndex((r) => r.live)
  stops[0] = `<stop offset="0" style="stop-color:${first >= 0 ? tint(rows[first].bias) : 'var(--line)'}" stop-opacity="0"/>`
  stops.push(`<stop offset="1" style="stop-color:${mainCol}"/>`)
  const main = `M${GX} ${YM} L${XE + 40} ${YM}`

  el.style.setProperty('--rt', Math.abs(b) < THRESH ? 'transparent' : tint(b, 1.8))
  el.innerHTML = `<div class="river-head"><h3>Río de decisión <span class="sim">simulada · hasta T20</span></h3>` +
    `<span class="chips"><i class="c up">${ups} compra</i><i class="c flat">${flat} neutral</i><i class="c down">${downs} venta</i></span></div>` +
    `<svg viewBox="0 0 1200 ${H}" role="img" aria-label="${esc(verdict)}: ${ups} agentes en verde, ${downs} en rojo">` +
    `<defs><filter id="rblur" x="-30%" y="-120%" width="160%" height="340%"><feGaussianBlur stdDeviation="9"/></filter>` +
    `<linearGradient id="rv" gradientUnits="userSpaceOnUse" x1="${GX}" y1="0" x2="${XE}" y2="0">${stops.join('')}</linearGradient>${defs.join('')}</defs>` +
    `<path d="${main}" stroke="url(#rv)" stroke-width="${mainW + 16}" stroke-linecap="round" fill="none" opacity=".45" filter="url(#rblur)"/>` +
    `<path d="${main}" stroke="url(#rv)" stroke-width="${mainW.toFixed(1)}" stroke-linecap="round" fill="none"/>` +
    `<path d="M${GX + 60} ${YM - mainW * 0.05} L${XE + 30} ${YM - mainW * 0.05}" stroke="#fff" stroke-opacity=".25" stroke-width="3" stroke-linecap="round" fill="none"/>` +
    tribs +
    `<path id="rmain" d="${main}" fill="none" stroke="none"/>` +
    particles('rmain', 6, 5, 2.4, '#fff') +
    `<text x="${XE + 85}" y="${YM - 4}" class="rbig" style="fill:${mainCol}" filter="url(#rblur)" opacity=".55" aria-hidden="true">${esc(verdict)}</text>` +
    `<text x="${XE + 85}" y="${YM - 4}" class="rbig" style="fill:${mainCol}">${esc(verdict)}</text>` +
    `<text x="${XE + 85}" y="${YM + 24}" class="rv">${syn ? sg(b) : '—'} · acuerdo ${syn ? Math.round(syn.agreement * 100) : 0}%</text></svg>`
}
