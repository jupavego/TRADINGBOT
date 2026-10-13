# MSI-META-001
# Market Structural Intelligence
# MetaModel Specification

---

| Campo | Valor |
|---|---|
| **Código** | MSI-META-001 |
| **Nombre** | MetaModel Specification |
| **Disciplina** | Market Structural Intelligence (MSI) |
| **Versión** | 1.0.0 |
| **Estado** | ACTIVE |
| **Fecha** | 2026-06-27 |
| **Nivel** | 0 — Constitución del sistema |
| **Dependencias** | Ninguna. Este documento no depende de ningún otro. |
| **Supersede** | N/A — documento fundacional |

---

## Historial de Cambios

| Versión | Fecha | Descripción |
|---|---|---|
| 1.0.0 | 2026-06-27 | Creación del documento fundacional. Definición de 7 meta-tipos, jerarquía de niveles, tipos de relaciones, restricciones, convenciones y principio de instanciación. |

---

## Advertencia de uso

Este documento es la **Constitución del MSI**.

Ningún repositorio, variable, fórmula, regla o implementación puede existir si contradice las definiciones aquí establecidas. Cualquier conflicto entre este documento y cualquier otro documento del proyecto se resuelve a favor de este documento.

Las modificaciones a este documento requieren incremento de versión MAJOR y revisión de todos los documentos dependientes.

---

# PARTE I — FUNDAMENTOS

---

## Capítulo 1 — Propósito y Alcance

### 1.1 Propósito

El MSI MetaModel Specification define el **lenguaje formal** de la disciplina Market Structural Intelligence.

No define variables. No define fórmulas. No define indicadores.

Define los **tipos de objetos** que pueden existir, los **tipos de relaciones** que pueden sostenerse entre ellos, y las **restricciones** que gobiernan su construcción.

Todo objeto concreto del proyecto EIM — cada variable, cada regla, cada entidad — es una **instancia** de un meta-tipo definido en este documento.

### 1.2 Posición en la jerarquía

El MSI MetaModel ocupa el **Nivel 0** de la arquitectura del sistema:

```
Nivel 0 — MSI MetaModel Specification     ← este documento
          (define el lenguaje y las reglas)
    ↓
Nivel 1 — Enterprise Architecture Repository (EAR)
          (instancia la arquitectura de un modelo concreto)
    ↓
Nivel 2 — Data Dictionary & Metadata Repository (DDMR)
          (instancia las variables del modelo)
    ↓
Nivel 3 — Formula Repository (FRM) / Business Rules Model (BRM)
          (instancia la operacionalización matemática)
    ↓
Nivel 4 — Inference Repository (IRM)
          (instancia la lógica de diagnóstico)
    ↓
Nivel 5 — Software / Implementación
          (instancia el sistema computacional)
```

### 1.3 Alcance

Este documento es **agnóstico al instrumento y al mercado**.

No menciona EMAs, futuros, criptomonedas ni ningún elemento concreto de implementación. Esos elementos pertenecen al Nivel 1 y siguientes.

Lo que aquí se define aplica a cualquier modelo que se construya bajo la disciplina MSI, ya sea sobre volumen, liquidez, order flow, volatilidad, o cualquier otro dominio de observación.

### 1.4 Definición de la disciplina

> **Market Structural Intelligence (MSI)** es la disciplina que estudia los mercados financieros como sistemas dinámicos mediante el análisis integrado de sus propiedades estructurales, temporales y emergentes, con el objetivo de producir diagnósticos cuantitativos, explicables y reproducibles del estado interno del sistema.

MSI no produce señales de compra o venta. Produce **diagnósticos de estado estructural**.

La diferencia es epistemológica: una señal prescribe una acción; un diagnóstico describe una condición. El MSI opera en el dominio del diagnóstico.

---

## Capítulo 2 — Principios Constitucionales

Los siguientes principios son invariantes. No pueden ser contradichos por ningún documento de Nivel 1 o inferior.

### PC-01 — Separación instrumento-fenómeno

Los instrumentos de observación no son el fenómeno de estudio. Son el medio para inferir propiedades del fenómeno. Un instrumento puede ser reemplazado sin que el modelo conceptual cambie.

*Consecuencia:* las EMAs son instrumentos. La Tendencia, el Momentum y la Estructura son fenómenos. El modelo describe fenómenos; los instrumentos los observan.

