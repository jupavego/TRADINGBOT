/**
 * Calculadora de operación de futuros USDT-M (estilo Binance, modo one-way).
 * Funciones puras: no tocan el DOM ni la red. Es una SIMULACIÓN, no una orden.
 */

export type Side = 'long' | 'short'
export type MarginMode = 'cross' | 'isolated'
export type OrderType = 'market' | 'limit'
/** En qué se expresa el monto: margen (costo), tamaño nocional o cantidad del activo. */
export type AmountUnit = 'margin' | 'notional' | 'qty'
/** Cómo se escribe el TP/SL: precio, ROE % sobre el margen o % de movimiento del precio. */
export type TargetMode = 'price' | 'roe' | 'move'

export interface SimInput {
  side: Side
  margin: MarginMode
  orderType: OrderType
  leverage: number
  entry: number
  amount: number
  unit: AmountUnit
  tp: number | null
  tpMode: TargetMode
  sl: number | null
  slMode: TargetMode
  balance: number
  makerFee: number // fracción (0.0002 = 0,02 %)
  takerFee: number
  mmr: number // tasa de margen de mantenimiento (fracción)
}

export interface Outcome {
  price: number
  move: number // movimiento del precio (fracción, con signo)
  gross: number // PnL sin comisiones
  fees: number // comisión de entrada + salida
  net: number
  roe: number // PnL bruto / margen inicial (como lo muestra Binance)
  balanceAfter: number
}

export interface SimResult {
  ok: boolean
  qty: number
  notional: number
  margin: number
  entryFee: number
  maxNotional: number
  liq: number | null
  liqDist: number | null // distancia a liquidación (fracción del precio de entrada)
  tp: Outcome | null
  sl: Outcome | null
  rr: number | null
  warnings: string[]
}

export const MAX_LEVERAGE = 125
const dirOf = (s: Side): number => (s === 'long' ? 1 : -1)

/** Convierte el valor escrito en TP/SL a precio. Para SL, ROE y % se escriben en positivo (pérdida). */
export function targetPrice(kind: 'tp' | 'sl', value: number | null, mode: TargetMode, entry: number, side: Side, lev: number): number | null {
  if (value === null || !Number.isFinite(value) || value <= 0 || entry <= 0) return null
  if (mode === 'price') return value
  const sign = dirOf(side) * (kind === 'tp' ? 1 : -1)
  const move = mode === 'roe' ? value / 100 / lev : value / 100
  const p = entry * (1 + sign * move)
  return p > 0 ? p : null
}

/** Nocional a partir del monto en su unidad. */
export function notionalOf(amount: number, unit: AmountUnit, entry: number, lev: number): number {
  if (unit === 'margin') return amount * lev
  if (unit === 'qty') return amount * entry
  return amount
}

/** Pasa un nocional a la unidad pedida (para el deslizador de % del saldo). */
export function amountFromNotional(notional: number, unit: AmountUnit, entry: number, lev: number): number {
  if (unit === 'margin') return notional / lev
  if (unit === 'qty') return entry > 0 ? notional / entry : 0
  return notional
}

/**
 * Precio de liquidación aproximado (fórmula de Binance con importe de mantenimiento 0, una sola posición).
 * Cruzado: respalda todo el saldo; aislado: solo el margen de la posición.
 */
export function liquidationPrice(side: Side, qty: number, entry: number, wallet: number, mmr: number): number | null {
  if (qty <= 0) return null
  const d = dirOf(side)
  const lp = (wallet - d * qty * entry) / (qty * mmr - d * qty)
  return Number.isFinite(lp) && lp > 0 ? lp : null
}

function outcome(price: number, inp: SimInput, qty: number, margin: number, entryFee: number): Outcome {
  const d = dirOf(inp.side)
  const gross = d * qty * (price - inp.entry)
  const fees = entryFee + qty * price * inp.takerFee // TP/SL se disparan como orden a mercado
  const net = gross - fees
  return {
    price, move: (price - inp.entry) / inp.entry, gross, fees, net,
    roe: margin > 0 ? gross / margin : 0, balanceAfter: inp.balance + net,
  }
}

export function simulate(inp: SimInput): SimResult {
  const lev = Math.min(MAX_LEVERAGE, Math.max(1, Math.round(inp.leverage)))
  const warnings: string[] = []
  const notional = inp.entry > 0 && inp.amount > 0 ? notionalOf(inp.amount, inp.unit, inp.entry, lev) : 0
  const qty = notional > 0 ? notional / inp.entry : 0
  const margin = notional / lev
  const entryFee = notional * (inp.orderType === 'market' ? inp.takerFee : inp.makerFee)
  const maxNotional = Math.max(0, inp.balance) * lev
  const empty: SimResult = {
    ok: false, qty, notional, margin, entryFee, maxNotional, liq: null, liqDist: null, tp: null, sl: null, rr: null, warnings,
  }
  if (inp.entry <= 0) { warnings.push('Falta el precio de entrada.'); return empty }
  if (notional <= 0) { warnings.push('Escribe un monto para simular la operación.'); return empty }

  const wallet = inp.margin === 'isolated' ? margin : inp.balance
  const liq = liquidationPrice(inp.side, qty, inp.entry, wallet, inp.mmr)
  const liqDist = liq === null ? null : Math.abs(liq - inp.entry) / inp.entry
  const tpP = targetPrice('tp', inp.tp, inp.tpMode, inp.entry, inp.side, lev)
  const slP = targetPrice('sl', inp.sl, inp.slMode, inp.entry, inp.side, lev)
  const d = dirOf(inp.side)

  if (margin + entryFee > inp.balance) warnings.push('El margen más la comisión supera el saldo disponible.')
  if (tpP !== null && d * (tpP - inp.entry) <= 0)
    warnings.push(`El take profit de un ${inp.side === 'long' ? 'long debe estar por encima' : 'short debe estar por debajo'} de la entrada.`)
  if (slP !== null && d * (slP - inp.entry) >= 0)
    warnings.push(`El stop loss de un ${inp.side === 'long' ? 'long debe estar por debajo' : 'short debe estar por encima'} de la entrada.`)
  if (slP !== null && liq !== null && d * (slP - liq) <= 0)
    warnings.push('El stop loss está más allá del precio de liquidación: te liquidarían antes de tocarlo.')
  if (tpP !== null && liq !== null && d * (tpP - liq) <= 0)
    warnings.push('El take profit está más allá del precio de liquidación.')
  if (slP === null)
    warnings.push(inp.margin === 'isolated'
      ? 'Sin stop loss: puedes perder todo el margen de la posición.'
      : 'Sin stop loss en cruzado: la liquidación compromete el saldo de la cuenta.')

  const tp = tpP === null ? null : outcome(tpP, inp, qty, margin, entryFee)
  const sl = slP === null ? null : outcome(slP, inp, qty, margin, entryFee)
  const rr = tp && sl && sl.net < 0 && tp.net > 0 ? tp.net / -sl.net : null
  return { ok: true, qty, notional, margin, entryFee, maxNotional, liq, liqDist, tp, sl, rr, warnings }
}
