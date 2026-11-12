/** Personalidad de cada etapa en la vista «Isométrico»: nombre de la sala, colores, paredes y
 * mobiliario según su actividad, y el puesto de cada pieza según su tipo (agente, puerta, almacén…).
 * Solo decora: ningún estado se deduce de aquí (los estados salen de `stateOf`). */
import { box, lineBL, lineBR, onBackLeft, onBackRight, onBL, onBR, P, pts, type Room } from './obs_iso_geo'

export const WALL_H = 1.3
export const STRIP = 0.95          // franja del fondo reservada al mobiliario de la sala

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
const ringBL = (r: Room, v: number, z: number, rad: number, attrs: string): string => ring((a, b) => onBL(r, a, b), v, z, rad, attrs)
const windowsBR = (r: Room, u0: number, u1: number): string => {
  const n = Math.max(2, Math.round((u1 - u0) / 0.7)), w = (u1 - u0) / n
  return Array.from({ length: n }, (_, i) => onBackRight(r, u0 + i * w + 0.04, u0 + (i + 1) * w - 0.04, 0.5, 1.15, 'fill="#bfe6ff" opacity=".55"')).join('')
}
const windowsBL = (r: Room, v0: number, v1: number): string => {
  const n = Math.max(2, Math.round((v1 - v0) / 0.7)), w = (v1 - v0) / n
  return Array.from({ length: n }, (_, i) => onBackLeft(r, v0 + i * w + 0.04, v0 + (i + 1) * w - 0.04, 0.5, 1.15, 'fill="#bfe6ff" opacity=".45"')).join('')
}
const plant = (r: Room, u: number, v: number): string => box(r, u, v, 0.2, 0.2, 0.18, 0, '#c9714a', '#8f4a2c', '#a85a37')
  + (() => { const c = P(r.cx, r.cy, u, v, 0.42); return `<ellipse cx="${c[0]}" cy="${c[1]}" rx="8" ry="10" fill="#2fa36b"/><ellipse cx="${c[0] - 4}" cy="${c[1] - 6}" rx="5" ry="7" fill="#45c486"/>` })()
const backV = (r: Room): number => -r.hv + 0.42

