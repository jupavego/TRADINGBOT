# A/B de salidas por perfil: protección progresiva frente a TP/BE+/tiempo (T111)

**SIMULADO, sin dinero real** · BTCUSDT · código `d757aa8 + cambios de la rama claude/t111-metricas-ab (commit de T111)` · camino de 15m hasta 2026-10-23 03:45 UTC.

## Cómo se reproduce

- Comando, desde `v2/` y sobre una **copia** del almacén: `python scripts/ppp_profiles_ab.py --data <copia> --symbol BTCUSDT --is-from 2026-08-16T00:00:00Z` (en un worktree, con `PYTHONPATH=.` delante para usar su `eim`). `--from-json <json>` rehace este informe sin recalcular.
- Datos: copia en caliente del almacén vivo (`POST /v2/share/snapshot` de T61, 2026-10-23): contextos de BTCUSDT por marco: 15m 3484 (2026-09-16 → 2026-10-23), 1h 33138 (2023-01-11 → 2026-10-23), 4h 1306 (2026-03-19 → 2026-10-23); 61.917 ideas sombra; velas de 15 m y funding real desde 2023. Velas de 1 min: el almacén vivo solo las tiene desde 2026-10-15; para esta corrida se sincronizó en la COPIA la historia desde 2023-01-01 con el proveedor del proyecto (`BinanceFutures.klines`, `fapi/v1/klines`): 2.003.274 velas, sin huecos.
- Tramos, sin optimizar nada: **fuera de muestra** = decisiones anteriores a 2026-08-16, inicio de la ventana con la que T48b ajustó el BE+ de A (2026-08-16 → 2026-10-16, `val_windows`); la escalera de B se diseñó y midió con datos desde 2026-09-10 (T105–T110). **Dentro de muestra** = desde 2026-08-16. Capital (10.000 USDT) y memoria de cada perfil se reinician en cada tramo.
- Costos y mecánica (`ExecParams`, iguales en A y B): taker 5,0 pb, maker 2,0 pb, deslizamiento de salida 1,0 pb + 0,10 × rango de la vela, de entrada a mercado 0,10 pb; BE+ de A: 1,0 R → +0,10 R en 1h, 4h; funding real. Criterios `validation_v1`, semilla 0. Mismo motor, mismas ideas, mismo camino.
- Escalera por perfil (versión de parámetros de T108/T109; la sensibilidad cambia solo el primer escalón y deja el incremento en la mitad):

| Perfil | Primer escalón | Incremento | BE+ conviviendo | Peso máx. propio |
|---|--:|--:|:-:|--:|
| conservador | 0,100 R | 0,0500 R | sí | 1,5 |
| moderado | 0,100 R | 0,0500 R | sí | 1,5 |
| agresivo | 0,075 R | 0,0375 R | sí | 1,5 |

- Arreglo previo al A/B (BACKLOG T109 (1)): la escalera entraba a mercado con el deslizamiento de SALIDA; ahora paga el de entrada de la sombra (`ladder._entry`), así que A y B entran al mismo precio. En los libros de B fuera de muestra eso deja de cobrarle ≈ 5.036 USDT (estimación directa del término quitado). Cambia también al control `ppp_btcusdt`.

## Conclusión

**La protección progresiva NO mejora a ningún perfil fuera de muestra.** Con las mismas entradas pierde más que la salida actual en los tres perfiles y con los tres umbrales probados.

| Perfil | A fuera de muestra (R/op) | B umbral del encargo (R/op) | B 0,5 R | B 1 R | Dentro de muestra: A → B encargo |
|---|--:|--:|--:|--:|--:|
| conservador | -2.919 (-0,121) | -2.993 (-0,133) | -3.699 (-0,156) | -3.897 (-0,166) | -288 → -106 |
| moderado | -4.474 (-0,071) | -7.458 (-0,106) | -5.975 (-0,084) | -6.959 (-0,124) | -2.264 → -941 |
| agresivo | -9.325 (-0,092) | -13.411 (-0,121) | -12.349 (-0,106) | -13.951 (-0,121) | -2.681 → -1.763 |

USDT netos de costos (cerrado + flotante de lo abierto al final); A/B emparejado (mismas entradas, mismo tamaño, velas de 1 min reales en las velas ambiguas). R/op sobre las cerradas.

- El orden real de los precios no la salva: con velas de 1 min B mejora frente a la regla conservadora (conservador -3.480 → -2.993, moderado -7.886 → -7.458, agresivo -13.941 → -13.411 USDT), pero sigue por debajo de A. Solo un orden sintético siempre favorable (cota optimista, no real) la pondría por delante en: conservador B 0.1 R (encargo), conservador B 0.5 R, moderado B 0.1 R (encargo), moderado B 0.5 R, agresivo B 0.075 R (encargo), agresivo B 0.5 R.
- Dentro de muestra (≈ 2 meses, el tramo con el que se diseñó la escalera) B sí perdía menos en conservador, moderado, agresivo: **no se confirma fuera de muestra**, que es lo que cuenta.
- Por tipo de día (emparejado fuera de muestra, B − A): con **tendencia** la escalera pierde lo que A ganaba (conservador -2.689, moderado -9.199, agresivo -12.191 USDT); en días **laterales** pierde menos que A (conservador +1.556, moderado +2.502, agresivo +4.423). La etiqueta del día es ex post: no sirve para elegir la salida al entrar (ver la tabla por régimen ex ante).
- Libro completo fuera de muestra (A → B encargo): conservador 530 → 11 ops, -2.966 → -42 USDT, -0,121 → -0,151 R/op; moderado 873 → 485 ops, -4.547 → -1.908 USDT, -0,071 → -0,083 R/op; agresivo 1339 → 395 ops, -9.398 → -4.498 USDT, -0,092 → -0,117 R/op. B pierde menos dinero porque **opera mucho menos** (su memoria propia pausa estrategias y el Conservador casi no sale de «en observación»), no porque la salida sea mejor: por operación es peor que A en conservador, moderado, agresivo.
- Ningún escenario es rentable: A y B **siguen siendo perdedores** en los dos tramos.
- La hipótesis de partida (como en T27: **no mejora**) se mantiene.

## Fuera de muestra: 2023-01-11 10:00 → 2026-08-15 22:00 UTC

52920 ideas sombra (por marco: 1h 50948, 4h 1972); capital y memoria de cada perfil reiniciados al empezar el tramo.

### A/B emparejado: las mismas entradas, solo cambia la salida

Entradas que A abrió de verdad, con su llenado y su tamaño (redondeado al paso de BTCUSDT en las dos columnas). Sin cuenta detrás: el drawdown va en R.

