# T145 — Qué clase de ventaja se persigue, con la aritmética delante

**Modo: SIMULADO.** Este informe no construye nada ni habilita dinero real. Compara cuatro clases de ventaja —A microestructura propia, B arbitraje y funding, C market making pasivo, D solo análisis— con lo que ya está medido en el repositorio, y propone **una**.

## 1. Regla de lectura (fijada antes de rellenar la tabla)

Esta sección se escribió y se versionó **antes** de reunir las cifras de §2; su commit es anterior al de la tabla (`git log -- v2/reports/t145_clase_de_ventaja.md`).

1. **Una clase solo entra si su ventaja medida más pesimista supera su costo medido** —los dos en la misma unidad (pb del nocional o R por operación), con el modelo de costos de T25 y los costos reales del libro— **y** el tiempo hasta un veredicto de T49 (V2 y V3) cabe en **6 meses** al ritmo de datos real de esa clase.
2. **Ninguna clase entra si la única forma de superar su costo es suponer una ventaja que nadie ha medido.** «Sin medir» cuenta en contra, no a favor: «podría funcionar» no es un criterio.
3. **El número de operaciones necesario se calcula como en T139 §4**: con la ventaja neta medida y su dispersión, el n que da potencia 0,8 a α = 0,05 tras corregir por Holm con la familia **actual (841) más los intentos que la clase añade**.
4. **Hipótesis nula de cada clase, fijada aquí** (lo que se espera ver si no hay ventaja):
   - A: el retorno a 100 ms–60 s tras las señales de libro es, en media, cero menos el costo de cruzar (no supera el diferencial efectivo).
   - B: el diferencial capturable (funding o base entre plataformas) neto de comisiones de las dos patas es ≤ 0.
   - C: lo que se cobra de diferencial no cubre la selección adversa más el riesgo de inventario: P&L por operación pasiva ≤ 0.
   - D: no hay hipótesis que contrastar; no opera, no paga costo y no añade intentos.
5. **D es un resultado válido y no una derrota.** Si ninguna de A, B o C cumple 1 y 2, la recomendación es D.
6. **Se elige una clase, no varias.** Si dos cumplieran, se elige la de menor tiempo hasta veredicto; si empatan, la que menos intentos añade a Holm.
7. Nada de lo que sigue reabre T139 (P1 vinculante) ni cambia perfiles, catálogo o `validation_v1`.

## 2. La tabla

Todo sale de informes ya versionados; no se corrió nada nuevo. «Sin medir» cuenta en contra (regla 2). Umbral de Holm unilateral a α = 0,05 con la familia actual: z = 3,848 (841) · 3,851 (851). Operaciones necesarias = ((z_Holm + 0,84)·σ / ventaja neta)², potencia 0,8.

| | **A. Microestructura propia** | **B. Arbitraje y funding** | **C. Market making pasivo** | **D. Solo análisis** |
|---|---|---|---|---|
| **1. Costo a superar** (T25 + libro) | Ida y vuelta 10 pb taker · 7 mixto · 4 maker-maker (`CostParams`, VIP 0). Libro vivido: 14,1 pb del nocional | Comisiones de las dos patas ≈ 32 pb por operación de carry (949,9 USD / 30 op. de 10 000 USD) más deslizamiento y pata incompleta; ya restados en el neto | 4 pb por ida y vuelta maker-maker (2 + 2 pb): **en VIP 0 la comisión de creador se paga, no se cobra** | 0 |
| **2. Ventaja medida más pesimista** | **Sin medir.** La única cifra es un techo de oráculo que sabe la dirección (`hft_cost_bound`): a 60 s, 0,11 pb por ventana taker y 0,73 pb maker-maker; a ≤ 10 s, ≤ 0,06 pb. Ninguna señal real se ha probado (T80 sin empezar) | **Medida, positiva:** carry a 2 160 h +102,5 pb netos por operación, IC95 % [+57,7; +157,6], n = 30 (2023–2026); base trimestral +131,0 pb [+59,0; +208,6], n = 20 (`arbitrage_edge`). Pero los últimos 12 meses rinden +1,17 % y +2,44 % anual sobre el capital comprometido, y 2026 +0,92 % y +0,47 % | **Medida, negativa por aritmética:** el diferencial de BTCUSDT es 1 tick = **0,0123 pb** (p50 = p99, `hft_cost_bound`). Cobrarlo en cada ida y vuelta da 0,012 pb contra 4 pb de comisión: **325 veces menos**. Antes de la selección adversa | No aplica |
| **Operaciones para V2 y V3** | Incalculable sin una ventaja medida | Carry: σ ≈ 140 pb → **41 op.**; ya hay 30 con z = 4,02 > 3,85 en la historia. Base: σ ≈ 171 pb → **38 op.**; con 20, z = 3,43 < 3,85 | Ninguna cantidad las pasa: la media esperada es negativa | 0 |
| **3. Tiempo hasta veredicto** | T139 exige **≥ 1 año de historia propia** para reabrir una línea con datos nuevos; la captura L2 empezó el 2026-10-24 → **no antes de 2027-10**. Más T80 antes de nada | La historia ya pasa V2, pero V5 de T49 exige ≥ 20 operaciones **en vivo**: con tenencias de 90 días en 2 activos salen ~8 al año → **~2,5 años** | Rápido en simulación, irrelevante: falla el criterio 1 antes | Inmediato |
| **4. Reutiliza / habría que construir** | Reutiliza T78 (captura) y T83 (riesgo). Construir **T79, T80, T81, T82, T84, T85, T86** (7 tareas) | Reutiliza T38, T39, T43 y T45 (construido y probado contra el exchange simulado). Construir: la corrida E2E de T45 en testnet (claves del usuario) y un seguimiento en vivo del carry a 2 160 h, porque **el motor vivo usa 24 h, que no tomó ninguna operación en todo el periodo** | Reutiliza T78 y T83. Construir T79 (cola y llenados: imprescindible para MM), T80, T82 (Avellaneda–Stoikov), T84, T85. **Y una comisión de creador negativa, que no se construye: depende del volumen** | Nada |
| **5. Hipótesis nula** (§1.4) | Retorno a 30–60 s tras la señal ≤ costo de cruzar | Diferencial neto de las dos patas ≤ 0 | P&L pasivo por ida y vuelta ≤ 0 | — |
| **6. Intentos que añade a Holm** | Sin cifrar, **≥ 4**: un horizonte por tenencia viable (30 s, 60 s) × al menos maker/mixto, más cada familia de rasgos de T80 | **10** ya consumidos y no contados: 5 tenencias × 2 estrategias, y la de 2 160 h se eligió mirando el resultado | ≥ 1 por juego de parámetros de A–S | **0** |

