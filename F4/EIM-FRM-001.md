# EIM-FRM-001
# Formula Repository
# Repositorio Matemático del EIM

---

| Campo | Valor |
|---|---|
| **Código** | EIM-FRM-001 |
| **Nombre** | Formula Repository — Repositorio Matemático |
| **Repositorio** | FRM |
| **Proyecto** | EMA Intelligence Model (EIM) |
| **Versión** | 1.0.0 |
| **Estado** | ACTIVE |
| **Fecha** | 2026-06-27 |
| **Dependencias** | MSI-META-001, EIM-EAR-001, EIM-ONT-001, EIM-DDMR-001 v1.1, EIM-KG-001 |

---

## Historial de Cambios

| Versión | Fecha | Descripción |
|---|---|---|
| 1.0.0 | 2026-06-27 | Creación del repositorio. 22 fórmulas formalizadas cubriendo F-001 a F-022. F-019 (MTF_SYNC) con arquitectura definida, implementación pendiente Fase VII. |

---

## Convenciones de Notación

### Índices temporales
- `t` — vela actual (cierre más reciente)
- `t-1` — vela inmediatamente anterior
- `t-k` — vela k períodos atrás

### Variables de entrada
- `P(t)` — precio de cierre en t (`PRICE_CLOSE`)
- `V(t)` — volumen en t (`VOLUME`)
- `n` — período del instrumento (parámetro de configuración)

### Convenciones de resultado
- Todos los resultados porcentuales se expresan en forma decimal multiplicada por 100 (ej. 2.5 = 2.5%)
- Los índices normalizados tienen rango [0, 10] salvo indicación contraria
- Los scores de confianza tienen rango [0, 100]

### Pseudocódigo
- `INPUT` — variables de entrada requeridas
- `PARAM` — parámetros configurables con valor por defecto
- `OUTPUT` — variable producida con tipo y unidad
- `REQUIRES` — fórmulas que deben calcularse antes

---

# BLOQUE 1 — INSTRUMENTOS DE OBSERVACIÓN
## Fórmulas F-001

---

### F-001 — Cálculo de EMA

**Variable producida:** `EMA_9`, `EMA_21`, `EMA_55`, `EMA_100`, `EMA_200` (V-L1-001 a V-L1-005)
**Propiedad:** Instrumento de observación (H-04)
**Tipo:** Recursiva — requiere inicialización

#### Notación matemática

$$\alpha_n = \frac{2}{n + 1}$$

$$EMA_n(t) = \alpha_n \cdot P(t) + (1 - \alpha_n) \cdot EMA_n(t-1)$$

**Inicialización** (primera vela con suficiente historia):

$$EMA_n(t_0) = \frac{1}{n} \sum_{k=0}^{n-1} P(t_0 - k)$$

**Valores de α por período:**

| Instrumento | n | α |
|---|---|---|
| EMA-9   | 9   | 0.2000 |
| EMA-21  | 21  | 0.0909 |
| EMA-55  | 55  | 0.0357 |
| EMA-100 | 100 | 0.0198 |
| EMA-200 | 200 | 0.0100 |

#### Pseudocódigo

```
INPUT:  P[t]         // PRICE_CLOSE — serie de precios de cierre
PARAM:  n            // período (9 | 21 | 55 | 100 | 200)
OUTPUT: EMA_n[t]     // float, USD

alpha = 2 / (n + 1)

// Inicialización en primera vela válida t0
IF t == t0:
    EMA_n[t] = MEAN(P[t0-n+1 .. t0])
ELSE:
    EMA_n[t] = alpha * P[t] + (1 - alpha) * EMA_n[t-1]

RETURN EMA_n[t]
```

**Nota de implementación:** Aplicar para n ∈ {9, 21, 55, 100, 200}. El período mínimo de datos requerido para que EMA-200 sea estadísticamente estable es 200 velas. Se recomienda usar al menos 400 velas de warmup antes de comenzar a producir diagnósticos.

---

# BLOQUE 2 — POSICIÓN RELATIVA Y ESTRUCTURA DEL STACK
## Fórmulas F-002, F-003, F-004

---

### F-002 — Orden del Stack (STACK_ORDER)

**Variable producida:** `STACK_ORDER` (V-L2-001)
**Propiedad:** PR-07 Posición Relativa
**Tipo:** Clasificación categórica

#### Notación matemática

Definir el vector ordenado del stack:

$$S(t) = [EMA_9(t),\ EMA_{21}(t),\ EMA_{55}(t),\ EMA_{100}(t),\ EMA_{200}(t)]$$

Definir función de pares correctamente ordenados (alcista):

$$\text{bull\_pairs}(t) = \sum_{i=1}^{4} \mathbb{1}[S_i(t) > S_{i+1}(t)]$$

Donde $\mathbb{1}[\cdot]$ es la función indicador (1 si verdadero, 0 si falso).

$$\text{STACK\_ORDER}(t) = \begin{cases} \text{BULL\_PERFECT} & \text{si bull\_pairs} = 4 \\ \text{BULL\_PARTIAL} & \text{si bull\_pairs} \in \{2, 3\} \\ \text{NEUTRAL} & \text{si bull\_pairs} = 2\ \text{y hay mezcla} \\ \text{BEAR\_PARTIAL} & \text{si bull\_pairs} \in \{1, 2\} \text{ bajista} \\ \text{BEAR\_PERFECT} & \text{si bull\_pairs} = 0 \end{cases}$$

**Tabla de clasificación determinista:**

| bull_pairs | bear_pairs | STACK_ORDER |
|---|---|---|
| 4 | 0 | BULL_PERFECT |
| 3 | 1 | BULL_PARTIAL |
| 2 | 2 | NEUTRAL |
| 1 | 3 | BEAR_PARTIAL |
| 0 | 4 | BEAR_PERFECT |

#### Pseudocódigo

```
INPUT:  EMA_9[t], EMA_21[t], EMA_55[t], EMA_100[t], EMA_200[t]
OUTPUT: STACK_ORDER[t]   // enum: BULL_PERFECT | BULL_PARTIAL | NEUTRAL | BEAR_PARTIAL | BEAR_PERFECT
REQUIRES: F-001

stack = [EMA_9[t], EMA_21[t], EMA_55[t], EMA_100[t], EMA_200[t]]
bull_pairs = 0

FOR i IN range(0, 4):
    IF stack[i] > stack[i+1]:
        bull_pairs += 1

SWITCH bull_pairs:
    CASE 4: RETURN "BULL_PERFECT"
    CASE 3: RETURN "BULL_PARTIAL"
    CASE 2: RETURN "NEUTRAL"
    CASE 1: RETURN "BEAR_PARTIAL"
    CASE 0: RETURN "BEAR_PERFECT"
```

