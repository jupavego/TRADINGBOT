# EIM-VRM-001
# Validation Repository
# Protocolo de Backtesting y Calibración

---

| Campo | Valor |
|---|---|
| **Código** | EIM-VRM-001 |
| **Nombre** | Validation Repository — Protocolo de Backtesting y Calibración |
| **Repositorio** | VRM |
| **Proyecto** | EMA Intelligence Model (EIM) |
| **Versión** | 1.0.0 |
| **Estado** | ACTIVE |
| **Fecha** | 2026-06-27 |
| **Dependencias** | MSI-META-001, EIM-FRM-001, EIM-BRM-001, EIM-IRM-001 |

---

## Historial de Cambios

| Versión | Fecha | Descripción |
|---|---|---|
| 1.0.0 | 2026-06-27 | Creación. Protocolo completo: 4 fases de validación, 22 parámetros calibrables, 8 métricas de evaluación, diseño de dataset, procedimiento de calibración iterativa y criterios de aceptación. |

---

## Propósito

Este documento define el **protocolo formal de validación** del EIM.

La validación tiene dos objetivos distintos que no deben confundirse:

**Objetivo 1 — Calibración:** Determinar los valores óptimos de los 22 parámetros provisionales definidos en BRM e IRM mediante análisis estadístico de datos históricos.

**Objetivo 2 — Evaluación:** Medir la calidad diagnóstica del modelo una vez calibrado, usando métricas formales sobre un conjunto de datos de prueba independiente.

Un modelo calibrado pero no evaluado no es un modelo validado. Un modelo evaluado sin calibración produce métricas sobre parámetros arbitrarios. Ambos procesos son obligatorios.

---

## Advertencia epistemológica

El EIM produce **diagnósticos de estado estructural**, no predicciones de precio. La validación debe medir la calidad del diagnóstico, no la rentabilidad de trading.

La pregunta correcta de validación es:

> "¿Cuando el modelo diagnostica TREND_STRONG con escenario CONTINUATION, el mercado efectivamente mantuvo esa estructura en las N velas siguientes?"

No:

> "¿Cuando el modelo diagnóstica CONTINUATION, el precio subió?"

Esta distinción es fundamental. Un mercado puede estar en TREND_STRONG CONTINUATION bajista — el diagnóstico es correcto aunque el precio caiga.

---

# PARTE I — DATASET DE VALIDACIÓN

---

## Capítulo 1 — Especificación del Dataset

### 1.1 Instrumentos

| Instrumento | Justificación |
|---|---|
| BTC-USDT Perpetual | Mayor liquidez y profundidad histórica en crypto futuros |
| ETH-USDT Perpetual | Segunda mayor capitalización — comportamiento estructural diferenciado |
| BTC-USDT Quarterly | Futuros con fecha de vencimiento — dinámica de basis distinta |

La inclusión de múltiples instrumentos garantiza que el modelo no esté sobreajustado a las particularidades de un solo par.

### 1.2 Timeframes

| Timeframe | Rol en validación |
|---|---|
| 1h | Calibración de umbrales de momentum (θ-004, θ-005) |
| 4h | Timeframe primario de calibración y evaluación |
| 1d | Calibración de umbrales estructurales (θ-001, θ-002, θ-003) |

### 1.3 Período temporal

```
Dataset completo: mínimo 4 años de datos OHLCV
Partición:
  ├── Training set:    60% (calibración de parámetros)
  ├── Validation set:  20% (ajuste fino y detección de overfitting)
  └── Test set:        20% (evaluación final — NO tocar hasta calibración completa)

Criterio adicional: el dataset debe incluir al menos:
  - 1 mercado alcista sostenido (> 3 meses)
  - 1 mercado bajista sostenido (> 3 meses)
  - 2 episodios de alta compresión seguidos de ruptura
  - 1 cambio estructural macro (cruce EMA-55/200)
```

### 1.4 Calidad de datos requerida

| Requisito | Criterio |
|---|---|
| Completitud | < 0.1% de velas faltantes |
| Consistencia OHLC | H >= max(O,C), L <= min(O,C) en toda vela |
| Volumen | Volumen > 0 en todas las velas |
| Warmup | Primeras 400 velas excluidas del análisis (requisito EMA-200) |
| Fuente | Exchange primario — no datos de agregadores para evitar discrepancias |

