# Runbook de incidentes

Principio: **ante la duda, kill-switch primero y diagnóstico después.** El kill-switch es global,
se persiste en `data/kill_switch.json`, sobrevive a reinicios y **solo se desactiva a mano**.
Comandos desde `v2/`. `API=http://127.0.0.1:8000`. Todo POST lleva `X-EIM-Confirm`.

## 0. Tabla rápida
| Síntoma | Alerta / señal | Ir a |
|---|---|---|
| Hay que parar todo ya | — | §1 |
| Posición o SL que no cuadra con el exchange | `divergencia`, reconciliación `ok=false` | §2 |
| Sin datos de Binance / feed detenido | `desconexion`, ciclos fallidos, `servicio` | §3 |
| Kill-switch activado solo | `kill_switch` (crítica) | §4 |
| Base dañada o borrada | API no arranca, error DuckDB | §5 |
| El proceso muere o se cuelga | `proceso_reiniciado` en el registro | §6 |
| Agentes degradados / plan vetado | `agentes_degradados`, vetos en «Plan» | §7 |
| Copia diaria fallida | `copia_seguridad` | §8 |
| Tablero de líderes viejo / `smart_money` sin datos | «Tablero viejo» en «Líderes», aviso «Líderes: servicio reiniciado» | §10 |
| Copia simulada en pausa o con kill-switch | aviso «Copia … en pausa» / «kill-switch» | §11 |
| Arbitraje «DESCUBIERTA» o kill-switch por pata incompleta | pestaña «Arbitraje» → «Ejecución automática» | §12 |
| Bot del escuadrón en cuarentena, colgado o con versión nueva | «Escuadrón», alerta `bots.<bot>` | §13 |
| Protección del bróker simulado recuperada o en «estado inconsistente» | `proteccion` («Protección recuperada…», «…en estado inconsistente», «Diario de protección sin verificar») | §14 |
| Carril HFT bloqueado, «cancelar todo», kill-switch HFT o 418 | `execution.hft` en el Observatorio (`bloqueo`, `cancelar_todo`, `cierre`, `kill`) | §15 |

Dónde mirar: pestaña «Operación» de la UI · `GET $API/v2/operation` · registro
`data/operation/logs/op-AAAA-MM-DD.jsonl` · tabla `op_alerts`.

## 1. Kill-switch (parada de emergencia)
```bash
curl -X POST -H "X-EIM-Confirm: kill-switch" "$API/v2/risk/kill-switch/activate?reason=manual"
curl "$API/v2/risk/kill-switch"
```
O botón «Kill-switch» en la pestaña Plan. Efecto: el motor de riesgo veta toda entrada nueva y la
reconciliación ordena el **cierre ordenado** de las posiciones abiertas (`close_requested`).
Comprueba: `GET $API/v2/execution` → sin posiciones y `kill_switch.active=true`.
Si la API no responde: detén el proceso (`Ctrl+C` en la terminal de `eim.operation run`; el
vigilante también se detiene) y, en testnet, cierra a mano en la web de la testnet.

**Reactivar** (solo tras entender la causa y con reconciliación limpia):
```bash
curl -X POST -H "X-EIM-Confirm: execution" "$API/v2/execution/reconcile"     # debe dar ok=true
curl -X POST -H "X-EIM-Confirm: kill-switch" "$API/v2/risk/kill-switch/deactivate?reason=<causa resuelta>"
```

## 2. Reconciliación (libro interno ≠ exchange)
La reconciliación corre en cada ciclo (servicio) o cada `EIM_RECON_S` s. Ya resuelve sola:
SL perdido → lo repone o cierra; órdenes huérfanas `eim-` → las cancela; posición desconocida sin SL
→ la cierra. Desvío ≥ 1 % (`kill_max_recon_drift`) → kill-switch.
1. Forzar una pasada y leer el informe: `curl -X POST -H "X-EIM-Confirm: execution" "$API/v2/execution/reconcile"`
   (`issues`, `actions`, `kill`).
