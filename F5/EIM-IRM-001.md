# EIM-IRM-001
# Inference Repository
# Motor de Diagnóstico Estructural

---

| Campo | Valor |
|---|---|
| **Código** | EIM-IRM-001 |
| **Nombre** | Inference Repository — Motor de Diagnóstico Estructural |
| **Repositorio** | IRM |
| **Proyecto** | EMA Intelligence Model (EIM) |
| **Versión** | 1.0.1 |
| **Estado** | ACTIVE |
| **Fecha** | 2026-08-17 |
| **Dependencias** | MSI-META-001, EIM-ONT-001, EIM-DDMR-001 v1.1, EIM-FRM-001, EIM-BRM-001, EIM-KG-001 |

---

## Historial de Cambios

| Versión | Fecha | Descripción |
|---|---|---|
| 1.0.0 | 2026-06-27 | Creación. Motor de inferencia completo: DIAG-001 con 4 componentes (Conviction Score, Scenario Mapping, Confidence Score, Explanation Template). 12 reglas de escenario, 6 modificadores de confianza, tabla de mapeo completa. |
| 1.0.1 | 2026-08-17 | Etapa 3: se añade el modificador M-007 (transición inválida de STRUCTURAL_STATE, -10 al confidence_score), implementando en código la obligación ya descrita en EIM-BRM-001 § Parte III desde v1.0.0 pero nunca formalizada aquí ni codificada. `StructuralDiagnosis` gana el campo `transition_status`. |

---

## Propósito

El IRM es el componente final del pipeline analítico del EIM. Recibe los cinco estados L3 producidos por FRM y BRM y produce el **STRUCTURAL_DIAGNOSIS** (V-L4-001): el output único del sistema.

El IRM no calcula. No clasifica. **Infiere.**

La distinción es importante:
- El FRM calcula valores numéricos a partir de datos.
- El BRM clasifica valores en estados categóricos.
- El IRM integra estados heterogéneos en un diagnóstico coherente con hipótesis, escenario, confianza y explicación.

---

## Arquitectura del Motor

El IRM opera en cuatro etapas secuenciales:

```
ETAPA 1 — Conviction Score
          Convierte estados L3 a scores numéricos y los pondera.
          Produce: conviction_score [0–100]
          ↓
ETAPA 2 — Scenario Mapping
          Mapea la combinación de estados al escenario más probable.
          Produce: probable_scenario [SC-01 a SC-05]
          ↓
ETAPA 3 — Confidence Score
          Cuantifica la confiabilidad del diagnóstico mediante
          COHERENCE_SCORE como base y modificadores contextuales.
          Produce: confidence_score [0–95]
          ↓
ETAPA 4 — Explanation Template
          Genera la narrativa explicativa del diagnóstico
          con referencias explícitas a los estados que lo produjeron.
          Produce: explanation [string]
```

---

# PARTE I — ETAPA 1: CONVICTION SCORE

---

## Definición

El **Conviction Score** es una puntuación numérica [0–100] que representa la fortaleza y dirección del estado estructural actual. Es la síntesis cuantitativa de los cinco inputs L3.

- Valores cercanos a 100 → convicción alcista fuerte
- Valores cercanos a 50 → neutralidad o incertidumbre
- Valores cercanos a 0 → convicción bajista fuerte

## Conversión de Estados a Scores Numéricos

Antes de la ponderación, cada estado L3 se convierte a un score numérico mediante tablas de conversión deterministas.

### Tabla CS-001 — Conversión STRUCTURAL_STATE

| Estado | Score base | Dirección requerida | Nota |
|---|---|---|---|
| E-01_TREND_STRONG (alcista) | 95 | SLOPE_DIRECTION = UP | Máxima convicción alcista |
| E-01_TREND_STRONG (bajista) | 5 | SLOPE_DIRECTION = DOWN | Máxima convicción bajista |
| E-03_ORDERED (alcista) | 75 | UP | Tendencia estructurada |
| E-03_ORDERED (bajista) | 25 | DOWN | Tendencia estructurada bajista |
| E-02_TREND_WEAK (alcista) | 62 | UP | Tendencia incipiente |
| E-02_TREND_WEAK (bajista) | 38 | DOWN | Tendencia débil bajista |
| E-06_EXPANDING (alcista) | 70 | UP | Expansión desde compresión |
| E-06_EXPANDING (bajista) | 30 | DOWN | Expansión bajista |
| E-04_EXHAUSTED | 50 | NEUTRAL | Transición sin dirección |
| E-05_COMPRESSED | 50 | NEUTRAL | Energía acumulada sin dirección |
| E-07_DIVERGENT | 50 | NEUTRAL | Incertidumbre estructural |

**Nota de implementación:** Para E-01, E-03, E-02 y E-06 la dirección se determina mediante SLOPE_DIRECTION. Si SLOPE_DIRECTION = NEUTRAL con estos estados, usar STACK_ORDER para inferir dirección (BULL → score alcista, BEAR → score bajista).