---

### F-003 — Puntaje del Stack (STACK_SCORE)

**Variable producida:** `STACK_SCORE` (V-L2-002)
**Propiedad:** PR-07 Posición Relativa
**Tipo:** Puntuación continua [0, 10]

#### Notación matemática

$$\text{STACK\_SCORE}(t) = \text{bull\_pairs}(t) \times 2.5$$

Donde bull_pairs se obtiene de F-002. Rango resultante: {0, 2.5, 5.0, 7.5, 10.0}.

**Interpretación:**

| STACK_SCORE | Significado |
|---|---|
| 10.0 | Alineamiento alcista perfecto |
| 7.5  | Alineamiento alcista fuerte |
| 5.0  | Estructura neutral / transición |
| 2.5  | Alineamiento bajista fuerte |
| 0.0  | Alineamiento bajista perfecto |

#### Pseudocódigo

```
INPUT:  bull_pairs   // resultado interno de F-002
OUTPUT: STACK_SCORE[t]   // float [0, 10]
REQUIRES: F-002

STACK_SCORE[t] = bull_pairs * 2.5

RETURN STACK_SCORE[t]
```

---

### F-004 — Posición del Precio vs. Stack (PRICE_VS_STACK)

**Variable producida:** `PRICE_VS_STACK` (V-L2-003)
**Propiedad:** PR-07 Posición Relativa
**Tipo:** Entero discreto [0, 5]

#### Notación matemática

$$\text{PRICE\_VS\_STACK}(t) = \sum_{n \in \{9,21,55,100,200\}} \mathbb{1}[P(t) > EMA_n(t)]$$

**Interpretación:**

| PRICE_VS_STACK | Significado |
|---|---|
| 5 | Precio sobre todas las EMAs — fortaleza máxima |
| 4 | Precio bajo EMA-200 únicamente |
| 3 | Precio en zona media del stack |
| 2 | Precio bajo la mayoría del stack |
| 1 | Precio sobre EMA-200 únicamente |
| 0 | Precio bajo todas las EMAs — debilidad máxima |

#### Pseudocódigo

```
INPUT:  P[t], EMA_9[t], EMA_21[t], EMA_55[t], EMA_100[t], EMA_200[t]
OUTPUT: PRICE_VS_STACK[t]   // integer [0, 5]
REQUIRES: F-001

emas = [EMA_9[t], EMA_21[t], EMA_55[t], EMA_100[t], EMA_200[t]]
count = 0

FOR ema IN emas:
    IF P[t] > ema:
        count += 1

RETURN count
```

---

# BLOQUE 3 — PENDIENTES Y DIRECCIÓN
## Fórmulas F-005, F-009

---

### F-005 — Pendiente de EMA (SLOPE)

**Variable producida:** `SLOPE_9` (V-L2-004), `SLOPE_55` (V-L2-005)
**Propiedad:** PR-02 Pendiente
**Tipo:** Tasa de cambio porcentual

#### Notación matemática

$$\text{SLOPE}_n(t) = \frac{EMA_n(t) - EMA_n(t-1)}{EMA_n(t-1)} \times 100$$

Unidad: % por vela.

**Nota:** La fórmula es genérica para cualquier n. Se aplica a n=9 y n=55 como instrumentos de observación primarios de momentum y tendencia respectivamente. Puede extenderse a n=21 y n=100 para F-018 (SLOPE_SYNC).

#### Pseudocódigo

```
INPUT:  EMA_n[t], EMA_n[t-1]   // para n = 9 ó 55
OUTPUT: SLOPE_n[t]              // float, % por vela
REQUIRES: F-001

SLOPE_n[t] = ((EMA_n[t] - EMA_n[t-1]) / EMA_n[t-1]) * 100

RETURN SLOPE_n[t]

// Aplicar para n ∈ {9, 55}
// Para SLOPE_SYNC (F-018) extender a n ∈ {9, 21, 55, 100, 200}
```

---

### F-009 — Dirección de Pendiente Predominante (SLOPE_DIRECTION)

**Variable producida:** `SLOPE_DIRECTION` (V-L2-012)
**Propiedad:** PR-01 Dirección
**Tipo:** Clasificación ternaria
**Condición:** Requiere acuerdo entre SLOPE_9 y SLOPE_55

#### Notación matemática

$$\text{SLOPE\_DIRECTION}(t) = \begin{cases} \text{UP}     & \text{si } \text{SLOPE}_9(t) > 0 \land \text{SLOPE}_{55}(t) > 0 \\ \text{DOWN}   & \text{si } \text{SLOPE}_9(t) < 0 \land \text{SLOPE}_{55}(t) < 0 \\ \text{NEUTRAL} & \text{en cualquier otro caso} \end{cases}$$

**Justificación:** La exigencia de acuerdo entre el instrumento de momentum (EMA-9) y el de tendencia media (EMA-55) filtra señales espurias. Una sola EMA apuntando en una dirección sin confirmación de la otra indica transición, no tendencia establecida.

#### Pseudocódigo

```
INPUT:  SLOPE_9[t], SLOPE_55[t]
OUTPUT: SLOPE_DIRECTION[t]   // enum: UP | DOWN | NEUTRAL
REQUIRES: F-005

IF SLOPE_9[t] > 0 AND SLOPE_55[t] > 0:
    RETURN "UP"
ELSE IF SLOPE_9[t] < 0 AND SLOPE_55[t] < 0:
    RETURN "DOWN"
ELSE:
    RETURN "NEUTRAL"
```

---

# BLOQUE 4 — SEPARACIÓN Y ENERGÍA
## Fórmulas F-006, F-007, F-010, F-013, F-014

---

### F-006 — Separación entre EMAs (SPREAD)

**Variable producida:** `SPREAD_9_21`, `SPREAD_21_55`, `SPREAD_55_100`, `SPREAD_100_200` (V-L2-006 a V-L2-009)
**Propiedad:** PR-03 Separación
**Tipo:** Distancia relativa porcentual

