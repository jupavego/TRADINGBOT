/** Plantilla y pestañas de la vista «Bróker simulado» (separadas de `paper_view.ts`, T118). */
import { symbolPicker } from './api'

export const TABS: [string, string][] = [['live', 'Señales en vivo'], ['pos', 'Posiciones'], ['ord', 'Órdenes abiertas'], ['hist', 'Historial'],
  ['log', 'Bitácora'], ['reg', 'Registro fijo'], ['learn', 'Aprendizaje'], ['prof', 'Perfiles'], ['arb', 'Arbitraje']]
const CHART_TFS = ['15m', '1h', '4h']

export const TEMPLATE = `
<header class="pp-head">
  <h2 class="pp-title">Bróker simulado</h2>
  <span class="mode" data-mode="SIMULADO">Modo: Simulado · papel, sin órdenes reales · dinero real deshabilitado</span>
  ${symbolPicker('data-k="symbol"')}
  <span class="pp-perp">Perpetuo USDT-M</span>
  <b class="price num" data-x="price">—</b>
  <span class="spacer"></span>
  <span class="pp-cov muted" data-x="cov"></span>
  <label class="pp-bt" title="Reconstruye las decisiones de días pasados para que el aprendizaje tenga historial; el servicio en vivo no lo necesita">Historial <select data-k="days"><option value="7">7 días</option><option value="30" selected>30 días</option>
    <option value="60">60 días</option><option value="90">90 días</option></select>
    <select data-k="bttf" aria-label="Temporalidades del backtest"><option value="">15m · 1h · 4h</option>
    <option>15m</option><option>1h</option><option>4h</option></select></label>
  <button class="btn" data-act="bt">Reconstruir historial (backtest)</button>
  <span class="pp-job" data-x="job"></span>
</header>
<div class="pp-scope" data-x="scope" aria-label="Instantánea y alcance de la vista"></div>
<div class="pp-livebar" data-x="live" aria-live="polite"></div>
<section class="pp-balance" data-x="bal" aria-label="Balance de operaciones ganadas y perdidas"></section>
<div class="pp-cards" data-x="cards" role="tablist" aria-label="Perfiles"></div>
<div class="pp-grid">
  <section class="pp-chart"><div class="pp-chart-h"><h4 class="sh">Velas · operaciones del perfil</h4>
    <div class="seg" data-x="ctf" role="group" aria-label="Temporalidad del gráfico">${CHART_TFS.map((t) => `<button type="button" data-ctf="${t}">${t}</button>`).join('')}</div>
    <small class="muted" data-x="src"></small></div>
    <div class="pp-pc" data-x="pc"></div></section>
  <aside class="pp-side">
    <div class="pp-acct" data-x="acct"></div>
    <h4 class="sh">Capital por perfil</h4><div class="pp-eqleg" data-x="eqleg"></div><div class="pp-eq" data-x="eq"></div>
  </aside>
</div>
<p class="alert" data-x="msg" role="status" hidden></p>
<nav class="tabs pp-tabs" role="tablist">${TABS.map(([id, t]) => `<button role="tab" data-t="${id}" aria-selected="${id === 'live'}">${t}<small data-n="${id}"></small></button>`).join('')}</nav>
<div class="pp-body" data-x="body"></div>`
