# T100 ◆ — Qué producto de renta fija, derivados u opciones merece clase propia

Fecha: 2026-11-26 · Insumo: `v2/reports/fixed_income_options_viability.md` (§4 veredicto por
producto, §5 recomendación) y la sonda real `v2/reports/fixed_income_probe.md` (curva del Tesoro
del 2026-11-25; fórmula de Svensson idéntica a la del BCE, 0,0 pb).

## Respuesta del usuario (2026-11-26): opción 1

> «Sí a las opciones cripto como información. Creo dos tareas nuevas: revisar los términos de
> Deribit y luego construir el agente de volatilidad.»

Queda fijado:

1. **Opciones cripto (BTC/ETH) entran, solo como información sobre la volatilidad.** No se
   operan, no votan dirección y no tocan plan, riesgo ni bróker (◆ de T145: solo análisis).
2. **Antes de guardar ninguna cadena se leen los términos de datos** de Deribit (y de Binance
   opciones, como alternativa). Deribit-cadenas no estaba en la lista cerrada de T88: esta ◆ lo
   admite **condicionado** a esa lectura. Si los términos prohíben guardar o usar los datos, la
   fuente no entra y T214 no empieza. → **T213**.
3. **El agente de superficie de volatilidad** se construye con pre-registro sobre el marco de
   T165 (HAR-IV con la pendiente del DVOL como referencia a batir). → **T214**.
4. **Ninguna otra clase**: bonos, ETF de renta fija, futuros de bonos, repos, swaps y opciones de
   acciones quedan como dice el §4 del informe. Los modelos de `eim/fixed_income/` y
   `eim/options/` quedan como biblioteca; los agentes de prueba de curva y carry, fuera del
   registro.

T100 queda cerrada (☑).
