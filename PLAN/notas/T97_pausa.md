# T97 en pausa — decisión del usuario del 2026-11-26

**Origen:** al pedir «Ejecuta PLAN/T97.md», la tarea no podía arrancar tal como está escrita y el
usuario eligió **aparcarla hasta la revisión del 2026-12-29**, junto a T96. Cambiar esta regla =
archivo nuevo, nunca editar este.

## Por qué no arranca hoy (todo con fuente)
1. **No hay proveedor de acciones aprobado.** El entregable 2 de T97 lo exige, y la pregunta 2 de
   T88 (gastar en EODHD o Tiingo, o esperar) sigue **sin respuesta** (`T88_decisiones.md` §7). No
   hay fuente gratuita con licencia limpia: `yfinance` está **descartado** (los Términos de Yahoo
   prohíben la recolección automatizada y crear bases de datos), Stooq **no admite ingesta
   automatizada** y Massive gratis da 2 años de EOD, solo como contraste (§2.2–2.3).
2. **El ajuste por *splits* y dividendos** no está documentado en ningún proveedor (T88 §5.3):
   sin él, T97 no puede dar un veredicto honesto.
3. **Los 246 perpetuos TradFi de Binance** (la única renta variable con licencia ya en uso) tienen
   una **mediana de 134 días de histórico y ninguno de un año** (T88 §5.4), sin cifra de comisiones
   con fuente (§5.1); por la regla por defecto de T88 ◆4 se **observan**, sin veredicto de
   rentabilidad. Una clase montada solo sobre ellos saldría «sin potencia».
4. **T95 midió que hoy el escáner no supera el azar** (mejor candidata 0,664 frente al umbral del
   placebo 0,669; p global 0,16), y el entregable 4 de T97 corre ese escáner sobre el universo
   nuevo. Por eso T96 ya está en pausa (`T96_revision.md`).

## Regla para retomarla
- **El 2026-12-29** la tarea «EIM - revision para decidir T96 (2026-12-29)» escribe
  `TRADINGBOT/_revision_t96.md`. Ese informe decide también T97:
  - **ARRANCAR T96** → se le pregunta al usuario la ◆2 de T88 (proveedor de acciones: probar antes
    *splits* y dividendos con los planes gratuitos de Tiingo y EODHD, pagar uno, o hacer T97 en
    versión de observación sobre los perpetuos TradFi) y T97 arranca con esa respuesta.
  - **NO ARRANCAR** o **POSPONER** → T97 sigue en pausa y se revisa con la siguiente revisión de T96.
- El usuario puede levantar la pausa antes con una decisión nueva (en un archivo nuevo).
- Mientras tanto no corre nada nuevo: el escáner diario de T95 ya acumula la evidencia hacia
  adelante. T98 y T99 dependen de T97 y esperan con ella. La deuda de `yfinance` (T88 §4.1) sigue
  en BACKLOG, sin cambios.
