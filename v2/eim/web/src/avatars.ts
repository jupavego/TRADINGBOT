/** Avatares de agentes: glifo de línea dentro de un hexágono HUD (estilo futurista).
 *  SVG en línea con `currentColor`: el color lo pone el tono del mosaico (alcista/bajista/neutro). */

const GLYPH: Record<string, string> = {
  // Estructura: capas apiladas
  structure: '<path d="M24 14l10 5-10 5-10-5z"/><path d="M14 24l10 5 10-5"/><path d="M14 29l10 5 10-5"/>',
  // VWAP: precio oscilando alrededor de la media ponderada
  vwap: '<path d="M12 28c3-9 6-9 8-3s5 7 8 0 5-8 8-3"/><path d="M12 24h24" stroke-dasharray="2 2.5"/>',
  // Price action: velas
  price_action: '<path d="M17 13v22M24 16v18M31 12v20"/>' +
    '<rect x="15" y="18" width="4" height="10" class="f"/><rect x="22" y="21" width="4" height="8"/>' +
    '<rect x="29" y="15" width="4" height="12" class="f"/>',
  // Elliott: ondas 1-5 en zigzag
  elliott: '<path d="M11 33l6-9 4 5 6-13 4 7 6-9"/><circle cx="37" cy="14" r="1.6" class="f"/>',
  // EMA / FRM: abanico de medias
  ema: '<path d="M11 32c8-2 14-8 26-17"/><path d="M11 33c9 0 16-4 26-11" opacity=".75"/>' +
    '<path d="M11 34c10 1 18-1 26-5" opacity=".5"/>',
  // Liquidaciones: rayo
  liquidations: '<path d="M27 11l-10 15h7l-3 11 10-15h-7z" class="f"/>',
  // Estacionalidad: órbita anual con marcas de meses
  seasonality: '<circle cx="24" cy="24" r="9"/><circle cx="24" cy="15" r="2" class="f"/>' +
    '<path d="M24 11v-2M24 39v-2M11 24H9M39 24h-2M15 15l-1.5-1.5M33 33l1.5 1.5M33 15l1.5-1.5M15 33l-1.5 1.5"/>',
  // Contexto (LLM): red neuronal
  context: '<circle cx="15" cy="17" r="2"/><circle cx="15" cy="31" r="2"/><circle cx="33" cy="24" r="2.4" class="f"/>' +
    '<circle cx="24" cy="13" r="2"/><circle cx="24" cy="35" r="2"/>' +
    '<path d="M17 17l6-3M17 31l6 3M17 17l14 6M17 31l14-6M26 13l6 9M26 35l6-9"/>',
  // Derivados: funding / OI, flechas en ciclo
  derivatives: '<path d="M33 19a10 10 0 0 0-17-3"/><path d="M15 29a10 10 0 0 0 17 3"/>' +
    '<path d="M16 11v5h5M32 37v-5h-5"/><text x="24" y="27.5" class="t">%</text>',
  // Niveles: soportes y resistencias
  levels: '<path d="M11 16h26M11 32h26" /><path d="M11 24h26" stroke-dasharray="2 2.5" opacity=".6"/>' +
    '<path d="M15 31l5-6 4 3 5-8 4 2"/>',
  // Microestructura: libro de órdenes (bids / asks)
  microstructure: '<path d="M24 12v24" opacity=".5"/><path d="M22 15h-6M22 20h-9M22 25h-5M22 30h-8"/>' +
    '<path d="M26 17h8M26 22h5M26 27h10M26 32h6"/>',
  // Plan: retícula de objetivo
  plan: '<circle cx="24" cy="24" r="9"/><circle cx="24" cy="24" r="3" class="f"/>' +
    '<path d="M24 10v6M24 32v6M10 24h6M32 24h6"/>',
  // Régimen: radar con punto de cambio
  regime: '<path d="M11 30c3 0 3-6 6-6s3 6 6 6" /><path d="M25 22l3-8 3 18 3-12 3 6"/>' +
    '<path d="M24 12v26" stroke-dasharray="1.5 2" opacity=".6"/>',
}

const DEFAULT = '<circle cx="24" cy="24" r="4" class="f"/><circle cx="24" cy="24" r="9" opacity=".5"/>'

/** Hexágono HUD con muescas en las esquinas + glifo del agente. */
export function avatar(id: string): string {
  return '<svg class="avatar" viewBox="0 0 48 48" aria-hidden="true">' +
    '<path class="hex" d="M24 2.5 42.6 13.25v21.5L24 45.5 5.4 34.75v-21.5z"/>' +
    '<path class="notch" d="M24 2.5l4 2.3M24 2.5l-4 2.3M24 45.5l4-2.3M24 45.5l-4-2.3"/>' +
    `<g class="glyph">${GLYPH[id] ?? DEFAULT}</g></svg>`
}
