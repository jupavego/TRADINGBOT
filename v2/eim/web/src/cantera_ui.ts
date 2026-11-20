/** Pestaña «Cantera» (T171): escalafón por agente, honesto con la muestra. Modo SIMULADO.
 *
 * Desde el 2026-11-20 vive en la barra superior, junto al mapa del sistema, y se presenta como el
 * bróker simulado: balance de ganadas frente a perdidas, capital por agente (SVG propio, sin el
 * gráfico de TradingView) y, debajo, el escalafón.
 *
 * Vista de entrada: la panorámica por agente (cada agente con sus prospectos de un vistazo); la
 * ficha del prospecto es el detalle al que se baja. El orden es por agente y etapa, nunca por
 * rendimiento, y con menos de 30 observaciones la cifra se atenúa con «muestra insuficiente».
 * La contabilidad de la cantera es aparte: no se suma a los cuatro perfiles ni a la de T144. */
import { fetchNursery, type CanteraPanel, type NurseryPayload, type ProspectRow, type Stage } from './cantera_api'
import { canteraBalanceView } from './cantera_balance'
import { CanteraCard } from './cantera_card'
import { canteraCurveView } from './cantera_curve'
import { agentLabel, cot, mag, num, pc, rr, STAGE, usd } from './cantera_fmt'
import { esc } from './panels'

const tone = (x: number | null | undefined): string => (x == null || x === 0 ? 'flat' : x > 0 ? 'up' : 'down')
const REGIME: Record<string, string> = {
  trend_up: 'tendencia alcista', trend_down: 'tendencia bajista', range: 'rango', volatile: 'volátil', sin_etiqueta: 'sin etiqueta',
}

/** Cifra con su fuente y su cobertura al pasar el puntero; atenuada si la muestra no da. */
function fig(text: string, p: ProspectRow, src: string, t?: string): string {
  const cov = `cobertura: ${p.sample.obs} ${p.sample.unit} medidas (mínimo ${p.sample.min})`
  return `<span class="ct-fig" data-t="${t ?? 'flat'}" title="${esc(`${src} · ${cov}`)}">${text}</span>`
}

function verdict(p: ProspectRow): string {
  const v = p.verdict
  const tip = `${v.motivo}. MinTRL (T161) de la hipótesis primaria con α = 0,05/${Math.round(0.05 / v.alpha)} (z = ${num(v.z, 2)}).`
  if (v.state === 'sin_muestra') return `<span class="ct-eta" data-s="none" title="${esc(tip)}">sin estimación<small>${v.obs} obs.</small></span>`
  if (v.state === 'sin_ventaja') return `<span class="ct-eta" data-s="neg" title="${esc(tip)}">no apunta a ventaja<small>d̃ ≤ 0</small></span>`
  const late = v.beyond_deadline ? ' · más allá del plazo' : ''
  return `<span class="ct-eta" data-s="${v.beyond_deadline ? 'late' : 'ok'}" title="${esc(tip)}">≈ ${num(v.days ?? 0, 0)} días` +
    `<small>faltan ${v.remaining} de ${num(v.mintrl ?? 0, 0)} obs.${late}</small></span>`
}

