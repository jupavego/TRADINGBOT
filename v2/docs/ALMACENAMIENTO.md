# Dónde vive cada dato y cómo se conserva (T125)

Inventario de todo lo persistente del proyecto, con su **fuente oficial** y el mecanismo que lo
conserva o lo lleva a otro equipo. Su versión ejecutable es `eim/continuity/inventory.py` (un test
exige que toda ruta de allí aparezca aquí); `python -m eim.continuity check` lo usa para decir qué
existe solo en el equipo donde se ejecuta. Procedimientos: `docs/CONTINUIDAD.md`.

Rutas relativas a `v2/` salvo indicación. Tamaños y filas medidos en `laptop-i6pf9ovp-fce8d9` el
2026-10-30 03:00 UTC (copia `eim_20261030-030349`, 1 000 MB, verificada).

## 1. Fuente oficial por tipo de información

| Tipo | Fuente oficial | Cómo llega a otro equipo | Conflictos |
|---|---|---|---|
| Código, documentos, configuración versionada | GitHub `jupavego/TRADINGBOT` (**público**: nunca datos ni claves) | `git pull` / ramas + PR | git (revisión en PR) |
| Tareas, estado, backlog, notas, bitácora | `PLAN/` en el mismo repo | `git pull` | `PLAN/BITACORA.md` con unión automática (`.gitattributes`); `STATUS.md` por fila |
| Historial de experiencia (backtests, operaciones simuladas, contextos, validación, líderes) | La base del equipo que lo generó; la unión de todos, en el repo **privado** `Santivego/eim-shared-data` (una rama `machine/<id>` por equipo) | `python -m eim.data.share import` (simulacro) → `--apply` | Unión por clave natural: sin duplicar, sin pisar; diferencias → `share_conflicts` |
| Estado completo de un equipo (las bases tal cual, kill-switch, estado del servicio) | `v2/data` de ese equipo | Copia completa → copia externa (versión `eim-copias` del repo privado) → `offsite pull` + `backup restore` | Una identidad por equipo; `check` bloquea si dos equipos publican con la misma |
| Claves y variables `EIM_*` | Cada equipo | Nunca por red; a mano | — |
| Velas, funding, calendario | Binance / Fed / BLS / BEA | Se descargan solas | — |
| Capturas crudas de microestructura y HFT | El equipo que las capturó | No viajan (GB); disco externo a mano | — |

## 2. Inventario

### Código, tareas y conocimiento (git)
| Ruta | Qué | Importancia | Se conserva / viaja |
|---|---|---|---|
| `eim` | Código de la aplicación (API, agentes, riesgo, ejecución, web) | crítica | git: ramas + PR; `check` avisa de lo no subido |
| `eim/risk/versions` | Versiones de parámetros de riesgo (papel, testnet, copia, arbitraje, HFT); su SHA-256 se sella en cada decisión | crítica | git (inmutables) |
| `eim/paper/params.py` | Perfiles del bróker simulado (Conservador, Moderado, Agresivo), SL/TP y escalera de protección (`ladder_params.py`) | crítica | git |
| `eim/calibration/versions` | Versiones de calibración | alta | git |
| `eim/validation/versions` | Criterios de la puerta de validación | alta | git |
| `reports` | Informes generados versionados (puerta de edge, escuadrón, A/B…) | alta | git; lo no versionado (`reports/operation/`, informe semanal del servicio) va en los extras de la copia externa |
| `../PLAN` | Tareas (`STATUS.md`), `BACKLOG.md`, notas, `ESTADO_PROYECTO.md`, `BITACORA.md` | crítica | git |
| `../CLAUDE.md` | Protocolo de sesión de Claude y reglas | alta | git |
| `../.claude/skills` | Skills del proyecto | media | git |
| `~/.claude/projects` | Memoria de Claude **de este equipo** (carpeta por ruta del clon) | media | extras de la copia externa; lo duradero está en `PLAN/ESTADO_PROYECTO.md` |

