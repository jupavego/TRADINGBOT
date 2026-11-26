# T100 — Renta fija, derivados y opciones: viabilidad y modelos propios

Fecha: 2026-11-26 · Modo **ANÁLISIS** (nada de esto ejecuta ni vota) · Fase 17, último puesto del
orden aprobado en la ◆ de T87 («renta fija, derivados y opciones: **solo viabilidad**») ·
Proveedores: solo los de la lista cerrada de la ◆ de T88 · **◆ pendiente del usuario (§5)**.

Regla de este informe: ninguna cifra de precio o de costo sin fuente; lo que no se pudo
comprobar dice «no disponible» o «no verificado».

## 0. Resumen

- **Los modelos existen y están validados** contra valores publicados (Hull, Fabozzi, Haug,
  Diebold–Li): bono, curva (Nelson–Siegel, Svensson, *bootstrap*), carry/roll-down,
  Black–Scholes generalizado con griegas, volatilidad implícita y calidad de una cadena (§2).
- **Datos gratis y con licencia clara solo hay para las curvas** (Tesoro de EE. UU., BCE) y los
  tipos de referencia. Con eso se construyeron los dos agentes de prueba de renta fija (curva y
  carry) y una sonda sobre datos reales (§3).
- **Nada de esto se puede negociar hoy** dentro del alcance aprobado (solo simulado, sin
  intermediarios: ◆1 de T87). Bonos, futuros de bonos, repos y swaps quedan como **dato o como
  costo de financiación**, no como clase operable.
- **El candidato más prometedor no es la renta fija: son las opciones cripto como fuente de
  información** sobre BTC/ETH. T165 ya demostró con pre-registro que la volatilidad implícita de
  Deribit (la pendiente del DVOL) mejora la previsión de volatilidad de BTC. Sus cadenas son
  públicas y gratuitas, pero **Deribit (cadenas) no está en la lista de T88**: entrarlas exige tu
  decisión y verificar sus términos (§4, §5).

## 1. Qué se puede obtener, gratis y con licencia clara

| Dato | Fuente | Nivel (◆ T88) | Licencia / condición | Estado en T100 |
|---|---|---|---|---|
| Curva soberana EE. UU. (par diaria, 14 plazos de 1 mes a 30 años) | US Treasury (CSV sin clave) | **2** | «offered free, without restriction»; no nombra licencia | **Comprobada el 2026-11-26**: responde sin clave; último dato 2026-11-25 (10 años 4,85 %, 2 años 4,61 %, 3 meses 4,34 %, 30 años 5,24 %). Proveedor nuevo `eim/data/providers/treasury.py` |
| Curva AAA del euro (parámetros Svensson + tipos cero) | BCE, Data Portal SDMX | **2** | Uso libre citando al BCE | **No verificada desde la nube** (el portal no respondió al lector). La sonda la descarga en la laptop y contrasta la fórmula (§3.3) |
| Tipos de referencia (SOFR, fondos federales, rendimientos de vencimiento constante) | FRED / ALFRED | **2** | Clave gratuita y atribución obligatoria | Ya hay cliente (`fred.py`, para publicaciones macro); las series de tipos no están cableadas. Sin `EIM_FRED_API_KEY` no hay nada |
| €STR | BCE | **2** | Citar al BCE; si su aviso añade algo, **no verificado** (T88 §5.6, 13) | No cableado |
| Spreads de crédito (índices OAS) | FRED (series de terceros) | **1** | Copyright de terceros: **solo uso personal** (condición de FRED, T88) | Solo investigable; su histórico en FRED no se verificó |
| ETF de renta fija como representante (bonos a corto, a 10 años, a largo, crédito) | Ningún proveedor aprobado | — | La ◆2 de T88 (proveedor de acciones de pago) **sigue sin responder**; `yfinance` descartado | **No disponible.** Si Binance lista perpetuos TradFi sobre ETF de bonos sería el camino sin licencia nueva: **no verificado** (BACKLOG) |
| Precios de bonos concretos (por emisión) | — | — | Ninguna fuente gratuita con licencia en la lista de T88 | **No disponible**: la curva par es un ajuste, no un precio negociable |
| Futuros de bonos (2, 5, 10, 30 años) | CME DataMine | 3 potencial | Exige cuenta y licencia; **precio no público** (T88) | No disponible; series continuas gratis con *roll* documentado **no existen** (T88) |
| Cadenas de opciones cripto (BTC, ETH) | Deribit API pública; Binance opciones europeas | **fuera de la lista** | API pública sin clave; **términos de datos no verificados** (igual que Binance `fapi`, T88 §5.2) | Endpoints documentados por cada plaza; **no se descargó nada en T100**. Deribit ya se usa, solo para el índice DVOL, desde T165 |
| Cadenas de opciones de acciones/índices EE. UU. | Massive (ex Polygon) | **1, proceso aislado** | Gratis = fin de día y 2 años, 5 peticiones/min; borrado al cancelar (T88) | Solo investigación; datos de calidad: **de pago, precio no verificado** |
| Repos, operaciones de financiación, swaps de tipos, bonos corporativos ilíquidos | — | — | **OTC sin cotización pública** | **Solo investigables**; los repos entran como **costo de financiación** (SOFR/€STR) |

