/** Cliente de los endpoints `/v2/more/*` ("Más análisis") y utilidades de formato. */
import { HIDDEN_ASSETS, SYMBOLS } from './api'
import { bogIso } from './tz'

const base = (): string =>
  (import.meta.env.VITE_API_URL as string | undefined) ?? `http://${location.hostname}:8000`

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Json = any

async function parse(r: Response): Promise<Json> {
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    const d = body.detail
    throw new Error(typeof d === 'string' ? d : JSON.stringify(d ?? r.statusText))
  }
  return r.json()
}

export const getMore = (path: string, params: Record<string, string | number>): Promise<Json> =>
  fetch(`${base()}/v2/more/${path}?${new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)]))}`).then(parse)

export const postMore = (path: string, form: FormData): Promise<Json> =>
  fetch(`${base()}/v2/more/${path}`, { method: 'POST', body: form }).then(parse)

const ENT: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
export const esc = (s: unknown): string => String(s ?? '').replace(/[&<>"']/g, (c) => ENT[c])

export const fmt = (n: number | null | undefined, d = 2): string =>
  n === null || n === undefined ? '—'
    : n.toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d })

export const usd = (n: number): string => fmt(n, 0)
export const day = (ms: number): string => bogIso(ms).slice(0, 10)

export const sourceLine = (source: string, cov?: { start: string; end: string } | null): string =>
  `Fuente — ${esc(source)}${cov ? ` · cobertura ${esc(cov.start.slice(0, 10))} → ${esc(cov.end.slice(0, 10))}` : ''}`

/** Activos de contexto sin los que están fuera de foco (p. ej. ETHUSDT); el activo en foco primero. */
export function focusAssets(xs: Json[]): Json[] {
  return xs.filter((a) => !HIDDEN_ASSETS.has(String(a.key)))
    .sort((a, b) => Number(b.key === SYMBOLS[0]) - Number(a.key === SYMBOLS[0]))
}
