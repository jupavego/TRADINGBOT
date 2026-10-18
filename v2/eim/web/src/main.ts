import './style.css'
import './cyber.css'
import './sim.css'
import './setups.css'
import './arb.css'
import './leaders.css'
import './paper.css'
import { fetchAgents, fetchAsofs, fetchJournal, fetchMode, fetchOverlays, fetchReplay, fetchReports, fetchSnapshot, fetchSynthesis, openStream, SYMBOLS, symbolPicker, TIMEFRAMES, type StreamHandle } from './api'
import { PriceChart } from './chart'
import { refreshArbitrage, renderRiver } from './river'
import { latestPerAgent, renderJournal } from './panels'
import { mountLayerBar, showCard } from './layers_ui'
import { ScenarioPanel } from './scenarios_ui'
import { CalibrationPanel } from './calibration_ui'
import { MoreView } from './more'
import { renderLog, TradeMarks } from './trades_ui'
import { RiskPanel } from './risk_ui'
import { OperationPanel } from './operation_ui'
import { TradeSimulator } from './sim_ui'
import { SetupsPanel } from './setups_ui'
import { ArbPanel } from './arb_ui'
import { LeadersPanel } from './leaders_ui'
import { PaperView } from './paper_view'
import { setCalendarClock } from './event_clock'
import { applyTheme, initialTheme, nextTheme, THEME_LABEL, type Theme } from './theme'
import type { AgentInfo, AgentReport, Candle, Mode, StreamMsg, Synthesis } from './types'

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T

const MODE_LABEL: Record<Mode, string> = {
  ANALISIS: 'Análisis', SIMULADO: 'Simulado', TESTNET: 'Testnet', REAL: 'Real',
}
const mode: Mode = 'ANALISIS' // propuestas del gráfico: análisis (no son órdenes)

let symbol: string = SYMBOLS[0]
let tf = '1h'
let link = false
let state: 'connecting' | 'up' | 'down' = 'connecting'
let stream: StreamHandle | null = null
let loadAbort: AbortController | null = null
let lastClose: number | null = null
let infos: AgentInfo[] = []
let latest: AgentReport[] = []
let synthesis: Synthesis | null = null
let journal: AgentReport[] = []
let replaying = false
let asofs: number[] = []
let replayTimer: number | undefined

let theme: Theme = initialTheme()
applyTheme(theme)
const chart = new PriceChart($('chart'))
const more = new MoreView($('more'))
const marks = new TradeMarks(chart)
const scenarios = new ScenarioPanel($('t-esc'), chart, () => ({ symbol, tf }))
const calibration = new CalibrationPanel($('t-cal'), () => ({ symbol, tf }))
const risk = new RiskPanel($('t-plan'), () => ({ symbol, tf }))
const operation = new OperationPanel($('t-op'))
const sim = new TradeSimulator($('simbar'), chart)
const setups = new SetupsPanel($('setups'), (x) => sim.apply(x))
// independiente del par/marco (T39); cada escaneo también repinta el satélite del río
const arb = new ArbPanel($('t-arb'), $('tab-arb'), (p) => refreshArbitrage($('river'), p))
const leaders = new LeadersPanel($('t-lead'), $('tab-lead'))
const paper = new PaperView($('paper')) // bróker simulado (T47): vista propia, modo Simulado
chart.layers.modeLabel = MODE_LABEL[mode]
mountLayerBar($('layerbar'), chart.layers)
chart.chart.subscribeCrosshairMove((p) => {
  const w = $('chart').clientWidth
  showCard($('evcard'), p.point ? chart.layers.hit(p.point.x, p.point.y) : null, p.point?.x ?? 0, p.point?.y ?? 0, w)
})

function paintLive(): void {
  const el = $('live')
  const ok = link && state !== 'down'
  const s = !link ? 'down' : state === 'up' ? 'up' : 'connecting'
  el.dataset.state = s
  el.querySelector('span')!.textContent =
    ok && s === 'up' ? 'En vivo' : !link ? 'Sin conexión' : s === 'down' ? 'Fuente caída' : 'Conectando…'
  const banner = $('banner')
  banner.hidden = ok && s === 'up' || s === 'connecting'
  if (!banner.hidden) {
    banner.textContent = !link
      ? 'Sin conexión con la API — reintentando…'
      : 'La fuente de datos en vivo está caída — mostrando el último dato conocido.'
  }
}

function paintPrice(c: Candle): void {
  const el = $('price')
  el.textContent = c.c.toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (lastClose !== null && c.c !== lastClose) el.dataset.dir = c.c > lastClose ? 'up' : 'down'
  lastClose = c.c
  if (!replaying) sim.setLast(c.c)
}

