# EIM-BRM-001
# Business Rules Model
# Motor de Clasificación de Estados

---

| Campo | Valor |
|---|---|
| **Código** | EIM-BRM-001 |
| **Nombre** | Business Rules Model — Motor de Clasificación de Estados |
| **Repositorio** | BRM |
| **Proyecto** | EMA Intelligence Model (EIM) |
| **Versión** | 1.0.1 |
| **Estado** | ACTIVE |
| **Fecha** | 2026-08-17 |
| **Dependencias** | MSI-META-001, EIM-ONT-001, EIM-DDMR-001 v1.1, EIM-FRM-001 |

---

## Historial de Cambios

| Versión | Fecha | Descripción |
|---|---|---|
| 1.0.0 | 2026-06-27 | Creación. 3 reglas de clasificación (R-001, R-002, R-003), 5 umbrales provisionales (θ-001 a θ-005), tabla de combinaciones de estado y matriz de transiciones válidas. |
| 1.0.1 | 2026-08-17 | Corrección editorial (no funcional salvo lo indicado): (1) C-005 — se retira de la prosa una cláusula sobre SLOPE_DIRECTION/STACK_SCORE que el pseudocódigo nunca formalizó; (2) C-008 — se aclara que `SLOPE_DIRECTION[t-3]` (no t-1) rige `direction_changed`, y se corrige código en Fase VII que comparaba contra t-1; se ajusta la prosa del cruce de EMAs a "vela actual" (como ya decía el pseudocódigo); (3) matriz de combinaciones — 2 filas tenían un valor de ENERGY_STATE en la columna MOMENTUM_STATE por error de copiado, corregidas a `ANY`; (4) matriz de transiciones — implementada por primera vez en `eim_brm_irm.py`, con modificador M-007 añadido en EIM-IRM-001 § Parte III. |

---

## Propósito

Este documento define las **reglas de negocio** que transforman los valores calculados por el FRM (variables L2) en los **estados ontológicos** (variables L3) definidos en EIM-ONT-001.

El BRM es la frontera entre el cálculo matemático (FRM) y el razonamiento estructural (IRM). Sin el BRM, los números existen pero no tienen significado estructural.

---

## Arquitectura del BRM

El BRM contiene dos tipos de componentes:

**Tipo A — Reglas de clasificación:** Transforman variables L2 en estados L3 categóricos. Son R-001, R-002 y R-003.

**Tipo B — Umbrales:** Valores numéricos que parametrizan las condiciones de las reglas. Son provisionales hasta la Fase VI (Validación). Se identifican con prefijo θ.

```
Variables L2 (FRM)
      │
      ▼
  Umbrales (θ)
      │
      ▼
Reglas de clasificación (R-001, R-002, R-003)
      │
      ▼
Estados L3: STRUCTURAL_STATE, MOMENTUM_STATE, ENERGY_STATE
      │
      ▼
  EIM-IRM-001 (Motor de Inferencia)
```

**Nota:** COHERENCE_SCORE (V-L3-004) y FRICTION_INDEX (V-L3-005) tienen fórmula directa en FRM (F-011 y F-012). No requieren reglas BRM — sus valores son continuos, no categóricos.

---

# PARTE I — UMBRALES

---

## Catálogo de Umbrales

Los umbrales son parámetros calibrables. Los valores aquí definidos son **provisionales** basados en criterios teóricos. Serán reemplazados por valores estadísticamente óptimos en Fase VI mediante backtesting sobre datos históricos de futuros de criptomonedas.

| ID | Nombre | Variable asociada | Valor provisional | Unidad | Justificación |
|---|---|---|---|---|---|
| θ-001 | Umbral de compresión | COMPRESSION_INDEX | 0.50 | % | CI < 0.5% indica convergencia significativa de EMAs |
| θ-002 | Umbral de expansión | COMPRESSION_INDEX | 2.00 | % | CI > 2.0% indica divergencia estructural relevante |
| θ-003 | Umbral de elasticidad | ELASTICITY | 5.00 | % | ±5% respecto a EMA-200 indica alejamiento significativo |
| θ-004 | Umbral de velocidad estable | SPREAD_VELOCITY | 0.05 | puntos/vela | Variación de CI < 0.05 por vela = estructura estable |
| θ-005 | Umbral de curvatura plana | CURVATURE_n | 0.02 | %/vela | Curvatura < 0.02 = pendiente sin cambio relevante |
| θ-006 | Duración mínima compresión | COMPRESSION_DURATION | 5 | velas | 5 velas consecutivas bajo θ-001 = compresión establecida |
| θ-007 | Persistencia mínima tendencia | PERSISTENCE_ABOVE_21 | 3 | velas | 3 velas sobre/bajo EMA-21 confirma dirección táctica |

