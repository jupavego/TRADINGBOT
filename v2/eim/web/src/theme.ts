export type Theme = 'light' | 'dark'

const KEY = 'eim.theme'

export function initialTheme(): Theme {
  try {
    const s = localStorage.getItem(KEY)
    if (s === 'light' || s === 'dark') return s
  } catch { /* sin almacenamiento */ }
  return 'light' // claro y cálido por defecto (UI_SPEC)
}

export function applyTheme(t: Theme): void {
  document.documentElement.dataset.theme = t
  try { localStorage.setItem(KEY, t) } catch { /* ignora */ }
}

export const cssVar = (name: string): string =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()
