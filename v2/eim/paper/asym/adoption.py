"""Fase 3 de T187–T189: qué se adoptó solo, desde cuándo, y cómo llega a la mesa.

- `settle`: el primer veredicto de cada regla que no sea EN CURSO queda en `verdicts.json` y ya
  no cambia (si no, bastaría con seguir mirando hasta que pase).
- `adopt`: las reglas de costo y riesgo (`prereg.AUTO_RULES`) con veredicto PASA entran en
  `adopted.json` con su instante: el siguiente 00:00 UTC después del veredicto y nunca antes del
  cierre de T31. Solo valen para decisiones posteriores a ese instante: los libros no se
  reescriben hacia atrás. T188 no se adopta nunca aquí (lo decide el usuario).
- `exec_params_with` y `profiles_with`: la mesa principal las aplica en cada cálculo de la vista
  (las corridas aparte no: miden otra cosa).

Solo lee y escribe los archivos que se le piden.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from eim.paper.asym import prereg as P
from eim.paper.asym.verdict import PASS, RUNNING
from eim.paper.params import ExecParams, ProfileParams

MAKER_RULE = "t189_"


def read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_json(path: Path, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    tmp.replace(p)


def settle(path: Path, results: Mapping[str, dict], now: int) -> dict:
    """Escribe los veredictos nuevos (no EN CURSO) y devuelve todos los escritos."""
    done = read_json(path)
    changed = False
    for rule, v in results.items():
        if rule in done or v.get("state") in (None, RUNNING):
            continue
        done[rule] = {**v, "at": now, "prereg": P.VERSION, "fingerprint": P.fingerprint()}
        changed = True
    if changed:
        write_json(path, done)
    return done


def instant_after(t: int) -> int:
    """El siguiente 00:00 UTC estrictamente después de `t`, y nunca antes del cierre de T31."""
    nxt = (t // P.DAY_MS + 1) * P.DAY_MS
    return max(nxt, P.T31_CLOSE_MS)


def adopt(path: Path, verdicts: Mapping[str, dict], enabled: bool = True) -> dict:
    """Añade a `adopted.json` las reglas automáticas con PASA. Nunca quita nada."""
    adopted = read_json(path)
    if not enabled:
        return adopted
    changed = False
    for rule in P.AUTO_RULES:
        v = verdicts.get(rule)
        if rule in adopted or not v or v.get("state") != PASS:
            continue
        adopted[rule] = {"from_ms": instant_after(int(v["at"])), "verdict_at": int(v["at"]),
                         "why": v.get("why", ""), "prereg": P.VERSION}
        changed = True
    if changed:
        write_json(path, adopted)
    return adopted


def instants(adopted: Mapping[str, dict]) -> dict[str, int]:
    out = {}
    for rule, v in adopted.items():
        try:
            out[rule] = int(v["from_ms"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def exec_params_with(ep: ExecParams, inst: Mapping[str, int]) -> ExecParams:
    """Entrada límite en los marcos de T189 adoptados, desde su instante."""
    maker = tuple(sorted((r[len(MAKER_RULE):], t) for r, t in inst.items()
                         if r.startswith(MAKER_RULE)))
    return ep if maker == ep.maker_from_ms else ep.model_copy(update={"maker_from_ms": maker})


def profiles_with(profiles: Sequence[ProfileParams], inst: Mapping[str, int],
                  phase2_from_ms: int | None) -> tuple[ProfileParams, ...]:
    """Cada perfil con sus reglas de riesgo adoptadas (T187b/c) y el instante de la fase 2."""
    risk = tuple(sorted((r, t) for r, t in inst.items() if r in ("t187b", "t187c")))
    out = []
    for p in profiles:
        if p.asym_from_ms == risk and p.phase2_from_ms == phase2_from_ms:
            out.append(p)
        else:
            out.append(p.model_copy(update={"asym_from_ms": risk,
                                            "phase2_from_ms": phase2_from_ms}))
    return tuple(out)


class AdoptedFile:
    """Lectura de `adopted.json` para la mesa, sin releer el disco si no cambió."""

    def __init__(self, path: Path | None) -> None:
        self.path = Path(path) if path is not None else None
        self._mtime: float | None = None
        self._inst: dict[str, int] = {}

    def instants(self) -> dict[str, int]:
        if self.path is None:
            return {}
        try:
            m = self.path.stat().st_mtime
        except OSError:
            return {}
        if m != self._mtime:
            self._inst, self._mtime = instants(read_json(self.path)), m
        return dict(self._inst)
