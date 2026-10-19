"""Versión de una estrategia (T49): huella estable de sus reglas, parámetros y mecánica.

- **Reglas y parámetros**: árbol sintáctico normalizado (sin comentarios, docstrings ni
  posiciones; campos vacíos omitidos para que coincida entre versiones de Python) de la función
  de la estrategia y, de forma recursiva, de las funciones y clases de `eim.paper` e
  `eim.indicators` que usa (p. ej. `atr_draft`, `Draft`, `Ind`), más el valor de las constantes
  de módulo y de las variables de cierre (`tp_index`, `aid`, …).
- **Mecánica**: los parámetros de `ExecParams` que cambian el resultado sombra EN ESE MARCO
  (costos, camino, `min_risk_frac`, funding supuesto, enfriamiento y break-even si aplica).
  Los filtros de perfil y la tendencia del marco mayor no entran: la validación usa la sombra.

Cambiar cualquiera de las dos cosas da otra huella = otra versión; la evidencia no se mezcla.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import sys
import textwrap
from functools import cache
from typing import Any

from eim.paper.params import ExecParams

SCOPES = ("eim.paper", "eim.indicators")
SKIP_FIELDS = frozenset({"ctx", "type_comment", "kind"})
SHORT = 12


def _strip_doc(body: list) -> list:
    if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        return body[1:]
    return body


def _canon(node: Any) -> Any:
    """Estructura canónica del AST: tipo + campos no vacíos (sin líneas ni contexto)."""
    if isinstance(node, ast.AST):
        out: list = [type(node).__name__]
        for name, val in ast.iter_fields(node):
            if name in SKIP_FIELDS:
                continue
            if name == "body" and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                    ast.ClassDef, ast.Module)):
                val = _strip_doc(val)
            c = _canon(val)
            if c is None or c == []:
                continue
            out.append([name, c])
        return out
    if isinstance(node, list):
        return [_canon(x) for x in node]
    if node is None:
        return None
    return repr(node)


_SKIP = object()      # no es un dato simple (módulo, objeto, función ajena): no entra


def _value(v: Any) -> Any:
    """Valor serializable de una constante, o `_SKIP`."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return repr(v)
    if isinstance(v, (tuple, list, set, frozenset)):
        items = [_value(x) for x in v]
        if any(x is _SKIP for x in items):
            return _SKIP
        return sorted(items, key=str) if isinstance(v, (set, frozenset)) else items
    if isinstance(v, dict):
        d = {str(k): _value(x) for k, x in v.items()}
        return _SKIP if any(x is _SKIP for x in d.values()) else d
    return _SKIP


def _in_scope(obj: Any) -> bool:
    mod = getattr(obj, "__module__", "") or ""
    return any(mod == s or mod.startswith(s + ".") for s in SCOPES)


def _names(tree: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


class _Collector:
    def __init__(self) -> None:
        self.code: dict[str, Any] = {}
        self.consts: dict[str, Any] = {}

    def add(self, obj: Any) -> None:
        obj = inspect.unwrap(obj) if inspect.isfunction(obj) else obj
        key = f"{obj.__module__}.{obj.__qualname__}"
        if key in self.code:
            return
        tree = ast.parse(textwrap.dedent(inspect.getsource(obj)))
        self.code[key] = _canon(tree)
        env = (obj.__globals__ if inspect.isfunction(obj)
               else vars(sys.modules[obj.__module__]))
        cells: dict[str, Any] = {}
        if inspect.isfunction(obj) and obj.__closure__:
            cells = dict(zip(obj.__code__.co_freevars,
                             (c.cell_contents for c in obj.__closure__), strict=True))
        for name in sorted(_names(tree)):
            if name in cells:
                self._ref(f"{key}:{name}", cells[name])
            elif name in env:
                self._ref(f"{obj.__module__}.{name}", env[name])

    def _ref(self, label: str, v: Any) -> None:
        if (inspect.isfunction(v) or inspect.isclass(v)) and _in_scope(v):
            self.add(v)
            return
        val = _value(v)
        if val is not _SKIP:
            self.consts[label] = val


@cache
def rules_fingerprint(fn: Any) -> str:
    """Huella de las reglas y parámetros de una función de estrategia (hex completo)."""
    col = _Collector()
    col.add(fn)
    blob = json.dumps({"code": col.code, "consts": col.consts}, sort_keys=True,
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def exec_fingerprint(ep: ExecParams, timeframe: str) -> dict:
    """Mecánica que cambia el resultado sombra en el marco `timeframe`."""
    be = ep.be_trigger_r > 0 and timeframe in ep.be_timeframes
    return {
        "costs": ep.costs.model_dump(mode="json"), "path_tf": ep.path_tf,
        "min_risk_frac": ep.min_risk_frac, "funding_8h_assumed": ep.funding_8h_assumed,
        "cooldown_bars": ep.cooldown_bars,
        "be": ({"trigger_r": ep.be_trigger_r, "lock_r": ep.be_lock_r,
                "cover_costs": ep.be_cover_costs, "est_cost_frac": ep.est_cost_frac}
               if be else None),
    }


def version_of(strategy_id: str, family: str, rules: str, timeframe: str,
               ep: ExecParams | None = None) -> str:
    """Huella corta de `estrategia@marco`: reglas + mecánica del marco."""
    blob = json.dumps({"id": strategy_id, "family": family, "rules": rules, "tf": timeframe,
                       "exec": exec_fingerprint(ep or ExecParams(), timeframe)},
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:SHORT]