#### Notación matemática

Para un par de EMAs (EMA_fast, EMA_slow):

$$\text{SPREAD}_{fast,slow}(t) = \frac{EMA_{fast}(t) - EMA_{slow}(t)}{EMA_{slow}(t)} \times 100$$

**Signo:**
- Positivo → EMA rápida sobre EMA lenta → alineamiento alcista en ese par
- Negativo → EMA rápida bajo EMA lenta → alineamiento bajista en ese par

**Instancias:**

| Variable | fast | slow | Horizonte medido |
|---|---|---|---|
| SPREAD_9_21   | EMA-9   | EMA-21  | Momentum vs. tendencia corta |
| SPREAD_21_55  | EMA-21  | EMA-55  | Tendencia corta vs. media |
| SPREAD_55_100 | EMA-55  | EMA-100 | Tendencia media vs. larga |
| SPREAD_100_200| EMA-100 | EMA-200 | Estructura vs. equilibrio macro |

#### Pseudocódigo

```
INPUT:  EMA_fast[t], EMA_slow[t]
OUTPUT: SPREAD[t]   // float, %
REQUIRES: F-001

SPREAD[t] = ((EMA_fast[t] - EMA_slow[t]) / EMA_slow[t]) * 100

RETURN SPREAD[t]

// Aplicar para cada par:
// SPREAD_9_21   : fast=EMA_9,   slow=EMA_21
// SPREAD_21_55  : fast=EMA_21,  slow=EMA_55
// SPREAD_55_100 : fast=EMA_55,  slow=EMA_100
// SPREAD_100_200: fast=EMA_100, slow=EMA_200
```

---

### F-007 — Elasticidad (ELASTICITY)

**Variable producida:** `ELASTICITY` (V-L2-010)
**Propiedad:** PR-03 Separación / Entidad EN-07
**Tipo:** Distancia relativa precio-equilibrio

#### Notación matemática

$$\text{ELASTICITY}(t) = \frac{P(t) - EMA_{200}(t)}{EMA_{200}(t)} \times 100$$

**Interpretación:**
- Valores extremos positivos (> +15%) → sobreextensión alcista, riesgo de reversión
- Valores extremos negativos (< -15%) → sobreextensión bajista, riesgo de reversión
- Zona [-5%, +5%] → precio en equilibrio
- Los umbrales exactos se calibrarán en Fase VI (Backtesting)

#### Pseudocódigo

```
INPUT:  P[t], EMA_200[t]
OUTPUT: ELASTICITY[t]   // float, %
REQUIRES: F-001

ELASTICITY[t] = ((P[t] - EMA_200[t]) / EMA_200[t]) * 100

RETURN ELASTICITY[t]
```

---

### F-010 — Índice de Compresión (COMPRESSION_INDEX)

**Variable producida:** `COMPRESSION_INDEX` (V-L2-013)
**Propiedad:** PR-05 Compresión
**Tipo:** Índice normalizado [0, ∞)

#### Notación matemática

$$\text{CI}(t) = \frac{|\text{SPREAD}_{9,21}(t)| + |\text{SPREAD}_{21,55}(t)| + |\text{SPREAD}_{55,100}(t)| + |\text{SPREAD}_{100,200}(t)|}{4}$$

Alternativamente en forma expandida:

$$\text{CI}(t) = \frac{1}{4} \sum_{(i,j) \in \text{pares}} \left| \frac{EMA_i(t) - EMA_j(t)}{EMA_j(t)} \right| \times 100$$

**Interpretación:**
- CI próximo a 0 → EMAs completamente convergidas → máxima compresión → energía acumulada máxima
- CI alto → EMAs muy separadas → máxima expansión → energía liberada

**Nota:** Los umbrales de "compresión significativa" y "expansión significativa" se definirán en EIM-BRM-001 mediante análisis estadístico en Fase VI.

#### Pseudocódigo

```
INPUT:  SPREAD_9_21[t], SPREAD_21_55[t], SPREAD_55_100[t], SPREAD_100_200[t]
OUTPUT: COMPRESSION_INDEX[t]   // float, % promedio [0, ∞)
REQUIRES: F-006

CI[t] = (ABS(SPREAD_9_21[t]) +
         ABS(SPREAD_21_55[t]) +
         ABS(SPREAD_55_100[t]) +
         ABS(SPREAD_100_200[t])) / 4

RETURN CI[t]
```

---

### F-013 — Velocidad de Separación (SPREAD_VELOCITY)

**Variable producida:** `SPREAD_VELOCITY` (V-L2-014)
**Propiedad:** PR-03 Separación (derivada primera)
**Tipo:** Tasa de cambio del CI

#### Notación matemática

$$\text{SPREAD\_VELOCITY}(t) = \text{CI}(t) - \text{CI}(t-1)$$

**Interpretación:**
- Positivo → las EMAs se están separando (expansión activa)
- Negativo → las EMAs se están acercando (compresión activa)
- Próximo a 0 → separación estable

#### Pseudocódigo

```
INPUT:  COMPRESSION_INDEX[t], COMPRESSION_INDEX[t-1]
OUTPUT: SPREAD_VELOCITY[t]   // float, puntos/vela
REQUIRES: F-010

SPREAD_VELOCITY[t] = COMPRESSION_INDEX[t] - COMPRESSION_INDEX[t-1]

RETURN SPREAD_VELOCITY[t]
```

---

### F-014 — Aceleración de Separación (SPREAD_ACCELERATION)

**Variable producida:** `SPREAD_ACCELERATION` (V-L2-015)
**Propiedad:** PR-03 Separación (derivada segunda)
**Tipo:** Tasa de cambio de la velocidad

#### Notación matemática

$$\text{SPREAD\_ACCELERATION}(t) = \text{SPREAD\_VELOCITY}(t) - \text{SPREAD\_VELOCITY}(t-1)$$

$$= [CI(t) - CI(t-1)] - [CI(t-1) - CI(t-2)]$$

$$= CI(t) - 2 \cdot CI(t-1) + CI(t-2)$$

**Interpretación:**
- Positivo → la expansión está acelerando (o la compresión desacelerando)
- Negativo → la expansión está desacelerando (o la compresión acelerando)
- Cambio de signo → inflexión en la dinámica del sistema

