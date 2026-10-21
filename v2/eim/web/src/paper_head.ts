/** Cabecera del bróker simulado: servicio en vivo por marco, tarjetas de perfil y cuenta. */
import { PROFILE_VAR } from './paper_chart'
import { dur, esc, hm, nf, pct, pct0, usd, utc } from './paper_fmt'
import type { Job, PaperSummary, ProfileView } from './paper_types'

const TF_MS: Record<string, number> = { '15m': 900_000, '1h': 3_600_000, '4h': 14_400_000 }
const STALE_MS = 3 * 60_000      // sin ciclo en 3 min = el servicio no está corriendo

/** Franja «en vivo»: cuándo corrió el último ciclo y última/próxima decisión de cada marco. */
export function liveStrip(v: PaperSummary, now = Date.now()): string {
  const last = v.live.last_tick, started = v.live.started
  const state = last === null ? (started ? 'starting' : 'off') : now - last > STALE_MS ? 'stale' : 'up'
  const label = state === 'up' ? `Servicio en vivo · último ciclo hace ${dur(now - last!)}`
    : state === 'stale' ? `Servicio detenido o atrasado · último ciclo hace ${dur(now - last!)}`
      : state === 'starting' ? `Servicio en vivo arrancando · poniéndose al día desde hace ${dur(now - started!)}`
        : 'Servicio en vivo apagado en esta API (EIM_PAPER=0 o sin fuente real)'
  const tfs = (v.timeframes ?? []).map((tf) => {
    const c = v.coverage.timeframes?.[tf]
    const to = c?.to ?? null
    const next = to === null ? null : to + (TF_MS[tf] ?? 0)
    return `<span class="pp-tf"><b>${tf}</b> ${c?.contexts ?? 0} velas · ${c?.origins?.vivo ?? 0} en vivo` +
      (to === null ? '' : ` · última ${hm(to)} COT · próxima ${next! + (TF_MS[tf] ?? 0) <= now ? 'atrasada (poniéndose al día)' : next! <= now ? 'en análisis' : `${hm(next!)} COT`}`) + '</span>'
  }).join('')
  const err = v.live.error ? ` <span class="down">· ${esc(v.live.error)}</span>` : ''
  return `<span class="pp-live-dot" data-state="${state}"><i></i>${label}${err}</span>${tfs}${viewNote(v, now)}`
}

/** Antigüedad de la vista: con un backtest en curso las cifras pueden ir unos minutos atrasadas. */
function viewNote(v: PaperSummary, now: number): string {
  const s = v.view
  if (!s) return ''
  const age = `cifras calculadas hace ${dur(now - s.computed)}`
  const why = s.refreshing ? 'recalculando con los datos nuevos'
    : v.job.state === 'corriendo' ? 'con el backtest en curso se rehacen cada 10 min' : 'se rehacen en la próxima carga'
  const err = s.error ? ` · error al recalcular: ${esc(s.error)}` : ''
  return s.stale || err ? `<span class="pp-tf"><span class="warn">${age} · ${why}${err}</span></span>` : `<span class="pp-tf">${age}</span>`
}

export function covText(v: PaperSummary): string {
  const c = v.coverage
  return c.contexts
    ? `${c.contexts} velas analizadas (${c.origins.vivo ?? 0} en vivo · ${c.origins.backtest ?? 0} reconstruidas) · ${utc(c.from!)} → ${utc(c.to!)} COT`
    : 'sin velas analizadas: ejecuta un backtest'
}

export function jobHtml(j: Job): string {
  if (j.state === 'corriendo') {
    return `<progress max="${j.total || 1}" value="${j.done}"></progress> ${j.done}/${j.total || '…'} velas${j.tf ? ` · ${j.tf}` : ''}`
  }
  if (j.state === 'error') return `<span class="down">error: ${esc(j.error)}</span>`
  return j.state === 'terminado' ? `<span class="muted">último: +${j.saved} velas</span>` : ''
}

export function cardsHtml(v: PaperSummary, profile: string): string {
  return v.profiles.map((p) => {
    const ret = p.return_pct
    return `<button class="pp-card" role="tab" data-prof="${p.id}" aria-selected="${p.id === profile}" style="--pc:var(${PROFILE_VAR[p.id] ?? '--accent'})">` +
      `<span class="pp-card-h"><i></i>${esc(p.name)}</span>` +
      `<b class="num">${nf(p.equity)} <small>USDT</small></b>` +
      `<span class="num ${ret > 0 ? 'up' : ret < 0 ? 'down' : ''}">${pct(ret)}</span>` +
      `<small class="muted">${p.n_closed} ops · acierto ${pct0(p.win_rate)} · PF ${p.pf === null ? '—' : nf(p.pf)} · DD máx. ${pct0(p.max_dd_pct)}</small>` +
      `<small class="muted">${p.positions.length} abiertas · ${p.orders.length} órdenes · riesgo ${nf(Number(p.params.risk_pct) * 100, 1)} % · hasta ${p.params.max_leverage}x</small></button>`
  }).join('')
}

export function acctHtml(p: ProfileView): string {
  const row = (k: string, v: string, cls = ''): string => `<div><span>${k}</span><b class="num ${cls}">${v}</b></div>`
  const t = (x: number): string => (x > 0 ? 'up' : x < 0 ? 'down' : '')
  return `<h4 class="sh">Cuenta · ${esc(p.name)}</h4><div class="pp-kv">` +
    row('Capital (equity)', `${nf(p.equity)} USDT`) + row('Saldo de la cartera', `${nf(p.balance)} USDT`) +
    `<div><span>PnL no realizado</span><b class="num ${t(p.upnl)}" data-x="upnl-live">${usd(p.upnl)} USDT</b></div>` +
    row('PnL realizado', `${usd(p.realized)} USDT`, t(p.realized)) +
    row('Margen en uso', `${nf(p.margin_used)} USDT`) + row('Margen reservado (órdenes)', `${nf(p.reserved)} USDT`) +
    row('Disponible', `${nf(p.available)} USDT`) + row('Capital inicial', `${nf(p.initial)} USDT`) +
    row('Comisiones · desliz.', `${nf(p.fees)} · ${nf(p.slip)}`) + row('Funding pagado (− cobrado)', `${usd(p.funding)} USDT`) +
    row('Mejor / peor', `${p.best === null ? '—' : usd(p.best)} / ${p.worst === null ? '—' : usd(p.worst)}`) +
    `</div><p class="muted pp-note">${esc(p.description)}</p>`
}
