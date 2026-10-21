# Auditoría de seguridad (T32, 2026-10-14)

Alcance: secretos, dependencias, superficie expuesta de la API, permisos de claves. Modelo de amenaza:
aplicación de un solo usuario en su propio equipo Windows; el atacante realista es **una página web
que el usuario visita** (CSRF, DNS rebinding, WebSocket entre sitios), **otro equipo de la red** o
**una dependencia vulnerable**. Sin dinero real: el peor caso hoy es alterar el papel/testnet o el
historial, pero la auditoría se hace como si hubiera dinero.

## Resultado
| # | Hallazgo | Severidad | Estado |
|---|---|---|---|
| S1 | La API no verificaba `Host` ni el origen del cliente. Una web con *DNS rebinding* (su dominio resuelve a 127.0.0.1) podía llamar a la API como «mismo origen» y saltarse CORS; lanzada con `--host 0.0.0.0` quedaba abierta a la red sin autenticación. | Alta | **Corregido**: `eim/api/security.py` (middleware ASGI): `Host` fuera de `EIM_ALLOWED_HOSTS` → 400; cliente no local → 403 salvo `EIM_API_TOKEN` + `Authorization: Bearer` (en WebSocket, subprotocolo `eim-token.<token>`, que la API devuelve al aceptar). |
| S2 | WebSocket `/v2/stream` aceptaba cualquier `Origin` (CORS no cubre WebSocket). Solo datos de mercado, pero cualquier web podía leerlos. | Baja | **Corregido**: `Origin` fuera de `EIM_CORS_ORIGINS` → cierre 1008. |
| S3 | `POST /v2/calibration/backfill` sin cabecera de confirmación: una web podía lanzarlo con un POST «simple» (escribe pronósticos en la base; CPU). | Media | **Corregido**: exige `X-EIM-Confirm: backfill`; UI actualizada. Test que recorre **todas** las rutas POST de la app y exige la cabecera (excepción documentada: `/v2/more/bitacora`, sin efecto lateral). |
| S4 | Subida de la bitácora sin límite de tamaño (memoria). | Baja | **Corregido**: `BodyLimitMiddleware` corta todo cuerpo > 41 MB con 413 antes de recibirlo entero (por `Content-Length` y contando si llega por trozos). |
| S5 | Vite 5 (servidor de desarrollo): `npm audit` 1 alta (bypass de `server.fs.deny` en rutas alternativas de Windows, path traversal en `.map`, fuga de hash NTLMv2 vía `launch-editor`) + 1 moderada (esbuild ≤ 0.24.2: cualquier web lee respuestas del servidor de desarrollo). | Alta (solo desarrollo) | **Corregido**: Vite 6.4.4 (compatible con Node 20.18+). `npm audit`: 0. Build y `tsc` OK. |
| S6 | Hash de la configuración de riesgo calculado sobre bytes crudos: con `core.autocrlf=true` (Windows) el archivo tiene CRLF y el `config_sha256` sellado en cada decisión difería entre equipos. | Baja (integridad/auditoría) | **Corregido**: hash sobre LF + `.gitattributes` (`eol=lf` en versiones) + `tests/test_param_versions.py` (inmutabilidad). |
| S7 | Dependencias Python | — | `pip-audit` sobre 94 paquetes del entorno: **sin vulnerabilidades conocidas**. `pip-audit` añadido a `[dev]`; política mensual en `docs/OPERACION.md` §5. |
| S8 | Secretos en el repositorio | — | **Limpio**: búsqueda en todo el historial (`git log --all -p`) de patrones de clave/secreto/token con valores largos: nada. Ningún `.env`, `.pem`, `.key` ni base `*.duckdb` versionado (`.gitignore`). `backups/` añadido a `.gitignore`. |
| S9 | Manejo de claves de exchange | — | **Correcto**: solo por entorno (`EIM_TESTNET_API_KEY/SECRET`); `Credentials.__repr__` oculta el secreto; el broker exige `https` y host en lista blanca de testnet (`testnet.binancefuture.com`, `demo-fapi.binance.com`) al construir y en cada cliente → una clave nunca viaja a producción. Las copias de seguridad no incluyen claves. `Settings.api_token` con `repr=False`. |
| S11 | Texto de libros (T52) | — | **Diseño**: el texto de los libros es dato; `eim/library/guards.py` marca las páginas con texto dirigido a un modelo (`pages_flagged` del catálogo, aviso en `search`) y nunca lo interpreta; T55 debe entregarlo al LLM como bloque de datos citado (como los titulares de T24). Libros e índice fuera de git (`.gitignore` + `tests/library/test_cards.py`) y nunca subidos a servicios. |
| S12 | Consulta a la biblioteca con LLM (T55) | — | **Diseño**: apagada por defecto (`EIM_LIBRARY_LLM=1` + `ANTHROPIC_API_KEY`). A la API de Anthropic solo viajan la pregunta, fichas parafraseadas y fragmentos ≤ 280 caracteres de ≤ 6 pasajes recuperados; nunca libros ni páginas enteras. Páginas con texto dirigido a un modelo no se envían; el resto va como JSON en `<library_data>` declarado no confiable; toda afirmación sin fuente entregada se descarta. Solo informa. `POST /v2/library/ask` exige `X-EIM-Confirm`. |
| S10 | Endpoints que escriben | — | Todos con `X-EIM-Confirm` (fuerza verificación previa CORS) y, desde S1, solo desde el propio equipo. Kill-switch solo se desactiva a mano; `REAL` prohibido por validación de configuración; ejecución solo por `OrderGateway` con `RiskDecision` sellada (HMAC de proceso, caduca a 60 s). |