**Importancia diagnóstica:** Esta es la variable que detecta cambios de régimen antes que cualquier otra. Un cambio de signo en SPREAD_ACCELERATION anticipa un cambio en SPREAD_VELOCITY, que anticipa un cambio en COMPRESSION_INDEX, que anticipa un cambio en STRUCTURAL_STATE.

#### Pseudocódigo

```
INPUT:  SPREAD_VELOCITY[t], SPREAD_VELOCITY[t-1]
OUTPUT: SPREAD_ACCELERATION[t]   // float, puntos/vela²
REQUIRES: F-013

SPREAD_ACCELERATION[t] = SPREAD_VELOCITY[t] - SPREAD_VELOCITY[t-1]

// Equivalente directo (evita requerir SPREAD_VELOCITY):
// SPREAD_ACCELERATION[t] = CI[t] - 2*CI[t-1] + CI[t-2]

RETURN SPREAD_ACCELERATION[t]
```

---

# BLOQUE 5 — CURVATURA
## Fórmula F-015

---

### F-015 — Curvatura de EMA (CURVATURE)

**Variable producida:** `CURVATURE_9` (V-L2-016), `CURVATURE_55` (V-L2-017)
**Propiedad:** PR-02 Pendiente (derivada)
**Tipo:** Segunda derivada de la EMA respecto al tiempo

#### Notación matemática

$$\text{CURVATURE}_n(t) = \text{SLOPE}_n(t) - \text{SLOPE}_n(t-1)$$

$$= \left[\frac{EMA_n(t) - EMA_n(t-1)}{EMA_n(t-1)}\right] - \left[\frac{EMA_n(t-1) - EMA_n(t-2)}{EMA_n(t-2)}\right] \times 100$$

**Interpretación:**
- Positivo → la EMA está curvando hacia arriba (acelerando al alza)
- Negativo → la EMA está curvando hacia abajo (acelerando a la baja)
- Cambio de signo en CURVATURE_9 → señal anticipada de cambio de momentum
- Cambio de signo en CURVATURE_55 → señal anticipada de cambio de tendencia media

**Relación con F-013/F-014:** CURVATURE actúa a nivel de EMA individual; SPREAD_ACCELERATION actúa a nivel del sistema completo. Son señales complementarias.

#### Pseudocódigo

```
INPUT:  SLOPE_n[t], SLOPE_n[t-1]   // para n = 9 ó 55
OUTPUT: CURVATURE_n[t]             // float, %/vela
REQUIRES: F-005

CURVATURE_n[t] = SLOPE_n[t] - SLOPE_n[t-1]

RETURN CURVATURE_n[t]

// Aplicar para n ∈ {9, 55}
```

---

# BLOQUE 6 — VARIABLES TEMPORALES Y DE CONTEO
## Fórmulas F-016, F-017, F-020

---

### F-016 — Persistencia sobre EMA-21 (PERSISTENCE_ABOVE_21)

**Variable producida:** `PERSISTENCE_ABOVE_21` (V-L2-018)
**Propiedad:** PR-04 Persistencia
**Tipo:** Contador con signo

#### Notación matemática

$$\text{PA}_{21}(t) = \begin{cases}
\text{PA}_{21}(t-1) + 1 & \text{si } P(t) > EMA_{21}(t) \land \text{PA}_{21}(t-1) \geq 0 \\
1 & \text{si } P(t) > EMA_{21}(t) \land \text{PA}_{21}(t-1) < 0 \\
\text{PA}_{21}(t-1) - 1 & \text{si } P(t) < EMA_{21}(t) \land \text{PA}_{21}(t-1) \leq 0 \\
-1 & \text{si } P(t) < EMA_{21}(t) \land \text{PA}_{21}(t-1) > 0
\end{cases}$$

**Interpretación:**
- PA = +20 → precio ha cerrado sobre EMA-21 durante 20 velas consecutivas → tendencia sólida
- PA = -10 → precio ha cerrado bajo EMA-21 durante 10 velas consecutivas → presión bajista sostenida
- PA = 0 → cruce reciente (en esta vela o reinicio del contador)

#### Pseudocódigo

```
INPUT:  P[t], EMA_21[t], PERSISTENCE_ABOVE_21[t-1]
OUTPUT: PERSISTENCE_ABOVE_21[t]   // integer, velas (positivo=sobre, negativo=bajo)
REQUIRES: F-001

prev = PERSISTENCE_ABOVE_21[t-1]  // 0 en la primera vela

IF P[t] > EMA_21[t]:
    IF prev >= 0:
        PERSISTENCE_ABOVE_21[t] = prev + 1
    ELSE:
        PERSISTENCE_ABOVE_21[t] = 1     // reinicio alcista
ELSE:
    IF prev <= 0:
        PERSISTENCE_ABOVE_21[t] = prev - 1
    ELSE:
        PERSISTENCE_ABOVE_21[t] = -1    // reinicio bajista

RETURN PERSISTENCE_ABOVE_21[t]
```

---

### F-017 — Duración de Compresión (COMPRESSION_DURATION)

**Variable producida:** `COMPRESSION_DURATION` (V-L2-019)
**Propiedad:** PR-05 Compresión
**Tipo:** Contador de velas en estado comprimido

#### Notación matemática

Sea $\theta$ el umbral de compresión (parámetro calibrable, valor inicial: percentil 25 histórico del CI):

$$\text{CD}(t) = \begin{cases}
\text{CD}(t-1) + 1 & \text{si } \text{CI}(t) \leq \theta \\
0 & \text{si } \text{CI}(t) > \theta
\end{cases}$$

**Interpretación:**
- CD = 0 → el mercado no está en compresión actualmente
- CD = 10 → el mercado lleva 10 velas consecutivas comprimido
- CD alto + CI bajo → energía potencial muy alta → ruptura inminente con alta probabilidad

**Nota:** El umbral θ se define como parámetro en EIM-BRM-001. Valor provisional: θ = 0.5% (sujeto a calibración en Fase VI).

#### Pseudocódigo

```
INPUT:  COMPRESSION_INDEX[t], COMPRESSION_DURATION[t-1]
PARAM:  theta = 0.5   // umbral de compresión (% - provisional, calibrar en Fase VI)
OUTPUT: COMPRESSION_DURATION[t]   // integer, velas [0, ∞)
REQUIRES: F-010

IF COMPRESSION_INDEX[t] <= theta:
    COMPRESSION_DURATION[t] = COMPRESSION_DURATION[t-1] + 1
ELSE:
    COMPRESSION_DURATION[t] = 0

RETURN COMPRESSION_DURATION[t]
```