### Tabla CS-002 — Modificador MOMENTUM_STATE

El MOMENTUM_STATE modifica el score estructural mediante un multiplicador aplicado sobre la desviación desde 50:

| Estado | Multiplicador | Efecto |
|---|---|---|
| ACCELERATING | 1.20 | Amplifica la convicción en un 20% |
| STABLE | 1.00 | Sin modificación |
| DECELERATING | 0.80 | Reduce la convicción en un 20% |
| REVERSING | 0.60 | Reduce fuertemente — señal de cambio |

**Fórmula del modificador:**

```
score_modificado = 50 + (score_base - 50) * multiplicador_momentum
```

### Tabla CS-003 — Modificador ENERGY_STATE

| Estado | Delta aplicado al score | Dirección del delta |
|---|---|---|
| HIGH_ENERGY | +8 | En dirección del score (aleja de 50) |
| MODERATE_ENERGY | +0 | Sin modificación |
| LOW_ENERGY | -5 | Hacia 50 (reduce convicción) |
| COMPRESSED | +3 | En dirección del score (potencial acumulado) |

**Fórmula del delta de energía:**

```
delta_energia = delta_tabla * SIGN(score_momentum - 50)
score_energia = score_momentum + delta_energia
```

### Tabla CS-004 — Modificador FRICTION_INDEX

| FRICTION_INDEX | Delta aplicado | Efecto |
|---|---|---|
| FI >= 8.0 | -8 | Alta fricción reduce la convicción de movimiento |
| FI ∈ [5.0, 8.0) | -3 | Fricción moderada |
| FI ∈ [2.0, 5.0) | +0 | Sin efecto |
| FI < 2.0 | +4 | Baja fricción amplifica la convicción |

### Fórmula completa del Conviction Score

```
// PASO 1: Score base desde estado estructural
S1 = score_tabla_CS001(STRUCTURAL_STATE, SLOPE_DIRECTION)

// PASO 2: Modificar por momentum
mult_momentum = multiplicador_tabla_CS002(MOMENTUM_STATE)
S2 = 50 + (S1 - 50) * mult_momentum

// PASO 3: Modificar por energía
delta_e = delta_tabla_CS003(ENERGY_STATE) * SIGN(S2 - 50)
S3 = S2 + delta_e

// PASO 4: Modificar por fricción
delta_f = delta_tabla_CS004(FRICTION_INDEX)
S4 = S3 + delta_f * SIGN(S3 - 50)

// PASO 5: Clamp al rango válido
CONVICTION_SCORE = CLAMP(S4, 0, 100)
```

### Pseudocódigo completo ETAPA 1

```
INPUT:  STRUCTURAL_STATE, MOMENTUM_STATE, ENERGY_STATE,
        FRICTION_INDEX, SLOPE_DIRECTION, STACK_ORDER
OUTPUT: conviction_score   // float [0, 100]

// Determinar dirección
IF SLOPE_DIRECTION == "UP":   dir = +1
IF SLOPE_DIRECTION == "DOWN": dir = -1
IF SLOPE_DIRECTION == "NEUTRAL":
    dir = +1 IF STACK_ORDER IN ["BULL_PERFECT","BULL_PARTIAL"] ELSE -1

// PASO 1: Score estructural base
score_map = {
    "E-01_TREND_STRONG": 95 IF dir==+1 ELSE 5,
    "E-03_ORDERED":      75 IF dir==+1 ELSE 25,
    "E-02_TREND_WEAK":   62 IF dir==+1 ELSE 38,
    "E-06_EXPANDING":    70 IF dir==+1 ELSE 30,
    "E-04_EXHAUSTED":    50,
    "E-05_COMPRESSED":   50,
    "E-07_DIVERGENT":    50
}
S1 = score_map[STRUCTURAL_STATE]

// PASO 2: Modificador momentum
mult_map = {"ACCELERATING": 1.20, "STABLE": 1.00,
            "DECELERATING": 0.80, "REVERSING": 0.60}
S2 = 50 + (S1 - 50) * mult_map[MOMENTUM_STATE]

// PASO 3: Modificador energía
energy_delta = {"HIGH_ENERGY": 8, "MODERATE_ENERGY": 0,
                "LOW_ENERGY": -5, "COMPRESSED": 3}
S3 = S2 + energy_delta[ENERGY_STATE] * SIGN(S2 - 50)

// PASO 4: Modificador fricción
IF   FRICTION_INDEX >= 8.0: fd = -8
ELIF FRICTION_INDEX >= 5.0: fd = -3
ELIF FRICTION_INDEX >= 2.0: fd = 0
ELSE:                       fd = +4
S4 = S3 + fd * SIGN(S3 - 50)

// PASO 5: Clamp
RETURN CLAMP(S4, 0, 100)
```

---

# PARTE II — ETAPA 2: SCENARIO MAPPING

---

## Definición

