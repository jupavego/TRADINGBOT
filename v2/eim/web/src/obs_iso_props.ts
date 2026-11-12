/** Personalidad de cada etapa en la vista «Isométrico»: nombre de la sala, colores, paredes y
 * mobiliario según su actividad, y el puesto de cada pieza según su tipo (agente, puerta, almacén…).
 * Solo decora: ningún estado se deduce de aquí (los estados salen de `stateOf`). */
import { ART } from './obs_iso_art'
import { box, lineBL, lineBR, onBackLeft, onBackRight, onBL, onBR, P, pts, type Room } from './obs_iso_geo'

export const WALL_H = 1.3
export const STRIP = 0.95          // franja del fondo reservada al mobiliario de la sala
export const NAME_STRIP = 0.78     // franja del frente donde va pintado el nombre del área (p. ej. «1. DATOS»)

/** Coloca un objeto de las ilustraciones: `hpx` = alto en pantalla; `at` = 'piso' (se apoya por abajo en
 * el punto) o 'pared' (centrado en el punto); `flip` lo refleja (mira hacia el otro lado del plano). */
export function art(name: string, [x, y]: [number, number], hpx: number, at: 'piso' | 'pared' = 'piso', flip = false, extra = ''): string {
  const d = ART[name]; if (!d) return ''
  const k = hpx / d[1], w = d[0] * k, x0 = x - w / 2, y0 = at === 'piso' ? y - hpx : y - hpx / 2
  const use = `<use href="#iso-a-${name}" x="${x0.toFixed(1)}" y="${y0.toFixed(1)}" width="${w.toFixed(1)}" height="${hpx.toFixed(1)}"${extra}/>`
  return flip ? `<g transform="translate(${(2 * x).toFixed(1)},0) scale(-1,1)">${use}</g>` : use
}
const onFloor = (r: Room, u: number, v: number): [number, number] => P(r.cx, r.cy, u, v, 0)

export interface Theme {
  room: string; floor: string; grid: string; wallL: string; wallR: string; accent: string; shirt: string
  walls: (r: Room) => string; props: (r: Room) => string
}

const ring = (at: (a: number, b: number) => [number, number], a: number, b: number, rad: number, attrs: string): string => {
  const p: [number, number][] = []
  for (let i = 0; i < 18; i++) { const t = (i / 18) * Math.PI * 2; p.push(at(a + Math.cos(t) * rad, b + Math.sin(t) * rad)) }
  return `<polygon points="${pts(p)}" ${attrs}/>`
}
const ringBR = (r: Room, u: number, z: number, rad: number, attrs: string): string => ring((a, b) => onBR(r, a, b), u, z, rad, attrs)
const windowsBR = (r: Room, u0: number, u1: number, z0 = 0.42, z1 = 1.16): string => {
  const n = Math.max(2, Math.round((u1 - u0) / 0.7)), w = (u1 - u0) / n
  return Array.from({ length: n }, (_, i) => onBackRight(r, u0 + i * w + 0.03, u0 + (i + 1) * w - 0.03, z0, z1, 'fill="#9fd6ee" stroke="#ffffff" stroke-width="2.5"')).join('')
}
const windowsBL = (r: Room, v0: number, v1: number): string => {
  const n = Math.max(2, Math.round((v1 - v0) / 0.7)), w = (v1 - v0) / n
  return Array.from({ length: n }, (_, i) => onBackLeft(r, v0 + i * w + 0.03, v0 + (i + 1) * w - 0.03, 0.42, 1.16, 'fill="#8fcbe6" stroke="#ffffff" stroke-width="2.5"')).join('')
}
const backV = (r: Room): number => -r.hv + 0.42

/** Criterio de cada sala (pared pintada, ventanas, mobiliario):
 * 1 Datos: técnico, pared de pantallas azul petróleo y ventanal · 2 Análisis: luminosa, ventanal y tablero de velas
 * 3 Proyección: inmersiva, paredes moradas oscuras tipo sala de cine · 4 Plan: cálida, pared ocre con corcho
 * 5 Riesgo: sobria y segura, pared grafito con bóveda · 6 Ejecución: mesa de operaciones, pared verde noche con
 * pantallas y ventanas · 7 Validación: biblioteca-laboratorio, pared amarilla suave con tableros.
 * El resto de paredes son claras, como en las ilustraciones; cada sala conserva su color de acento. */
const WL = '#eef0f4', WR = '#dde1e8'
const fl = onFloor

