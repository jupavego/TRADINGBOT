/** Geometría decorativa del río de decisión holográfico: esfera de hexágonos, haz de luz,
 * red de nodos y plataforma de anillos. Solo SVG, sin estado. Se tiñen con el reparto
 * subida/bajada (verde a la izquierda, rojo a la derecha, fundidos en degradado) igual que la
 * esfera 3D: los gradientes `hsplit*` y las máscaras de brillo viven en `holoDefs`. */

import { areaSplit, BAND } from './river_sphere_paint'

const f1 = (n: number): string => n.toFixed(1)

/** Hexágono de lado `s` centrado en (x, y) (punta a izquierda/derecha). */
export function hexPath(x: number, y: number, s: number): string {
  const p = Array.from({ length: 6 }, (_, k) => {
    const a = (Math.PI / 3) * k
    return `${f1(x + s * Math.cos(a))} ${f1(y + s * Math.sin(a))}`
  })
  return `M${p.join('L')}Z`
}

/** Puntos y triángulos de la "red" que rodea la esfera (deterministas). */
function network(cx: number, cy: number, r: number): string {
  const pts = Array.from({ length: 16 }, (_, k) => {
    const a = k * 2.39996 + 0.4
    const rr = r + 14 + ((k * 37) % 46)
    return [cx + rr * Math.cos(a), cy + rr * Math.sin(a) * 0.82] as const
  })
  const lines = pts.map(([x, y], k) => {
    const [x2, y2] = pts[(k + 3) % pts.length]
    return Math.hypot(x2 - x, y2 - y) < r * 1.2 ? `M${f1(x)} ${f1(y)}L${f1(x2)} ${f1(y2)}` : ''
  }).join('')
  const tris = [0, 5, 9, 12].map((k) => {
    const [x, y] = pts[k]
    return `<path d="M${f1(x)} ${f1(y)}l11 -6l-3 12z" fill="url(#hsplitS)" opacity=".22"/>`
  }).join('')
  return `<path d="${lines}" stroke="url(#hsplitS)" stroke-width=".8" opacity=".3" fill="none"/>` + tris +
    pts.map(([x, y], k) => `<circle cx="${f1(x)}" cy="${f1(y)}" r="${k % 4 ? 1.6 : 2.6}" fill="#fff" opacity="${k % 4 ? .45 : .9}"/>`).join('')
}

/** Haz vertical, halo y red alrededor de la esfera (la esfera 3D la dibuja `river_sphere`). */
export function core(cx: number, cy: number, r: number, base: number): string {
  const beam = `<g filter="url(#hsoft)"><rect x="${cx - 46}" y="0" width="92" height="${base}" fill="url(#hsplitL)" mask="url(#mbeam)"/></g>` +
    `<rect x="${cx - 1.2}" y="0" width="2.4" height="${base}" fill="url(#hline)"/>`
  return '<g>' + beam +
    `<circle cx="${cx}" cy="${cy}" r="${r + 26}" fill="url(#hsplit)" mask="url(#mglow)"/>` +
    network(cx, cy, r) +
    `<circle cx="${cx}" cy="${cy}" r="${r + 9}" fill="none" stroke="url(#hsplit)" stroke-width="1" stroke-dasharray="2 9" opacity=".6" class="hspin"/></g>`
}

/** Plataforma de anillos en perspectiva bajo la esfera. */
export function platform(cx: number, py: number): string {
  const rings = [250, 196, 142, 92, 48].map((rx, k) =>
    `<ellipse cx="${cx}" cy="${py}" rx="${rx}" ry="${f1(rx * 0.16)}" fill="none" stroke="url(#hsplit)" ` +
    `stroke-width="${k === 1 ? 5 : 1.2}" opacity="${k === 1 ? .35 : .6}"` +
    `${k === 1 ? ' stroke-dasharray="26 10"' : k === 3 ? ' stroke-dasharray="3 6"' : ''}` +
    `${k === 1 || k === 3 ? ` class="hdash${k === 3 ? ' rev' : ''}"` : ''}/>`).join('')
  return `<g><ellipse cx="${cx}" cy="${py}" rx="260" ry="46" fill="url(#hsplit)" mask="url(#mglow)" opacity=".7"/>${rings}</g>`
}

/** Gradiente horizontal `id`: `left` hasta `at − band`, fundido, y `right` desde `at + band`
 * (fracciones de la caja del elemento, o coordenadas si `user`). */
function split(id: string, left: string, right: string, at: number, band: number, user = ''): string {
  const off = (v: number): string => Math.min(1, Math.max(0, v)).toFixed(4)
  const [o0, o1] = user ? ['0', '1'] : [off(at - band), off(at + band)]
  return `<linearGradient id="${id}"${user}>` +
    `<stop offset="${o0}" style="stop-color:${left}"/><stop offset="${o1}" style="stop-color:${right}"/></linearGradient>`
}

/** `<defs>` compartidos: filtros, gradientes de reparto y máscaras de brillo.
 * `up` = % de subida (null = sin señal → todo `rc`); (cx, cy, r) = esfera, para la red que la
 * rodea, cuya frontera coincide con la de la esfera 3D. */
export function holoDefs(rc: string, up: number | null, cx: number, r: number): string {
  const two = up !== null && up > 0 && up < 100
  const [left, right] = two ? ['var(--up)', 'var(--down)'] : [rc, rc]
  const s = two ? areaSplit(up / 100) : 0 // frontera por área, en radios (−1…1)
  const xb = cx + s * r, band = BAND * r
  return `<filter id="rblur" x="-30%" y="-120%" width="160%" height="340%"><feGaussianBlur stdDeviation="6"/></filter>` +
    `<filter id="hsoft" x="-50%" y="-5%" width="200%" height="110%"><feGaussianBlur stdDeviation="10"/></filter>` +
    // círculos y elipses: frontera por área (como la esfera); el haz (rectángulo): por anchura
    split('hsplit', left, right, (1 + s) / 2, BAND / 2) +
    split('hsplitL', left, right, two ? up / 100 : 0.5, BAND / 2) +
    split('hsplitS', left, right, 0, 0, ` gradientUnits="userSpaceOnUse" x1="${f1(xb - band)}" x2="${f1(xb + band)}" y1="0" y2="0"`) +
    // brillo radial (halo, plataforma) y perfil del haz, como máscaras: el color lo pone el reparto
    `<radialGradient id="hglowW"><stop offset="0" stop-color="#fff" stop-opacity=".28"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>` +
    `<mask id="mglow" maskContentUnits="objectBoundingBox"><rect width="1" height="1" fill="url(#hglowW)"/></mask>` +
    `<linearGradient id="hbeamW"><stop offset="0" stop-color="#fff" stop-opacity="0"/>` +
    `<stop offset=".5" stop-color="#fff" stop-opacity=".35"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>` +
    `<mask id="mbeam" maskContentUnits="objectBoundingBox"><rect width="1" height="1" fill="url(#hbeamW)"/></mask>` +
    `<linearGradient id="hline" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>` +
    `<stop offset=".5" stop-color="#fff" stop-opacity=".8"/><stop offset="1" stop-color="#fff" stop-opacity=".1"/></linearGradient>`
}