El **Scenario Mapping** asigna el escenario más probable de los cinco definidos en EIM-ONT-001 a partir de la combinación de STRUCTURAL_STATE, MOMENTUM_STATE y ENERGY_STATE, con refinamientos por FRICTION_INDEX y CONVICTION_SCORE.

Los cinco escenarios posibles:

| Código | Nombre | Descripción |
|---|---|---|
| SC-01 | CONTINUATION | El mercado mantiene su estado actual. La estructura sugiere persistencia. |
| SC-02 | BREAKOUT | Salida de compresión o expansión con cambio significativo de estructura. |
| SC-03 | PULLBACK | Corrección temporal hacia una EMA de referencia. Estado subyacente se preserva. |
| SC-04 | STRUCTURAL_CHANGE | Reconfiguración sostenida de la organización interna del mercado. |
| SC-05 | CONSOLIDATION | Sin tendencia definida. Propiedades oscilan sin dirección clara. |

## Tabla de Mapeo de Escenarios

La siguiente tabla define el escenario primario para cada combinación de estados. Las celdas con `*` indican que el refinamiento por FRICTION o CONVICTION es necesario.

| STRUCTURAL_STATE | MOMENTUM_STATE | ENERGY_STATE | Escenario primario |
|---|---|---|---|
| E-01_TREND_STRONG | ACCELERATING | HIGH_ENERGY | SC-01 CONTINUATION |
| E-01_TREND_STRONG | ACCELERATING | COMPRESSED | SC-02 BREAKOUT* |
| E-01_TREND_STRONG | STABLE | HIGH_ENERGY | SC-01 CONTINUATION |
| E-01_TREND_STRONG | STABLE | MODERATE_ENERGY | SC-01 CONTINUATION |
| E-01_TREND_STRONG | DECELERATING | ANY | SC-03 PULLBACK |
| E-01_TREND_STRONG | REVERSING | ANY | SC-04 STRUCTURAL_CHANGE |
| E-03_ORDERED | ACCELERATING | ANY | SC-01 CONTINUATION |
| E-03_ORDERED | STABLE | MODERATE_ENERGY | SC-01 CONTINUATION |
| E-03_ORDERED | STABLE | LOW_ENERGY | SC-05 CONSOLIDATION |
| E-03_ORDERED | DECELERATING | ANY | SC-03 PULLBACK |
| E-03_ORDERED | REVERSING | ANY | SC-04 STRUCTURAL_CHANGE |
| E-02_TREND_WEAK | ACCELERATING | ANY | SC-01 CONTINUATION |
| E-02_TREND_WEAK | STABLE | ANY | SC-05 CONSOLIDATION |
| E-02_TREND_WEAK | DECELERATING | ANY | SC-03 PULLBACK* |
| E-02_TREND_WEAK | REVERSING | ANY | SC-04 STRUCTURAL_CHANGE |
| E-04_EXHAUSTED | ACCELERATING | ANY | SC-03 PULLBACK |
| E-04_EXHAUSTED | STABLE | ANY | SC-03 PULLBACK |
| E-04_EXHAUSTED | DECELERATING | ANY | SC-04 STRUCTURAL_CHANGE |
| E-04_EXHAUSTED | REVERSING | ANY | SC-04 STRUCTURAL_CHANGE |
| E-05_COMPRESSED | STABLE | COMPRESSED | SC-02 BREAKOUT (inminente) |
| E-05_COMPRESSED | ACCELERATING | ANY | SC-02 BREAKOUT (activo) |
| E-05_COMPRESSED | DECELERATING | ANY | SC-05 CONSOLIDATION |
| E-05_COMPRESSED | REVERSING | ANY | SC-04 STRUCTURAL_CHANGE |
| E-06_EXPANDING | ACCELERATING | HIGH_ENERGY | SC-02 BREAKOUT (confirmado) |
| E-06_EXPANDING | ACCELERATING | MODERATE_ENERGY | SC-01 CONTINUATION |
| E-06_EXPANDING | STABLE | ANY | SC-01 CONTINUATION |
| E-06_EXPANDING | DECELERATING | ANY | SC-03 PULLBACK |
| E-06_EXPANDING | REVERSING | ANY | SC-04 STRUCTURAL_CHANGE |
| E-07_DIVERGENT | ANY | ANY | SC-05 CONSOLIDATION |

## Reglas de Refinamiento

Tras la asignación del escenario primario se aplican las siguientes reglas de refinamiento en orden. Cada regla puede sobrescribir el escenario primario.

### SR-001 — Refinamiento por Alta Fricción en BREAKOUT

```
IF escenario_primario == "SC-02_BREAKOUT"
   AND FRICTION_INDEX >= 7.0:
    escenario = "SC-05_CONSOLIDATION"
    // Alta fricción impide la ruptura — el mercado sigue consolidando
```

### SR-002 — Refinamiento por Baja Convicción en CONTINUATION