/** Siete salas: el orden sigue `graph.stages`; si llega una etapa desconocida usa la neutra. */
export const THEMES: Record<string, Theme> = {
  datos: {
    room: 'Centro de recolección', floor: '#1f5f7a', grid: '#7fd3ff', wallL: '#2a3e5c', wallR: '#22324b', accent: '#2ee6ff', shirt: '#2a7fb8',
    walls: (r) => windowsBR(r, -r.hu + 0.3, r.hu - 0.3) + onBackLeft(r, -r.hv + 0.3, r.hv - 0.4, 0.42, 1.12, 'fill="#061a2c" stroke="#2ee6ff" stroke-width=".8"')
      + Array.from({ length: 9 }, (_, i) => { const v = -r.hv + 0.45 + i * ((2 * r.hv - 1) / 9); const h = 0.55 + ((i * 37) % 5) * 0.1
        return lineBL(r, [[v, 0.5], [v, Math.min(1.05, h)]], 'stroke="#2ee6ff" stroke-width="3" opacity=".75"') }).join(''),
    props: (r) => [r.hu - 0.45, r.hu - 0.95].map((u) => box(r, u, backV(r), 0.42, 0.42, 1.0, 0, '#3a4a66', '#1c2740', '#26334f')
      + [0.25, 0.45, 0.65, 0.85].map((z) => { const p = P(r.cx, r.cy, u - 0.21, backV(r) + 0.12, z); return `<circle cx="${p[0]}" cy="${p[1]}" r="1.8" fill="#2ee6ff" class="iso-blink"/>` }).join('')).join('')
      + box(r, -r.hu + 0.5, backV(r), 0.14, 0.14, 0.5, 0, '#9aa7bf', '#6b7891', '#7d8aa3')
      + (() => { const c = P(r.cx, r.cy, -r.hu + 0.5, backV(r), 0.72); return `<ellipse cx="${c[0]}" cy="${c[1]}" rx="15" ry="9" fill="#dfe8f5" stroke="#9aa7bf" transform="rotate(-25 ${c[0]} ${c[1]})"/><circle cx="${c[0]}" cy="${c[1]}" r="2.5" fill="#2ee6ff"/>` })(),
  },
  analisis: {
    room: 'Sala de analistas', floor: '#24478f', grid: '#9ec0ff', wallL: '#2c3963', wallR: '#243055', accent: '#7aa7ff', shirt: '#3c5fb0',
    walls: (r) => onBackRight(r, -r.hu + 0.4, r.hu - 0.6, 0.42, 1.12, 'fill="#eef3ff" stroke="#9fb1d6" stroke-width="1"')
      + Array.from({ length: 10 }, (_, i) => { const u = -r.hu + 0.65 + i * ((2 * r.hu - 1.4) / 10), up = (i * 7) % 3 !== 0, y0 = 0.6 + ((i * 13) % 4) * 0.07
        return lineBR(r, [[u, y0 - 0.06], [u, y0 + 0.24]], 'stroke="#667" stroke-width="1"') + lineBR(r, [[u, y0], [u, y0 + 0.16]], `stroke="${up ? '#12b673' : '#e0405a'}" stroke-width="4"`) }).join('')
      + windowsBL(r, -r.hv + 0.4, r.hv - 0.4) + ringBR(r, r.hu - 0.3, 0.95, 0.13, 'fill="#fff" stroke="#c0392b" stroke-width="1.5"'),
    props: (r) => box(r, -r.hu + 0.4, backV(r), 0.24, 0.24, 0.55, 0, '#e8eef8', '#aab6c9', '#c3cede')
      + (() => { const c = P(r.cx, r.cy, -r.hu + 0.4, backV(r), 0.72); return `<ellipse cx="${c[0]}" cy="${c[1]}" rx="6" ry="9" fill="#7cc6ff" opacity=".85"/>` })()
      + plant(r, r.hu - 0.35, backV(r)),
  },
  proyeccion: {
    room: 'Sala de escenarios', floor: '#4a2f8f', grid: '#c7a8ff', wallL: '#33275f', wallR: '#2a2050', accent: '#b98cff', shirt: '#6a45b8',
    walls: (r) => onBackRight(r, -r.hu + 0.3, r.hu - 0.3, 0.38, 1.18, 'fill="#0d0a24" stroke="#b98cff" stroke-width="1"')
      + (() => { const u0 = -r.hu + 0.5, u1 = r.hu - 0.5, m = (u0 + u1) / 2
        return lineBR(r, [[u0, 0.62], [m, 0.72], [u1, 1.05]], 'stroke="#12e58f" stroke-width="2.4"') + lineBR(r, [[u0, 0.62], [m, 0.66], [u1, 0.7]], 'stroke="#9aa6c8" stroke-width="2.4"')
          + lineBR(r, [[u0, 0.62], [m, 0.56], [u1, 0.46]], 'stroke="#ff3d5f" stroke-width="2.4"') })()
      + ringBL(r, 0, 0.78, 0.3, 'fill="#1b1442" stroke="#b98cff" stroke-width="1"') + ringBL(r, 0, 0.78, 0.18, 'fill="none" stroke="#b98cff" stroke-width=".8"'),
    props: (r) => box(r, 0, backV(r) + 0.1, 0.36, 0.36, 0.3, 0, '#5b4a99', '#33285f', '#43357a')
      + (() => { const c = P(r.cx, r.cy, 0, backV(r) + 0.1, 0.62); return `<circle cx="${c[0]}" cy="${c[1]}" r="11" fill="#b98cff" opacity=".35" class="iso-orb"/><circle cx="${c[0]}" cy="${c[1]}" r="6" fill="#e5d6ff"/>` })(),
  },
  plan: {
    room: 'Sala de estrategia', floor: '#7a5420', grid: '#ffd08a', wallL: '#4a3a2a', wallR: '#3d3023', accent: '#ffb547', shirt: '#b8741e',
    walls: (r) => onBackRight(r, -r.hu + 0.35, r.hu - 0.35, 0.42, 1.12, 'fill="#fdf7ec" stroke="#c9a76b" stroke-width="1"')
      + ([[0.95, '#12b673'], [0.75, '#22a7e1'], [0.55, '#e0405a']] as [number, string][]).map(([z, c]) => lineBR(r, [[-r.hu + 0.45, z], [r.hu - 0.45, z]], `stroke="${c}" stroke-width="2" stroke-dasharray="${c === '#22a7e1' ? '0' : '5 3'}"`)).join('')
      + Array.from({ length: 6 }, (_, i) => onBackLeft(r, -r.hv + 0.35 + (i % 3) * 0.4, -r.hv + 0.65 + (i % 3) * 0.4, 0.62 + Math.floor(i / 3) * 0.28, 0.82 + Math.floor(i / 3) * 0.28,
        `fill="${['#ffd166', '#ff9f80', '#9be7a1'][i % 3]}"`)).join(''),
    props: (r) => box(r, 0, backV(r) + 0.05, 1.3, 0.5, 0.26, 0, '#e9d5b5', '#a8885c', '#c4a274')
      + [-0.45, 0, 0.45].map((u) => box(r, u, backV(r) + 0.42, 0.2, 0.18, 0.16, 0, '#3a3a4a', '#22222d', '#2c2c3a')).join(''),
  },
  riesgo: {
    room: 'Control de riesgo', floor: '#5a2333', grid: '#ff9fb1', wallL: '#3f2630', wallR: '#341f28', accent: '#ff5d7a', shirt: '#8a2f45',
    walls: (r) => ringBR(r, r.hu - 0.75, 0.78, 0.36, 'fill="#8f99ab" stroke="#4b5568" stroke-width="2"') + ringBR(r, r.hu - 0.75, 0.78, 0.22, 'fill="#6f7a8e" stroke="#c9d2e0" stroke-width="1.5"')
      + (() => { const a = onBR(r, -r.hu + 0.6, 1.1), b = onBR(r, -r.hu + 1.1, 1.1), c = onBR(r, -r.hu + 1.1, 0.75), d = onBR(r, -r.hu + 0.85, 0.5), e = onBR(r, -r.hu + 0.6, 0.75)
        return `<polygon points="${pts([a, b, c, d, e])}" fill="#ff5d7a" opacity=".85"/>` })()
      + [-0.5, 0.2].map((v) => ringBL(r, v, 0.8, 0.22, 'fill="#1d1218" stroke="#ff9fb1" stroke-width="1"')).join(''),
    props: (r) => box(r, -r.hu + 0.55, backV(r) + 0.05, 0.3, 0.3, 0.5, 0, '#444b5c', '#262b36', '#333948')
      + (() => { const c = P(r.cx, r.cy, -r.hu + 0.55, backV(r) + 0.05, 0.56); return `<ellipse cx="${c[0]}" cy="${c[1]}" rx="9" ry="5" fill="#ff2d4d" class="iso-blink"/>` })()
      + box(r, r.hu - 0.45, backV(r), 0.45, 0.4, 0.45, 0, '#9aa3b3', '#5f6878', '#7a8393'),
  },
  ejecucion: {
    room: 'Mesa de operaciones', floor: '#1d5e48', grid: '#8ff0c4', wallL: '#22413a', wallR: '#1b362f', accent: '#12e58f', shirt: '#1f8a62',
    walls: (r) => onBackRight(r, -r.hu + 0.3, r.hu - 0.3, 0.82, 1.15, 'fill="#04140e" stroke="#12e58f" stroke-width=".8"')
      + Array.from({ length: 12 }, (_, i) => { const u = -r.hu + 0.45 + i * ((2 * r.hu - 0.9) / 12); return lineBR(r, [[u, 0.92], [u + 0.12, 0.92]], `stroke="${i % 3 ? '#12e58f' : '#ff3d5f'}" stroke-width="3"`) }).join('')
      + Array.from({ length: 6 }, (_, i) => onBackLeft(r, -r.hv + 0.35 + (i % 3) * 0.55, -r.hv + 0.82 + (i % 3) * 0.55, 0.45 + Math.floor(i / 3) * 0.34, 0.74 + Math.floor(i / 3) * 0.34,
        'fill="#071c2c" stroke="#12e58f" stroke-width=".6"')).join(''),
    props: (r) => box(r, r.hu - 0.45, backV(r), 0.4, 0.34, 0.36, 0, '#e3e8ef', '#a3adbb', '#c2cad6') + plant(r, -r.hu + 0.35, backV(r)),
  },
  validacion: {
    room: 'Laboratorio de aprendizaje', floor: '#6b5a22', grid: '#ffe58a', wallL: '#3d3a2c', wallR: '#333024', accent: '#ffd23f', shirt: '#9c7d1c',
    walls: (r) => onBackLeft(r, -r.hv + 0.35, r.hv - 0.5, 0.45, 1.12, 'fill="#fffdf4" stroke="#c9b56b" stroke-width="1"')
      + Array.from({ length: 6 }, (_, i) => { const v = -r.hv + 0.6 + i * ((2 * r.hv - 1.3) / 6); return lineBL(r, [[v, 0.52], [v, 0.6 + ((i * 11) % 5) * 0.09]], `stroke="${i % 2 ? '#22a7e1' : '#ffb547'}" stroke-width="6"`) }).join('')
      + ringBL(r, r.hv - 0.25, 0.98, 0.12, 'fill="#ffe066" stroke="#c9a200" stroke-width="1"'),
    props: (r) => [r.hu - 0.4, r.hu - 0.85, r.hu - 1.3].map((u) => box(r, u, backV(r) - 0.08, 0.42, 0.26, 1.05, 0, '#d8c39a', '#8e7448', '#a98b5b')
      + [0.3, 0.6, 0.9].map((z) => box(r, u, backV(r) - 0.08, 0.34, 0.22, 0.2, z - 0.15, '#c0392b', ['#2e86de', '#c0392b', '#27ae60'][Math.round(z * 3) % 3], '#f39c12')).join('')).join('')
      + box(r, -r.hu + 0.55, backV(r), 0.6, 0.3, 0.3, 0, '#e9eef5', '#a9b3c2', '#c6cfdb'),
  },
}
const NEUTRAL: Theme = { ...THEMES.analisis, room: 'Área de trabajo' }
export const themeOf = (stage: string): Theme => THEMES[stage] ?? NEUTRAL

