# Traspaso a otra cuenta de Claude — 2026-11-05, T136 a medio terminar

**Dónde está todo:** worktree `.claude/worktrees/t136`, rama `worktree-t136`. `main` está en
`d5cb1c5` (PR #206 y #207 fusionados: gate completo verde, 2 778 pruebas, 0 fallos).

## Lo que ya está hecho y commiteado aquí
- Commit `2f2010d` — **decisión ◆ de T134 registrada**: no se adopta ninguna salida, los perfiles
  siguen con la escalera, **T135 queda aparcada**, el SL inicial pasa a T136/T49. Está en §4 y §0
  de `PLAN/ESTADO_PROYECTO.md` y en las filas de T134/T135 de `PLAN/STATUS.md`.

## Lo que está SIN COMMITEAR en este worktree (T136, hecho pero sin cerrar)
Código nuevo, todo con pruebas y `ruff` limpio, y **todos los interruptores apagados por defecto**
(ningún perfil cambia, T31 sigue igual):
- `v2/eim/paper/risk_budget.py` — riesgo = distancia al SL + costo; una sola definición de
  `cost_r`, que ahora usa también `vetoes.py`. Parámetro `ProfileParams.risk_includes_costs`.
- `v2/eim/paper/kelly.py` — Kelly fraccionado sobre el límite inferior del IC (E10). Da 0 %.
- `v2/eim/paper/caps.py` — freno **gradual** (`dd_steps`), límite de CVaR (`cvar_limit_r`),
  `Brake.scale`, `cvar95_r`. `policy.py` y `book.py` cableados.
- `v2/eim/paper/exits/es_check.py` — contraste Z2 de Acerbi y Székely.
- `v2/eim/paper/exits/risk_study.py` + `risk_report.py`, `v2/scripts/t136_riesgo.py`.
- `v2/eim/paper/slip_check.py` + `v2/scripts/t136_deslizamiento.py` (E4b).
- Pruebas: `v2/tests/paper/test_{risk_budget,kelly,caps_gradual,slip_check}.py` y
  `v2/tests/paper/exits/test_{es_check,risk_study}.py`. `tests/paper` entero pasó (rc 0).
- Informes ya calculados: `v2/reports/t136_riesgo.{md,json}` y `v2/reports/t136_deslizamiento.json`.
- `PLAN/notas/T136_riesgo.md` (nota completa), fila de T136 en `STATUS.md` (☑) y 5 entradas en
  `PLAN/BACKLOG.md`.

## LO QUE FALTA, en orden
1. **Rellenar dos marcadores** con el resultado del deslizamiento, que ya está medido:
   - `PLAN/notas/T136_riesgo.md` contiene el texto `RESULTADO_DESLIZAMIENTO` (§6).
   - `PLAN/STATUS.md`, fila T136, contiene `RESULTADO_DESLIZAMIENTO_STATUS`.
   Cifras (de `v2/reports/t136_deslizamiento.json`): captura 2026-10-28T23 → 2026-11-04T18
   (122 h); 346 cerradas en vivo, **todas por stop**, 129 en horas con captura, **114 medidas**,
   15 «el libro no llegó al nivel». Real: mediana **2,08 pb**, media 5,02, p90 14,35. Modelo:
   mediana **5,70 pb**, media 6,10. **Veredicto con la regla declarada (falla si se queda corto en
   más de la mitad): el modelo aguanta**, falla en el **28 %**. Pero la cola: peor caso **77,4 pb
   reales frente a 17,1 del modelo**. En el **17 %** la mejor punta no aguantaba la cantidad, así
   que esos son cota por abajo (haría falta `depth`). **No se cambia el modelo de costos.**
2. Entrada al final de `PLAN/BITACORA.md` (hecho, archivos, pruebas, abierto, siguiente paso).
3. `python PLAN/build_roadmap.py` (publica también la carpeta viva).
4. Gate: `python -m ruff check eim tests` (ya pasaba) y el `pytest` entero **por la cola**:
   `python -m eim.operation.jobs submit --name gate-t136 --retry-paused 1 -- python -m pytest -q`.
5. Commit + PR a `main` y fusionar.

## Hallazgos de T136 que no hay que perder (están en la nota)
1. El riesgo por operación **miente un 17,3 %**: al saltar el SL inicial se pierde ×1,1734 el
   riesgo declarado. Incluirlo multiplica la cantidad por 0,8522. **Es cota por abajo**: el banco
   de T131 no lleva 15 m, que es donde el costo pesa más.
2. El **tope de costo** debería ser 0,08 R y no 0,12–0,20 (E[R] −0,118 → −0,056, PF 0,44 → 0,63),
   pero deja fuera el 89 %: es el mismo hallazgo del SL inicial de T134 por otro camino.
3. **Freno gradual** por pliegue de 3 meses: Agresivo sin frenos −100 % (10/10 ruinas), con el
   freno de hoy −96,5 %, con el gradual −9,7 % sin ruinas. El gradual con tramo 0 es en la
   práctica un interruptor de apagado (el máximo solo sube).
4. **Kelly da 0 %** para los cuatro perfiles (E[R] −0,1538, error por día 0,0052, límite −0,1640).
5. **El ES se queda corto en 2 de 10 pliegues** (p 0,0002).
6. Volatilidad objetivo: **medida y NO adoptada**, empeora las tres cifras.
7. Tres defectos del propio pre-registro, en BACKLOG (arreglarlos exige versión nueva): sin 15 m,
   límites de CVaR de S3 inalcanzables (pide −0,30/−0,50 R con CVaR real −1,35 R), y los
   `vol_target` de S3 no están en las unidades de la σ versionada y saturan el tope.

## Dos cosas de operación que hay que saber
- **El gate por la cola en prioridad `batch` ya NO rompe la racha de T78**: el del 2026-11-04
  17:13–17:28 UTC cayó entero dentro de la hora 17 y la hora salió **completa** (`hft_ops
  --streak`: racha 2 h, match 1,0). Era la pregunta que quedaba abierta en §3 de
  `ESTADO_PROYECTO.md`; conviene anotarlo allí.
- **Yo rompí algo sin querer:** la primera versión de `t136_deslizamiento.py` traía la vela entera
  de `bbo` a Python (0,8–2 **millones** de mensajes por vela de 15 m) y el proceso llegó a
  **10,2 GB** en un equipo de 7,9 GB; hubo que matarlo (18:30–18:50 UTC aprox.). **La hora 18 UTC
  del 2026-11-04 de la captura no estaba auditada todavía: hay que mirar si se perdió.** Ya está
  arreglado (condición dentro del SQL con `LIMIT 1`: 5 s y 123 MB).
- Para correr un script de un worktree hace falta forzar su `eim` por delante del instalado; se
  usó un envoltorio que inserta la ruta en `sys.path` y hace `chdir`, porque `python scripts/x.py`
  resuelve `eim` al checkout principal.

## Siguiente tarea después de T136
La fase 22 queda cerrada (T130–T134 y T136; T135 aparcada). El frente siguiente es la **entrada**:
**T27** (puerta de edge) y **T49** (versiones de estrategia, donde encaja el SL inicial más amplio
de T134). Cinco mediciones independientes de la fase apuntan ahí.

## Las ◆ abiertas para el usuario (están en la nota de T136)
1. ¿Se enciende `risk_includes_costs`? (−14,8 % de tamaño; cambia una corrida en marcha).
2. ¿Se aprieta el tope de costo a 0,08 R?
3. ¿Se cambia el freno de hoy por el gradual?
No se pregunta encender el Kelly: hoy equivale a parar la operación en papel.