### PC-02 — Ninguna variable es suficiente

Ninguna variable aislada puede producir un diagnóstico válido del estado de un mercado. Todo diagnóstico requiere la integración de múltiples variables.

*Consecuencia:* toda Rule de tipo DIAGNOSIS debe tener al menos tres inputs de niveles distintos.

### PC-03 — El contexto es obligatorio

Una observación sin contexto temporal no es válida. Toda variable debe llevar su dimensión temporal como metadato.

*Consecuencia:* TIMESTAMP y TIMEFRAME son campos obligatorios en toda instancia de Variable.

### PC-04 — Los mercados son sistemas emergentes

Las propiedades más importantes de un mercado no se observan en variables individuales sino en la interacción entre ellas. El modelo debe diseñarse para capturar propiedades emergentes.

*Consecuencia:* toda arquitectura de diagnóstico debe incluir al menos una variable de tipo EMERGENT.

### PC-05 — Reproducibilidad total

Todo cálculo debe ser reproducible. Toda fórmula debe estar documentada. Toda regla debe ser explícita.

*Consecuencia:* ningún elemento del modelo puede depender de juicio no formalizado.

### PC-06 — Explicabilidad del diagnóstico

Todo diagnóstico debe poder explicarse en términos de las variables y reglas que lo produjeron. Un diagnóstico sin trazabilidad no es válido.

*Consecuencia:* toda instancia de Diagnosis debe incluir un explanation_template que referencie sus inputs.

### PC-07 — El precio es la única fuente de verdad observable primaria

Toda inferencia del modelo parte, directa o indirectamente, del precio. El volumen y el tiempo son dimensiones contextuales. Los instrumentos son derivaciones del precio.

### PC-08 — Gobierno del dato como requisito de existencia

Ningún objeto puede existir en el sistema si no está registrado en el repositorio correspondiente al nivel que le corresponde en la jerarquía.

---

# PARTE II — METAMODELO

---

## Capítulo 3 — Los Siete Meta-Tipos

El MSI MetaModel define exactamente **siete meta-tipos de objetos**. Todo objeto que exista en cualquier modelo MSI es instancia de uno de estos siete tipos.

Los meta-tipos se organizan en una cadena de abstracción creciente:

```
CONCEPT → PROPERTY → METRIC → INSTRUMENT → VARIABLE → RULE → DIAGNOSIS
```

Cada tipo en la cadena es más concreto que el anterior. Un CONCEPT es pura abstracción. Un DIAGNOSIS es el output computacional del sistema.

---

### Meta-Tipo 1 — CONCEPT

**Definición:** Un constructo abstracto que representa una entidad del dominio de conocimiento del mercado. Los Concepts no son calculables directamente. Son el vocabulario fundamental del modelo.

**Atributos formales:**

| Atributo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `id` | string | Sí | Identificador permanente. Formato: `[PROJECT]-CONCEPT-[SEQ]` |
| `name` | string | Sí | Nombre canónico del concepto |
| `description` | string | Sí | Definición formal en lenguaje natural |
| `domain` | string | Sí | Dominio de aplicación (ej. "Futuros de criptomonedas") |
| `parent_concept` | ref:CONCEPT | No | Concepto padre en la jerarquía taxonómica |
| `child_concepts` | ref[]:CONCEPT | No | Conceptos hijos |
| `synonyms` | string[] | No | Términos equivalentes en otros marcos teóricos |
| `axioms` | string[] | No | Proposiciones aceptadas como verdaderas para este concepto |
| `bibliography` | string[] | No | Referencias teóricas externas |
| `properties` | ref[]:PROPERTY | Sí | Al menos una Property debe estar asociada |

**Restricción:** Todo CONCEPT debe tener al menos una PROPERTY asociada para ser considerado operacionalizable (RC-07).

**Ejemplos de instancias en EIM:** Tendencia (EN-03), Momentum (EN-04), Estructura (EN-05), Energía (EN-06).

---

### Meta-Tipo 2 — PROPERTY

**Definición:** Una característica observable o inferible de un CONCEPT. Las Properties describen *qué* se puede medir de un Concept, sin especificar *cómo* medirlo.

**Atributos formales:**