**Política de calibración:** Todos los umbrales deben revisarse en EIM-VRM-001 (Fase VI). El proceso de calibración usará percentiles históricos sobre al menos 2 años de datos OHLCV en los principales pares de futuros de criptomonedas (BTC, ETH). Los valores calibrados reemplazarán los provisionales mediante incremento MINOR del BRM.

---

# PARTE II — REGLAS DE CLASIFICACIÓN

---

## R-001 — Clasificación de Estado Estructural (STRUCTURAL_STATE)

**Variable producida:** `STRUCTURAL_STATE` (V-L3-001)
**Tipo de regla:** COMPOSITE con jerarquía de evaluación
**Metamodelo ref:** MSI-META-001 § Meta-Tipo RULE
**Entidad:** EN-05 Estructura
**Estados posibles:** E-01 a E-07 (definidos en EIM-ONT-001 §5)

### Inputs

| Variable | Business Key | Tipo | Rol en la regla |
|---|---|---|---|
| V-L2-001 | STACK_ORDER | enum | Clasificador primario de estructura |
| V-L2-002 | STACK_SCORE | float [0,10] | Gradación de la clasificación |
| V-L2-003 | PRICE_VS_STACK | integer [0,5] | Posición precio relativa al sistema |
| V-L2-012 | SLOPE_DIRECTION | enum | Dirección confirmada |
| V-L2-013 | COMPRESSION_INDEX | float | Detección de compresión |
| V-L2-014 | SPREAD_VELOCITY | float | Detección de expansión activa |
| V-L2-019 | COMPRESSION_DURATION | integer | Duración del estado de compresión |
| V-L2-026 | CROSS_EVENT_9_21 | object | Evento de cambio corto |
| V-L2-027 | CROSS_EVENT_21_55 | object | Evento de cambio medio |
| V-L2-028 | CROSS_EVENT_55_200 | object | Evento de cambio macro |

### Jerarquía de evaluación

Las condiciones se evalúan en el orden definido. La primera condición verdadera determina el estado. No se evalúan condiciones posteriores.

```
EVALUAR en orden:

[1] → E-05_COMPRESSED
[2] → E-06_EXPANDING
[3] → E-01_TREND_STRONG
[4] → E-03_ORDERED
[5] → E-04_EXHAUSTED
[6] → E-02_TREND_WEAK
[7] → E-07_DIVERGENT  (default)
```

**Justificación del orden:** La compresión y la expansión son condiciones de energía que prevalecen sobre la dirección. Un mercado puede estar BULL_PERFECT en stack y al mismo tiempo estar comprimido — en ese caso el diagnóstico más informativo es COMPRESSED porque indica el estado energético inminente.

### Definición formal de condiciones

#### Condición C-001 → E-05_COMPRESSED

```
C-001 = (COMPRESSION_INDEX[t] <= θ-001)
        AND (COMPRESSION_DURATION[t] >= θ-006)
```

Un mercado está estructuralmente comprimido cuando el índice de compresión lleva al menos 5 velas consecutivas por debajo del umbral θ-001. La duración es obligatoria para evitar falsos positivos en cruces transitorios.

#### Condición C-002 → E-06_EXPANDING

```
C-002 = (SPREAD_VELOCITY[t] > θ-004)
        AND (COMPRESSION_DURATION[t-1] >= 3
             OR COMPRESSION_INDEX[t-1] <= θ-001 * 1.5)
```

Una expansión estructural requiere que la velocidad de separación sea positiva Y que el mercado haya estado recientemente en compresión. Esto distingue la expansión real (salida de compresión) del simple crecimiento de spreads en un mercado ya expandido.

#### Condición C-003 → E-01_TREND_STRONG (alcista o bajista)

