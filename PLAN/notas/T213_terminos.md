# T213 — Términos de datos de las opciones cripto (entregable 1)

Fecha: **2026-11-27** · Modo **ANÁLISIS** · Insumo de la ◆ de T100 (`PLAN/notas/T100_decision.md`) ·
**◆ resuelta por el usuario el 2026-11-27: aprobada a nivel 1 (§6)**.

Cómo se leyó: páginas oficiales de Deribit y Binance abiertas desde la nube el 2026-11-27. **No se
llamó a ningún endpoint ni se descargó ningún dato** (el shell de esta sesión no tiene red): todo lo
que dependa de una respuesta real de la API queda «no verificado» y se mide en la laptop si se
aprueba la fuente. Las citas son cortas a propósito; el resto va parafraseado con el número de
cláusula y la URL para leerlo entero.

## 0. Resumen

- **Deribit permite el uso personal de sus datos de mercado y de los derivados de ellos** (cl. 2.10
  de los términos de Deribit FZE). Prohíbe agregarlos, revenderlos, publicarlos, reenviarlos o
  «procesarlos» para cualquier otra cosa sin aprobación escrita. **No exige atribución** y **no
  tiene cláusula específica sobre guardar en local**.
- **Hay una cláusula que choca**: en la 27.1(i) el miembro se compromete a no hacer recolección
  sistemática o automatizada de datos en sus sistemas (raspado, minería, extracción). Al mismo
  tiempo, la 2.11 admite el acceso por API, Deribit publica límites para las peticiones públicas
  sin clave y una guía para montar canales de datos de opciones. La lectura razonable es que la
  27.1(i) apunta a raspar fuera de la API documentada, **pero el texto no lo dice**: es
  interpretación, no verificado.
- **Límites de petición**: las públicas sin clave van por IP y **sin cifra publicada**. El método
  que haría falta (`public/get_book_summary_by_currency`) **trae la cadena entera en una sola
  llamada**, así que una toma por hora y moneda queda muy lejos de cualquier límite razonable.
- **Histórico**: cada operación pública de opciones trae su volatilidad implícita (`iv`), 1 000 por
  petición. El servidor de histórico completo (`history.deribit.com`) **no aparece en la
  documentación oficial** leída: no verificado. Sin cotizaciones bid/ask pasadas, una superficie
  reconstruida desde operaciones queda sesgada → **T214 debe contar con acumular hacia adelante**
  salvo que se verifique otra cosa.
- **Binance opciones (alternativa)**: sus Términos de Uso están en un PDF embebido que **no se pudo
  leer** (el mismo hueco que Binance `fapi` desde T33, ◆ T88 §5.2): no verificado. Peor candidata
  que Deribit, que al menos tiene el texto legible.
- **Esto ya afecta a algo vivo**: el colector del DVOL (T165) usa la misma API pública de Deribit,
  cada hora, desde el 2026-11-11, bajo estos mismos términos, y `deribit-dvol` **no tiene ficha** en
  `eim/data/providers/meta.py` (`lookup` la devuelve como nivel 1, «licencia no declarada»).
  Decidas lo que decidas, vale también para el DVOL.

## 1. Deribit

### 1.1 Qué términos aplican

Deribit funciona con dos entidades: **Deribit FZE** (Dubái, la plaza; sus «Exchange Membership
Terms», versión del **26-01-2026**) y **DRB Panama Inc.** (el intermediario que atiende a clientes
minoristas, con sus propios «Terms of Service», y que como miembro de la plaza queda atado también a
los de FZE).
Fuente: https://support.deribit.com/hc/en-us/sections/25944530944285-Terms-Of-Service-Overview

- Los de FZE **se leyeron**:
  https://support.deribit.com/hc/en-us/articles/25944532191645-Deribit-Exchange-Membership-Terms-Deribit-FZE
- Los de DRB Panama **no se pudieron localizar** (la página índice los nombra sin enlace): **no
  verificado**.
- **Ámbito**: el preámbulo de FZE dice que acceder al sitio o a los servicios ya vincula, pero las
  obligaciones están redactadas para el «Member» (persona aprobada como cliente, con acceso a la
  plaza; definiciones al final del documento). Para quien solo llama a la API pública sin cuenta,
  el texto **es ambiguo**. Aquí se toma la lectura prudente: **se aplican como si fueras miembro**.

### 1.2 Las cláusulas que importan

