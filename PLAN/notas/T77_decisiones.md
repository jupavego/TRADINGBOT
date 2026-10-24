# T77 — Decisiones HFT: presupuesto, alcance, hipótesis nula y criterios `hft_v1`

2026-10-23 · **◆ Aprobada por escrito por el usuario el 2026-10-23** (presupuesto, horizonte, alcance híbrido, criterios `hft_v1`, motor propio, Python y extra `hft`): T79–T85 quedan desbloqueadas. Evidencia: `v2/reports/hft_latency.md` (banco), `v2/reports/hft_cost_bound.md` (cota), `PLAN/notas/T77_fuentes.md` (Binance y repos).

## (a) Presupuesto de latencia y horizonte mínimo viable
Medido en este equipo (i5-10300H, Wi-Fi, con el servicio continuo en marcha), 3 corridas de 60 min seguidas a las 21, 22 y 23 h UTC del 2026-10-23, sin una sola reconexión:
- **Datos** (evento en Binance → aquí), p50/p95/p99: `depth@100ms` **113 / 123 / 144 ms** (10 por s fijos: ≈ fracción del tiempo); `bookTicker` **118 / 270 / 2 112 ms** (pondera por evento). La cola de `bookTicker` sale casi entera de la corrida de las 22 h, con minutos de 1 300 msg/s (p99 2,6 s ahí; 0,2 s a las 21 y 23 h). No es el proceso Python: el cliente consume ≥ 38 600 msg/s (`scripts/hft_client_capacity.py`); queda por separar Wi-Fi y servidor (BACKLOG). Valor absoluto ± 120 ms (RTT/2); reloj local a 4–13 ms del de Binance, deriva < 1 ppm.
- **Orden** (ida y vuelta): WS API `ping` **237 / 249 / 277 ms**; REST `GET /fapi/v1/time` 255 / 380 / 410 ms. **Proceso Python** (json + libro local) p99 5,3 ms; bucle asyncio p99 21,9 ms.
- **Presupuesto de reacción** (evento → orden en Binance) p50/p95/p99: **233 / 267 / 310 ms** por tiempo; **238 / 413 / 2 277 ms** por evento. Se fija **310 ms (p99) en régimen normal y 2,3 s (p99) en ráfagas**; T79 simula con la distribución medida completa (histogramas de `v2/reports/hft_latency/`), no con una constante.
- **Horizonte mínimo viable: 30 s.** Por latencia bastaría ≥ 10 × p99 en ráfagas ≈ 23 s; mandan los costos (cota, 22,8 h de BTCUSDT): a ≤ 10 s |Δmid| supera 10 pb en el 0,12 % de las ventanas y el techo con previsión perfecta es ≤ 0,06 pb/ventana incluso maker-maker; a 30 s, 13,5 % de ventanas > 4 pb (techo maker 0,30 pb); a 60 s, 3,1 % > 10 pb (techo taker 0,11 pb) y 26 % > 4 pb (maker 0,73 pb). ⇒ entrada pasiva (maker o mixta) desde 30 s; taker solo desde 60 s; < 10 s descartado con VIP 0. T80 mide 1/5/30 s (como pide) **y 60 s**; 1 y 5 s quedan como features, no como tenencia.

## (b) Qué es «HFT» aquí (escala B)
Microestructura rápida sobre la API pública de Binance: decisiones deterministas sobre eventos L2 (`depth@100ms`, `bookTicker`) y operaciones (`aggTrade`) a escala de 100 ms–60 s, **tenencias ≥ 30 s**, órdenes por REST/WS API con ≈ 240 ms de ida y vuelta. Sin colocación, sin L3 (la cola se estima; las órdenes RPI no se ven) y sin LLM en la ruta de una orden.

## (c) Alcance de la v1
**BTCUSDT perpetuo; datos reales (T78) + órdenes simuladas (T79, cola pesimista); equipo local.** ETH, otros símbolos y VPS después de T84. «Híbrido» (lectura del plan, confirmada por el usuario el 2026-10-23): las dos familias de T82 bajo un selector con `stand_down` — direccional con entrada pasiva (`ofi_directional`, mixta 7 pb o maker-maker 4 pb) y creador de mercado con sesgo de señal (Avellaneda–Stoikov). Comisión base VIP 0 sin BNB (2/5 pb); BNB (−10 %) y VIP solo como sensibilidad.

## (d) Hipótesis nula y criterios `hft_v1` (fijados hoy, antes de T80)
**H0: ninguna estrategia tiene edge neto > 0 con IC 95 % tras costos y latencia medida.** Unidad: operación cerrada fuera de muestra, en pb netos del nocional (comisión VIP 0, deslizamiento del simulador T79, latencia muestreada del banco).