| Perfil | Escenario | Ops | Acierto | Ganado | Perdido | Neto USDT | PF | Esperanza R | Esperanza USDT | DD (R) | Costos USDT | Costo R | Activó prot. | Cierres |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| conservador | A (TP/BE+/tiempo) | 530 | 48 % | 8.626 | -11.545 | **-2.919** | 0,75 | -0,121 | -5,51 | 87,1 | 2.237 | 0,107 | — | SL ini 240 · TP 114 · BE 120 · tiempo 56 |
| conservador | B 0.1 R (encargo) | 530 | 76 % | 1.874 | -4.867 | **-2.993** | 0,39 | -0,133 | -5,65 | 75,0 | 2.367 | 0,115 | 426 | SL ini 104 · SL din 426 |
| conservador | B 0.5 R | 530 | 60 % | 6.001 | -9.700 | **-3.699** | 0,62 | -0,156 | -6,98 | 95,2 | 2.675 | 0,130 | 320 | SL ini 210 · SL din 320 |
| conservador | B 1 R | 530 | 50 % | 8.279 | -12.177 | **-3.897** | 0,68 | -0,166 | -7,35 | 99,5 | 2.861 | 0,139 | 265 | SL ini 265 · SL din 265 |
| moderado | A (TP/BE+/tiempo) | 873 | 52 % | 29.067 | -33.541 | **-4.474** | 0,87 | -0,071 | -5,12 | 94,3 | 7.056 | 0,104 | — | SL ini 379 · TP 213 · BE 208 · tiempo 73 |
| moderado | B 0.1 R (encargo) | 873 | 79 % | 6.049 | -13.507 | **-7.458** | 0,45 | -0,106 | -8,54 | 94,7 | 7.457 | 0,110 | 722 | SL ini 151 · SL din 722 |
| moderado | B 0.5 R | 873 | 65 % | 20.993 | -26.968 | **-5.975** | 0,78 | -0,084 | -6,84 | 91,9 | 8.551 | 0,125 | 564 | SL ini 309 · SL din 564 |
| moderado | B 1 R | 873 | 52 % | 28.276 | -35.234 | **-6.959** | 0,80 | -0,124 | -7,97 | 125,1 | 9.184 | 0,135 | 455 | SL ini 418 · SL din 455 |
| agresivo | A (TP/BE+/tiempo) | 1339 | 52 % | 47.729 | -57.053 | **-9.325** | 0,84 | -0,092 | -6,96 | 143,7 | 13.087 | 0,117 | — | SL ini 594 · TP 338 · BE 298 · tiempo 109 |
| agresivo | B 0.075 R (encargo) | 1339 | 77 % | 8.887 | -22.298 | **-13.411** | 0,40 | -0,121 | -10,02 | 162,2 | 13.854 | 0,124 | 1108 | SL ini 231 · SL din 1108 |
| agresivo | B 0.5 R | 1339 | 63 % | 33.755 | -46.104 | **-12.349** | 0,73 | -0,106 | -9,22 | 151,3 | 15.924 | 0,141 | 843 | SL ini 496 · SL din 843 |
| agresivo | B 1 R | 1339 | 52 % | 45.427 | -59.378 | **-13.951** | 0,77 | -0,121 | -10,42 | 169,3 | 17.323 | 0,151 | 698 | SL ini 641 · SL din 698 |

Mismo precio de entrada en A y B: todas las parejas. Ninguna entrada de A quedaría fuera por el filtro de viabilidad de B.

### Libro completo de cada perfil (lo que haría el perfil adoptado)

Cada escenario con su propio libro: sus entradas cambian porque los cupos se liberan antes y porque con escalera el perfil aprende de SUS cierres (T109).

| Perfil | Escenario | Ops | Acierto | Ganado | Perdido | Neto USDT | PF | Esperanza R | Esperanza USDT | Capital final | Rentab. | DD equity | Costos USDT | Costo R | Activó prot. | Cierres |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| conservador | A (TP/BE+/tiempo) | 530 | 48 % | 8.715 | -11.681 | **-2.966** | 0,75 | -0,121 | -5,60 | 7.034 | -29,7 % | 34,0 % | 2.260 | 0,107 | — | SL ini 240 · TP 114 · BE 120 · tiempo 56 |
| conservador | B 0.1 R (encargo) | 11 | 73 % | 27 | -69 | **-42** | 0,40 | -0,151 | -3,78 | 9.958 | -0,4 % | 0,7 % | 54 | 0,197 | 9 | SL ini 2 · SL din 9 |
| conservador | B 0.5 R | 18 | 72 % | 149 | -149 | **-1** | 1,00 | -0,001 | -0,04 | 9.999 | -0,0 % | 0,8 % | 87 | 0,193 | 13 | SL ini 5 · SL din 13 |
| conservador | B 1 R | 68 | 62 % | 833 | -776 | **57** | 1,07 | +0,012 | +0,84 | 10.057 | 0,6 % | 2,4 % | 321 | 0,178 | 43 | SL ini 25 · SL din 43 |
| moderado | A (TP/BE+/tiempo) | 873 | 52 % | 29.239 | -33.786 | **-4.547** | 0,87 | -0,071 | -5,21 | 5.453 | -45,5 % | 54,9 % | 7.099 | 0,104 | — | SL ini 379 · TP 213 · BE 208 · tiempo 73 |
| moderado | B 0.1 R (encargo) | 485 | 80 % | 1.868 | -3.776 | **-1.908** | 0,49 | -0,083 | -3,93 | 8.092 | -19,1 % | 19,3 % | 2.126 | 0,110 | 408 | SL ini 77 · SL din 408 |
| moderado | B 0.5 R | 720 | 67 % | 15.734 | -17.331 | **-1.597** | 0,91 | -0,047 | -2,22 | 8.403 | -16,0 % | 27,1 % | 5.704 | 0,123 | 479 | SL ini 241 · SL din 479 |
| moderado | B 1 R | 581 | 52 % | 11.932 | -14.791 | **-2.859** | 0,81 | -0,107 | -4,92 | 7.141 | -28,6 % | 33,1 % | 3.807 | 0,136 | 306 | SL ini 275 · SL din 306 |
| agresivo | A (TP/BE+/tiempo) | 1339 | 52 % | 47.982 | -57.380 | **-9.398** | 0,84 | -0,092 | -7,02 | 602 | -94,0 % | 95,4 % | 13.151 | 0,117 | — | SL ini 594 · TP 338 · BE 298 · tiempo 109 |
| agresivo | B 0.075 R (encargo) | 395 | 77 % | 3.119 | -7.617 | **-4.498** | 0,41 | -0,117 | -11,39 | 5.502 | -45,0 % | 45,0 % | 4.891 | 0,123 | 329 | SL ini 66 · SL din 329 |
| agresivo | B 0.5 R | 395 | 63 % | 10.348 | -15.941 | **-5.592** | 0,65 | -0,131 | -14,16 | 4.408 | -55,9 % | 56,3 % | 5.147 | 0,135 | 248 | SL ini 147 · SL din 248 |
| agresivo | B 1 R | 426 | 55 % | 22.085 | -24.681 | **-2.596** | 0,89 | -0,038 | -6,09 | 7.404 | -26,0 % | 45,0 % | 7.087 | 0,145 | 237 | SL ini 189 · SL din 237 |

### Protección: activación, escalones y lo devuelto (libro completo)