---

# PARTE II — PARÁMETROS A CALIBRAR

---

## Capítulo 2 — Inventario de Parámetros

El EIM tiene 22 parámetros calibrables organizados en tres grupos según su impacto en el sistema.

### Grupo A — Umbrales BRM (Impacto: clasificación de estados)

Estos parámetros determinan qué estado se asigna a cada observación. Son los de mayor impacto en el sistema — un umbral mal calibrado afecta todos los diagnósticos subsiguientes.

| ID | Parámetro | Valor provisional | Variable asociada | Rango de búsqueda |
|---|---|---|---|---|
| θ-001 | Umbral compresión CI | 0.50% | COMPRESSION_INDEX | [0.20, 1.50] |
| θ-002 | Umbral expansión CI | 2.00% | COMPRESSION_INDEX | [1.00, 5.00] |
| θ-003 | Umbral elasticidad | 5.00% | ELASTICITY | [2.00, 15.00] |
| θ-004 | Velocidad estable | 0.05 pts/vela | SPREAD_VELOCITY | [0.01, 0.20] |
| θ-005 | Curvatura plana | 0.02 %/vela | CURVATURE_n | [0.005, 0.10] |
| θ-006 | Duración mín. compresión | 5 velas | COMPRESSION_DURATION | [2, 15] |
| θ-007 | Persistencia mín. tendencia | 3 velas | PERSISTENCE_ABOVE_21 | [2, 10] |

### Grupo B — Pesos IRM (Impacto: conviction score)

Estos parámetros determinan cuánto pesa cada estado L3 en el score de convicción final. Impacto alto pero localizado en la Etapa 1 del IRM.

| ID | Parámetro | Valor provisional | Restricción |
|---|---|---|---|
| W-001 | Peso STRUCTURAL_STATE | 0.30 | Suma de todos los pesos = 1.0 |
| W-002 | Peso MOMENTUM_STATE | 0.25 | ≥ 0.10 cada uno |
| W-003 | Peso ENERGY_STATE | 0.20 | W-001 ≥ W-002 ≥ W-003 |
| W-004 | Peso COHERENCE_SCORE | 0.15 | (orden estructural) |
| W-005 | Peso FRICTION_INDEX | 0.10 | |

### Grupo C — Modificadores IRM (Impacto: confidence score)

Estos parámetros ajustan la confianza del diagnóstico. Impacto menor que los grupos A y B — afectan la calibración de confianza, no la clasificación del estado.

| ID | Parámetro | Valor provisional | Modificador |
|---|---|---|---|
| MC-001 | Delta MTF_SYNC alto (≥75%) | +10 | M-001 |
| MC-002 | Delta MTF_SYNC medio (50-75%) | +5 | M-001 |
| MC-003 | Delta MTF_SYNC bajo (<25%) | -15 | M-001 |
| MC-004 | Delta BOUNCE_COUNT_200 ≥ 5 | +8 | M-002 |
| MC-005 | Delta BOUNCE_COUNT_200 = 0 | -5 | M-002 |
| MC-006 | Delta fricción alta en BREAKOUT | -10 | M-004 |
| MC-007 | Delta convicción extrema | +8 | M-005 |
| MC-008 | Delta convicción neutral | -8 | M-005 |
| MC-009 | Delta COMPRESSED + BREAKOUT | +10 | M-006 |
| MC-010 | Delta LOW_ENERGY + CONTINUATION | -8 | M-006 |

---

# PARTE III — MÉTRICAS DE EVALUACIÓN

---

## Capítulo 3 — Métricas de Calidad del Diagnóstico

### 3.1 Definición del Horizonte de Evaluación

Cada diagnóstico se evalúa contra el **comportamiento observado** en las N velas siguientes al momento del diagnóstico.

```
Horizonte de evaluación H:
  1h  timeframe → H = 12 velas (12 horas)
  4h  timeframe → H = 6 velas  (24 horas)
  1d  timeframe → H = 5 velas  (5 días)
```

### 3.2 Definición de Diagnóstico Correcto

Un diagnóstico se considera **correcto** si el estado estructural observado en las H velas siguientes es consistente con el escenario diagnosticado:

