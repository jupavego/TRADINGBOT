import type { AgentInfo, AgentReport, Snapshot, StreamMsg } from './types'

/** Base de la API: variable VITE_API_URL o el mismo host en el puerto 8000. */
const base = (): string =>
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

export const fetchReports = (
  symbol: string, tf: string, limit = 100, signal?: AbortSignal,
): Promise<AgentReport[]> =>
  getJson(`/v2/reports?symbol=${symbol}&tf=${tf}&limit=${limit}`, signal)

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