```
// Alcista:
C-003_BULL = (STACK_ORDER[t] = "BULL_PERFECT")
             AND (STACK_SCORE[t] >= 7.5)
             AND (PRICE_VS_STACK[t] >= 4)
             AND (SLOPE_DIRECTION[t] = "UP")

// Bajista:
C-003_BEAR = (STACK_ORDER[t] = "BEAR_PERFECT")
             AND (STACK_SCORE[t] <= 2.5)
             AND (PRICE_VS_STACK[t] <= 1)
             AND (SLOPE_DIRECTION[t] = "DOWN")

C-003 = C-003_BULL OR C-003_BEAR
```

La tendencia fuerte requiere los cuatro factores simultáneos: ordenamiento perfecto, score extremo, precio en posición extrema y dirección confirmada. Es la condición más restrictiva intencionalmente.

#### Condición C-004 → E-03_ORDERED

```
C-004 = (STACK_SCORE[t] >= 5.0)
        AND (SLOPE_DIRECTION[t] != "NEUTRAL")
        AND NOT C-003  // no tan fuerte como TREND_STRONG
```

Un mercado ordenado tiene la mayoría del stack alineado y una dirección, pero sin los requisitos estrictos de TREND_STRONG. Es el estado de tendencia sana y sostenible.

#### Condición C-005 → E-04_EXHAUSTED

```
C-005 = (STACK_ORDER[t] IN ["BULL_PARTIAL", "BEAR_PARTIAL"])
        AND (SPREAD_VELOCITY[t] < -θ-004)
```

Un mercado agotado mantiene una dirección pero está perdiendo separación activamente. El stack parcial combinado con velocidad negativa indica que la estructura se está deteriorando sin reversión confirmada aún.

**Nota de consistencia (v1.0.1):** una versión anterior de esta prosa incluía además una cláusula sobre SLOPE_DIRECTION/STACK_SCORE que el "Pseudocódigo completo" de esta misma sección nunca formalizó como parte de C-005. La implementación en Fase VII siempre siguió el pseudocódigo (sin esa cláusula) — se elimina aquí para que prosa y pseudocódigo dejen de contradecirse. Si en Fase VI el análisis estadístico muestra que la cláusula adicional mejora la clasificación, debe reintroducirse en ambos (prosa y pseudocódigo) como cambio deliberado de versión MINOR, no como corrección de una inconsistencia.

#### Condición C-006 → E-02_TREND_WEAK

```
C-006 = (STACK_SCORE[t] >= 2.5 AND STACK_SCORE[t] < 7.5)
        AND (SLOPE_DIRECTION[t] != "NEUTRAL")
        AND NOT (C-003 OR C-004 OR C-005)
```

Tendencia presente pero con insuficiente convicción estructural. Captura estados de tendencia incipiente o en proceso de formación.

#### Condición C-007 → E-07_DIVERGENT (default)

```
C-007 = TRUE  // evaluado solo si ninguna condición anterior fue verdadera
```

Estado por defecto. Indica que las propiedades del mercado son inconsistentes o insuficientes para clasificar en cualquier otro estado. Alta COHERENCE_SCORE con DIVERGENT es una combinación imposible — si ocurre indica error de configuración.

### Pseudocódigo completo R-001

```
INPUT:  STACK_ORDER, STACK_SCORE, PRICE_VS_STACK, SLOPE_DIRECTION,
        COMPRESSION_INDEX, SPREAD_VELOCITY, COMPRESSION_DURATION,
        COMPRESSION_INDEX[t-1], COMPRESSION_DURATION[t-1],
        CROSS_EVENT_9_21, CROSS_EVENT_21_55, CROSS_EVENT_55_200
OUTPUT: STRUCTURAL_STATE   // enum E-01 a E-07
REQUIRES: F-001 a F-014, F-016 a F-019, F-021

// [1] Compresión
IF COMPRESSION_INDEX <= 0.50 AND COMPRESSION_DURATION >= 5:
    RETURN "E-05_COMPRESSED"

// [2] Expansión activa (salida de compresión)
IF SPREAD_VELOCITY > 0.05
   AND (COMPRESSION_DURATION_PREV >= 3 OR COMPRESSION_INDEX_PREV <= 0.75):
    RETURN "E-06_EXPANDING"

// [3] Tendencia fuerte
IF STACK_ORDER == "BULL_PERFECT"
   AND STACK_SCORE >= 7.5
   AND PRICE_VS_STACK >= 4
   AND SLOPE_DIRECTION == "UP":
    RETURN "E-01_TREND_STRONG"

IF STACK_ORDER == "BEAR_PERFECT"
   AND STACK_SCORE <= 2.5
   AND PRICE_VS_STACK <= 1
   AND SLOPE_DIRECTION == "DOWN":
    RETURN "E-01_TREND_STRONG"

// [4] Ordenado
IF STACK_SCORE >= 5.0 AND SLOPE_DIRECTION != "NEUTRAL":
    RETURN "E-03_ORDERED"

// [5] Agotado
IF STACK_ORDER IN ["BULL_PARTIAL", "BEAR_PARTIAL"]
   AND SPREAD_VELOCITY < -0.05:
    RETURN "E-04_EXHAUSTED"

// [6] Tendencia débil
IF STACK_SCORE >= 2.5 AND SLOPE_DIRECTION != "NEUTRAL":
    RETURN "E-02_TREND_WEAK"

// [7] Default
RETURN "E-07_DIVERGENT"
```