```
IF escenario_primario == "SC-01_CONTINUATION"
   AND CONVICTION_SCORE IN [40, 60]  // zona neutral
   AND COHERENCE_SCORE < 5.0:
    escenario = "SC-05_CONSOLIDATION"
    // Baja convicción y baja coherencia → no hay continuación clara
```

### SR-003 — Confirmación de BREAKOUT por MTF_SYNC

```
IF escenario_primario == "SC-02_BREAKOUT"
   AND MTF_SYNC IS AVAILABLE
   AND MTF_SYNC < 50:
    escenario = "SC-01_CONTINUATION"
    // Ruptura no confirmada en múltiples timeframes → es continuación de tendencia local
```

### SR-004 — Refinamiento PULLBACK vs STRUCTURAL_CHANGE por BOUNCE_COUNT_200

```
IF escenario_primario == "SC-03_PULLBACK"
   AND BOUNCE_COUNT_200 == 0
   AND STRUCTURAL_STATE IN ["E-04_EXHAUSTED"]:
    escenario = "SC-04_STRUCTURAL_CHANGE"
    // Sin historia de respeto a EMA-200 + agotamiento → cambio estructural probable
```

### Pseudocódigo completo ETAPA 2

```
INPUT:  STRUCTURAL_STATE, MOMENTUM_STATE, ENERGY_STATE,
        FRICTION_INDEX, CONVICTION_SCORE, COHERENCE_SCORE,
        MTF_SYNC, BOUNCE_COUNT_200
OUTPUT: probable_scenario   // enum SC-01 a SC-05

// Lookup tabla de mapeo
scenario = lookup_table(STRUCTURAL_STATE, MOMENTUM_STATE, ENERGY_STATE)

// Refinamientos SR-001 a SR-004
IF scenario == "SC-02_BREAKOUT" AND FRICTION_INDEX >= 7.0:
    scenario = "SC-05_CONSOLIDATION"

IF scenario == "SC-01_CONTINUATION"
   AND 40 <= CONVICTION_SCORE <= 60
   AND COHERENCE_SCORE < 5.0:
    scenario = "SC-05_CONSOLIDATION"

IF scenario == "SC-02_BREAKOUT"
   AND MTF_SYNC IS NOT NULL AND MTF_SYNC < 50:
    scenario = "SC-01_CONTINUATION"

IF scenario == "SC-03_PULLBACK"
   AND BOUNCE_COUNT_200 == 0
   AND STRUCTURAL_STATE == "E-04_EXHAUSTED":
    scenario = "SC-04_STRUCTURAL_CHANGE"

RETURN scenario
```

---

# PARTE III — ETAPA 3: CONFIDENCE SCORE

---

## Definición

El **Confidence Score** [0–95] cuantifica cuánto se puede confiar en el diagnóstico producido. No mide si el diagnóstico es correcto — mide si las condiciones que lo produjeron son internamente coherentes y están bien confirmadas.

**Límite máximo de 95:** El sistema nunca afirma certeza absoluta. Un confidence_score de 95 significa condiciones óptimas, no garantía de resultado.

## Base del Confidence Score

```
base = COHERENCE_SCORE * 10
// COHERENCE_SCORE ∈ [0,10] → base ∈ [0,100]
```

La coherencia estructural es la base porque implementa el axioma AX-03: la consistencia entre propiedades incrementa la confiabilidad del diagnóstico.

## Modificadores del Confidence Score

Los modificadores se aplican secuencialmente sobre la base. El resultado se clampea a [0, 95] al final.

### Modificador M-001 — MTF_SYNC (confirmación multi-timeframe)

```
IF MTF_SYNC IS AVAILABLE:
    IF MTF_SYNC >= 75:  delta = +10
    IF MTF_SYNC >= 50:  delta = +5
    IF MTF_SYNC >= 25:  delta = 0
    IF MTF_SYNC <  25:  delta = -15
ELSE:
    delta = 0   // sin penalización si MTF no está implementado aún
```

### Modificador M-002 — BOUNCE_COUNT_200 (respeto a equilibrio macro)

```
IF BOUNCE_COUNT_200 >= 5:  delta = +8
IF BOUNCE_COUNT_200 >= 3:  delta = +5
IF BOUNCE_COUNT_200 >= 1:  delta = +2
IF BOUNCE_COUNT_200 == 0:  delta = -5
```

### Modificador M-003 — Combinación de estados (BRM)

```
IF combinacion == "IMPOSIBLE":   delta = -50  // error crítico
IF combinacion == "INUSUAL":     delta = -10
IF combinacion == "NORMAL":      delta = 0
IF combinacion == "ATENCIÓN":    delta = -5
```

### Modificador M-004 — FRICTION_INDEX vs Escenario

```
IF probable_scenario == "SC-02_BREAKOUT" AND FRICTION_INDEX >= 6.0:
    delta = -10
    // Alta fricción contradice la ruptura

IF probable_scenario == "SC-01_CONTINUATION" AND FRICTION_INDEX < 3.0:
    delta = +5
    // Baja fricción confirma la continuación
```