| Perfil | Escenario | Activó | Escalones alcanzados (escalón: ops) | Flotante máx. medio (neto reg.) | Avance máx. medio (precio) | Escalón máx. | Devuelto medio vs flotante máx. | Realizado − protegido medio | Abiertas fin | Incid. | Inconsist. | Errores de ejecución |
|---|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| conservador | B 0.1 R (encargo) | 9 (82 %) | 0: 2, 1: 2, 2: 3, 3: 1, 5: 1, 8: 1, 13: 1 | 4,80 | 14,57 | 13 (0,70 R) | 8,58 | -3,84 | 0 | 0 | 0 | 0 |
| conservador | B 0.5 R | 13 (72 %) | 0: 5, 1: 11, 2: 1, 4: 1 | 13,95 | 23,08 | 4 (1,25 R) | 13,99 | -3,18 | 0 | 0 | 0 | 0 |
| conservador | B 1 R | 43 (63 %) | 0: 36, 1: 28, 2: 4 | 22,91 | 29,94 | 2 (1,50 R) | 20,57 | -3,03 | 0 | 0 | 0 | 0 |
| moderado | B 0.1 R (encargo) | 408 (84 %) | 0: 77, 1: 234, 2: 79, 3: 42, 4: 15, 5: 16, 6: 6, 7: 2 … | 5,69 | 14,05 | 18 (0,95 R) | 8,99 | -1,78 | 0 | 0 | 0 | 0 |
| moderado | B 0.5 R | 479 (67 %) | 0: 241, 1: 399, 2: 51, 3: 19, 4: 9, 5: 1 | 31,25 | 44,45 | 5 (1,50 R) | 31,93 | -4,50 | 0 | 0 | 0 | 0 |
| moderado | B 1 R | 306 (53 %) | 0: 324, 1: 239, 2: 15, 3: 2, 4: 1 | 35,56 | 44,52 | 4 (2,50 R) | 39,80 | -3,89 | 0 | 0 | 0 | 0 |
| agresivo | B 0.075 R (encargo) | 329 (83 %) | 0: 66, 1: 156, 2: 70, 3: 41, 4: 21, 5: 11, 6: 7, 7: 3 … | 12,03 | 35,42 | 21 (0,82 R) | 22,13 | -4,89 | 0 | 0 | 0 | 0 |
| agresivo | B 0.5 R | 248 (63 %) | 0: 147, 1: 215, 2: 21, 3: 8, 4: 4 | 40,88 | 61,42 | 4 (1,25 R) | 53,90 | -8,40 | 0 | 0 | 0 | 0 |
| agresivo | B 1 R | 237 (56 %) | 0: 222, 1: 189, 2: 13, 3: 2 | 84,44 | 109,42 | 3 (2,00 R) | 88,97 | -7,80 | 0 | 0 | 0 | 0 |

### ¿Corta la escalera a las ganadoras? (emparejado)

| Perfil | Umbral | A cerró en TP (n, R medio) | B en esas mismas: R medio | B se llevó menos / quedó en pérdida | USDT cedidos | Ganadoras de A: R medio A → B | Perdedoras de A: R medio A → B | Perdedoras de A que B salvó | Duración media A → B |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| conservador | B 0.1 R (encargo) | 114 (+1,72) | +0,13 | 114 / 2 | 7.089 | +0,87 → +0,12 | -1,03 → -0,36 | 162 de 277 | 14,6 h → 3,0 h |
| conservador | B 0.5 R | 114 (+1,72) | +0,50 | 114 / 0 | 5.440 | +0,87 → +0,49 | -1,03 → -0,74 | 67 de 277 | 14,6 h → 8,7 h |
| conservador | B 1 R | 114 (+1,72) | +0,98 | 112 / 0 | 3.324 | +0,87 → +0,78 | -1,03 → -1,03 | 14 de 277 | 14,6 h → 13,8 h |
| moderado | B 0.1 R (encargo) | 213 (+1,63) | +0,12 | 213 / 9 | 24.459 | +0,85 → +0,11 | -1,05 → -0,34 | 258 de 423 | 16,6 h → 3,3 h |
| moderado | B 0.5 R | 213 (+1,63) | +0,50 | 213 / 0 | 18.235 | +0,85 → +0,49 | -1,05 → -0,70 | 114 de 423 | 16,6 h → 9,6 h |
| moderado | B 1 R | 213 (+1,63) | +1,00 | 208 / 0 | 10.380 | +0,85 → +0,75 | -1,05 → -1,05 | 16 de 423 | 16,6 h → 16,0 h |
| agresivo | B 0.075 R (encargo) | 338 (+1,55) | +0,11 | 337 / 22 | 40.680 | +0,84 → +0,10 | -1,08 → -0,36 | 384 de 648 | 12,1 h → 2,3 h |
| agresivo | B 0.5 R | 338 (+1,55) | +0,52 | 336 / 0 | 29.409 | +0,84 → +0,51 | -1,08 → -0,76 | 154 de 648 | 12,1 h → 7,5 h |
| agresivo | B 1 R | 338 (+1,55) | +1,02 | 324 / 0 | 15.669 | +0,84 → +0,78 | -1,08 → -1,08 | 22 de 648 | 12,1 h → 12,1 h |

### Condiciones de mercado (umbral del encargo)

Etiqueta del día UTC de la decisión, medida con sus velas de 15 m (ex post, cuantiles fijos de todos los días; ver `ab_conditions.py`), y régimen que el agente asignó al decidir (ex ante, el único que se conoce antes de entrar).

| Condición (emparejado) | conservador: n · A R/op · B R/op · B−A USDT | moderado: n · A R/op · B R/op · B−A USDT | agresivo: n · A R/op · B R/op · B−A USDT |
|---|--:|--:|--:|
| Tendencia | 244 · +0,205 · -0,093 · -2.689 | 385 · +0,259 · -0,039 · -9.199 | 554 · +0,189 · -0,049 · -12.191 |
| Intermedio | 145 · -0,392 · -0,160 · +1.153 | 258 · -0,364 · -0,110 · +3.900 | 405 · -0,283 · -0,140 · +4.065 |
| Lateral | 138 · -0,446 · -0,184 · +1.556 | 225 · -0,308 · -0,210 · +2.502 | 375 · -0,305 · -0,203 · +4.423 |
| Volatilidad alta | 461 · -0,101 · -0,124 · -190 | 722 · -0,047 · -0,105 · -3.954 | 1023 · -0,025 · -0,111 · -8.483 |
| Volatilidad baja | 66 · -0,330 · -0,213 · +210 | 146 · -0,200 · -0,101 · +1.157 | 311 · -0,317 · -0,149 · +4.781 |
| Con movimiento brusco | 164 · -0,010 · -0,094 · -458 | 226 · +0,009 · -0,079 · -1.811 | 256 · +0,033 · -0,083 · -4.515 |
| Sin movimiento brusco | 363 · -0,184 · -0,154 · +479 | 642 · -0,102 · -0,113 · -986 | 1078 · -0,123 · -0,129 · +813 |

| Condición (régimen ex ante, emparejado) | conservador: n · A R/op · B R/op · B−A USDT | moderado: n · A R/op · B R/op · B−A USDT | agresivo: n · A R/op · B R/op · B−A USDT |
|---|--:|--:|--:|
| range | 305 · -0,190 · -0,180 · +130 | 596 · -0,125 · -0,132 · -1.209 | 1032 · -0,118 · -0,134 · -2.048 |
| trend_down | 24 · -0,040 · +0,112 · +155 | 30 · +0,077 · +0,025 · +43 | 35 · -0,101 · +0,052 · +519 |
| trend_up | 16 · -0,306 · +0,125 · +290 | 28 · -0,056 · +0,058 · +367 | 46 · -0,041 · -0,091 · +300 |
| volatile | 185 · -0,002 · -0,111 · -649 | 219 · +0,054 · -0,076 · -2.186 | 226 · +0,022 · -0,094 · -2.857 |

