/** Pestaña «Señales en vivo» (T48c): cada decisión en tiempo real, su estado en la evaluación
 *  sombra y qué hizo cada perfil con ella y por qué. */
import { PROFILE_VAR } from './paper_chart'
import { CAUSE, esc, getPaper, hm, px, REASON, rr, side, utc } from './paper_fmt'
import type { LiveDecision, LiveFeed } from './paper_types'

interface Ctx { symbol: string; names: Record<string, string>; profiles: { id: string; name: string }[] }

const SHADOW: Record<string, string> = {
  ABIERTA: 'Abierta', PENDIENTE: 'Pendiente', CERRADA: 'Cerrada', CANCELADA: 'Cancelada', RECHAZADA: 'Precio ya fuera',
}

function shadowCell(d: LiveDecision): string {
  let detail = ''
  if (d.status === 'ABIERTA') detail = `${rr(d.r)} a la marca ${d.mark === null ? '—' : px(d.mark)}`
  else if (d.status === 'CERRADA') detail = `${REASON[d.reason] ?? d.reason} · ${rr(d.r)}` + (d.cause ? ` · ${esc(CAUSE[d.cause] ?? d.cause)}` : '')
  else if (d.status === 'PENDIENTE') detail = d.kind === 'limit' ? 'orden límite esperando precio' : 'entra a la apertura siguiente'
  else if (d.status === 'CANCELADA') detail = REASON[d.reason] ?? d.reason
  const tone = d.r === null ? '' : d.r > 0 ? 'up' : d.r < 0 ? 'down' : ''
  return `<span class="pp-sh" data-s="${d.status}">${SHADOW[d.status] ?? d.status}</span><br><small class="${tone}">${detail}</small>`
}

export class PaperLive {
  private ctx: Ctx = { symbol: 'BTCUSDT', names: {}, profiles: [] }
  private abort: AbortController | null = null

  constructor(private el: HTMLElement) {}

  async show(ctx: Ctx): Promise<void> {
    this.ctx = ctx
    this.abort?.abort(); this.abort = new AbortController()
    try {
      const f = await getPaper<LiveFeed>(`/live?symbol=${ctx.symbol}&limit=150`, this.abort.signal)
      this.el.innerHTML = this.render(f)
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      this.el.innerHTML = `<p class="alert bad">No se pudieron leer las señales en vivo: ${esc((e as Error).message)}</p>`
    }
  }

  private render(f: LiveFeed): string {
    const byTf: Record<string, number> = {}
    for (const c of f.candles) byTf[c.timeframe] = (byTf[c.timeframe] ?? 0) + 1
    const st = f.status
    const sum = `<div class="pp-live-sum"><span><b>${f.candles_total}</b> velas analizadas en vivo</span>` +
      `<span><b>${f.total}</b> señales · sombra: ${st.ABIERTA ?? 0} abiertas · ${st.PENDIENTE ?? 0} pendientes · ` +
      `${st.CERRADA ?? 0} cerradas · ${st.CANCELADA ?? 0} canceladas</span>` +
      this.ctx.profiles.map((p) => {
        const x = f.profiles[p.id]
        const why = x?.top_reasons.map(([k, n]) => `${esc(k)} ${n}`).join(', ')
        return `<span class="pp-ls-prof"><i style="background:var(${PROFILE_VAR[p.id] ?? '--accent'})"></i><b>${esc(p.name)}</b>: ` +
          `tomó ${x?.taken ?? 0} · rechazó ${x?.actions.rechazada ?? 0}${why ? ` <small class="muted">(${why})</small>` : ''}</span>`
      }).join('') + '</div>'
    const candles = f.candles.slice(0, 24).map((c) =>
      `<span class="pp-lc" data-n="${c.signals ? 1 : 0}"><b>${hm(c.t)}</b> ${esc(c.timeframe)} · ${c.signals ? `${c.signals} señal${c.signals > 1 ? 'es' : ''}` : 'sin señales'}</span>`).join('')
    if (!f.total) {
      return sum + `<p class="muted">Aún no hay señales decididas en vivo. El servicio analiza cada vela al cerrar (15 m, 1 h y 4 h); ` +
        'cuando una estrategia propone una operación aparece aquí con su estado y lo que hizo cada perfil.</p>' +
        (candles ? `<div class="pp-lcs">${candles}</div>` : '')
    }
    const heads = this.ctx.profiles.map((p) => `<th>${esc(p.name)}</th>`).join('')
    const rows = f.decisions.map((d) => {
      const name = (this.ctx.names[d.sid] ?? d.strategy).split(' · ')[0]
      const profs = this.ctx.profiles.map((p) => {
        const a = d.profiles[p.id]
        if (!a) return '<td>—</td>'
        const pnl = typeof a.pnl === 'number' ? ` · ${a.pnl > 0 ? '+' : ''}${a.pnl.toFixed(2)} USDT` : ''
        return `<td><span class="pp-act" data-a="${a.action}">${esc(a.label)}</span><br><small class="muted">${esc(a.text)}${pnl}</small></td>`
      }).join('')
      return `<tr><td class="num">${utc(d.t)}</td>` +
        `<td><b>${esc(name)}</b> <span class="pp-tfb">${esc(d.timeframe)}</span><br><small class="muted" title="${esc(d.why.join(' · '))}">${esc(d.why[0] ?? '')}</small></td>` +
        `<td>${side(d.side)}<br><small class="muted">${d.kind === 'limit' ? 'límite' : 'mercado'} · R:B ${d.rr.toFixed(2)}</small></td>` +
        `<td class="num">${px(d.fill ?? d.entry)}<br><small><span class="down">${px(d.sl)}</span> / <span class="up">${px(d.tp)}</span></small></td>` +
        `<td>${shadowCell(d)}</td>${profs}</tr>`
    }).join('')
    return sum + `<div class="pp-lcs">${candles}</div>` +
      `<div class="pp-scroll"><table class="pp-t pp-live-t"><thead><tr><th>Decisión (COT)</th><th>Estrategia</th><th>Lado</th>` +
      `<th>Entrada / SL / TP</th><th>Evaluación sombra</th>${heads}</tr></thead><tbody>${rows}</tbody></table></div>` +
      '<p class="muted pp-note">La <b>evaluación sombra</b> simula TODAS las señales con precios reales y costos, sin capital: así se mide cada estrategia ' +
      'aunque ningún perfil la tome. Cada <b>perfil</b> solo abre las que pasan sus filtros (costo, tendencia del marco mayor, estrategia no pausada…); ' +
      'si una estrategia en pausa vuelve a ganar en la sombra, se reactiva sola. Se actualiza cada minuto.</p>'
  }
}
