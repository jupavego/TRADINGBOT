/** Pestañas de mercado de "Más análisis": Backtest/VRM, VWAP por periodos y Multi-activo. */
import { LineSeries, LineStyle, type UTCTimestamp } from 'lightweight-charts'
import { PriceChart } from './chart'
import { cssVar } from './theme'
import { esc, fmt, getMore, sourceLine, type Json } from './more_api'

export interface Ctx { symbol: string; tf: string }

const sec = (ms: number): UTCTimestamp => Math.floor(ms / 1000) as UTCTimestamp
const bar = (c: Json): Json => ({ time: sec(c.t), open: c.o, high: c.h, low: c.l, close: c.c })
let charts: PriceChart[] = []
export const disposeCharts = (): void => { charts.forEach((c) => c.destroy()); charts = [] }
export const restyleCharts = (): void => charts.forEach((c) => c.restyle())

function newChart(el: HTMLElement): PriceChart {
  const c = new PriceChart(el)
  charts.push(c)
  return c
}

const STATUS_CLS: Record<string, string> = { PASS: 'up', FAIL: 'down', NO_EVALUADO: 'warn' }

export async function backtestView(el: HTMLElement, ctx: Ctx): Promise<void> {
  el.innerHTML = `<div class="mrow">
    <label>Velas <input id="bt-n" type="number" value="1000" min="450" max="20000"></label>
    <label>Horizonte <input id="bt-h" type="number" value="6" min="1" max="100"></label>
    <button class="btn" id="bt-run">Ejecutar backtest</button>
    <span class="muted">${esc(ctx.symbol)} ${esc(ctx.tf)} · protocolo EIM-VRM-001 · sobre el almacén local</span>
  </div><div id="bt-out" class="muted">Pulsa «Ejecutar backtest».</div>`
  const out = el.querySelector<HTMLElement>('#bt-out')!
  el.querySelector<HTMLButtonElement>('#bt-run')!.onclick = async () => {
    out.textContent = 'Calculando…'
    try {
      const j = await getMore('backtest', {
        symbol: ctx.symbol, tf: ctx.tf,
        candles: el.querySelector<HTMLInputElement>('#bt-n')!.value,
        horizon: el.querySelector<HTMLInputElement>('#bt-h')!.value,
      })
      out.innerHTML = renderBacktest(j)
    } catch (e) { out.innerHTML = `<div class="alert bad">${esc((e as Error).message)}</div>` }
  }
}

function renderBacktest(m: Json): string {
  const ca = m.acceptance_criteria
  const sc = Object.entries(m['MET-002_accuracy_by_scenario'] as Record<string, number | null>)
    .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v === null ? 'sin muestras' : `${fmt(v)}%`}</td></tr>`).join('')
  const crit = Object.entries(ca.criteria as Record<string, Json>).map(([k, c]) => {
    const r = c.result === null ? '—' : esc(typeof c.result === 'object' ? JSON.stringify(c.result) : c.result)
    return `<tr><td>${esc(k)}</td><td>${esc(c.criticidad)}</td><td>${esc(c.threshold)}</td><td>${r}</td>
      <td class="${STATUS_CLS[c.status] ?? ''}">${esc(c.status)}</td></tr>`
  }).join('')
  const na = Object.entries(m.not_evaluated as Record<string, string>)
    .map(([k, v]) => `<li><b>${esc(k)}</b>: ${esc(v)}</li>`).join('')
  return `<div class="msrc">${sourceLine(m.source, m.coverage)} · ${m.bars} velas · horizonte ${m.horizon}</div>
  <div class="kpi-row">
    <div class="kpi"><b>${fmt(m['MET-001_accuracy_global'])}%</b><span>MET-001 exactitud global</span></div>
    <div class="kpi"><b>${fmt(m['MET-004_calibration_error'], 4)}</b><span>MET-004 error de calibración</span></div>
    <div class="kpi"><b>${fmt(m['MET-005_stability'], 4)}</b><span>MET-005 estabilidad</span></div>
    <div class="kpi"><b>${fmt(m['MET-006_coverage_pct'])}%</b><span>MET-006 cobertura de estados</span></div>
    <div class="kpi"><b>${m['MET-008_detection_latency_p50'] ?? '—'}</b><span>MET-008 latencia (velas)</span></div>
    <div class="kpi"><b>${m.correct_diagnoses}/${m.total_evaluated}</b><span>diagnósticos correctos</span></div>
  </div>
  <div class="alert ${ca.overall_status === 'FAIL' ? 'bad' : ''}">Veredicto VRM: <b>${esc(ca.overall_status)}</b>
    ${ca.blocking_failures.length ? ` · fallos bloqueantes: ${esc(ca.blocking_failures.join(', '))}` : ''}</div>
  <div class="two"><div><h4>MET-002 · exactitud por escenario</h4><table class="mt">${sc}</table></div>
  <div><h4>Criterios de aceptación</h4><table class="mt"><tr><th>CA</th><th>Criticidad</th><th>Umbral</th><th>Resultado</th><th>Estado</th></tr>${crit}</table></div></div>
  <h4>No evaluado en esta corrida (no se inventa)</h4><ul class="muted">${na}</ul>`
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
  const { assets } = await getMore('assets', {})
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