| Condición (libro completo) | conservador: n · A R/op · B R/op · B−A USDT | moderado: n · A R/op · B R/op · B−A USDT | agresivo: n · A R/op · B R/op · B−A USDT |
|---|--:|--:|--:|
| Tendencia | 244/6 · +0,205 · +0,077 · -1.692 | 385/209 · +0,259 · -0,075 · -8.887 | 554/163 · +0,189 · -0,154 · -11.854 |
| Intermedio | 145/0 · -0,392 · — · +2.194 | 258/151 · -0,364 · -0,118 · +5.685 | 405/132 · -0,283 · -0,107 · +8.374 |
| Lateral | 138/0 · -0,446 · — · +2.584 | 225/120 · -0,308 · -0,037 · +6.029 | 375/95 · -0,305 · -0,048 · +8.764 |
| Volatilidad alta | 461/6 · -0,101 · +0,077 · +2.363 | 722/357 · -0,047 · -0,103 · +457 | 1023/274 · -0,025 · -0,164 · -2.423 |
| Volatilidad baja | 66/0 · -0,330 · — · +722 | 146/123 · -0,200 · -0,010 · +2.370 | 311/116 · -0,317 · +0,009 · +7.708 |
| Con movimiento brusco | 164/6 · -0,010 · +0,077 · +279 | 226/137 · +0,009 · -0,037 · -579 | 256/109 · +0,033 · -0,084 · -3.082 |
| Sin movimiento brusco | 363/0 · -0,184 · — · +2.807 | 642/343 · -0,102 · -0,096 · +3.406 | 1078/281 · -0,123 · -0,123 · +8.367 |

### Entradas: por qué cambian entre A y B (libro completo)

| Perfil | Escenario | Entradas A | Entradas B | Comunes | Solo A | Solo B | Por qué B no tomó las de A | Entradas por mínimo de abiertas A / B |
|---|---|--:|--:|--:|--:|--:|---|--:|
| conservador | B 0.1 R (encargo) | 530 | 11 | 6 | 524 | 5 | en observación (memoria) 524 | 117 / 11 |
| conservador | B 0.5 R | 530 | 18 | 12 | 518 | 6 | en observación (memoria) 518 | 117 / 18 |
| conservador | B 1 R | 530 | 68 | 41 | 489 | 27 | en observación (memoria) 456, estrategia en pausa (memoria) 32, otro 1 | 117 / 63 |
| moderado | B 0.1 R (encargo) | 873 | 485 | 206 | 667 | 279 | estrategia en pausa (memoria) 663, costo > tope 1, contexto en pausa (memoria) 1, freno de entradas 1, otro 1 | 16 / 16 |
| moderado | B 0.5 R | 873 | 720 | 249 | 624 | 471 | estrategia en pausa (memoria) 601, contexto en pausa (memoria) 7, tope de riesgo por dirección 6, otro 3, cupo lleno 3, freno de entradas 3, costo > tope 1 | 16 / 26 |
| moderado | B 1 R | 873 | 581 | 234 | 639 | 347 | estrategia en pausa (memoria) 605, cupo lleno 14, freno de entradas 10, contexto en pausa (memoria) 4, otro 3, tope de riesgo por dirección 2, costo > tope 1 | 16 / 21 |
| agresivo | B 0.075 R (encargo) | 1339 | 395 | 103 | 1236 | 292 | estrategia en pausa (memoria) 1218, freno de entradas 8, costo > tope 8, tope de riesgo por dirección 2 | 19 / 8 |
| agresivo | B 0.5 R | 1339 | 395 | 97 | 1242 | 298 | estrategia en pausa (memoria) 1208, freno de entradas 13, costo > tope 8, tope de riesgo por dirección 7, contexto en pausa (memoria) 6 | 19 / 8 |
| agresivo | B 1 R | 1339 | 426 | 101 | 1238 | 325 | estrategia en pausa (memoria) 1180, tope de riesgo por dirección 23, freno de entradas 18, costo > tope 10, contexto en pausa (memoria) 7 | 19 / 6 |

### Sensibilidad al orden de los precios dentro de la vela

B con velas de 1 min reales (lo de arriba) frente a una cota optimista SINTÉTICA: dentro de cada vela de 15 m, siempre primero el extremo a favor y luego el contrario. No es un dato real: dice cuánto depende el resultado de ese orden.

| Perfil | Umbral | A neto (R/op) | B con 1 min reales (R/op) | B cota optimista sintética (R/op) | ¿La cota supera a A? |
|---|---|--:|--:|--:|---|
| conservador | B 0.1 R (encargo) | -2.919 (-0,121) | -2.993 (-0,133) | -796 (-0,026) | sí |
| conservador | B 0.5 R | -2.919 (-0,121) | -3.699 (-0,156) | -2.080 (-0,074) | sí |
| conservador | B 1 R | -2.919 (-0,121) | -3.897 (-0,166) | -2.929 (-0,118) | no |
| moderado | B 0.1 R (encargo) | -4.474 (-0,071) | -7.458 (-0,106) | -493 (-0,007) | sí |
| moderado | B 0.5 R | -4.474 (-0,071) | -5.975 (-0,084) | -853 (-0,012) | sí |
| moderado | B 1 R | -4.474 (-0,071) | -6.959 (-0,124) | -4.643 (-0,088) | no |
| agresivo | B 0.075 R (encargo) | -9.325 (-0,092) | -13.411 (-0,121) | 320 (-0,005) | sí |
| agresivo | B 0.5 R | -9.325 (-0,092) | -12.349 (-0,106) | -2.295 (-0,036) | sí |
| agresivo | B 1 R | -9.325 (-0,092) | -13.951 (-0,121) | -10.458 (-0,097) | no |

## Dentro de muestra: 2026-08-16 00:00 → 2026-10-23 03:45 UTC

8997 ideas sombra (por marco: 1h 2973, 4h 973, 15m 5051); capital y memoria de cada perfil reiniciados al empezar el tramo.

### A/B emparejado: las mismas entradas, solo cambia la salida

Entradas que A abrió de verdad, con su llenado y su tamaño (redondeado al paso de BTCUSDT en las dos columnas). Sin cuenta detrás: el drawdown va en R.

