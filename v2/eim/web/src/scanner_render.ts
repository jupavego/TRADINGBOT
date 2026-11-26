/** Render de la pestaña «Escáner» (T94): funciones puras dato → HTML, sin DOM ni red.
 *
 * Reglas de visualización (skill dataviz): las tres puntuaciones son magnitudes 0–1 → barra fina
 * de UN solo tono con la cifra en tinta de texto; el lado no depende del color (flecha + palabra);
 * el estado del mercado lleva icono y texto; ninguna puntuación se combina en un número único
 * (la priorización global es T95). El modo y el aviso «candidata, no validada» van siempre arriba. */
import type { DeepDetail, MarketRow, Opportunity, UniversePayload, UniverseRow } from './scanner_api'
import { agentName, esc } from './panels'
import { cot, num } from './cantera_fmt'

const DAY = 86_400_000
export const CLASS: Record<string, string> = {
  crypto: 'Cripto', equity: 'Acciones', etf: 'ETF', index: 'Índices', fx: 'Divisas',
  commodity: 'Materias primas', future: 'Futuros', option: 'Opciones', bond: 'Renta fija', cash: 'Monetario',
}
const STATE: Record<string, [string, string]> = {
  abierto: ['●', 'abierto'], cerrado: ['○', 'cerrado'], sin_calendario: ['◌', 'sin calendario'],
}
const STATUS: Record<string, string> = { ok: 'OK', degraded: 'degradado', no_data: 'sin datos' }
const SCEN: Record<string, string> = { bull: 'alcista', neutral: 'neutral', bear: 'bajista' }

export interface Filters { cls: string; market: string; horizon: string; side: string }
export const ALL = ''

const f2 = (x: number | null | undefined): string => (x == null ? '—' : num(x, 2))
const pct = (x: number | null | undefined): string => (x == null ? '—' : `${num(x * 100, 0)} %`)
const sgn = (x: number): string => `${x > 0 ? '+' : x < 0 ? '−' : ''}${num(x, 2)}`

export function stateTag(s: string): string {
  const [icon, label] = STATE[s] ?? ['◌', s]
  return `<span class="sc-state" data-s="${esc(s)}">${icon} ${esc(label)}</span>`
}

export function sideTag(side: 'largo' | 'corto'): string {
  return `<span class="sc-side" data-side="${side}">${side === 'largo' ? '▲ largo' : '▼ corto'}</span>`
}

/** Barra fina 0–1 de un solo tono; la cifra va aparte, en tinta de texto. */
export function scoreBar(x: number, title: string): string {
  const w = Math.max(0, Math.min(1, x)) * 100
  return `<span class="sc-score" title="${esc(title)}"><i><b style="width:${w.toFixed(0)}%"></b></i><em>${f2(x)}</em></span>`
}

export function horizonDays(o: Opportunity): number { return o.horizon_ms / DAY }

export function matches(o: { asset_class: string; market: string }, f: Filters): boolean {
  return (f.cls === ALL || o.asset_class === f.cls) && (f.market === ALL || o.market === f.market)
}

export function filterOpps(opps: Opportunity[], f: Filters): Opportunity[] {
  const hmax = f.horizon === ALL ? Infinity : Number(f.horizon)
  return opps.filter((o) => matches(o, f) && (f.side === ALL || o.side === f.side) && horizonDays(o) <= hmax)
}

export function head(u: UniversePayload, nOpps: number): string {
  const d = u.deep
  const ex = Object.entries(u.exclusions ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 4)
    .map(([k, n]) => `${esc(k.replace('_', ' '))} ${n}`).join(' · ')
  return `<div class="sc-head">
    <div class="sc-title"><h3>Escáner global</h3>
      <span class="sc-mode" title="Toda vista de plan u operación muestra el modo">Modo: Análisis</span>
      <span class="sc-flag" role="note">⚠ ${esc(u.status_label)}</span></div>
    <p class="sc-notice">${esc(u.notice)}</p>
    <div class="sc-kpis">
      <div><b>${u.n_scored ?? 0}</b><small>instrumentos puntuados</small></div>
      <div><b>${d?.n_shortlist ?? 0}</b><small>en la lista corta (agentes)</small></div>
      <div><b>${nOpps}</b><small>candidatas (no validadas)</small></div>
      <div><b>${esc(u.timeframe ?? '—')}</b><small>marco · barrido ${esc(cot(u.asof))}</small></div>
    </div>
    <p class="sc-meta muted">Exclusiones del embudo: ${ex || 'ninguna'} · vista publicada ${esc(cot(u.generated_at))} (hora de Bogotá)</p>
  </div>`
}

