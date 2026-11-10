# T150 — Calibración de la confianza de la síntesis, antes (v1) y después (v2)

Generado el 2026-11-10 con `python scripts/t150_calibracion.py` (por la cola de T127, 2 procesos, 45 min, 2 pausas por huecos de captura). Datos: `reports/t150_calibracion.{json,csv}`. Análisis histórico: **no es una promesa de resultados**.

**Regla fijada antes de calcular (◆2 de T146):** la síntesis v2 se adopta en el panel sea cual sea el resultado, y esto se publica aunque sea desfavorable. Lo es.

## Lo que dice, en cuatro líneas

1. **La dirección de la síntesis acierta menos que una moneda.** En el banco de T131 (BTCUSDT 1 h, 2023-01 → 2026-11), acierta el signo del retorno a 24 h el **46,1 %** de las veces en muestras sin solape (n = 1 381, IC 95 % ±2,6 pp). El intervalo no llega al 50 %. Con v1 y con v2: v2 cambia cuánto dice saber, no hacia dónde apunta.
2. **La confianza no lleva información.** El acierto es plano en todos los tramos de confianza (46–48 % entre 0,1 y 0,4). Una síntesis que dice 35 % no acierta más que una que dice 15 %.
3. **Leída como «distancia a la moneda» (B), la confianza promete más de lo que hay**: con 0,25 publica un 62 % de acierto implícito y obtiene un 46 %. v2 lo reduce **muy poco** (ECE 0,143 → 0,140; Brier 0,2708 → 0,2700, ambos peor que decir siempre 50 %, 0,25).
4. **El comité no es de 14: es de ~1,9.** En el banco votan 5,7 agentes de media y equivalen a **1,88 votos efectivos**; en vivo, 6,5 votantes ≈ 2,1 votos (1 h) y 7,0 ≈ 2,3 (4 h).

Por qué v2 apenas baja la confianza media (0,221 → 0,215 en el banco): sacar del denominador a los agentes sin datos la **sube** (v1 los contaba como ceros que diluían en silencio) y la correlación la **baja**; las dos cosas casi se compensan. Ahora la cifra tiene una razón escrita detrás (factor «correlacion» y votos efectivos a la vista) en lugar de una dilución invisible.

## Método

- **Fuentes.** (1) Banco de T131 pasado por el panel de T44 (`eim/analytics/agent_panel.py`, reportes reales de los agentes salvo `plan`, `context` y `arbitrage`) cada 4 velas: 8 292 instantes. Las ventanas de v2 se cuentan en filas del panel con el mismo tramo de tiempo: cobertura 12 filas (48 h), correlación 50 (200 h). (2) Reportes guardados en vivo (copia `backups/eim_20261110-000029/reports.duckdb`, 13-oct → 9-nov), con las ventanas del panel tal cual (48 y 200 velas).
- **Resultado.** Signo del retorno de cierre a 24 velas en 1 h y 6 velas en 4 h (un día). Se cuenta cada instante con sesgo ≠ 0 y retorno ≠ 0.
- **Dos lecturas de la confianza**, porque el contrato no la fija: (A) probabilidad de acertar la dirección, lo que dice la ficha de T150; (B) distancia a la moneda: P(acierto) = 0,5 + confianza / 2. Referencias: Brier de decir siempre la tasa de acierto observada (A) o 0,5 (B, = 0,25).
- **Sin solape.** Los horizontes de 24 h se pisan entre instantes vecinos, así que el IC ingenuo es optimista; se da también con una muestra cada 24 h (banco) o cada horizonte (en vivo).
- La lectura A es mala para las dos versiones por construcción: con confianza 0,2 promete un 20 % de acierto en una apuesta binaria. Se publica porque es la que pedía la ficha, pero la que interpreta lo que el panel quiere decir es la B.

## Resultados

| Fuente | Variante | n | Acierto | Sin solape (n) | Conf. media | Votantes ≈ votos efectivos | Brier A (ref.) | Brier B (ref. 0,25) | ECE A | ECE B |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Banco T131 · BTC 1 h | v1 | 8 285 | 46,8 % | 46,1 % ±2,6 (1 381) | 0,221 | — | 0,316 (0,249) | 0,2708 | 0,246 | 0,143 |
| Banco T131 · BTC 1 h | **v2** | 8 285 | 46,8 % | 46,1 % ±2,6 (1 381) | 0,215 | 5,7 ≈ **1,88** | 0,319 (0,249) | **0,2700** | 0,254 | **0,140** |
| En vivo · BTC 1 h | v1 | 499 | 42,7 % | 52,4 % ±21 (21) | 0,184 | — | 0,309 (0,245) | 0,2733 | 0,243 | 0,165 |
| En vivo · BTC 1 h | **v2** | 499 | 41,7 % | 47,6 % ±21 (21) | 0,176 | 6,5 ≈ **2,12** | 0,308 (0,243) | 0,2747 | 0,241 | 0,171 |
| En vivo · BTC 4 h | v1 | 126 | 38,9 % | 42,9 % ±21 (21) | 0,174 | — | 0,284 (0,238) | 0,2756 | 0,221 | 0,198 |
| En vivo · BTC 4 h | **v2** | 126 | 38,1 % | 42,9 % ±21 (21) | 0,149 | 7,0 ≈ **2,30** | 0,290 (0,236) | **0,2728** | 0,232 | **0,194** |
| En vivo · ETH 1 h | v1 | 69 | 34,8 % | — (3) | 0,188 | — | 0,279 (0,227) | 0,2991 | 0,236 | 0,246 |
| En vivo · ETH 1 h | **v2** | 69 | 34,8 % | — (3) | 0,145 | 6,3 ≈ **1,57** | 0,295 (0,227) | **0,2894** | 0,293 | **0,231** |

En vivo son 4 semanas: 21 días sin solape en BTC y 3 en ETH. **No deciden nada**; se dan para que conste que no contradicen al banco.

### Fiabilidad en el banco (tramo de confianza → acierto real)

| Tramo | v1: n | v1: conf. media | v1: acierto | v2: n | v2: conf. media | v2: acierto |
|---|--:|--:|--:|--:|--:|--:|
| 0,0–0,1 | 322 | 0,091 | 48,4 % | 398 | 0,090 | 48,2 % |
| 0,1–0,2 | 2 996 | 0,143 | 46,9 % | 3 075 | 0,144 | 47,2 % |
| 0,2–0,3 | 3 223 | 0,245 | 45,9 % | 3 392 | 0,245 | 46,1 % |
| 0,3–0,4 | 1 744 | 0,336 | 47,8 % | 1 411 | 0,328 | 47,2 % |
| 0,4–0,5 | — | — | — | 9 | 0,415 | 22,2 % |

Una síntesis calibrada (lectura B) subiría del 54 % al 67 % de acierto de arriba abajo. La de aquí está plana en ~47 %.

## Qué se hace con esto

- **v2 se adopta en el panel** (regla previa): la confianza ya no se diluye en silencio con agentes sin datos ni cuenta cinco veces el mismo voto, y los votos efectivos y la cobertura están a la vista.
- **No se recalibra la confianza** con estos datos: escalarla a mano para que cuadre sería ajustar a un resultado ya visto, y la conclusión honesta es otra: **la síntesis direccional no tiene ventaja** (coincide con T44, T139 y T145). El panel debería decirlo, y eso es BACKLOG T145 (2): publicar en «Operaciones sugeridas» por qué no hay operaciones validadas.
- El bróker simulado, el plan y las estrategias de T49 siguen con v1: T150 no los toca (BACKLOG T150 (2)–(3)).