| Perfil | Escenario | Ops | Acierto | Ganado | Perdido | Neto USDT | PF | Esperanza R | Esperanza USDT | DD (R) | Costos USDT | Costo R | Activó prot. | Cierres |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| conservador | A (TP/BE+/tiempo) | 72 | 46 % | 1.552 | -1.840 | **-288** | 0,84 | -0,123 | -4,00 | 16,5 | 339 | 0,109 | — | SL ini 35 · TP 19 · BE 10 · tiempo 8 |
| conservador | B 0.1 R (encargo) | 72 | 83 % | 342 | -448 | **-106** | 0,76 | -0,034 | -1,47 | 5,7 | 339 | 0,107 | 63 | SL ini 9 · SL din 63 |
| conservador | B 0.5 R | 72 | 61 % | 984 | -1.504 | **-520** | 0,65 | -0,140 | -7,22 | 12,8 | 412 | 0,130 | 44 | SL ini 28 · SL din 44 |
| conservador | B 1 R | 71 | 51 % | 1.421 | -1.820 | **-400** | 0,78 | -0,124 | -5,63 | 15,2 | 435 | 0,136 | 36 | SL ini 35 · SL din 36 |
| moderado | A (TP/BE+/tiempo) | 141 | 45 % | 3.306 | -5.570 | **-2.264** | 0,59 | -0,171 | -16,06 | 24,1 | 1.028 | 0,109 | — | SL ini 66 · TP 33 · BE 21 · tiempo 21 |
| moderado | B 0.1 R (encargo) | 141 | 80 % | 883 | -1.824 | **-941** | 0,48 | -0,103 | -6,67 | 16,0 | 1.006 | 0,105 | 117 | SL ini 24 · SL din 117 |
| moderado | B 0.5 R | 141 | 60 % | 2.552 | -4.688 | **-2.136** | 0,54 | -0,155 | -15,15 | 22,2 | 1.176 | 0,123 | 85 | SL ini 56 · SL din 85 |
| moderado | B 1 R | 140 | 48 % | 4.052 | -5.783 | **-1.731** | 0,70 | -0,131 | -12,37 | 22,5 | 1.248 | 0,133 | 67 | SL ini 73 · SL din 67 |
| agresivo | A (TP/BE+/tiempo) | 98 | 44 % | 6.620 | -9.301 | **-2.681** | 0,71 | -0,185 | -27,36 | 18,8 | 1.950 | 0,127 | — | SL ini 50 · TP 25 · BE 11 · tiempo 12 |
| agresivo | B 0.075 R (encargo) | 98 | 79 % | 1.219 | -2.982 | **-1.763** | 0,41 | -0,137 | -17,99 | 13,7 | 1.935 | 0,124 | 80 | SL ini 18 · SL din 80 |
| agresivo | B 0.5 R | 98 | 59 % | 4.691 | -7.102 | **-2.412** | 0,66 | -0,174 | -24,61 | 18,6 | 2.280 | 0,148 | 58 | SL ini 40 · SL din 58 |
| agresivo | B 1 R | 98 | 45 % | 6.207 | -10.049 | **-3.841** | 0,62 | -0,231 | -39,20 | 23,6 | 2.400 | 0,155 | 44 | SL ini 54 · SL din 44 |

Mismo precio de entrada en A y B: todas las parejas. Entradas que B no habría abierto (contadas aparte, fuera de la tabla): conservador B 1 R: 1 vetadas por la viabilidad de B (A -33 USDT, B -33), 0 no negociables; moderado B 1 R: 1 vetadas por la viabilidad de B (A -66 USDT, B -66), 0 no negociables.

### Libro completo de cada perfil (lo que haría el perfil adoptado)

Cada escenario con su propio libro: sus entradas cambian porque los cupos se liberan antes y porque con escalera el perfil aprende de SUS cierres (T109).

| Perfil | Escenario | Ops | Acierto | Ganado | Perdido | Neto USDT | PF | Esperanza R | Esperanza USDT | Capital final | Rentab. | DD equity | Costos USDT | Costo R | Activó prot. | Cierres |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| conservador | A (TP/BE+/tiempo) | 72 | 46 % | 1.576 | -1.858 | **-282** | 0,85 | -0,123 | -3,91 | 9.718 | -2,8 % | 9,7 % | 343 | 0,109 | — | SL ini 35 · TP 19 · BE 10 · tiempo 8 |
| conservador | B 0.1 R (encargo) | 10 | 90 % | 27 | -30 | **-3** | 0,90 | -0,013 | -0,31 | 9.997 | -0,0 % | 0,3 % | 38 | 0,155 | 9 | SL ini 1 · SL din 9 |
| conservador | B 0.5 R | 10 | 40 % | 45 | -177 | **-132** | 0,25 | -0,534 | -13,20 | 9.868 | -1,3 % | 1,5 % | 47 | 0,191 | 4 | SL ini 6 · SL din 4 |
| conservador | B 1 R | 12 | 42 % | 101 | -205 | **-104** | 0,49 | -0,348 | -8,68 | 9.896 | -1,0 % | 2,0 % | 59 | 0,200 | 5 | SL ini 7 · SL din 5 |
| moderado | A (TP/BE+/tiempo) | 141 | 45 % | 3.344 | -5.615 | **-2.272** | 0,60 | -0,171 | -16,11 | 7.728 | -22,7 % | 23,0 % | 1.037 | 0,109 | — | SL ini 66 · TP 33 · BE 21 · tiempo 21 |
| moderado | B 0.1 R (encargo) | 340 | 82 % | 1.069 | -2.242 | **-1.173** | 0,48 | -0,065 | -3,45 | 8.827 | -11,7 % | 12,5 % | 1.182 | 0,101 | 293 | SL ini 47 · SL din 293 |
| moderado | B 0.5 R | 317 | 65 % | 3.295 | -4.700 | **-1.405** | 0,70 | -0,073 | -4,43 | 8.595 | -14,1 % | 15,2 % | 1.337 | 0,125 | 205 | SL ini 112 · SL din 205 |
| moderado | B 1 R | 264 | 48 % | 2.820 | -4.117 | **-1.297** | 0,69 | -0,170 | -4,91 | 8.703 | -13,0 % | 13,0 % | 931 | 0,136 | 127 | SL ini 137 · SL din 127 |
| agresivo | A (TP/BE+/tiempo) | 98 | 44 % | 6.644 | -9.331 | **-2.687** | 0,71 | -0,185 | -27,42 | 7.313 | -26,9 % | 30,8 % | 1.956 | 0,127 | — | SL ini 50 · TP 25 · BE 11 · tiempo 12 |
| agresivo | B 0.075 R (encargo) | 341 | 77 % | 2.115 | -6.172 | **-4.056** | 0,34 | -0,126 | -11,90 | 5.944 | -40,6 % | 41,4 % | 3.592 | 0,127 | 283 | SL ini 58 · SL din 283 |
| agresivo | B 0.5 R | 294 | 64 % | 8.955 | -12.148 | **-3.192** | 0,74 | -0,103 | -10,86 | 6.804 | -32,0 % | 37,2 % | 4.127 | 0,147 | 187 | SL ini 107 · SL din 187 |
| agresivo | B 1 R | 222 | 51 % | 9.900 | -12.651 | **-2.751** | 0,78 | -0,100 | -12,39 | 7.276 | -27,2 % | 30,9 % | 3.596 | 0,163 | 114 | SL ini 108 · SL din 114 |

### Protección: activación, escalones y lo devuelto (libro completo)

