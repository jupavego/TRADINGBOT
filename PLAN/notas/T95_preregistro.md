# T95 — Pre-registro del ranking global, el control placebo y la multiplicidad

Fijado el 2026-11-26, **antes** de correr el placebo o el ranking sobre datos reales (los corre `aplicar_t95.cmd` después de aplicar este código). Cambiar cualquier regla = archivo nuevo `T95_preregistro_v2.md`, nunca editar este. Su SHA-256 queda en el informe `v2/reports/scanner_placebo.md`.

## 1. Pregunta (◆)
¿El escáner global, con su umbral de prioridad, muestra en el universo de Binance algo que supere el azar? **Hipótesis nula: no.** Un «no» es un resultado válido.

## 2. Qué se mide
- **Universo:** los perpetuos USDT de Binance que pasan las etapas 1–2 de T93 con la última vela guardada (`--asof latest`), marco `1d`, 500 velas por instrumento, lista corta de 25 (parámetros por defecto de `eim/scanner/params.py`), agentes = última versión de `default_registry()`.
- **Prioridad** (la única combinación, `eim/scanner/rank.py` 1.0.0): media con pesos **iguales (0,25)** de calidad de la señal, viabilidad, riesgo/costos (las de T94, sin tocar) y ventaja = Φ(ventaja neta en σ de su horizonte). La ventaja es la esperanza de los tres escenarios en el lado de la candidata menos el costo de ida y vuelta de su clase (T92), dividida por σ por vela (60 velas) × √horizonte. Sin costo o sin σ: no comparable, sin prioridad.
- **Placebo vinculante:** 30 réplicas con **permutación conjunta de fechas** (la misma permutación para todo el universo: conserva volatilidad, distribución y correlación contemporánea; destruye la estructura temporal), semilla 95. **Sensibilidad (no vinculante):** 10 réplicas gaussianas con la misma σ y correlación. En cada réplica corre el mismo escáner completo: etapa 3 → lista corta → agentes → síntesis → proyección → prioridad.

## 3. Regla de decisión
- α = 0,05 (`validation_v1`, V3).
- **Umbral del panel** = cuantil 95 % (método «higher») del máximo de prioridad por réplica permutada.
- **«Supera el azar»** si y solo si (a) al menos una candidata real tiene prioridad ≥ umbral **y** (b) p global = (1 + nº de réplicas cuyo máximo ≥ máximo real) / (1 + 30) < α. Si no, **no supera**.
- Se informan además: falsos esperados por pasada con ese umbral, tasa de falsos por candidata y la estimación de la tasa de falsos descubrimientos (falsos por pasada / reales por encima).
- Superar el azar **no valida** nada: solo la puerta v1 de T49 valida.

## 4. Registro de intentos y multiplicidad (hacia adelante)
- **Intento** = `instrumento|agente@versión|marco|hH` (la síntesis es el agente `sintesis`, con versión de síntesis, etapa profunda, puntuaciones y huella de agentes). Se registra cada vez que se evalúa, con lado o sin él, y nunca se borra.
- **Observación:** al cerrar las H = 25 velas, resultado = lado × ln(cierre final / cierre de partida) en σ del horizonte, neto del costo de su clase; y el del lado contrario con el mismo costo.
- **p bruto** con ≥ 10 observaciones maduras: lado al azar, réplicas = mín(250 000, máx(500, 40 × familia)).
- **Familia** = 841 intentos previos de la puerta T49 (sin p = 1) + todos los del escáner. **Holm vinculante**; Benjamini–Hochberg informativa; Sharpe deflactado con el tamaño de la familia. PBO no aplica (T84 se archivó sin construirse).
- Cada candidata muestra el nº de hipótesis de su familia y su p ajustado; hasta madurar, p = 1.

## 5. Pesos de la prioridad
Iguales hasta tener **≥ 200 resultados maduros de la síntesis**. Entonces `python -m eim.scanner calibrate`: mitad anterior en el tiempo para elegir (rejilla del símplex, paso 0,25, correlación de rangos con el resultado), mitad posterior para comprobar; **se adoptan solo si superan a los iguales fuera de muestra y la correlación es positiva**. Unos pesos nuevos dejan el umbral del placebo desactualizado: hay que repetirlo antes de marcar nada.
