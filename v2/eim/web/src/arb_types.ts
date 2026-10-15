import type { AgentReport } from './types'

/** Contratos del escáner de arbitraje (T39): `GET /v2/arbitrage/opportunities` y WS `arbitrage`. */
export type ArbStrategy = 'funding_carry' | 'basis' | 'triangular' | 'related_perps'

export interface ArbLeg {
  text: string; market: 'spot' | 'usdm' | 'usdcm'; symbol: string; side: 'buy' | 'sell'
  action: 'open' | 'close'; qty: number; filled: number; vwap: number; mid: number
  fee_rate: number; fee: number; slippage: number; levels: number; complete: boolean
}

export interface ArbRisk { legging: number; basis: number; liquidation: number; liquidity: number }

export interface ArbRow {
  id: string; strategy: ArbStrategy; variant: string; asset: string; legs: ArbLeg[]
  gross: number
  costs: { fees: number; slippage: number; funding: number; borrow: number; total: number }
  net: number; net_bps: number; annualized: number | null; capital: number; horizon_h: number
  risk: ArbRisk; risk_notes: Record<string, string>; valid_until: number; executable: boolean
  source: string; selected: boolean; score: number | null; reject_code: string | null
  reason: string | null; details: Record<string, number | string | null>; warnings: string[]
}

export interface ArbAlert {
  key: string; strategy: ArbStrategy; asset: string; variant: string; since: number; asof: number
  held_s: number; net_bps: number; score: number; annualized: number | null; active: boolean; new: boolean
}

export interface ArbFunding {
  symbol: string; margin: string; history: [number, number][]; realized_mean: number | null
  realized_n: number; predicted: number | null; predicted_annual?: number
  realized_annual?: number | null; next_funding_t?: number; interval_h?: number
  premium_bps?: number; error?: string; source?: string | null
}

export interface ArbBasis {
  asset: string; contract: string | null; vs: string | null; kind?: 'perpetual' | 'quarterly'
  delivery_t?: number | null; days?: number | null; basis_bps?: number; annualized?: number | null
  error?: string
}

export interface ArbScanInfo {
  strategy: ArbStrategy; label: string; status: 'ok' | 'degraded' | 'no_data'; valued: number
  missing: string[]; warnings: string[]
}

export interface ArbMetrics {
  mode: string; label: string; scan_asof: number; age_s: number
  quality: { freshness: number; depth: number; coverage: number; books: number; min_levels: number }
  notional_usd: number
  cost_model: { spot_vip: number; futures_vip: number; bnb_discount: boolean; role: string; source: string }
  counts: { valued: number; selected: number; rejected: number }
  rejected_by_code: Record<string, number>
  funding: Record<string, ArbFunding>; basis: ArbBasis[]; scans: ArbScanInfo[]
  sources: Record<string, string>
}

export interface ArbPayload {
  type: 'arbitrage'; mode: string; label: string; now: number; scan_asof: number | null
  age_s: number | null; stale: boolean; report: AgentReport; opportunities: ArbRow[]
  alerts: ArbAlert[]; alert_params: { min_score: number; hold_s: number }
  errors: Record<string, string>
}
