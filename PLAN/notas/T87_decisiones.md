# T87 ◆ — Decisiones de alcance multiactivo (pendientes de tu aprobación por escrito)

Fecha: 2026-11-20. Insumos: `PLAN/notas/T87_matriz.md`, `v2/reports/t87_agents_cost.md`,
`v2/reports/t87_portabilidad.md`, y las dos decisiones que ya tomaste: **T145 (2026-11-10, D: solo
análisis)** y **T163**, cuya regla general dice que *ninguna hipótesis de Sharpe sobre un solo
activo cripto es comprobable —hacen falta (2,4865/S)² años— y la única vía es multiactivo
(T93–T96)*.

**Nada de T89 en adelante empieza sin tu aprobación de esta página.**

---

## Por qué la fase 17 cambia de sentido

Cuando se escribió el plan, «multiactivo» era *más mercados donde buscar ventaja*. Después:

- **T27 NO PASA** y **T49** no validó ninguna estrategia; **T145** cerró la cuestión: solo análisis.
- **T163** demostró que el problema no es el mercado, es la **muestra**: 5,85 años de BTC dan 51,9 %
  de potencia para detectar un Sharpe de 0,70. Una moneda al aire.
- **T164** ya usó el universo de perpetuos (T181, 659 instrumentos) y, por primera vez, una
  hipótesis **sí tuvo potencia** (5,69 años evaluables frente a 5,1 exigidos). Veredicto: NO PASA,
  con t 0,81. Un «no» medible es exactamente el producto que buscamos.

**Multiactivo ya no es un buscador de ventajas: es el único instrumento de potencia estadística que
tenemos.** Eso es lo que recomiendo aprobar, y cambia cuatro de las cinco decisiones.

---

## ◆1 · Alcance de ejecución

**Recomendación: investigación global, ejecución SOLO simulada, sin intermediarios ni cuentas
nuevas.** Coherente con T145 (D) y con `CLAUDE.md` (sin dinero real hasta T27/T31). El contrato
`Broker` no se toca; T103 (adaptador de otro intermediario) se archiva en BACKLOG hasta que alguna
clase demuestre valor medido.

- *Alternativa A*: abrir testnet de un intermediario de acciones para «no perder tiempo». **No la
  recomiendo**: T45 ya está aparcada esperando claves de testnet, y no hay nada que ejecutar.
- *Alternativa B*: ni simular fuera de cripto (solo analizar). Más barato, pero deja T92 sin molde
  de costos y no se puede comparar entre clases.

## ◆2 · Horizontes

**Recomendación: 1 h–1 d, y 1 d como marco de primera clase del sistema.** Lo intradía rápido se
queda en cripto, donde ya hay datos.

Esto **no es gratis**: `build_snapshot` no puede construir un snapshot de 1 d hoy
(`eim/data/snapshot.py:146` levanta `ValueError: '1d' is not in list`), y `1d` está relegado a
`STORE_ONLY_TF_MS`. Es el primer trabajo concreto de T90 y hay que decidirlo aquí porque sin él
ninguna clase que solo opere en diario puede entrar.

- *Alternativa*: quedarse en 1 h/4 h. Evita ese trabajo, pero excluye acciones, índices y bonos —
  es decir, excluye la fase entera.

## ◆3 · Datos gratuitos frente a suscripciones

**Recomendación: solo datos públicos y gratuitos, con licencia verificada en la fuente (T88), y
ninguna suscripción hasta que una clase demuestre valor medido.**

Lo que ya hay en el equipo, sin pagar nada: 659 perpetuos con 641 828 velas diarias y 2,70 M de
liquidaciones de funding (T181); oro, S&P 500 y Nasdaq en diario (T183). Con eso T93–T96 se pueden
construir enteras.

**Aviso que te debo**: las series de S&P 500 y Nasdaq llegan por `yfinance`, y **las condiciones de
uso de Yahoo no están verificadas** (la alerta 3 de T04 ya lo marcó para OpenBB). Hoy se usan solo
para el visor y el contexto; antes de que un informe las use como insumo de decisión, T88 tiene que
verificarlo. Si no pasan, la clase de renta variable se queda sin datos gratuitos y ◆5 cambia.

- *Alternativa*: contratar un proveedor de acciones ahora. **No la recomiendo**: ninguna clase ha
  demostrado nada todavía, y el costo recurrente precede a cualquier medición.

