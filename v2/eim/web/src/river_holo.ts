/** Geometría decorativa del río de decisión holográfico: esfera de hexágonos, haz de luz,
 * red de nodos y plataforma de anillos. Solo SVG, sin estado. */

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
    return `<path d="M${f1(x)} ${f1(y)}l11 -6l-3 12z" fill="var(--rc)" opacity=".22"/>`
  }).join('')
  return `<path d="${lines}" stroke="var(--rc)" stroke-width=".8" opacity=".3" fill="none"/>` + tris +
    pts.map(([x, y], k) => `<circle cx="${f1(x)}" cy="${f1(y)}" r="${k % 4 ? 1.6 : 2.6}" fill="#fff" opacity="${k % 4 ? .45 : .9}"/>`).join('')
}

/** Haz vertical, halo y red alrededor de la esfera (la esfera 3D la dibuja `river_sphere`). */
export function core(cx: number, cy: number, r: number, base: number, rc: string): string {
  const beam = `<rect x="${cx - 46}" y="0" width="92" height="${base}" fill="url(#hbeam)" filter="url(#hsoft)"/>` +
    `<rect x="${cx - 1.2}" y="0" width="2.4" height="${base}" fill="url(#hline)"/>`
  return `<g style="--rc:${rc}">` + beam +
    `<circle cx="${cx}" cy="${cy}" r="${r + 26}" fill="url(#hglow)"/>` +
    network(cx, cy, r) +
    `<circle cx="${cx}" cy="${cy}" r="${r + 9}" fill="none" stroke="var(--rc)" stroke-width="1" stroke-dasharray="2 9" opacity=".6" class="hspin"/></g>`
}

/** Plataforma de anillos en perspectiva bajo la esfera. */
export function platform(cx: number, py: number, rc: string): string {
  const rings = [250, 196, 142, 92, 48].map((rx, k) =>
    `<ellipse cx="${cx}" cy="${py}" rx="${rx}" ry="${f1(rx * 0.16)}" fill="none" stroke="${rc}" ` +
    `stroke-width="${k === 1 ? 5 : 1.2}" opacity="${k === 1 ? .35 : .6}"` +
    `${k === 1 ? ' stroke-dasharray="26 10"' : k === 3 ? ' stroke-dasharray="3 6"' : ''}` +
    `${k === 1 || k === 3 ? ` class="hdash${k === 3 ? ' rev' : ''}"` : ''}/>`).join('')
  return `<g><ellipse cx="${cx}" cy="${py}" rx="260" ry="46" fill="url(#hglow)" opacity=".7"/>${rings}</g>`
}

/** `<defs>` compartidos (gradientes, filtros, recorte de la esfera). */
export function holoDefs(rc: string): string {
  return `<filter id="rblur" x="-30%" y="-120%" width="160%" height="340%"><feGaussianBlur stdDeviation="6"/></filter>` +
    `<filter id="hsoft" x="-50%" y="-5%" width="200%" height="110%"><feGaussianBlur stdDeviation="10"/></filter>` +
    `<radialGradient id="hglow"><stop offset="0" style="stop-color:${rc}" stop-opacity=".28"/><stop offset="1" style="stop-color:${rc}" stop-opacity="0"/></radialGradient>` +
    `<linearGradient id="hbeam" x1="0" x2="1"><stop offset="0" style="stop-color:${rc}" stop-opacity="0"/>` +
    `<stop offset=".5" style="stop-color:${rc}" stop-opacity=".35"/><stop offset="1" style="stop-color:${rc}" stop-opacity="0"/></linearGradient>` +
    `<linearGradient id="hline" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>` +
    `<stop offset=".5" stop-color="#fff" stop-opacity=".8"/><stop offset="1" stop-color="#fff" stop-opacity=".1"/></linearGradient>`
}