## Permisos de claves (checklist antes de testnet)
1. Crear la clave **en la testnet** (`testnet.binancefuture.com`), nunca en la cuenta real.
2. Permisos: solo lectura + trading de futuros. **Sin retiro, sin transferencias universales.**
3. Restricción de IP a la IP pública del equipo si la testnet lo permite.
4. Guardarla en variables de entorno del usuario (no en archivos del repo, no en `.env` versionado).
5. Rotar si se sospecha fuga (`docs/RUNBOOK.md` §9).

## Riesgos aceptados / pendientes
- **Sin autenticación de usuario en la UI** (BACKLOG T29 (1), T31 (6)): mitigado por S1 (solo local).
  Si algún día se expone fuera de la máquina: `EIM_API_TOKEN` + HTTPS delante (proxy inverso) y
  autenticación real en la UI. No exponer a internet.
- Cualquier proceso local del mismo usuario puede llamar a la API (modelo de un solo usuario).
- `GET /v2/risk` registra decisiones (efecto lateral en GET; BACKLOG T29 (4)): sin impacto de
  seguridad tras S1, pero un GET entre sitios ya no llega (Host/Origin).
- La API en marcha durante la auditoría (corrida de papel T31) usa el código anterior: las
  correcciones S1–S4 y S6 entran en vigor al reiniciarla.

## Cómo repetir la auditoría
```bash
cd v2
python -m pip_audit
cd eim/web && npm audit && cd ../..
git log --all -p -G "(api[_-]?key|secret|token)\s*[=:]\s*['\"][A-Za-z0-9]{16,}" --oneline
git ls-files | grep -iE "\.env|secret|\.pem|\.key$|\.duckdb"
python -m pytest -q tests/api/test_security.py tests/test_param_versions.py
```

## Bots de terceros (T57)
Un bot público es código ajeno. El diseño asume que puede ser malicioso o estar mal hecho y limita lo que puede hacer, no lo que dice querer hacer:
- **Sin autoridad**: `BotSignal` solo tiene una postura (sin orden, tamaño ni claves; `extra="forbid"`). Las posturas pasan por síntesis → plan → riesgo (con veto) → `OrderGateway`, como cualquier otra opinión; el agente `bots` tiene peso 0 y está `excluded` hasta T59/T60.
- **Modo A** (licencia permisiva): se porta la regla (~10 líneas) y corre dentro del agente, sin I/O ni dependencias del bot. Hummingbot completo y `pandas-ta` (sin licencia) no se instalan.
- **Modo B** (GPL/AGPL o dependencias pesadas): `eim/data/bots/runner.py` lanza el bot en un intérprete aparte con **entorno por lista blanca** (ninguna variable que no esté en ella: ni `*_KEY/SECRET/TOKEN/PASSWORD`, ni `EIM_*`), `HOME` y directorio de trabajo nuevos y vacíos que se borran al terminar (sin `.env` ni configuración con claves), proxies muertos, `pip` sin índice y `HF_HUB_OFFLINE`; tiempo (se mata el grupo de procesos), memoria, CPU y tamaño de salida acotados (rlimit en POSIX); las velas entran por `candles.json` y la postura sale por `out.json`. El checkout del bot debe estar en el SHA fijado de la ficha y sin cambios locales, o no se ejecuta. Sin descargas en ejecución: el entorno y el checkout se preparan aparte (`docs/BOTS.md`).
- **Windows**: no hay aislamiento de red por proceso fiable ni rlimit de memoria; solo timeout y árbol de procesos. Se compensa con lo anterior (proceso sin credenciales —probado en `tests/bots/test_runner.py::test_subprocess_receives_no_credentials`—, proxies muertos y sin índice de paquetes), con la revisión del código del bot en T56 (S1–S9 y alertas rojas) y con que el bot solo recibe velas públicas. En Linux, si el sistema lo permite, se añade `unshare --net` (sin red); `RunResult.network_isolated` y `raw.isolation` dicen si se aplicó. Quien quiera más: ejecutar la API dentro de WSL2/contenedor sin salida a internet para el proceso del bot.
- **Passivbot (T58)**: el bot trae un archivo con códigos de bróker y lee `api-keys.json`; en el carril de simulación no se crea ni se entrega ninguno, no se instancia ningún exchange (solo `run_backtest` sobre arreglos) y la petición/salida solo llevan velas y fills. La compilación de su motor Rust (cargo descarga crates) es una instalación manual aparte, no parte de la ejecución.
- **Riesgo residual aceptado**: un bot modo B comprometido podría leer archivos del propio usuario que sean legibles desde su proceso (no hay *chroot*) y, en Windows, intentar red. No tiene claves, no ve la API ni el almacén (la API solo escucha en local y exige `X-EIM-Confirm`), y su salida se valida como datos. No se amplía el alcance sin otra auditoría.
- **Escuadrón integrado (T60)**: un bot solo puede votar tras superar la puerta de edge y la prueba marginal de T59, con peso medido y fuera de cuarentena; los de clase `L`/`IA` jamás votan. Ningún endpoint nuevo (`/v2/bots*`) acepta órdenes, tamaño ni apalancamiento, y el escaneo estático de `tests/api/test_security.py` sigue pasando. Si un bot que vota se degrada pierde el voto de inmediato (`data/bots/quarantine.json`). Los subprocesos de modo B siguen sin claves; sus límites en Windows son los de arriba (solo timeout y árbol de procesos, sin aislamiento de red por proceso).