| Atributo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `id` | string | Sí | Formato: `[PROJECT]-PROP-[SEQ]` |
| `name` | string | Sí | Nombre de la propiedad |
| `concept_ref` | ref:CONCEPT | Sí | Concepto al que pertenece esta propiedad |
| `nature` | enum | Sí | `STRUCTURAL` \| `TEMPORAL` \| `EMERGENT` |
| `observability` | enum | Sí | `DIRECT` \| `DERIVED` \| `INFERRED` |
| `temporality` | enum | Sí | `INSTANT` \| `WINDOW` \| `CUMULATIVE` |
| `description` | string | Sí | Definición formal |
| `metrics` | ref[]:METRIC | Sí | Al menos una Metric debe operacionalizarla |

**Valores del atributo `nature`:**
- `STRUCTURAL` — describe la organización interna del sistema (ej. Posición Relativa, Orden del Stack)
- `TEMPORAL` — describe la evolución del sistema en el tiempo (ej. Persistencia, Duración de Compresión)
- `EMERGENT` — no se puede inferir de ninguna variable aislada, solo de su interacción (ej. Coherencia, Sincronía)

**Valores del atributo `observability`:**
- `DIRECT` — se obtiene sin cálculo (ej. precio)
- `DERIVED` — requiere operación matemática sobre observables (ej. pendiente)
- `INFERRED` — requiere lógica de inferencia sobre variables derivadas (ej. estado estructural)

**Ejemplos de instancias en EIM:** Dirección (PR-01), Pendiente (PR-02), Separación (PR-03), Persistencia (PR-04).

---

### Meta-Tipo 3 — METRIC

**Definición:** La operacionalización cuantitativa de una PROPERTY. Una Metric especifica *cómo* se mide una Property: método, unidad, escala y normalización.

**Atributos formales:**

| Atributo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `id` | string | Sí | Formato: `[PROJECT]-METRIC-[SEQ]` |
| `name` | string | Sí | Nombre de la métrica |
| `property_ref` | ref:PROPERTY | Sí | Property que esta métrica operacionaliza |
| `method` | string | Sí | Descripción del método de cálculo |
| `unit` | string | Sí | Unidad de medida |
| `scale` | enum | Sí | `NOMINAL` \| `ORDINAL` \| `INTERVAL` \| `RATIO` |
| `normalization` | string | No | Método de normalización si aplica |
| `range` | object | No | `{min, max, note}` |
| `interpretation` | string | Sí | Qué significa un valor alto vs. bajo |

**Valores del atributo `scale`:**
- `NOMINAL` — categorías sin orden (ej. BULL/BEAR/NEUTRAL)
- `ORDINAL` — categorías con orden pero sin distancia definida (ej. STRONG/WEAK/EXHAUSTED)
- `INTERVAL` — valores numéricos con distancia definida, sin cero absoluto
- `RATIO` — valores numéricos con cero absoluto significativo (ej. porcentajes de separación)

**Nota:** Una PROPERTY puede tener múltiples METRICS. Esto permite que una misma propiedad (ej. Separación) sea medida de distintas formas (spread absoluto, spread relativo, índice compuesto).

---

### Meta-Tipo 4 — INSTRUMENT

**Definición:** El mecanismo de observación que produce datos sobre el mercado. Los Instruments son la interfaz entre el mundo observable y el modelo.

**Atributos formales:**

| Atributo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `id` | string | Sí | Formato: `[PROJECT]-INST-[SEQ]` |
| `name` | string | Sí | Nombre del instrumento |
| `source` | string | Sí | Fuente de datos primaria (ej. "precio de cierre OHLCV") |
| `configuration` | object | Sí | Parámetros de configuración del instrumento |
| `resolution` | string | Sí | Resolución temporal del instrumento |
| `parameters` | object | Sí | Parámetros ajustables con sus valores por defecto |
| `limitations` | string[] | Sí | Limitaciones conocidas del instrumento |
| `observes` | ref[]:CONCEPT | Sí | Concepts que este instrumento observa |

**Principio de separación (PC-01):** Un Instrument puede ser reemplazado por otro que observe el mismo Concept sin que el modelo conceptual cambie. Esto es lo que hace posible que el EIM pueda migrar de EMAs a cualquier otro instrumento de suavizado en el futuro.

**Ejemplos de instancias en EIM:** EMA(9), EMA(21), EMA(55), EMA(100), EMA(200).