### Modificador M-005 — Conviction Score extremo

```
IF CONVICTION_SCORE >= 85 OR CONVICTION_SCORE <= 15:
    delta = +8
    // Alta convicción en cualquier dirección aumenta la confianza

IF 45 <= CONVICTION_SCORE <= 55:
    delta = -8
    // Zona neutral de convicción → diagnóstico menos confiable
```

### Modificador M-006 — ENERGY_STATE vs Escenario

```
IF probable_scenario == "SC-02_BREAKOUT" AND ENERGY_STATE == "COMPRESSED":
    delta = +10
    // Energía acumulada confirma la ruptura inminente

IF probable_scenario == "SC-01_CONTINUATION" AND ENERGY_STATE == "LOW_ENERGY":
    delta = -8
    // Sin energía no hay continuación sostenible
```

### Modificador M-007 — Transición inválida de STRUCTURAL_STATE (añadido v1.0.1)

```
IF TRANSITION_STATUS == "INVALID":
    delta = -10
    // La transición desde el estado anterior no figura en la matriz de
    // transiciones válidas de EIM-BRM-001 § Parte III — no bloquea el
    // diagnóstico (por diseño, ver nota de implementación del BRM), pero
    // reduce la confianza. Penalidad análoga a INUSUAL (M-003) porque
    // ambas comparten el mismo tratamiento ("no bloquear, registrar
    // anomalía"). Valor provisional, no fijado numéricamente en la v1.0.0
    // original — sujeto a calibración en Fase VI como el resto.
```

Este modificador estaba descrito como obligación del IRM en EIM-BRM-001 § Parte III ("El IRM debe verificar estas transiciones... reducir el confidence_score") desde la v1.0.0 de ese documento, pero no tenía tabla ni pseudocódigo propio aquí ni implementación en Fase VII hasta esta versión.

### Pseudocódigo completo ETAPA 3

```
INPUT:  COHERENCE_SCORE, MTF_SYNC, BOUNCE_COUNT_200,
        combinacion_status, probable_scenario,
        FRICTION_INDEX, CONVICTION_SCORE, ENERGY_STATE,
        transition_status
OUTPUT: confidence_score   // float [0, 95]

score = COHERENCE_SCORE * 10   // base

// M-001: MTF_SYNC
IF MTF_SYNC IS NOT NULL:
    IF   MTF_SYNC >= 75: score += 10
    ELIF MTF_SYNC >= 50: score += 5
    ELIF MTF_SYNC >= 25: score += 0
    ELSE:                score -= 15

// M-002: BOUNCE_COUNT_200
IF   BOUNCE_COUNT_200 >= 5: score += 8
ELIF BOUNCE_COUNT_200 >= 3: score += 5
ELIF BOUNCE_COUNT_200 >= 1: score += 2
ELSE:                       score -= 5

// M-003: Combinación de estados
IF   combinacion_status == "IMPOSIBLE":  score -= 50
ELIF combinacion_status == "INUSUAL":    score -= 10
ELIF combinacion_status == "ATENCIÓN":   score -= 5

// M-004: Fricción vs Escenario
IF probable_scenario == "SC-02_BREAKOUT" AND FRICTION_INDEX >= 6.0:
    score -= 10
IF probable_scenario == "SC-01_CONTINUATION" AND FRICTION_INDEX < 3.0:
    score += 5

// M-005: Conviction Score extremo
IF CONVICTION_SCORE >= 85 OR CONVICTION_SCORE <= 15:
    score += 8
IF 45 <= CONVICTION_SCORE <= 55:
    score -= 8

// M-006: Energía vs Escenario
IF probable_scenario == "SC-02_BREAKOUT" AND ENERGY_STATE == "COMPRESSED":
    score += 10
IF probable_scenario == "SC-01_CONTINUATION" AND ENERGY_STATE == "LOW_ENERGY":
    score -= 8

// M-007: Transición inválida (añadido v1.0.1 — ver EIM-BRM-001 § Parte III)
IF transition_status == "INVALID":
    score -= 10

RETURN CLAMP(score, 0, 95)
```

---

# PARTE IV — ETAPA 4: EXPLANATION TEMPLATE

---

## Definición

El Explanation Template genera una narrativa estructurada y reproducible que explica el diagnóstico en términos de los estados que lo produjeron. Implementa RC-10 del MSI-META-001 (trazabilidad obligatoria del diagnóstico).

El template no es texto libre. Es una **plantilla parametrizada** donde cada campo se resuelve dinámicamente a partir de los valores de los estados.

## Componentes del Template

### Bloque 1 — Estado estructural
```
"El mercado presenta [STRUCTURAL_STATE_LABEL] 
 ([STRUCTURAL_STATE_DESC])."
```

### Bloque 2 — Momentum
```
"El momentum es [MOMENTUM_STATE_LABEL] 
 con dirección [SLOPE_DIRECTION] y 
 [CONVICTION_SCORE > 60: 'alta' | 40-60: 'moderada' | < 40: 'baja'] convicción."
```

