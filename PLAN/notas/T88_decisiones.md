# T88 ◆ — Lista cerrada de repositorios y proveedores para T89–T100

Fecha de la propuesta: **2026-11-20** · Evidencia: `PLAN/notas/T88_auditoria.md` ·
**Estado: APROBADA POR EL USUARIO el 2026-11-20** (apartados 1 y 2; §7). Es la lista de
dependencias de T89–T100: lo de los apartados 1 y 2 entra con el papel y los límites escritos ahí,
y lo del 3 queda descartado. No autoriza instalar nada de los apartados 2.3 ni gastar dinero.

## 0. Qué se decide aquí y qué no

Se decide **qué repositorios y qué proveedores de datos pueden entrar** en la fase 17, con qué
papel, con qué licencia y con qué límites escritos. **No** se decide el alcance multiactivo (eso es
la ◆ de T87), **no** se contrata nada, **no** se abre ninguna cuenta y **no** se instala nada: cada
«A usar» de abajo es un permiso, no un hecho.

Tres reglas del proyecto siguen mandando sobre todo lo de abajo y ninguna se toca:

- **Solo análisis** (◆ de T145, 2026-11-10, opción D). Nada de esta lista autoriza ejecución.
- **Sin dinero real** hasta T27/T31; solo claves de papel o testnet sin permiso de retiro.
- Toda cifra expone su `source` y su cobertura real; los agentes siguen siendo funciones puras.

**Si la ◆ de T87 recorta el alcance** (por ejemplo, si el usuario deja fuera renta variable o
materias primas), esta lista se recorta con él: las entradas quedan, pero sin tarea que las use.

## 1. Repositorios que entran

| Repo | Papel en la fase 17 | Dónde vive | Licencia verificada | Límites escritos |
|---|---|---|---|---|
| **`exchange_calendars`** 4.13.3 | **Autoridad de calendarios de mercado** (T89, T90): sesiones del **subyacente**, y `"24/7"` para los contratos | Dependencia del venv, extra `calendars` | Apache-2.0 (`spdx_id`, `license_expression` y cabeceras coinciden) | Pasar **siempre `start` y `end` explícitos**: su horizonte por defecto se congela al importar el módulo, y los servicios de EIM corren días. Festivos codificados a mano y **sin cláusula de exactitud**: cualquier festivo que importe para una decisión se contrasta |
| **`pandas_market_calendars`** 5.6.1 | Complemento, **solo** si hacen falta CME Globex por sector o un FOREX 24/5 real | Mismo extra | MIT + **`NOTICE`** que declara su origen en `zipline` (Quantopian), Apache-2.0 | Hay que **conservar los dos avisos** (MIT y NOTICE). No tiene XETRA ni KRX nativos: para esos, la anterior |
| **`PyPortfolioOpt`** ==1.6.0 | Cartera en **T96** (comparación de optimizadores con las mismas restricciones) | Dependencia del venv, extra `portfolio` | MIT, `Copyright (c) 2018 Robert Andrew Martin`, coherente en las tres fuentes | **Fijar `==1.6.0`**: no declara `requires_python`, así que pip no protege. Vigilar el tope `scikit-base<0.14.0`. Es cartera, **no señales** |
| **`Riskfolio-Lib`** 7.4.1 | Segundo optimizador para contrastar en T96 | **Venv aparte**, nunca el venv vivo; escribe resultados a disco | BSD-3, `Copyright (c) 2020-2026, Dany Cajas` | **Arrastra `vectorbt` (Commons Clause) como dependencia obligatoria.** Por eso va aislado: la Commons Clause no entra en el entorno de la captura 24/7. Ninguna línea de `eim/` lo importa |
| **`NautilusTrader`** 1.231.0 | **Solo lectura** de su taxonomía de `Instrument` para diseñar la de T89. Si algún día se usa como comparador, en proceso aparte y **sin modificar** | Ni en el venv ni en `eim/` hoy; clon de lectura fuera del proyecto | LGPL-3.0 (`or-later` en 1.x) | **Prohibido copiar o modificar su código**: la LGPL contagiaría a `eim/`. Se copia el **patrón** (base común + variante por tipo de contrato), no el código. Y **no hay clase de renta fija**: la de bonos hay que diseñarla. Su compatibilidad con 3.12 **caduca en la v2** (exige ≥3.13) |
| **LEAN**, **Qlib**, **vectorbt**, **ib_async** | **Referencia de lectura.** LEAN: `IBuyingPowerModel` y los modelos de margen de perpetuos como plantilla del veto de `eim/risk` (T92). Qlib: `DataHandlerLP`, `TSDataSampler` y sus procesadores *point-in-time* (T90), y su `restricted_pickle_load` como patrón de seguridad. vectorbt: ideas de barrido para el embudo de T93, que se escribe con NumPy propio. ib_async: informativo para T103 | Fuera del proyecto, clones de lectura | Apache-2.0 · MIT · Apache-2.0 **+ Commons Clause** · BSD-2 | **Nada se instala.** De Qlib, si se porta un fragmento, se trae el aviso MIT a mano (su rueda puede no incluirlo). De vectorbt no se copia código: su cláusula impediría vender EIM y se transmitiría por distribución. De ib_async, nada: manda el token de IB en la URL y guarda contraseñas en claro |