| Escenario diagnosticado | Criterio de corrección |
|---|---|
| SC-01 CONTINUATION | STRUCTURAL_STATE se mantiene igual o adyacente en H velas |
| SC-02 BREAKOUT | COMPRESSION_INDEX aumenta > θ-002 en las primeras H/2 velas |
| SC-03 PULLBACK | Precio toca EMA-21 o EMA-55 en H velas y retoma dirección |
| SC-04 STRUCTURAL_CHANGE | STRUCTURAL_STATE cambia a estado no adyacente en H velas |
| SC-05 CONSOLIDATION | STRUCTURAL_STATE permanece en DIVERGENT u ORDERED con baja convicción |

### 3.3 Métricas Formales

#### MET-001 — Accuracy Global

$$\text{Accuracy} = \frac{\text{diagnósticos correctos}}{\text{total diagnósticos}} \times 100$$

**Umbral de aceptación:** Accuracy ≥ 60% en test set.
**Justificación:** Un modelo aleatorio tendría ~20% (5 escenarios). 60% representa capacidad predictiva real.

#### MET-002 — Accuracy por Escenario

$$\text{Accuracy}_{SC_i} = \frac{\text{correctos en }SC_i}{\text{total diagnósticos }SC_i} \times 100$$

**Umbral de aceptación:** Accuracy ≥ 55% en cada escenario individualmente.
**Importancia:** Detecta si el modelo está acertando en escenarios frecuentes y fallando en los raros.

#### MET-003 — Precision y Recall por Estado Estructural

Para cada estado E-01 a E-07:

$$\text{Precision}_E = \frac{TP_E}{TP_E + FP_E}$$

$$\text{Recall}_E = \frac{TP_E}{TP_E + FN_E}$$

$$\text{F1}_E = 2 \times \frac{\text{Precision}_E \times \text{Recall}_E}{\text{Precision}_E + \text{Recall}_E}$$

**Umbral de aceptación:** F1 ≥ 0.50 en estados E-01, E-03, E-05 (los de mayor impacto diagnóstico).

#### MET-004 — Calibración del Confidence Score

El confidence_score debe estar bien calibrado: un diagnóstico con confidence 80% debe ser correcto aproximadamente el 80% de las veces.

$$\text{Calibration Error} = \frac{1}{B} \sum_{b=1}^{B} \left| \text{Accuracy}(b) - \overline{\text{confidence}}(b) \right|$$

Donde B = 10 bins de 10% cada uno (0-10%, 10-20%, ..., 90-95%).

**Umbral de aceptación:** Calibration Error ≤ 0.10 (10% de desviación promedio).

#### MET-005 — Estabilidad del Diagnóstico

Un diagnóstico estable no debe cambiar entre velas consecutivas sin que haya un cambio estructural real.

$$\text{Stability} = 1 - \frac{\text{cambios de diagnóstico sin cambio estructural}}{\text{total de velas}}$$

**Umbral de aceptación:** Stability ≥ 0.85 (máximo 15% de cambios espurios).

#### MET-006 — Cobertura de Estados

El modelo debe diagnosticar todos los estados, no solo los frecuentes.

$$\text{Coverage} = \frac{\text{estados diagnosticados al menos una vez}}{7} \times 100$$

**Umbral de aceptación:** Coverage = 100% en el training set.

#### MET-007 — Consistencia Temporal

El modelo debe producir diagnósticos coherentes en distintos timeframes para el mismo instrumento en el mismo momento.

$$\text{Cross-TF Consistency} = \frac{\text{diagnósticos compatibles entre 1h, 4h y 1d}}{\text{total de observaciones comunes}} \times 100$$

**Umbral de aceptación:** Cross-TF Consistency ≥ 65%.

#### MET-008 — Latencia de Detección

Para estados con cambio estructural (BREAKOUT, STRUCTURAL_CHANGE): cuántas velas tarda el modelo en detectar el cambio una vez que ocurrió.

$$\text{Detection Latency} = \text{mediana}(\text{velas hasta diagnóstico correcto tras cambio real})$$

**Umbral de aceptación:** Detection Latency ≤ 3 velas en timeframe 4h.

---

# PARTE IV — PROTOCOLO DE CALIBRACIÓN