2. Si persiste el desvío: kill-switch (§1) y cerrar el símbolo:
   `curl -X POST -H "X-EIM-Confirm: execution" "$API/v2/execution/flatten?symbol=BTCUSDT&reason=reconciliacion"`.
3. Contrastar con el exchange (testnet: web de la testnet; papel: `data/operation/state_simulado.json`).
4. Causas conocidas: entrada LIMIT parcialmente llena tras cerrar el SL; reinicio con libro de
   ejecución en memoria (testnet) → BACKLOG T30 (1)(2).
5. Reactivar solo con `ok=true`.

## 3. Caída de fuente de datos
- **REST de Binance caído / sin red:** el ciclo falla → reintento con espera exponencial; tras 3
  fallos seguidos, alerta `servicio`. Sin respuesta del exchange ≥ 5 min (`kill_max_disconnect_ms`)
  → kill-switch automático. Datos obsoletos → el motor de riesgo veta (no se opera a ciegas).
- **Qué hacer:** comprobar conectividad (`curl https://fapi.binance.com/fapi/v1/ping`), estado de
  Binance, proxy/VPN. No reactivar nada hasta que `GET $API/v2/health` y un ciclo completo vayan bien.
- **WebSocket del gráfico sin ticks** (`fstream` conecta pero no envía en algunas redes): usar
  `EIM_WS_URL=wss://stream.binance.com:9443/ws`. No afecta al servicio (usa REST).
- **Tras una caída larga:** solo se reproducen ≤ 7 días de precio y se analiza la última vela
  (BACKLOG T31 (5)); revisar el informe parcial: `python -m eim.operation report`.

## 4. Kill-switch activado automáticamente
Causas (ver `reason` en `GET $API/v2/risk/kill-switch` y eventos): drawdown ≥ 15 %, desconexión
≥ 5 min, desvío de reconciliación ≥ 1 %, o manual. Seguir §2/§3 según la causa. Un drawdown del
15 % en papel es motivo para **revisar la estrategia**, no para reactivar: anótalo en el informe.

## 5. Restaurar desde copia de seguridad
> Para traer el historial de **otro equipo** (no restaurar el propio): `python -m eim.data.share import` (OPERACION.md §3.1).

Una copia (T115) lleva las tres bases con historial —`reports.duckdb`, `paper.duckdb` (bróker
simulado y registro de sugerencias) y `leaders.duckdb` (capturas de líderes y copia simulada)—,
el observatorio (`obs/obs.duckdb`, derivado), el kill-switch y el estado del servicio.

```bash
# 1) detener TODO lo que abre las bases: el vigilante y la API (Ctrl+C en eim.operation run)
#    y el servicio de líderes (eim.leaders supervise + run; comando en OPERACION.md §6)
python -m eim.data.backup list
python -m eim.data.backup verify backups/eim_AAAAMMDD-HHMMSS
python -m eim.data.backup restore backups/eim_AAAAMMDD-HHMMSS --data-dir data
# 2) relanzar y comprobar
powershell -ExecutionPolicy Bypass -File scripts\servicio_continuo.ps1 -ConWeb
```
- `verify` lista cada base con sus tablas y filas, y las **ausentes** con su motivo. Salida 0 =
  íntegra y completa; 2 = íntegra pero incompleta (una base estaba en uso y su dueño no la
  entregó: se puede restaurar el resto); 1 = dañada (archivo que falta, hash o filas distintas):
  no se restaura, prueba con la copia anterior.
- `restore` comprueba la copia y que **ninguna** base de destino esté abierta **antes de tocar
  nada**: con la API o el servicio de líderes en marcha falla con «detén la API y el servicio de
  líderes antes de restaurar (en uso: …); no se ha tocado nada».
- Cada base se **reemplaza entera** (nunca se mezcla): la actual queda al lado como
  `<base>.antes-de-restaurar-<AAAAMMDD-HHMMSS>` (con su `.wal`, si lo había), y la carpeta
  `operation/` como `operation.antes-de-restaurar-<…>` (cada restauración con su sello: repetirla no
  pierde el original). Una base **ausente** en la copia no se toca (sigue la local). Para volver
  atrás, borra la restaurada y quita el sufijo a la apartada.
