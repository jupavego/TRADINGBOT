/** Formato y peticiones del bróker simulado. */
import { base } from './api'
import { bogIso } from './tz'

export const esc = (s: string): string => s.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`)
export const nf = (x: number, d = 2): string =>
  x.toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d })
const sg = (x: number): string => (x > 0 ? '+' : x < 0 ? '−' : '')
export const usd = (x: number, d = 2): string => `${sg(x)}${nf(Math.abs(x), d)}`
export const pct = (x: number | null, d = 2): string => (x === null ? '—' : `${sg(x)}${nf(Math.abs(x * 100), d)} %`)
export const pct0 = (x: number | null): string => (x === null ? '—' : `${Math.round(x * 100)} %`)
export const rr = (x: number | null | undefined, d = 2): string => (x === null || x === undefined ? '—' : `${sg(x)}${nf(Math.abs(x), d)} R`)
export const tone = (x: number | null | undefined): string => (!x ? 'flat' : x > 0 ? 'up' : 'down')
export const side = (s: number): string => (s > 0 ? 'Largo' : 'Corto')
export const utc = (t: number): string => bogIso(t).slice(0, 16).replace('T', ' ')
export const day = (t: number): string => bogIso(t).slice(0, 10)
export const hm = (t: number): string => bogIso(t).slice(11, 16)

/** Duración legible: «3 h 20 min», «2 d 4 h». */
export function dur(ms: number): string {
  const m = Math.max(0, Math.round(ms / 60_000))
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  if (h < 48) return `${h} h${m % 60 ? ` ${m % 60} min` : ''}`
  return `${Math.floor(h / 24)} d ${h % 24} h`
}

/** Decimales de precio según el activo. */
export const px = (x: number): string => nf(x, x >= 1000 ? 1 : 2)
export const qty = (x: number, sym: string): string => `${nf(x, sym.startsWith('BTC') ? 4 : 3)} ${sym.replace(/USDT$/, '')}`

/** Error HTTP del bróker simulado; 503 = la vista aún se está calculando (se reintenta sola). */
export class PaperError extends Error {
  constructor(message: string, readonly status: number) { super(message) }
}

export async function getPaper<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${base()}/v2/paper${path}`, { signal })
  const body = await r.json().catch(() => ({ detail: r.statusText }))
  if (!r.ok) throw new PaperError(String((body as { detail?: string }).detail ?? r.statusText), r.status)
  return body as T
}

export async function postPaper<T>(path: string): Promise<T> {
  const r = await fetch(`${base()}/v2/paper${path}`, { method: 'POST', headers: { 'X-EIM-Confirm': 'paper-backtest' } })
  const body = await r.json().catch(() => ({ detail: r.statusText }))
  if (!r.ok) throw new Error(String((body as { detail?: string }).detail ?? r.statusText))
  return body as T
}

export const CAT_LABEL: Record<string, string> = {
  orden: 'Orden', llenada: 'Llenada', tp: 'Take profit', be: 'Break-even +', sl: 'Stop loss', tiempo: 'Por tiempo',
  liquidacion: 'Liquidación', salvaguarda: 'Salvaguarda', cuenta: 'Cuenta', cancelada: 'Cancelada', rechazada: 'Rechazada',
  aprendizaje: 'Aprendizaje', violacion: 'Violación de reglas',
}
export const REASON: Record<string, string> = {
  TP: 'Take profit', SL: 'Stop loss', SLD: 'SL dinámico (escalón)', BE: 'Break-even +', TIEMPO: 'Por tiempo',
  LIQUIDACION: 'Liquidación (margen perdido)', SALVAGUARDA: 'Salvaguarda (kill-switch)', NO_LLENADA: 'No llenada',
  OBJETIVO_SIN_LLENAR: 'Objetivo sin llenar', GEOMETRIA: 'Precio ya fuera', '': '—',
}
export const STATUS: Record<string, string> = {
  CERRADA: 'Cerrada', ABIERTA: 'Abierta', PENDIENTE: 'Pendiente', CANCELADA: 'Cancelada', RECHAZADA: 'Rechazada',
}
/** Causa de una pérdida (T48), en corto. */
export const CAUSE: Record<string, string> = {
  direccion: 'dirección equivocada', sl_rapido: 'SL rápido', casi_tp: 'casi TP', tiempo: 'por tiempo', costos: 'por costos',
}