### Bloque 3 — Energía
```
"La energía estructural es [ENERGY_STATE_LABEL]
 [SI COMPRESSED: 'indicando alta energía potencial acumulada']
 [SI HIGH_ENERGY: 'con expansión activa en curso']
 [SI LOW_ENERGY: 'con capacidad de movimiento limitada']."
```

### Bloque 4 — Coherencia
```
"La coherencia estructural es [COHERENCE_SCORE]/10
 ([>= 8: 'alta — diagnóstico confiable' | 
   5-8: 'moderada — diagnóstico válido con reservas' | 
   < 5: 'baja — señales contradictorias'])."
```

### Bloque 5 — Escenario
```
"El escenario más probable es [SCENARIO_LABEL]: [SCENARIO_DESC].
 Confianza del diagnóstico: [CONFIDENCE_SCORE]%."
```

### Bloque 6 — Moduladores (condicional)
```
[SI MTF_SYNC DISPONIBLE]:
"Confirmación multi-timeframe: [MTF_SYNC]%
 ([>= 75: 'alta confirmación' | 50-75: 'confirmación parcial' | < 50: 'sin confirmación'])."

[SI FRICTION_INDEX >= 6]:
"Alta fricción estructural ([FRICTION_INDEX]/10) limita la velocidad del movimiento esperado."

[SI BOUNCE_COUNT_200 >= 3]:
"El precio ha respetado la EMA-200 [BOUNCE_COUNT_200] veces en la ventana actual,
 confirmando el régimen macro."
```

## Tablas de Etiquetas

### Labels STRUCTURAL_STATE

| Estado | Label | Descripción corta |
|---|---|---|
| E-01_TREND_STRONG | "tendencia fuerte" | "alineamiento estructural completo con alta convicción direccional" |
| E-02_TREND_WEAK | "tendencia débil" | "dirección presente pero con insuficiente convicción estructural" |
| E-03_ORDERED | "estructura ordenada" | "stack alineado con tendencia sostenible establecida" |
| E-04_EXHAUSTED | "estructura agotada" | "pérdida de impulso sin confirmación de reversión" |
| E-05_COMPRESSED | "compresión estructural" | "convergencia de EMAs con alta energía potencial acumulada" |
| E-06_EXPANDING | "expansión estructural" | "salida de compresión con separación de EMAs en progreso" |
| E-07_DIVERGENT | "estructura divergente" | "propiedades inconsistentes — baja fiabilidad diagnóstica" |

### Labels SCENARIO

| Escenario | Label | Descripción corta |
|---|---|---|
| SC-01_CONTINUATION | "continuación" | "persistencia del estado actual sin señales de reversión" |
| SC-02_BREAKOUT | "ruptura" | "salida de estructura con cambio significativo en propiedades" |
| SC-03_PULLBACK | "pullback" | "corrección temporal hacia referencia estructural" |
| SC-04_STRUCTURAL_CHANGE | "cambio estructural" | "reconfiguración sostenida de la organización interna" |
| SC-05_CONSOLIDATION | "consolidación" | "ausencia de tendencia definida — propiedades oscilan sin dirección" |

## Pseudocódigo completo ETAPA 4

```
INPUT:  STRUCTURAL_STATE, MOMENTUM_STATE, ENERGY_STATE,
        COHERENCE_SCORE, FRICTION_INDEX, CONVICTION_SCORE,
        probable_scenario, confidence_score,
        MTF_SYNC, BOUNCE_COUNT_200, SLOPE_DIRECTION
OUTPUT: explanation   // string

parts = []

// Bloque 1
parts.append(f"El mercado presenta {label(STRUCTURAL_STATE)}
               ({desc(STRUCTURAL_STATE)}).")

// Bloque 2
conv_label = "alta" IF CONVICTION_SCORE > 60
             ELSE "moderada" IF CONVICTION_SCORE >= 40
             ELSE "baja"
parts.append(f"El momentum es {label(MOMENTUM_STATE)}
               con dirección {SLOPE_DIRECTION}
               y {conv_label} convicción.")

// Bloque 3
energy_suffix = {
    "COMPRESSED":       "indicando alta energía potencial acumulada",
    "HIGH_ENERGY":      "con expansión activa en progreso",
    "LOW_ENERGY":       "con capacidad de movimiento reducida",
    "MODERATE_ENERGY":  ""
}
parts.append(f"La energía estructural es {label(ENERGY_STATE)}
               {energy_suffix[ENERGY_STATE]}.")

// Bloque 4
coh_label = "alta — diagnóstico confiable" IF COHERENCE_SCORE >= 8
            ELSE "moderada — diagnóstico válido con reservas" IF COHERENCE_SCORE >= 5
            ELSE "baja — señales contradictorias"
parts.append(f"La coherencia estructural es {COHERENCE_SCORE}/10 ({coh_label}).")

// Bloque 5
parts.append(f"El escenario más probable es {label(probable_scenario)}:
               {desc(probable_scenario)}.
               Confianza del diagnóstico: {confidence_score}%.")

// Bloque 6 — moduladores condicionales
IF MTF_SYNC IS NOT NULL:
    mtf_label = "alta confirmación" IF MTF_SYNC >= 75
                ELSE "confirmación parcial" IF MTF_SYNC >= 50
                ELSE "sin confirmación"
    parts.append(f"Confirmación multi-timeframe: {MTF_SYNC}% ({mtf_label}).")

IF FRICTION_INDEX >= 6:
    parts.append(f"Alta fricción estructural ({FRICTION_INDEX}/10)
                   limita la velocidad del movimiento esperado.")

IF BOUNCE_COUNT_200 >= 3:
    parts.append(f"El precio ha respetado la EMA-200
                   {BOUNCE_COUNT_200} veces en la ventana actual,
                   confirmando el régimen macro.")

RETURN " ".join(parts)
```