### Historial (bases DuckDB; un solo proceso escritor por base)
| Ruta | Qué | Tamaño / filas | Importancia | Se conserva / viaja |
|---|---|---|---|---|
| `data/reports.duckdb` | Reportes de agentes, decisiones de riesgo, operaciones simuladas (`sim_trades`), alertas, capital, pronósticos | 206 MB · 9 tablas · 70 915 filas | crítica | copia diaria + copia externa; experiencia (`reports`, `sim_trades`) |
| `data/paper.duckdb` | Bróker simulado: contextos por vela, ideas, operaciones con entrada/salida/SL/TP y costos, validación (intentos, ventanas, veredictos), sugerencias, protección, instantáneas del panel | 91 MB · 12 tablas · 49 066 filas | crítica | copia diaria + copia externa; experiencia (`paper_ctx`, `val_versions`, `val_windows`) |
| `data/leaders.duckdb` | Capturas en vivo de líderes de Hyperliquid y copia simulada (**irrepetibles**: el exchange solo sirve las 10 000 ejecuciones más recientes). De los rechazados, 7 días de detalle y lo anterior archivado ya plegado (`leader_archive*`, T128) | 1 125 MB · 12 tablas · 5,17 M filas | crítica | copia diaria + copia externa; experiencia (`leader_*` salvo el archivo, `copy_journal`) |
| `data/obs/obs.duckdb` | Observatorio (derivado del spool JSONL) | 10 tablas · 894 k filas | media | copia diaria + externa; reconstruible |

Las operaciones simuladas conservan sus registros originales (no resúmenes): entrada, salida,
precios, horas UTC, SL/TP vigentes, costos y motivo de cierre están en `paper.duckdb` y
`reports.duckdb`; las relaciones (idea → operación → protección → veredicto) viajan con las bases
completas en la copia. Lo que el sistema «aprende» son datos, no un modelo opaco: intentos y
veredictos de la puerta de validación (`val_*`), contextos de los que salen las ideas
(`paper_ctx`), calibración versionada y la evidencia de líderes. No hay pesos entrenados fuera de
estas bases y de las versiones en git.

Excepción (T128): de los líderes rechazados, el grupo de control de la evaluación, la base viva
solo guarda 7 días de ejecuciones y cotizaciones del seguidor. Lo anterior queda plegado en
`leader_archive` y `leader_archive_trips` (viajes cerrados con su seguidor, latencias, tomadoras
y número de ejecuciones), lo justo para que la evaluación dé las mismas cifras. Con el detalle
se borra su procedencia de la unión T61 (`share_origin`). El detalle crudo
de esos días solo sigue en las copias diarias (14) y en las versiones de la copia externa.

### Estado de la máquina
| Ruta | Qué | Importancia | Se conserva / viaja |
|---|---|---|---|
| `data/kill_switch.json` | Kill-switch persistido | alta | copia diaria (`state/`) |
| `data/operation` | Latido, estado del servicio (libro simulado), registros JSONL por día | alta | copia diaria (`state/operation`) |
| `data/usage` | Registro de consumo (T127): CPU, RAM privada y prioridad por proceso cada 30 s; ~5–7 MB/día, los días cerrados en `.jsonl.gz`; 30 días. Desde T141, también la línea de órdenes recortada y la carpeta de los programas ajenos que pasan de un umbral | baja | no viaja, y por eso esas órdenes se quedan aquí: el registro de operación y el observatorio, que sí van en las copias, solo reciben las causas del aviso |
| `data/jobs` | Cola de trabajos pesados (T127): un JSON por trabajo, pasos por día y salida de cada uno; 14 días | baja | no viaja |
| `data/machine_id` | Identidad del equipo (`laptop-i6pf9ovp-fce8d9` aquí): procedencia de cada fila compartida | alta | no se copia a otro equipo; queda anotada en la copia externa |
| `data/leaders` | Tableros, resumen de la copia simulada (`copy_sim.json`), metadatos, latido | media | lo regenera el servicio; resumen y meta en los extras |
| `data/paper/arb_tests.json` | Resultados de los escenarios de arbitraje simulado | media | extras |
| `data/arb_history` | Capturas reales de libros para arbitraje (única profundidad disponible) | media | extras |
| `data/share_config.json` | Configuración del transporte de experiencia (sin claves). **No existe** en la carpeta viva de este equipo: T117 espera el visto bueno de los simulacros | media | extras; se rehace con `share setup` |
| `data/share_repo` | Caché de clones del repo de experiencia | baja | se regenera |
| `data/copytrading` | Bitácora completa del replay de la copia simulada (188 MB) | baja | se regenera con `python -m eim.leaders copy-sim` |