| # | Criterio | Umbral |
|---|---|---|
| H1 | Muestra | ≥ 1 000 operaciones de prueba; ≥ 10 días UTC de prueba (contiguos, intactos hasta la corrida final) con ≥ 30 cada uno; ≥ 2 regímenes de volatilidad (terciles de RV diaria *ex ante*) con ≥ 200 cada uno |
| H2 | Edge neto | media ≥ **+1,0 pb**/operación **y** extremo inferior del IC 95 % > 0 (bootstrap por bloques de día UTC, 5 000 réplicas) |
| H3 | Contra el azar | entrada aleatoria con la misma latencia, cola, costos, lado y tenencia: p unilateral (+1) < 0,05 **tras Holm sobre todos los intentos** (estrategias × parámetros × horizontes); réplicas = máx(1 000, 40 × intentos) |
| H4 | Sobreajuste | PBO (CSCV, 16 bloques de día) ≤ **0,25**; Sharpe deflactado ≥ **0,95** |
| H5 | Sensibilidad (cada una sola; IC 95 % inferior > 0) | latencia **×2** (datos y orden); **cola pesimista** (al final de la cola visible al llegar, sin avanzar por cancelaciones; llena solo si el volumen negociado a su precio supera esa cola o el precio se atraviesa); **+1 pb de comisión por lado**; deslizamiento taker ×1,5 |
| H6 | Estabilidad por día | ≥ 60 % de días de prueba con PnL neto > 0; mejor día ≤ 25 % del PnL neto total; caída máxima de la curva acumulada ≤ 50 % del PnL neto total; media > 0 en cada régimen con ≥ 200 operaciones |
| — | Corte temprano | con ≥ 200 operaciones, media + 1 × error estándar < 0 ⇒ RECHAZADA |

Veredicto: **PUBLICABLE A PAPEL** si H1–H6; **EN OBSERVACIÓN** si solo falla H1 sin pérdida clara; **RECHAZADA** en otro caso. T84 los publica tal cual como `hft_v1` en `eim/validation/versions/` con hash fijado; cambiar un umbral = `hft_v2`.

## (e) Simulador: motor mínimo propio + HftBacktest solo como contraste
Motor propio en `eim/hft/` (T79) sobre `Broker`/`SimBroker`, con latencia muestreada del banco y cola pesimista. HftBacktest **no entra en el proyecto**: exige `numpy<2.3` (el proyecto usa 2.4.4), pesa 714 MB, lleva ~10 meses sin commits y usa su propio `.npz`. Se usa solo como contraste en un entorno aparte, fuera de `pyproject.toml`, sobre 2–3 días de T78: si los llenados difieren > 10 %, se documenta cuál es más pesimista y se usa ese.

## (f) Cliente propio, no SDK
`binance_rest.py` para REST; si T83 lo necesita, un módulo propio mínimo del WS API (`order.place/cancel`, firma HMAC por petición; Ed25519 y `session.logon` solo si la latencia lo justifica). El SDK oficial no baja la latencia (mismos servidores), añade otra pila HTTP y lleva 18 versiones mayores.

## (g) Python, no Rust
Regla aplicada a la medición: proceso + bucle p99 = 27,2 ms = **8,8 %** del menor presupuesto p99 (310 ms), por debajo del 20 % ⇒ **Python**. La red domina; Rust no la acorta. Si T78 mostrara que la cola de las ráfagas es del cliente (hoy descartado con un margen de ~30× sobre la tasa medida), se reabre.

## (h) Matriz de aceptación y extra `hft`
Columnas fijas de `v2/reports/hft_acceptance_matrix.md` (T81 la crea, T84 la exige completa): método · familia · tarea · **fuente de la implementación** (propia, o portada con licencia y aviso en `THIRD_PARTY.md`) · **prueba unitaria** · **prueba con datos de Binance** · **costo y latencia modelados** (perfil del banco) · **validación fuera de muestra** (IC, Holm, intentos registrados) · **criterio de desactivación** · estado.
Extra `hft`, lista cerrada: `statsmodels>=0.15,<0.16`, `arch>=8,<9`, `scikit-learn>=1.9,<1.10` (BSD-3/NCSA; probados con numpy 2.4.4). SciPy ya está en el núcleo. Fuera: hmmlearn (mantenimiento limitado; solo con medición), HftBacktest, numba, SDK de Binance, Nautilus, Cryptofeed.

## ◆ Qué se aprueba
1. Presupuesto de 310 ms p99 (2,3 s en ráfagas) y horizonte mínimo de 30 s (taker desde 60 s). 2. Alcance v1 y lectura de «híbrido». 3. Criterios `hft_v1` de la tabla (d). 4. Motor propio + HftBacktest aislado. 5. Cliente propio, Python y la lista cerrada del extra `hft`.