**Nota de procedencia.** Los clones de esta auditoría viven en `C:\t88clones\`, **fuera de
`TRADINGBOT`**, y son desechables. Cuatro de ellos traen `AGENTS.md` o `CLAUDE.md` en la raíz: no se
clonan dentro del árbol del proyecto, para no inyectarle instrucciones ajenas.

## 2. Proveedores de datos que entran

Nivel: **1 investigación** (estudiar, no operar ni publicar) · **2 operativa** (licencia y límites
claros) · **3 ejecución** (autorizada por un intermediario). Hoy **no hay ninguna de nivel 3**, y
no hace falta: el alcance es solo análisis.

### 2.1 Entran ya, gratis y con licencia limpia (nivel 2)

| Fuente | Clase y papel | Licencia y condiciones anotadas | Límites |
|---|---|---|---|
| **Binance `fapi`** | Cripto (567 perpetuos) y **TradFi (246)**: OHLCV 1 m-1 w, índice, marca, *premium*, funding, interés abierto. La fuente primaria de la fase 17 | **Términos de datos de la API: NO VERIFICADOS** (§5.6). Se usa porque ya está en uso desde T03 y no añade licencia nueva, **no porque se haya comprobado el permiso** | 2 400 *weight*/min por IP. Operar TradFi exigiría firmar `POST /fapi/v1/stock/contract`: **no se ha firmado nada** |
| **FRED / ALFRED** | Macro, tipos, FX; y los *vintages* para el *point-in-time* de T90 | Clave gratuita con **atribución obligatoria**: «This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.» Las series con copyright de terceros, **solo uso personal** | Sin cifra publicada: solo banda «razonable». *Vintages* desde 2006 |
| **US Treasury** | Curva par diaria de EE. UU., 14 plazos, para T100 | «offered free, without restriction, and available to copy, adapt, redistribute, or otherwise use». **No nombran ninguna licencia** (ni dominio público ni CC): se anota como reutilización declarada, no como licencia | Sin clave y sin límites publicados. Desde 1990-01-02; se actualiza ~15:30 ET |
| **BCE** (tipos de referencia y Data Portal SDMX) | FX de referencia y curva AAA del euro | «users of this website may make free use of the information obtained directly from it», **citando al BCE como fuente** | Sin clave. EUR/USD diario desde 1999-01-04 (verificado) |
| **Frankfurter** | FX diario, envoltorio cómodo de los datos del BCE | Código **MIT**; los datos son del BCE, con su misma condición de cita | **Sin cuotas y sin clave** (verificado). Histórico diario largo |
| **Binance Vision** | Archivo histórico (ya en uso en `eim/data/providers/liquidations.py`) | **CC BY-NC-SA 4.0** (v1.0, 2026-08-26). Permite «algorithmic historical backtesting for purely personal non-production research». **Prohíbe la ejecución en real y la distribución de señales** | **Dos condiciones duras**: (a) el día que haya dinero real, estos datos **no pueden estar en la cadena**; (b) cualquier derivado que se publique arrastra **CC BY-NC-SA 4.0 y la atribución** |

### 2.2 Entran aisladas, para investigación (nivel 1, modo B)

| Fuente | Papel | Condiciones anotadas |
|---|---|---|
| **Stooq** | Histórico diario largo de acciones, índices, FX y futuros, solo para estudio | «This data is intended solely for personal use. Any commercial use is prohibited» y sin redistribución. **Hoy exige navegador real** (devuelve verificación JavaScript a `curl`): **no se construye ingesta automatizada contra ella**, y no se sortea la verificación. Los índices de S&P DJI que sirve llevan licencia propia |
| **Massive** (ex Polygon.io) | Contraste de precios de acciones, si hace falta | Gratis = EOD y **2 años**, 5 req/min. Borrado en 30 días al cancelar; los datos de CME se purgan «immediately» |
| **Twelve Data** | Contraste multi-bolsa | Prohíbe el uso comercial del nivel gratuito, y limita el almacenamiento a plazos «specified in the Documentation» **que no se pudieron localizar**: mientras no se lean, **no se almacena nada suyo** |

### 2.3 Entran solo si el usuario decide gastar (renta variable)

**Esta es la única decisión de dinero de la lista.** No hay fuente de renta variable gratuita con
licencia limpia: la única sin coste es Yahoo vía `yfinance`, y no tiene licencia de datos.

| Fuente | Coste | Licencia y condiciones anotadas |
|---|---|---|
| **EODHD** (recomendada) | Plan de pago | **El único proveedor que autoriza por escrito guardar los datos**: los Non-Professional «are permitted to store, manipulate, and analyze the data for private, non-commercial purposes». Es exactamente lo que un almacén local necesita |
| **Tiingo** (alternativa) | 0-30 $/mes | 30+ años de histórico. «For Basic and Power accounts, data is for internal and personal use only» y «You may not redistribute the data in any form» |

**Recomendación:** no gastar todavía. T97 (renta variable) no puede dar un veredicto honesto hasta
cerrar el hueco del **ajuste por *splits* y dividendos** (§5.1, alerta 9), que ningún proveedor
documenta en sus páginas. Primero se comprueba endpoint por endpoint con el plan gratuito, y solo
entonces se decide el gasto.

## 3. Descartados, con motivo

| Candidato | Motivo del descarte |
|---|---|
| **OpenBB** (meta-paquete) | 250 paquetes en el *lock*; `eval()` en código de producción que **escribe módulos Python en disco**; tres licencias en tres años (MIT → AGPL-3.0 → Apache-2.0 solo desde 5.0.0); claves de proveedores en claro en el perfil del usuario. Baja de «reevaluar» (T87 §5) a **descartado**. Se conserva su **catálogo de fuentes públicas sin clave** (CFTC, FINRA, SEC, Fama-French, FRED, ECB, EIA) para implementarlas **directamente contra la API del emisor** |
| **QuickFIX** | Licencia propia no OSI con atribución obligatoria, PyPI sin metadatos de licencia, ninguna rueda para cp312/win_amd64 (habría que compilar C++17) y EIM no tiene contraparte FIX. Confirma el «no» provisional de T87 §5 |
| **QuestDB** | Apache-2.0 impecable, pero exige un servidor Java permanente en un equipo de 4 núcleos y 16 GB donde ya corren 24/7 la captura y el bróker simulado. DuckDB 1.5.6 + Parquet cubren el caso. Reevaluar **solo con volumen medido**, como ya decía T87 §5 |
| **`yfinance` / Yahoo** | **Sin licencia de datos.** Los Términos de Yahoo prohíben la recolección automatizada y usar su contenido «to create any database, archive». Funciona, pero el derecho no existe. **Es dependencia de producción hoy** → ver §4 |
| **FMP** | «may not copy or download any content … except with the prior written approval of FMP» y borrado obligatorio «including data cached»: incompatible con un almacén local |
| **exchangerate.host** | 100 peticiones/mes y licencia no legible |
| **Nasdaq Data Link / Quandl** | Ha dejado de ser fuente gratuita de series: el filtro «Free» devuelve hoy un solo conjunto, y los futuros continuos ya no están |
| **Alpha Vantage** | 25 peticiones/día y **ninguna cláusula de almacenamiento**: no se puede saber si guardar está permitido |
| **SimFin, Sharadar** | Licencia de datos no publicada (SimFin) y sin precios ni términos públicos (Sharadar). Ningún proveedor entra sin condiciones anotadas |
| **CME DataMine** | Única vía legítima a tick real de futuros, pero exige cuenta y licencia y el precio no es público. Queda como referencia para cuando haya una clase que lo justifique |
| **Series continuas de futuros gratis** | **No existen con *roll* documentado.** Stooq da 11 460 sesiones de `CL.F` con volumen e interés abierto a 0 y sin metodología; los símbolos de Yahoo son el vencimiento más cercano, no una serie empalmada |
| **Tick y bid/ask intradía de FX gratis** | No existe. Lo gratuito es un punto de referencia al día, y el volumen de FX spot no existe como dato consolidado |
| **RD-Agent, FinRL, Zipline-reloaded** | Se mantienen fuera, como ya decidió T87 §5. No se auditaron: no estaban en el alcance de T88 |

## 4. Dos cosas que hay que arreglar en lo que ya existe

No son tareas nuevas de la fase 17: son deudas que esta auditoría ha encontrado en el código de hoy.

1. **`yfinance` es dependencia de producción y no tiene licencia de datos.** Está en
   `dependencies` de `v2/pyproject.toml` (no en un extra), instalado, y lo usa
   `eim/data/providers/multi_asset.py` para `^GSPC` y `^IXIC` en el visor y la estacionalidad.
   **Propuesta:** sustituir esos dos activos por `SPYUSDT` y `QQQUSDT` de Binance —mismo proveedor
   y misma licencia que el resto del visor, y además 24/7, lo que elimina el caso raro de los
   índices sin velas de 4 h— y sacar `yfinance` de las dependencias. Es un cambio pequeño y cerrado;
   va al BACKLOG como tarea de T89/T90 salvo que el usuario prefiera hacerlo ya.
2. **El nombre «Polygon» y las referencias a Nasdaq Data Link, si aparecen en documentos del
   proyecto, están desactualizados**: `polygon.io` redirige a `massive.com` y el catálogo gratuito
   de Nasdaq Data Link ya no existe. Una pasada de búsqueda y corrección, al BACKLOG.

## 5. Lo que esta lista NO resuelve

Está todo en la auditoría (§3.6, §5.6, §6); lo que importa para decidir:

1. **Las comisiones de los perpetuos TradFi de Binance.** Sin cifra con fuente, **T92 no puede
   modelar el costo de esa clase**, y sin costo no hay veredicto de rentabilidad. Es el hueco que
   más pesa.
2. **Los términos de datos de la API REST de Binance** (almacenamiento local, redistribución): la
   página legal devuelve cuerpo vacío. Abierto desde T33. Nada lo bloquea mientras sea análisis
   personal, pero no está verificado.
3. **El ajuste por *splits* y dividendos** en todos los proveedores de acciones.
4. **246 instrumentos TradFi con mediana de 134 días de histórico y ninguno de un año.** No es un
   hueco de licencia: es un límite físico. Cualquier tarea que prometa validar algo en esa clase
   (T95, T97, T101) tiene que decir antes qué potencia tiene con 4 meses de datos.
5. **El *roll* de los futuros tradicionales**, que deja a T99 sin histórico utilizable.

## 6. ◆ Lo que se le pide al usuario

Una respuesta a cada punto; con la 1 basta para desbloquear T89–T100.

1. **¿Se aprueba la lista de los apartados 1 y 2?** (entran: `exchange_calendars`,
   `pandas_market_calendars`, `PyPortfolioOpt` en el venv; `Riskfolio-Lib` aislado;
   NautilusTrader/LEAN/Qlib/vectorbt/ib_async solo como lectura; y como datos: Binance `fapi`,
   Binance Vision, FRED/ALFRED, US Treasury, BCE, Frankfurter, más Stooq, Massive y Twelve Data
   aisladas.)
2. **Renta variable (§2.3): ¿se autoriza gastar en EODHD o Tiingo, o se espera?** La recomendación
   es **esperar** hasta cerrar el hueco de *splits* y dividendos con los planes gratuitos.
3. **`yfinance` (§4.1): ¿se sustituye ya por `SPYUSDT`/`QQQUSDT` de Binance, o va al BACKLOG?**
4. **¿Se acepta que los 246 perpetuos TradFi entren como universo de *observación* en T93, pero que
   ninguna tarea publique un veredicto de rentabilidad sobre ellos hasta que haya más histórico y
   una cifra de comisiones con fuente?** La recomendación es sí: es la única forma de usarlos sin
   faltar a la regla de no presentar como real lo que no está medido.

## 7. Respuesta del usuario (2026-11-20)

**Punto 1: APROBADO.** Las listas de los apartados 1 y 2 quedan cerradas y son la dependencia
declarada de T89-T100: ningún repositorio ni proveedor fuera de ellas entra en esas tareas sin
volver a pasar por una decisión como esta. Los descartes del apartado 3 quedan en firme.

**Puntos 2, 3 y 4: sin respuesta todavía.** No bloquean T89 ni T90-T91. Lo que implica dejarlos
abiertos:

- **2 (renta variable de pago):** mientras no se decida, no se contrata nada. T97 no tiene
  proveedor de acciones asignado y el hueco de *splits* y dividendos (alerta 11) sigue abierto.
- **3 (`yfinance`):** sigue siendo dependencia de producción sin licencia de datos. Queda anotado
  en BACKLOG T88 y en los problemas conocidos de `PLAN/ESTADO_PROYECTO.md`.
- **4 (universo TradFi):** hasta que se diga lo contrario se aplica la recomendación por defecto,
  que es la única compatible con la regla de no presentar como real lo que no está medido: los 246
  perpetuos TradFi se **observan** en T93 y ninguna tarea publica un veredicto de rentabilidad
  sobre ellos mientras no haya más histórico y una cifra de comisiones con fuente.