---

### Meta-Tipo 5 — VARIABLE

**Definición:** La instancia computacional del modelo. Una Variable combina una METRIC, un INSTRUMENT y una configuración específica para producir un valor numérico o categórico computable.

Las Variables son los objetos que se calculan en código. Todo lo anterior (Concept, Property, Metric, Instrument) es conceptual. La Variable es donde el modelo toca el dato.

**Atributos formales:**

| Atributo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `id` | string | Sí | Formato: `V-[LEVEL]-[SEQ]` |
| `business_key` | string | Sí | Nombre en código (SNAKE_UPPER_CASE) |
| `name` | string | Sí | Nombre legible |
| `metric_ref` | ref:METRIC | Sí | Metric que esta variable implementa |
| `instrument_ref` | ref:INSTRUMENT | Condicional | Instrument usado. Obligatorio en L1. Opcional en L2+. |
| `level` | enum | Sí | `L0` \| `L1` \| `L2` \| `L3` \| `L4` |
| `data_type` | string | Sí | Tipo de dato del resultado |
| `formula_ref` | string | Condicional | Referencia a EIM-FRM-001. Obligatorio en L1-L4. |
| `depends_on` | ref[]:VARIABLE | Sí | Variables de las que se deriva |
| `used_by` | ref[]:VARIABLE | Sí | Variables que la consumen |
| `timestamp_required` | boolean | Sí | Siempre `true` (PC-03) |
| `timeframe_parameter` | boolean | Sí | Si la variable varía por timeframe |

**Niveles de Variable:**

| Nivel | Nombre | Descripción |
|---|---|---|
| L0 | Observable | Dato crudo del mercado. Sin cálculo. Fuente primaria. |
| L1 | Primaria | Derivada directamente de L0 mediante operación simple (ej. EMA sobre precio). |
| L2 | Secundaria | Derivada de L1 mediante operación compuesta. Operacionaliza Properties. |
| L3 | Estado | Combinación de L2 mediante lógica de inferencia. Asigna estados ontológicos. |
| L4 | Diagnóstico | Síntesis de L3. Output del motor de inferencia. |

**Restricciones de nivel (RC-02, RC-03):**
- Una Variable L0 no puede derivarse de ninguna otra Variable.
- Una Variable L4 no puede ser input directo de una Rule sin pasar por L3.
- El flujo de datos es estrictamente ascendente: L0 → L1 → L2 → L3 → L4.

---

### Meta-Tipo 6 — RULE

**Definición:** Una proposición formal que transforma un conjunto de Variables en un Estado o en un input para un DIAGNOSIS. Las Rules son la lógica explícita del sistema.

**Atributos formales:**

| Atributo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `id` | string | Sí | Formato: `R-[SEQ]` |
| `name` | string | Sí | Nombre descriptivo |
| `type` | enum | Sí | `THRESHOLD` \| `COMPARISON` \| `COMPOSITE` \| `TEMPORAL` \| `EMERGENT` |
| `inputs` | ref[]:VARIABLE | Sí | Variables que alimentan la regla |
| `operator` | string | Sí | Descripción formal del operador lógico o matemático |
| `output` | object | Sí | `{type, values, variable_ref}` |
| `confidence_weight` | float | Sí | Peso de esta regla en el diagnóstico compuesto (0–1) |
| `conditions` | string[] | No | Condiciones adicionales de activación |
| `sub_rules` | ref[]:RULE | Condicional | Obligatorio si type = COMPOSITE |
| `exceptions` | string[] | No | Condiciones que invalidan la regla |

**Valores del atributo `type`:**
- `THRESHOLD` — una variable cruza un umbral numérico
- `COMPARISON` — dos variables se comparan entre sí
- `COMPOSITE` — combina el output de múltiples sub-reglas
- `TEMPORAL` — evalúa la evolución de una variable en el tiempo
- `EMERGENT` — evalúa la interacción entre variables de distintas Properties

**Principio de PC-06:** Toda Rule debe producir un output cuya trazabilidad hacia sus inputs sea completamente explícita.

---

### Meta-Tipo 7 — DIAGNOSIS

**Definición:** El output final del sistema. Un Diagnosis integra múltiples outputs de Rules para producir una clasificación del estado del mercado con hipótesis, probabilidad, confianza y explicación.