### Mercado y capturas
| Ruta | Qué | Importancia | Se conserva / viaja |
|---|---|---|---|
| `data/candles` | Velas de futuros (parquet, 88 MB) | baja | se descargan solas |
| `data/spot_candles` | Velas spot | baja | se descargan solas |
| `data/funding` | Funding | baja | se descarga solo |
| `data/calendar` | Calendario económico | baja | se descarga solo |
| `data/micro` | Microestructura del agente: fotos top-10 por segundo (`top`, de la captura HFT desde T128), liquidaciones en vivo y lo que dejó el recolector T23 (`trades`, `depth`, `gaps`: ya no crecen) (2,2 GB) | alta (irrepetible) | **no viaja**; se poda sola; para conservar un tramo, copiarlo a un disco externo |
| `data/micro_hft` | Captura HFT T78 (3,1 GB; ≈ 830 MB/día; poda a 45 días) | alta (irrepetible) | solo el QC en la copia; crudos a disco externo a mano |
| `data/library/index` | Índice de la biblioteca de libros (T52) | baja | se rehace con `python -m eim.library ingest`; los libros (`17.0 - TRADING\Books`) nunca se suben |
| `data/roadmap_live` | Hoja de ruta servida por el icono | baja | `python PLAN/build_roadmap.py` |

### Copias
| Ruta | Qué | Importancia | Se conserva / viaja |
|---|---|---|---|
| `backups` | Copias completas locales (14 retenidas, ≈ 1 GB cada una; mismo disco). `backups/remote/<equipo>/` = copias bajadas de otro equipo; `backups/archivo/` = copias apartadas a mano | alta | copia externa (versiones del repo privado de datos) |

### Fuera de archivos
| Ruta | Qué | Importancia | Se conserva / viaja |
|---|---|---|---|
| `@EIM_*` | Variables de entorno del usuario (claves de testnet, rutas, alias). En este equipo: **ninguna** definida | alta | nunca por red; a mano (lista en `docs/OPERACION.md` §2) |
| `@tareas de Windows` | Inicio automático del servicio, vigilancia HFT, copia externa diaria | media | scripts en git (`v2/scripts/instalar_*.ps1`) |
| `@entornos externos` | Freqtrade (`D:/eim-bots`, solo en el equipo de Juan Pablo), Ollama, Tesseract, libros | media | se instalan a mano (`docs/BOTS.md`, `docs/OPERACION.md`) |

## 3. Qué se perdería abriendo otro equipo sin migrar

Abrir el proyecto en otro equipo con solo `git clone` trae código, tareas y documentos, pero
**no** trae: las tres bases (todo el historial de operaciones simuladas, backtests, validación y
líderes), el kill-switch y el estado del servicio, la memoria de Claude de este equipo, las
variables `EIM_*`, las capturas de microestructura/HFT y los cambios sin confirmar de los
worktrees. Antes de T125 la API habría arrancado además con bases **vacías** sin avisar; ahora
`eim.operation run` se niega y `check` lo marca como BLOQUEO.