/** Siete salas: el orden sigue `graph.stages`; si llega una etapa desconocida usa la neutra. */
export const THEMES: Record<string, Theme> = {
  datos: {
    room: 'Centro de recolección', floor: '#1f5f7a', grid: '#7fd3ff', wallL: '#24566b', wallR: WR, accent: '#12a9d6', shirt: '#2a7fb8',
    walls: (r) => windowsBR(r, -r.hu + 0.3, r.hu - 0.3) + onBackLeft(r, -r.hv + 0.3, r.hv - 0.4, 0.42, 1.12, 'fill="#061a2c" stroke="#12a9d6" stroke-width=".8"')
      + Array.from({ length: 9 }, (_, i) => { const v = -r.hv + 0.45 + i * ((2 * r.hv - 1) / 9); const h = 0.55 + ((i * 37) % 5) * 0.1
        return lineBL(r, [[v, 0.5], [v, Math.min(1.05, h)]], 'stroke="#2ee6ff" stroke-width="3" opacity=".75"') }).join(''),
    props: (r) => [r.hu - 0.45, r.hu - 0.95].map((u) => box(r, u, backV(r), 0.42, 0.42, 1.0, 0, '#3a4a66', '#1c2740', '#26334f')
      + [0.25, 0.45, 0.65, 0.85].map((z) => { const p = P(r.cx, r.cy, u - 0.21, backV(r) + 0.12, z); return `<circle cx="${p[0]}" cy="${p[1]}" r="1.8" fill="#2ee6ff" class="iso-blink"/>` }).join('')).join('')
      + box(r, -r.hu + 0.5, backV(r), 0.14, 0.14, 0.5, 0, '#9aa7bf', '#6b7891', '#7d8aa3')
      + (() => { const c = P(r.cx, r.cy, -r.hu + 0.5, backV(r), 0.72); return `<ellipse cx="${c[0]}" cy="${c[1]}" rx="15" ry="9" fill="#dfe8f5" stroke="#9aa7bf" transform="rotate(-25 ${c[0]} ${c[1]})"/><circle cx="${c[0]}" cy="${c[1]}" r="2.5" fill="#2ee6ff"/>` })()
      + art('dispensador', fl(r, -r.hu + 1.15, backV(r)), 32) + art('planta_alta', fl(r, r.hu - 1.45, backV(r) - 0.05), 40),
  },
  analisis: {
    room: 'Sala de analistas', floor: '#24478f', grid: '#9ec0ff', wallL: WL, wallR: '#dbe6f7', accent: '#4f7fe8', shirt: '#3c5fb0',
    walls: (r) => onBackRight(r, -r.hu + 0.4, r.hu - 0.7, 0.42, 1.12, 'fill="#ffffff" stroke="#9fb1d6" stroke-width="1"')
      + Array.from({ length: 10 }, (_, i) => { const u = -r.hu + 0.65 + i * ((2 * r.hu - 1.5) / 10), up = (i * 7) % 3 !== 0, y0 = 0.6 + ((i * 13) % 4) * 0.07
        return lineBR(r, [[u, y0 - 0.06], [u, y0 + 0.24]], 'stroke="#667" stroke-width="1"') + lineBR(r, [[u, y0], [u, y0 + 0.16]], `stroke="${up ? '#12b673' : '#e0405a'}" stroke-width="4"`) }).join('')
      + windowsBL(r, -r.hv + 0.4, r.hv - 0.4) + art('reloj', onBR(r, r.hu - 0.35, 0.95), 15, 'pared'),
    props: (r) => art('dispensador', fl(r, -r.hu + 0.4, backV(r)), 32) + art('arbol', fl(r, r.hu - 0.35, backV(r)), 42)
      + art('cajonera', fl(r, -r.hu + 0.85, backV(r) - 0.05), 18),
  },
  proyeccion: {
    room: 'Sala de escenarios', floor: '#4a2f8f', grid: '#c7a8ff', wallL: '#4a3a7a', wallR: '#3d2f68', accent: '#9a6cf0', shirt: '#6a45b8',
    walls: (r) => onBackRight(r, -r.hu + 0.3, r.hu - 0.3, 0.38, 1.18, 'fill="#0d0a24" stroke="#b98cff" stroke-width="1"')
      + (() => { const u0 = -r.hu + 0.5, u1 = r.hu - 0.5, m = (u0 + u1) / 2
        return lineBR(r, [[u0, 0.62], [m, 0.72], [u1, 1.05]], 'stroke="#12e58f" stroke-width="2.4"') + lineBR(r, [[u0, 0.62], [m, 0.66], [u1, 0.7]], 'stroke="#9aa6c8" stroke-width="2.4"')
          + lineBR(r, [[u0, 0.62], [m, 0.56], [u1, 0.46]], 'stroke="#ff3d5f" stroke-width="2.4"') })()
      + art('grafico', onBL(r, 0, 0.8), 26, 'pared', true),
    props: (r) => box(r, 0, backV(r) + 0.1, 0.36, 0.36, 0.3, 0, '#5b4a99', '#33285f', '#43357a')
      + (() => { const c = P(r.cx, r.cy, 0, backV(r) + 0.1, 0.62); return `<circle cx="${c[0]}" cy="${c[1]}" r="11" fill="#b98cff" opacity=".35" class="iso-orb"/><circle cx="${c[0]}" cy="${c[1]}" r="6" fill="#e5d6ff"/>` })()
      + art('planta', fl(r, -r.hu + 0.35, backV(r)), 22) + art('planta', fl(r, r.hu - 0.35, backV(r)), 22),
  },
  plan: {
    room: 'Sala de estrategia', floor: '#7a5420', grid: '#ffd08a', wallL: '#e8c37a', wallR: WR, accent: '#f0a020', shirt: '#b8741e',
    walls: (r) => onBackRight(r, -r.hu + 0.35, r.hu - 0.35, 0.42, 1.12, 'fill="#fffdf7" stroke="#c9a76b" stroke-width="1"')
      + ([[0.95, '#12b673'], [0.75, '#22a7e1'], [0.55, '#e0405a']] as [number, string][]).map(([z, c]) => lineBR(r, [[-r.hu + 0.45, z], [r.hu - 0.45, z]], `stroke="${c}" stroke-width="2" stroke-dasharray="${c === '#22a7e1' ? '0' : '5 3'}"`)).join('')
      + art('corcho', onBL(r, -r.hv + 0.75, 0.8), 30, 'pared', true) + art('reloj', onBL(r, r.hv - 0.4, 0.98), 14, 'pared', true),
    props: (r) => box(r, 0, backV(r) + 0.05, 1.3, 0.5, 0.26, 0, '#e9d5b5', '#a8885c', '#c4a274')
      + [-0.45, 0, 0.45].map((u) => box(r, u, backV(r) + 0.42, 0.2, 0.18, 0.16, 0, '#3a3a4a', '#22222d', '#2c2c3a')).join('')
      + art('arbol', fl(r, r.hu - 0.3, backV(r) - 0.05), 40),
  },
  riesgo: {
    room: 'Control de riesgo', floor: '#5a2333', grid: '#ff9fb1', wallL: '#3e4350', wallR: WR, accent: '#e8405f', shirt: '#8a2f45',
    walls: (r) => ringBR(r, r.hu - 0.75, 0.78, 0.36, 'fill="#8f99ab" stroke="#4b5568" stroke-width="2"') + ringBR(r, r.hu - 0.75, 0.78, 0.22, 'fill="#6f7a8e" stroke="#c9d2e0" stroke-width="1.5"')
      + (() => { const a = onBR(r, -r.hu + 0.6, 1.1), b = onBR(r, -r.hu + 1.1, 1.1), c = onBR(r, -r.hu + 1.1, 0.75), d = onBR(r, -r.hu + 0.85, 0.5), e = onBR(r, -r.hu + 0.6, 0.75)
        return `<polygon points="${pts([a, b, c, d, e])}" fill="#e8405f" opacity=".85"/>` })()
      + art('pizarra_negra', onBL(r, -0.2, 0.8), 30, 'pared', true) + art('repisa_reloj', onBR(r, 0.15, 0.8), 30, 'pared'),
    props: (r) => box(r, -r.hu + 0.55, backV(r) + 0.05, 0.3, 0.3, 0.5, 0, '#444b5c', '#262b36', '#333948')
      + (() => { const c = P(r.cx, r.cy, -r.hu + 0.55, backV(r) + 0.05, 0.56); return `<ellipse cx="${c[0]}" cy="${c[1]}" rx="9" ry="5" fill="#ff2d4d" class="iso-blink"/>` })()
      + art('archivador', fl(r, r.hu - 0.45, backV(r)), 36) + art('cactus', fl(r, r.hu - 0.95, backV(r) - 0.05), 16),
  },
  ejecucion: {
    room: 'Mesa de operaciones', floor: '#1d5e48', grid: '#8ff0c4', wallL: '#1f3b34', wallR: WR, accent: '#0fbf7a', shirt: '#1f8a62',
    walls: (r) => onBackRight(r, -r.hu + 0.3, r.hu - 0.3, 0.82, 1.15, 'fill="#04140e" stroke="#12e58f" stroke-width=".8"')
      + Array.from({ length: 12 }, (_, i) => { const u = -r.hu + 0.45 + i * ((2 * r.hu - 0.9) / 12); return lineBR(r, [[u, 0.92], [u + 0.12, 0.92]], `stroke="${i % 3 ? '#12e58f' : '#ff3d5f'}" stroke-width="3"`) }).join('')
      + Array.from({ length: 6 }, (_, i) => onBackLeft(r, -r.hv + 0.35 + (i % 3) * 0.55, -r.hv + 0.82 + (i % 3) * 0.55, 0.45 + Math.floor(i / 3) * 0.34, 0.74 + Math.floor(i / 3) * 0.34,
        'fill="#071c2c" stroke="#12e58f" stroke-width=".6"')).join('')
      + windowsBR(r, -r.hu + 0.3, r.hu - 0.3, 0.3, 0.72),
    props: (r) => art('mueble', fl(r, r.hu - 0.45, backV(r)), 22) + art('libros', fl(r, r.hu - 0.45, backV(r)), 8, 'piso', false, ' transform="translate(0,-21)"')
      + art('planta_alta', fl(r, -r.hu + 0.35, backV(r)), 40) + art('dispensador', fl(r, r.hu - 1.0, backV(r) - 0.05), 30),
  },
  validacion: {
    room: 'Laboratorio de aprendizaje', floor: '#6b5a22', grid: '#ffe58a', wallL: WL, wallR: '#f6e7a8', accent: '#e0b400', shirt: '#9c7d1c',
    walls: (r) => onBackLeft(r, -r.hv + 0.35, r.hv - 0.5, 0.45, 1.12, 'fill="#ffffff" stroke="#c9b56b" stroke-width="1"')
      + Array.from({ length: 6 }, (_, i) => { const v = -r.hv + 0.6 + i * ((2 * r.hv - 1.3) / 6); return lineBL(r, [[v, 0.52], [v, 0.6 + ((i * 11) % 5) * 0.09]], `stroke="${i % 2 ? '#22a7e1' : '#ffb547'}" stroke-width="6"`) }).join('')
      + art('tablero_graf', onBR(r, -r.hu + 0.9, 0.78), 36, 'pared') + art('corcho_reloj', onBR(r, 0.2, 0.82), 36, 'pared')
      + art('barras', onBR(r, r.hu - 0.8, 0.8), 26, 'pared') + art('dona', onBR(r, r.hu - 0.35, 0.8), 20, 'pared'),
    props: (r) => [r.hu - 0.45, r.hu - 1.05].map((u) => art('estante', fl(r, u, backV(r) - 0.05), 30)).join('')
      + art('mesa', fl(r, -r.hu + 0.6, backV(r)), 22) + art('planta', fl(r, -r.hu + 0.6, backV(r)), 10, 'piso', false, ' transform="translate(0,-15)"')
      + art('arbol', fl(r, -r.hu + 1.3, backV(r) - 0.05), 38),
  },
}
const NEUTRAL: Theme = { ...THEMES.analisis, room: 'Área de trabajo' }
export const themeOf = (stage: string): Theme => THEMES[stage] ?? NEUTRAL

