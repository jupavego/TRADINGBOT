"""Interruptores de configuración del mapa (T174): piezas construidas y apagadas a propósito.

Una pieza con `switch` en el catálogo que no está encendida en este equipo no es una avería
ni «sin datos»: el mapa la pinta «pausada» y dice qué variable la enciende. Solo se lee el
entorno (y la configuración de la experiencia compartida); nunca se muestran valores, solo si
están puestos. Encender algo de esto sigue siendo decisión del usuario.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path


def _share_cfg(data_dir: Path | None) -> dict:
    try:
        return json.loads((data_dir / "share_config.json").read_text(encoding="utf-8")) \
            if data_dir else {}
    except (OSError, ValueError):
        return {}


def _share_on(env: Mapping[str, str], data_dir: Path | None) -> bool:
    if env.get("EIM_SHARE_AUTO", "1") == "0":
        return False
    if env.get("EIM_SHARED_DIR") or env.get("EIM_SHARE_GIT_URL"):
        return True
    cfg = _share_cfg(data_dir)
    return bool(cfg.get("shared_dir") or cfg.get("git_url"))


def _share_wait(env: Mapping[str, str], data_dir: Path | None) -> str | None:
    """T196: configurada pero con encendido programado aún por llegar → la fecha; si no, None."""
    start = (env.get("EIM_SHARE_FROM") or _share_cfg(data_dir).get("start") or "").strip()
    if not start or start.lower() == "off":
        return None
    try:
        d = datetime.fromisoformat(start)
    except ValueError:
        return None
    d = d if d.tzinfo else d.replace(tzinfo=UTC)
    return start if datetime.now(UTC) < d else None


def _share(env: Mapping[str, str], data_dir: Path | None) -> str | None:
    if not _share_on(env, data_dir):
        return ("Apagado: no hay carpeta ni repo de experiencia compartida (EIM_SHARED_DIR / "
                "EIM_SHARE_GIT_URL o `python -m eim.data.share setup`). Solo hace falta con "
                "varios equipos.")
    if (start := _share_wait(env, data_dir)) is not None:
        return (f"Encendido programado (T196): configurada y dormida hasta {start} UTC; desde "
                "entonces une el libro central de los equipos sola, sin reiniciar.")
    return None


Check = Callable[[Mapping[str, str], Path | None], str | None]

CHECKS: dict[str, Check] = {
    "testnet": lambda e, _d: None if e.get("EIM_EXECUTION", "").lower() == "testnet" else
    "Apagado a propósito: la operación corre en papel. Se enciende con EIM_EXECUTION=testnet "
    "y claves de testnet, solo tras la puerta de edge (T27/T31).",
    "arb_testnet": lambda e, _d: None if e.get("EIM_ARB_EXECUTION", "").lower() == "testnet"
    else "Apagado a propósito: el arbitraje solo se analiza. Se enciende con "
    "EIM_ARB_EXECUTION=testnet, tras su prueba extremo a extremo (T45).",
    "hft_live": lambda _e, _d: "Construido y probado, pero aún sin servicio en vivo: lo arranca "
    "la tarea T85 (que depende de la puerta de T84).",
    "share": _share,
    "context_llm": lambda e, _d: None if (e.get("EIM_CONTEXT_LLM", "").lower() == "local"
                                          or e.get("ANTHROPIC_API_KEY")) else
    "Apagado: no hay modelo de lenguaje. Se enciende con Ollama (EIM_CONTEXT_LLM=local, lo "
    "pone servicio_continuo.ps1 si encuentra Ollama) o con ANTHROPIC_API_KEY.",
    "intermarket": lambda e, _d: None if e.get("EIM_INTERMARKET", "1") != "0" else
    "Apagado con EIM_INTERMARKET=0: no se descargan oro ni índices y el agente intermercado "
    "dice «sin datos». Se enciende quitando la variable (T183).",
    "video": lambda e, _d: None if e.get("EIM_VIDEO") == "1" else
    "Apagado: opcional. Se enciende con EIM_VIDEO=1 y la clave de YouTube (T64).",
}


def off_reason(switch: str | None, env: Mapping[str, str] | None = None,
               data_dir: Path | None = None) -> str | None:
    """None = encendida (o sin interruptor); si no, el motivo en lenguaje llano."""
    if not switch:
        return None
    check = CHECKS.get(switch)
    return check(os.environ if env is None else env, data_dir) if check else None