| Pregunta | Respuesta | Cláusula y fuente |
|---|---|---|
| ¿Guardar en local y usar para análisis personal? | **Sí, como uso personal.** El uso de datos de mercado y derivados es solo personal; fuera de eso no se pueden agregar, revender, publicar, reenviar ni «procesar» sin aprobación escrita. No hay cláusula que hable de guardar o cachear: la lectura más natural es que guardar para uso propio cabe en el uso personal | FZE cl. 2.10 (texto vigente, 26-01-2026). Es la misma cláusula que Deribit anunció en 2021 como art. 4.6: los datos son «for personal use only» — https://insights.deribit.com/exchange-updates/deribit-updates-terms-of-service-as-of-29-january-2021/ |
| ¿Publicar resultados derivados (informes, señales)? | **No sin aprobación escrita.** Publicar o reenviar «derivados» está prohibido salvo uso personal | FZE cl. 2.10 |
| ¿Exige atribución? | **No** en el texto leído | — (no encontrada en FZE) |
| ¿Recolección automatizada? | **Ambiguo.** El miembro se compromete a no hacer recolección sistemática o automatizada (raspado, minería, extracción, cosecha de datos) en los sistemas de Deribit. A la vez puede acceder «using any API, algorithm, software» (2.11) y Deribit puede limitar el número de instrucciones (9.2) o cobrar por la API (15.5) | FZE cl. 27.1(i), 2.11, 9.2, 15.5 |
| ¿Los datos son exactos? | Sin garantía; se usan bajo tu riesgo | FZE cl. 2.9, 2.13 |
| Propiedad intelectual | Contenido de Deribit; prohibido copiar, mostrar, distribuir o explotar comercialmente | FZE cl. 37.1-37.3 |

**Lo que inclina la lectura de la 27.1(i) hacia «la API documentada está permitida»** (indicios, no
texto legal):

- Deribit tiene una guía oficial de recogida de datos de opciones dirigida a quien monte un canal
  de datos de mercado («anyone building a market data pipeline against Deribit options»), que
  recomienda justo `get_book_summary_by_currency` para las tomas:
  https://docs.deribit.com/articles/options-data-collection-best-practices
- La página de límites de petición regula expresamente las peticiones públicas sin clave (§1.3).

### 1.3 Límites de petición publicados

Fuente: https://docs.deribit.com/articles/rate-limits (sin fecha de actualización en la página).

- **Públicas sin clave**: limitadas por IP («rate-limited on a per-IP basis»), sin tocar el cupo de
  las subcuentas, y **sin cifra publicada**. Si se pasa, rechazo temporal o desconexión.
- Por defecto (métodos sin límite propio, cupo de subcuenta): 500 créditos por petición, 50 000 de
  máximo, recarga de ~20 peticiones/s.
- `public/ticker` y `public/get_order_book` comparten cupo: **5/s sostenido, ráfaga de 25**.
- `public/get_instruments`: **1/s**, y la guía avisa de no consultarlo en bucle.
- `public/get_book_summary_by_currency` y `public/get_last_trades_by_currency`: **sin límite
  propio** en la tabla.
- Además rigen las reglas generales de uso de la API (política de abuso y relación órdenes/volumen,
  pensada para quien opera): https://docs.deribit.com/articles/api-usage-policy

### 1.4 Endpoint para el colector (si se aprueba)

`GET /api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option` — una llamada devuelve
todas las opciones vivas de la moneda:
https://docs.deribit.com/api-reference/market-data/public-get_book_summary_by_currency

| Campo | Qué es | Nota |
|---|---|---|
| `bid_price`, `ask_price`, `mid_price` | Mejor compra, venta y medio | `null` si un lado está vacío: **se guarda como dato** (nadie compra o vende). Incompleta, y descartada con el motivo contado, es la fila sin nombre legible, marca, IV de marca, subyacente, tipo, interés abierto o instante |
| `mark_price`, `mark_iv` | Precio de marca y su volatilidad implícita | |
| `underlying_price`, `underlying_index` | Subyacente usado para la IV (futuro o índice) | |
| `interest_rate` | Tipo usado para la IV | |
| `open_interest` | Interés abierto, en la moneda base | **Llega con 8 h de retraso** según la propia página |
| `creation_timestamp` | Instante de la toma (ms) | |
| `volume`, `last`, `high`, `low` | Actividad de 24 h | |

No trae `bid_iv`/`ask_iv` (eso sale de `ticker`, una llamada por instrumento): se calcularían con
`eim/options/implied_vol.py` desde bid/ask, o se dejan fuera. La lista de instrumentos (vencimiento,
precio de ejercicio, tipo) se saca del propio `instrument_name` o de `get_instruments`, una vez al
día como mucho.

### 1.5 Histórico público

- `public/get_last_trades_by_currency_and_time` devuelve operaciones con `iv`, `mark_price` e
  `index_price`, hasta 1 000 por petición:
  https://docs.deribit.com/api-reference/market-data/public-get_last_trades_by_currency_and_time
- **Hasta dónde llega, y si incluye vencimientos ya expirados: la página no lo dice.** El servidor
  `history.deribit.com`, que varios proyectos de terceros usan para bajar todo el histórico, **no
  aparece en la documentación oficial** leída → no verificado (comprobable en la laptop con una
  sola llamada).
- Aun si existe completo: las operaciones dan IV donde hubo negocio, no una cadena con dos lados a
  una hora fija. Reconstruir superficies pasadas así mezcla instantes y deja huecos en los precios
  de ejercicio sin negocio. **Para el pre-registro de T214: acumular hacia adelante** es lo
  honesto; el histórico de operaciones, como mucho, un contraste secundario declarado.

## 2. Binance opciones europeas (alternativa)

