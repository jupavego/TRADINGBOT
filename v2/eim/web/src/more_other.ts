/** Pestañas de "Más análisis": Liquidaciones, Estacionalidad y Bitácora de trading. */
import { day, esc, fmt, getMore, postMore, sourceLine, usd, type Json } from './more_api'
import type { Ctx } from './more_market'

export async function liquidationsView(el: HTMLElement, ctx: Ctx): Promise<void> {
  const j = await getMore('liquidations', { symbol: ctx.symbol, days: 30, bins: 20 })
  const max = Math.max(1, ...j.daily.map((d: Json) => d.longs_usd + d.shorts_usd))
  const bars = j.daily.map((d: Json) => `<tr><td>${day(d.t)}</td>
    <td class="bcell"><span class="bl" style="width:${(d.longs_usd / max) * 100}%"></span><span class="bs" style="width:${(d.shorts_usd / max) * 100}%"></span></td>
    <td class="num">${usd(d.longs_usd)}</td><td class="num">${usd(d.shorts_usd)}</td></tr>`).join('')
  const top = [...j.levels]
    .sort((a: Json, b: Json) => b.longs_usd + b.shorts_usd - a.longs_usd - a.shorts_usd).slice(0, 8)
    .map((l: Json) => `<tr><td class="num">${fmt(l.price)}</td><td class="num">${usd(l.longs_usd)}</td><td class="num">${usd(l.shorts_usd)}</td></tr>`).join('')
  el.innerHTML = `${j.stale ? `<div class="alert bad"><b>Dato obsoleto (stale):</b> el último archivo publicado es
    ${esc(j.most_recent_date)} (hace ${j.stale_age_days} días). Binance dejó de publicar este dataset en octubre de 2024:
    es histórico, NO describe el mercado actual.</div>` : ''}
    <div class="msrc">${sourceLine(j.source)} · ${j.days_with_data} días con archivo real</div>
    <div class="alert">Contrato usado: ${esc(j.liquidation_symbol)} (coin-margined), proxy correlacionado de ${esc(j.requested_symbol)} — no idéntico.</div>
    <div class="two"><div><h4>Totales diarios (USD) — <span class="down">longs</span> / <span class="up">shorts</span></h4>
    <table class="mt"><tr><th>Día</th><th></th><th>Longs</th><th>Shorts</th></tr>${bars}</table></div>
    <div><h4>Niveles con más notional liquidado</h4><table class="mt"><tr><th>Precio</th><th>Longs</th><th>Shorts</th></tr>${top}</table></div></div>`
}

const heat = (v: number | null): string => {
  if (v === null) return ''
  const a = Math.min(0.55, Math.abs(v) / 40)
  return `background:${v >= 0 ? `rgba(47,143,91,${a})` : `rgba(198,74,59,${a})`}`
}

export async function seasonalityView(el: HTMLElement): Promise<void> {
  const { assets } = await getMore('assets', {})
  el.innerHTML = `<div class="mrow"><label>Activo <select id="se-a">${assets.map((a: Json) =>
    `<option value="${esc(a.key)}">${esc(a.label)}</option>`).join('')}</select></label>
    <label>Desde <input id="se-y" type="number" value="2015" min="2000" max="2100"></label>
    <button class="btn" id="se-go">Actualizar</button></div><div id="se-out" class="muted"></div>`
  const out = el.querySelector<HTMLElement>('#se-out')!
  const go = async (): Promise<void> => {
    out.textContent = 'Cargando…'
    try {
      const j = await getMore('seasonality', {
        asset: el.querySelector<HTMLSelectElement>('#se-a')!.value,
        start_year: el.querySelector<HTMLInputElement>('#se-y')!.value })
      const head = j.months.map((m: string) => `<th>${esc(m)}</th>`).join('')
      const rows = j.rows.map((r: Json) => `<tr><th>${r.year}</th>${j.months.map((m: string) =>
        `<td class="num" style="${heat(r[m])}">${r[m] === null ? '' : fmt(r[m], 1)}</td>`).join('')}</tr>`).join('')
      const avg = j.months.map((m: string) =>
        `<td class="num" style="${heat(j.monthly_average_pct[m])}"><b>${fmt(j.monthly_average_pct[m], 1)}</b></td>`).join('')
      out.innerHTML = `<div class="msrc">${sourceLine(j.source)} · <b>cobertura real ${esc(j.real_data_range.start)} → ${esc(j.real_data_range.end)}</b>
        (pedido desde ${j.requested_range.start_year}; los años sin datos reales no se rellenan)</div>
        <table class="mt heat"><tr><th>Año</th>${head}</tr>${rows}<tr><th>Prom.</th>${avg}</tr></table>`
    } catch (e) { out.innerHTML = `<div class="alert bad">${esc((e as Error).message)}</div>` }
  }
  el.querySelector<HTMLButtonElement>('#se-go')!.onclick = () => void go()
  await go()
}