**Atributos formales:**

| Atributo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `id` | string | Sí | Formato: `DIAG-[SEQ]` |
| `name` | string | Sí | Nombre del diagnóstico |
| `hypothesis` | string | Sí | La proposición que el diagnóstico evalúa |
| `inputs` | ref[]:RULE | Sí | Rules que alimentan el diagnóstico |
| `confidence_score` | float | Sí | Score de confianza resultante (0–100) |
| `explanation_template` | string | Sí | Plantilla narrativa explicativa con referencias a inputs |
| `scenario_ref` | ref:CONCEPT | Sí | Escenario ontológico asociado (SC-01 a SC-05 en EIM) |
| `emergent_inputs` | ref[]:VARIABLE | Sí | Al menos una variable EMERGENT requerida (PC-04) |
| `timestamp` | datetime | Sí | Momento del diagnóstico |
| `timeframe` | string | Sí | Timeframe de la observación |

**Restricción RC-04:** Todo Diagnosis debe tener al menos un input de tipo EMERGENT Property. Un diagnóstico basado únicamente en propiedades STRUCTURAL o TEMPORAL no es válido bajo el MSI MetaModel.

---

# PARTE III — RELACIONES

---

## Capítulo 4 — Tipos de Relaciones

El MSI define **diez tipos de relaciones** válidas entre objetos del modelo. Solo estas relaciones pueden existir. Cualquier relación que no corresponda a uno de estos tipos es inválida.

### Tabla de relaciones

| ID | Nombre | Origen | Destino | Descripción |
|---|---|---|---|---|
| REL-01 | `INSTANTIATES` | Objeto concreto | Meta-tipo | Un objeto de Nivel 1+ es instancia de un meta-tipo del Nivel 0. |
| REL-02 | `INHERITS` | CONCEPT hijo | CONCEPT padre | Herencia taxonómica entre conceptos. El hijo hereda todas las Properties del padre. |
| REL-03 | `OBSERVES` | INSTRUMENT | CONCEPT | Un instrumento produce observaciones sobre un concepto. |
| REL-04 | `MEASURES` | METRIC | PROPERTY | Una métrica cuantifica una propiedad. |
| REL-05 | `OPERATIONALIZES` | VARIABLE | METRIC + INSTRUMENT | Una variable implementa una métrica usando un instrumento. |
| REL-06 | `DERIVES_FROM` | VARIABLE | VARIABLE | Una variable se calcula a partir de otra. Implica dependencia computacional directa. |
| REL-07 | `MODULATES` | VARIABLE | VARIABLE | Una variable afecta la interpretación de otra sin ser su causa directa. No implica causalidad. |
| REL-08 | `FEEDS` | VARIABLE | RULE | Una variable es input de una regla. |
| REL-09 | `PRODUCES` | RULE | VARIABLE (L3/L4) | Una regla produce un estado o diagnóstico. |
| REL-10 | `CONSTRAINS` | RULE | Relación | Una restricción limita qué relaciones son válidas entre objetos. |

### Propiedades de las relaciones

Toda relación en el MSI debe declarar:

| Atributo | Tipo | Descripción |
|---|---|---|
| `id` | string | Formato: `REL-[TYPE_ID]-[FROM_ID]-[TO_ID]` |
| `type` | enum | Uno de los diez tipos definidos |
| `from` | ref:objeto | Origen de la relación |
| `to` | ref:objeto | Destino de la relación |
| `strength` | enum | `MANDATORY` \| `OPTIONAL` \| `CONDITIONAL` |
| `directionality` | enum | `UNIDIRECTIONAL` \| `BIDIRECTIONAL` |
| `description` | string | Explicación de la relación en este contexto |

### Reglas de validez de relaciones

- `DERIVES_FROM` es siempre UNIDIRECTIONAL y MANDATORY. Si A depende de B, B debe calcularse antes que A.
- `MODULATES` es UNIDIRECTIONAL pero OPTIONAL. Debe documentarse qué aspecto de la interpretación modula.
- `INHERITS` es transitiva: si C hereda de B y B hereda de A, entonces C hereda de A.
- `OBSERVES` no implica `MEASURES`. Un instrumento puede observar un Concept sin que exista una Metric formal para él.
- `FEEDS` y `PRODUCES` definen el flujo de información. Juntas forman el grafo de inferencia del sistema.