---

## R-002 — Clasificación de Estado de Momentum (MOMENTUM_STATE)

**Variable producida:** `MOMENTUM_STATE` (V-L3-002)
**Tipo de regla:** COMPOSITE con jerarquía de evaluación
**Entidad:** EN-04 Momentum
**Estados posibles:** ACCELERATING, STABLE, DECELERATING, REVERSING

### Inputs

| Variable | Business Key | Tipo | Rol en la regla |
|---|---|---|---|
| V-L2-004 | SLOPE_9 | float % | Velocidad de momentum inmediato |
| V-L2-005 | SLOPE_55 | float % | Velocidad de tendencia media |
| V-L2-012 | SLOPE_DIRECTION | enum | Dirección predominante |
| V-L2-001 | STACK_ORDER | enum | Contexto estructural |
| V-L2-014 | SPREAD_VELOCITY | float | Dinámica del sistema completo |
| V-L2-015 | SPREAD_ACCELERATION | float | Cambio de dinámica |
| V-L2-016 | CURVATURE_9 | float | Aceleración del momentum inmediato |
| V-L2-017 | CURVATURE_55 | float | Aceleración de tendencia media |
| V-L2-018 | PERSISTENCE_ABOVE_21 | integer | Persistencia de la dirección táctica |

### Jerarquía de evaluación

```
EVALUAR en orden:

[1] → REVERSING      (condición de mayor urgencia diagnóstica)
[2] → ACCELERATING
[3] → DECELERATING
[4] → STABLE         (default si no hay señal dinámica clara)
```

### Definición formal de condiciones

#### Condición C-008 → REVERSING

```
// Signo de SLOPE_DIRECTION es UP → signo esperado de curvatura positiva
// Si curvatura va en contra con fuerza, hay reversión en progreso

C-008 = (CROSS_EVENT_cualquiera.occurred = TRUE en la vela actual)
        OR (
             CURVATURE_55 opuesto a SLOPE_DIRECTION
             AND ABS(CURVATURE_55) > θ-005 * 3
           )
        OR (
             SLOPE_DIRECTION cambió respecto a t-3
           )
```

REVERSING es el estado de mayor prioridad porque indica un cambio estructural en curso. La curvatura de EMA-55 opuesta a la dirección con magnitud alta es la señal más temprana de reversión.

**Nota de consistencia (v1.0.1):** el comparativo de dirección usa explícitamente `SLOPE_DIRECTION[t-3]` (ver `SLOPE_DIRECTION[t-3]` en el INPUT del pseudocódigo completo) — no t-1. Una implementación previa en Fase VII comparaba contra t-1 por error, lo que disparaba REVERSING con cualquier flip de una sola vela; ya corregido en `eim_brm_irm.py`. El evento de cruce (`CROSS_EVENT_cualquiera.occurred`), en cambio, solo se evalúa en la vela actual — una versión anterior de esta prosa decía "en últimas 3 velas" pero el "Pseudocódigo completo" nunca formalizó esa ventana; se ajusta la prosa para reflejar lo que de hecho está implementado. Si se quiere una ventana de 3 velas para el cruce también, es un cambio deliberado de versión MINOR con su propia validación en Fase VI, no una corrección de esta inconsistencia.

**Función auxiliar `direction_sign(d)`:**
- d = "UP" → +1
- d = "DOWN" → -1
- d = "NEUTRAL" → 0

#### Condición C-009 → ACCELERATING