/** Puesto de una pieza: escritorio con monitor y una persona sentada de espaldas (de las ilustraciones),
 * con un accesorio según su tipo en el catálogo (puerta, almacén, motor). `alt` alterna mujer/hombre. */
export function station(r: Room, u: number, v: number, k: number, kind: string, _shirt: string, accent: string, screen: string, alt = 0): string {
  const dv = v - 0.18 * k, s = (x: number): number => x * k
  let out = ''
  if (kind === 'gate') out += box(r, u, dv, s(0.7), s(0.3), s(0.3), 0, accent, '#8a93a8', '#b3bacb')
  else out += box(r, u, dv, s(0.64), s(0.34), s(0.26), 0, '#f5f7f7', '#c9ccd2', '#e3e3e3')
  if (kind === 'store') out += art('cajonera', P(r.cx, r.cy, u + s(0.46), dv + s(0.08), 0), s(16))
  if (kind === 'engine') out += box(r, u - s(0.44), dv, s(0.18), s(0.28), s(0.46), 0, '#2d3b66', '#141c38', '#1d2849')
    + (() => { const p = P(r.cx, r.cy, u - s(0.53), dv + s(0.1), s(0.3)); return `<circle cx="${p[0]}" cy="${p[1]}" r="${s(2)}" fill="${accent}" class="iso-blink"/>` })()
  const top = kind === 'gate' ? 0.3 : 0.26
  out += art('monitor', P(r.cx, r.cy, u + s(0.04), dv - s(0.02), s(top)), s(15))
  const sc = P(r.cx, r.cy, u + s(0.06), dv - s(0.01), s(top) + s(0.24))
  out += `<circle cx="${sc[0].toFixed(1)}" cy="${sc[1].toFixed(1)}" r="${s(2.2)}" fill="${screen}"/>`
  out += art(alt % 2 ? 'hombre' : 'mujer', P(r.cx, r.cy, u + s(0.05), v + 0.24 * k, 0), s(34), 'piso', true)
  return out
}
