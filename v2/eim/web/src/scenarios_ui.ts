import { fetchForecast } from './api'
import type { PriceChart } from './chart'
import { SCEN_LABEL, scenColor } from './scenarios'
import { esc } from './panels'
import type { Candle, ForecastSet, ScenarioId } from './types'

const HORIZONS = [20, 25, 30]
const WEEK_MS = 7 * 86_400_000

/** Pestaña "Escenarios": selector de horizonte, interruptor de velas, avisos y tarjetas. */
export class ScenarioPanel {
  private fs: ForecastSet | null = null
  private last: Candle | null = null
  private sel: ScenarioId | null = null
  private candles = false
  private horizon = 25
  private err = ''
  private abort: AbortController | null = null
  private key = ''
  private roomFor = ''

  constructor(private readonly el: HTMLElement, private readonly chart: PriceChart,
    private readonly ctx: () => { symbol: string; tf: string }) {
    el.onclick = (e) => {
      const t = e.target as HTMLElement
      const card = t.closest<HTMLElement>('.scen')
      if (card) {
        const id = card.dataset.id as ScenarioId
        this.sel = this.sel === id ? null : id
        this.apply()
      } else if (t.closest('#scen-candles')) { this.candles = !this.candles; this.apply() }
    }
    el.onchange = (e) => {
      const t = e.target as HTMLSelectElement
      if (t.id === 'scen-h') { this.horizon = Number(t.value); void this.reload() }
    }
  }

  setLast(c: Candle | null): void { this.last = c }

  /** Cambio de símbolo/marco u horizonte: vuelve a pedir el pronóstico. */
  async reload(): Promise<void> {
    this.abort?.abort(); this.abort = new AbortController()
    const { symbol, tf } = this.ctx()
    const key = `${symbol}|${tf}`
    if (key !== this.key) { this.key = key; this.fs = null; this.sel = null; this.chart.scen.set(null, null) }
    try {
      this.fs = await fetchForecast(symbol, tf, this.horizon, this.abort.signal)
      this.err = ''
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      this.fs = null; this.err = `No hay pronóstico disponible (${(e as Error).message}).`
    }
    this.apply()
  }

  /** Pronóstico recibido por el stream al cerrar la vela. */
  push(fs: ForecastSet, last: Candle | null): void {
    const { symbol, tf } = this.ctx()
    if (fs.symbol !== symbol || fs.timeframe !== tf || fs.horizon_bars !== this.horizon) return
    if (last) this.last = last
    this.fs = fs; this.err = ''; this.apply()
  }

  fail(detail: string): void {
    this.fs = null; this.err = `Sin pronóstico: ${detail}`; this.apply()
  }

  private apply(): void {
    const rk = `${this.key}|${this.horizon}`
    if (this.fs && rk !== this.roomFor) { this.roomFor = rk; this.chart.makeRoom(this.fs.horizon_bars) }
    this.chart.scen.set(this.fs, this.last)
    this.chart.scen.setView(this.sel, this.candles)
    this.render()
  }

  private notices(fs: ForecastSet): string[] {
    const n = [...fs.warnings]
    if (fs.engine === fs.baseline_engine) {
      n.push(`El motor «${fs.engine}» es la línea base: no hay evidencia de que la supere (se evalúa en T16/T19).`)
    }
    const first = fs.scenarios[0]?.candles[0]
    if (this.last && first && first.t - this.last.t > WEEK_MS) {
      n.push('El pronóstico no parte de la vela actual: cobertura de datos incompleta o desactualizada.')
    }
    return n
  }

  private render(): void {
    const bar = '<div class="scen-bar"><label>Velas a proyectar <select id="scen-h">' +
      HORIZONS.map((h) => `<option${h === this.horizon ? ' selected' : ''}>${h}</option>`).join('') +
      `</select></label><button id="scen-candles" aria-pressed="${this.candles}">Ver escenario como velas</button>` +
      (this.candles ? `<span class="muted">Velas simuladas de «${SCEN_LABEL[this.sel ?? 'neutral']}» — ` +
        'elige una tarjeta para cambiar de escenario.</span>' : '') + '</div>'
    if (!this.fs) {
      this.el.innerHTML = bar + `<p class="muted">${esc(this.err || 'Cargando escenarios…')}</p>`
      return
    }
    const fs = this.fs
    const warn = this.notices(fs).map((w) => `<p class="scen-warn" role="alert">⚠ ${esc(w)}</p>`).join('')
    const total = fs.scenarios.reduce((a, s) => a + s.probability, 0)
    const cards = fs.scenarios.map((s) => {
      const on = this.sel === s.id
      return `<button class="scen" data-id="${s.id}" aria-pressed="${on}" data-dim="${this.sel != null && !on}" ` +
        `style="--c:${scenColor(s.id)}"><h4><span>${SCEN_LABEL[s.id]}</span>` +
        `<span class="num">${(s.probability * 100).toFixed(0)}%</span></h4>` +
        `<p>${esc(s.narrative)}</p><p><b>Invalidación:</b> ${esc(s.invalidation.condition)}</p>` +
        `<p class="meta">motor ${esc(s.engine)} · n_paths ${s.n_paths} · simulado</p></button>`
    }).join('')
    this.el.innerHTML = bar + warn + `<div class="scen-cards">${cards}</div>` +
      `<p class="muted meta">Suma de probabilidades: ${(total * 100).toFixed(0)}% · ` +
      `hecho ${new Date(fs.made_at).toISOString().slice(0, 16).replace('T', ' ')} UTC · ` +
      `${fs.horizon_bars} velas · proyección estadística simulada, no una predicción.</p>`
  }
}