---

## Capítulo 5 — Grafo de Tipos

El siguiente diagrama define el grafo de **tipos** del MSI. Es el mapa de cómo los meta-tipos se relacionan entre sí. Todo grafo de objetos concretos (como el KG del EIM) debe ser conforme a este grafo de tipos.

```
MARKET (dominio)
  │
  ├─[posee]──► CONCEPT
  │               │
  │               ├─[tiene]──► PROPERTY
  │               │               │
  │               │               └─[se cuantifica mediante]──► METRIC
  │               │                                               │
  │               └─[se observa mediante]──► INSTRUMENT           │
  │                                           │                   │
  │                                           └─────────────────► VARIABLE ◄─[operacionaliza]─┘
  │                                                               │
  │                                                     [DERIVES_FROM / MODULATES]
  │                                                               │
  │                                                               ▼
  │                                                            VARIABLE (L2/L3)
  │                                                               │
  │                                                           [FEEDS]
  │                                                               │
  │                                                               ▼
  │                                                             RULE
  │                                                               │
  │                                                          [PRODUCES]
  │                                                               │
  │                                                               ▼
  └────────────────────────────────────────────────────────► DIAGNOSIS
```

---

# PARTE IV — RESTRICCIONES

---

## Capítulo 6 — Restricciones Constitucionales

Las siguientes restricciones son invariantes. Se identifican con prefijo `RC`.

| ID | Restricción | Nivel | Descripción |
|---|---|---|---|
| RC-01 | Separación instrumento-diagnóstico | Relaciones | Un INSTRUMENT no puede relacionarse con un DIAGNOSIS directamente. Debe pasar por VARIABLE → RULE. |
| RC-02 | Inmutabilidad de L0 | Variables | Una Variable L0 no puede tener ninguna Variable en su atributo `depends_on`. Sus inputs vienen únicamente del mercado. |
| RC-03 | Secuencialidad de niveles | Variables | El flujo de datos es estrictamente L0→L1→L2→L3→L4. Ningún nivel puede saltarse en la cadena de derivación. |
| RC-04 | Emergencia obligatoria en diagnóstico | Diagnosis | Todo DIAGNOSIS debe tener al menos un input de tipo EMERGENT Property. |
| RC-05 | Registro obligatorio | Gobierno | Ningún objeto puede existir en el sistema sin estar registrado en el repositorio de su nivel. |
| RC-06 | Documentación de MODULATES | Relaciones | Una relación MODULATES debe declarar explícitamente qué aspecto de la interpretación modula. No implica causalidad. |
| RC-07 | Operacionalizabilidad de CONCEPT | Concepts | Todo CONCEPT que no tenga al menos una PROPERTY asociada se considera no operacionalizable y no puede ser referenciado por ninguna VARIABLE. |
| RC-08 | Descomposición de COMPOSITE | Rules | Una RULE de tipo COMPOSITE debe declarar explícitamente todas sus sub-Rules en el atributo `sub_rules`. |
| RC-09 | Contexto temporal obligatorio | Variables | Toda Variable debe poder asociarse a un TIMESTAMP y un TIMEFRAME. Variables que no varían por timeframe deben igualmente declarar `timeframe_parameter: false`. |
| RC-10 | Trazabilidad del diagnóstico | Diagnosis | Todo DIAGNOSIS debe incluir un `explanation_template` que referencie explícitamente los IDs de las Rules y Variables que lo produjeron. |

---

# PARTE V — CONVENCIONES

---

## Capítulo 7 — Convenciones de Nomenclatura

### 7.1 Identificadores

Los identificadores son permanentes. Una vez asignados, no pueden cambiarse aunque el objeto se renombre o modifique. El ID es la clave primaria del sistema.

| Tipo de objeto | Formato | Ejemplo |
|---|---|---|
| Meta-tipo | `MSI-[METATYPE]-[SEQ]` | `MSI-CONCEPT-001` |
| Proyecto / Repositorio | `[PROJECT]-[REPO]-[SEQ]` | `EIM-EAR-001` |
| Concepto (EIM) | `EN-[SEQ]` | `EN-03` |
| Propiedad (EIM) | `PR-[SEQ]` | `PR-02` |
| Variable | `V-L[LEVEL]-[SEQ]` | `V-L2-013` |
| Regla | `R-[SEQ]` | `R-001` |
| Relación | `REL-[TYPE_ID]-[FROM_ID]-[TO_ID]` | `REL-06-V013-V014` |
| Diagnóstico | `DIAG-[SEQ]` | `DIAG-001` |
| Restricción | `RC-[SEQ]` | `RC-04` |
| Principio constitucional | `PC-[SEQ]` | `PC-01` |

