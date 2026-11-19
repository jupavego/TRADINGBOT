# T196 — Enmienda de los pre-registros por el libro central entre equipos

Declarada el 2026-11-19 ≈ 01:30 UTC, **antes de cualquier mirada** a los datos que enmienda: la
primera mirada de T187 es el 2026-12-17 y la primera lectura de T190 el 2026-11-28. Nadie ha visto
todavía una sola operación de las ventanas que esto toca. Su huella SHA-256 queda en `PLAN/STATUS.md`
(fila T196) y en la bitácora del mismo día.

## Qué cambia en el mundo
Desde el **2026-11-28 00:00 UTC** (cierre de T31), la portátil (`laptop-i6pf9ovp-fce8d9`) y
`juanpablo-cpu` intercambian su libro fijo cada hora (T61 + T196). Las dos corren el mismo cerebro
sobre BTCUSDT en 15 m, 1 h y 4 h, así que casi todas las operaciones son las mismas; las nuevas de
verdad son las de velas que un equipo vio y el otro no.

## Regla de unión (fija; no depende de los resultados)
1. **Una vela = una operación.** Identidad = `ledger_id` (alcance|perfil|símbolo|idea, con la idea =
   símbolo:marco:vela:estrategia). Si dos equipos la vivieron, cuenta una vez: la del equipo que la
   registró primero en el libro de quien mide (la local); la otra queda en `share_conflicts` si su
   resultado difiere.
2. **Se juzga en el equipo que la vivió.** `retro` viaja tal como lo calculó ese equipo. La regla de
   T144 no cambia: vivida, con peso, sin `retro`, cerrada con resultado.
3. **El tamaño es el de quien la vivió.** La unidad de T187 (R unitario del perfil, `r × peso`) usa el
   peso de esa fila; el PnL en USDT también.

## T187 · `t187_asimetria_v1` (pre-registro congelado el 2026-11-19, huella `0d4977fa…`)
- **Universo principal:** operaciones abiertas desde el 2026-11-19 00:00 UTC en **cualquiera de los
  dos equipos**, bajo la regla de unión de arriba. Incluye las de juanpablo-cpu entre el 19 y el 28 de
  noviembre que lleguen con la primera importación.
- **Sensibilidad declarada (no decide):** el mismo cálculo solo con la portátil
  (`GET /v2/paper/accounting?machines=local`). Se informa al lado en las tres miradas.
- Las tres miradas (2026-12-17, 2027-01-14, 2027-02-11), el IC 98,33 % por bloques de día, los umbrales
  y las reglas de adopción de las fases 2 y 3 **no cambian**. Los bloques de día se forman con el cierre
  de cada operación, venga del equipo que venga.
- Si la importación falla o queda desactivada en una mirada, esa mirada se hace con lo que haya y lo
  dice; no se aplaza.

## T190 · `direccion_v1` (pre-registro congelado el 2026-11-18)
- La boleta lee `reports.duckdb`, que ya viajaba en T61. `ReportStore.history` toma **un reporte por
  agente e instante** (la versión más reciente), así que la unión no duplica votos.
- **Universo principal:** los reportes de los dos equipos. Ninguna otra parte del pre-registro cambia
  (horizontes, Wilson, Holm, puertas de las sombras).

## T31
Se cierra con **la portátil sola**, tal como esté su libro a 2026-11-28 00:00 UTC
(`GET /v2/paper/accounting?machines=local&to_t=1795824000000`, con su `counted_digest`). Lo que llegue
después de otro equipo no reescribe ese cierre.

## Lo que esta enmienda NO hace
No cambia ninguna hipótesis, umbral, fecha de mirada ni regla de adopción; no reabre T139 P1; no
habilita dinero real.