function vs(p: ProspectRow): string {
  const r = p.vs.random, b = p.vs.buy_hold, s = p.vs.sibling, g = p.vs.generic
  const lines: string[] = []
  lines.push(`<li title="Gemelos aleatorios pareados (K = ${r.k}): misma vela, misma plantilla y costos; d = R − media de los gemelos">` +
    `al azar: ${fig(pc(r.diff_pct), p, 'rentabilidad propia − la de sus gemelos', tone(r.diff_pct))} <small>d ${rr(r.d_mean_r)}</small></li>`)
  if (b) {
    const own = b.own_by_side
    const split = own ? `largo ${rr(own.largo.r_sum, 1)} (${own.largo.n}) · corto ${rr(own.corto.r_sum, 1)} (${own.corto.n})` : ''
    lines.push(`<li title="${esc(`Comprar y mantener desde el alta: ${pc(b.return_pct)}; ${b.basis}`)}">comprar y mantener: ` +
      `${fig(`${rr(b.r_long, 1)} / ${rr(b.r_short, 1)}`, p, 'comprar y mantener en unidades de riesgo, largo / corto')}` +
      `<small>${split}</small></li>`)
  }
  if (s) lines.push(`<li title="Hermano simple ${esc(s.id)}: a empate asciende el simple">hermano simple: ${fig(pc(s.diff_pct), p, `rentabilidad propia − la de ${s.id}`, tone(s.diff_pct))}</li>`)
  if (g) lines.push(`<li title="Agente genérico de control ${esc(g.id)} en las mismas fechas">genérico: ${fig(pc(g.diff_pct), p, `rentabilidad propia − la de ${g.id}`, tone(g.diff_pct))}</li>`)
  return `<ul class="ct-vs">${lines.join('')}</ul>`
}

function early(p: ProspectRow): string {
  const e = p.early
  const used = e.dd_used == null ? 0 : Math.min(1, e.dd_used)
  const bar = `<i class="ct-ddbar" data-s="${used >= 0.75 ? 'hi' : used >= 0.4 ? 'mid' : 'lo'}"><b style="width:${(used * 100).toFixed(0)}%"></b></i>`
  return `<span title="${esc(`Volatilidad del R por operación y drawdown frente a su tope calibrado (${mag(e.dd_cap_pct)}): señal temprana; el retorno necesita mucha más evidencia (rec. 17)`)}">` +
    `vol ${e.vol_r == null ? '—' : num(e.vol_r, 2) + ' R'}<small>DD ${mag(e.max_dd_pct)} de ${mag(e.dd_cap_pct)}</small>${bar}</span>`
}

function row(p: ProspectRow): string {
  const thin = !p.sample.ok
  const since = p.stage === 'baja' && p.exit ? `${esc(p.exit.reason)} · ${cot(p.exit.at_ms).slice(0, 10)}` : `desde ${cot(p.stage_since_ms).slice(0, 10)}`
  const stageTip = p.exit?.motivo ?? p.criteria.map((c) => `${c.id}: ${c.motivo}`).join('\n')
  const regime = p.regime.dominant ? `${REGIME[p.regime.dominant] ?? p.regime.dominant}` : '—'
  const regTip = Object.entries(p.regime.by).map(([k, v]) => `${REGIME[k] ?? k}: ${v.n} op., d ${rr(v.d_mean)}`).join('\n')
  return `<tr class="ct-row" data-id="${esc(p.id)}" data-thin="${thin ? 1 : 0}" data-stage="${p.stage}" tabindex="0" title="Abrir la ficha del prospecto">` +
    `<td><b>${esc(p.name ?? p.id)}</b><small>${esc(p.id)} · ${p.role === 'base' ? 'base' : 'candidato'} · ${esc(p.timeframe)}</small>` +
    `<small class="ct-band">${esc(p.band.replace('_', ' '))} · se mide en ${esc(p.unit)}</small></td>` +
    `<td><span class="ct-stage" data-stage="${p.stage}" title="${esc(stageTip)}">${STAGE[p.stage] ?? p.stage}</span><small>${since}</small></td>` +
    `<td>${fig(pc(p.net_return_pct), p, 'rentabilidad neta acumulada de su cuenta (comisiones, deslizamiento y funding)', tone(p.net_return_pct))}` +
    `<small>saldo ${usd(p.balance)}</small><small>DD máx ${mag(p.max_drawdown_pct)}</small>` +
    `${thin ? `<em class="ct-thin">${esc(p.sample.label ?? '')} · ${p.sample.obs}/${p.sample.min}</em>` : ''}</td>` +
    `<td>${fig(String(p.n), p, 'operaciones cerradas y contabilizadas')}${p.open ? ` <small>+${p.open} abierta</small>` : ''}` +
    `<small>acierto ${p.hit_rate == null ? '—' : Math.round(p.hit_rate * 100) + ' %'}</small><small>costo ${usd(p.cost_paid_usd, 2)}</small></td>` +
    `<td>${vs(p)}</td>` +
    `<td title="R neto medio por operación (bruto de encogimiento) y d̃ frente a los gemelos: sin encoger y encogido hacia su tema «${esc(p.r_net.theme)}» (Bayes empírico)">` +
    `${fig(rr(p.r_net.gross_r), p, 'R neto medio por operación', tone(p.r_net.gross_r))}` +
    `<small>d̃ bruto ${rr(p.r_net.d_raw)}</small><small>d̃ encogido ${rr(p.r_net.d_shrunk)}</small></td>` +
    `<td title="${esc(regTip || 'sin operaciones con régimen')}">${esc(regime)}</td>` +
    `<td>${early(p)}</td><td>${verdict(p)}</td></tr>`
}

