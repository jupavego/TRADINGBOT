import type { AgentInfo, Overlay, AgentReport, Snapshot, StreamMsg, Decision, Trade, Replay, ForecastSet, Synthesis } from './types'

/** Base de la API: variable VITE_API_URL o el mismo host en el puerto 8000. */
export const base = (): string =>
  (import.meta.env.VITE_API_URL as string | undefined) ?? `http://${location.hostname}:8000`

export const SYMBOLS = ['BTCUSDT', 'ETHUSDT'] as const
export const TIMEFRAMES = ['15m', '1h', '4h'] as const

export async function fetchSnapshot(
  symbol: string, tf: string, n = 500, signal?: AbortSignal,
): Promise<Snapshot> {
  const r = await fetch(`${base()}/v2/snapshot?symbol=${symbol}&tf=${tf}&n=${n}`, { signal })
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(String(body.detail ?? r.statusText))
  }
  return (await r.json()) as Snapshot
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${base()}${path}`, { signal })
  if (!r.ok) throw new Error(r.statusText)
  return (await r.json()) as T
}

export const fetchAgents = (symbol: string, tf: string, signal?: AbortSignal): Promise<AgentInfo[]> =>
  getJson(`/v2/agents?symbol=${symbol}&tf=${tf}`, signal)

export const fetchSynthesis = (
  symbol: string, tf: string, signal?: AbortSignal,
): Promise<{ synthesis: Synthesis | null }> =>
  getJson(`/v2/synthesis?symbol=${symbol}&tf=${tf}`, signal)

export const fetchReports = (
  symbol: string, tf: string, limit = 100, signal?: AbortSignal,
): Promise<AgentReport[]> =>
  getJson(`/v2/reports?symbol=${symbol}&tf=${tf}&limit=${limit}`, signal)

export const fetchOverlays = (symbol: string, tf: string, signal?: AbortSignal): Promise<Overlay[]> =>
  getJson(`/v2/overlays?symbol=${symbol}&tf=${tf}`, signal)

export interface StreamHandle { close(): void }

/** WebSocket con reconexión exponencial. `onLink(false)` = socket caído (sin conexión). */
export function openStream(
  symbol: string, tf: string,
  onMsg: (m: StreamMsg) => void, onLink: (up: boolean) => void,
): StreamHandle {
  let ws: WebSocket | null = null
  let stopped = false
  let backoff = 1000
  let timer: number | undefined

  const connect = (): void => {
    const url = base().replace(/^http/, 'ws') + `/v2/stream?symbol=${symbol}&tf=${tf}`
    ws = new WebSocket(url)
    ws.onopen = () => { backoff = 1000; onLink(true) }
    ws.onmessage = (e) => {
      try { onMsg(JSON.parse(e.data as string) as StreamMsg) } catch { /* mensaje inválido */ }
    }
    ws.onclose = () => {
      if (stopped) return
      onLink(false)
      timer = window.setTimeout(connect, backoff)
      backoff = Math.min(backoff * 2, 15000)
    }
    ws.onerror = () => ws?.close()
  }
  connect()
  return { close() { stopped = true; clearTimeout(timer); ws?.close() } }
}

export const fetchJournal = (
  symbol: string, tf: string, signal?: AbortSignal,
): Promise<{ mode: string; decisions: Decision[]; trades: Trade[] }> =>
  getJson(`/v2/journal?symbol=${symbol}&tf=${tf}`, signal)

export const fetchTrades = (
  symbol: string, tf: string, signal?: AbortSignal,
): Promise<{ mode: string; trades: Trade[] }> => getJson(`/v2/trades?symbol=${symbol}&tf=${tf}`, signal)

export const fetchAsofs = (symbol: string, tf: string, signal?: AbortSignal): Promise<number[]> =>
  getJson(`/v2/replay/asofs?symbol=${symbol}&tf=${tf}`, signal)

export const fetchReplay = (
  symbol: string, tf: string, asof: number, signal?: AbortSignal,
): Promise<Replay> => getJson(`/v2/replay?symbol=${symbol}&tf=${tf}&asof=${asof}`, signal)

export const fetchForecast = (
  symbol: string, tf: string, h: number, signal?: AbortSignal,
): Promise<ForecastSet> => getJson(`/v2/forecast?symbol=${symbol}&tf=${tf}&h=${h}`, signal)

export interface CalibrationReport {
  n_evaluated: number; n_pending: number; n_effective: number; n_backfill?: number; horizon: number
  coverage?: Record<string, { nominal: number; terminal: number | null; pooled: number | null }>
  brier?: number; brier_rw?: number; brier_skill?: number | null
  pinball_skill?: number | null; ece?: number
  directional?: { n: number; accuracy: number | null }
  curve?: { p_pred: number; p_obs: number; n: number }[]
  verdict: string[]; source?: string
}

export const fetchCalibration = (
  symbol: string, tf: string, h: number, signal?: AbortSignal,
): Promise<CalibrationReport> => getJson(`/v2/calibration?symbol=${symbol}&tf=${tf}&h=${h}`, signal)

export async function runBackfill(symbol: string, tf: string, h: number): Promise<CalibrationReport> {
  const r = await fetch(`${base()}/v2/calibration/backfill?symbol=${symbol}&tf=${tf}&h=${h}&origins=800`,
    { method: 'POST' })
  const body = await r.json().catch(() => ({ detail: r.statusText }))
  if (!r.ok) throw new Error(String(body.detail ?? r.statusText))
  return body as CalibrationReport
}

/** Activa o desactiva el kill-switch (T29). La cabecera propia evita peticiones de otros sitios. */
export async function setKillSwitch(on: boolean, reason: string): Promise<void> {
  const r = await fetch(`${base()}/v2/risk/kill-switch/${on ? 'activate' : 'deactivate'}?reason=${encodeURIComponent(reason)}`,
    { method: 'POST', headers: { 'X-EIM-Confirm': 'kill-switch' } })
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(String(body.detail ?? r.statusText))
  }
}

/** Envía el plan vigente aprobado al broker de testnet (T30): el servidor reevalúa el riesgo. */
export async function executePlan(symbol: string, tf: string): Promise<{ executed: boolean }> {
  const r = await fetch(`${base()}/v2/risk/execute?symbol=${symbol}&tf=${tf}`,
    { method: 'POST', headers: { 'X-EIM-Confirm': 'execute' } })
  const body = await r.json().catch(() => ({ detail: r.statusText }))
  if (!r.ok) throw new Error(String(body.detail ?? r.statusText))
  return body as { executed: boolean }
}

/** Modo de operación del servidor (`/v2/health`): TESTNET si hay broker de testnet (T30). */
export async function fetchMode(): Promise<string | null> {
  try {
    const r = await fetch(`${base()}/v2/health`)
    if (!r.ok) return null
    return ((await r.json()) as { mode?: string }).mode ?? null
  } catch {
    return null
  }
}
