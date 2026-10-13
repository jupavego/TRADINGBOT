# EIM-ONT-001 — Ontología del Mercado

## Metadatos del Documento

| Campo | Valor |
|---|---|
| **Código** | EIM-ONT-001 |
| **Nombre** | Ontología del Mercado |
| **Repositorio** | ONT — Ontology Repository |
| **Proyecto** | EMA Intelligence Model (EIM) |
| **Disciplina** | Market Structural Intelligence (MSI) |
| **Fase** | I — Ontología del Mercado |
| **Versión** | 1.0.0 |
| **Estado** | ACTIVE |
| **Fecha de creación** | 2026-06-27 |
| **Última actualización** | 2026-06-27 |
| **Dependencias** | EIM-EAR-001 |

---

## Historial de Cambios

| Versión | Fecha | Descripción |
|---|---|---|
| 1.0.0 | 2026-06-27 | Creación del diccionario ontológico inicial. Definición de premisa, niveles, entidades y axiomas. |

---

## 1. Propósito

Este documento establece el marco conceptual completo del EIM.

Define el lenguaje, las entidades y los principios que gobiernan el modelo. No contiene fórmulas ni algoritmos. Estos serán desarrollados en las Fases II a IV.

Todo componente posterior del proyecto debe ser consistente con las definiciones aquí establecidas.

---

## 2. Premisa Ontológica

> El mercado de futuros de criptomonedas es un sistema dinámico compuesto por propiedades estructurales, temporales y emergentes.  
> Las EMAs son instrumentos de observación para inferir el estado interno de ese sistema.  
> Las EMAs no son el fenómeno de estudio.

Esta premisa es el axioma fundacional del EIM. Todo razonamiento del modelo debe ser compatible con ella.

---

## 3. Dominio de Aplicación

El EIM opera inicialmente sobre el dominio de **futuros de criptomonedas**.

La arquitectura del modelo es agnóstica al instrumento. El dominio se declara como parámetro de configuración, no como supuesto implícito, lo que permite extensión futura a otros mercados sin rediseño.

---

## 4. Niveles Ontológicos

El EIM organiza el conocimiento del mercado en cuatro niveles jerárquicos:

### Nivel 1 — Hechos Observables

Datos primarios capturados directamente del mercado. No requieren inferencia.

| ID | Hecho | Definición |
|---|---|---|
| H-01 | Precio | Valor numérico resultante del consenso entre compradores y vendedores en un instante dado. |
| H-02 | Tiempo | Dimensión temporal que ordena la secuencia de hechos observables. Parámetro de toda observación. |
| H-03 | Volumen | Cantidad de contratos negociados en un período de tiempo determinado. |
| H-04 | EMA(n) | Media móvil exponencial de período n calculada sobre el precio. Instrumento de observación del modelo. |

> **Nota:** El precio, el tiempo y el volumen son hechos del mercado. La EMA es un instrumento derivado del precio. Se listan juntos porque constituyen la materia prima observable del modelo, pero su naturaleza epistemológica es distinta.

---

### Nivel 2 — Propiedades

Características del mercado inferidas a partir de los hechos observables. Requieren cálculo o comparación.

| ID | Propiedad | Definición |
|---|---|---|
| PR-01 | Dirección | Orientación predominante del desplazamiento del precio en un período. |
| PR-02 | Pendiente | Tasa de cambio de una EMA en el tiempo. Mide la intensidad del movimiento. |
| PR-03 | Separación | Distancia relativa entre dos o más EMAs. Refleja el grado de divergencia entre perspectivas temporales. |
| PR-04 | Persistencia | Capacidad del mercado para mantener una dirección a lo largo del tiempo sin revertirla. |
| PR-05 | Compresión | Estado en que múltiples EMAs convergen hacia un rango estrecho, indicando reducción de la divergencia entre perspectivas. |
| PR-06 | Cruce | Evento de intersección entre dos EMAs de diferente período. |
| PR-07 | Posición Relativa | Ordenamiento jerárquico de las EMAs entre sí y respecto al precio. |

---

### Nivel 3 — Estados

Condiciones estructurales del mercado derivadas de la combinación de propiedades. Un estado es una caracterización del sistema en un momento dado.

| ID | Estado | Definición |
|---|---|---|
| E-01 | Tendencia Fuerte | El mercado exhibe dirección clara, pendiente pronunciada y separación amplia entre EMAs. Las propiedades son coherentes entre sí. |
| E-02 | Tendencia Débil | El mercado mantiene dirección pero con pendiente reducida, separación estrecha o señales de agotamiento. |
| E-03 | Ordenado | Las EMAs presentan un ordenamiento jerárquico limpio y consistente. El sistema muestra organización interna. |
| E-04 | Agotado | Las propiedades del mercado indican pérdida de impulso sin confirmación de reversión. Estado de transición. |
| E-05 | Comprimido | El mercado se encuentra en un estado de baja separación entre EMAs, indicando acumulación de energía potencial. |
| E-06 | En Expansión | El mercado sale del estado de compresión con aumento de separación y pendiente. |
| E-07 | Divergente | Las propiedades del mercado son inconsistentes entre sí, generando señales contradictorias. |

---

### Nivel 4 — Escenarios

Proyecciones dinámicas del mercado basadas en el estado actual y las reglas de transición entre estados. Un escenario describe lo que el modelo anticipa que puede ocurrir, no lo que ocurrirá con certeza.

