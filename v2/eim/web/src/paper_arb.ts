/** Bróker simulado → «Arbitraje» (T45): pruebas del ejecutor de dos patas en modo Simulado sobre
 * velas y funding reales de Binance, sin cuenta. Gráfico spot/perpetuo con cada orden marcada. */
import {
  ColorType, createChart, createSeriesMarkers, LineSeries,
  type IChartApi, type ISeriesApi, type SeriesMarker, type UTCTimestamp,
} from 'lightweight-charts'
import { base } from './api'
import { esc, nf, px, usd, utc } from './paper_fmt'
import { cssVar } from './theme'
import './paper_arb.css'
import { chartTimeLocale } from './tz'

interface Check { label: string; ok: boolean; detail: string }
interface Order { t: number; market: string; side: number; role: string; qty: number; filled: number; avg: number | null; status: string; price: number | null }
interface Scenario {
  id: string; title: string; ok: boolean; t0: number; t1: number; checks: Check[]; orders: Order[]
  position: { funding_received: number; funding_expected: number; funding_n: number; incident_loss: number; exit_reason: string } | null
  pnl?: number | null; pnl_before_close?: number | null; fees_usd?: number; settlements?: number; note?: string
}
interface Report {
  mode: string; symbol: string; config: string; notional: number; ok: boolean; window: [number, number]; generated_at?: number
  series: { spot: [number, number][]; futures: [number, number][]; funding: [number, number][] }
  sources: Record<string, string>; scenarios: Scenario[]; assumptions: string[]
}

const ROLE: Record<string, string> = { abrir: 'abrir', cubrir: 'cubrir', deshacer: 'deshacer', 'deshacer mercado': 'deshacer', cerrar: 'cerrar', recortar: 'recortar', mercado: 'mercado', rebalanceo: 'rebal.' }
const MARKET: Record<string, string> = { spot: 'Spot', usdm: 'Perpetuo' }
const STATUS: Record<string, string> = { FILLED: 'Llenada', REJECTED: 'Rechazada', CANCELED: 'Cancelada', EXPIRED: 'Expirada', PARTIALLY_FILLED: 'Parcial', NEW: 'Abierta' }
const sec = (t: number): UTCTimestamp => (Math.floor(t / 3_600_000) * 3600) as UTCTimestamp   // a la vela de 1 h

export class PaperArb {
  private rep: Report | null = null
  private err = ''
  private busy = false
  private loaded = false
  private chart: IChartApi | null = null
  private spot: ISeriesApi<'Line'> | null = null
  private fut: ISeriesApi<'Line'> | null = null

  constructor(private readonly el: HTMLElement) {
    el.addEventListener('click', (e) => { if ((e.target as HTMLElement).closest('[data-pa="run"]')) void this.run() })
  }

  async show(): Promise<void> {
    if (!this.loaded) {
      this.loaded = true
      try {
        const r = await fetch(`${base()}/v2/paper/arbitrage`)
        if (!r.ok) throw new Error(r.statusText)
        this.rep = ((await r.json()) as { report: Report | null }).report
      } catch (e) { this.err = `No se pudo leer el informe: ${(e as Error).message}` }
    }
    this.render()
  }

  private async run(): Promise<void> {
    if (this.busy) return
    const hold = this.el.querySelector<HTMLSelectElement>('[data-pa="hold"]')?.value ?? '48'
    this.busy = true; this.render()
    try {
      const r = await fetch(`${base()}/v2/paper/arbitrage/run?hold_h=${hold}`, { method: 'POST', headers: { 'X-EIM-Confirm': 'paper-arb' } })
      const body = await r.json().catch(() => ({ detail: r.statusText }))
      if (!r.ok) throw new Error(String((body as { detail?: string }).detail ?? r.statusText))
      this.rep = (body as { report: Report }).report; this.err = ''
    } catch (e) { this.err = (e as Error).message }
    this.busy = false
    this.render()
  }

