/** Panel multiactivo de la pestaña «Escáner» (T102): funciones puras dato → HTML, sin DOM ni red.
 *
 * Qué mercados se vigilan, con qué datos y qué no se puede ver: salud por clase (cobertura, calidad,
 * frescura, mercados abiertos/cerrados, candidatas y su nivel en el despliegue gradual), por fuente
 * (nivel, licencia, techo de uso, errores), estado y presupuesto del escáner, y el recorrido de una
 * candidata del dato a la decisión. Reglas de visualización (skill dataviz): magnitudes 0–1 con la
 * barra fina de un solo tono de la pestaña; el estado lleva SIEMPRE icono y palabra (nunca solo
 * color) y usa los tonos de estado reservados; «sin datos» nunca se pinta como sano. Modo visible. */
import type { CandidateTrace, HealthClass, HealthPayload, HealthProvider, RolloutUnit } from './scanner_api'
import { esc } from './panels'
import { cot, num } from './cantera_fmt'

const STATE: Record<string, [string, string]> = {
  ok: ['●', 'sano'], degradado: ['◐', 'degradado'], obsoleto: ['◷', 'obsoleto'], sin_datos: ['○', 'sin datos'],
  error: ['✕', 'error'], pausado: ['‖', 'pausado'], planeado: ['◌', 'fuera de alcance']
}
const LEVEL: Record<string, string> = { alerta: 'Alerta', simulacion: 'Simulación', papel: 'Papel', ejecucion_limitada: 'Ejecución limitada' }
const pct = (x: number | null | undefined): string => (x == null ? '—' : `${num(x * 100, 0)} %`)

export function healthTag(s: string): string {
  const [icon, word] = STATE[s] ?? ['?', s]
  return `<span class="sc-hs" data-hs="${esc(s)}">${icon} ${esc(word)}</span>`
}

/** Magnitud 0–1 con su cifra; sin dato → «no medida», nunca una barra vacía que parezca cero. */
function bar(x: number | null, title: string): string {
  if (x == null) return `<span class="muted" title="${esc(title)}">no medida</span>`
  const w = Math.max(0, Math.min(1, x)) * 100
  return `<span class="sc-score" title="${esc(title)}"><i><b style="width:${w.toFixed(1)}%"></b></i><em>${pct(x)}</em></span>`
}

function levelCell(u: RolloutUnit | undefined): string {
  if (!u) return '<span class="muted">—</span>'
  const why = u.active ? (u.next ?? []).join(' · ') : `desactivada: ${u.reason}`
  return `<span title="${esc(why)}">${esc(LEVEL[u.level] ?? u.level)}${u.active ? '' : ' · <b class="sc-shadow">en sombra</b>'}</span>` +
    `<small>${esc((u.active ? u.next?.[0] : u.reason) ?? '')}</small>`
}

function classRow(c: HealthClass, u: RolloutUnit | undefined): string {
  const excl = Object.entries(c.exclusions).map(([k, n]) => `${k} ${n}`).join(' · ')
  const covTitle = c.coverage == null ? 'cobertura no medida: la base del escáner estaba ocupada en la revisión'
    : `${c.n_scored} puntuados de ${c.n_scored + (c.n_excluded ?? 0)}; fuera: ${excl || 'nadie'}`
  return `<tr data-plan="${esc(c.plan)}"><td><b>${esc(c.label)}</b><small>${esc(c.plan)} · ${esc(c.task)}</small></td>` +
    `<td>${healthTag(c.state)}<small>${esc(c.reasons.join('; '))}</small></td>` +
    `<td class="num">${c.n_scored}</td><td>${bar(c.coverage, covTitle)}</td>` +
    `<td>${bar(c.quality_mean, `${c.quality_incomplete} con calidad incompleta · ${c.stale_rows} con datos viejos`)}</td>` +
    `<td class="num">● ${c.markets.abierto} · ○ ${c.markets.cerrado}${c.markets.sin_calendario ? ` · ◌ ${c.markets.sin_calendario}` : ''}</td>` +
    `<td class="num">${c.candidates}<small>${c.above_threshold} sobre el umbral del azar</small></td>` +
    `<td>${levelCell(u)}</td></tr>`
}

function providerRow(p: HealthProvider): string {
  return `<tr><td><b>${esc(p.name)}</b><small>${esc(p.classes.join(', ') || 'sin uso en el escáner')}</small></td>` +
    `<td>${healthTag(p.state)}</td><td class="num">nivel ${p.level}</td>` +
    `<td>${bar(p.usage_share, p.usage_note)}</td><td class="num">${p.errors}</td>` +
    `<td><small>${esc(p.license)}</small></td></tr>`
}