### 7.2 Business Keys

Las business keys son los nombres en código de las Variables. Siguen la convención `SNAKE_UPPER_CASE`.

Reglas:
- Máximo 30 caracteres
- Sin espacios ni caracteres especiales
- Deben ser únicos dentro del proyecto
- Deben ser descriptivos del contenido, no de la implementación

Correcto: `COMPRESSION_INDEX`, `STACK_SCORE`, `MTF_SYNC`
Incorrecto: `ema_calc_1`, `var003`, `indicador_nuevo`

### 7.3 Nombres de atributos en JSON

Todos los documentos estructurados del proyecto usan `snake_case` para los nombres de atributos.

Correcto: `formula_ref`, `depends_on`, `business_key`
Incorrecto: `FormulaRef`, `DependsOn`, `businessKey`

---

## Capítulo 8 — Convenciones de Versionado

El proyecto usa **versionado semántico** (SemVer) con la forma `MAJOR.MINOR.PATCH`.

| Componente | Cuándo incrementa | Ejemplo |
|---|---|---|
| `MAJOR` | Cambio que rompe compatibilidad con versiones anteriores. Requiere revisión de todos los documentos dependientes. | `1.0.0 → 2.0.0` |
| `MINOR` | Adición de objetos nuevos sin modificar los existentes. Los documentos dependientes siguen siendo válidos. | `1.0.0 → 1.1.0` |
| `PATCH` | Corrección de errores tipográficos, aclaraciones, sin cambio estructural. | `1.0.0 → 1.0.1` |

**Regla de cascada:** Un cambio MAJOR en un documento de Nivel N requiere revisión de todos los documentos de Nivel N+1 y superiores.

**Regla de congelamiento:** Un documento en estado `ACTIVE` no puede recibir cambios MAJOR sin pasar primero a estado `REVIEW`. El flujo de estados es:

```
DRAFT → REVIEW → ACTIVE → DEPRECATED → ARCHIVED
```

---

# PARTE VI — GOBIERNO

---

## Capítulo 9 — Gobierno del Modelo

### 9.1 Fuente única de verdad

El EAR (Nivel 1) es la Single Source of Truth (SSOT) para todo objeto concreto del proyecto.

Este documento (Nivel 0) es la Single Source of Truth para las reglas del sistema.

Cuando existe conflicto entre un objeto concreto y las reglas del Nivel 0, el Nivel 0 prevalece.

### 9.2 Proceso de adición de objetos

Para añadir cualquier objeto nuevo al sistema (variable, concepto, regla):

1. Verificar que el objeto corresponde a un meta-tipo definido en este documento.
2. Completar todos los atributos obligatorios del meta-tipo.
3. Verificar que no viola ninguna restricción RC.
4. Registrar en el repositorio correspondiente al nivel del objeto.
5. Actualizar el EAR con las referencias cruzadas.
6. Incrementar la versión MINOR del documento receptor.

### 9.3 Proceso de modificación de objetos

Para modificar un objeto existente:

1. Evaluar si el cambio afecta atributos que otros objetos referencian.
2. Si hay dependencias afectadas: incremento MAJOR, revisión en cascada.
3. Si no hay dependencias afectadas: incremento MINOR o PATCH según magnitud.
4. Registrar el cambio en el historial del documento.
5. Notificar en los documentos dependientes que fueron revisados.

### 9.4 Proceso de deprecación

Un objeto puede ser marcado como `DEPRECATED` cuando:
- Es reemplazado por otro objeto más preciso.
- Su Property ya no es observable con los instrumentos disponibles.
- Contradice una restricción RC identificada con posterioridad.

Un objeto `DEPRECATED` no se elimina. Permanece en el repositorio con su estado actualizado y una referencia al objeto que lo reemplaza.

### 9.5 Extensibilidad del metamodelo