/** Monitor plano mirando al frente-izquierda, apoyado en (u, v) a la altura z0. */
const monitor = (r: Room, u: number, v: number, w: number, z0: number, h: number, screen: string): string => {
  const m = [P(r.cx, r.cy, u - w / 2, v, z0), P(r.cx, r.cy, u + w / 2, v, z0), P(r.cx, r.cy, u + w / 2, v, z0 + h), P(r.cx, r.cy, u - w / 2, v, z0 + h)]
  const c = P(r.cx, r.cy, u, v + 0.01, z0 + h / 2)
  return `<polygon points="${pts(m)}" fill="#1b2a5c" stroke="#8fb4ff" stroke-width=".7"/><circle cx="${c[0]}" cy="${c[1]}" r="2.3" fill="${screen}"/>`
}

/** Puesto de una pieza: escritorio y persona, con un accesorio según su tipo en el catálogo. */
export function station(r: Room, u: number, v: number, k: number, kind: string, shirt: string, accent: string, screen: string): string {
  const dv = v - 0.18 * k, s = (x: number): number => x * k
  let out = ''
  if (kind === 'gate') {
    out += box(r, u, dv, s(0.7), s(0.3), s(0.36), 0, accent, '#2b3350', '#3a4466')
    out += monitor(r, u, dv - s(0.06), s(0.26), s(0.36), s(0.22), screen)
  } else {
    out += box(r, u, dv, s(0.64), s(0.34), s(0.24), 0, '#e6ecf7', '#9fb0cc', '#c2cfe3')
    if (kind === 'agent') out += monitor(r, u - s(0.16), dv - s(0.1), s(0.26), s(0.24), s(0.26), screen) + monitor(r, u + s(0.16), dv - s(0.1), s(0.26), s(0.24), s(0.26), screen)
    else if (kind === 'view') out += monitor(r, u, dv - s(0.1), s(0.52), s(0.24), s(0.32), screen)
    else out += monitor(r, u, dv - s(0.1), s(0.34), s(0.24), s(0.26), screen)
    if (kind === 'store') out += box(r, u + s(0.44), dv, s(0.2), s(0.3), s(0.6), 0, '#b9c3d3', '#7d889b', '#98a3b5')
    if (kind === 'engine') out += box(r, u - s(0.44), dv, s(0.18), s(0.28), s(0.46), 0, '#2d3b66', '#141c38', '#1d2849')
      + (() => { const p = P(r.cx, r.cy, u - s(0.53), dv + s(0.1), s(0.3)); return `<circle cx="${p[0]}" cy="${p[1]}" r="${s(2)}" fill="${accent}" class="iso-blink"/>` })()
  }
  out += box(r, u, v + 0.24 * k, s(0.26), s(0.24), s(0.14), 0, '#3a4675', '#232c55', '#2c3766')
  const b = P(r.cx, r.cy, u, v + 0.22 * k, s(0.34)), h = P(r.cx, r.cy, u, v + 0.22 * k, s(0.66))
  out += `<path d="M${b[0] - s(7)},${b[1] + s(8)} Q${b[0] - s(7)},${b[1] - s(8)} ${b[0]},${b[1] - s(9)} Q${b[0] + s(7)},${b[1] - s(8)} ${b[0] + s(7)},${b[1] + s(8)} Z" fill="${shirt}"/>`
  out += `<circle cx="${h[0]}" cy="${h[1]}" r="${s(5.4)}" fill="#f1c9a5"/><path d="M${h[0] - s(5.4)},${h[1] - 1} A${s(5.4)},${s(5.4)} 0 0 1 ${h[0] + s(5.4)},${h[1] - 1} Z" fill="#3b2a20"/>`
  return out
}