/** Reloj del próximo evento en la barra superior (T44): siempre con el último dato en vivo. */
function paintClock(): void {
  if (!replaying) setCalendarClock($('evclock'), latest.find((r) => r.agent_id === 'calendar'))
}

function paintAgents(): void {
  renderRiver($('river'), infos, latest, synthesis, tf)
  renderJournal($('journal'), journal)
}

async function loadAgents(signal: AbortSignal): Promise<void> {
  try {
    const [i, r, s] = await Promise.all([
      fetchAgents(symbol, tf, signal), fetchReports(symbol, tf, 200, signal),
      fetchSynthesis(symbol, tf, signal),
    ])
    infos = i; journal = r; latest = latestPerAgent(r); synthesis = s.synthesis
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    infos = []; latest = []; journal = []; synthesis = null
  }
  paintClock()
  paintAgents()
}

async function loadTrades(signal?: AbortSignal): Promise<void> {
  try {
    const [j, a] = await Promise.all([fetchJournal(symbol, tf, signal), fetchAsofs(symbol, tf, signal)])
    marks.set(j.trades)
    renderLog($('trades-log'), j.trades, j.decisions)
    asofs = a
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    marks.set([]); asofs = []
    $('trades-log').innerHTML = '<p class="muted">No se pudo cargar la bitácora.</p>'
  }
  paintReplayBar()
}

function paintReplayBar(): void {
  const bar = $('replay'), range = $<HTMLInputElement>('replay-range')
  bar.hidden = asofs.length < 2
  range.max = String(Math.max(0, asofs.length - 1))
  if (!replaying) range.value = range.max
  bar.dataset.replaying = String(replaying)
  $('replay-live').hidden = !replaying
  $('replay-label').textContent = replaying
    ? `Reproducción · ${new Date(asofs[Number(range.value)]).toISOString().slice(0, 16).replace('T', ' ')} UTC (Simulado)`
    : 'En vivo'
}

async function showReplay(i: number): Promise<void> {
  replaying = true; paintReplayBar(); risk.replayNote()
  try {
    const r = await fetchReplay(symbol, tf, asofs[i])
    if (!replaying || Number($<HTMLInputElement>('replay-range').value) !== i) return
    chart.setData(r.candles, null)
    chart.layers.replace(r.overlays)
    marks.set(r.trades)
    latest = r.reports; synthesis = r.synthesis; paintAgents()
  } catch { $('banner').hidden = false; $('banner').textContent = 'No se pudo reconstruir ese instante.' }
}

function leaveReplay(): void {
  if (!replaying) return
  replaying = false; clearTimeout(replayTimer)
  void load()
}

function onMsg(m: StreamMsg): void {
  if (m.type === 'arbitrage') { arb.push(m); return } // escáner: no depende de la reproducción
  if (replaying) return
  if (m.type === 'status') { state = m.state; paintLive() }
  else if (m.type === 'reports') {
    if (m.symbol !== symbol || m.timeframe !== tf) return
    latest = m.reports as AgentReport[]
    synthesis = m.synthesis
    chart.layers.replace(m.overlays)
    journal = [...latest, ...journal].slice(0, 200)
    paintClock()
    paintAgents()
    void loadTrades()
    void risk.reload()
    setups.soon()
  } else if (m.type === 'tick') {
    if (m.symbol !== symbol || m.timeframe !== tf) return
    state = 'up'; paintLive()
    chart.update(m.candle)
    paintPrice(m.candle)
    if (m.closed) scenarios.setLast(m.candle)
  } else if (m.type === 'forecast') {
    scenarios.push(m.forecast, null)
  } else if (m.type === 'forecast_error') {
    scenarios.fail(m.detail)
  }
}

async function load(): Promise<void> {
  stream?.close(); loadAbort?.abort()
  replaying = false; clearTimeout(replayTimer)
  loadAbort = new AbortController()
  link = false; state = 'connecting'; lastClose = null
  $('price').textContent = '—'; delete $('price').dataset.dir
  paintLive()
  more.setContext(symbol, tf)
  sim.setSymbol(symbol)
  setups.setSymbol(symbol)
  void loadAgents(loadAbort.signal)
  void loadTrades(loadAbort.signal)
  void calibration.reload()
  void risk.reload()
  chart.layers.clear()
  fetchOverlays(symbol, tf, loadAbort.signal).then((o) => chart.layers.replace(o)).catch(() => {})
  try {
    const snap = await fetchSnapshot(symbol, tf, 500, loadAbort.signal)
    chart.setData(snap.candles, snap.forming)
    const last = snap.forming ?? snap.candles[snap.candles.length - 1]
    if (last) paintPrice(last)
    scenarios.setLast(snap.candles[snap.candles.length - 1] ?? null)
    void scenarios.reload()
    const src = Object.entries(snap.sources).map(([k, v]) => `${k}: ${v}`).join(' · ')
    const cov = snap.candles.length
      ? `${new Date(snap.candles[0].t).toISOString().slice(0, 10)} → ` +
        `${new Date(snap.candles[snap.candles.length - 1].t).toISOString().slice(0, 10)}`
      : 'sin datos'
    $('source').textContent = `Fuente — ${src || 'almacén local'} · cobertura ${cov} · ${snap.candles.length} velas`
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    $('banner').hidden = false
    $('banner').textContent = `No se pudo cargar el histórico: ${(e as Error).message}`
  }
  stream = openStream(symbol, tf, onMsg, (up) => { link = up; if (!up) state = 'down'; paintLive() })
}