Nuevos dominios de observación (volumen, liquidez, order flow, volatilidad implícita) se incorporan al sistema como **nuevas instancias de los meta-tipos existentes**, no como nuevos meta-tipos.

La adición de un nuevo meta-tipo es un cambio MAJOR al MSI-META-001 y requiere justificación formal de por qué ninguno de los siete meta-tipos existentes es suficiente.

---

# PARTE VII — APÉNDICES

---

## Apéndice A — Glosario del MetaModel

| Término | Definición |
|---|---|
| **Meta-tipo** | Tipo abstracto que define la estructura de una clase de objetos. Los objetos concretos son instancias de meta-tipos. |
| **Instancia** | Un objeto concreto que cumple la estructura definida por un meta-tipo. |
| **Instanciación** | El proceso de crear un objeto concreto a partir de un meta-tipo, asignando valores a sus atributos. |
| **Constitución** | Este documento. El conjunto de reglas que no pueden ser contradichas por ningún nivel inferior. |
| **Dominio** | El universo de mercados y condiciones sobre el cual opera un modelo MSI. |
| **Emergencia** | Propiedad del sistema que no puede inferirse de ninguna variable aislada sino de la interacción entre varias. |
| **Trazabilidad** | La capacidad de seguir el origen de cualquier diagnóstico hasta las variables y reglas que lo produjeron. |
| **SSOT** | Single Source of Truth. El repositorio que contiene la versión oficial de un tipo de objeto. |
| **Operacionalizar** | Convertir un concepto abstracto en una variable computable con método, unidad y fórmula definidos. |
| **Grafo de inferencia** | La red de relaciones FEEDS y PRODUCES que define cómo las variables alimentan las reglas y las reglas producen diagnósticos. |

---

## Apéndice B — Mapa de conformidad EIM → MSI

La siguiente tabla muestra cómo los objetos del EIM (Nivel 1) se mapean a los meta-tipos del MSI (Nivel 0).

| Objeto EIM | Meta-tipo MSI | Repositorio EIM |
|---|---|---|
| Entidades EN-01 a EN-10 | CONCEPT | EIM-ONT-001 |
| Propiedades PR-01 a PR-07 | PROPERTY | EIM-ONT-001 |
| Métricas (implícitas en DDMR) | METRIC | EIM-DDMR-001 |
| EMA-9, EMA-21, EMA-55, EMA-100, EMA-200 | INSTRUMENT | EIM-EAR-001 |
| Variables V-L0 a V-L4 | VARIABLE | EIM-DDMR-001 |
| Reglas R-001 a R-00N | RULE | EIM-BRM-001 |
| STRUCTURAL_DIAGNOSIS | DIAGNOSIS | EIM-IRM-001 |
| Axiomas AX-01 a AX-08 | Restricciones constitucionales del EIM | EIM-ONT-001 |
| Estados E-01 a E-07 | Output de RULE tipo COMPOSITE | EIM-BRM-001 |
| Escenarios SC-01 a SC-05 | `scenario_ref` en DIAGNOSIS | EIM-IRM-001 |

---

## Apéndice C — Checklist de conformidad

Antes de añadir cualquier objeto al sistema, verificar:

**Para CONCEPT:**
- [ ] Tiene ID permanente en formato correcto
- [ ] Tiene al menos una PROPERTY asociada (RC-07)
- [ ] Su dominio está declarado
- [ ] Está registrado en el EAR

**Para VARIABLE:**
- [ ] Tiene business_key en SNAKE_UPPER_CASE
- [ ] Tiene nivel L0-L4 declarado
- [ ] Tiene formula_ref si nivel > L0
- [ ] Sus depends_on están todos en nivel inferior
- [ ] Tiene timestamp_required: true
- [ ] No viola RC-02 ni RC-03

**Para RULE:**
- [ ] Declara todos sus inputs
- [ ] Declara su confidence_weight
- [ ] Si es COMPOSITE, declara sub_rules (RC-08)
- [ ] Su output referencia una Variable L3 o L4

**Para DIAGNOSIS:**
- [ ] Tiene explanation_template con referencias explícitas (RC-10)
- [ ] Tiene al menos un input EMERGENT (RC-04)
- [ ] Tiene scenario_ref válido
- [ ] Tiene timestamp y timeframe

---

*Fin del documento MSI-META-001 v1.0.0*
