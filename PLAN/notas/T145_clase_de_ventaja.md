# T145 — Nota: qué clase de ventaja se persigue

Informe: `v2/reports/t145_clase_de_ventaja.md`. Regla de lectura en el commit `613cd99`, anterior a la tabla.

## Qué se hizo
Reunir en una sola tabla lo que ya estaba medido para las cuatro clases (A microestructura, B arbitraje y funding, C market making pasivo, D solo análisis): costo, ventaja medida más pesimista, operaciones para V2/V3, tiempo hasta veredicto, qué se reutiliza, hipótesis nula e intentos de Holm. No se corrió nada nuevo ni se tocó código de operación.

## Resultado
- **A**: sin ventaja medida; el techo de oráculo es < 1 pb por ventana incluso maker-maker. Y no hay un año de historia propia hasta 2027-10 → no entra.
- **B**: la única con neto positivo medido (carry +102,5 pb por operación, IC95 % > 0, z = 4,02 > 3,85 de Holm). Pero V5 en vivo tardaría ~2,5 años, la tenencia se eligió a posteriori, los últimos 12 meses rinden +1,17 % anual y lo desplegado (24 h) no es lo medido → no entra.
- **C**: en VIP 0 la comisión de creador **se paga** (2 pb) y el diferencial es de 1 tick (0,0123 pb): cobrarlo da 325 veces menos que la comisión → no entra. **Corrige el enunciado de T145**, que decía que maker «invierte el signo» de la fricción.
- **D**: entra.

## Recomendación (◆)
**D, solo análisis.** T31 sigue hasta cerrar sus semanas. B queda como información, con un disparador escrito (funding ≥ 4 % anual en 12 meses móviles → nuevo pre-registro). A se congela en la captura. C se archiva. T146 pierde su condición y pasa al BACKLOG como mejora del análisis. Se publica el diagnóstico en «Operaciones sugeridas».
