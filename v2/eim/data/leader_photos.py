"""Cómo se guarda una foto de posiciones (T178): compacta y sin perder nada.

Hasta T178 cada foto era la lista de posiciones en JSON **con todos sus campos**, así que
repetía en cada posición `leader_id` (65 caracteres), `address` (42), `source`, `t` y
`observed_at`, que ya son columnas de la fila. Una foto de 15 monedas gastaba ~1,5 KB solo en
eso: medido en disco, 20 000 fotos reales ocupaban 129,2 MB y recodificadas **32,0 MB**.

Formato nuevo (`v` = 2), un objeto JSON para distinguirlo de la lista de antes:

    {"v":2,"h":{"leader_id":…,"address":…,"source":…,"t":…,"observed_at":…},
     "p":[[symbol, side, size, entry, leverage, margin_mode, liquidation_px,
           unrealized_pnl, margin_used], …]}

`h` sale una vez por foto. Si alguna posición no comparte esa cabecera (no pasa con lo que
escribe `parse_positions`, pero puede llegar de otra fuente), se guarda **el formato de antes**:
el códec nunca inventa ni pierde un campo. `decode` lee los dos, así que las fotos viejas se
siguen leyendo tal cual y `recode` (en `leader_retention.py`) las pasa al formato nuevo cuando
le toca.
"""

from __future__ import annotations

import json

from eim.core.leaders import LeaderPosition

VERSION = 2
_HEAD = ("leader_id", "address", "source", "t", "observed_at")
_BODY = ("symbol", "side", "size", "entry", "leverage", "margin_mode", "liquidation_px",
         "unrealized_pnl", "margin_used")
_SHAPE = ("symbol", "side", "size", "entry", "leverage", "margin_mode")


def _encode_rows(rows: list[dict]) -> str:
    if not rows:
        return json.dumps({"v": VERSION, "h": {}, "p": []}, separators=(",", ":"))
    head = {k: rows[0].get(k) for k in _HEAD}
    if any(any(r.get(k) != v for k, v in head.items()) for r in rows[1:]):
        return json.dumps(rows)                      # no comparten cabecera: como antes
    body = [[r.get(k) for k in _BODY] for r in rows]
    return json.dumps({"v": VERSION, "h": head, "p": body}, separators=(",", ":"))


def encode(positions: list[LeaderPosition]) -> str:
    """La foto en el formato nuevo; en el de antes si las posiciones no comparten cabecera."""
    return _encode_rows([p.model_dump() for p in positions])


def recode(raw: str | None) -> str | None:
    """La misma foto en el formato nuevo, sin pasar por el modelo. None si ya lo está o si no
    se puede compactar sin perder nada (entonces se deja como está)."""
    if raw is None or is_compact(raw):
        return None
    out = _encode_rows(_rows(raw))
    return out if is_compact(out) else None


def _rows(raw: str | None) -> list[dict]:
    """Las posiciones de la foto como diccionarios, venga en el formato que venga."""
    data = json.loads(raw or "[]")
    if isinstance(data, list):                       # formato de antes
        return data
    head, out = data.get("h") or {}, []
    for row in data.get("p") or []:
        d = dict(head)
        d.update(dict(zip(_BODY, row, strict=False)))
        out.append(d)
    return out


def decode(raw: str | None) -> list[LeaderPosition]:
    return [LeaderPosition.model_validate(d) for d in _rows(raw)]


def shape(raw: str | None) -> str:
    """Lo que define la posición, sin PnL ni margen (cambian con el precio), como texto: así se
    compara una foto con otra y se guarda en `leader_photo_cover`."""
    try:
        rows = _rows(raw)
    except (TypeError, ValueError):
        return f"?{raw}"
    return json.dumps(sorted([r.get(k) for k in _SHAPE] for r in rows), separators=(",", ":"))


def is_compact(raw: str | None) -> bool:
    return bool(raw) and raw.lstrip()[:1] == "{"