export function markets(rows: MarketRow[]): string {
  if (!rows.length) return ''
  const body = rows.map((m) => `<tr><td>${esc(m.market)}</td><td>${esc(CLASS[m.asset_class] ?? m.asset_class)}</td>` +
    `<td class="num">${m.n}</td><td class="num">${stateTag('abierto')} ${m.abierto}</td>` +
    `<td class="num">${stateTag('cerrado')} ${m.cerrado}</td><td class="num">${m.sin_calendario}</td></tr>`).join('')
  return `<h4>Mercados</h4><table class="sc-table sc-mk"><thead><tr><th>Plaza · mercado</th><th>Clase</th>` +
    `<th>Instrumentos</th><th>Abiertos</th><th>Cerrados</th><th>Sin calendario</th></tr></thead><tbody>${body}</tbody></table>`
}

function options(values: string[], cur: string, label: (v: string) => string): string {
  return [`<option value="">todos</option>`, ...values.map((v) =>
    `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(label(v))}</option>`)].join('')
}

export function filters(u: UniversePayload, f: Filters): string {
  const rows = u.rows ?? []
  const cls = [...new Set(rows.map((r) => r.asset_class))].sort()
  const mk = [...new Set(rows.map((r) => r.market))].sort()
  const hz: [string, string][] = [['', 'todos'], ['1', '≤ 1 día'], ['7', '≤ 7 días'], ['30', '≤ 30 días']]
  return `<div class="sc-filters" role="group" aria-label="Filtros">
    <label>Clase<select data-sc="cls">${options(cls, f.cls, (v) => CLASS[v] ?? v)}</select></label>
    <label>Mercado<select data-sc="market">${options(mk, f.market, (v) => v)}</select></label>
    <label>Horizonte<select data-sc="horizon">${hz.map(([v, l]) => `<option value="${v}"${v === f.horizon ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
    <label>Lado<select data-sc="side">${options(['largo', 'corto'], f.side, (v) => v)}</select></label>
  </div>`
}

export function oppTable(opps: Opportunity[], byId: Map<string, UniverseRow>): string {
  if (!opps.length) return `<p class="muted sc-empty">Ninguna candidata con estos filtros.</p>`
  const rows = opps.map((o) => {
    const s = o.scores, c = s.components, r = byId.get(o.instrument_id)
    const voters = o.agents.filter((a) => a.votes).length
    return `<tr class="sc-row" data-id="${esc(o.instrument_id)}" tabindex="0" title="Ver agentes, proyección y trazabilidad">` +
      `<td><b>${esc(o.symbol)}</b><small>${esc(CLASS[o.asset_class] ?? o.asset_class)} · ${esc(o.market)}</small></td>` +
      `<td>${sideTag(o.side)}<small>sesgo ${sgn(o.synthesis.bias)}</small></td>` +
      `<td>${scoreBar(s.signal_quality, `confianza ${f2(c.confidence)} × acuerdo ${f2(c.agreement)}`)}</td>` +
      `<td>${scoreBar(s.viability, `calidad de datos ${f2(c.data_quality)} · liquidez ${f2(c.liquidity)} · diferencial ${c.spread == null ? 'sin medir' : f2(c.spread)} · agentes sin degradar ${pct(c.agents_clean)}`)}</td>` +
      `<td>${scoreBar(s.risk_cost, `costo/movimiento ${f2(c.cost_to_move)} · prob. en contra ${pct(c.p_adverse)}`)}</td>` +
      `<td>${o.horizon_bars} velas ${esc(o.timeframe)}<small>≈ ${num(horizonDays(o), 0)} días · vigente hasta ${esc(cot(o.valid_until))}</small></td>` +
      `<td>${voters} votan / ${o.agents.length} corrieron<small>${r?.n_bars ?? o.coverage.n_bars ?? '—'} velas · volumen ${esc(o.coverage.volume ?? '—')}</small></td>` +
      `<td>${stateTag(r?.state ?? 'sin_calendario')}</td></tr>`
  }).join('')
  return `<table class="sc-table sc-opps"><thead><tr><th>Instrumento</th><th>Lado</th>` +
    `<th title="Confianza × acuerdo de la síntesis">Calidad de la señal</th><th title="Datos, liquidez, diferencial y agentes sin degradar">Viabilidad operativa</th>` +
    `<th title="Costo frente al movimiento esperado y probabilidad del escenario en contra (más alto = más favorable)">Riesgo / costos</th>` +
    `<th>Horizonte</th><th>Agentes · cobertura</th><th>Mercado</th></tr></thead><tbody>${rows}</tbody></table>`
}

export function universeTable(rows: UniverseRow[]): string {
  const body = rows.map((r) => `<tr class="sc-row" data-id="${esc(r.instrument_id)}" tabindex="0">` +
    `<td class="num">${r.rank}</td><td><b>${esc(r.symbol)}</b><small>${esc(CLASS[r.asset_class] ?? r.asset_class)} · ${esc(r.market)}</small></td>` +
    `<td>${r.score == null ? '—' : scoreBar(r.score, 'interés de la etapa 3 (no es una señal)')}</td>` +
    `<td class="num">${pct(r.quality)}</td><td>${stateTag(r.state)}</td>` +
    `<td>${r.deep ? (r.opportunity_id ? 'candidata' : 'analizado, sin candidata') : '—'}</td><td>${esc(cot(r.last_t))}</td></tr>`).join('')
  return `<table class="sc-table sc-univ"><thead><tr><th>#</th><th>Instrumento</th><th>Interés (etapa 3)</th>` +
    `<th>Calidad de datos</th><th>Mercado</th><th>Agentes</th><th>Última vela</th></tr></thead><tbody>${body}</tbody></table>`
}

export function detail(d: DeepDetail | null, o: Opportunity | null, row: UniverseRow | null, note: string | null): string {
  const name = esc(o?.symbol ?? d?.symbol ?? row?.symbol ?? '')
  let html = `<div class="sc-detail"><button type="button" class="sc-back" data-sc-back>← Volver a la lista</button>` +
    `<h3>${name} <span class="sc-flag">⚠ candidata, no validada</span> <span class="sc-mode">Modo: Análisis</span></h3>`
  if (!d) return `${html}<p class="muted">${esc(note ?? 'sin análisis de agentes')}</p></div>`
  const cov = d.coverage
  html += `<p class="sc-meta">${stateTag(d.state)} · cobertura real: ${cov.n_bars} velas ${esc(d.timeframe)} (${num(cov.span_days, 0)} días), ` +
    `volumen ${esc(cov.volume)}, datos: ${esc(cov.fields.join(', '))} · ${num(d.elapsed_ms, 0)} ms</p>`
  if (o) html += `<p>${sideTag(o.side)} · señal ${f2(o.scores.signal_quality)} · viabilidad ${f2(o.scores.viability)} · riesgo/costos ${f2(o.scores.risk_cost)}</p>`
  else html += `<p class="sc-warn">Sin candidata: ${esc(d.reason)}</p>`
  html += `<h4>Agentes que corrieron (${d.ran.length})</h4><table class="sc-table"><thead><tr><th>Agente</th><th>Versión</th><th>Estado</th>` +
    `<th>Sesgo</th><th>Confianza</th><th>¿Vota?</th><th>Avisos</th></tr></thead><tbody>` +
    d.ran.map((a) => {
      const vote = o?.agents.find((v) => v.agent_id === a.agent_id)?.votes
      return `<tr><td>${esc(agentName(a.agent_id))}</td><td>${esc(a.version)}</td><td data-status="${esc(a.status)}">${esc(STATUS[a.status] ?? a.status)}</td>` +
        `<td class="num">${sgn(a.bias)}</td><td class="num">${f2(a.confidence)}</td><td>${vote == null ? '—' : vote ? 'sí' : 'no (peso 0)'}</td>` +
        `<td><small>${esc([...a.warnings, a.eligibility === 'elegible' ? '' : a.eligibility].filter(Boolean).join(' · ') || '—')}</small></td></tr>`
    }).join('') + `</tbody></table>`
  html += `<h4>No corrieron (${d.skipped.length})</h4><ul class="sc-skip">` +
    d.skipped.map((s) => `<li><b>${esc(agentName(s.agent_id))}</b>: ${esc(s.reason)}</li>`).join('') + `</ul>`
  if (d.synthesis) html += `<h4>Síntesis (la existente, sin cambios)</h4><p>${esc(d.synthesis.thesis)}</p>`
  if (d.forecast) {
    const sc = d.forecast.scenarios
    html += `<h4>Proyección · ${esc(d.forecast.label)}</h4><p class="sc-scen">` +
      (['bull', 'neutral', 'bear'] as const).map((k) => `${SCEN[k]} ${pct(sc[k].p)} (mediana final ${num(sc[k].median_end, 4)})`).join(' · ') +
      ` · ${d.forecast.horizon_bars} velas, motor ${esc(d.forecast.engine)}</p>`
  }
  if (o) {
    const ref = o.input_ref
    html += `<h4>Trazabilidad</h4><dl class="sc-trace">` +
      `<dt>Oportunidad</dt><dd><code>${esc(o.opportunity_id)}</code> (versión ${esc(o.version)})</dd>` +
      `<dt>Datos</dt><dd><code>${esc(o.input_hash)}</code> · ${ref.n_bars} velas ${esc(ref.timeframe)} de ${esc(ref.symbol)} en <code>${esc(ref.store)}</code>, ${esc(cot(ref.first_t))} → ${esc(cot(ref.last_t))} · fuente: ${esc(o.source)}</dd>` +
      `<dt>Barrido</dt><dd><code>${esc(o.run_id)}</code></dd>` +
      `<dt>Versiones</dt><dd>${Object.entries(o.versions).map(([k, v]) => `${esc(k)} ${esc(v)}`).join(' · ')}</dd>` +
      `<dt>Comprobar</dt><dd><code>python -m eim.scanner verify ${esc(o.opportunity_id)}</code></dd></dl>`
    if (o.scores.notes.length) html += `<p class="muted">${o.scores.notes.map(esc).join(' · ')}</p>`
  }
  if (d.warnings.length) html += `<p class="sc-warn">${d.warnings.map(esc).join('<br>')}</p>`
  return `${html}</div>`
}