/** Bloque de salud multiactivo, arriba de la pestaña. */
export function healthBlock(h: HealthPayload | null, err = ''): string {
  if (!h) return err ? `<p class="sc-warn">Salud multiactivo no disponible: ${esc(err)}</p>` : ''
  const units = h.rollout?.units ?? {}
  const watched = h.classes.filter((c) => c.n_scored > 0 || c.alerting)
  const outOf = h.classes.filter((c) => c.n_scored === 0 && !c.alerting)
  const sc = h.scanner, b = sc.budget
  const alerts = Object.keys(h.alerts_active ?? {})
  const ob = h.observability
  const used = h.providers.filter((p) => p.used), unused = h.providers.filter((p) => !p.used)
  return `<section class="sc-health" aria-label="Salud multiactivo">
    <h4>Salud multiactivo ${healthTag(h.overall)} <small>Modo: Análisis · revisión ${esc(cot(h.checked_at ?? null))} · vista de hace ${h.view.age_h == null ? '—' : `${num(h.view.age_h, 1)} h`}</small></h4>
    ${h.note ? `<p class="sc-warn">${esc(h.note)}</p>` : ''}
    ${alerts.length ? `<p class="sc-warn">⚠ ${alerts.length} aviso${alerts.length > 1 ? 's' : ''} activo${alerts.length > 1 ? 's' : ''}: ${esc(alerts.map((k) => k.replace('multiactivo:', '')).join(', '))}</p>` : ''}
    <div class="sc-kpis">
      <div><b>${h.watching.n_instruments}</b><small>instrumentos vigilados en ${h.watching.classes.length} clases</small></div>
      <div><b>${b.ms_per_instrument == null ? '—' : num(b.ms_per_instrument, 1)} ms</b><small>por instrumento en el embudo (presupuesto ${num(b.budget_ms, 0)} ms) · ${b.within_budget === false ? 'FUERA' : 'dentro'}</small></div>
      <div><b>${num(b.deep_ms_per_instrument / 1000, 1)} s</b><small>agentes por instrumento de la lista corta · ${b.max_procs} procesos</small></div>
      <div><b>${healthTag(sc.state)}</b><small>escáner · ${sc.failed_jobs} trabajos fallidos · umbral ${esc(sc.ranking.threshold_status ?? '—')}</small></div>
    </div>
    <div class="sc-scroll"><table class="sc-table sc-hclass"><thead><tr><th>Clase</th><th>Estado</th><th>Puntuados</th><th>Cobertura</th>` +
    `<th>Calidad de datos</th><th>Abiertos · cerrados</th><th>Candidatas</th><th>Despliegue · qué falta</th></tr></thead>` +
    `<tbody>${watched.map((c) => classRow(c, units[`class:${c.asset_class}`])).join('')}</tbody></table></div>
    <p class="sc-meta">Fuera de la vigilancia: ${outOf.map((c) => `${esc(c.label)} (${esc(c.plan)}, ${esc(c.task)})`).join(' · ') || 'ninguna'}.</p>
    <details class="sc-uni"><summary>Fuentes, qué no se puede ver y protocolo</summary>
      <div class="sc-scroll"><table class="sc-table sc-hprov"><thead><tr><th>Fuente</th><th>Estado</th><th>Nivel</th><th>Techo de uso</th><th>Errores</th><th>Licencia</th></tr></thead>
      <tbody>${used.map(providerRow).join('')}</tbody></table></div>
      <p class="sc-meta">Fichas sin uso en el escáner: ${unused.map((p) => `${esc(p.name)} (nivel ${p.level})`).join(' · ') || 'ninguna'}.</p>
      <h4>Qué no puede ver</h4><ul class="sc-skip">${h.blind_spots.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
      <p class="sc-meta">Despliegue gradual: alerta → simulación → papel; la ejecución limitada nunca es automática. Una clase o un agente que se degrada dos revisiones seguidas pasa a sombra solo y vuelve solo tras dos sanas (protocolo en docs/OPERACION.md §8).` +
    (ob ? ` Observatorio: ${ob.events} eventos por lote en ${num((ob.build_ms ?? 0) + (ob.emit_ms ?? 0), 1)} ms (${ob.within === false ? 'FUERA' : 'dentro'} del umbral).` : '') + `</p>
    </details>
  </section>`
}

/** Nota bajo las candidatas: cuántas quedan en sombra y por qué (no se listan como candidatas). */
export function shadowNote(rows: { symbol: string; reason: string }[] | undefined): string {
  if (!rows?.length) return ''
  return `<p class="sc-meta"><b class="sc-shadow">${rows.length} en sombra</b> por el despliegue gradual (se siguen calculando): ` +
    `${esc(rows.slice(0, 6).map((r) => `${r.symbol}: ${r.reason}`).join(' · '))}</p>`
}

const STEP: Record<string, [string, string]> = { ok: ['✓', 'en orden'], degradado: ['◐', 'con reservas'], sin_datos: ['○', 'sin datos'] }
function stepTag(s: string): string {
  const [icon, word] = STEP[s] ?? ['?', s]
  return `<span class="sc-hs" data-hs="${esc(s)}">${icon} ${esc(word)}</span>`
}

/** Recorrido de la candidata, del dato a su decisión (botón «Recorrido» del detalle). */
export function pathBlock(t: CandidateTrace | null, err = ''): string {
  if (!t) return err ? `<p class="sc-warn">Recorrido no disponible: ${esc(err)}</p>` : ''
  return `<section class="sc-path" aria-label="Recorrido de la candidata"><h4>Recorrido: del dato a la decisión <small>traza <code>${esc(t.trace_id)}</code> · la misma de sus eventos en el mapa del sistema</small></h4>` +
    `<ol>${t.steps.map((s) => `<li data-hs="${esc(s.status)}"><b>${esc(s.title)}</b> ${stepTag(s.status)}<br><span>${esc(s.summary)}</span></li>`).join('')}</ol></section>`
}