const COLS = '<colgroup><col style="width:15%"><col style="width:8%"><col style="width:10%"><col style="width:8%">' +
  '<col style="width:22%"><col style="width:10%"><col style="width:7%"><col style="width:10%"><col style="width:10%"></colgroup>'
const HEAD = COLS + '<thead><tr><th>Prospecto</th><th>Etapa</th><th>Rentabilidad · saldo · DD</th><th>n · acierto · costo</th>' +
  '<th>Frente a (rentabilidad)</th><th>R neto · d̃ bruto/encogido</th><th>Régimen</th><th>Señal temprana</th><th>Días hasta veredicto</th></tr></thead>'

/** Cabecera: modo, contabilidad aparte, promesas falsas que espera el azar y cobertura. */
function header(d: NurseryPayload, p: CanteraPanel): string {
  const h = p.header, fp = h.false_promises
  const stages = (Object.keys(STAGE) as Stage[]).map((s) => `<span class="ct-stage" data-stage="${s}">${STAGE[s]} ${h.stages[s] ?? 0}</span>`).join('')
  return `<div class="ct-acct" role="note"><b>Contabilidad aparte.</b> ${esc(p.accounting)}</div>` +
    `<div class="ct-meta"><div title="${esc(fp.reading)}"><b>Promesas falsas que espera el azar:</b> ${num(fp.mean, 4)} en la fase ` +
    `(P(≥ 1) = ${num(fp.p_at_least_one * 100, 2)} %; e-BH con q = ${num(fp.q, 2)} sobre m = ${h.family_m}, ${fp.sims.toLocaleString('es-CO')} simulaciones con los gemelos).</div>` +
    `<div><b>Familia:</b> ${h.members} prospectos de m = ${h.family_m} · MinTRL corregido por la familia con z = ${num(h.z_family, 2)} · ` +
    `próxima revisión ${cot(h.next_review_ms).slice(0, 10)} · plazo ${cot(h.deadline_ms).slice(0, 10)} (COT)</div>` +
    `<div class="ct-stages">${stages}</div>` +
    `<div class="muted">Alta ${cot(p.coverage.from_ms)} · ${num(p.coverage.days, 1)} días medidos · ${p.coverage.closed} operaciones cerradas` +
    ` · última ${cot(p.coverage.last_close_ms)} · pre-registro ${esc(d.prereg?.version ?? '')} (${esc((d.prereg?.sha256 ?? '').slice(0, 8))}…)` +
    ` · fuente: ${esc(p.source)}</div></div>`
}

export class CanteraPanelView {
  private data: NurseryPayload | null = null
  private err = ''
  private band = ''
  private group: 'agente' | 'banda' = 'agente'
  private period = 'todo'
  private readonly hidden = new Set<string>()
  private abort: AbortController | null = null
  private readonly card: CanteraCard