## 2. Modelos mínimos con pruebas (funciones puras)

Todo en `v2/eim/fixed_income/` y `v2/eim/options/`, sin red, sin disco y sin estado; las pruebas
están en `v2/tests/fixed_income/` y `v2/tests/options/`.

| Pieza | Módulo | Validación (referencia publicada → resultado) |
|---|---|---|
| Precio ↔ rendimiento, duración de Macaulay y modificada, convexidad, DV01, cupón corrido | `bond.py` | Hull §4.8–4.9: bono 3 años, 10 % semestral, 12 % continuo → **94,213 / 2,653 años / 7,570** (exactos). Fabozzi: 20 años, 9 % semestral al 6 % → **134,6722** y convexidad **164,106** (exactos). Derivadas contra diferencias finitas |
| Curva Nelson–Siegel y Svensson (parametrización τ del BCE), ajuste determinista | `curve.py` | Diebold–Li: λ = 0,0609 → máximo de la curvatura a ~30 meses (29,4) y L2 máxima en x = 1,7933. Recupera parámetros conocidos con error < 1e-10. Contraste en vivo con el BCE en la sonda |
| *Bootstrap* de tipos cero desde bonos y desde la curva par | `curve.py` | Hull §4.5: **10,127 / 10,469 / 10,536 / 10,681 / 10,808 %** (exactos). Curva par plana y par → cero → par |
| Carry y roll-down con la curva quieta | `carry.py` | Identidades exactas: sin roll-down en curva plana; carry + roll-down = integral del tipo a plazo = rendimiento logarítmico del cupón cero; bono con cupón por revalorización completa |
| Black–Scholes generalizado (`b`: acción, dividendo, divisa, Black-76) y griegas | `black_scholes.py` | Hull 15.6: **4,76 / 0,81**. Hull 19.x: **2,40; Δ 0,522; Γ 0,066; vega 12,1; θ −4,31; ρ 8,91**. Haug: **2,1334**, Merton **2,4648**, Black-76 **1,7011**, Garman–Kohlhagen **0,0291**. Griegas contra diferencias finitas |
| Volatilidad implícita (con cotas de no arbitraje antes de resolver) | `implied_vol.py` | Hull §15.11: c = 1,875 → **σ = 23,5 %**. Ida y vuelta en 24 casos (se omiten los 4 sin valor temporal medible); fuera de cotas → `NoImpliedVol` con motivo |
| Calidad de una cadena (cruces, horquillas, monotonía, convexidad, paridad) y resumen (σ ATM, pendiente 90/110) | `chain.py` | Cadena sintética con sonrisa conocida: recupera la σ ATM (±0,2 pt) y la pendiente; detecta cruzadas, horquillas anchas, mariposa negativa y paridad rota |

**Lo que estos modelos no cubren** (fuera de alcance): opciones americanas (ejercicio anticipado:
las de acciones sueltas de EE. UU. lo son, Black–Scholes no basta), entregable más barato de los
futuros de bonos, curvas de crédito por emisor, convexidad de futuros frente a forwards y
calendarios de cupones reales (conteo de días por convención).

## 3. Agentes hermanos especificados (uno de prueba por familia si hay datos)

Ninguno está en el registro de agentes, ni vota en la síntesis, ni toca plan, riesgo o bróker.
Para que alguno pase a ser un agente de verdad tiene que cumplir la lista de 8 puntos de T87 §9
(registro, datos con licencia, calidad contra calendario, capacidades declaradas, costos,
simulación, validación con pre-registro y multiplicidad ampliada, no regresión de BTC/ETH).

### 3.1 Familia «curva» — **implementado de prueba** (`proto.curve_state`)

