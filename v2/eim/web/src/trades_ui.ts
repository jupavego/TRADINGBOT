import { createSeriesMarkers, type ISeriesMarkersPluginApi, type SeriesMarker, type Time, type UTCTimestamp } from 'lightweight-charts'
import type { PriceChart } from './chart'
import { cssVar } from './theme'
import type { Decision, Trade } from './types'

const sec = (t: number): UTCTimestamp => Math.floor(t / 1000) as UTCTimestamp
const fmtR = (r: number): string => `${r >= 0 ? '+' : ''}${r.toFixed(2)}R`
const esc = (s: string): string => s.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`)
const hhmm = (t: number): string => new Date(t).toISOString().slice(0, 16).replace('T', ' ')
const EXIT: Record<string, string> = { SL: 'SL', TP1: 'TP1', TP2: 'TP2', INVALIDADO: 'Inval.', EXPIRADO: 'Exp.' }

/** Marcadores de operaciones simuladas sobre el gráfico: entrada, salida y resultado en R. */
export class TradeMarks {
  private plugin: ISeriesMarkersPluginApi<Time>
  constructor(pc: PriceChart) {
    this.plugin = createSeriesMarkers(pc.series, [])
  }

  set(trades: Trade[]): void {
    const up = cssVar('--up'), down = cssVar('--down'), muted = cssVar('--muted')
    const ms: SeriesMarker<UTCTimestamp>[] = []
    for (const t of trades) {
      const long = t.side > 0
      ms.push({
        time: sec(t.entry_t), position: long ? 'belowBar' : 'aboveBar', shape: long ? 'arrowUp' : 'arrowDown',
        color: long ? up : down, text: `${long ? 'Largo' : 'Corto'} (sim)`,
      })
      if (t.exit_t !== null && t.r !== null) {
        ms.push({
          time: sec(t.exit_t), position: long ? 'aboveBar' : 'belowBar', shape: 'circle',
          color: t.r >= 0 ? up : t.status === 'SL' ? down : muted,
          text: `${EXIT[t.status] ?? t.status} ${fmtR(t.r)}`,
        })
      }
    }
    ms.sort((a, b) => (a.time as number) - (b.time as number))
    this.plugin.setMarkers(ms)
  }
}

/** Pestaña Bitácora: operaciones simuladas y decisiones del agente con su evidencia. */
export function renderLog(el: HTMLElement, trades: Trade[], decisions: Decision[]): void {
  const net = trades.reduce((s, t) => s + (t.r ?? 0), 0)
  const closed = trades.filter((t) => t.r !== null)
  const head = `<p class="muted"><b>Modo: Simulado</b> — sin exchange ni órdenes. ` +
    `${closed.length} operaciones cerradas · neto ${fmtR(net)} · comisiones y funding supuestos ` +
    `(${esc(trades[0]?.funding_source ?? 'constante')}).</p>`
  const tr = trades.length
    ? '<table class="log"><thead><tr><th>Entrada (UTC)</th><th>Lado</th><th>Entrada</th><th>SL</th>' +
      '<th>TP1</th><th>Estado</th><th>Salida</th><th>Resultado</th><th>Evidencia</th></tr></thead><tbody>' +
      trades.map((t) => `<tr><td>${hhmm(t.entry_t)}</td><td>${t.side > 0 ? 'Largo' : 'Corto'}</td>` +
        `<td class="num">${t.entry.toFixed(2)}</td><td class="num">${t.sl0.toFixed(2)}</td>` +
        `<td class="num">${t.tp1.toFixed(2)}</td><td><span class="chip">${t.status}</span></td>` +
        `<td class="num">${t.exit === null ? '—' : t.exit.toFixed(2)}</td>` +
        `<td class="num">${t.r === null ? '—' : fmtR(t.r)}</td>` +
        `<td class="muted">${esc(t.evidence[0] ?? '')}</td></tr>`).join('') + '</tbody></table>'
    : '<p class="muted">Sin operaciones simuladas todavía.</p>'
  const dec = decisions.length
    ? '<h4>Decisiones del agente de plan</h4><table class="log"><thead><tr><th>Hora (UTC)</th>' +
      '<th>Decisión</th><th>Conf.</th><th>Evidencia</th></tr></thead><tbody>' +
      decisions.slice(0, 60).map((d) => `<tr><td>${hhmm(d.asof)}</td><td>${esc(d.action)}</td>` +
        `<td class="num">${Math.round(d.confidence * 100)}%</td>` +
        `<td class="muted">${esc(d.evidence.join(' · '))}</td></tr>`).join('') + '</tbody></table>'
    : ''
  el.innerHTML = head + tr + dec
}