| Pregunta | Respuesta | Fuente |
|---|---|---|
| Términos de datos | **No verificados.** La página de términos carga el texto desde un PDF embebido que no se pudo leer; la documentación de la API solo enlaza a esa página. Es el mismo hueco que Binance `fapi` (◆ T88 §5.2) | https://www.binance.com/en/terms · https://developers.binance.com/docs/derivatives/options-trading/general-info |
| Límites | Por IP, por peso, con la cifra en `/eapi/v1/exchangeInfo` (no en la página). Vetos automáticos crecientes de 2 min a 3 días si no se respeta el 429 | misma página de la API |
| Clave | Los métodos `MARKET_DATA` (p. ej. operaciones antiguas) **exigen clave**; los públicos no | misma página |
| Histórico con licencia | Binance Vision tiene licencia leída (CC BY-NC-SA 4.0, ya aprobada en T88), pero su repositorio público **no lista conjuntos de opciones** → no verificado que existan | https://github.com/binance/binance-public-data/ |

Conclusión: Binance opciones no mejora a Deribit en nada que se pueda comprobar hoy, y tiene menos
liquidez en opciones. Queda como alternativa solo si Deribit se rechaza **y** se acepta usar una
fuente con términos sin leer, cosa que la ◆ de T100 no pide.

## 3. Lo que no se pudo verificar

1. Texto de los términos de **DRB Panama** (la entidad minorista).
2. Si la cl. 27.1(i) de FZE alcanza a la API pública documentada.
3. Cifra del límite por IP de las peticiones públicas de Deribit.
4. Cobertura de `history.deribit.com` y de las operaciones públicas (fecha de inicio, expirados).
5. Términos de datos de Binance (opciones y `fapi`) y si Binance Vision publica opciones.
6. **Volumen en disco**: se mide en la laptop antes de programar nada (entregable 4).

## 4. Qué haría el colector si se aprueba (para que la decisión sea informada)

Nivel **1 (investigación)** en `SourceMeta`, no 2: los límites no tienen cifra y la 27.1(i) queda
ambigua. Una llamada por moneda y hora (BTC; ETH solo si cabe), en prioridad de lote como el DVOL,
reintentos, solo filas completas (una cara vacía del libro es un dato y se guarda), calidad de cada toma con `eim/options/chain.py` guardada
al lado, `data/options/` en la copia diaria, **nada publicado ni compartido fuera del proyecto**. La
misma ficha se pondría a `deribit-dvol`, que hoy no tiene.

## 5. ◆ Lo que se te pide

**¿Se aprueba Deribit (API pública) como fuente de las cadenas de opciones, con las condiciones del
§4?**

- **Recomendación: aprobar con nivel 1** y, en paralelo, escribir a Deribit pidiendo confirmación
  de que una toma horaria por la API pública para análisis personal no choca con la 27.1(i). El uso
  personal está permitido por escrito, el canal es el que Deribit documenta para esto y el DVOL ya
  funciona igual desde hace dos semanas. Si Deribit contesta que no, se retiran el colector de
  cadenas y el del DVOL.
- **Alternativa A — esperar la respuesta de Deribit** antes de construir nada (T213 queda ◐, T214
  no empieza).
- **Alternativa B — rechazar**: T213 se cierra, T214 no empieza y, por coherencia, habría que
  decidir también sobre el colector del DVOL de T165.

## 6. Respuesta del usuario (2026-11-27): aprobada, nivel 1

Elegida la recomendación del §5 («Aprobar, nivel 1»). Queda fijado:

1. **Deribit (API pública) entra como fuente de las cadenas de opciones de BTC (y ETH si cabe en
   el presupuesto)**, con ficha `DERIBIT` de **nivel 1** en `v2/eim/data/providers/meta.py`. La
   misma ficha cubre el DVOL de T165, que hasta hoy no tenía.
2. **Solo uso personal**: nada de `data/options` (ni derivados suyos: informes, señales) se publica,
   se reenvía ni se comparte fuera del proyecto. Solo información sobre la volatilidad: no se
   operan opciones y no toca síntesis, plan, riesgo ni bróker.
3. **En paralelo se pide confirmación por escrito a Deribit** de que una toma periódica por la API
   pública para análisis personal no choca con la cl. 27.1(i). La escribe el usuario (borrador en
   la sesión de Claude del 2026-11-27). **Si Deribit contesta que no, se retiran el colector de
   cadenas y el del DVOL** (`opciones_colector.ps1 -Quitar`, `dvol_colector.ps1 -Quitar`).
4. **El colector corre en la portátil**: las cadenas no se pueden volver a descargar y allí se
   aplica y queda encendida; el DVOL, que corre en `juanpablo-cpu`, sí se puede volver a descargar
   entero donde haga falta para T214.

Lo que se construyó con esta aprobación (entregables 3-5) está en `PLAN/STATUS.md` (fila de T213)
y en la BITÁCORA del 2026-11-27: proveedor `option_book_summary`, colector
`v2/eim/data/options_chain.py` (+ `options_parse.py`), tarea `v2/scripts/opciones_colector.ps1`,
copia diaria de `options/`, pruebas sin red con un recorte real grabado y el volumen medido.
