/** Vistas de mercado (antes pestañas; desde T185, lupa de su esfera en el río): VWAP por periodos y
 * multi-activo (lupa del intermercado). El backtest/VRM salió: lo vivo manda (T182). */
import { LineSeries, LineStyle, type UTCTimestamp } from 'lightweight-charts'
import { PriceChart } from './chart'
import { cssVar } from './theme'
import { esc, fmt, focusAssets, getMore, sourceLine, type Json } from './more_api'

export interface Ctx { symbol: string; tf: string }

const sec = (ms: number): UTCTimestamp => Math.floor(ms / 1000) as UTCTimestamp
const bar = (c: Json): Json => ({ time: sec(c.t), open: c.o, high: c.h, low: c.l, close: c.c })
let charts: PriceChart[] = []
export const disposeCharts = (): void => { charts.forEach((c) => c.destroy()); charts = [] }

function newChart(el: HTMLElement): PriceChart {
  const c = new PriceChart(el)
  charts.push(c)
  return c
}

const PERIOD_ORDER = ['daily', 'weekly', 'quincenal', 'monthly']

export async function vwapView(el: HTMLElement, ctx: Ctx): Promise<void> {
  const j = await getMore('vwap-periods', { symbol: ctx.symbol, tf: ctx.tf, n: 500 })
  const rows = PERIOD_ORDER.map((p) => {
    const c = j.current[p]
    return `<tr><td>${esc(c.label)}</td><td>${fmt(c.vwap)}</td><td>${esc(c.position)}</td>
      <td>${fmt(c.slope_pct, 3)}%</td><td>${c.partial ? 'parcial: la ventana no cubre el período' : ''}</td></tr>`
  }).join('')
  el.innerHTML = `<div class="msrc">${sourceLine(j.source, j.coverage)} · ${esc(ctx.symbol)} ${esc(ctx.tf)} · cierre ${fmt(j.close)}</div>
    <div class="mrow"><div class="seg" id="vp-seg">${PERIOD_ORDER.map((p) =>
      `<button data-p="${p}" aria-pressed="${p === 'daily'}">${esc(j.current[p].label)}</button>`).join('')}</div>
      <span class="muted">línea sólida = VWAP · discontinua = ±1σ · punteada = ±2σ</span></div>
    <div class="mchart" id="vp-chart"></div>
    <table class="mt"><tr><th>Período</th><th>VWAP</th><th>Posición</th><th>Pendiente</th><th>Aviso</th></tr>${rows}</table>`
  const pc = newChart(el.querySelector<HTMLElement>('#vp-chart')!)
  pc.series.setData(j.candles.map(bar))
  const lines = [
    ['vwap', cssVar('--accent'), LineStyle.Solid], ['u1', cssVar('--muted'), LineStyle.Dashed],
    ['l1', cssVar('--muted'), LineStyle.Dashed], ['u2', cssVar('--warn'), LineStyle.Dotted],
    ['l2', cssVar('--warn'), LineStyle.Dotted],
  ] as const
  const sers = lines.map(([, color, lineStyle]) => pc.chart.addSeries(LineSeries, {
    color, lineStyle, lineWidth: 1, priceLineVisible: false, lastValueVisible: false }))
  const paint = (p: string): void => lines.forEach(([k], i) => sers[i].setData(
    j.series[p].filter((r: Json) => r[k] !== null).map((r: Json) => ({ time: sec(r.t), value: r[k] }))))
  paint('daily')
  el.querySelector<HTMLElement>('#vp-seg')!.onclick = (e) => {
    const b = (e.target as HTMLElement).closest('button')
    if (!b) return
    el.querySelectorAll('#vp-seg button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)))
    paint(b.dataset.p!)
  }
}

export async function multiAssetView(el: HTMLElement): Promise<void> {
  const assets = focusAssets((await getMore('assets', {})).assets)
  el.innerHTML = `<div class="mrow"><label>Activo <select id="ma-a">${assets.map((a: Json) =>
    `<option value="${esc(a.key)}">${esc(a.label)}</option>`).join('')}</select></label>
    <label>Marco <select id="ma-t"></select></label><span id="ma-src" class="msrc"></span></div>
    <div class="mchart" id="ma-chart"></div>`
  const selA = el.querySelector<HTMLSelectElement>('#ma-a')!
  const selT = el.querySelector<HTMLSelectElement>('#ma-t')!
  const mc = newChart(el.querySelector<HTMLElement>('#ma-chart')!)
  const fillTf = (): void => {
    const a = assets.find((x: Json) => x.key === selA.value)
    selT.innerHTML = a.intervals.map((t: string) => `<option>${esc(t)}</option>`).join('')
  }
  const load = async (): Promise<void> => {
    const src = el.querySelector<HTMLElement>('#ma-src')!
    src.textContent = 'Cargando…'
    try {
      const j = await getMore('multi-asset', { asset: selA.value, tf: selT.value, n: 300 })
      mc.series.setData(j.candles.map(bar))
      mc.chart.timeScale().fitContent()
      src.innerHTML = `${sourceLine(j.source, j.coverage)} · ${j.bars} velas`
    } catch (e) { src.innerHTML = `<span class="down">${esc((e as Error).message)}</span>` }
  }
  selA.onchange = () => { fillTf(); void load() }
  selT.onchange = () => void load()
  fillTf(); await load()
}
