# T150 — Lo que publica la síntesis no puede decir más de lo que sabe (2026-11-10, `juanpablo-cpu`)

**Modo análisis.** El panel publica la síntesis v2. El bróker simulado, el plan y las estrategias de T49 siguen con la v1, bit a bit: T31 y T143 no cambian.

## 1. Prerrequisito: el falso hueco de `microstructure` (BACKLOG T120 (2))

No eran los silencios de `depth`: `HFT_GAP_SQL` ya los excluía. **El recolector de liquidaciones (`liq_ws`) escribe sus reconexiones (bybit, okx, binance) en la misma tabla `micro/gaps`**, con flujo `liq:<venue>`, y `read_micro` las contaba como huecos del flujo de órdenes. Medido sobre la carpeta viva, BTCUSDT, las últimas 22 jornadas:

| Velas incompletas | 1 h | 4 h |
|---|--:|--:|
| Antes (regla vieja) | 38,9 % | 67,4 % |
| Sin `liq:*` (arreglo) | 25,2 % | 48,3 % |
| Solo los huecos de la captura HFT | 9,7 % | 24,7 % |

Reproduce exacto el 38 %/69 % de T120. Lo que queda entre la segunda y la tercera fila son reconexiones **reales** del recolector viejo de T23 (flujo `ws`, 21-oct → 2-nov), cuando era la fuente: se dejan, y salen solas de la ventana. Arreglo: `eim/data/micro.py::OLD_GAP_SQL` (la lectura ignora `liq:*`); prueba `tests/data/test_collector.py::test_reconexion_de_liquidaciones_no_es_hueco_del_flujo`. El escritor sigue mezclando tablas (BACKLOG T150 (4)).

**Despliegue (decisión delegada por el usuario, 2026-11-10):** lo que lee el agente también lo lee el bróker simulado, y T31 no cambia hasta su cierre (◆ de T143). Por eso el arreglo queda **detrás de `EIM_MICRO_IGNORE_LIQ_GAPS=1`, apagado por defecto**, y se enciende al cerrar T31 (≥ 2026-11-27; BACKLOG T150 (6)). Con eso, la síntesis v2 del panel no cambia nada que lea el bróker y puede entrar en cualquier reinicio. Mientras tanto, `microstructure` seguirá sin voto en el panel por «degradado».

Aviso: en 4 h el agente seguirá «degradado» un tiempo (48 % > `max_incomplete` 0,3), porque su ventana de 500 velas abarca toda la captura y arrastra esos huecos reales de octubre.

## 2. Entregables 1–4: la síntesis v2

Código puro en `eim/synthesis/evidence.py` y `synth.py` (parámetro `evidence`); reglas declaradas en `EvidenceParams` (`params.py`); lectura del historial en `ReportStore.history` (solo columnas) y `eim/api/synthesis_live.py`. La usan `GET /v2/synthesis`, el flujo `reports` del WebSocket y la repetición (`/v2/replay`).

- **Sin datos no vota (1).** Por agente, en las últimas **48 velas guardadas en vivo**: si `no_data` + `degraded` (o ausente) pasa del **50 %**, peso 0, fuera del denominador de la confianza, y la tesis lo dice («Sin voto por falta de datos en las últimas 48 velas: …»). Con menos de 12 velas guardadas decide la vela actual («ventana corta»).
- **Cobertura publicada (2).** `synthesis.coverage[agente]` = estado dominante, cuentas ok/degradado/sin datos, ventana, fuente declarada por el agente y motivo; `synthesis.window` = ventanas, umbral, ρ previa, pares medidos y tramo. En la interfaz: detalle de cada esfera y detalle de la síntesis.
- **Correlación verificable (3).** ρ de Pearson del sesgo entre votantes, en las últimas **200 velas** con datos en ambos (≥ 30 comunes; si no, **ρ previa 0,5**: lo desconocido no se supone independiente), recortada a [0, 1]. Confianza × (N_eff / N)^0,5 (factor «correlacion»): la precisión de una media de N votos con correlación ρ es la de N_eff independientes, y el error típico va con √N.
- **Votos efectivos (4).** N_eff = (Σw)² / ΣΣ wᵢwⱼρᵢⱼ, con w = el peso efectivo de cada votante. En la tesis, en el río («6 votantes ≈ 1,9 votos efectivos») y en el detalle de la síntesis.

