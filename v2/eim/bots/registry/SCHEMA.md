# Ficha común de bot (`eim/bots/registry/<id>.json`)

Fijada en T56 (2026-10-19) **antes de puntuar**. T57 la convierte en un modelo pydantic inmutable
(`extra=forbid`) y carga las fichas con validación; mientras tanto la vigila
`tests/bots/test_registry_cards.py`. Un archivo = un bot; las estrategias empaquetadas
(`bot@estrategia`, unidad del catálogo) van dentro. Identificadores en inglés, textos en español.
La evidencia completa de cada ficha está en `PLAN/notas/T56_auditoria.md`.

## Campos
| Campo | Contenido |
|---|---|
| `id` | minúsculas y guiones; igual al nombre del archivo |
| `name`, `repo` | nombre; `owner/repo` de GitHub |
| `commit_sha` | SHA completo (40 hex) auditado (clon superficial `--depth 1`); es la versión que T57/T58 fijan |
| `commit_date`, `audited_at` | fecha del commit y de la auditoría (ISO) |
| `license` | `{spdx, file, sha256, head}`: licencia **del archivo real**, hash y primeras palabras. `spdx = "NONE"` si no hay archivo (un badge del README no cuenta) |
| `bot_class` | `D` direccional · `L` liquidez/inventario (market making, grid, DCA) · `IA` LLM/RL · `INFRA` marco o librería (no se puntúa como bot) |
| `integration_mode` | `A` portar lógica pura · `B` proceso aislado en modo señal, sin claves (obligatorio con GPL/AGPL) · `C` referencia (se reimplementa la idea con pruebas propias) · `D` descartar |
| `binance_markets` | subconjunto de `spot`, `usdm_futures` que **soporta el código** (verificado); `[]` si ninguno |
| `strategies` | `[{name, path, note}]` estrategias empaquetadas que expone (`path` relativo a la raíz del repo) |
| `dependencies` | dependencias relevantes (nativas, pesadas o sospechosas) y versión de Python exigida |
| `risks`, `reasons` | riesgos concretos; motivos del veredicto (frases con evidencia) |
| `verdict` | `usar` · `referencia` · `descartar` (misma escala que T04/T33) |
| `squad_proposal` | `propuesto` · `opcional` · `no` — lo que T56 **recomienda** llevar a T58; no es una aprobación |
| `approval` | `{state, by, at}`; `pendiente` hasta que **el usuario** apruebe por escrito (◆). Nadie más lo cambia |
| `operational` | `{checks: {O1..O8: puntos}, total}` según las reglas de abajo |
| `security` | `{checks: {S1..S9: bool}, notes: {Sx: motivo}, red_alerts: [R*], total, enabled}` según las reglas |
| `evidence` | `[{what, url}]` enlaces permanentes (commit fijado) a los archivos que sustentan el veredicto |
| `universe_ref` | número de fila en `T56_universo_bots.md` (o `null` si es un hallazgo de T56) |

## Puntuación operativa (0–100, checklist de peso fijo, sin juicio libre)
Mide si el bot se puede **operar como fuente de señal** dentro del escuadrón. No mide rentabilidad (T59).
| Id | Peso | Regla (se otorga el máximo o lo indicado; nunca valores intermedios inventados) |
|---|---|---|
| O1 | 20 | Último commit ≤ 90 días de `audited_at` → 20; ≤ 365 días → 10; más → 0 |
| O2 | 15 | Archivos de prueba automatizados (`*test*`) ≥ 20 → 15; 1–19 → 8; 0 → 0 |
| O3 | 15 | Soporte de Binance USDⓈ-M verificado en el código → 15; declarado pero no verificado → 8; solo spot → 5; ninguno → 0 |
| O4 | 15 | La señal se calcula sobre velas sin tocar el exchange (función pura o clase de estrategia ejecutable offline) → 15; separable con trabajo → 8; acoplada a la ejecución → 0 |
| O5 | 10 | Se instala en Windows con ruedas (wheels) y sin compilador → 10; exige compilador/Docker/WSL → 5; no corre en Windows → 0 |
| O6 | 10 | Versión fijable por SHA y salida reproducible (sin entrenamiento aleatorio ni datos en línea en la señal) → 10; con aleatoriedad o datos en línea que se pueden fijar → 5; no → 0 |
| O7 | 10 | Lógica de la estrategia documentada con parámetros (docs o comentarios suficientes para reproducirla) → 10; solo README → 5; nada → 0 |
| O8 | 5 | No exige cuenta, licencia de pago ni servicio de terceros para la parte que se usa → 5; si lo exige → 0 |

## Puntuación de seguridad (0–100) y habilitación
Nueve comprobaciones sí/no; cada una suma su peso si **se cumple**.
| Id | Peso | Se cumple si… |
|---|---|---|
| S1 | 15 | Hay código fuente y un archivo de licencia con texto reconocible |
| S2 | 15 | No implementa retiros ni transferencias entre cuentas (los nombres en campos de datos o en bibliotecas vendorizadas ajenas a la ruta de señal no cuentan) |
| S3 | 15 | Sin `exec`/`eval`/`pickle.load`/`joblib.load` sobre datos externos en la ruta de señal. Un uso se acepta **solo** si se leyó y es sobre archivos propios del bot; si no se revisó, no se cumple |
| S4 | 10 | Sin telemetría ni reporte saliente activo por defecto hacia el autor o terceros (una opción de pago o con clave propia, desactivada por defecto, no cuenta) |
| S5 | 10 | La señal se calcula sin claves de exchange (las claves solo aparecen en la parte de ejecución) |
| S6 | 10 | Sin dependencias sin licencia, deprecadas o abandonadas en la ruta de señal |
| S7 | 10 | No usa endpoints no documentados, sesión de navegador ni *scraping* |
| S8 | 10 | No descarga ni ejecuta binarios, instaladores o actualizaciones remotas en el uso normal |
| S9 | 5 | Tiene pruebas automáticas (O2 > 0) |

**Alertas rojas (veto).** Cualquiera deja la ficha en `enabled = false` aunque sume 100:
`R1` señuelo o sin código fuente (solo binario/APK/enlace de descarga) · `R2` sin licencia real (todos los derechos reservados) ·
`R3` exige o implementa retiros/transferencias · `R4` endpoints privados, sesión de navegador o *scraping* ·
`R5` plataforma que ejecuta código de terceros dentro de su propio proceso sin sandbox ·
`R6` procedencia dudosa (fork joven, cuenta nueva, popularidad atípica) · `R7` deserializa artefactos que descarga o recibe de terceros.
**Habilitación:** `enabled = (sin alertas rojas) y (total ≥ 70)`. La seguridad **no se compensa** con rendimiento ni con la puntuación operativa.
Una ficha `enabled = false` queda fuera del escuadrón (`deshabilitado_seguridad` en T59).

## Qué obliga cada modo
- **A** exige licencia permisiva (MIT, BSD, Apache-2.0, ISC, dominio público), lógica separable y registrar el origen en `THIRD_PARTY.md` si se copia código; se prefiere reimplementar con `eim/indicators` (T34). El código portado corre dentro del agente, sin I/O.
- **B** corre el bot en un entorno propio **sin claves** y sin red hacia el exchange; solo cruza datos por archivo o REST local; no se importa su código desde `eim/`. Es el único modo permitido para GPL/AGPL (§ licencias del informe).
- **C** y **D** no ejecutan ni copian nada.
