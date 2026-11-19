/** Qué pieza va en qué zona de cada sala del mapa isométrico (gramática en `obs_iso_eco`). Para una pieza
 * nueva basta con añadir su id a la zona que le toca; si no se añade, cae en la zona por defecto de su sala
 * (`fallback`) o en la que acepte su tipo (`pick`), y si es planeada, en obra. El orden de `ids` es el orden
 * de los puestos dentro de la zona: lo que sale directo a otra sala va cerca de su salida. */
import type { ObsComp } from './obs_types'

export type Zone = 'back' | 'left' | 'center' | 'side' | 'hub' | 'obra'
export const ZONES: Zone[] = ['back', 'left', 'center', 'side', 'hub', 'obra']

export interface ZoneDef { label: string; ids?: string[]; pick?: (c: ObsComp) => boolean; tint?: string }
export interface StageSpec { zones: Partial<Record<Zone, ZoneDef>>; fallback: Zone }

export const continuo = (c: ObsComp): boolean => /continuo/i.test(c.cadence ?? '')
const VIGIL = '#2ee6ff', ARCHIVO = '#7d8aa6'

export const SPECS: Record<string, StageSpec> = {
  /** 1 · Llega del mercado por las ventanillas; lo continuo escucha junto a las pantallas; el archivo guarda
   * velas; la fotografía junta todo y lo reparte. */
  datos: { fallback: 'back', zones: {
    back: { label: 'Ventanillas · fuentes externas', ids: ['data.binance_rest', 'data.liquidations', 'data.news', 'data.calendar', 'leaders.service', 'data.arb_market'] },
    left: { label: 'Monitoreo continuo', tint: VIGIL, ids: ['data.micro_collector', 'data.liq_collector', 'data.live_ticks', 'data.hft_collector'], pick: continuo },
    side: { label: 'Archivo', tint: ARCHIVO, ids: ['data.store'], pick: (c) => c.kind === 'store' },
    hub: { label: 'Fotografía · reparto', ids: ['data.snapshot'] },
  } },
  /** 2 · Los analistas de la mesa opinan y la opinión conjunta los consolida; los informantes directos van
   * al riesgo o a la biblioteca sin pasar por ella; el escuadrón de bots trabaja en cadena junto a la pared. */
  analisis: { fallback: 'center', zones: {
    back: { label: 'Informantes directos', ids: ['agent.calendar', 'agent.context', 'agent.literature', 'agent.arbitrage', 'arbitrage.engine'] },
    left: { label: 'Escuadrón de bots', tint: VIGIL, ids: ['bots.runner', 'agent.bots', 'bots.vote'] },
    center: { label: 'Mesa de analistas', ids: ['agent.structure', 'agent.levels', 'agent.ema', 'agent.vwap', 'agent.price_action', 'agent.technical', 'agent.elliott',
      'agent.seasonality', 'agent.regime', 'agent.derivatives', 'agent.liquidations', 'agent.microstructure', 'agent.smart_money'] },
    hub: { label: 'Opinión conjunta', ids: ['synthesis.thesis', 'api.hub'] },
  } },
  /** 3 · Una sola mesa: simula futuros y los resume en escenarios. */
  proyeccion: { fallback: 'hub', zones: {
    hub: { label: 'Escenarios', ids: ['forecast.engine'] },
  } },
  /** 4 · El plan se arma al frente y se muestra en el panel en vivo del fondo. */
  plan: { fallback: 'center', zones: {
    back: { label: 'Panel en vivo', ids: ['web.dashboard'], pick: (c) => c.kind === 'view' },
    hub: { label: 'Plan de operación', ids: ['agent.plan'] },
  } },
  /** 5 · Todo entra por la puerta única; el interruptor vigila desde la pared; cada carril tiene su riesgo;
   * el motor principal decide y el registro guarda cada decisión. */
  riesgo: { fallback: 'center', zones: {
    back: { label: 'Puerta de entrada', ids: ['risk.authority'] },
    left: { label: 'Interruptor', tint: '#ff4d5e', ids: ['risk.killswitch'] },
    center: { label: 'Riesgo por carril', ids: ['risk.arb_engine', 'risk.hft_engine'] },
    side: { label: 'Registro', tint: ARCHIVO, ids: ['risk.journal'], pick: (c) => c.kind === 'store' },
    hub: { label: 'Motor de riesgo', ids: ['risk.engine'] },
  } },
  /** 6 · Las órdenes entran por sus puertas, la mesa las ejecuta y reconcilia, la sala de control vigila el
   * ciclo y los libros llevan el resultado a validación. */
  ejecucion: { fallback: 'center', zones: {
    back: { label: 'Puertas de órdenes', ids: ['execution.gateway', 'execution.hft', 'arbitrage.executor'] },
    left: { label: 'Sala de control', tint: VIGIL, ids: ['operation.cycle', 'operation.supervisor', 'operation.watchdog', 'operation.alerts'] },
    center: { label: 'Mesa de ejecución', ids: ['execution.service', 'execution.sim_broker', 'execution.testnet_broker', 'execution.reconcile', 'leaders.copy_sim'] },
    hub: { label: 'Libros → validación', ids: ['paper.broker', 'execution.sim_ledger'] },
  } },
  /** 7 · Los resultados llegan a recepción, el laboratorio los pone a prueba, el observatorio vigila y lo
   * aprendido vuelve al análisis (nuevo ciclo); la biblioteca se consulta al lado. */
  validacion: { fallback: 'center', zones: {
    back: { label: 'Recepción de resultados', ids: ['validation.gate', 'validation.setups_publisher', 'operation.experience_sync', 'operation.report', 'forecast.calibration'] },
    left: { label: 'Observatorio', tint: VIGIL, ids: ['observability.indexer', 'observability.map', 'observability.traces', 'operation.backup'] },
    center: { label: 'Laboratorio', ids: ['backtest.engine', 'calibration.optimizer', 'validation.edge_gate', 'validation.setups_followup'] },
    side: { label: 'Biblioteca', tint: ARCHIVO, ids: ['library.query'] },
    hub: { label: 'Aprendizaje → nuevo ciclo', ids: ['bots.scoring', 'library.cards'] },
  } },
}