| Perfil | Escenario | Activó | Escalones alcanzados (escalón: ops) | Flotante máx. medio (neto reg.) | Avance máx. medio (precio) | Escalón máx. | Devuelto medio vs flotante máx. | Realizado − protegido medio | Abiertas fin | Incid. | Inconsist. | Errores de ejecución |
|---|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| conservador | B 0.1 R (encargo) | 9 (90 %) | 0: 1, 1: 8, 11: 1 | 3,75 | 9,49 | 11 (0,60 R) | 4,06 | -0,86 | 0 | 0 | 0 | 0 |
| conservador | B 0.5 R | 4 (40 %) | 0: 6, 1: 3, 2: 1 | 9,66 | 14,66 | 2 (0,75 R) | 22,86 | -2,61 | 0 | 0 | 0 | 0 |
| conservador | B 1 R | 5 (42 %) | 0: 7, 1: 5 | 15,52 | 23,02 | 1 (1,00 R) | 24,19 | -4,45 | 0 | 0 | 0 | 0 |
| moderado | B 0.1 R (encargo) | 293 (86 %) | 0: 47, 1: 194, 2: 51, 3: 29, 4: 10, 5: 3, 6: 4, 11: 1 … | 4,17 | 10,15 | 19 (1,00 R) | 7,40 | -1,00 | 0 | 0 | 0 | 0 |
| moderado | B 0.5 R | 205 (65 %) | 0: 112, 1: 181, 2: 15, 3: 6, 4: 3 | 13,77 | 20,29 | 4 (1,25 R) | 18,05 | -1,16 | 0 | 0 | 0 | 0 |
| moderado | B 1 R | 127 (48 %) | 0: 153, 1: 107, 2: 4 | 16,88 | 21,67 | 2 (1,50 R) | 21,63 | -0,83 | 0 | 0 | 0 | 0 |
| agresivo | B 0.075 R (encargo) | 283 (83 %) | 0: 58, 1: 162, 2: 60, 3: 27, 4: 14, 5: 9, 6: 5, 7: 2 … | 8,15 | 27,65 | 12 (0,49 R) | 18,13 | -2,49 | 0 | 0 | 0 | 0 |
| agresivo | B 0.5 R | 187 (64 %) | 0: 107, 1: 166, 2: 17, 3: 2, 4: 2 | 40,34 | 63,52 | 4 (1,25 R) | 50,15 | -3,75 | 1 | 0 | 0 | 0 |
| agresivo | B 1 R | 114 (51 %) | 0: 117, 1: 100, 2: 4, 3: 1 | 67,58 | 93,53 | 3 (2,00 R) | 78,57 | -5,47 | 3 | 0 | 0 | 0 |

### ¿Corta la escalera a las ganadoras? (emparejado)

| Perfil | Umbral | A cerró en TP (n, R medio) | B en esas mismas: R medio | B se llevó menos / quedó en pérdida | USDT cedidos | Ganadoras de A: R medio A → B | Perdedoras de A: R medio A → B | Perdedoras de A que B salvó | Duración media A → B |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| conservador | B 0.1 R (encargo) | 19 (+1,56) | +0,18 | 19 / 0 | 1.328 | +0,97 → +0,14 | -1,05 → -0,18 | 30 de 39 | 18,5 h → 4,1 h |
| conservador | B 0.5 R | 19 (+1,56) | +0,52 | 19 / 0 | 986 | +0,97 → +0,51 | -1,05 → -0,69 | 11 de 39 | 18,5 h → 13,8 h |
| conservador | B 1 R | 19 (+1,56) | +1,00 | 19 / 0 | 567 | +0,97 → +0,80 | -1,04 → -0,93 | 4 de 38 | 18,7 h → 20,9 h |
| moderado | B 0.1 R (encargo) | 33 (+1,55) | +0,11 | 33 / 0 | 2.822 | +0,88 → +0,10 | -1,05 → -0,27 | 53 de 77 | 20,6 h → 3,9 h |
| moderado | B 0.5 R | 33 (+1,55) | +0,50 | 33 / 0 | 2.071 | +0,88 → +0,51 | -1,05 → -0,71 | 21 de 77 | 20,6 h → 13,3 h |
| moderado | B 1 R | 33 (+1,55) | +1,02 | 33 / 0 | 1.032 | +0,88 → +0,91 | -1,04 → -1,01 | 5 de 76 | 20,7 h → 23,4 h |
| agresivo | B 0.075 R (encargo) | 25 (+1,54) | +0,11 | 25 / 1 | 5.688 | +0,96 → +0,11 | -1,08 → -0,33 | 35 de 55 | 16,1 h → 3,4 h |
| agresivo | B 0.5 R | 25 (+1,54) | +0,51 | 25 / 0 | 4.096 | +0,96 → +0,47 | -1,08 → -0,68 | 16 de 55 | 16,1 h → 10,7 h |
| agresivo | B 1 R | 25 (+1,54) | +1,02 | 23 / 0 | 2.039 | +0,96 → +0,77 | -1,08 → -1,01 | 4 de 55 | 16,1 h → 19,0 h |

### Condiciones de mercado (umbral del encargo)

Etiqueta del día UTC de la decisión, medida con sus velas de 15 m (ex post, cuantiles fijos de todos los días; ver `ab_conditions.py`), y régimen que el agente asignó al decidir (ex ante, el único que se conoce antes de entrar).

| Condición (emparejado) | conservador: n · A R/op · B R/op · B−A USDT | moderado: n · A R/op · B R/op · B−A USDT | agresivo: n · A R/op · B R/op · B−A USDT |
|---|--:|--:|--:|
| Tendencia | 40 · -0,093 · -0,086 · -184 | 68 · -0,012 · -0,138 · +205 | 51 · -0,204 · -0,181 · +118 |
| Intermedio | 16 · +0,011 · +0,044 · +38 | 43 · -0,094 · +0,013 · +97 | 23 · -0,054 · -0,187 · -575 |
| Lateral | 16 · -0,332 · +0,017 · +328 | 30 · -0,643 · -0,191 · +1.021 | 24 · -0,269 · +0,004 · +1.376 |
| Volatilidad alta | 46 · -0,059 · -0,093 · -72 | 87 · -0,028 · -0,169 · +458 | 61 · +0,033 · -0,112 · -1.259 |
| Volatilidad baja | 26 · -0,237 · +0,070 · +254 | 54 · -0,402 · +0,004 · +865 | 37 · -0,544 · -0,178 · +2.177 |
| Con movimiento brusco | 19 · +0,515 · +0,092 · -450 | 25 · +0,265 · -0,101 · -12 | 13 · +0,450 · -0,127 · -1.173 |
| Sin movimiento brusco | 53 · -0,352 · -0,079 · +632 | 116 · -0,265 · -0,103 · +1.335 | 85 · -0,282 · -0,138 · +2.091 |

| Condición (régimen ex ante, emparejado) | conservador: n · A R/op · B R/op · B−A USDT | moderado: n · A R/op · B R/op · B−A USDT | agresivo: n · A R/op · B R/op · B−A USDT |
|---|--:|--:|--:|
| range | 42 · -0,371 · -0,045 · +557 | 81 · -0,339 · -0,131 · +1.348 | 56 · -0,405 · -0,189 · +1.589 |
| trend_down | 1 · -1,191 · +0,018 · +59 | 1 · -1,191 · +0,018 · +104 | 1 · -1,191 · +0,018 · +210 |
| trend_up | 3 · +0,324 · +0,135 · -11 | 3 · -1,119 · +0,101 · +82 | 2 · +0,201 · +0,037 · -70 |
| volatile | 26 · +0,267 · -0,039 · -423 | 56 · +0,141 · -0,076 · -211 | 39 · +0,136 · -0,075 · -812 |