```
C-009 = (SPREAD_VELOCITY > θ-004)
        AND (SPREAD_ACCELERATION > 0)
        AND (SIGN(CURVATURE_9) == direction_sign(SLOPE_DIRECTION))
        AND (SIGN(CURVATURE_55) == direction_sign(SLOPE_DIRECTION))
```

El momentum acelera cuando el sistema se está expandiendo cada vez más rápido Y ambas curvaturas confirman la dirección. Requiere acuerdo de señales en tres dimensiones: velocidad del sistema, aceleración del sistema y curvatura individual de EMA-9 y EMA-55.

#### Condición C-010 → DECELERATING

```
C-010 = (SPREAD_VELOCITY < -θ-004)
        OR (
             SPREAD_ACCELERATION < 0
             AND SPREAD_VELOCITY > 0  // todavía expandiendo pero desacelerando
           )
        OR (
             SIGN(CURVATURE_9) != direction_sign(SLOPE_DIRECTION)
             AND ABS(CURVATURE_9) > θ-005
           )
```

La deceleración puede ocurrir de tres formas: el sistema se está comprimiendo activamente, el sistema sigue expandiendo pero cada vez menos, o el momentum inmediato (EMA-9) ya curvó contra la dirección.

#### Condición C-011 → STABLE (default)

```
C-011 = TRUE  // solo si ninguna condición anterior fue verdadera

// Condición afirmativa adicional (refuerza el STABLE):
// ABS(SPREAD_VELOCITY) <= θ-004
// AND ABS(CURVATURE_9) <= θ-005
// AND PERSISTENCE_ABOVE_21 >= θ-007
```

### Pseudocódigo completo R-002

```
INPUT:  SLOPE_9, SLOPE_55, SLOPE_DIRECTION, STACK_ORDER,
        SPREAD_VELOCITY, SPREAD_ACCELERATION,
        CURVATURE_9, CURVATURE_55, PERSISTENCE_ABOVE_21,
        CROSS_EVENT_9_21, CROSS_EVENT_21_55, CROSS_EVENT_55_200,
        SLOPE_DIRECTION[t-3]
OUTPUT: MOMENTUM_STATE   // enum: ACCELERATING | STABLE | DECELERATING | REVERSING
REQUIRES: F-005, F-009, F-013, F-014, F-015, F-016, F-021

dir_sign = +1 IF SLOPE_DIRECTION == "UP" ELSE (-1 IF SLOPE_DIRECTION == "DOWN" ELSE 0)

// [1] Reversión — mayor prioridad diagnóstica
any_cross = (CROSS_EVENT_9_21.occurred
             OR CROSS_EVENT_21_55.occurred
             OR CROSS_EVENT_55_200.occurred)

curvature_55_opposing = (SIGN(CURVATURE_55) != dir_sign
                         AND ABS(CURVATURE_55) > 0.06
                         AND dir_sign != 0)

direction_changed = (SLOPE_DIRECTION != SLOPE_DIRECTION_T3)

IF any_cross OR curvature_55_opposing OR direction_changed:
    RETURN "REVERSING"

// [2] Aceleración
IF (SPREAD_VELOCITY > 0.05
    AND SPREAD_ACCELERATION > 0
    AND SIGN(CURVATURE_9) == dir_sign
    AND SIGN(CURVATURE_55) == dir_sign
    AND dir_sign != 0):
    RETURN "ACCELERATING"

// [3] Deceleración
IF (SPREAD_VELOCITY < -0.05
    OR (SPREAD_ACCELERATION < 0 AND SPREAD_VELOCITY > 0)
    OR (SIGN(CURVATURE_9) != dir_sign AND ABS(CURVATURE_9) > 0.02 AND dir_sign != 0)):
    RETURN "DECELERATING"

// [4] Estable — default
RETURN "STABLE"
```

---

## R-003 — Clasificación de Estado de Energía (ENERGY_STATE)

**Variable producida:** `ENERGY_STATE` (V-L3-003)
**Tipo de regla:** COMPOSITE con jerarquía de evaluación
**Entidad:** EN-06 Energía
**Estados posibles:** HIGH_ENERGY, MODERATE_ENERGY, LOW_ENERGY, COMPRESSED

### Inputs

