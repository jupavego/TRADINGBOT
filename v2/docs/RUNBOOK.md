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
```bash
# 1) detener la API / servicio (Ctrl+C en eim.operation run)
python -m eim.data.backup list
python -m eim.data.backup verify backups/eim_AAAAMMDD-HHMMSS
python -m eim.data.backup restore backups/eim_AAAAMMDD-HHMMSS --data-dir data
# 2) relanzar y comprobar
python -m eim.operation run --execution paper
```
`restore` verifica hashes antes de tocar nada, se niega si la base está abierta, guarda la base
actual como `reports.duckdb.antes-de-restaurar-<AAAAMMDD-HHMMSS>` y la carpeta `operation/` como
`operation.antes-de-restaurar-<…>` (cada restauración con su sello: repetirla no pierde el original)
y restaura kill-switch y estado del servicio.
La configuración versionada no se restaura (vive en git; la copia la conserva para auditoría).
Velas: si no se copiaron, se vuelven a descargar solas (`EIM_AUTO_HISTORY=1`).
En testnet, tras restaurar: reconciliar (§2) antes de reactivar.

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

## 8. Copia diaria fallida
Alerta `copia_seguridad` con el error (disco lleno, ruta inexistente, permisos). Corregir y esperar
el reintento automático (cada hora) o forzar `python -m eim.data.backup create`. La operación no
se detiene por esto.

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
5. **Base dañada:** no hay copia automática todavía (BACKLOG T40 (5)). Renombrar
   `data/leaders.duckdb` y volver a registrar los líderes (`add 0x… --watch`) reinicia la cuenta de
   días adelante: último recurso.
6. **Tras el arreglo:** el tablero se renueva en ≤ 5 min y `smart_money` vuelve a tener datos. Si
   el apagado fue largo, ver en `docs/OPERACION.md` §6 qué huecos quedan (tope de 10 000
   ejecuciones y de 24 h por líder al volver).
