export type Theme = 'cyber' | 'light' | 'dark'

const KEY = 'eim.theme'
const ORDER: Theme[] = ['cyber', 'dark', 'light']

export const THEME_LABEL: Record<Theme, string> = { cyber: 'Futurista', dark: 'Oscuro', light: 'Claro' }

export function initialTheme(): Theme {
  try {
    const s = localStorage.getItem(KEY)
    if (s === 'cyber' || s === 'light' || s === 'dark') return s
  } catch { /* sin almacenamiento */ }
  return 'cyber' // tema futurista por defecto; claro y oscuro siguen disponibles
}

/** Siguiente tema del ciclo Futurista → Oscuro → Claro. */
export const nextTheme = (t: Theme): Theme => ORDER[(ORDER.indexOf(t) + 1) % ORDER.length]

export function applyTheme(t: Theme): void {
  document.documentElement.dataset.theme = t
  try { localStorage.setItem(KEY, t) } catch { /* ignora */ }
}

export const cssVar = (name: string): string =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()
