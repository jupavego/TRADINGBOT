import './style.css'
import { fetchAgents, fetchReports, fetchSnapshot, openStream, SYMBOLS, TIMEFRAMES, type StreamHandle } from './api'
import { PriceChart } from './chart'
import { latestPerAgent, renderJournal, renderSide } from './panels'
import { applyTheme, initialTheme, type Theme } from './theme'
import type { AgentInfo, AgentReport, Candle, Mode, StreamMsg } from './types'

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T

const MODE_LABEL: Record<Mode, string> = {
  ANALISIS: 'Análisis', SIMULADO: 'Simulado', TESTNET: 'Testnet', REAL: 'Real',
}
const mode: Mode = 'ANALISIS' // hasta T27/T31 la UI no opera

let symbol: string = SYMBOLS[0]
let tf = '1h'
let link = false
let state: 'connecting' | 'up' | 'down' = 'connecting'
let stream: StreamHandle | null = null
let loadAbort: AbortController | null = null
let lastClose: number | null = null
let infos: AgentInfo[] = []
let latest: AgentReport[] = []
let journal: AgentReport[] = []

let theme: Theme = initialTheme()
applyTheme(theme)
const chart = new PriceChart($('chart'))

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

function paintAgents(): void {
  renderSide($('side'), infos, latest)
  renderJournal($('journal'), journal)
}

async function loadAgents(signal: AbortSignal): Promise<void> {
  try {
    const [i, r] = await Promise.all([
      fetchAgents(symbol, tf, signal), fetchReports(symbol, tf, 200, signal),
    ])
    infos = i; journal = r; latest = latestPerAgent(r)
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    infos = []; latest = []; journal = []
  }
  paintAgents()
}

function onMsg(m: StreamMsg): void {
  if (m.type === 'status') { state = m.state; paintLive() }
  else if (m.type === 'reports') {
    if (m.symbol !== symbol || m.timeframe !== tf) return
    latest = m.reports as AgentReport[]
    journal = [...latest, ...journal].slice(0, 200)
    paintAgents()
  } else if (m.type === 'tick') {
    if (m.symbol !== symbol || m.timeframe !== tf) return
    state = 'up'; paintLive()
    chart.update(m.candle)
    paintPrice(m.candle)
  }
}

async function load(): Promise<void> {
  stream?.close(); loadAbort?.abort()
  loadAbort = new AbortController()
  link = false; state = 'connecting'; lastClose = null
  $('price').textContent = '—'; delete $('price').dataset.dir
  paintLive()
  void loadAgents(loadAbort.signal)
  try {
    const snap = await fetchSnapshot(symbol, tf, 500, loadAbort.signal)
    chart.setData(snap.candles, snap.forming)
    const last = snap.forming ?? snap.candles[snap.candles.length - 1]
    if (last) paintPrice(last)
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
  const sel = $<HTMLSelectElement>('symbol')
  sel.innerHTML = SYMBOLS.map((s) => `<option>${s}</option>`).join('')
  sel.onchange = () => { symbol = sel.value; void load() }
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
    }
  })
  const modeEl = $('mode')
  modeEl.textContent = `Modo: ${MODE_LABEL[mode]}`
  $('theme').onclick = () => {
    theme = theme === 'light' ? 'dark' : 'light'
    applyTheme(theme); chart.restyle()
  }
}

build()
void load()
;(window as unknown as { __eim: unknown }).__eim = { chart }
