"""Estado persistente del servicio: libro de ejecución, simulador y cursores del ciclo.

Se guarda tras cada ciclo (escritura atómica). Al reiniciar se restaura: un SimBroker en
memoria sin esto perdería posiciones y SL/TP en cada caída, y la operación «continua» no
lo sería. Con testnet el exchange es la fuente de verdad; aquí solo va el libro interno.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from eim.execution.service import ExecutionService, LiveTrade
from eim.execution.sim_broker import SimBroker

VERSION = 1


@dataclass
class Cursors:
    fed: dict[str, int] = field(default_factory=dict)        # última vela de camino aplicada
    analyzed: dict[str, int] = field(default_factory=dict)   # última vela del marco analizada
    last_report_week: int | None = None                       # inicio (ms) de la última semana
    started_at: int | None = None                             # primera vez que corrió

    def to_json(self) -> dict:
        return {"fed": self.fed, "analyzed": self.analyzed,
                "last_report_week": self.last_report_week, "started_at": self.started_at}

    @classmethod
    def from_json(cls, d: dict) -> Cursors:
        return cls(fed={k: int(v) for k, v in d.get("fed", {}).items()},
                   analyzed={k: int(v) for k, v in d.get("analyzed", {}).items()},
                   last_report_week=d.get("last_report_week"), started_at=d.get("started_at"))


def save(path: Path, svc: ExecutionService | None, cursors: Cursors, mode: str) -> None:
    data: dict = {"version": VERSION, "mode": mode, "cursors": cursors.to_json(), "trades": [],
                  "broker": None}
    if svc is not None:
        data["trades"] = [t.to_json() for t in list(svc.trades.values())]
        if isinstance(svc.broker, SimBroker):
            data["broker"] = svc.broker.dump()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)


def load(path: Path, svc: ExecutionService | None, mode: str) -> Cursors:
    """Restaura en `svc` (si coincide el modo) y devuelve los cursores. Sin archivo → vacíos."""
    if not path.exists():
        return Cursors()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("mode") != mode:          # otro modo: no se mezclan libros
        return Cursors()
    if svc is not None:
        svc.trades = {d["key"]: LiveTrade(**d) for d in data.get("trades", [])}
        if data.get("broker") and isinstance(svc.broker, SimBroker):
            svc.broker.load(data["broker"])
    return Cursors.from_json(data.get("cursors", {}))