- Restaura también kill-switch y estado del servicio. La configuración versionada no se restaura
  (vive en git; la copia la conserva para auditoría). Velas: si no se copiaron, se vuelven a
  descargar solas (`EIM_AUTO_HISTORY=1`).
- Tras restaurar `leaders.duckdb`, los días adelante y la copia simulada siguen donde quedó la copia;
  lo capturado entre la copia y la restauración se pierde (el exchange solo devuelve las 10 000
  ejecuciones más recientes por líder).
- En testnet, tras restaurar: reconciliar (§2) antes de reactivar.

## 6. Proceso caído o colgado
`eim.operation run` es un vigilante: relanza la API si muere o si el latido
(`data/operation/heartbeat.json`) no avanza en 15 min, con espera creciente (máx. 5 min). El libro
simulado y los cursores se restauran del estado. Si entra en bucle de reinicios: leer
`proceso_reiniciado` en el registro, arrancar la API a mano en primer plano para ver el error:
`python -m uvicorn eim.api.main:app --port 8000`.
Puerto ocupado: `netstat -ano | findstr :8000` y cerrar el proceso viejo.

## 7. Agentes degradados o planes vetados
Normal que el riesgo vete: cada veto queda en `GET $API/v2/risk/decisions` con su motivo. Si un
agente crítico está `degraded`/`no_data`, revisar cobertura del snapshot (`GET $API/v2/agents`) y
la fuente de datos (§3). No se fuerza la ejecución: el riesgo tiene la última palabra.

## 8. Copia diaria fallida o incompleta
Alerta `copia_seguridad` con el error (disco lleno, ruta inexistente, permisos). Corregir y esperar
el reintento automático (cada hora) o forzar `python -m eim.data.backup create`. La operación no
se detiene por esto.
**«Copia de seguridad incompleta»:** la copia se hizo, pero una base quedó *ausente* con el motivo
del aviso; casi siempre `leaders.duckdb` con el servicio de líderes colgado (no entregó la
instantánea) → §10, y luego `python -m eim.data.backup create` (salida 0 = completa). La retención
nunca borra la última copia completa por culpa de las incompletas.

## 9. Sospecha de clave comprometida (testnet)
Revocar la clave en la testnet, crear otra (solo futuros, sin retiro, con restricción de IP),
actualizar las variables de entorno y reiniciar. Las claves nunca están en el repo ni en las copias.

## 10. Servicio de líderes (copy trading) detenido o en bucle
Solo lectura de datos públicos de Hyperliquid: no hay órdenes ni dinero en juego, pero cada
minuto sin captura retrasa la aprobación de líderes (los días adelante solo cuentan con captura).
1. ¿Corre? `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? CommandLine -match 'eim\.leaders'`
   → debe haber un `supervise` y un `run`. Latido: `data/leaders/heartbeat.json` (`last_heartbeat`
   de hace < 1 min salvo en el arranque; `state` `arrancando` → `capturando`). Tablero más reciente:
   `data/leaders/board_*.json` (cada 5 min).
2. **Nada corriendo:** `powershell -ExecutionPolicy Bypass -File v2\scripts\servicio_continuo.ps1 -ConWeb`.
   Si responde «Servicio de líderes NO lanzado: …»: sin líderes en seguimiento (`watch 0x…`) o
   `data/leaders.duckdb` en uso por otro proceso (un `list`/`score` o un `run` a mano: ciérralo).
3. **Solo hay `run` (sin `supervise`):** captura huérfana o lanzada a mano; funciona pero nadie la
   relanza. Detén ambos (comando en `docs/OPERACION.md` §6) y vuelve a lanzar el script.
4. **Bucle de reinicios** (`proceso_reiniciado` repetido en `data/leaders/logs/op-AAAA-MM-DD.jsonl`):
   el motivo está en `reason` (código de salida o «latido detenido»). Detén el servicio y lánzalo
   en primer plano para ver el error: `python -m eim.leaders run --minutes 5`. Salida de consola del
   servicio: `data/operation/logs/lideres.err.log`. Causas típicas: sin red o Hyperliquid caído
   (la captura reintenta sola sin morir), disco lleno, base dañada.