  private head(r: Report | null): string {
    const hold = r?.scenarios[0] ? Math.round((r.scenarios[0].t1 - r.scenarios[0].t0) / 3_600_000) : 48
    const opt = (h: number): string => `<option value="${h}"${h === hold ? ' selected' : ''}>${h} h</option>`
    return `<div class="pa-head"><b>Pruebas del arbitraje</b>` +
      `<span class="mode" data-mode="SIMULADO">Modo: Simulado · sin cuenta de Binance</span>` +
      `<label>Carry abierto <select data-pa="hold">${[24, 48, 72, 120].map(opt).join('')}</select></label>` +
      `<button class="btn" data-pa="run"${this.busy ? ' disabled' : ''}>${this.busy ? 'Ejecutando…' : 'Ejecutar pruebas'}</button>` +
      (r ? `<small class="muted">${r.generated_at ? `corrida ${utc(r.generated_at)} COT · ` : ''}${esc(r.symbol)} · velas 1 h ` +
        `${utc(r.window[0])} → ${utc(r.window[1])} COT · ${esc(r.config)} · ${nf(r.notional, 0)} USD por arbitraje</small>` : '') +
      '</div>'
  }

  private card(s: Scenario, i: number): string {
    const p = s.position
    const facts = s.id === 'carry' && p
      ? `<p class="pa-facts">Funding real <b>${usd(p.funding_received, 4)}</b> USD en ${p.funding_n} liquidaciones · esperado ${usd(p.funding_expected, 4)} · ` +
        `comisiones ${nf(s.fees_usd ?? 0, 2)} USD · resultado al cerrar <b class="${(s.pnl ?? 0) >= 0 ? 'up' : 'down'}">${usd(s.pnl ?? 0)}</b> USD</p>` +
        (s.note ? `<p class="muted pa-note">${esc(s.note)}</p>` : '')
      : p && p.incident_loss ? `<p class="pa-facts">Pérdida de la pata incompleta <b class="down">${usd(-p.incident_loss, 4)}</b> USD · ${esc(p.exit_reason)}</p>` : ''
    const rows = s.orders.map((o) =>
      `<tr><td>${utc(o.t)}</td><td>${MARKET[o.market] ?? esc(o.market)}</td><td class="${o.side > 0 ? 'up' : 'down'}">${o.side > 0 ? 'Compra' : 'Venta'}</td>` +
      `<td>${esc(o.role)}</td><td class="num">${o.filled.toFixed(5)} / ${o.qty.toFixed(5)}</td><td class="num">${o.avg ? px(o.avg) : '—'}</td>` +
      `<td data-st="${esc(o.status)}">${STATUS[o.status] ?? esc(o.status)}</td></tr>`).join('')
    return `<article class="pa-card" data-ok="${s.ok}"><h4>${i + 1}. ${esc(s.title)} <span>${s.ok ? '✔ superada' : '✖ fallida'}</span></h4>` +
      `<ul class="pa-checks">${s.checks.map((c) => `<li data-ok="${c.ok}">${c.ok ? '✔' : '✖'} ${esc(c.label)}${c.detail ? `<small>${esc(c.detail)}</small>` : ''}</li>`).join('')}</ul>` +
      facts + (rows ? `<details class="pa-orders"><summary>${s.orders.length} órdenes</summary><div class="pp-scroll"><table class="tbl">` +
      `<thead><tr><th>Hora COT</th><th>Mercado</th><th>Lado</th><th>Rol</th><th>Llenado / pedido</th><th>Precio medio</th><th>Estado</th></tr></thead>` +
      `<tbody>${rows}</tbody></table></div></details>` : '') + '</article>'
  }

