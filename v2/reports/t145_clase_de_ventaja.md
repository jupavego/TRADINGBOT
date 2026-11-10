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

*(Se rellena en el commit siguiente.)*
