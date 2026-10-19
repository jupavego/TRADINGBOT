/**
 * Agentes del río como esferas 3D holográficas con su icono futurista dentro.
 * SVG puro: degradado radial (luz arriba-izquierda, borde en sombra), brillo especular,
 * ecuador y un meridiano que gira, sombra en el suelo y el glifo del agente iluminado.
 * El color es el del sesgo del agente (verde compra, rojo venta, gris neutro/sin datos).
 */

// Glifos en una caja de 48×48 (trazo; `.f` = relleno translúcido, `.t` = texto).
export const GLYPH: Record<string, string> = {
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
  // Técnico: osciladores apilados por familia (tablero de indicadores)
  technical: '<path d="M12 17h24M12 24h24M12 31h24" opacity=".45"/>' +
    '<circle cx="18" cy="17" r="2.2" class="f"/><circle cx="29" cy="24" r="2.2" class="f"/>' +
    '<circle cx="22" cy="31" r="2.2" class="f"/>',
  // Calendario: hoja de calendario con un evento marcado
  calendar: '<rect x="13" y="15" width="22" height="20" rx="2"/><path d="M13 21h22M18 12v5M30 12v5"/>' +
    '<rect x="25" y="26" width="5" height="5" class="f"/>',
  // Arbitraje: dos patas opuestas (compra / venta) entre dos mercados
  arbitrage: '<path d="M13 19h20l-4-4M35 29H15l4 4"/><circle cx="24" cy="24" r="1.8" class="f"/>',
  // Smart money: líderes aprobados (nodo central y seguidores)
  smart_money: '<circle cx="24" cy="17" r="4" class="f"/><circle cx="14" cy="32" r="3"/>' +
    '<circle cx="34" cy="32" r="3"/><path d="M21 20l-5 9M27 20l5 9M17 32h14"/>',
  // Literatura: libro abierto con una marca de cita
  literature: '<path d="M24 17c-3-2-8-2-11-1v17c3-1 8-1 11 1 3-2 8-2 11-1V16c-3-1-8-1-11 1z"/>' +
    '<path d="M24 17v17" opacity=".5"/><circle cx="30" cy="22" r="1.8" class="f"/>',
  // Plan: retícula de objetivo
  plan: '<circle cx="24" cy="24" r="9"/><circle cx="24" cy="24" r="3" class="f"/>' +
    '<path d="M24 10v6M24 32v6M10 24h6M32 24h6"/>',
  // Régimen: radar con punto de cambio
  regime: '<path d="M11 30c3 0 3-6 6-6s3 6 6 6" /><path d="M25 22l3-8 3 18 3-12 3 6"/>' +
    '<path d="M24 12v26" stroke-dasharray="1.5 2" opacity=".6"/>',
}

const DEFAULT = '<circle cx="24" cy="24" r="4" class="f"/><circle cx="24" cy="24" r="9" opacity=".5"/>'

/** Esfera 3D de un agente centrada en (x, y) con radio `r`. `k` hace únicos los ids. */
export function orb(id: string, x: number, y: number, r: number, col: string, live: boolean, k: number): string {
  const g = `og${k}`, c = `oc${k}`
  const s = (r * 1.6) / 48 // el glifo ocupa ~1,6 r
  const ry = (r * 0.32).toFixed(1)
  return `<defs><radialGradient id="${g}" cx="36%" cy="30%" r="78%">` +
    // cristal: centro casi transparente y borde más denso (efecto Fresnel)
    `<stop offset="0" style="stop-color:color-mix(in srgb, ${col} 40%, #fff);stop-opacity:.32"/>` +
    `<stop offset=".55" style="stop-color:${col};stop-opacity:.18"/>` +
    `<stop offset=".85" style="stop-color:${col};stop-opacity:.42"/>` +
    `<stop offset="1" style="stop-color:${col};stop-opacity:.75"/></radialGradient>` +
    `<clipPath id="${c}"><circle cx="${x}" cy="${y}" r="${r}"/></clipPath></defs>` +
    `<g class="orb${live ? '' : ' off'}">` +
    `<ellipse cx="${x}" cy="${y + r + 5}" rx="${(r * 0.8).toFixed(1)}" ry="3" class="orb-shadow"/>` +
    `<circle cx="${x}" cy="${y}" r="${r + 3}" fill="${col}" opacity=".14" filter="url(#rblur)"/>` +
    `<circle cx="${x}" cy="${y}" r="${r}" fill="url(#${g})" class="orb-body"/>` +
    `<g clip-path="url(#${c})" class="orb-grid">` +
    `<ellipse cx="${x}" cy="${y}" rx="${r}" ry="${ry}"/>` +
    `<ellipse cx="${x}" cy="${y - r * 0.55}" rx="${(r * 0.84).toFixed(1)}" ry="${(r * 0.2).toFixed(1)}"/>` +
    `<ellipse cx="${x}" cy="${y + r * 0.55}" rx="${(r * 0.84).toFixed(1)}" ry="${(r * 0.2).toFixed(1)}"/>` +
    `<ellipse cx="${x}" cy="${y}" rx="${r}" ry="${r}" class="orb-mer"><animate attributeName="rx" values="${r};0.5;${r}" dur="6s" repeatCount="indefinite"/></ellipse></g>` +
    `<circle cx="${x}" cy="${y}" r="${r}" fill="none" stroke="${col}" stroke-width="1.2" class="orb-rim"/>` +
    `<g class="orb-glyph" transform="translate(${(x - 24 * s).toFixed(2)} ${(y - 24 * s).toFixed(2)}) scale(${s.toFixed(3)})">` +
    `${GLYPH[id] ?? DEFAULT}</g>` +
    `<ellipse cx="${(x - r * 0.36).toFixed(1)}" cy="${(y - r * 0.46).toFixed(1)}" rx="${(r * 0.34).toFixed(1)}" ry="${(r * 0.18).toFixed(1)}" ` +
    `transform="rotate(-30 ${(x - r * 0.36).toFixed(1)} ${(y - r * 0.46).toFixed(1)})" class="orb-spec"/></g>`
}
