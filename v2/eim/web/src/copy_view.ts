import { esc } from './panels'
import { f, pct, usd, utc } from './leaders_view'

/** Copia simulada en vivo (T42, `GET /v2/leaders/copy`): una subcuenta virtual por líder.
 *  Siempre modo Simulado: saldo virtual, ninguna orden real ni de testnet. */
export interface CopyPosition {
  coin: string; size: number; entry: number | null; mark: number | null; stop: number | null
  upnl: number | null; notional: number; leader: number; target: number; ratio: number | null
  excluded: string | null; note: string | null
}
export interface CopyEntry { seq: number; t: number; kind: string; coin: string; code: string; text: string }
export interface CopyAccount {
  leader_id: string; label: string; mode: string; measure: boolean; approved: boolean
  paused: string | null; kill: { active: boolean; reason: string }; started_t: number
  equity0: number; equity: number; pnl: number; ret: number | null; fees: number; funding: number
  max_dd: number; trips: number; wins: number; positions: CopyPosition[]
  counts: Record<string, number>; rejects: Record<string, number>
  last_recon: { t: number; ok: boolean; diffs: { coin: string; status: string; why: string }[] } | null
  journal: CopyEntry[]
}
export interface CopyPayload {
  mode: string; now: number; age_s: number | null; stale: boolean
  sim: { asof: number; sim_mode: string; label: string; risk_version: string; accounts: CopyAccount[] } | null
}

const KIND: Record<string, string> = {
  signal: 'Señal', decision: 'Decisión', risk: 'Riesgo', order: 'Orden', reject: 'Rechazo',
  stop: 'Stop', funding: 'Funding', recon: 'Reconciliación', pause: 'Pausa', resume: 'Reanudación',
  kill: 'Kill-switch', start: 'Inicio',
}
const short = (a: string): string => { const x = a.split(':').pop() ?? a; return `${x.slice(0, 6)}…${x.slice(-4)}` }

function state(a: CopyAccount): string {
  if (a.kill.active) return `<span class="ld-chip" data-v="rejected">Kill-switch</span>`
  if (a.paused) return `<span class="ld-chip" data-v="rejected" title="${esc(a.paused)}">En pausa</span>`
  return a.measure ? '<span class="ld-chip" data-v="watch" title="Líder no aprobado: solo medición">Medición</span>'
    : '<span class="ld-chip" data-v="approved">Copiando</span>'
}

function positions(a: CopyAccount): string {
  // Lo que el líder ya tenía al seguirlo y no se copia va en una línea: la tabla queda para lo vivo.
  const idle = a.positions.filter((p) => p.size === 0 && p.excluded)
  const live = a.positions.filter((p) => !(p.size === 0 && p.excluded))
  const skipped = idle.length ? `<p class="muted">${idle.length} posiciones del líder no se copian ` +
    `(${esc([...new Set(idle.map((p) => p.excluded))].join(', '))}): ${esc(idle.map((p) => p.coin).join(', '))}.</p>` : ''
  return table(live) + skipped
}

function table(ps: CopyPosition[]): string {
  const rows = ps.map((p) => `<tr><td>${esc(p.coin)}</td><td>${f(p.size, 5)}</td><td>${f(p.target, 5)}</td>` +
    `<td>${f(p.leader, 4)}</td><td>${f(p.entry)}</td><td>${f(p.mark)}</td><td>${f(p.stop)}</td><td>${usd(p.upnl, 2)}</td>` +
    `<td><small>${esc(p.excluded ? `no se copia: ${p.excluded}` : p.note ?? '')}</small></td></tr>`).join('')
  return rows ? '<table class="ld-table cp-pos"><thead><tr><th>Moneda</th><th>Propia</th><th>Objetivo</th><th>Líder</th>' +
    `<th>Entrada</th><th>Marca</th><th>Stop</th><th>Latente</th><th>Motivo de la diferencia</th></tr></thead><tbody>${rows}</tbody></table>`
    : '<p class="muted">Sin posiciones propias ni objetivos pendientes.</p>'
}

function journal(a: CopyAccount): string {
  return '<ol class="cp-journal">' + a.journal.slice().reverse().map((e) =>
    `<li data-k="${esc(e.kind)}"><span class="muted">${utc(e.t).slice(11)}</span> <b>${KIND[e.kind] ?? esc(e.kind)}</b> ` +
    `${e.coin ? `${esc(e.coin)} · ` : ''}${esc(e.text)}</li>`).join('') + '</ol>'
}

function account(a: CopyAccount, open: Set<string>): string {
  const rej = Object.entries(a.rejects).sort((x, y) => y[1] - x[1]).slice(0, 3).map(([k, v]) => `${esc(k)} ${v}`).join(' · ') || '—'
  const r = a.last_recon
  const recon = r ? (r.ok ? `ok ${utc(r.t).slice(11)}` : `<span data-dir="down">divergencia: ${esc(r.diffs.map((d) => d.coin).join(', '))}</span>`) : '—'
  const held = a.positions.filter((p) => p.size !== 0).length
  return `<details class="cp-acc" data-id="${esc(a.leader_id)}"${open.has(a.leader_id) ? ' open' : ''}><summary><b>${esc(a.label || short(a.leader_id))}</b> ${state(a)} ` +
    `<span>capital <b>${f(a.equity)}</b> (<span data-dir="${a.pnl > 0 ? 'up' : a.pnl < 0 ? 'down' : 'flat'}">${usd(a.pnl, 2)}</span>)</span>` +
    `<span class="muted">${a.counts.orders ?? 0} órdenes · ${held} abiertas · comisiones ${usd(a.fees ? -a.fees : 0, 2)} · funding ${usd(a.funding, 2)} · ` +
    `caída máx. ${pct(a.max_dd)} · rechazos: ${rej} · reconciliación: ${recon}</span></summary>` +
    (a.paused ? `<p class="scen-warn">En pausa: ${esc(a.paused)}. Revisar y reanudar a mano: <code>python -m eim.leaders copy-resume ${esc(a.leader_id.split(':').pop() ?? '')}</code></p>` : '') +
    positions(a) + journal(a) + '</details>'
}

export function copyBox(p: CopyPayload | null, err: string, open: Set<string> = new Set()): string {
  const head = '<div class="scen-bar arb-head"><b>Copia simulada</b>' +
    '<span class="mode" data-mode="SIMULADO">Modo: Simulado · saldo virtual, sin órdenes reales ni de testnet</span>'
  if (err) return `${head}</div><p class="scen-warn">${esc(err)}</p>`
  const s = p?.sim
  if (!s) {
    return `${head}</div><p class="muted">Sin copia en vivo: el servicio de líderes la escribe en <code>data/leaders/copy_sim.json</code> ` +
      '(se desactiva con <code>EIM_COPY_SIM=off</code>).</p>'
  }
  const measure = s.accounts.some((a) => a.measure)
  return `${head}<span class="muted">${s.accounts.length} subcuentas · ${utc(s.asof)} (hace ${Math.round(p?.age_s ?? 0)} s) · riesgo ${esc(s.risk_version)}</span></div>` +
    (p?.stale ? '<p class="scen-warn">Resumen viejo: el servicio de líderes parece detenido.</p>' : '') +
    (measure ? '<p class="muted">Ningún líder está aprobado: se copian todos los capturados <b>solo para medir</b> qué parte de su ' +
      'rendimiento es copiable (latencia, precio del seguidor, comisiones, topes y vetos del motor de riesgo).</p>' : '') +
    s.accounts.map((a) => account(a, open)).join('')
}