---

## Capítulo 4 — Procedimiento de Calibración

La calibración se ejecuta en tres fases secuenciales. Los grupos de parámetros se calibran en orden de impacto decreciente.

### Fase C-1 — Calibración de Umbrales BRM (Grupo A)

**Objetivo:** Encontrar los valores de θ-001 a θ-007 que maximizan la consistencia de la clasificación de estados con el comportamiento histórico observado.

**Método:** Grid Search con validación cruzada temporal.

```
ALGORITMO C-1:

PARA cada instrumento IN {BTC-PERP, ETH-PERP}:
  PARA cada timeframe IN {4h, 1d}:

    // Definir grilla de búsqueda
    grilla = {
      θ-001: [0.20, 0.35, 0.50, 0.75, 1.00, 1.50],
      θ-002: [1.00, 1.50, 2.00, 3.00, 4.00, 5.00],
      θ-003: [2.00, 3.50, 5.00, 7.50, 10.0, 15.0],
      θ-004: [0.01, 0.03, 0.05, 0.10, 0.15, 0.20],
      θ-005: [0.005, 0.010, 0.020, 0.050, 0.100],
      θ-006: [2, 3, 5, 7, 10, 15],
      θ-007: [2, 3, 5, 7, 10]
    }

    // Validación cruzada temporal (5-fold)
    PARA cada combinación en grilla:
      scores = []
      PARA cada fold IN 5-fold-temporal:
        ejecutar_pipeline_completo(training_fold, θ_actual)
        score = calcular_MET001(validation_fold)
        scores.append(score)
      media_score = MEAN(scores)
      registrar(θ_actual, media_score)

    // Seleccionar mejor combinación
    θ_optimo = combinación con mayor media_score
    verificar en validation_set

RESULTADO: θ-001 a θ-007 calibrados por instrumento y timeframe
```

**Nota sobre Grid Search:** Con 7 parámetros y las grillas definidas, el espacio total es ~46,656 combinaciones. Computacionalmente manejable en Python con vectorización. Tiempo estimado: 2-4 horas en hardware estándar.

### Fase C-2 — Calibración de Pesos IRM (Grupo B)

**Objetivo:** Encontrar los pesos W-001 a W-005 que maximizan MET-001 (Accuracy Global) y MET-004 (Calibración de Confidence).

**Restricciones:**
- Suma de pesos = 1.0
- W-001 ≥ W-002 ≥ W-003 (orden de importancia estructural)
- Cada peso ≥ 0.05

**Método:** Optimización por Simplex (Nelder-Mead) sobre el simplex de probabilidades.

```
ALGORITMO C-2:

// Función objetivo: maximizar Accuracy + penalizar mala calibración
f(W) = MET-001(W) - λ * MET-004_error(W)

// λ = 0.5 (peso relativo calibración vs accuracy)

// Condiciones de frontera:
// sum(W) = 1.0
// W_i >= 0.05 para todo i
// W[0] >= W[1] >= W[2]

OPTIMIZAR f(W) con Nelder-Mead sobre training set
VALIDAR resultado en validation set
VERIFICAR que MET-001 no degrada > 2% vs training (overfitting check)

RESULTADO: W-001 a W-005 calibrados
```

### Fase C-3 — Calibración de Modificadores Confidence (Grupo C)

**Objetivo:** Calibrar MC-001 a MC-010 para minimizar el Calibration Error (MET-004).

**Método:** Regresión isotónica sobre el confidence score base.

```
ALGORITMO C-3:

// Para cada bin de confidence [0-10%, 10-20%, ..., 90-95%]:
PARA cada bin b:
    observaciones_b = diagnósticos con confidence ∈ bin_b
    accuracy_real_b = fracción de diagnósticos correctos en bin_b
    delta_b = accuracy_real_b - midpoint(bin_b)

// Los modificadores se ajustan para que:
// E[confidence_ajustado | bin_b] ≈ accuracy_real_b

// Isotonic regression garantiza la condición:
// confidence_ajustado es monotónicamente creciente

RESULTADO: MC-001 a MC-010 ajustados
VERIFICAR: MET-004 ≤ 0.10 en validation set
```

---

## Capítulo 5 — Protocolo Anti-Overfitting