function build(): void {
  $('symbol-box').innerHTML = symbolPicker('id="symbol"')
  const sel = document.querySelector<HTMLSelectElement>('select#symbol')
  if (sel) sel.onchange = () => { symbol = sel.value; void load() }
  const box = $('tfs')
  box.innerHTML = TIMEFRAMES.map((t) => `<button data-tf="${t}">${t}</button>`).join('')
  const mark = (): void =>
    box.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tf === tf)))
  box.onclick = (e) => {
    const b = (e.target as HTMLElement).closest('button')
    if (!b) return
    tf = b.dataset.tf!; mark(); void load()
  }
  mark()
  const tabs = document.querySelectorAll<HTMLButtonElement>('.tabs button')
  tabs.forEach((b) => {
    b.onclick = () => {
      tabs.forEach((x) => x.setAttribute('aria-selected', String(x === b)))
      document.querySelectorAll<HTMLElement>('.tabbody').forEach((p) => { p.hidden = p.id !== b.dataset.tab })
      if (b.dataset.tab === 't-op') void operation.reload()
      if (b.dataset.tab === 't-arb') void arb.reload()
      if (b.dataset.tab === 't-lead') void leaders.reload()
    }
  })
  const range = $<HTMLInputElement>('replay-range')
  range.oninput = () => {
    const i = Number(range.value)
    clearTimeout(replayTimer)
    if (i >= Number(range.max)) { leaveReplay(); return }
    replayTimer = window.setTimeout(() => void showReplay(i), 120)
    replaying = true; paintReplayBar()
  }
  $('replay-live').onclick = () => leaveReplay()
  const modeEl = $('mode')
  modeEl.textContent = `Modo: ${MODE_LABEL[mode]}`
  // con ejecución en testnet (T30) el servidor manda: la cabecera muestra TESTNET
  void fetchMode().then((m) => {
    if (m === 'TESTNET') { modeEl.textContent = `Modo: ${MODE_LABEL.TESTNET}`; modeEl.dataset.mode = m }
  })
  const themeBtn = $('theme')
  const paintTheme = (): void => { themeBtn.textContent = `Tema: ${THEME_LABEL[theme]}` }
  paintTheme()
  themeBtn.onclick = () => {
    theme = nextTheme(theme)
    applyTheme(theme); paintTheme(); chart.restyle(); more.restyle(); paper.restyle()
  }
  const mb = $<HTMLButtonElement>('more-btn'), pb = $<HTMLButtonElement>('paper-btn')
  // Vistas de pantalla completa: Más análisis y Bróker simulado (una a la vez)
  const show = (view: 'desk' | 'more' | 'paper'): void => {
    if (view !== 'more' && mb.getAttribute('aria-pressed') === 'true') more.toggle(false)
    if (view !== 'paper' && pb.getAttribute('aria-pressed') === 'true') paper.toggle(false)
    mb.setAttribute('aria-pressed', String(view === 'more'))
    pb.setAttribute('aria-pressed', String(view === 'paper'))
    mb.textContent = view === 'more' ? 'Volver a la mesa' : 'Más análisis'
    pb.textContent = view === 'paper' ? 'Volver a la mesa' : 'Bróker simulado'
    modeEl.textContent = `Modo: ${MODE_LABEL[view === 'paper' ? 'SIMULADO' : mode]}`
    if (view === 'more') more.toggle(true)
    if (view === 'paper') paper.toggle(true, symbol)
    if (view === 'desk') document.getElementById('app')!.dataset.view = 'desk'
  }
  mb.onclick = () => show(mb.getAttribute('aria-pressed') === 'true' ? 'desk' : 'more')
  pb.onclick = () => show(pb.getAttribute('aria-pressed') === 'true' ? 'desk' : 'paper')
}

build()
void load()
void arb.reload()
;(window as unknown as { __eim: unknown }).__eim = { chart, layers: chart.layers, scen: chart.scen }
