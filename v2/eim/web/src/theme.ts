/** Tema único (T122): solo el futurista (`data-theme="cyber"`, fijo en index.html). Los gráficos
 * de canvas leen sus colores de las variables CSS con `cssVar`. */

export const cssVar = (name: string): string =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()

// Limpia la preferencia del interruptor de temas retirado (claro/oscuro) que pudiera quedar guardada.
try { localStorage.removeItem('eim.theme') } catch { /* sin almacenamiento */ }