| Variable | Business Key | Tipo | Rol en la regla |
|---|---|---|---|
| V-L2-006 | SPREAD_9_21 | float % | Separación de corto |
| V-L2-007 | SPREAD_21_55 | float % | Separación de medio |
| V-L2-008 | SPREAD_55_100 | float % | Separación de largo |
| V-L2-009 | SPREAD_100_200 | float % | Separación macro |
| V-L2-010 | ELASTICITY | float % | Distancia al equilibrio |
| V-L2-013 | COMPRESSION_INDEX | float | Estado global de compresión |
| V-L2-019 | COMPRESSION_DURATION | integer | Tiempo en compresión |
| V-L2-029 | ATR_RELATIVE | float % | Volatilidad contextual |

### Jerarquía de evaluación

```
EVALUAR en orden:

[1] → COMPRESSED    (energía potencial acumulada — condición especial)
[2] → HIGH_ENERGY   (energía cinética liberada)
[3] → LOW_ENERGY    (sistema sin energía ni acumulación)
[4] → MODERATE_ENERGY (default intermedio)
```

### Definición formal de condiciones

#### Condición C-012 → COMPRESSED

```
C-012 = (COMPRESSION_INDEX <= θ-001)
        AND (COMPRESSION_DURATION >= θ-006)
```

Idéntica a C-001 en R-001. El estado COMPRESSED en ENERGY_STATE y en STRUCTURAL_STATE coexisten: son perspectivas diferentes del mismo fenómeno (estructura vs. energía).

#### Condición C-013 → HIGH_ENERGY

```
C-013 = (COMPRESSION_INDEX > θ-002)
        AND (ABS(ELASTICITY) > θ-003)
        AND (SPREAD_VELOCITY > 0)
        AND (ATR_RELATIVE > 0.5)
```

Alta energía cinética: EMAs muy separadas, precio lejos del equilibrio, el sistema sigue expandiendo y la volatilidad lo confirma. Es el estado de máxima liberación de energía.

#### Condición C-014 → LOW_ENERGY

```
C-014 = (COMPRESSION_INDEX <= θ-002)
        AND (COMPRESSION_DURATION < θ-006)
        AND (ABS(ELASTICITY) <= θ-003 / 2)
        AND (ATR_RELATIVE < 0.3)
```

Sistema sin energía acumulada ni liberada. Difiere de COMPRESSED en que no hay duración significativa de compresión — el mercado simplemente está en estado de mínima actividad.

#### Condición C-015 → MODERATE_ENERGY (default)

```
C-015 = TRUE  // cualquier caso no cubierto por C-012, C-013, C-014
```

### Pseudocódigo completo R-003

```
INPUT:  SPREAD_9_21, SPREAD_21_55, SPREAD_55_100, SPREAD_100_200,
        ELASTICITY, COMPRESSION_INDEX, COMPRESSION_DURATION,
        SPREAD_VELOCITY, ATR_RELATIVE
OUTPUT: ENERGY_STATE   // enum: HIGH_ENERGY | MODERATE_ENERGY | LOW_ENERGY | COMPRESSED
REQUIRES: F-006, F-007, F-008, F-010, F-013, F-017, F-022

// [1] Compresión — energía potencial acumulada
IF COMPRESSION_INDEX <= 0.50 AND COMPRESSION_DURATION >= 5:
    RETURN "COMPRESSED"

// [2] Alta energía cinética
IF (COMPRESSION_INDEX > 2.00
    AND ABS(ELASTICITY) > 5.00
    AND SPREAD_VELOCITY > 0.05
    AND ATR_RELATIVE > 0.5):
    RETURN "HIGH_ENERGY"

// [3] Baja energía
IF (COMPRESSION_INDEX <= 2.00
    AND COMPRESSION_DURATION < 5
    AND ABS(ELASTICITY) <= 2.50
    AND ATR_RELATIVE < 0.3):
    RETURN "LOW_ENERGY"

// [4] Energía moderada — default
RETURN "MODERATE_ENERGY"
```

---

# PARTE III — COMBINACIONES DE ESTADO

---

## Matriz de Combinaciones Válidas

La siguiente tabla define qué combinaciones de estados son estructuralmente coherentes. Las combinaciones marcadas como IMPOSIBLE indican un error de cálculo o datos corruptos. Las marcadas como INUSUAL requieren análisis adicional antes de producir diagnóstico.