  render(): void {
    const r = this.rep
    const err = this.err ? `<p class="down">${esc(this.err)}</p>` : ''
    if (!r) {
      this.el.innerHTML = this.head(null) + err + '<p class="muted">Aún no hay pruebas. «Ejecutar pruebas» abre, mantiene y cierra un carry de funding, provoca una pata fallida y un corte de red ' +
        'con el mismo ejecutor, riesgo y reconciliación de la testnet, sobre un exchange simulado con precios reales.</p>'
      this.chart?.remove(); this.chart = null
      return
    }
    const passed = r.scenarios.filter((s) => s.ok).length
    this.el.innerHTML = this.head(r) + err +
      `<p class="pa-verdict" data-ok="${r.ok}">${r.ok ? '✔' : '✖'} ${passed} de ${r.scenarios.length} escenarios superados</p>` +
      '<div class="pa-chart"><div class="pa-leg"><span><i data-s="spot"></i>Spot</span><span><i data-s="fut"></i>Perpetuo</span>' +
      '<small class="muted">▲ compra · ▼ venta · ● rechazada — el número es el escenario</small></div><div class="pa-pc" data-pa="pc"></div></div>' +
      `<div class="pa-grid">${r.scenarios.map((s, i) => this.card(s, i)).join('')}</div>` +
      `<details class="pa-assume"><summary>Supuestos y fuentes</summary><ul>${r.assumptions.map((a) => `<li>${esc(a)}</li>`).join('')}` +
      `${Object.entries(r.sources).map(([k, v]) => `<li>${esc(k)}: ${esc(v)}</li>`).join('')}</ul></details>`
    this.paintChart(r)
  }

  private paintChart(r: Report): void {
    this.chart?.remove()
    const el = this.el.querySelector<HTMLElement>('[data-pa="pc"]')!
    this.chart = createChart(el, {
      autoSize: true, localization: chartTimeLocale.localization,
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: cssVar('--line'), ...chartTimeLocale.timeScale },
      rightPriceScale: { borderColor: cssVar('--line') },
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, fontFamily: 'inherit', fontSize: 11, textColor: cssVar('--muted') },
      grid: { vertLines: { visible: false }, horzLines: { color: cssVar('--grid') } },
    })
    const cSpot = cssVar('--accent'), cFut = cssVar('--warn')
    this.spot = this.chart.addSeries(LineSeries, { color: cSpot, lineWidth: 2, priceLineVisible: false, title: 'Spot' })
    this.fut = this.chart.addSeries(LineSeries, { color: cFut, lineWidth: 2, priceLineVisible: false, title: 'Perpetuo' })
    this.spot.setData(r.series.spot.map(([t, v]) => ({ time: sec(t), value: v })))
    this.fut.setData(r.series.futures.map(([t, v]) => ({ time: sec(t), value: v })))
    const ms: Record<string, SeriesMarker<UTCTimestamp>[]> = { spot: [], usdm: [] }
    r.scenarios.forEach((s, i) => {
      for (const o of s.orders) {
        const rej = o.status === 'REJECTED'
        if (!rej && o.filled <= 0) continue
        const buy = o.side > 0
        ms[o.market]?.push({
          time: sec(o.t), position: buy ? 'belowBar' : 'aboveBar', shape: rej ? 'circle' : buy ? 'arrowUp' : 'arrowDown',
          color: rej ? cssVar('--muted') : buy ? cssVar('--up') : cssVar('--down'), text: `${i + 1}·${ROLE[o.role] ?? o.role}${rej ? ' ✖' : ''}`,
        })
      }
    })
    /** Ordena por hora y agrupa marcas iguales en la misma vela (p. ej. tres rechazos → «×3»). */
    const sort = (a: SeriesMarker<UTCTimestamp>[]): SeriesMarker<UTCTimestamp>[] => {
      const g = new Map<string, { m: SeriesMarker<UTCTimestamp>; n: number }>()
      for (const m of a) {
        const k = `${m.time}|${m.text}|${m.shape}`
        const x = g.get(k)
        if (x) x.n += 1; else g.set(k, { m, n: 1 })
      }
      return [...g.values()].map(({ m, n }) => (n > 1 ? { ...m, text: `${m.text} ×${n}` } : m)).sort((x, y) => x.time - y.time)
    }
    createSeriesMarkers(this.spot, sort(ms.spot))
    createSeriesMarkers(this.fut, sort(ms.usdm))
    this.chart.timeScale().fitContent()
    this.el.querySelector<HTMLElement>('i[data-s="spot"]')!.style.background = cSpot
    this.el.querySelector<HTMLElement>('i[data-s="fut"]')!.style.background = cFut
  }
}