  /** Vive en su propia pestaña de la barra superior (junto al mapa del sistema). La cantera opera
   * sola en el servicio; esta vista se refresca sola cada 30 s mientras está a la vista. */
  constructor(private readonly el: HTMLElement) {
    this.card = new CanteraCard(() => this.render())
    el.addEventListener('click', (e) => {
      const t = e.target as HTMLElement
      if (t.closest('[data-ct-back]')) { this.card.close(); return }
      const bal = t.closest<HTMLElement>('[data-ct-bal]')
      if (bal?.dataset.ctBal) { this.period = bal.dataset.ctBal; this.render(); return }
      const ag = t.closest<HTMLElement>('[data-ct-agent]')
      if (ag?.dataset.ctAgent) {
        const id = ag.dataset.ctAgent
        if (this.hidden.has(id)) this.hidden.delete(id); else this.hidden.add(id)
        this.render(); return
      }
      const r = t.closest<HTMLElement>('.ct-row')
      if (r?.dataset.id) void this.card.open(r.dataset.id)
    })
    el.addEventListener('keydown', (e) => {
      const r = (e.target as HTMLElement).closest<HTMLElement>('.ct-row')
      if (r?.dataset.id && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); void this.card.open(r.dataset.id) }
    })
    el.addEventListener('change', (e) => {
      const t = e.target as HTMLSelectElement
      if (t.id === 'ct-band') { this.band = t.value; this.render() }
      if (t.id === 'ct-group') { this.group = t.value as 'agente' | 'banda'; this.render() }
    })
    window.setInterval(() => { if (!this.el.hidden && !this.card.isOpen) void this.reload() }, 30_000)
  }

  async reload(): Promise<void> {
    this.abort?.abort()
    const ac = (this.abort = new AbortController())
    try { this.data = await fetchNursery(ac.signal); this.err = '' }
    catch (e) { if (ac.signal.aborted) return; this.err = `No se pudo consultar la cantera: ${(e as Error).message}` }
    this.render()
  }

  private controls(p: CanteraPanel): string {
    const opts = p.bands.map((b) => `<option value="${b.id}"${this.band === b.id ? ' selected' : ''}>${esc(b.label)} · ${b.count} (en ${esc(b.unit)})</option>`).join('')
    return `<div class="ct-ctrl"><label>Banda de horizonte <select id="ct-band"><option value="">Todas · ${p.prospects.length}</option>${opts}</select></label>` +
      `<label>Agrupar por <select id="ct-group"><option value="agente"${this.group === 'agente' ? ' selected' : ''}>agente</option>` +
      `<option value="banda"${this.group === 'banda' ? ' selected' : ''}>banda de horizonte</option></select></label>` +
      `<span class="muted">Orden: ${esc(p.order)}. Con menos de ${p.header.min_sample} observaciones la cifra se atenúa.</span></div>`
  }

  private groups(p: CanteraPanel): string {
    const ps = p.prospects.filter((x) => !this.band || x.band === this.band)
    if (!ps.length) return '<p class="muted">Ningún prospecto en esta banda.</p>'
    const table = (rows: ProspectRow[]): string => `<div class="tablewrap"><table class="ct-table">${HEAD}<tbody>${rows.map(row).join('')}</tbody></table></div>`
    if (this.group === 'banda') {
      return p.bands.filter((b) => ps.some((x) => x.band === b.id)).map((b) =>
        `<section class="ct-group"><h4>${esc(b.label)} <small>se mide en ${esc(b.unit)}</small></h4>${table(ps.filter((x) => x.band === b.id))}</section>`).join('')
    }
    return p.agents.filter((a) => ps.some((x) => x.agent_id === a.agent_id)).map((a) => {
      const gen = a.generic.map((g) => `<span title="${esc(g.account)}">${esc(g.account.replace('control:', ''))}: ${pc(g.net_return_pct)} (${g.n ?? 0} op.)</span>`).join(' · ')
      const st = (Object.keys(a.stages) as Stage[]).map((s) => `${STAGE[s]} ${a.stages[s]}`).join(' · ')
      return `<section class="ct-group"><h4>${esc(agentLabel(a.agent_id))} <small>${a.prospects.length} prospectos · ${st}</small></h4>` +
        `<p class="muted ct-gen">Genérico de control: ${gen || '—'}</p>${table(ps.filter((x) => x.agent_id === a.agent_id))}</section>`
    }).join('')
  }

  private head(): string {
    const d = this.data
    const live = d?.enabled && d.live
      ? (d.live.error
        ? `<span class="ct-live" data-s="warn" title="${esc(d.live.error)}">● en vivo · aviso</span>`
        : `<span class="ct-live" data-s="ok" title="La cantera opera sola en el servicio: cada vela nueva se analiza y sus prospectos abren y cierran sin intervención">● en vivo · último ciclo ${d.live.last_tick ? cot(d.live.last_tick).slice(11) : '—'}</span>`)
      : d && !d.enabled ? '<span class="ct-live" data-s="off">● no corre en este equipo</span>' : ''
    const alta = d?.prereg ? `<span class="pp-cov muted">alta ${cot(d.prereg.alta_ms)} COT · pre-registro ${esc(d.prereg.version)}</span>` : ''
    return '<header class="pp-head"><h2 class="pp-title">Cantera</h2>' +
      '<span class="mode" data-mode="SIMULADO" title="Toda cifra de esta pestaña es simulada">Modo: Simulado · cuenta propia por prospecto · contabilidad aparte</span>' +
      '<span class="ct-tag">Perfiles propios por agente · solo hacia adelante · BTCUSDT</span>' +
      `<span class="spacer"></span>${alta}${live}</header>`
  }

  render(): void {
    const d = this.data
    const head = this.head()
    if (this.card.isOpen) { this.el.innerHTML = head + `<section class="ct-box">${this.card.html()}</section>`; return }
    if (!d) { this.el.innerHTML = head + `<section class="ct-box"><p class="muted">${esc(this.err || 'Consultando la cantera…')}</p></section>`; return }
    if (!d.enabled) {
      this.el.innerHTML = head + '<section class="ct-box"><p class="ct-acct">La cantera es una contabilidad aparte de los cuatro perfiles.</p>' +
        `<p>${esc(d.reason ?? 'La cantera no corre en este equipo.')}</p></section>`
      return
    }
    const live = d.live?.error ? `<p class="ct-warn" role="status">${esc(d.live.error)}</p>` : ''
    const bal = d.balance
      ? `<section class="pp-balance" aria-label="Balance de operaciones ganadas y perdidas">${canteraBalanceView(d.balance, this.period)}</section>` +
        '<section class="pp-eqbox ct-eqbox" aria-label="Capital por agente"><div class="pp-eq-h"><h4 class="sh">Capital por agente</h4>' +
        '<small class="muted">capital realizado de las cuentas de sus prospectos sumadas (USDT) · % frente a su capital inicial (línea punteada en 0) · ' +
        'clic en un agente para ocultar o mostrar su curva</small></div>' + canteraCurveView(d.balance, this.hidden) + '</section>'
      : `<section class="ct-box"><p class="muted">${esc(d.reason ?? 'Primer cálculo de la cantera en curso…')}</p></section>`
    const ladder = d.panel
      ? `<section class="ct-box"><h4 class="sh">Escalafón por agente</h4>${header(d, d.panel)}${this.controls(d.panel)}${this.groups(d.panel)}</section>`
      : `<section class="ct-box"><p class="muted">${esc(d.live?.error || 'sin pre-registro: el escalafón necesita la familia de cantera_v1')}</p></section>`
    this.el.innerHTML = head + live + bal + ladder
  }
}
