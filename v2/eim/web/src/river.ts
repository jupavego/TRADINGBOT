import { agentName, esc } from './panels'
import { simulateSynthesis } from './synth'
import type { AgentInfo, AgentReport } from './types'

const THRESH = 0.1 // |sesgo| mínimo para teñir de verde/rojo
const X0 = 170, XM = 560, XE = 930, YM = 160, H = 320

type Row = { id: string; bias: number; conf: number; live: boolean }

/** Color de un sesgo: gris (neutro) → verde/rojo según intensidad. */
const tint = (b: number, k = 1): string =>
  Math.abs(b) < THRESH
    ? 'var(--muted)'
    : `color-mix(in srgb, var(--${b > 0 ? 'up' : 'down'}) ${Math.round(Math.min(1, Math.abs(b) * k) * 55 + 45)}%, var(--panel))`

/**
 * Río principal con un afluente por agente. Cada afluente lleva el color de su conclusión
 * (verde = compra, rojo = venta, gris = neutral) y al confluir tiñe el cauce según el sesgo
 * acumulado de los agentes que ya han desembocado. Ancho del afluente = confianza.
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

  const gap = (H - 60) / Math.max(1, n - 1)
  const ys = rows.map((_, i) => (n === 1 ? YM : 30 + i * gap))
  const cx = rows.map((_, i) => XM + 20 + (i * (XE - XM - 80)) / Math.max(1, n - 1))
  let sw = 0, sb = 0
  const stops = [`<stop offset="0" style="stop-color:var(--line)"/>`]
  const tribs = rows.map((r, i) => {
    if (r.live) { sw += r.conf; sb += r.conf * r.bias }
    const cum = sw > 0 ? sb / sw : 0
    const off = ((cx[i] - XM) / (XE - XM)).toFixed(3)
    stops.push(`<stop offset="${off}" style="stop-color:${tint(cum, 1.8)}"/>`)
    const w = r.live ? 4 + r.conf * 16 : 3
    const path = `M${X0} ${ys[i]} C${X0 + (cx[i] - X0) * 0.55} ${ys[i]} ${cx[i] - 130} ${YM} ${cx[i]} ${YM}`
    const col = r.live ? tint(r.bias) : 'var(--line)'
    const dur = (7 - 4 * r.conf).toFixed(1)
    return `<g class="trib"><path d="${path}" fill="none" stroke="${col}" stroke-width="${w.toFixed(1)}" ` +
      `stroke-linecap="round" opacity=".92"${r.live ? '' : ' stroke-dasharray="4 7"'}/>` +
      (r.live ? `<path class="flow" d="${path}" fill="none" stroke="#fff" stroke-width="${(w * 0.28).toFixed(1)}" ` +
        `stroke-linecap="round" stroke-dasharray="2 26" style="animation-duration:${dur}s"/>` : '') +
      `<circle cx="${X0}" cy="${ys[i]}" r="${(w / 2 + 2).toFixed(1)}" fill="${col}"/>` +
      `<text x="${X0 - 16}" y="${ys[i] + 4}" text-anchor="end" class="rl">${esc(agentName(r.id))}</text>` +
      `<text x="${X0 + 18}" y="${ys[i] - 8}" class="rv">${r.live ? (r.bias > 0 ? '+' : '') + r.bias.toFixed(2) : 'sin datos'}</text></g>`
  }).join('')

  const ups = rows.filter((r) => r.live && r.bias >= THRESH).length
  const downs = rows.filter((r) => r.live && r.bias <= -THRESH).length
  const flat = rows.filter((r) => r.live).length - ups - downs
  const syn = simulateSynthesis(reports)
  const b = syn?.bias ?? 0
  const verdict = Math.abs(b) < THRESH ? 'Neutral' : b > 0 ? 'Sesgo de compra' : 'Sesgo de venta'
  const mainW = 26 + Math.min(1, sw / Math.max(1, n)) * 30
  const mainCol = tint(b, 1.8)
  stops.push(`<stop offset="1" style="stop-color:${mainCol}"/>`)

  el.innerHTML = `<div class="river-head"><h3>Río de decisión <span class="sim">simulada · hasta T20</span></h3>` +
    `<span class="muted">${ups} verdes · ${downs} rojos · ${flat} neutrales</span></div>` +
    `<svg viewBox="0 0 1200 ${H}" role="img" aria-label="${esc(verdict)}: ${ups} agentes en verde, ${downs} en rojo">` +
    `<defs><linearGradient id="rv" gradientUnits="userSpaceOnUse" x1="${XM}" y1="0" x2="${XE}" y2="0">${stops.join('')}</linearGradient></defs>` +
    `<path d="M${XM - 30} ${YM} L${XE} ${YM}" stroke="url(#rv)" stroke-width="${mainW.toFixed(1)}" stroke-linecap="round" fill="none"/>` +
    `<path class="flow" d="M${XM - 30} ${YM} L${XE} ${YM}" stroke="#fff" stroke-width="5" stroke-linecap="round" fill="none" stroke-dasharray="2 34" style="animation-duration:3s"/>` +
    tribs +
    `<path d="M${XE} ${YM} l30 0" stroke="${mainCol}" stroke-width="${mainW.toFixed(1)}" stroke-linecap="round" fill="none"/>` +
    `<text x="${XE + 56}" y="${YM - 6}" class="rbig" style="fill:${mainCol}">${esc(verdict)}</text>` +
    `<text x="${XE + 56}" y="${YM + 22}" class="rv">${syn ? (b > 0 ? '+' : '') + b.toFixed(2) : '—'} · acuerdo ${syn ? Math.round(syn.agreement * 100) : 0}%</text></svg>`
}
