/** Tema único: futurista (`data-theme="cyber"` fijo en index.html; los modos claro y oscuro se retiraron). */
export const cssVar = (name: string): string =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()
