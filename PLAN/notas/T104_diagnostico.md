# T104 — Diagnóstico: ¿por qué la esfera de Microestructura decía «sin datos»?

Fecha: 2026-10-20. Evidencia tomada del equipo del usuario (carpeta viva `v2/data`) y del código.

## Cadena de causas

**(a) Nadie lanzaba el recolector (causa raíz).** `scripts/servicio_continuo.ps1` solo lanzaba
Ollama, el vigilante de operación (API), los líderes y la hoja de ruta; `eim.operation.watchdog`
solo vigila la API y los líderes. `python -m eim.data.collectors.binance_ws SYMBOL --root data`
no tenía supervisor, ni latido, ni cerrojo, y `docs/` no lo mencionaba. Con el proceso apagado
no se escribe `data/micro/` y el agente devuelve su motivo `no_data`:
«sin recolección de microestructura (colector no corre)».

**(b) Estado en el equipo.** Antes de T104 no existía `data/micro/`. Tras el avance del
2026-10-19 (lanzamiento desde `servicio_continuo.ps1`) el 2026-10-20 había procesos
`binance_ws` y `liq_ws` vivos desde las 00:35 (hora local) y `data/micro/{trades,top,depth,gaps,liqs}`
con Parquet por hora. Verificado a las ~01:50: 12 velas de 15 m con datos, 4 incompletas.

**(c) Ruta de lectura.** `read_micro` (trades+top+gaps → `aggregate`) → `build_snapshot`
(`snapshot.micro`, `sources["micro"]="binance_ws"`) → agente → `AgentReport` → esfera
(`web/src/river.ts`). Con datos reales devuelve `MicroBar` con OFI, delta, imbalance y
`complete=False` en las velas que cruzan un hueco. La ruta funciona; no había nada que leer.

**(d) Umbral `min_bars`.** El agente exige 24 velas con datos (`MicrostructureParams.min_bars`):
6 h en 15 m, 24 h en 1 h, 4 días en 4 h. Hasta entonces responde «recolección insuficiente (n/24
velas)» (la esfera ya muestra «acumulando n/24»). No es un fallo: es acumulación.

**(e) Red.** Los datos reales muestran 4 cortes `ConnectionClosedError: no close frame received
or sent` en el flujo `ws` en ~6 h (y otros en liquidaciones): el WebSocket de futuros conecta
y se cae sin cierre limpio. El recolector ya los registra como hueco y reconecta
(espera exponencial, snapshot REST), de modo que las velas afectadas salen `complete=False` y,
si superan `max_incomplete`, el agente pasa a `degraded`. `aggTrade` va por una conexión
aparte (`/market/stream`) y depth por otra: un corte de una no tumba la otra. Hipótesis de
«conecta pero no entrega» (BACKLOG T09): no se observó aquí; si ocurriera, el latido muestra
`last_msg_ms` viejo → estado `sin_flujo` y aviso local.

## Qué se hizo
- **Supervisor** `python -m eim.data.collectors.supervise` (cerrojo `micro/supervisor.lock`;
  reinicio con espera creciente; reinicio si el latido `micro/heartbeat.json` se detiene 120 s;
  cerrojo `micro/collector.lock` en el recolector contra duplicados). Integrado en
  `servicio_continuo.ps1`. Hora de arranque en el latido (`started_at`) y en el registro
  `micro/logs/op-*.jsonl`.
- **Prueba real** (Binance real, carpeta temporal): arranque → 98 trades y 282 diffs en 30 s;
  proceso hijo matado a la fuerza → relanzado a los 10 s con PID nuevo y latido nuevo.
  Corte de red físico: no provocado en esta sesión (pendiente en la prueba de ≥ 24 h);
  el camino de reconexión ya lo ejercitan los 4 cortes reales de arriba.
- **Disco**: Parquet con compresión ZSTD; medido sobre datos reales (pre-ZSTD):
  profundidad ≈ 471 MB/día, top 11, trades 8, liqs 1,7, huecos 0,1 → ≈ 493 MB/día. Retención:
  la profundidad cruda se poda a 30 días (≈ 14 GB; E: tiene 400 GB libres); el resto se conserva.
  Aviso local si el disco baja de 5 GB, si el recolector está apagado o sin flujo.
- **Interfaz**: la esfera dice «recolector apagado» · «acumulando n/24» · «sin datos recientes» ·
  `% · degradado por huecos`. `GET /v2/micro/status` expone estado, motivo, MB/día y disco.

## Pendiente (requiere tiempo de calendario)
- ≥ 24 h con el servicio en marcha + captura de pantalla de la esfera con datos.
- ≥ 7 días: repetir `agents_marginal_report` para `microstructure` (línea base de la Fase 16).
- Para que el vigilante asuma el recolector que ya corre sin supervisión (lanzado a mano o por
  la versión previa del script): detenerlo y volver a ejecutar `servicio_continuo.ps1`.