## ◆4 · Orden de clases

**Recomendación: cambiar el orden de la nota de octubre.** Era cripto → acciones → FX → materias
primas → renta fija. Lo que la medición aconseja es **ordenar por potencia estadística ganada por
unidad de trabajo**:

1. **Cripto completo de Binance (659 perpetuos).** Ya descargado, mismo proveedor, mismo modelo de
   costos, mismo camino de ejecución. Cero licencias nuevas. Es donde T93–T96 se construyen y donde
   T95 (control de multiplicidad) se prueba de verdad.
2. **Índices en diario (S&P 500, Nasdaq, oro).** Ya en el almacén; cuestan solo el trabajo de 1 d y
   del calendario de sesiones. Dan la primera prueba real de que el sistema vive fuera de 24/7.
3. **Acciones y ETF líquidos en diario.** Primera clase que exige trabajo nuevo de verdad:
   universo, calendario, festivos, **dividendos y splits point-in-time**.
4. **FX mayores.** Exige declarar `market_structure` (OTC fragmentado) y aceptar que el volumen es
   de ticks o no existe: `technical` pierde su familia de flujo.
5. **Futuros tradicionales.** Multiplicador, roll, vencimiento, series continuas con empalme
   declarado.
6. **Renta fija, derivados y opciones: solo viabilidad (T100), sin construir.**

- *Alternativa*: mantener el orden de octubre (acciones antes que índices). Cuesta más y prueba
  menos: los índices ya están descargados y ejercen el mismo calendario de sesiones.

## ◆5 · Lista de aceptación por clase (los 8 puntos, como estándar de T97–T100)

**Recomendación: aprobarla tal cual.** Está en `PLAN/notas/T87_matriz.md` §9 y es el molde
vinculante para T97–T100: registro · datos con licencia verificada · calidad contra el calendario
real · agentes elegibles con capacidades declaradas · costos y margen de la clase · simulación ·
validación con pre-registro y multiplicidad ampliada (no reiniciada) · **no regresión de BTC/ETH**.

El punto 4 es el que esta auditoría hizo necesario, y es el más importante: **el riesgo medido no es
que un agente falle, es que acierte en silencio.** Ninguno de los 11 agentes de `candles` falló
sobre oro, S&P 500 ni Nasdaq —cero excepciones, cero `no_data`— pero:

- `vwap` publica `status="ok"`, sesgo −0,13 y confianza 0,60 en el S&P 500 **con un ancla vacía**
  (período diario con σ = 0, `position = "SIN_DATOS"`) y con los períodos semanal y quincenal
  devolviendo **el mismo número**: cuenta la misma evidencia dos veces.
- `bars_per_year = 8766` (`eim/backtest/params.py:40`) **infla el Sharpe de una serie diaria de
  acciones ×5,9** (√(8766/252)).

Un sistema que presenta cifras falsas sin avisar es peor que uno que no cubre la clase. De ahí la
regla del punto 4: *un agente sin el dato que declara necesitar no corre; sale `no_data` con
motivo, nunca un número silencioso*.

---

## Lo que apruebas, en una línea

> Multiactivo como **instrumento de potencia estadística**, solo análisis y solo simulado, con datos
> públicos y licencia verificada; 1 h–1 d con `1d` de primera clase; orden cripto completo →
> índices en diario → acciones → FX → futuros → (renta fija solo viabilidad); y la lista de
> aceptación de 8 puntos como requisito para que una clase entre.

## Si prefieres no seguir con la fase 17

Es una opción legítima y te la debo escrita: T164 ya dio el «no» que el universo de perpetuos podía
dar, y construir T89–T96 son semanas de trabajo cuyo producto más probable son más «no» medibles.
La razón para seguir es T163: **sin multiactivo no hay ninguna hipótesis de Sharpe comprobable en
este sistema**, así que la alternativa no es «buscar la ventaja en otro sitio», es dejar de poder
medir. Pero la decisión es tuya, y si la respuesta es no, T89–T100 pasan a BACKLOG y la fase se
cierra sin más trabajo.

## Lo que NO se decide aquí

Qué repositorios y proveedores entran, con licencias y condiciones verificadas en la fuente: **T88**,
con el formato de T04. Esta página no aprueba ningún repositorio de terceros ni ningún proveedor.
