"""Contrato `Prospect` y carga validada de los expedientes de T167 (T168, entregable 1).

`prospecto = agente@versión · regla nativa · marco · plantilla de salida · huella`. La huella,
como las versiones de T49, firma la regla (su código normalizado), sus parámetros, sus variables,
el marco, la plantilla y el tope de velas: cambiar cualquiera es **otro prospecto**, con otra
cuenta que empieza de cero y no hereda operaciones.

La carga falla fuerte si un prospecto pide una variable que su agente no expone (ni la declara su
expediente ni la sabe leer su módulo de reglas) o si su regla no existe.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable, Mapping
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, computed_field

from eim.nursery.rules import MODULES
from eim.nursery.rules.base import Signal, View
from eim.paper.versioning import SHORT, _canon

DOSSIERS = Path(__file__).resolve().parent / "dossiers"
CEILING = 50                      # techo de la familia (◆ de T167, 2026-11-11)
ExitTemplate = Literal["atr_ladder", "rule_flip", "mean_target", "time_stop"]
Rule = Callable[[View, dict], Signal]


class Prospect(BaseModel):
    """Un perfil propio de un agente, congelado. Los parámetros son canon, no un ajuste."""

    model_config = ConfigDict(frozen=True)

    id: str
    agent_id: str
    agent_version: str
    name: str
    role: Literal["base", "candidato"]
    rule_text: str
    timeframe: Literal["15m", "1h", "4h"]
    exit_template: ExitTemplate
    max_bars: int | None = None
    horizon: Literal["scalping", "intradia", "tres_dias", "semanal"]
    params: dict[str, Any]
    variables: tuple[str, ...]
    opposite_of: str | None = None
    literature: tuple[str, ...] = ()

    @property
    def rule(self) -> Rule:
        return MODULES[self.agent_id].RULES[self.id]

    @computed_field
    @property
    def fingerprint(self) -> str:
        return fingerprint_of(self)

    @property
    def account(self) -> str:
        """Identidad de su cuenta: prospecto@huella (otra huella = otra cuenta)."""
        return f"{self.id}@{self.fingerprint}"


@cache
def _rule_code(fn: Rule) -> str:
    import ast
    import textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return json.dumps(_canon(tree), sort_keys=True)


def fingerprint_of(p: Prospect) -> str:
    payload = {"id": p.id, "agent": f"{p.agent_id}@{p.agent_version}", "rule": _rule_code(p.rule),
               "params": p.params, "variables": sorted(p.variables), "tf": p.timeframe,
               "exit": p.exit_template, "max_bars": p.max_bars}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:SHORT]


def from_dossier(d: Mapping[str, Any], raw: Mapping[str, Any]) -> Prospect:
    """Un prospecto de un expediente, validado contra lo que su agente expone."""
    aid = d["agent_id"]
    mod = MODULES.get(aid)
    if mod is None:
        raise ValueError(f"{raw['id']}: el agente {aid} no tiene módulo de reglas")
    declared = {v["name"] for v in d["variables"]}
    missing = [v for v in raw["variables"] if v not in declared or v not in mod.EXPOSES]
    if missing:
        raise ValueError(f"{raw['id']}: pide variables que {aid} no expone: {missing}")
    if raw["id"] not in mod.RULES:
        raise ValueError(f"{raw['id']}: sin regla en eim/nursery/rules/{aid}.py")
    return Prospect(
        id=raw["id"], agent_id=aid, agent_version=d["agent_version"], name=raw["name"],
        role=raw["role"], rule_text=raw["rule"], timeframe=raw["timeframe"],
        exit_template=raw["exit_template"], max_bars=raw.get("max_bars"),
        horizon=raw["horizon"], params={k: v["value"] for k, v in raw["params"].items()},
        variables=tuple(raw["variables"]), opposite_of=raw.get("opposite_of"),
        literature=tuple(raw.get("literature") or ()))


def load_dossiers(folder: Path = DOSSIERS) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(folder.glob("*.json"))}


def load_prospects(folder: Path = DOSSIERS) -> tuple[Prospect, ...]:
    """Los prospectos inscritos, validados; falla si la familia pasa del techo o se repite un id."""
    out = [from_dossier(d, raw) for d in load_dossiers(folder).values()
           if d.get("status") == "inscrito" for raw in d.get("prospects", [])]
    ids = [p.id for p in out]
    if len(set(ids)) != len(ids):
        raise ValueError("ids de prospecto repetidos")
    if len(out) > CEILING:
        raise ValueError(f"{len(out)} prospectos superan el techo de la familia ({CEILING})")
    return tuple(out)


def native_paths(prospects: tuple[Prospect, ...]) -> dict[str, tuple[str, ...]]:
    """Rutas que el contexto debe guardar por agente: la unión de lo que declaran sus prospectos."""
    acc: dict[str, set[str]] = {}
    for p in prospects:
        acc.setdefault(p.agent_id, set()).update(p.variables)
    return {a: tuple(sorted(v)) for a, v in sorted(acc.items())}
