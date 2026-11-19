/** Formato compartido de la pestaña «Cantera» (T171). */
import type { Stage } from './cantera_api'
import { agentName } from './panels'
import { bogIso } from './tz'

export const STAGE: Record<Stage, string> = {
  guarderia: 'Guardería', cantera: 'Cantera', promesa: 'Promesa', primer_equipo: 'Primer equipo', baja: 'Baja',
}
const AGENT: Record<string, string> = { bots: 'Bots', smart_money: 'Smart money' }
export const agentLabel = (id: string): string => AGENT[id] ?? agentName(id)
export const cot = (t: number | null | undefined): string =>
  t == null ? '—' : bogIso(t).slice(0, 16).replace('T', ' ')
export const num = (x: number, d: number): string =>
  Math.abs(x).toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d })
const sg = (x: number): string => (x > 0 ? '+' : x < 0 ? '−' : '')
export const pc = (x: number | null | undefined, d = 2): string => (x == null ? '—' : `${sg(x)}${num(x, d)} %`)
export const rr = (x: number | null | undefined, d = 2): string => (x == null ? '—' : `${sg(x)}${num(x, d)} R`)
export const usd = (x: number | null | undefined, d = 0): string => (x == null ? '—' : `${num(x, d)} USDT`)
/** Magnitud sin signo (drawdown, topes): «3,1 %». */
export const mag = (x: number | null | undefined, d = 1): string => (x == null ? '—' : `${num(x, d)} %`)