| ID | Escenario | Definición |
|---|---|---|
| SC-01 | Continuación | El mercado mantiene su estado actual sin señales de reversión. La estructura sugiere persistencia de la tendencia. |
| SC-02 | Ruptura | El mercado sale de un estado de compresión o consolidación con cambio significativo en separación y pendiente. |
| SC-03 | Pullback | Corrección temporal hacia una EMA de referencia sin quiebre estructural. El estado subyacente se preserva. |
| SC-04 | Cambio Estructural | El mercado experimenta una reconfiguración de su organización interna. Las propiedades cambian de forma sostenida. |
| SC-05 | Consolidación | El mercado no exhibe tendencia definida. Las propiedades oscilan sin dirección clara. |

---

## 5. Entidades Fundamentales

Las entidades son los conceptos abstractos que el modelo utiliza para describir el mercado. No son variables calculables directamente; son constructos que se operacionalizan mediante variables en la Fase II.

| ID | Entidad | Definición | Nivel Ontológico |
|---|---|---|---|
| EN-01 | Precio | Consenso observable entre participantes del mercado en un instante dado. | Hecho |
| EN-02 | Tiempo | Dimensión que ordena y escala toda observación del sistema. | Hecho |
| EN-03 | Tendencia | Persistencia de una dirección de precio a lo largo del tiempo. | Propiedad / Estado |
| EN-04 | Momentum | Capacidad del mercado para mantener y sostener su tendencia actual. | Propiedad |
| EN-05 | Estructura | Organización interna del mercado expresada en el ordenamiento y comportamiento de las EMAs. | Estado |
| EN-06 | Energía | Potencial acumulado de movimiento, inferido a partir del grado de compresión o expansión. | Propiedad |
| EN-07 | Elasticidad | Grado de alejamiento del precio respecto a su referencia de equilibrio (EMA de mayor período). | Propiedad |
| EN-08 | Equilibrio | Estado teórico alrededor del cual el precio tiende a oscilar en ausencia de momentum. Operacionalizado mediante la EMA de mayor período del modelo. | Referencia |
| EN-09 | Fricción | Resistencia estructural al movimiento del precio, manifestada como ralentización de pendiente o compresión entre EMAs. | Propiedad |
| EN-10 | Coherencia | Grado de consistencia entre múltiples propiedades del mercado. Un mercado coherente exhibe propiedades que apuntan en la misma dirección. | Propiedad Emergente |

---

## 6. Axiomas del Modelo

Los axiomas son proposiciones que el modelo acepta como verdaderas sin requerir demostración. Constituyen el fundamento lógico de todo razonamiento posterior.

| ID | Axioma |
|---|---|
| AX-01 | El mercado no puede ser descrito por una sola variable. |
| AX-02 | Una EMA es una aproximación del estado del mercado en una escala temporal, no una verdad absoluta. |
| AX-03 | La coherencia entre propiedades incrementa la confiabilidad del diagnóstico. |
| AX-04 | Todo estado del mercado es transitorio. |
| AX-05 | La compresión precede a la expansión. |
| AX-06 | El precio es la única fuente de verdad observable. Todo lo demás es inferencia. |
| AX-07 | El volumen modula la validez de las propiedades inferidas desde el precio. |
| AX-08 | Un diagnóstico sin contexto temporal no es válido. |

---

## 7. Restricciones Ontológicas

Las siguientes restricciones delimitan el alcance del modelo en esta fase:

- **R-01:** La Fase I no define fórmulas matemáticas. Las propiedades se describen conceptualmente; su operacionalización ocurre en la Fase IV.
- **R-02:** Los estados definidos son mutuamente excluyentes en su forma pura, pero el mercado puede exhibir estados de transición entre ellos.
- **R-03:** Los escenarios no son predicciones deterministas. Son proyecciones probabilísticas condicionadas al estado actual.
- **R-04:** Toda entidad listada en la Sección 5 debe ser operacionalizada mediante al menos una variable en la Fase II antes de ser utilizada en cálculo alguno.

---

## 8. Relación con Otros Repositorios

| Repositorio | Dependencia |
|---|---|
| DDMR | Operacionaliza las entidades EN-01 a EN-10 mediante variables calculables. |
| FRM | Formaliza matemáticamente las propiedades PR-01 a PR-07. |
| BRM | Define reglas para la asignación de estados E-01 a E-07 a partir de propiedades. |
| IRM | Define reglas de transición entre estados y asignación de escenarios. |
| KG | Representa las relaciones entre entidades, propiedades, estados y escenarios. |
| PRM | Cataloga configuraciones recurrentes observadas en los niveles 3 y 4. |

---

## 9. Glosario

| Término | Definición |
|---|---|
| Ontología | Marco conceptual que define las entidades, relaciones y principios de un dominio de conocimiento. |
| Hecho Observable | Dato capturado directamente del mercado sin necesidad de inferencia. |
| Propiedad | Característica del mercado inferida a partir de uno o más hechos observables. |
| Estado | Condición estructural del mercado derivada de la combinación de propiedades. |
| Escenario | Proyección dinámica del comportamiento del mercado basada en el estado actual. |
| Entidad | Constructo abstracto que agrupa propiedades relacionadas bajo un concepto unificador. |
| Axioma | Proposición aceptada como verdadera sin demostración. Fundamento del razonamiento del modelo. |
| Propiedad Emergente | Característica del sistema que no puede inferirse de ninguna variable aislada, sino de su interacción. |
| SSOT | Single Source of Truth. El EAR es la SSOT del proyecto. |
| EIM | EMA Intelligence Model. Nombre del proyecto. |
| MSI | Market Structural Intelligence. Disciplina propuesta en la que se enmarca el EIM. |