---

### F-020 — Conteo de Rebotes en EMA (BOUNCE_COUNT)

**Variable producida:** `BOUNCE_COUNT_9`, `BOUNCE_COUNT_21`, `BOUNCE_COUNT_55`, `BOUNCE_COUNT_200` (V-L2-022 a V-L2-025)
**Propiedad:** PR-04 Persistencia
**Tipo:** Conteo de eventos en ventana

#### Notación matemática

Un **rebote** en $EMA_n$ ocurre en la vela $t$ si:

$$\text{rebote}_n(t) = \mathbb{1}\left[\min(P(t), P(t-1)) \leq EMA_n(t) \leq \max(P(t), P(t-1))\right] \land \mathbb{1}\left[\text{lado}(t) = \text{lado}(t-2)\right]$$

Donde $\text{lado}(t) = \text{sgn}(P(t) - EMA_n(t))$ indica si el precio cerró sobre (+1) o bajo (-1) la EMA.

Condición simplificada: la EMA es tocada o cruzada en la vela t, y el precio cierra en el mismo lado de donde venía dos velas atrás.

El conteo en una ventana deslizante de N velas:

$$\text{BOUNCE\_COUNT}_n(t) = \sum_{k=0}^{N-1} \text{rebote}_n(t-k)$$

**Parámetro:** N = 50 velas por defecto.

#### Pseudocódigo

```
INPUT:  P[t..t-N], EMA_n[t..t-N]   // serie de precios y EMA en ventana
PARAM:  N = 50                      // ventana de lookback en velas
OUTPUT: BOUNCE_COUNT_n[t]           // integer, conteo [0, N]
REQUIRES: F-001

bounce_count = 0

FOR k IN range(1, N):              // empezar en k=1 para tener t-2 disponible
    ema_touched = (MIN(P[t-k], P[t-k-1]) <= EMA_n[t-k] <= MAX(P[t-k], P[t-k-1]))

    IF ema_touched:
        side_current = SIGN(P[t-k]   - EMA_n[t-k])
        side_before  = SIGN(P[t-k-2] - EMA_n[t-k-2])

        IF side_current == side_before AND side_current != 0:
            bounce_count += 1

RETURN bounce_count

// Aplicar para n ∈ {9, 21, 55, 200}
```

---

# BLOQUE 7 — EVENTOS DE CRUCE
## Fórmula F-021

---

### F-021 — Evento de Cruce entre EMAs (CROSS_EVENT)

**Variable producida:** `CROSS_EVENT_9_21`, `CROSS_EVENT_21_55`, `CROSS_EVENT_55_200` (V-L2-026 a V-L2-028)
**Propiedad:** PR-06 Cruce
**Tipo:** Objeto de evento (no booleano)

#### Notación matemática

Un cruce alcista de $EMA_{fast}$ sobre $EMA_{slow}$ ocurre en t si:

$$\text{cross\_bull}_{f,s}(t) = \mathbb{1}\left[EMA_f(t-1) \leq EMA_s(t-1)\right] \land \mathbb{1}\left[EMA_f(t) > EMA_s(t)\right]$$

Un cruce bajista ocurre si:

$$\text{cross\_bear}_{f,s}(t) = \mathbb{1}\left[EMA_f(t-1) \geq EMA_s(t-1)\right] \land \mathbb{1}\left[EMA_f(t) < EMA_s(t)\right]$$

La magnitud del cruce:

$$\text{magnitude}_{f,s}(t) = \frac{|EMA_f(t) - EMA_s(t)|}{EMA_s(t)} \times 100$$

Para CROSS_EVENT_55_200 (Golden/Death Cross):
- `direction = GOLDEN_CROSS` si cross_bull
- `direction = DEATH_CROSS` si cross_bear

#### Pseudocódigo

```
INPUT:  EMA_fast[t], EMA_fast[t-1], EMA_slow[t], EMA_slow[t-1], STACK_ORDER[t]
OUTPUT: CROSS_EVENT object
REQUIRES: F-001, F-002

occurred = FALSE
direction = NULL
magnitude = 0.0

IF EMA_fast[t-1] <= EMA_slow[t-1] AND EMA_fast[t] > EMA_slow[t]:
    occurred  = TRUE
    direction = "BULLISH"          // "GOLDEN_CROSS" para par 55/200
    magnitude = ABS(EMA_fast[t] - EMA_slow[t]) / EMA_slow[t] * 100

ELSE IF EMA_fast[t-1] >= EMA_slow[t-1] AND EMA_fast[t] < EMA_slow[t]:
    occurred  = TRUE
    direction = "BEARISH"          // "DEATH_CROSS" para par 55/200
    magnitude = ABS(EMA_fast[t] - EMA_slow[t]) / EMA_slow[t] * 100

RETURN {
    occurred:      occurred,
    direction:     direction,
    magnitude:     magnitude,
    stack_context: STACK_ORDER[t]   // contexto estructural del cruce
}

// Aplicar para pares:
// CROSS_EVENT_9_21  : fast=EMA_9,  slow=EMA_21
// CROSS_EVENT_21_55 : fast=EMA_21, slow=EMA_55
// CROSS_EVENT_55_200: fast=EMA_55, slow=EMA_200
```

---

# BLOQUE 8 — VARIABLES DE CONTEXTO
## Fórmulas F-008, F-022

---

### F-008 — Ratio de Volumen (VOLUME_RATIO)

**Variable producida:** `VOLUME_RATIO` (V-L2-011)
**Tipo:** Ratio adimensional

#### Notación matemática

$$\overline{V}_{N}(t) = \frac{1}{N} \sum_{k=1}^{N} V(t-k)$$

$$\text{VOLUME\_RATIO}(t) = \frac{V(t)}{\overline{V}_{N}(t)}$$

**Parámetro:** N = 20 velas por defecto.

**Interpretación:**
- VR = 1.0 → volumen igual al promedio
- VR > 2.0 → volumen significativamente alto → señal con mayor peso
- VR < 0.5 → volumen muy bajo → señal con menor confianza

#### Pseudocódigo

