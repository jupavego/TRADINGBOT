import type { Time } from 'lightweight-charts'

/** Hora de la interfaz: Bogotá (COT, UTC−5). Colombia no tiene horario de verano desde 1993, así que
 * el desfase es fijo. Los datos y registros del sistema siguen en UTC (ms): solo se convierte al mostrar. */
export const TZ_NAME = 'COT'
export const TZ_OFFSET_MS = -5 * 3_600_000

/** ISO («YYYY-MM-DDTHH:MM:SS.sssZ») del instante `t` desplazado a la hora de Bogotá; úsese solo
 * para cortar con `slice`: la «Z» final no significa UTC aquí. */
export const bogIso = (t: number): string => new Date(t + TZ_OFFSET_MS).toISOString()

const two = (n: number): string => String(n).padStart(2, '0')

/** Opciones de lightweight-charts para que ejes y cruz muestren la hora de Bogotá aunque los
 * datos de las series sigan en segundos UTC. */
export const chartTimeLocale = {
  localization: {
    timeFormatter: (t: Time): string => bogIso(Number(t) * 1000).slice(0, 16).replace('T', ' ') + ' ' + TZ_NAME,
  },
  timeScale: {
    tickMarkFormatter: (t: Time, type: number): string => {
      const d = new Date(Number(t) * 1000 + TZ_OFFSET_MS)
      const hm = `${two(d.getUTCHours())}:${two(d.getUTCMinutes())}`
      // type: 0 año · 1 mes · 2 día · 3 hora · 4 hora con segundos (TickMarkType de lightweight-charts)
      if (type === 0) return String(d.getUTCFullYear())
      if (type === 1) return `${two(d.getUTCMonth() + 1)}/${d.getUTCFullYear()}`
      if (type === 2) return `${two(d.getUTCDate())}/${two(d.getUTCMonth() + 1)}`
      return hm
    },
  },
}
