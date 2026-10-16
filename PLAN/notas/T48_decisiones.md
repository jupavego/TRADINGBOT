# T48 — Decisiones para subir el acierto y la rentabilidad del bróker simulado (2026-10-16)

Muestra: BTCUSDT, evaluación sombra de 4.034 operaciones cerradas (15 m: 21 días, 1 h y 4 h: 60 días),
contextos reconstruidos sin anticipación. Mismos datos antes y después. **Ojo:** la configuración se
eligió mirando estos mismos 60 días (pocas decisiones, todas con razón económica previa); la
retroalimentación sí es walk-forward. Hay que confirmarlo con la corrida en vivo antes de creerlo.

## Qué causa las pérdidas (evidencia)
| Factor | Resultado |
|---|---|
| Costo estimado en R (0,16 % / riesgo) | < 0,10 R → −0,10 R/op · 0,10–0,20 R → −0,23 · > 0,30 R → −0,63 (n = 1.784) |
| Costo real medio por marco | 15 m 0,48 R · 1 h 0,23 R · 4 h 0,12 R |
| Tendencia del marco mayor (EMA) | a favor mejor que en contra en los 3 marcos (+0,03…+0,05 R/op) |
| Causa de cada pérdida | dirección equivocada 59–74 % · SL rápido 12–20 % · casi TP 9–12 % · tiempo 5–9 % |
| Break-even a +0,1 R tras +1 R | **empeora**: la salida no cubre costos (acierto 36 → 31 %) |
| Break-even que cubre costos (+0,1 R neto) | acierto 1 h 37 → 44 %, 4 h 38 → 48 %, R medio igual o mejor; 15 m peor |

## Decisiones (en código)
1. **Filtro de costo por perfil** (`max_cost_r`): Conservador 0,12 R, Moderado 0,15 R, Agresivo 0,20 R.
2. **Tendencia del marco mayor obligatoria** en los 3 perfiles (`require_htf`; 15 m→1 h, 1 h→4 h, 4 h→EMA 50/200 de 4 h).
3. **Break-even + que cubre costos** solo en 1 h y 4 h (`be_timeframes`).
4. **Retroalimentación más estricta**: pausa toda estrategia@marco (y contexto) con expectativa contraída negativa
   (`z_pause = 0`); el Conservador solo opera lo ya probado (`observe_w = 0`, ≥ 10 operaciones), el Moderado
   explora con 0,25 de peso y el Agresivo con 0,5.
5. Conservador con todas las familias direccionales: sigue siendo el más estricto, pero aprende de más datos.

## Resultado (mismos datos)
| | Antes | Después |
|---|---|---|
| Ponderado ganadas/perdidas | 536 / 940 (36,3 %) | 165 / 206 (44,5 %) |
| Esperanza por operación | −0,30 R | −0,09 R |
| Conservador / Moderado / Agresivo | −14 % / −61 % / −96 % | −5 % / −16 % / −39 % |
| 1 h Moderado · Agresivo | −0,19 · −0,24 R | **+0,10 · +0,13 R, 53 % de acierto** |

Aún no es rentable en conjunto: 4 h y 15 m siguen en negativo y el aprendizaje por contexto debe pausarlos
donde pierdan. Siguiente palanca con evidencia: entradas límite (maker) para bajar el costo, y variantes
de salida («casi TP») evaluadas en sombra antes de adoptarlas (BACKLOG T48).
