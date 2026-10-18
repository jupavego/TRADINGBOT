"""Linaje de versiones (T49): tipos puros, ventanas de ajuste y declaraciones versionadas.

Una **ventana de ajuste** es un tramo de datos que se miró para elegir o ajustar una versión. Una
operación es **fuera de muestra** para una versión solo si su decisión cae fuera de TODAS las
ventanas de esa versión y de sus ancestros (`out_of_sample`): lo aplica el código.

Las ventanas de una versión nueva salen de `lineage.json` (versionado en git junto al cambio de
código: origen, nota, ventanas y las huellas a las que aplica). Sin declaración, el alta es
**automática y conservadora**: todo lo anterior al alta cuenta como ajuste (`auto_windows`).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

LINEAGE_FILE = Path(__file__).parent / "lineage.json"
AUTO_ORIGIN = "auto"
AUTO_NOTE = "Alta automática sin declaración: todo lo anterior al alta pudo mirarse."


@dataclass(frozen=True)
class Window:
    from_ms: int
    to_ms: int
    symbol: str | None = None        # None = todos los símbolos
    note: str = ""

    def covers(self, t: int, symbol: str) -> bool:
        return self.from_ms <= t < self.to_ms and self.symbol in (None, symbol)

    def to_json(self) -> dict:
        return {"from": self.from_ms, "to": self.to_ms, "symbol": self.symbol, "note": self.note}


@dataclass(frozen=True)
class Version:
    sid: str                         # estrategia@marco
    n: int                           # vN
    fingerprint: str
    strategy: str
    timeframe: str
    created_ms: int
    parent: int | None
    origin: str
    note: str = ""
    retired_ms: int | None = None
    windows: tuple[Window, ...] = ()

    @property
    def label(self) -> str:
        """estrategia@marco@vN: la identidad que se valida."""
        return f"{self.sid}@v{self.n}"

    def to_json(self) -> dict:
        return {"id": self.label, "sid": self.sid, "n": self.n, "fingerprint": self.fingerprint,
                "strategy": self.strategy, "timeframe": self.timeframe,
                "created": self.created_ms, "parent": self.parent, "origin": self.origin,
                "note": self.note, "retired": self.retired_ms,
                "windows": [w.to_json() for w in self.windows]}


@dataclass(frozen=True)
class Declaration:
    origin: str
    note: str
    windows: tuple[Window, ...]
    versions: dict[str, str] = field(default_factory=dict)    # sid -> huella


def ancestry(v: Version, by_n: dict[int, Version]) -> list[Version]:
    """La versión y sus ancestros (padre, abuelo, …) dentro de la misma estrategia@marco."""
    out, seen, cur = [], set(), v
    while cur is not None and cur.n not in seen:
        out.append(cur)
        seen.add(cur.n)
        cur = by_n.get(cur.parent) if cur.parent is not None else None
    return out


def tuning_windows(v: Version, family: Iterable[Version]) -> tuple[Window, ...]:
    """Ventanas de ajuste de `v` y de todos sus ancestros (`family` = versiones de su sid)."""
    by_n = {x.n: x for x in family if x.sid == v.sid}
    by_n[v.n] = v
    return tuple(w for x in ancestry(v, by_n) for w in x.windows)


def out_of_sample(t: int, symbol: str, windows: Sequence[Window]) -> bool:
    return not any(w.covers(t, symbol) for w in windows)


def auto_windows(now_ms: int) -> tuple[Window, ...]:
    return (Window(0, now_ms, None, AUTO_NOTE),)


def iso_ms(s: str) -> int:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return int((d if d.tzinfo else d.replace(tzinfo=UTC)).timestamp() * 1000)


def ms_iso(t: int) -> str:
    return datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_declarations(path: Path = LINEAGE_FILE) -> list[Declaration]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for d in raw.get("declarations", []):
        ws = tuple(Window(iso_ms(w["from"]), iso_ms(w["to"]), w.get("symbol"), w.get("note", ""))
                   for w in d["windows"])
        if any(w.to_ms <= w.from_ms for w in ws):
            raise ValueError(f"ventana vacía o invertida en la declaración {d['origin']}")
        out.append(Declaration(d["origin"], d.get("note", ""), ws, dict(d.get("versions", {}))))
    return out


def find_declaration(decls: Sequence[Declaration], sid: str, fingerprint: str
                     ) -> Declaration | None:
    """La última declaración que nombra esta huella de esta estrategia@marco."""
    for d in reversed(decls):
        if d.versions.get(sid) == fingerprint:
            return d
    return None


def declare(path: Path, origin: str, note: str, windows: Sequence[Window],
            versions: dict[str, str], declared: str) -> dict:
    """Añade una declaración al archivo (solo se añade; nunca se reescribe una anterior)."""
    raw = (json.loads(path.read_text(encoding="utf-8")) if path.exists()
           else {"description": "Ventanas de ajuste declaradas por versión (T49). Solo se "
                                "añaden declaraciones.", "declarations": []})
    entry = {"origin": origin, "declared": declared, "note": note,
             "windows": [{"from": ms_iso(w.from_ms), "to": ms_iso(w.to_ms), "symbol": w.symbol,
                          "note": w.note} for w in windows],
             "versions": dict(sorted(versions.items()))}
    raw["declarations"].append(entry)
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return entry