- **`requires`**: `DataCapability.CURVE` (≥ 6 plazos del día).
- **Entrada**: curva par del día (Tesoro; con el BCE, la misma interfaz).
- **Salida**: nivel, pendiente y curvatura empíricas de Diebold–Li (10 años; 10a − 3m;
  2·2a − 3m − 10a), 2s10s, inversión y calidad del ajuste Svensson/NS. **Informante: sin
  sesgo** (no hay instrumento sobre el que opinar dentro del universo operable).
- **Costos**: datos 0 € (Tesoro); cómputo despreciable (ajuste por rejilla, < 1 s).
- **Validación propuesta**: solo como contexto de BTC/ETH (¿la pendiente o sus cambios
  anticipan la volatilidad o el régimen?), con pre-registro y en la familia ampliada de T95.
  Sin esa validación no entra en ninguna decisión.
- Aviso medido sobre la curva real del 2026-11-25: Svensson la reproduce con **1,5 pb** de
  error medio, pero sus β salen **mal identificados** (τ en el borde de la rejilla, β0 = 1,5 %
  con el 10 años al 4,85 %). Por eso el agente publica las medidas empíricas y usa Svensson
  solo para interpolar.

### 3.2 Familia «carry» — **implementado de prueba** (`proto.carry_state`)

- **`requires`**: `DataCapability.CURVE` + ≥ 61 días hábiles del plazo (volatilidad) + tipo de
  financiación (hoy, la letra del mismo horizonte como aproximación declarada; con FRED, SOFR).
- **Salida**: carry, roll-down, financiación y exceso (pb del horizonte), volatilidad del
  rendimiento (60 días), exceso/riesgo («Sharpe ex ante»), punto muerto (pb que puede subir el
  tipo antes de perder) y un **sesgo sobre la duración** (largo en el cupón cero del plazo) con
  confianza fija 0,2 por ser prototipo.
- **Costos**: datos 0 €; cómputo despreciable.
- **Validación propuesta**: el rendimiento realizado de un cupón cero sintético se calcula con
  la propia curva del Tesoro (histórico desde 1990, gratis), así que la hipótesis «el carry
  ex ante predice el exceso realizado» se puede contrastar **sin comprar datos**, como
  validación pre-registrada al estilo de T164/T165 (no es reconstruir el historial del bróker).
  Aun pasando, no hay instrumento negociable en el alcance: serviría como informante.

### 3.3 Sonda sobre datos reales (`v2/scripts/fixed_income_probe.py`)

La corre `aplicar_t100.cmd` en la laptop (allí hay red): descarga la curva del año en curso y
del anterior, corre los dos agentes (carry en 2, 5, 10 y 30 años) y **contrasta la fórmula de
Svensson con el BCE** (parámetros publicados frente a los tipos cero que publica el propio BCE;
tolerancia 0,5 pb). Resultado en `v2/reports/fixed_income_probe.md`; sin red, todo queda «no
disponible». En la nube, con el último día real: carry + roll-down de un cupón cero a 10 años
en 3 meses ≈ **+121 pb + 10 pb − 107 pb de financiación = +24 pb** (curva del 2026-11-25; la
volatilidad y el exceso/riesgo necesitan el histórico, que da la sonda).

### 3.4 Familia «opciones / volatilidad implícita» — **especificado; sin datos aprobados**

- **`requires`**: `DataCapability.OPTION_CHAIN` (cotizaciones con dos lados de al menos un
  vencimiento que cubra el forward) + subyacente + tipo.
- **Salida propuesta**: σ ATM por vencimiento (estructura temporal), pendiente de la sonrisa
  (90/110 y 25-delta), prima de varianza frente a la realizada, calidad de la cadena; sesgo
  **sobre la volatilidad de BTC/ETH** (no sobre la dirección), que es lo que T165 validó.
- **Pieza hecha**: `eim/options/chain.py` (calidad + resumen) sobre cualquier cadena.
  **No se conectó a ningún proveedor**: Deribit (cadenas) y Binance opciones no están en la
  lista de T88. Por eso no hay agente de prueba con datos reales en esta familia.
- **Costos**: datos 0 € (API pública); límites de petición de Deribit **no verificados**;
  almacenar cadenas cada hora pesa más que el DVOL (decenas de vencimientos × cientos de
  precios de ejercicio: volumen **no medido**).
- **Validación propuesta**: extender el marco de T165 (HAR-IV) con la superficie completa:
  ¿la pendiente de la sonrisa o la estructura temporal añaden algo a la pendiente del DVOL?
  Pre-registro, QLIKE, MCS y Holm como allí.

