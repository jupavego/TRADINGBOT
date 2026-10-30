"""Inventario de todo lo persistente del proyecto (T125): qué es, dónde vive, cuánto importa,
cuál es su fuente oficial y cómo se conserva o viaja entre equipos.

Es la versión ejecutable de `docs/ALMACENAMIENTO.md` (un test exige que toda ruta de aquí
aparezca allí). `check` lo recorre para decir qué existe SOLO en este equipo.
Rutas relativas a `v2/` salvo las que empiezan por `~` (carpeta del usuario) o `@` (no son
archivos: variables de entorno, tareas de Windows).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CRITICAL, HIGH, MEDIUM, LOW = "crítica", "alta", "media", "baja"

GIT = "git (jupavego/TRADINGBOT)"
BACKUP = "copia diaria T115 + copia externa T125"
SHARE = "experiencia compartida T61/T117"
EXTRAS = "extras de la copia externa T125"
NONE = "no viaja"


@dataclass(frozen=True)
class Item:
    path: str
    what: str
    importance: str
    truth: str          # fuente oficial
    keeps: str          # cómo se conserva / viaja
    regenerable: bool = False


ITEMS: tuple[Item, ...] = (
    # --- código, tareas y conocimiento: git ----------------------------------------------
    Item("eim", "código fuente de la aplicación (API, agentes, riesgo, ejecución, web)",
         CRITICAL, GIT, "git: ramas + PR; `check` avisa de lo no subido"),
    Item("eim/risk/versions", "versiones de los parámetros de riesgo (papel, testnet, copia, "
         "arbitraje, HFT)", CRITICAL, GIT, "git (inmutables, SHA-256 sellado en cada decisión)"),
    Item("eim/paper/params.py", "perfiles del bróker simulado (Conservador, Moderado, "
         "Agresivo), SL/TP y escalera de protección (`ladder_params.py`)", CRITICAL, GIT, "git"),
    Item("eim/calibration/versions", "versiones de calibración", HIGH, GIT, "git"),
    Item("eim/validation/versions", "criterios de la puerta de validación", HIGH, GIT, "git"),
    Item("reports", "informes generados versionados (puerta de edge, escuadrón, A/B…)", HIGH,
         GIT, "git; lo no versionado (p. ej. `reports/operation/`) va en los extras"),
    Item("../PLAN", "tareas, estado, backlog, notas, bitácora de sesiones", CRITICAL, GIT, "git"),
    Item("../CLAUDE.md", "protocolo de sesión de Claude y reglas", HIGH, GIT, "git"),
    Item("../.claude/skills", "skills del proyecto", MEDIUM, GIT, "git"),
    Item("~/.claude/projects", "memoria de Claude de este equipo (por ruta del clon)", MEDIUM,
         "cada equipo", EXTRAS + "; lo duradero se pasa a `PLAN/ESTADO_PROYECTO.md`"),
    # --- historial: bases DuckDB -----------------------------------------------------------
    Item("data/reports.duckdb", "reportes de agentes, decisiones de riesgo, operaciones "
         "simuladas (`sim_trades`), alertas, capital, pronósticos", CRITICAL,
         "el equipo que lo generó", f"{BACKUP}; {SHARE} (reports, sim_trades)"),
    Item("data/paper.duckdb", "bróker simulado: contextos por vela, ideas, operaciones con "
         "entrada/salida/SL/TP, validación (intentos, ventanas, veredictos), sugerencias, "
         "protección, instantáneas del panel", CRITICAL, "el equipo que lo generó",
         f"{BACKUP}; {SHARE} (paper_ctx, val_versions, val_windows)"),
    Item("data/leaders.duckdb", "capturas en vivo de líderes de Hyperliquid y copia simulada "
         "(irrepetibles)", CRITICAL, "el equipo que lo generó", f"{BACKUP}; {SHARE} (leader_*)"),
    Item("data/obs/obs.duckdb", "observatorio (derivado del spool)", MEDIUM, "derivado", BACKUP,
         regenerable=True),
    # --- estado de la máquina --------------------------------------------------------------
    Item("data/kill_switch.json", "kill-switch persistido", HIGH, "cada equipo", BACKUP),
    Item("data/operation", "latido, estado del servicio (libro simulado), registros JSONL",
         HIGH, "cada equipo", BACKUP),
    Item("data/machine_id", "identidad del equipo (procedencia de cada fila compartida)", HIGH,
         "cada equipo", "no se copia a otro equipo; queda anotada en la copia externa"),
    Item("data/leaders", "tableros, resumen de la copia simulada, metadatos y latido del "
         "servicio de líderes", MEDIUM, "servicio de líderes", EXTRAS + " (resumen y meta)",
         regenerable=True),
    Item("data/paper/arb_tests.json", "resultados de los escenarios de arbitraje simulado",
         MEDIUM, "cada equipo", EXTRAS),
    Item("data/arb_history", "capturas reales de libros para arbitraje (única profundidad)",
         MEDIUM, "cada equipo", EXTRAS),
    Item("data/share_config.json", "configuración del transporte de experiencia (sin claves)",
         MEDIUM, "cada equipo", EXTRAS + "; se rehace con `share setup`"),
    Item("data/share_repo", "caché de clones del repo de experiencia", LOW, SHARE, NONE,
         regenerable=True),
    Item("data/copytrading", "bitácora completa del replay de la copia simulada", LOW,
         "derivado", "se regenera con `python -m eim.leaders copy-sim`", regenerable=True),
    # --- mercado y capturas ------------------------------------------------------------------
    Item("data/candles", "velas de futuros (parquet)", LOW, "Binance", "se descargan solas",
         regenerable=True),
    Item("data/spot_candles", "velas spot (parquet)", LOW, "Binance", "se descargan solas",
         regenerable=True),
    Item("data/funding", "funding (parquet)", LOW, "Binance", "se descarga solo",
         regenerable=True),
    Item("data/calendar", "calendario económico", LOW, "Fed/BLS/BEA", "se descarga solo",
         regenerable=True),
    Item("data/micro", "captura de microestructura T23/T104 (trades, libro, liquidaciones)",
         HIGH, "el equipo que la capturó", "no viaja (GB); se poda sola; copia manual a disco "
         "externo si hace falta un tramo"),
    Item("data/micro_hft", "captura HFT T78 (libro L2, bookTicker…; ≈ 830 MB/día)", HIGH,
         "el equipo que la capturó", "solo el QC en la copia; crudos a disco externo a mano"),
    Item("data/library/index", "índice de la biblioteca de libros (T52)", LOW, "cada equipo",
         "se rehace con `python -m eim.library ingest`; los libros nunca se suben",
         regenerable=True),
    Item("data/roadmap_live", "hoja de ruta servida por el icono", LOW, GIT,
         "`python PLAN/build_roadmap.py`", regenerable=True),
    # --- copias -------------------------------------------------------------------------------
    Item("backups", "copias completas locales (mismo disco)", HIGH, "cada equipo",
         "copia externa T125 (versiones del repo privado de datos)"),
    # --- fuera de archivos --------------------------------------------------------------------
    Item("@EIM_*", "variables de entorno del usuario (claves de testnet, rutas, alias)", HIGH,
         "cada equipo", "nunca se suben; se ponen a mano (lista en `docs/OPERACION.md` §2)"),
    Item("@tareas de Windows", "inicio automático, vigilancia HFT, copia externa diaria", MEDIUM,
         "cada equipo", "scripts en git (`v2/scripts/instalar_*.ps1`)"),
    Item("@entornos externos", "Freqtrade (`D:/eim-bots`), Ollama, Tesseract, libros", MEDIUM,
         "cada equipo", "se instalan a mano (`docs/BOTS.md`, `docs/OPERACION.md`)"),
)


def local_path(item: Item, v2: Path, home: Path | None = None) -> Path | None:
    """Ruta en este equipo; None para lo que no es un archivo."""
    if item.path.startswith("@"):
        return None
    if item.path.startswith("~"):
        return (home or Path.home()) / item.path[2:]
    return v2 / item.path


def size_bytes(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    total = 0
    for q in p.rglob("*"):
        try:
            if q.is_file():
                total += q.stat().st_size
        except OSError:                    # parte compactada/borrada mientras se recorre
            continue
    return total