```
INPUT:  V[t], V[t-1..t-N]
PARAM:  N = 20   // ventana de promedio
OUTPUT: VOLUME_RATIO[t]   // float, ratio [0, ∞)

V_avg = MEAN(V[t-1], V[t-2], ..., V[t-N])   // excluye vela actual
VOLUME_RATIO[t] = V[t] / V_avg

RETURN VOLUME_RATIO[t]
```

---

### F-022 — ATR Relativo (ATR_RELATIVE)

**Variable producida:** `ATR_RELATIVE` (V-L2-029)
**Tipo:** Volatilidad normalizada por precio

#### Notación matemática

El True Range en t:

$$TR(t) = \max\left(H(t) - L(t),\ |H(t) - P(t-1)|,\ |L(t) - P(t-1)|\right)$$

Donde H(t) = precio máximo, L(t) = precio mínimo, P(t-1) = cierre anterior.

El ATR de período 14:

$$ATR_{14}(t) = \frac{1}{14} \sum_{k=0}^{13} TR(t-k)$$

El ATR relativo normalizado por precio:

$$\text{ATR\_RELATIVE}(t) = \frac{ATR_{14}(t)}{P(t)} \times 100$$

**Nota de implementación:** Requiere campos HIGH y LOW del OHLCV. Registrar V-L0-005 (PRICE_HIGH) y V-L0-006 (PRICE_LOW) en EIM-DDMR-001 v1.2.

#### Pseudocódigo

```
INPUT:  H[t], L[t], P[t], P[t-1]   // high, low, close actual, close anterior
PARAM:  period = 14
OUTPUT: ATR_RELATIVE[t]             // float, % del precio
NOTE:   Requiere V-L0-005 y V-L0-006 (PRICE_HIGH, PRICE_LOW)

// True Range
TR[t] = MAX(H[t] - L[t], ABS(H[t] - P[t-1]), ABS(L[t] - P[t-1]))

// ATR como media simple (Wilder usa EMA; ambas son válidas)
ATR_14[t] = MEAN(TR[t], TR[t-1], ..., TR[t-13])

// Normalizar por precio
ATR_RELATIVE[t] = (ATR_14[t] / P[t]) * 100

RETURN ATR_RELATIVE[t]
```

---

# BLOQUE 9 — SINCRONÍA
## Fórmulas F-018, F-019

---

### F-018 — Sincronía de Pendientes (SLOPE_SYNC)

**Variable producida:** `SLOPE_SYNC` (V-L2-020)
**Propiedad:** PR-01 Dirección / Entidad EN-10 Coherencia
**Tipo:** Porcentaje de acuerdo [0, 100]

#### Notación matemática

Calcular pendiente para las 5 EMAs:

$$\text{SLOPE}_n(t) = \frac{EMA_n(t) - EMA_n(t-1)}{EMA_n(t-1)} \times 100 \quad \forall n \in \{9, 21, 55, 100, 200\}$$

Determinar la dirección predominante D = SLOPE_DIRECTION(t).

Contar EMAs cuya pendiente concuerda con D:

$$\text{sync\_count}(t) = \sum_{n \in \{9,21,55,100,200\}} \mathbb{1}\left[\text{sgn}(\text{SLOPE}_n(t)) = \text{sgn}(D)\right]$$

Donde sgn(UP) = +1, sgn(DOWN) = -1. Si D = NEUTRAL, sync\_count = 0.

$$\text{SLOPE\_SYNC}(t) = \frac{\text{sync\_count}(t)}{5} \times 100$$

**Interpretación:**
- 100% → todas las EMAs apuntan en la misma dirección → máxima coherencia direccional
- 60% → 3 de 5 EMAs alineadas → coherencia parcial
- 0% → ninguna EMA alinea con la dirección predominante (solo cuando D=NEUTRAL)

#### Pseudocódigo

```
INPUT:  EMA_9[t], EMA_21[t], EMA_55[t], EMA_100[t], EMA_200[t],
        EMA_9[t-1], EMA_21[t-1], EMA_55[t-1], EMA_100[t-1], EMA_200[t-1],
        SLOPE_DIRECTION[t]
OUTPUT: SLOPE_SYNC[t]   // float, % [0, 100]
REQUIRES: F-005, F-009

emas   = [9, 21, 55, 100, 200]
slopes = {}

FOR n IN emas:
    slopes[n] = ((EMA_n[t] - EMA_n[t-1]) / EMA_n[t-1]) * 100

IF SLOPE_DIRECTION[t] == "NEUTRAL":
    RETURN 0.0

direction_sign = +1 IF SLOPE_DIRECTION[t] == "UP" ELSE -1
sync_count = 0

FOR n IN emas:
    IF SIGN(slopes[n]) == direction_sign:
        sync_count += 1

SLOPE_SYNC[t] = (sync_count / 5) * 100

RETURN SLOPE_SYNC[t]
```

---

### F-019 — Sincronía Multi-Timeframe (MTF_SYNC)

**Variable producida:** `MTF_SYNC` (V-L2-021)
**Propiedad:** PR-01 Dirección / Entidad EN-10 Coherencia
**Tipo:** Porcentaje de acuerdo entre timeframes [0, 100]
**Estado:** ARQUITECTURA DEFINIDA — IMPLEMENTACIÓN FASE VII

#### Notación matemática

Sea $\mathcal{T}$ el conjunto de timeframes activos (ej. {1h, 4h, 1d, 1w}).

Para cada timeframe $\tau \in \mathcal{T}$, el modelo produce un STRUCTURAL_STATE:

$$SS_\tau(t) = \text{STRUCTURAL\_STATE computado en timeframe } \tau$$

Determinar el estado predominante:

$$SS^*(t) = \text{MODE}\{SS_\tau(t) : \tau \in \mathcal{T}\}$$

Contar timeframes que coinciden con el estado predominante:

$$\text{MTF\_SYNC}(t) = \frac{|\{\tau \in \mathcal{T} : SS_\tau(t) = SS^*(t)\}|}{|\mathcal{T}|} \times 100$$

#### Pseudocódigo