5. **Base dañada:** restaurar `leaders.duckdb` de la última copia que la tenga (§5; la copia
   diaria la pide al servicio). Solo si ninguna copia la tiene: renombrar `data/leaders.duckdb` y
   volver a registrar los líderes (`add 0x… --watch`), que reinicia la cuenta de días adelante.
6. **Tras el arreglo:** el tablero se renueva en ≤ 5 min y `smart_money` vuelve a tener datos. Si
   el apagado fue largo, ver en `docs/OPERACION.md` §6 qué huecos quedan (tope de 10 000
   ejecuciones y de 24 h por líder al volver).

## 11. Copia simulada en pausa o con kill-switch (T42)
Simulación con saldo virtual: no hay dinero en juego. La pausa existe para que una diferencia
entre la copia y el líder **nunca se «arregle» operando a ciegas**.
1. Ver qué pasó: `python -m eim.leaders copy-status` y la pestaña «Líderes» → «Copia simulada»
   (motivo de la pausa, última reconciliación y bitácora). Aviso de Windows «Copia … en pausa» y
   registro en `data/leaders/logs/op-AAAA-MM-DD.jsonl` (`kind: copia`).
2. **Pausa por divergencia no explicada**: el líder tiene una posición que la copia no vio como
   señal (hueco del WS o resincronización de T40) o la subcuenta difiere del objetivo sin motivo.
   Comparar con `data/leaders/logs` y `leader_gaps`; si la causa es un hueco del flujo, reanudar.
3. **Kill-switch de la subcuenta** (caída ≥ 25 %): ya cerró todo; es propio de la subcuenta y no
   toca el kill-switch global de la operación en papel (T31).
4. Tras un reinicio del servicio (o una caída) la subcuenta se restaura de la base y relee las
   ejecuciones posteriores a su último guardado; un hueco de captura > 5 min (equipo apagado)
   se resincroniza solo con la foto real, con motivo en la bitácora (no pausa).
5. Reanudar (solo a mano): `python -m eim.leaders copy-resume 0x…` (o `--all`). El servicio lo
   aplica en ≤ 1 min; con la siguiente foto adopta la posición real del líder: cierra lo que el
   líder ya no tiene y **no** abre lo que abrió sin que lo viéramos (lo marca «apertura no vista»).

## 12. Arbitraje en testnet: pata descubierta o kill-switch (T45)
Solo testnet. Una posición de arbitraje tiene dos patas (spot largo + futuro corto) que deben
sumar cero; el ejecutor nunca deja una pata huérfana a propósito.
1. Ver el estado: `GET $API/v2/arbitrage/execution` (posiciones, último ciclo, reconciliación,
   bitácora) o `data/arb_exec/journal_AAAA-MM-DD.jsonl`; el libro está en `data/arb_exec/state.json`.
2. **DESCUBIERTA**: una orden quedó sin respuesta (red) o la segunda pata no llenó en un cierre
   urgente. La reconciliación de cada ciclo consulta las órdenes por su id (`eia-…`), aplica lo
   llenado y recorta la pata que sobra. Si persiste: comprobar conexión y claves; forzar con
   `curl -X POST -H "X-EIM-Confirm: arb-cycle" "$API/v2/arbitrage/execution/cycle"`.
3. **Kill-switch por pata incompleta** (`regla:pata`): al deshacer una pata la pérdida superó el
   tope de la decisión (50 pb del nocional, `risk_arb_v1`). Con el kill-switch activo cada ciclo
   cierra todos los arbitrajes (ambas patas). Revisar el libro de la testnet y la bitácora antes
   de desactivarlo a mano (§1). El kill-switch es el mismo del carril direccional.
4. Cerrar a mano: `POST $API/v2/arbitrage/execution/close?key=eia-…` (`X-EIM-Confirm: arb-close`)
   o todo con `/flatten` (`X-EIM-Confirm: arb-flatten`).
