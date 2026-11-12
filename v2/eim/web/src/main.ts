import './style.css'
import './cyber.css'
import './setups.css'
import './arb.css'
import './leaders.css'
import './squad.css'
import { SquadPanel } from './squad_ui'
import './paper.css'
import './obs.css'
import './obs_trace.css'
import { fetchAgents, fetchJournal, fetchMicroStatus, fetchMode, fetchReports, fetchSnapshot, fetchSynthesis, openStream, SYMBOLS, symbolPicker, TIMEFRAMES, type StreamHandle } from './api'
import { refreshArbitrage, renderRiver } from './river'
import { latestPerAgent, renderJournal } from './panels'
import { LibraryPanel } from './library_ui'
import { ScenarioPanel } from './scenarios_ui'
import { CalibrationPanel } from './calibration_ui'
import { MoreView } from './more'
import { renderLog } from './trades_ui'
import { RiskPanel } from './risk_ui'
import { OperationPanel } from './operation_ui'
import { SetupsHistory } from './setups_history'
import { ArbPanel } from './arb_ui'
import { LeadersPanel } from './leaders_ui'
import { PaperView } from './paper_view'
import { ObsView } from './obs_view'
import { setCalendarClock } from './event_clock'
import { setCollectorState } from './no_data_label'
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

// Sin gráfico de velas ni simulador en la mesa: el río, el mapa del sistema y el bróker
// simulado (bajo el mapa) cuentan la decisión; el bróker trae su propio gráfico por perfil.
const more = new MoreView($('more'))
let squadSupport: SquadPanel | null = null
const scenarios = new ScenarioPanel($('t-esc'), null, () => ({ symbol, tf }),
  () => latest.find((r) => r.agent_id === 'literature'), () => squadSupport?.support ?? null)
const calibration = new CalibrationPanel($('t-cal'), () => ({ symbol, tf }))
const risk = new RiskPanel($('t-plan'), () => ({ symbol, tf }))
const operation = new OperationPanel($('t-op'))
const library = new LibraryPanel($('t-lib'), () => $('mode').textContent ?? '')
const setupsHistory = new SetupsHistory($('t-hist')) // T51; pestaña inferior tras Bitácora (T122)
// independiente del par/marco (T39); cada escaneo también repinta el satélite del río
const arb = new ArbPanel($('t-arb'), $('tab-arb'), (p) => refreshArbitrage($('river'), p))
const leaders = new LeadersPanel($('t-lead'), $('tab-lead'))
const squad = new SquadPanel($('t-squad'), () => ({ symbol, tf }), () => scenarios.refresh()) // T60
squadSupport = squad
const obs = new ObsView($('obs')) // Mapa del sistema (T75), en la mesa bajo el río (T122)
const paper = new PaperView($('paper')) // bróker simulado (T47): en la mesa, bajo el mapa del sistema; modo Simulado en su cabecera

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
}

/** Reloj del próximo evento en la barra superior (T44): siempre con el último dato en vivo. */
function paintClock(): void {
  setCalendarClock($('evclock'), latest.find((r) => r.agent_id === 'calendar'))
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
    // T120: el estado del recolector manda sobre el motivo del agente (sin él, no se inventa nada)
    setCollectorState('microstructure', await fetchMicroStatus(symbol, signal).catch((e) => {
      if ((e as Error).name === 'AbortError') throw e
      return null
    }))
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    infos = []; latest = []; journal = []; synthesis = null
  }
  paintClock()
  paintAgents()
}

async function loadTrades(signal?: AbortSignal): Promise<void> {
  try {
    const j = await fetchJournal(symbol, tf, signal)
    renderLog($('trades-log'), j.trades, j.decisions)
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    $('trades-log').innerHTML = '<p class="muted">No se pudo cargar la bitácora.</p>'
  }
}

function onMsg(m: StreamMsg): void {
  if (m.type === 'arbitrage') { arb.push(m); return } // escáner: no depende de la reproducción
  if (m.type === 'status') { state = m.state; paintLive() }
  else if (m.type === 'reports') {
    if (m.symbol !== symbol || m.timeframe !== tf) return
    latest = m.reports as AgentReport[]
    synthesis = m.synthesis
    journal = [...latest, ...journal].slice(0, 200)
    paintClock()
    paintAgents()
    scenarios.refresh()
    void loadTrades()
    void risk.reload()
    setupsHistory.soon()
  } else if (m.type === 'tick') {
    if (m.symbol !== symbol || m.timeframe !== tf) return
    state = 'up'; paintLive()
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
  loadAbort = new AbortController()
  link = false; state = 'connecting'; lastClose = null
  $('price').textContent = '—'; delete $('price').dataset.dir
  paintLive()
  more.setContext(symbol, tf)
  setupsHistory.setSymbol(symbol)
  void loadAgents(loadAbort.signal)
  void loadTrades(loadAbort.signal)
  void calibration.reload()
  void risk.reload()
  try {
    const snap = await fetchSnapshot(symbol, tf, 500, loadAbort.signal)
    const last = snap.forming ?? snap.candles[snap.candles.length - 1]
    if (last) paintPrice(last)
    scenarios.setLast(snap.candles[snap.candles.length - 1] ?? null)
    void scenarios.reload()
    void squad.reload()
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
      if (b.dataset.tab === 't-squad') void squad.reload()
      if (b.dataset.tab === 't-lib') void library.reload()
      setupsHistory.show(b.dataset.tab === 't-hist')
    }
  })
  const modeEl = $('mode')
  modeEl.textContent = `Modo: ${MODE_LABEL[mode]}`
  // con ejecución en testnet (T30) el servidor manda: la cabecera muestra TESTNET
  void fetchMode().then((m) => {
    if (m === 'TESTNET') { modeEl.textContent = `Modo: ${MODE_LABEL.TESTNET}`; modeEl.dataset.mode = m }
  })
  const mb = $<HTMLButtonElement>('more-btn')
  // Única vista de pantalla completa: Más análisis. El mapa del sistema (T122) y el bróker
  // simulado viven en la mesa, uno debajo del otro.
  const show = (view: 'desk' | 'more'): void => {
    mb.setAttribute('aria-pressed', String(view === 'more'))
    mb.textContent = view === 'more' ? 'Volver a la mesa' : 'Más análisis'
    more.toggle(view === 'more')
  }
  mb.onclick = () => show(mb.getAttribute('aria-pressed') === 'true' ? 'desk' : 'more')
  // «Ver la validación en Bróker simulado» (operaciones sugeridas): baja hasta el bróker
  window.addEventListener('eim:open-paper', () => {
    show('desk')
    $('paper').scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

build()
obs.mount()
paper.toggle(true, symbol)
void load()
void arb.reload()
