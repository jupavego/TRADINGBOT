"""Variables nativas de los agentes en el contexto del bróker (T168, entregable 3). Puro.

Un prospecto declara rutas del reporte de su agente (`metrics.variables.STACK_ORDER`,
`metrics.bots[].stance`, `metrics.pivots[-1].wave_label`, `bias`…). El contexto guarda **solo**
esas rutas, compactas: números a 6 decimales, de los diccionarios solo sus campos simples y de las
listas cada elemento compactado. La clave guardada es la ruta sin el prefijo `metrics.`.

Sintaxis de ruta: `a.b` entra en diccionarios; `a[]` recorre una lista (el resultado es lista);
`a[-1]` toma un elemento. Una ruta que no existe en el reporte da `None`, nunca un valor inventado.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

from eim.core import AgentReport

_R = 6
_IDX = re.compile(r"^(?P<key>[^\[\]]+)\[(?P<idx>-?\d*)\]$")
HORIZON_KEY = "_h"          # horizonte del agente en velas (plantillas `time_stop`/`mean_target`)


def stored_key(path: str) -> str:
    """Clave compacta con la que se guarda una ruta en el contexto."""
    return path[len("metrics."):] if path.startswith("metrics.") else path


def _compact(v: Any) -> Any:
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        f = float(v)
        if not math.isfinite(f):
            return None
        return int(v) if isinstance(v, int) else round(f, _R)
    if isinstance(v, Mapping):
        return {str(k): _compact(x) for k, x in v.items()
                if not isinstance(x, (Mapping, list, tuple))}
    if isinstance(v, (list, tuple)):
        return [_compact(x) for x in v]
    return None


def resolve(obj: Any, path: str) -> Any:
    """Valor de `path` en `obj` (diccionario del reporte), o None si no existe."""
    cur: list[Any] = [obj]
    many = False
    for part in path.split("."):
        m = _IDX.match(part)
        nxt: list[Any] = []
        for o in cur:
            if m is None:
                nxt.append(o.get(part) if isinstance(o, Mapping) else None)
                continue
            seq = o.get(m["key"]) if isinstance(o, Mapping) else None
            if m["idx"] == "":
                many = True
                nxt.extend(seq if isinstance(seq, list) else [])
            else:
                i = int(m["idx"])
                ok = isinstance(seq, list) and -len(seq) <= i < len(seq)
                nxt.append(seq[i] if ok else None)
        cur = nxt
    if many:
        return cur
    return cur[0] if cur else None


def report_dict(rep: AgentReport) -> dict:
    """Lo que una ruta puede leer de un reporte: su sesgo, su confianza y sus métricas."""
    return {"bias": rep.bias, "confidence": rep.confidence, "metrics": rep.metrics}


def extract(rep: AgentReport, paths: Iterable[str]) -> dict:
    """Variables declaradas de un reporte, compactas, más el horizonte del agente."""
    d = report_dict(rep)
    out = {stored_key(p): _compact(resolve(d, p)) for p in paths}
    out[HORIZON_KEY] = int(rep.horizon_bars)
    return out


def native_block(reports: Iterable[AgentReport],
                 wanted: Mapping[str, tuple[str, ...]]) -> dict:
    """`{agente: {clave: valor}}` solo de los agentes con alguna ruta pedida y con datos."""
    out: dict[str, dict] = {}
    for r in reports:
        paths = wanted.get(r.agent_id)
        if paths and r.status != "no_data":
            out[r.agent_id] = extract(r, paths)
    return out