| STRUCTURAL_STATE | MOMENTUM_STATE | ENERGY_STATE | Validez | Escenario probable |
|---|---|---|---|---|
| E-01_TREND_STRONG | ACCELERATING | HIGH_ENERGY | ✓ NORMAL | SC-01 Continuación |
| E-01_TREND_STRONG | STABLE | HIGH_ENERGY | ✓ NORMAL | SC-01 Continuación |
| E-01_TREND_STRONG | DECELERATING | MODERATE_ENERGY | ✓ NORMAL | SC-03 Pullback |
| E-01_TREND_STRONG | REVERSING | ANY | ✓ ATENCIÓN | SC-04 Cambio estructural |
| E-01_TREND_STRONG | ANY | COMPRESSED | ⚠ INUSUAL | Requiere análisis |
| E-02_TREND_WEAK | ACCELERATING | MODERATE_ENERGY | ✓ NORMAL | SC-01 Continuación incipiente |
| E-02_TREND_WEAK | REVERSING | ANY | ✓ NORMAL | SC-04 Cambio estructural |
| E-02_TREND_WEAK | STABLE | LOW_ENERGY | ✓ NORMAL | SC-05 Consolidación |
| E-03_ORDERED | STABLE | MODERATE_ENERGY | ✓ NORMAL | SC-01 Continuación |
| E-03_ORDERED | DECELERATING | MODERATE_ENERGY | ✓ NORMAL | SC-03 Pullback |
| E-03_ORDERED | REVERSING | ANY | ✓ ATENCIÓN | SC-04 Cambio estructural |
| E-04_EXHAUSTED | DECELERATING | MODERATE_ENERGY | ✓ NORMAL | SC-03 Pullback / SC-04 |
| E-04_EXHAUSTED | ACCELERATING | HIGH_ENERGY | ⚠ INUSUAL | Requiere análisis |
| E-04_EXHAUSTED | REVERSING | ANY | ✓ NORMAL | SC-04 Cambio estructural |
| E-05_COMPRESSED | STABLE | COMPRESSED | ✓ NORMAL | SC-02 Ruptura inminente |
| E-05_COMPRESSED | ACCELERATING | ANY | ✓ NORMAL | SC-02 Ruptura en progreso |
| E-05_COMPRESSED | ANY | HIGH_ENERGY | ✗ IMPOSIBLE | Error de cálculo |
| E-06_EXPANDING | ACCELERATING | HIGH_ENERGY | ✓ NORMAL | SC-02 Ruptura confirmada |
| E-06_EXPANDING | DECELERATING | MODERATE_ENERGY | ✓ NORMAL | Expansión moderada |
| E-06_EXPANDING | ANY | COMPRESSED | ✗ IMPOSIBLE | Error de cálculo |
| E-07_DIVERGENT | ANY | ANY | ✓ BAJA CONFIANZA | SC-05 Consolidación |

---

## Matriz de Transiciones Válidas (STRUCTURAL_STATE)

Define qué transiciones entre estados son estructuralmente posibles. Una transición no listada como válida debe tratarse como anomalía y registrarse para revisión en Fase VI.

| Estado actual → | E-01 | E-02 | E-03 | E-04 | E-05 | E-06 | E-07 |
|---|---|---|---|---|---|---|---|
| **E-01_TREND_STRONG** | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ |
| **E-02_TREND_WEAK** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **E-03_ORDERED** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **E-04_EXHAUSTED** | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **E-05_COMPRESSED** | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |
| **E-06_EXPANDING** | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ |
| **E-07_DIVERGENT** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

**Transiciones marcadas ✗:** No son físicamente posibles en un mercado real sin pasar por un estado intermedio. Su ocurrencia directa indica error de datos o configuración.

**Nota de implementación:** El IRM (EIM-IRM-001) debe verificar estas transiciones y emitir una advertencia si se detecta una transición inválida. No debe bloquear el diagnóstico, sino registrar la anomalía y reducir el confidence_score.

**Estado (v1.0.1):** implementado — `EIMBRM._check_transitions()` en `eim_brm_irm.py` calcula `TRANSITION_STATUS` (`VALID`/`INVALID`/`N/A` en la primera vela) contra esta misma matriz, y el IRM lo consume vía el modificador M-007 (ver EIM-IRM-001 § Parte III) con una penalidad de -10 al confidence_score, además de una frase explícita en la narrativa (Etapa 4) cuando se detecta. Antes de esta versión, la verificación estaba documentada pero no tenía código asociado.

---

# PARTE IV — ORDEN DE EVALUACIÓN Y DEPENDENCIAS

