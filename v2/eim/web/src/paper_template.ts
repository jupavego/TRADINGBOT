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
  <span class="pp-job" data-x="job" title="Puesta al día automática: el servicio analiza solo las velas que faltan (no decidió en tiempo real: cuentan como reconstruidas)"></span>
</header>
<div class="pp-livebar" data-x="live" aria-live="polite"></div>
<section class="pp-gates" data-x="gates" aria-label="Puerta del marco mayor"></section>
<section class="pp-balance" data-x="bal" aria-label="Balance de operaciones ganadas y perdidas"></section>
<section class="pp-eqbox" aria-label="Capital por perfil">
  <div class="pp-eq-h"><h4 class="sh">Capital por perfil</h4>
    <small class="muted">capital realizado + no realizado (USDT) · % frente al capital inicial (línea punteada) ·
      clic en un perfil para verlo abajo (velas, cuenta y pestañas); su línea de color oculta o muestra la curva</small></div>
  <div class="pp-eqrow"><div class="pp-eq" data-x="eq"></div>
    <div class="pp-eqleg" data-x="eqleg" role="group" aria-label="Perfiles: elegir uno y ver su curva de capital"></div></div>
</section>
<div class="pp-grid">
  <section class="pp-chart"><div class="pp-chart-h"><h4 class="sh">Velas · operaciones del perfil</h4>
    <div class="seg" data-x="ctf" role="group" aria-label="Temporalidad del gráfico">${CHART_TFS.map((t) => `<button type="button" data-ctf="${t}">${t}</button>`).join('')}</div>
    <small class="muted" data-x="src"></small></div>
    <div class="pp-pc" data-x="pc"></div></section>
  <aside class="pp-side">
    <div class="pp-acct" data-x="acct"></div>
  </aside>
</div>
<p class="alert" data-x="msg" role="status" hidden></p>
<nav class="tabs pp-tabs" role="tablist">${TABS.map(([id, t]) => `<button role="tab" data-t="${id}" aria-selected="${id === 'live'}">${t}<small data-n="${id}"></small></button>`).join('')}</nav>
<div class="pp-body" data-x="body"></div>`