```
// IMPLEMENTACIÓN PENDIENTE — FASE VII
// Requiere múltiples instancias del modelo en paralelo

INPUT:  STRUCTURAL_STATE[t, τ]   // para cada timeframe τ en T
PARAM:  T = [timeframes activos]   // ej. ["1h", "4h", "1d", "1w"]
OUTPUT: MTF_SYNC[t]               // float, % [0, 100]
REQUIRES: F-002 (en cada timeframe)

states = [STRUCTURAL_STATE[t, tau] FOR tau IN T]
predominant = MODE(states)
matching = COUNT(s FOR s IN states IF s == predominant)
MTF_SYNC[t] = (matching / LEN(T)) * 100

RETURN MTF_SYNC[t]

// Nota arquitectural: la arquitectura paramétrica del EIM
// (TIMEFRAME como metadato de cada observación) soporta
// nativamente esta implementación. Ver EIM-EAR-001 § temporality.
```

---

# BLOQUE 10 — VARIABLES COMPUESTAS
## Fórmulas F-011, F-012

---

### F-011 — Puntaje de Coherencia (COHERENCE_SCORE)

**Variable producida:** `COHERENCE_SCORE` (V-L3-004)
**Entidad:** EN-10 Coherencia
**Tipo:** Score ponderado emergente [0, 10]
**Naturaleza:** EMERGENT — no reducible a ninguna variable individual

#### Notación matemática

Componentes y pesos:

| Componente | Variable | Peso | Normalización |
|---|---|---|---|
| C1 — Stack Score | STACK_SCORE | 0.30 | Ya en [0,10] |
| C2 — Precio vs Stack | PRICE_VS_STACK | 0.30 | × 2 → [0,10] |
| C3 — Sincronía pendientes | SLOPE_SYNC | 0.20 | ÷ 10 → [0,10] |
| C4 — Volumen | VOLUME_RATIO | 0.10 | min(VR, 3) × 10/3 → [0,10] |
| C5 — Rebotes EMA-55 | BOUNCE_COUNT_55 | 0.10 | min(BC, 10) → [0,10] |

$$C_2^{norm} = \text{PRICE\_VS\_STACK} \times 2$$

$$C_3^{norm} = \frac{\text{SLOPE\_SYNC}}{10}$$

$$C_4^{norm} = \min\left(\text{VOLUME\_RATIO},\ 3\right) \times \frac{10}{3}$$

$$C_5^{norm} = \min\left(\text{BOUNCE\_COUNT}_{55},\ 10\right)$$

$$\text{COHERENCE\_SCORE}(t) = 0.30 \cdot \text{STACK\_SCORE} + 0.30 \cdot C_2^{norm} + 0.20 \cdot C_3^{norm} + 0.10 \cdot C_4^{norm} + 0.10 \cdot C_5^{norm}$$

**Interpretación:**
- CS ≥ 8.0 → mercado altamente coherente → diagnóstico de alta confianza
- CS ∈ [5.0, 8.0) → coherencia moderada → diagnóstico válido con reservas
- CS < 5.0 → baja coherencia → señales contradictorias → diagnóstico de baja confianza

#### Pseudocódigo

```
INPUT:  STACK_SCORE[t], PRICE_VS_STACK[t], SLOPE_SYNC[t],
        VOLUME_RATIO[t], BOUNCE_COUNT_55[t]
OUTPUT: COHERENCE_SCORE[t]   // float [0, 10]
REQUIRES: F-003, F-004, F-018, F-008, F-020

C1 = STACK_SCORE[t]                               // ya en [0, 10]
C2 = PRICE_VS_STACK[t] * 2                        // [0,5] → [0,10]
C3 = SLOPE_SYNC[t] / 10                           // [0,100] → [0,10]
C4 = MIN(VOLUME_RATIO[t], 3) * (10 / 3)           // cap en 3x → [0,10]
C5 = MIN(BOUNCE_COUNT_55[t], 10)                  // cap en 10 → [0,10]

COHERENCE_SCORE[t] = 0.30*C1 + 0.30*C2 + 0.20*C3 + 0.10*C4 + 0.10*C5

RETURN COHERENCE_SCORE[t]
```

---

### F-012 — Índice de Fricción (FRICTION_INDEX)

**Variable producida:** `FRICTION_INDEX` (V-L3-005)
**Entidad:** EN-09 Fricción
**Tipo:** Índice ponderado [0, 10]

#### Notación matemática

La fricción es alta cuando el mercado está comprimido, el precio no se aleja del equilibrio, el volumen es bajo y la volatilidad es baja. Es la resistencia estructural al movimiento.

| Componente | Variable | Peso | Normalización |
|---|---|---|---|
| F1 — Compresión | COMPRESSION_INDEX | 0.35 | Invertido: 10 - min(CI×10, 10) |
| F2 — Elasticidad baja | ELASTICITY | 0.25 | 10 - min(|ELAST|, 10) |
| F3 — Volumen bajo | VOLUME_RATIO | 0.20 | Invertido: 10 - C4_norm |
| F4 — Duración compresión | COMPRESSION_DURATION | 0.10 | min(CD/5, 10) |
| F5 — Volatilidad baja | ATR_RELATIVE | 0.10 | Invertido: 10 - min(ATR×10, 10) |

$$F_1^{norm} = 10 - \min(\text{CI} \times 10,\ 10)$$

$$F_2^{norm} = 10 - \min(|\text{ELASTICITY}|,\ 10)$$

$$F_3^{norm} = 10 - \min\left(\text{VOLUME\_RATIO},\ 3\right) \times \frac{10}{3}$$

$$F_4^{norm} = \min\left(\frac{\text{COMPRESSION\_DURATION}}{5},\ 10\right)$$

$$F_5^{norm} = 10 - \min(\text{ATR\_RELATIVE} \times 10,\ 10)$$

$$\text{FRICTION\_INDEX}(t) = 0.35 \cdot F_1 + 0.25 \cdot F_2 + 0.20 \cdot F_3 + 0.10 \cdot F_4 + 0.10 \cdot F_5$$

**Interpretación:**
- FI ≥ 8.0 → fricción máxima → mercado con alta resistencia al movimiento
- FI ∈ [4.0, 8.0) → fricción moderada
- FI < 4.0 → baja fricción → mercado con energía para moverse

#### Pseudocódigo