**Una corrección a la ficha:** con cinco votantes y ρ 0,6 la fórmula da **1,47**, no 1,8. El ~1,8 corresponde a ρ 0,44, el mínimo medido en T44. Se usa la fórmula estándar y la prueba fija las dos cifras.

**Pruebas** (`tests/synthesis/test_t150_evidence.py`): la del entregable 1 (el agente sin datos no mueve el sesgo, con su sesgo en −0,9, 0 y +0,9) y la del 3 (cinco agentes con ρ > 0,6 dan menos del 75 % de la confianza de cinco independientes). **Las dos fallan con la síntesis v1**: se comprobó parcheando `synthesize` para que ignore la evidencia, y además hay dos pruebas que fijan el defecto de v1. Golden de T02/T05 (`tests/legacy/test_golden.py`, agentes) intactos: T150 no toca ningún agente.

## 3. Entregable 5: calibración

`v2/reports/t150_calibracion.md` (y `.json`/`.csv`), con `scripts/t150_calibracion.py` por la cola (45 min). **Desfavorable para las dos versiones**: en el banco de T131 la dirección acierta el **46,1 %** a 24 h (sin solape, ±2,6 pp), la confianza no lleva información (el acierto es plano entre tramos) y, leída como distancia a una moneda, promete de más; v2 lo reduce muy poco (Brier 0,2708 → 0,2700, ECE 0,143 → 0,140). Votan 5,7 agentes y equivalen a **1,88 votos efectivos**. Se adopta igual (regla previa, ◆2 de T146). No se recalibra a mano: sería ajustar a un resultado ya visto.

## 4. Entregable 6 (◆, resuelta por el usuario el 2026-11-10: «lo recomendado»)

`EvidenceParams.informative`: `seasonality` y `liquidations` se muestran pero no votan en el panel; `smart_money` queda retirado del voto. `calendar` ya no votaba (modula la confianza). `microstructure` y `derivatives` votan solo con cobertura en vivo, como cualquier agente con la regla 1. Solo afecta a la v2.

## 5. Verificación en la interfaz

API temporal del worktree (8011) sobre una copia de `reports.duckdb` y de las velas, y Vite en 5174. Capturas: `T150_sintesis_panel.jpg` (detalle de la síntesis: «6 votantes ≈ 1,8 votos efectivos (ρ medio 0,49)», «Confianza ×0,55 por correlación entre votantes», ventanas 48/200) y `T150_microestructura_sin_voto.jpg` («No vota por falta de datos: 0/48 velas con datos, 45 degradadas y 3 sin datos…», fuente y ventana). Ahí `microstructure` sale sin voto porque sus reportes guardados se calcularon con la regla vieja de huecos: con el arreglo desplegado, empezará a votar cuando su ventana de 48 velas se limpie (~2 días en 1 h).

## 6. Revisión (`code-review` alto)

10 hallazgos, 5 arreglados: bloqueados pintados como votantes (ahora van en `weights` con 0), un fallo del historial ya no tumba el mensaje de reportes (no se publica síntesis y queda en el registro), la correlación solo entre quienes pueden votar, estado de cobertura = lo dominante y sin la doble penalización de la tabla fija de T44 en v2. Los otros 5, al BACKLOG T150: observatorio y deriva del pronóstico en v1, escritor de `liq_ws` y orden de versiones por texto. El quinto, el Pearson hecho a mano en vez de numpy, se deja: es puro, corto y está probado.