El overfitting en modelos de diagnóstico de mercados es especialmente peligroso porque los mercados tienen régimen-dependencia — un modelo calibrado en un mercado alcista puede fallar completamente en uno bajista.

### Reglas anti-overfitting

**AO-001 — Separación temporal estricta:**
El test set nunca se usa durante calibración. Solo se abre una vez, al final, para la evaluación final. Viola este principio y la evaluación es inválida.

**AO-002 — Validación en régimen adverso:**
El modelo debe evaluarse explícitamente en el subconjunto del dataset que corresponde al régimen opuesto al de calibración (si se calibró principalmente en alcista, evaluar en bajista y viceversa).

```
Accuracy_adverso = Accuracy calculado en régimen opuesto al de calibración
Umbral: Accuracy_adverso >= Accuracy_global * 0.80
// El modelo no puede degradar más de un 20% en régimen adverso
```

**AO-003 — Estabilidad de parámetros:**
Los parámetros calibrados en BTC-PERP deben producir Accuracy ≥ 55% en ETH-PERP sin re-calibración. Si no, el modelo está sobreajustado al instrumento.

**AO-004 — Walk-forward validation:**
Tras la calibración inicial, ejecutar walk-forward validation para confirmar que los parámetros son robustos en el tiempo:

```
WALK-FORWARD:
  Ventana de calibración: 12 meses
  Ventana de test: 3 meses
  Paso: 3 meses
  Repeticiones: mínimo 8

  Resultado esperado: Accuracy promedio walk-forward
                      dentro de ±5% del Accuracy en test set
```

---

## Capítulo 6 — Criterios de Aceptación Global

El modelo se considera **validado** si cumple TODOS los siguientes criterios simultáneamente:

| ID | Métrica | Umbral | Criticidad |
|---|---|---|---|
| CA-001 | MET-001 Accuracy Global | ≥ 60% | BLOQUEANTE |
| CA-002 | MET-002 Accuracy por Escenario | ≥ 55% en cada uno | BLOQUEANTE |
| CA-003 | MET-003 F1 estados críticos | ≥ 0.50 en E-01, E-03, E-05 | BLOQUEANTE |
| CA-004 | MET-004 Calibration Error | ≤ 0.10 | BLOQUEANTE |
| CA-005 | MET-005 Stability | ≥ 0.85 | BLOQUEANTE |
| CA-006 | MET-006 Coverage | = 100% | BLOQUEANTE |
| CA-007 | MET-007 Cross-TF Consistency | ≥ 65% | ADVERTENCIA |
| CA-008 | MET-008 Detection Latency | ≤ 3 velas (4h) | ADVERTENCIA |
| CA-009 | AO-002 Accuracy adverso | ≥ Accuracy_global × 0.80 | BLOQUEANTE |
| CA-010 | AO-003 Cross-instrument | ≥ 55% en ETH sin re-calibración | ADVERTENCIA |

**Criterios BLOQUEANTES:** Si no se cumple, el modelo NO puede avanzar a Fase VII.
**Criterios ADVERTENCIA:** Si no se cumple, debe documentarse y re-evaluarse en v1.1.

---

# PARTE V — REPORTE DE VALIDACIÓN

---

## Capítulo 7 — Estructura del Reporte

Cada ejecución del protocolo de validación produce un **Reporte de Validación** con la siguiente estructura:

### Sección 1 — Metadatos

```json
{
  "report_code": "EIM-VRM-001-RPT-001",
  "date": "YYYY-MM-DD",
  "model_versions": {
    "FRM": "EIM-FRM-001 v1.0.0",
    "BRM": "EIM-BRM-001 v1.0.0",
    "IRM": "EIM-IRM-001 v1.0.0"
  },
  "dataset": {
    "instruments": ["BTC-USDT-PERP", "ETH-USDT-PERP"],
    "timeframes": ["1h", "4h", "1d"],
    "period": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
    "total_observations": 0,
    "warmup_excluded": 400
  }
}
```

### Sección 2 — Parámetros calibrados