const SRC_LABEL: Record<string, string> = {
  ledger: 'libro contable (real)', trading_history: 'historial de trading (real)', estimado: 'estimado',
}

export function bitacoraView(el: HTMLElement): void {
  el.innerHTML = `<form id="bi-f" class="mrow">
    <label>Export Binance (.xlsx) <input name="file" type="file" accept=".xlsx,.xls" required></label>
    <label>Historial de transacciones (opcional) <input name="income_file" type="file" accept=".xlsx,.xls"></label>
    <label>Apalancamiento <b class="down">*</b> <input name="leverage" type="number" min="1" step="any" required placeholder="obligatorio"></label>
    <label>Capital inicial USDT <input name="starting_capital_usdt" type="number" step="any" value="0"></label>
    <label>Saldo real USDT <input name="current_balance_usdt" type="number" step="any" placeholder="opcional"></label>
    <label>TRM (COP) <input name="trm" type="number" step="any" placeholder="opcional"></label>
    <button class="btn">Reconstruir bitácora</button></form>
    <p class="muted">El apalancamiento no viene en ningún export de Binance: debes indicarlo, no se asume.
    Los archivos se procesan en tu API local; no se guardan.</p><div id="bi-out"></div>`
  const out = el.querySelector<HTMLElement>('#bi-out')!
  el.querySelector<HTMLFormElement>('#bi-f')!.onsubmit = async (ev) => {
    ev.preventDefault()
    const fd = new FormData(ev.target as HTMLFormElement)
    for (const [k, v] of [...fd.entries()]) if (v === '' || (v instanceof File && !v.size)) fd.delete(k)
    out.textContent = 'Procesando…'
    try { out.innerHTML = renderBitacora(await postMore('bitacora', fd)) }
    catch (e) { out.innerHTML = `<div class="alert bad">${esc((e as Error).message)}</div>` }
  }
}

function renderBitacora(j: Json): string {
  const s = j.summary
  const bySrc: Record<string, number> = {}
  for (const t of j.trades) bySrc[t.pnl_source] = (bySrc[t.pnl_source] ?? 0) + 1
  const when = (iso: string): string => esc(iso.slice(0, 16).replace('T', ' '))
  const rows = j.trades.map((t: Json) => `<tr><td>${esc(t.symbol)}</td><td>${esc(t.side)}</td><td class="num">${fmt(t.qty, 4)}</td>
    <td>${when(t.open_time)}</td><td>${when(t.close_time)}</td>
    <td class="num">${fmt(t.entry_price)}</td><td class="num">${fmt(t.exit_price)}</td><td class="num">${fmt(t.pct_return)}%</td>
    <td class="num ${t.pnl_usdt >= 0 ? 'up' : 'down'}">${fmt(t.pnl_usdt)}</td><td class="num">${fmt(t.saldo_usdt)}</td>
    <td>${esc(SRC_LABEL[t.pnl_source] ?? t.pnl_source)} · ${t.pnl_basis === 'bruta' ? 'bruta' : 'neta'}</td></tr>`).join('')
  const mix = Object.entries(bySrc).map(([k, n]) => `${n} ${esc(SRC_LABEL[k] ?? k)}`).join(' · ')
  return `<div class="kpi-row">
    <div class="kpi"><b>${s.total_trades}</b><span>operaciones</span></div>
    <div class="kpi"><b>${fmt(s.win_rate_pct, 1)}%</b><span>acierto</span></div>
    <div class="kpi"><b class="${s.total_pnl_usdt >= 0 ? 'up' : 'down'}">${fmt(s.total_pnl_usdt)}</b><span>PnL USDT</span></div>
    <div class="kpi"><b>${fmt(s.final_saldo_usdt)}</b><span>saldo final USDT</span></div></div>
    <div class="alert">Fuente de la PnL (ledger &gt; historial &gt; estimado): ${mix}. Verificadas: ${s.verified_trades} · estimadas: ${s.estimated_trades}.<br>
    Apalancamiento ${s.leverage}× (${esc(s.leverage_source)}) · saldo: ${esc(s.capital_source)}.</div>
    <table class="mt"><tr><th>Símbolo</th><th>Lado</th><th>Cant.</th><th>Apertura</th><th>Cierre</th><th>Entrada</th><th>Salida</th><th>%</th><th>PnL</th><th>Saldo</th><th>Fuente PnL</th></tr>${rows}</table>`
}