---

# PARTE V — DIAGNÓSTICO COMPLETO (DIAG-001)

---

## Definición del Output

**Código:** DIAG-001
**Variable:** V-L4-001 STRUCTURAL_DIAGNOSIS
**Tipo:** Objeto estructurado

## Estructura del Objeto STRUCTURAL_DIAGNOSIS

```json
{
  "timestamp": "2026-06-27T00:00:00Z",
  "timeframe": "4h",
  "instrument": "BTC-PERP",

  "inputs": {
    "structural_state":   "E-01_TREND_STRONG",
    "momentum_state":     "ACCELERATING",
    "energy_state":       "HIGH_ENERGY",
    "coherence_score":    8.4,
    "friction_index":     2.1,
    "conviction_score":   91.2,
    "mtf_sync":           82.0,
    "bounce_count_200":   4
  },

  "diagnosis": {
    "market_state":       "E-01_TREND_STRONG",
    "probable_scenario":  "SC-01_CONTINUATION",
    "conviction_score":   91.2,
    "confidence_score":   87.0,
    "coherence_score":    8.4
  },

  "explanation": "El mercado presenta tendencia fuerte (alineamiento estructural completo con alta convicción direccional). El momentum es acelerado con dirección UP y alta convicción. La energía estructural es alta con expansión activa en progreso. La coherencia estructural es 8.4/10 (alta — diagnóstico confiable). El escenario más probable es continuación: persistencia del estado actual sin señales de reversión. Confianza del diagnóstico: 87.0%. Confirmación multi-timeframe: 82.0% (alta confirmación). El precio ha respetado la EMA-200 4 veces en la ventana actual, confirmando el régimen macro.",

  "metadata": {
    "model_version":   "EIM v1.0",
    "frm_version":     "EIM-FRM-001 v1.0.0",
    "brm_version":     "EIM-BRM-001 v1.0.0",
    "irm_version":     "EIM-IRM-001 v1.0.0",
    "combination_status": "NORMAL"
  }
}
```

## Pseudocódigo completo DIAG-001

```
INPUT:  todos los outputs de FRM + BRM
OUTPUT: STRUCTURAL_DIAGNOSIS object

// ETAPA 1
conviction_score = compute_conviction_score(
    STRUCTURAL_STATE, MOMENTUM_STATE, ENERGY_STATE,
    FRICTION_INDEX, SLOPE_DIRECTION, STACK_ORDER
)

// ETAPA 2
probable_scenario = compute_scenario_mapping(
    STRUCTURAL_STATE, MOMENTUM_STATE, ENERGY_STATE,
    FRICTION_INDEX, conviction_score, COHERENCE_SCORE,
    MTF_SYNC, BOUNCE_COUNT_200
)

// ETAPA 3
confidence_score = compute_confidence_score(
    COHERENCE_SCORE, MTF_SYNC, BOUNCE_COUNT_200,
    combinacion_status, probable_scenario,
    FRICTION_INDEX, conviction_score, ENERGY_STATE
)

// ETAPA 4
explanation = generate_explanation(
    STRUCTURAL_STATE, MOMENTUM_STATE, ENERGY_STATE,
    COHERENCE_SCORE, FRICTION_INDEX, conviction_score,
    probable_scenario, confidence_score,
    MTF_SYNC, BOUNCE_COUNT_200, SLOPE_DIRECTION
)

// Construir objeto
RETURN {
    timestamp:          CURRENT_TIMESTAMP,
    timeframe:          TIMEFRAME,
    instrument:         INSTRUMENT_ID,
    inputs: {
        structural_state:  STRUCTURAL_STATE,
        momentum_state:    MOMENTUM_STATE,
        energy_state:      ENERGY_STATE,
        coherence_score:   COHERENCE_SCORE,
        friction_index:    FRICTION_INDEX,
        conviction_score:  conviction_score,
        mtf_sync:          MTF_SYNC,
        bounce_count_200:  BOUNCE_COUNT_200
    },
    diagnosis: {
        market_state:      STRUCTURAL_STATE,
        probable_scenario: probable_scenario,
        conviction_score:  conviction_score,
        confidence_score:  confidence_score,
        coherence_score:   COHERENCE_SCORE
    },
    explanation: explanation,
    metadata: {
        model_version:      "EIM v1.0",
        frm_version:        "EIM-FRM-001 v1.0.0",
        brm_version:        "EIM-BRM-001 v1.0.0",
        irm_version:        "EIM-IRM-001 v1.0.0",
        combination_status: combinacion_status
    }
}
```