| Condición (libro completo) | conservador: n · A R/op · B R/op · B−A USDT | moderado: n · A R/op · B R/op · B−A USDT | agresivo: n · A R/op · B R/op · B−A USDT |
|---|--:|--:|--:|
| Tendencia | 40/8 · -0,093 · -0,060 · -65 | 68/171 · -0,012 · -0,070 · +189 | 51/159 · -0,204 · -0,093 · +25 |
| Intermedio | 16/2 · +0,011 · +0,174 · +13 | 43/94 · -0,094 · -0,013 · +61 | 23/97 · -0,054 · -0,129 · -1.309 |
| Lateral | 16/0 · -0,332 · — · +331 | 30/75 · -0,643 · -0,117 · +850 | 24/85 · -0,269 · -0,186 · -85 |
| Volatilidad alta | 46/0 · -0,059 · — · +105 | 87/223 · -0,028 · -0,092 · +289 | 61/198 · +0,033 · -0,139 · -2.759 |
| Volatilidad baja | 26/10 · -0,237 · -0,013 · +173 | 54/117 · -0,402 · -0,013 · +810 | 37/143 · -0,544 · -0,108 · +1.389 |
| Con movimiento brusco | 19/0 · +0,515 · — · -580 | 25/85 · +0,265 · +0,037 · +179 | 13/56 · +0,450 · -0,049 · -919 |
| Sin movimiento brusco | 53/10 · -0,352 · -0,013 · +858 | 116/255 · -0,265 · -0,098 · +920 | 85/285 · -0,282 · -0,142 · -450 |

### Entradas: por qué cambian entre A y B (libro completo)

| Perfil | Escenario | Entradas A | Entradas B | Comunes | Solo A | Solo B | Por qué B no tomó las de A | Entradas por mínimo de abiertas A / B |
|---|---|--:|--:|--:|--:|--:|---|--:|
| conservador | B 0.1 R (encargo) | 72 | 10 | 7 | 65 | 3 | en observación (memoria) 65 | 24 / 10 |
| conservador | B 0.5 R | 72 | 10 | 8 | 64 | 2 | en observación (memoria) 64 | 24 / 10 |
| conservador | B 1 R | 72 | 12 | 9 | 63 | 3 | en observación (memoria) 63 | 24 / 12 |
| moderado | B 0.1 R (encargo) | 141 | 340 | 105 | 36 | 235 | estrategia en pausa (memoria) 26, otro 4, freno de entradas 3, costo > tope 2, cupo lleno 1 | 15 / 16 |
| moderado | B 0.5 R | 141 | 317 | 106 | 35 | 211 | estrategia en pausa (memoria) 18, contexto en pausa (memoria) 6, otro 4, cupo lleno 3, freno de entradas 3, tope de riesgo por dirección 1 | 15 / 16 |
| moderado | B 1 R | 141 | 264 | 97 | 44 | 167 | estrategia en pausa (memoria) 18, cupo lleno 15, freno de entradas 5, otro 4, costo > tope 1, contexto en pausa (memoria) 1 | 15 / 16 |
| agresivo | B 0.075 R (encargo) | 98 | 341 | 56 | 42 | 285 | freno de entradas 18, estrategia en pausa (memoria) 16, tope de riesgo por dirección 8 | 6 / 8 |
| agresivo | B 0.5 R | 98 | 295 | 51 | 47 | 244 | tope de riesgo por dirección 22, freno de entradas 15, estrategia en pausa (memoria) 10 | 6 / 7 |
| agresivo | B 1 R | 98 | 225 | 48 | 50 | 177 | tope de riesgo por dirección 32, freno de entradas 16, estrategia en pausa (memoria) 2 | 6 / 6 |

## Criterios de T49 (validation_v1), tal cual

**Estricto** (ventanas de ajuste registradas de cada versión de estrategia + ventana de las salidas): 

| Escenario | Veredicto | Ops fuera de muestra | R medio | IC95 % | p bruto → Holm | V1 | V2 | V3 | V4 | V5 | V6 | Motivo |
|---|---|--:|--:|--:|--:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| conservador · A | **EN OBSERVACIÓN** | 0 | — | [—, —] | — → — | ✘ | … | … | … | … | … | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| conservador · B 0.1 R (encargo) | **EN OBSERVACIÓN** | 0 | — | [—, —] | — → — | ✘ | … | … | … | … | … | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| conservador · B 0.5 R | **EN OBSERVACIÓN** | 0 | — | [—, —] | — → — | ✘ | … | … | … | … | … | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| conservador · B 1 R | **EN OBSERVACIÓN** | 0 | — | [—, —] | — → — | ✘ | … | … | … | … | … | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| moderado · A | **EN OBSERVACIÓN** | 0 | — | [—, —] | — → — | ✘ | … | … | … | … | … | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| moderado · B 0.1 R (encargo) | **EN OBSERVACIÓN** | 0 | — | [—, —] | — → — | ✘ | … | … | … | … | … | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| moderado · B 0.5 R | **EN OBSERVACIÓN** | 0 | — | [—, —] | — → — | ✘ | … | … | … | … | … | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| moderado · B 1 R | **EN OBSERVACIÓN** | 0 | — | [—, —] | — → — | ✘ | … | … | … | … | … | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| agresivo · A | **EN OBSERVACIÓN** | 0 | — | [—, —] | — → — | ✘ | … | … | … | … | … | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| agresivo · B 0.075 R (encargo) | **EN OBSERVACIÓN** | 0 | — | [—, —] | — → — | ✘ | … | … | … | … | … | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| agresivo · B 0.5 R | **EN OBSERVACIÓN** | 0 | — | [—, —] | — → — | ✘ | … | … | … | … | … | V1: 0 operaciones fuera de muestra; regímenes: ninguno |
| agresivo · B 1 R | **EN OBSERVACIÓN** | 0 | — | [—, —] | — → — | ✘ | … | … | … | … | … | V1: 0 operaciones fuera de muestra; regímenes: ninguno |

Excluidas del estricto por escenario: conservador · A: 602 en ventana, 0 sin versión; conservador · B 0.1 R (encargo): 21 en ventana, 0 sin versión; conservador · B 0.5 R: 28 en ventana, 0 sin versión; conservador · B 1 R: 80 en ventana, 0 sin versión; moderado · A: 1014 en ventana, 0 sin versión; moderado · B 0.1 R (encargo): 825 en ventana, 0 sin versión; moderado · B 0.5 R: 1037 en ventana, 0 sin versión; moderado · B 1 R: 845 en ventana, 0 sin versión; agresivo · A: 1437 en ventana, 0 sin versión; agresivo · B 0.075 R (encargo): 736 en ventana, 0 sin versión; agresivo · B 0.5 R: 689 en ventana, 0 sin versión; agresivo · B 1 R: 648 en ventana, 0 sin versión.

**Informativo, NO es veredicto de T49** (mismos criterios sobre el tramo fuera de la ventana de las salidas; las entradas sí cayeron en ventanas de ajuste de sus estrategias). Holm sobre 295 intentos registrados + estos 12.