5. Con `EIM_ARB_EXECUTION` apagado y posiciones vivas en `state.json`, la reconciliación T30 sigue
   respetando sus futuros (no los cierra como «posición desconocida»), pero nadie las gestiona:
   volver a encenderlo o cerrarlas.

## 13. Un bot del escuadrón se cuelga, falla o cambia de versión (T60)
Síntoma: en «Escuadrón» el bot sale `cuarentena`, con señal `degraded` o con el aviso «versión cambió»; alerta `bots.<bot>` o latido `bots.service` en `degraded` en la pestaña «Operación».
Solo entra en cuarentena un bot que **vota** (hoy ninguno: ver `GET $API/v2/bots/scorecard`); uno que solo informa y falla deja la señal `degraded` y la alerta, nada más.
1. Mirar el motivo: `GET $API/v2/bots` (`reasons`, `evidence`, `quarantine`) y, desde `v2/`, `python -m eim.bots.quarantine list` (o `data/bots/quarantine.jsonl`). Un bot que se cuelga (modo B) lo mata el tiempo límite del ejecutor y solo deja una señal `degraded`: el resto del ciclo sigue.
2. Un bot en cuarentena no vota (la síntesis queda como si estuviera en `informa`). No hay que hacer nada urgente: el riesgo y la ejecución no dependen de él.
3. Versión cambiada (SHA de la ficha o parámetros): su puntuación anterior ya no vale. Volver a puntuar (`python -m eim.bots.scorecard_cli`, `docs/BOTS.md` §Cambiar de versión); mientras tanto vota solo si la nueva medición lo permite.
4. Reactivar a mano, solo tras entender la causa (desde `v2/`, **con la API en marcha**; no hay botón):
   ```bash
   python -m eim.bots.quarantine release <bot_id>@<estrategia> --by <tu nombre>
   ```
   La API relee `data/bots/quarantine.json` en el siguiente cierre de vela del escuadrón o en la siguiente consulta a `GET $API/v2/bots`, y la política recupera el voto sin reiniciar (antes de T119 había que reiniciar la API y un disparo posterior deshacía la reactivación). Comprueba: `GET $API/v2/bots` → `quarantine` sin el bot; la bitácora `quarantine.jsonl` guarda el `release` con quién lo hizo.
   Camino comprobado en T119 con el adaptador real de Hummingbot (`bollinger_v1`) y una caída del ejecutor simulada: voto perdido al instante, `list`, `release` desde otro proceso y voto recuperado en el ciclo siguiente (`tests/bots/test_t119_quarantine.py`).

## 14. Protección del bróker simulado recuperada o inconsistente (T110)
El diario `paper_protection` (en `data/paper.duckdb`, solo adición) guarda el escalón y el SL vigente
de cada operación abierta con escalera; al recalcular la vista el SL nunca queda por debajo de lo
guardado. Todo es SIMULADO.
- **«Protección recuperada del diario» (aviso):** el recálculo daba un SL menor (velas de 1 min que
  faltan, parámetros cambiados…) y se adoptó el guardado. No hay que hacer nada; si se repite tras
  cada arranque, revisar qué cambió en los datos o en `params.py`.
- **«Protección por delante de lo guardado» (info, al arrancar):** el precio siguió mientras la API
  estaba parada; se adoptó el recálculo (el mayor) y se registraron los cambios que faltaban.
- **«Protección en estado inconsistente» (crítica):** la instantánea falta o está corrupta, no cuadra
  con la operación recalculada, el recálculo la cerraría antes de lo que se vio en vivo o ya no la
  encuentra. Esa operación **no se cierra sola ni mueve su stop por lo guardado** hasta resolverla:
  ```bash
  python -m eim.paper proteccion lista --estado inconsistente      # motivo en «note»
  python -m eim.paper proteccion historial "<op_id>"                # todas sus filas
  python -m eim.paper proteccion reconciliar "<op_id>" --decision recalculo --nota "por qué"
  ```
  `recalculo` deja mandar al recálculo (la próxima pasada reanuda el diario desde él; única vía que
  puede dejar atrás un SL guardado, y queda anotada); `descartar` deja de seguirla (p. ej. la idea ya
  no existe). Con la API en marcha la CLI va por ella (`POST /v2/paper/protection/resolve`); si no,
  escribe la base directamente.