---

# PARTE VI — VALIDACIONES Y CONDICIONES DE FALLO

---

## Validaciones pre-diagnóstico

```
// El IRM no produce diagnóstico si alguna de estas condiciones falla:

V-001: STRUCTURAL_STATE IS NOT NULL
V-002: MOMENTUM_STATE IS NOT NULL
V-003: ENERGY_STATE IS NOT NULL
V-004: COHERENCE_SCORE IS NOT NULL AND COHERENCE_SCORE IN [0, 10]
V-005: FRICTION_INDEX IS NOT NULL AND FRICTION_INDEX IN [0, 10]
V-006: combinacion_status != "IMPOSIBLE"
V-007: TIMESTAMP IS NOT NULL
V-008: TIMEFRAME IS NOT NULL

// Si V-006 falla: registrar error, no producir diagnóstico
// Si cualquier otro falla: registrar warning, intentar diagnóstico parcial
```

## Casos especiales

### Caso E-01 — COMPRESSED + REVERSING

```
// Estado paradójico: mercado comprimido pero con señal de reversión
// Resolución: REVERSING prevalece sobre COMPRESSED en MOMENTUM
// El escenario no es BREAKOUT sino STRUCTURAL_CHANGE
// confidence_score recibe penalización adicional de -10
```

### Caso E-02 — TREND_STRONG + MTF_SYNC < 25%

```
// Tendencia fuerte local pero sin confirmación multi-timeframe
// El diagnóstico es válido pero confidence_score se reduce
// El explanation debe mencionar explícitamente la divergencia temporal
```

### Caso E-03 — CONVICTION_SCORE en zona neutral [45, 55]

```
// El sistema no tiene convicción clara en ninguna dirección
// STRUCTURAL_STATE se mantiene pero probable_scenario se fuerza a SC-05
// confidence_score recibe penalización adicional de -5
```

---

# APÉNDICE A — Pipeline completo EIM

El siguiente diagrama representa el flujo completo desde dato crudo hasta diagnóstico:

```
DATOS OHLCV (exchange)
        │
        ▼
[FRM F-001] EMA_9, EMA_21, EMA_55, EMA_100, EMA_200
        │
        ├──► [FRM F-002 a F-009] Stack, Slopes, Spreads, Elasticidad
        │           │
        │           ├──► [FRM F-010 a F-018] CI, Velocity, Acceleration, Curvature,
        │           │                         Persistence, Compression Duration, Sync
        │           │
        │           └──► [FRM F-020, F-021] Bounces, Cross Events
        │
        ├──► [FRM F-008, F-022] Volume Ratio, ATR Relative
        │
        ▼
[BRM R-001] STRUCTURAL_STATE   ─────────────────────────────┐
[BRM R-002] MOMENTUM_STATE     ──────────────────────────── │
[BRM R-003] ENERGY_STATE       ──────────────────────────── │
[FRM F-011] COHERENCE_SCORE    ──────────────────────────── │
[FRM F-012] FRICTION_INDEX     ──────────────────────────── │
                                                            ▼
                                              [IRM ETAPA 1] CONVICTION_SCORE
                                              [IRM ETAPA 2] PROBABLE_SCENARIO
                                              [IRM ETAPA 3] CONFIDENCE_SCORE
                                              [IRM ETAPA 4] EXPLANATION
                                                            │
                                                            ▼
                                               STRUCTURAL_DIAGNOSIS (DIAG-001)
```

---

# APÉNDICE B — Checklist de conformidad IRM

**Pre-ejecución:**
- [ ] Todos los outputs de FRM disponibles
- [ ] Todos los outputs de BRM disponibles
- [ ] combinacion_status verificado (no IMPOSIBLE)
- [ ] TIMESTAMP y TIMEFRAME presentes

**Post-diagnóstico:**
- [ ] conviction_score ∈ [0, 100]
- [ ] confidence_score ∈ [0, 95]
- [ ] probable_scenario ∈ {SC-01, SC-02, SC-03, SC-04, SC-05}
- [ ] explanation referencia al menos 3 estados L3 explícitamente
- [ ] metadata contiene versiones de FRM, BRM e IRM
- [ ] Si MTF_SYNC disponible → mencionado en explanation
- [ ] Si FRICTION_INDEX >= 6 → mencionado en explanation

---

*Fin del documento EIM-IRM-001 v1.0.0*