## 4. Veredicto por producto

Veredictos: **viable ahora** (datos gratis con licencia y modelo hecho) · **viable con datos de
pago** · **solo investigación** · **descartado**. «Ejecución» describe cómo se liquidaría en el
mundo real; dentro del alcance aprobado nada se ejecuta.

| Producto | Veredicto | Datos y costo estimado | Ejecución (liquidación, garantías, contraparte) |
|---|---|---|---|
| Curva soberana EE. UU. como **dato/contexto** | **Viable ahora** (análisis) | Tesoro, 0 € (comprobado) | No se negocia: es un dato |
| Curva AAA del euro como dato/contexto | **Viable ahora** (análisis) | BCE, 0 €, citando la fuente | Ídem |
| Bonos del Tesoro (posición en el bono) | **Solo investigación** | Precios por emisión: no disponibles gratis con licencia | Contado OTC entre intermediarios, liquidación T+1, custodia; exige intermediario (fuera de alcance, ◆1 T87) |
| ETF de renta fija | **Viable con datos de pago** (o con la ◆2 de T88) | EODHD o Tiingo, 0–30 $/mes (T88); perpetuos TradFi de Binance sobre ETF de bonos: no verificado | Acción al contado EE. UU. (T+1); en EIM, como acción (`EquityCostModel`, T92) |
| Futuros de bonos | **Viable con datos de pago** | CME DataMine, precio no público (T88); sin series continuas gratis | Cámara de compensación, margen inicial y de variación diaria, entrega física con entregable más barato (no modelado) |
| Repos / financiación | **Solo como costo de financiación** | SOFR (FRED) y €STR (BCE), 0 € | OTC bilateral o tripartito, recortes sobre la garantía, contrato marco; no es instrumento operable |
| Spreads de crédito (índices) | **Solo investigación** | FRED, series de terceros: solo uso personal | — |
| Bonos corporativos ilíquidos | **Descartado** | Sin cotización pública utilizable | OTC, liquidez escasa, riesgo de emisor |
| Swaps de tipos | **Descartado como clase** (solo investigación) | Sin datos gratis con licencia | OTC compensado en cámara, anexos de garantías |
| **Opciones cripto BTC/ETH** (como información) | **Viable ahora en análisis si apruebas la fuente** | Deribit / Binance, API pública, 0 €; términos no verificados | Europeas, liquidación en efectivo (Deribit en la moneda o en USDC según el contrato; Binance en USDT), vencimientos a las 08:00 UTC, margen de cartera; ejecución fuera de alcance |
| Opciones de acciones/índices EE. UU. | **Viable con datos de pago** | Massive gratis (2 años, fin de día, 5/min) para estudiar; calidad: de pago, precio no verificado | Americanas en acciones sueltas (ejercicio anticipado: hace falta otro modelo), europeas en índices; cámara OCC, T+1 |

## 5. ◆ Lo que se te pide

**¿Qué producto, si alguno, merece su propia clase (nuevas tareas) y con qué datos?**

**Recomendación:**

1. **Opciones cripto, solo como información sobre la volatilidad de BTC/ETH: sí, con una
   decisión previa de fuente.** Es la única pieza con evidencia a favor (T165), datos gratis y
   el mismo activo que EIM ya analiza. Supondría dos tareas nuevas: (a) verificar los términos
   de datos de Deribit (y de Binance opciones) y, si pasan, un colector de cadenas de baja
   frecuencia con su ficha de fuente; (b) el agente de superficie de volatilidad con
   pre-registro sobre el marco de T165, en la familia ampliada. Ninguna ejecución.
2. **Curva del Tesoro: sin clase propia.** Los dos agentes de prueba quedan fuera del registro
   como informantes; si quieres, una validación pre-registrada del carry con el histórico
   gratuito desde 1990 (tarea pequeña, opcional).
3. **Todo lo demás (bonos, ETF de renta fija, futuros de bonos, repos, swaps, opciones de
   acciones): no.** O no hay datos con licencia gratis, o no se puede negociar dentro del
   alcance, o ambas. Se revisa solo si T96/T97 arrancan en la revisión del 2026-12-29.

**Alternativas:** (A) ninguna clase: T100 se cierra con los modelos como biblioteca y la fase 17
sigue en pausa; (B) además de 1, el ETF de renta fija, que va atado a la ◆2 de T88 (proveedor de
acciones de pago) y por tanto a la revisión de T96/T97.

Hasta tu respuesta T100 queda **◐** (entregables 1–4 hechos, falta el 5).