---

## Orden de Evaluación del BRM

```
PASO 1 — Calcular todas las variables L2 (FRM completo)
         Verificar que ninguna variable L2 sea null antes de continuar.

PASO 2 — R-003: ENERGY_STATE
         Solo requiere variables de spreads, compresión y volatilidad.
         No depende de otros estados.

PASO 3 — R-002: MOMENTUM_STATE
         Requiere pendientes, curvaturas y cruces.
         Consume SLOPE_DIRECTION (ya calculado en FRM F-009).
         No depende de otros estados.

PASO 4 — R-001: STRUCTURAL_STATE
         Consume STACK_ORDER, STACK_SCORE, PRICE_VS_STACK,
         SLOPE_DIRECTION, COMPRESSION_INDEX, SPREAD_VELOCITY,
         COMPRESSION_DURATION y eventos de cruce.
         No depende de ENERGY_STATE ni MOMENTUM_STATE directamente,
         pero comparte inputs comunes.

PASO 5 — F-011: COHERENCE_SCORE (FRM)
         Puede calcularse en paralelo con los estados.

PASO 6 — F-012: FRICTION_INDEX (FRM)
         Puede calcularse en paralelo con los estados.

PASO 7 — Verificar combinación de estados contra matriz de combinaciones.
         Si combinación = IMPOSIBLE → registrar error, no producir diagnóstico.
         Si combinación = INUSUAL → registrar advertencia, continuar.

PASO 8 → Pasar todos los estados a EIM-IRM-001.
```

---

## Dependencias cruzadas

| Regla | Depende de (FRM) | Depende de (BRM) |
|---|---|---|
| R-001 | F-002, F-003, F-004, F-009, F-010, F-013, F-017, F-021 | Ninguna |
| R-002 | F-005, F-009, F-013, F-014, F-015, F-016, F-021 | Ninguna |
| R-003 | F-006, F-007, F-010, F-013, F-017, F-022 | Ninguna |

Las tres reglas son **independientes entre sí** — pueden evaluarse en paralelo tras completar el FRM. Esto es una ventaja arquitectural importante para la implementación computacional.

---

# APÉNDICE A — Glosario del BRM

| Término | Definición |
|---|---|
| **Regla de clasificación** | Función que transforma un conjunto de variables L2 en un estado L3 categórico mediante condiciones lógicas ordenadas jerárquicamente. |
| **Umbral (θ)** | Valor numérico que separa regiones de clasificación. Provisional hasta calibración en Fase VI. |
| **Jerarquía de evaluación** | Orden en que se evalúan las condiciones de una regla. La primera condición verdadera determina el estado y detiene la evaluación. |
| **Combinación imposible** | Par o trío de estados que no puede ocurrir simultáneamente en un mercado real. Su ocurrencia indica error de datos o cálculo. |
| **Combinación inusual** | Combinación de estados teóricamente posible pero estadísticamente infrecuente. Requiere análisis adicional. |
| **Transición inválida** | Cambio de estado que no puede ocurrir sin pasar por un estado intermedio. |
| **Calibración** | Proceso de Fase VI que determina los valores óptimos de los umbrales mediante análisis estadístico de datos históricos. |

---

# APÉNDICE B — Checklist de conformidad BRM

Antes de considerar válido cualquier ciclo de evaluación:

**Verificaciones pre-evaluación:**
- [ ] Todas las variables L2 calculadas y no nulas
- [ ] TIMESTAMP y TIMEFRAME presentes en la observación
- [ ] Al menos 400 velas de warmup disponibles (requisito EMA-200)

**Verificaciones post-evaluación:**
- [ ] STRUCTURAL_STATE asignado (nunca null)
- [ ] MOMENTUM_STATE asignado (nunca null)
- [ ] ENERGY_STATE asignado (nunca null)
- [ ] Combinación de estados verificada contra matriz de combinaciones válidas
- [ ] Transición desde estado anterior verificada contra matriz de transiciones
- [ ] Anomalías registradas si combinación = IMPOSIBLE o INUSUAL

**Condiciones de fallo:**
- Combinación IMPOSIBLE detectada → no producir diagnóstico, registrar error
- Variables L2 críticas nulas (COMPRESSION_INDEX, STACK_ORDER, SLOPE_DIRECTION) → no producir diagnóstico

---

*Fin del documento EIM-BRM-001 v1.0.0*