```json
{
  "thresholds_calibrated": {
    "θ-001": {"provisional": 0.50, "calibrated": null, "instrument": "BTC-PERP", "timeframe": "4h"},
    "θ-002": {"provisional": 2.00, "calibrated": null},
    "θ-003": {"provisional": 5.00, "calibrated": null},
    "θ-004": {"provisional": 0.05, "calibrated": null},
    "θ-005": {"provisional": 0.02, "calibrated": null},
    "θ-006": {"provisional": 5,    "calibrated": null},
    "θ-007": {"provisional": 3,    "calibrated": null}
  },
  "weights_calibrated": {
    "W-001": {"provisional": 0.30, "calibrated": null},
    "W-002": {"provisional": 0.25, "calibrated": null},
    "W-003": {"provisional": 0.20, "calibrated": null},
    "W-004": {"provisional": 0.15, "calibrated": null},
    "W-005": {"provisional": 0.10, "calibrated": null}
  }
}
```

### Sección 3 — Métricas de evaluación

```json
{
  "metrics": {
    "MET-001_accuracy_global": null,
    "MET-002_accuracy_by_scenario": {
      "SC-01": null, "SC-02": null, "SC-03": null,
      "SC-04": null, "SC-05": null
    },
    "MET-003_f1_by_state": {
      "E-01": null, "E-02": null, "E-03": null,
      "E-04": null, "E-05": null, "E-06": null, "E-07": null
    },
    "MET-004_calibration_error": null,
    "MET-005_stability": null,
    "MET-006_coverage": null,
    "MET-007_cross_tf_consistency": null,
    "MET-008_detection_latency_p50": null
  }
}
```

### Sección 4 — Criterios de aceptación

```json
{
  "acceptance_criteria": {
    "CA-001": {"threshold": 0.60, "result": null, "status": "PENDING"},
    "CA-002": {"threshold": 0.55, "result": null, "status": "PENDING"},
    "CA-003": {"threshold": 0.50, "result": null, "status": "PENDING"},
    "CA-004": {"threshold": 0.10, "result": null, "status": "PENDING"},
    "CA-005": {"threshold": 0.85, "result": null, "status": "PENDING"},
    "CA-006": {"threshold": 1.00, "result": null, "status": "PENDING"},
    "CA-007": {"threshold": 0.65, "result": null, "status": "PENDING"},
    "CA-008": {"threshold": 3,    "result": null, "status": "PENDING"},
    "CA-009": {"threshold": 0.80, "result": null, "status": "PENDING"},
    "CA-010": {"threshold": 0.55, "result": null, "status": "PENDING"}
  },
  "overall_status": "PENDING",
  "blocking_failures": [],
  "warnings": []
}
```

### Sección 5 — Análisis de fallo (si aplica)

Si algún criterio BLOQUEANTE no se cumple, el reporte debe incluir:

```
- Métrica fallida
- Valor obtenido vs umbral
- Diagnóstico de causa probable:
    A) Umbral mal calibrado → re-ejecutar Fase C-1
    B) Lógica de regla incorrecta → revisar BRM
    C) Fórmula incorrecta → revisar FRM
    D) Insuficiencia del modelo → revisar ONT (ampliar propiedades)
- Acción correctiva recomendada
- Documento afectado y versión siguiente
```

---

# PARTE VI — IMPLEMENTACIÓN EN PYTHON

---

## Capítulo 8 — Esqueleto de Implementación

El siguiente pseudocódigo define la estructura del script de backtesting. La implementación completa ocurre en Fase VII.