```
INPUT:  COMPRESSION_INDEX[t], ELASTICITY[t], VOLUME_RATIO[t],
        COMPRESSION_DURATION[t], ATR_RELATIVE[t]
OUTPUT: FRICTION_INDEX[t]   // float [0, 10]
REQUIRES: F-010, F-007, F-008, F-017, F-022

F1 = 10 - MIN(COMPRESSION_INDEX[t] * 10, 10)     // CI bajo → alta fricción
F2 = 10 - MIN(ABS(ELASTICITY[t]), 10)            // elasticidad baja → alta fricción
F3 = 10 - MIN(VOLUME_RATIO[t], 3) * (10/3)       // volumen bajo → alta fricción
F4 = MIN(COMPRESSION_DURATION[t] / 5, 10)        // más tiempo comprimido → más fricción
F5 = 10 - MIN(ATR_RELATIVE[t] * 10, 10)          // volatilidad baja → alta fricción

FRICTION_INDEX[t] = 0.35*F1 + 0.25*F2 + 0.20*F3 + 0.10*F4 + 0.10*F5

RETURN FRICTION_INDEX[t]
```

---

# APÉNDICE A — Orden de Cálculo

El siguiente orden garantiza que toda variable esté disponible cuando es requerida por otra.

```
PASO 1 — Observables (L0)
  PRICE_CLOSE, VOLUME, TIMESTAMP, TIMEFRAME

PASO 2 — Instrumentos (L1) — F-001
  EMA_9, EMA_21, EMA_55, EMA_100, EMA_200

PASO 3 — Propiedades de posición y pendiente (L2, grupo A)
  F-002  → STACK_ORDER
  F-003  → STACK_SCORE
  F-004  → PRICE_VS_STACK
  F-005  → SLOPE_9, SLOPE_55
  F-006  → SPREAD_9_21, SPREAD_21_55, SPREAD_55_100, SPREAD_100_200
  F-007  → ELASTICITY
  F-008  → VOLUME_RATIO
  F-009  → SLOPE_DIRECTION

PASO 4 — Propiedades derivadas (L2, grupo B)
  F-010  → COMPRESSION_INDEX        (requiere F-006)
  F-015  → CURVATURE_9, CURVATURE_55 (requiere F-005)
  F-016  → PERSISTENCE_ABOVE_21     (requiere F-001)
  F-020  → BOUNCE_COUNT_9/21/55/200 (requiere F-001)
  F-021  → CROSS_EVENT_9_21/21_55/55_200 (requiere F-001, F-002)
  F-022  → ATR_RELATIVE             (requiere HIGH, LOW)

PASO 5 — Propiedades de segunda derivada (L2, grupo C)
  F-013  → SPREAD_VELOCITY          (requiere F-010)
  F-017  → COMPRESSION_DURATION     (requiere F-010)
  F-018  → SLOPE_SYNC               (requiere F-005, F-009)

PASO 6 — Tercera derivada
  F-014  → SPREAD_ACCELERATION      (requiere F-013)

PASO 7 — Variables compuestas L3
  F-019  → MTF_SYNC                 (requiere STRUCTURAL_STATE de múltiples TF)
  F-011  → COHERENCE_SCORE          (requiere F-003, F-004, F-018, F-008, F-020)
  F-012  → FRICTION_INDEX           (requiere F-010, F-007, F-008, F-017, F-022)

PASO 8 — Estados L3 (via BRM — EIM-BRM-001)
  R-001  → STRUCTURAL_STATE
  R-002  → MOMENTUM_STATE
  R-003  → ENERGY_STATE

PASO 9 — Diagnóstico L4 (via IRM — EIM-IRM-001)
  DIAG-001 → STRUCTURAL_DIAGNOSIS
```

---

# APÉNDICE B — Tabla de Referencia Rápida

| Código | Variable | Tipo | Fórmula base | Nivel | Requiere |
|---|---|---|---|---|---|
| F-001 | EMA_n | Recursiva | α·P + (1-α)·EMA_prev | L1 | PRICE_CLOSE |
| F-002 | STACK_ORDER | Clasificación | Conteo pares ordenados | L2 | F-001 |
| F-003 | STACK_SCORE | Puntuación | bull_pairs × 2.5 | L2 | F-002 |
| F-004 | PRICE_VS_STACK | Conteo | ΣI[P > EMAn] | L2 | F-001 |
| F-005 | SLOPE_n | Tasa cambio | (EMA_t - EMA_t-1)/EMA_t-1 × 100 | L2 | F-001 |
| F-006 | SPREAD | Distancia relativa | (EMA_fast - EMA_slow)/EMA_slow × 100 | L2 | F-001 |
| F-007 | ELASTICITY | Distancia precio-equilibrio | (P - EMA200)/EMA200 × 100 | L2 | F-001 |
| F-008 | VOLUME_RATIO | Ratio | V / V_avg_N | L2 | VOLUME |
| F-009 | SLOPE_DIRECTION | Clasificación | Acuerdo SLOPE_9 y SLOPE_55 | L2 | F-005 |
| F-010 | COMPRESSION_INDEX | Índice | Promedio spreads absolutos | L2 | F-006 |
| F-011 | COHERENCE_SCORE | Score emergente | Composición ponderada 5 vars | L3 | F-003,004,018,008,020 |
| F-012 | FRICTION_INDEX | Índice | Composición ponderada 5 vars | L3 | F-010,007,008,017,022 |
| F-013 | SPREAD_VELOCITY | Derivada 1ª | CI_t - CI_t-1 | L2 | F-010 |
| F-014 | SPREAD_ACCELERATION | Derivada 2ª | SV_t - SV_t-1 | L2 | F-013 |
| F-015 | CURVATURE_n | Derivada pendiente | SLOPE_t - SLOPE_t-1 | L2 | F-005 |
| F-016 | PERSISTENCE_ABOVE_21 | Contador con signo | Velas consecutivas sobre EMA-21 | L2 | F-001 |
| F-017 | COMPRESSION_DURATION | Contador | Velas en CI ≤ θ | L2 | F-010 |
| F-018 | SLOPE_SYNC | % acuerdo | EMAs alineadas / 5 × 100 | L2 | F-005,009 |
| F-019 | MTF_SYNC | % acuerdo TF | Estados coincidentes / TF × 100 | L2 | Fase VII |
| F-020 | BOUNCE_COUNT_n | Conteo eventos | Rebotes en ventana N | L2 | F-001 |
| F-021 | CROSS_EVENT | Objeto evento | Cruce + dirección + magnitud + contexto | L2 | F-001,002 |
| F-022 | ATR_RELATIVE | Volatilidad | ATR14 / P × 100 | L2 | HIGH, LOW |

---

*Fin del documento EIM-FRM-001 v1.0.0*