- **«Diario de protección sin verificar» (crítica):** no se pudo leer el diario; la vista se calcula
  sin suelo y marcada `protection.verified = false` en `GET $API/v2/paper`. Ver §5 si la base está dañada.

## 15. Carril HFT: bloqueo, cancelar todo, divergencia o 418 (T83)
Solo SIMULADO o TESTNET (`hft_risk_v1`); el servicio en vivo llega en T85. Cada orden del carril
lleva su `HftDecision` sellada (vigente 1 s) de `risk.hft_engine`; cancelar no la necesita. Los
hechos quedan en `HftLane.events` y en el Observatorio (componente `execution.hft`).
1. **Bloqueo + «cancelar todo» (se resuelve solo):** la vigilancia (`HftLane.tick`, con su propio
   temporizador) cancela del lado cliente todas las órdenes `eih-` vivas y veta toda orden que no
   reduzca mientras dure la causa. El detalle dice cuál:
   - `datos`: el libro tiene más de 1 s (WebSocket de mercado cortado o Binance retiene mensajes,
     como el silencio de 6–8 s visto en T78). Mirar `data/micro_hft/heartbeat.json`.
   - `libro`: hueco de secuencia (`pu`) o divergencia con el snapshot REST: espera a que el libro
     se resincronice (lo rehace el recolector, T78).
   - `reloj`: desvío local − Binance > 500 ms o sin medir. Sincronizar la hora de Windows
     (`w32tm /resync`) y comprobar el desfase en el banco (`scripts/hft_latency.py`).
   - `flujo de usuario`: la conexión del `listenKey` se cortó; los fills de ese tramo no llegan
     por evento. Al reconectar, la reconciliación los recupera consultando cada orden por su id.
   - `hombre muerto`: la estrategia dejó de latir > 3 s (proceso colgado o bucle bloqueado).
     En testnet, además, `countdownCancelAll` (15 s) deja de renovarse y Binance cancela todas
     las órdenes del símbolo aunque este proceso haya muerto.
   El aviso «desbloqueo» marca la vuelta a la normalidad; no hay que reactivar nada.
2. **Divergencia (kill-switch global y del carril, `regla:hft_reconciliacion`):** la posición
   del carril no cuadra con la del exchange tras releer todas sus órdenes. Con el kill-switch el
   carril cancela todo y cierra su inventario a mercado (reduce-only, con decisión). Antes de
   desactivar (§1, y el del carril a mano): contrastar con la web de la testnet y revisar si
   otro carril operó el mismo símbolo en la misma cuenta (su posición debe ir en `external`).
3. **Sin respuesta del exchange ≥ 30 s:** misma regla y mismo cierre ordenado.
4. **429 (límite de tasa):** el cliente deja de enviar hasta `Retry-After` (o 1 s) y el riesgo
   veta «límite del exchange»; reanuda solo. Si se repite, las tasas propias (1/3 de 300/10 s y
   1200/min) están mal o hay otro proceso usando la misma cuenta o IP.
5. **418 (IP bloqueada, 2 min–3 días):** kill-switch del carril (`regla:hft_418`), que solo se
   apaga a mano y después de que venza el bloqueo. No reiniciar en bucle: cada petición alarga
   el bloqueo. Las órdenes vivas las cancela `countdownCancelAll` (testnet) al no renovarse.
6. **Rechazos** (`HftExecutor.rejections`): `-5022` post-only que habría cruzado (el libro se
   movió en vuelo: normal, sin reintento), `-4164` nocional mínimo, `-2022` reduce-only sin
   posición. Muchos `-5022` seguidos = la estrategia cotiza demasiado cerca del otro lado.
7. **Cuenta compartida:** `countdownCancelAll` cancela TODAS las órdenes del símbolo, también
   las de otro carril. Usar una cuenta (o subcuenta) de testnet propia para el carril HFT, o
   poner `exchange_countdown_ms = 0` en una versión nueva de la configuración.