| Escenario | Veredicto | Ops fuera de muestra | R medio | IC95 % | p bruto → Holm | V1 | V2 | V3 | V4 | V5 | V6 | Motivo |
|---|---|--:|--:|--:|--:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| conservador · A | **RECHAZADA** | 530 | -0,121 | [-0,250, +0,005] | 0,8347 → 1,0000 | ✔ | ✘ | ✘ | ✘ | ✘ | ✔ | claramente negativa: R medio -0.121 + 1·EE 0.049 < 0 → ciclo de mejora |
| conservador · B 0.1 R (encargo) | **EN OBSERVACIÓN** | 11 | -0,151 | [-0,425, +0,077] | 0,6434 → 1,0000 | ✘ | ✘ | ✘ | ✔ | … | ✔ | V1: 11 operaciones fuera de muestra; regímenes: volatile 6, range 5 |
| conservador · B 0.5 R | **EN OBSERVACIÓN** | 18 | -0,001 | [-0,235, +0,445] | 0,3130 → 1,0000 | ✘ | ✘ | ✘ | ✔ | … | ✔ | V1: 18 operaciones fuera de muestra; regímenes: volatile 15, range 3 |
| conservador · B 1 R | **EN OBSERVACIÓN** | 68 | +0,012 | [-0,201, +0,239] | 0,1772 → 1,0000 | ✘ | ✘ | ✘ | ✔ | … | ✔ | V1: 68 operaciones fuera de muestra; regímenes: volatile 39, range 29 |
| moderado · A | **RECHAZADA** | 873 | -0,071 | [-0,169, +0,028] | 0,3479 → 1,0000 | ✔ | ✘ | ✘ | ✘ | ✘ | ✔ | claramente negativa: R medio -0.071 + 1·EE 0.038 < 0 → ciclo de mejora |
| moderado · B 0.1 R (encargo) | **RECHAZADA** | 485 | -0,083 | [-0,140, -0,029] | 0,4496 → 1,0000 | ✔ | ✘ | ✘ | ✘ | ✘ | ✔ | claramente negativa: R medio -0.083 + 1·EE 0.021 < 0 → ciclo de mejora |
| moderado · B 0.5 R | **RECHAZADA** | 720 | -0,047 | [-0,119, +0,023] | 0,2356 → 1,0000 | ✔ | ✘ | ✘ | ✘ | ✘ | ✔ | claramente negativa: R medio -0.047 + 1·EE 0.029 < 0 → ciclo de mejora |
| moderado · B 1 R | **RECHAZADA** | 581 | -0,107 | [-0,210, -0,002] | 0,3738 → 1,0000 | ✔ | ✘ | ✘ | ✘ | ✘ | ✔ | claramente negativa: R medio -0.107 + 1·EE 0.042 < 0 → ciclo de mejora |
| agresivo · A | **RECHAZADA** | 1339 | -0,092 | [-0,157, -0,025] | 0,4470 → 1,0000 | ✔ | ✘ | ✘ | ✘ | ✘ | ✔ | claramente negativa: R medio -0.092 + 1·EE 0.030 < 0 → ciclo de mejora |
| agresivo · B 0.075 R (encargo) | **RECHAZADA** | 395 | -0,117 | [-0,172, -0,065] | 0,7098 → 1,0000 | ✔ | ✘ | ✘ | ✘ | ✘ | ✔ | claramente negativa: R medio -0.117 + 1·EE 0.024 < 0 → ciclo de mejora |
| agresivo · B 0.5 R | **RECHAZADA** | 395 | -0,131 | [-0,223, -0,047] | 0,5714 → 1,0000 | ✔ | ✘ | ✘ | ✘ | ✘ | ✔ | claramente negativa: R medio -0.131 + 1·EE 0.040 < 0 → ciclo de mejora |
| agresivo · B 1 R | **RECHAZADA** | 426 | -0,038 | [-0,144, +0,066] | 0,0616 → 1,0000 | ✔ | ✘ | ✘ | ✘ | ✘ | ✔ | falla V2 (Expectativa neta), V3 (Contra el azar), V4 (Drawdown), V5 (Estabilidad) → ciclo de mejora |

## Causas probables y límites

1. **Decapita a las ganadoras.** Moderado fuera de muestra, B 0.1 R (encargo): las 213 entradas que A cerró en TP valían +1,63 R de media; con la escalera esas mismas dejaron +0,12 R (213 se llevaron menos, 9 acabaron en pérdida; 24.459 USDT cedidos). A cambio las perdedoras de A pasan de -1,05 a -0,34 R y 258 de 423 se salvan, pero no compensa: ganadora media +0,12 R frente a perdedora -0,94 R con escalera (A: +0,85 / -1,05). Con umbrales más altos (B 0.5 R, B 1 R) corta menos a las ganadoras, pero protege tarde y renuncia al BE+ y a la salida por tiempo de A: tampoco mejora.
2. **Toda salida de la escalera es un stop** (taker + deslizamiento con el rango de la vela); el TP de A sale como límite (maker, sin deslizamiento): costo medio 0,104 R en A frente a 0,110 R en B con las mismas entradas.
3. **Velas de 1 min**: el almacén vivo solo las tiene desde 2026-10-15; para esta corrida se sincronizó la historia completa en la copia (ver arriba). Dentro de cada minuto el orden sigue siendo desconocido (regla conservadora allí).
4. **Memoria propia de la escalera (T109)**: el Conservador («solo lo probado») hizo 11 operaciones en 3,6 años fuera de muestra frente a 530 con A; casi todas las ideas que A tomó B las rechazó «en observación» (BACKLOG T109 (4)): con escalera esa regla deja al perfil sin operar.
5. Fuera de muestra solo hay contextos de 1 h (y de 4 h desde 2026-03): los de 15 m solo existen dentro de muestra. El emparejado usa los tamaños de A; el libro completo, los de cada escenario.
6. **T49 estricto sin tramo fuera de muestra**: 12 de 12 escenarios quedan con 0 operaciones porque las versiones vigentes de las estrategias se dieron de alta automáticamente el 2026-10-22 con una ventana de ajuste que cubre toda la historia anterior. Su veredicto es «EN OBSERVACIÓN» y la tabla informativa no es un veredicto.
7. A7 de T106 sigue abierto: `exit_mode` no entra en la huella de versión de T49 y la puerta mide la sombra con TP; si alguna vez se adopta la escalera, tiene que medirse como una salida propia (BACKLOG).

## ◆ Decisión del usuario

Opciones: (1) adoptar en los tres perfiles · (2) adoptar solo en los que mejoren fuera de muestra · (3) archivar y dejar el 4.º perfil (`ppp_btcusdt`) como único con escalera.

**Respuesta (2026-10-23): adoptar en los tres perfiles (Conservador, Moderado y Agresivo siguen con la escalera de T109; el control ppp_btcusdt sigue igual).** Decisión tomada con el informe a la vista y contra la recomendación del A/B: fuera de muestra, con las mismas entradas y velas de 1 min reales, la escalera del encargo pierde más que la salida anterior (Conservador −2.993 frente a −2.919 USDT, Moderado −7.458 frente a −4.474, Agresivo −13.411 frente a −9.325) y ningún escenario es rentable; en el libro completo pierde menos solo porque opera menos. Nada de esto cambia la puerta de dinero real: sigue cerrada (T27/T49/T31).