```python
# EIM Backtesting Engine — Esqueleto
# Implementación completa: EIM-VRM-001-RPT-001

import pandas as pd
import numpy as np
from itertools import product

class EIMBacktester:
    """
    Motor de backtesting para el EIM.
    Ejecuta el pipeline completo sobre datos históricos
    y produce el reporte de validación.
    """

    def __init__(self, data: pd.DataFrame, params: dict):
        """
        data:   DataFrame con columnas [timestamp, open, high, low, close, volume]
        params: diccionario con todos los parámetros calibrables (θ, W, MC)
        """
        self.data   = data
        self.params = params
        self.results = []

    def run_pipeline(self, row_idx: int) -> dict:
        """
        Ejecuta el pipeline completo para una observación.
        Orden: FRM → BRM → IRM → DIAG
        Returns: STRUCTURAL_DIAGNOSIS object
        """
        # PASO 1-6: FRM
        emas       = self._compute_emas(row_idx)
        l2_vars    = self._compute_l2(row_idx, emas)

        # PASO 7-8: BRM
        states     = self._classify_states(l2_vars)

        # PASO 9: IRM
        diagnosis  = self._run_inference(states, l2_vars)

        return diagnosis

    def _compute_emas(self, idx: int) -> dict:
        """ F-001: Calcula EMA_9, EMA_21, EMA_55, EMA_100, EMA_200 """
        # Implementación en Fase VII
        pass

    def _compute_l2(self, idx: int, emas: dict) -> dict:
        """ F-002 a F-022: Calcula todas las variables L2 """
        # Implementación en Fase VII
        pass

    def _classify_states(self, l2: dict) -> dict:
        """ R-001, R-002, R-003: Clasifica estados L3 """
        # Implementación en Fase VII
        pass

    def _run_inference(self, states: dict, l2: dict) -> dict:
        """ DIAG-001: Produce el diagnóstico estructural """
        # Implementación en Fase VII
        pass

    def evaluate(self, horizon: int = 6) -> dict:
        """
        Evalúa la calidad del diagnóstico.
        horizon: número de velas para evaluar el diagnóstico
        Returns: diccionario con todas las métricas MET-001 a MET-008
        """
        diagnoses   = []
        ground_truth = []

        for i in range(400, len(self.data) - horizon):
            diag = self.run_pipeline(i)
            actual = self._get_actual_state(i, horizon)
            diagnoses.append(diag)
            ground_truth.append(actual)

        return {
            "MET001": self._accuracy_global(diagnoses, ground_truth),
            "MET002": self._accuracy_by_scenario(diagnoses, ground_truth),
            "MET003": self._f1_by_state(diagnoses, ground_truth),
            "MET004": self._calibration_error(diagnoses, ground_truth),
            "MET005": self._stability(diagnoses),
            "MET006": self._coverage(diagnoses),
            "MET008": self._detection_latency(diagnoses, ground_truth)
        }

    def calibrate_thresholds(self, param_grid: dict) -> dict:
        """
        Grid Search para calibrar umbrales BRM.
        Returns: mejores parámetros encontrados
        """
        best_score  = 0
        best_params = {}

        keys   = list(param_grid.keys())
        values = list(param_grid.values())

        for combo in product(*values):
            params_test = dict(zip(keys, combo))
            self.params.update(params_test)
            metrics = self.evaluate()
            score   = metrics["MET001"]

            if score > best_score:
                best_score  = score
                best_params = params_test.copy()

        return best_params

    def _get_actual_state(self, idx: int, horizon: int) -> str:
        """
        Determina el estado estructural real observado
        en las 'horizon' velas siguientes al diagnóstico.
        """
        # Implementación en Fase VII
        pass
```

---

# APÉNDICE A — Checklist de validación

**Pre-validación:**
- [ ] Dataset descargado y verificado (< 0.1% valores faltantes)
- [ ] Partición training/validation/test creada sin solapamiento temporal
- [ ] Primeras 400 velas de warmup excluidas
- [ ] Pipeline completo FRM + BRM + IRM ejecutable end-to-end

**Durante calibración:**
- [ ] Fase C-1 completada (umbrales BRM)
- [ ] Fase C-2 completada (pesos IRM)
- [ ] Fase C-3 completada (modificadores confidence)
- [ ] Walk-forward validation ejecutado (mínimo 8 ventanas)
- [ ] Test set NO utilizado durante calibración

**Evaluación final:**
- [ ] Todas las métricas MET-001 a MET-008 calculadas en test set
- [ ] Criterios CA-001 a CA-010 evaluados
- [ ] Análisis de régimen adverso completado (AO-002)
- [ ] Cross-instrument check completado (AO-003)
- [ ] Reporte EIM-VRM-001-RPT-001 producido y archivado

**Criterio de paso a Fase VII:**
- [ ] TODOS los criterios BLOQUEANTES (CA-001 a CA-006, CA-009) en estado PASS
- [ ] BRM actualizado con parámetros calibrados (versión MINOR)
- [ ] IRM actualizado con pesos y modificadores calibrados (versión MINOR)

---

*Fin del documento EIM-VRM-001 v1.0.0*