## 3. Lectura con la regla de §1

- **A no entra.** Falla la regla 2: no hay ninguna ventaja medida, solo un techo de oráculo que ya está por debajo de 1 pb por ventana incluso con comisiones de creador. Y falla el plazo: con menos de un mes de historia propia, el año que exige T139 para reabrir con datos nuevos acaba en octubre de 2027.
- **B no entra, y es el caso más cercano.** Es la **única clase con ventaja neta positiva medida**, y el carry pasa Holm con la familia actual (z = 4,02 frente a 3,85). Pero falla el plazo: V5 pide 20 operaciones en vivo y salen unas 8 al año. Además hay tres reservas, todas ya escritas en `arbitrage_edge.md`: la tenencia de 2 160 h se eligió después de ver las cinco, el rendimiento se hundió a +1,17 % anual en los últimos 12 meses (régimen de funding bajo, por debajo de cualquier tipo sin riesgo) y lo desplegado (24 h) no es lo medido. Operarla exigiría capital real en spot y perpetuo, que T31 no habilita.
- **C no entra, y es el resultado más claro.** El enunciado de T145 decía que maker «invierte el signo» de la fricción. **En VIP 0 no es así:** maker paga 2 pb en vez de 5, pero paga. Con un diferencial de 1 tick (0,0123 pb), cobrarlo nunca cubre 4 pb de comisión. C solo existe con reembolso de creador (programas de market making), y eso exige un volumen que no está al alcance.
- **D entra.** No opera, no paga costo, no añade intentos y aprovecha lo que el sistema ya hace mejor.

## 4. Recomendación y decisión

**Decisión del usuario (2026-11-10): D, solo análisis**, tal como se recomendaba.

**D: solo análisis.** Es lo que dicen las cifras con la regla escrita antes de mirarlas, no una derrota: T27 midió que comprar y mantener dio +188 % mientras la estrategia daba −70 %, y el sistema vale por medir con honestidad y decirlo.

Qué significa en la práctica:

1. **T31 sigue hasta cerrar sus semanas** como registro en vivo, sin cambiar de objeto (◆2 de T145).
2. **B se queda como información, no como operación.** El agente `arbitrage` ya informa con `bias = 0`. Si el funding volviera a niveles de 2023–2024 (≥ 4 % anual en 12 meses móviles), B sería la primera clase que revisar, con su propio pre-registro y sin reutilizar la tenencia elegida a posteriori.
3. **A queda congelada en la captura.** T78 sigue acumulando historia propia, que es barato y es el único dato que nadie más tiene. T79–T86 no se empiezan; si en 2027-10 hay un año de libro, puede abrirse con su propio pre-registro.
4. **C se archiva.** Las cuentas no dependen de ninguna estimación: el diferencial es de 1 tick y la comisión de creador se paga.
5. **T146 queda sin condición.** Solo tenía sentido si quedaba viva una línea direccional que opere. Que la síntesis no sume cinco veces el mismo voto sigue importando para lo que el panel *muestra*, así que se deja en el BACKLOG como mejora del análisis, no como tarea de fase.
6. **Publicar el diagnóstico en «Operaciones sugeridas»** (◆3): recomendado. Que el panel diga por qué no hay operaciones validadas, no solo que no las hay.

## 5. Lo que este informe no hace

No construye ninguna clase, no reabre T139 ni cambia `validation_v1`, perfiles o catálogo. No mide nada nuevo: donde no había cifra, pone «sin medir». La aritmética de C supone VIP 0 sin BNB, que es la configuración verificada del proyecto (T38, 2026-10-15).
