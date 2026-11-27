# T214 ◆ — ¿La superficie de volatilidad entra como insumo o queda como contexto?

Fecha: 2026-11-27 · Insumo: `v2/reports/t214_superficie.md` (potencia a priori) y el pre-registro
`PLAN/notas/T214_preregistro.md`.

## Respuesta del usuario (2026-11-27): opción 1

> «Decisión 1.» (la recomendada: queda como contexto)

Queda fijado:

1. **El agente `vol_surface` queda como contexto en la interfaz**: informante en sombra, sesgo 0,
   no direccional en la síntesis. No entra en el cono, las bandas ni el tamaño de los stops.
2. **Solo podría pasar a insumo de volatilidad si la evaluación pre-registrada lo aprueba**, y
   entonces sería otra entrega con su propia ◆, como A2 de T165.
3. **El pre-registro sigue vigente tal cual**: revisión de potencia cuando haya 250 días válidos
   de tomas (no antes del 2027-08-05), con Holm en la familia ampliada de T95. Si esa revisión no
   llega a la potencia antes del tope (2029-11-27), la pregunta se cierra SIN POTENCIA y los 3
   intentos no se suman a la familia. El código de la revisión queda en BACKLOG T214 (1).
4. El colector de T213 sigue encendido en la portátil (sin él no hay muestra).

T214 queda cerrada (☑).
