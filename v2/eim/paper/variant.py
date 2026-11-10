"""Segunda mesa en papel con otra ejecución, en paralelo a T31 (T143, ◆ 2026-11-10).

Reutiliza los **contextos** de la mesa principal (los agentes no se vuelven a correr: es la misma
decisión) y solo cambia la ejecución: costos, entradas, puerta de marcos y tamaño. Escribe en su
propia base (`data/paper_<nombre>.duckdb`): su libro fijo, su diario de protección y sus
instantáneas no se mezclan nunca con los de T31.

Lo que NO hace, a propósito: no genera contextos, no sincroniza velas, no registra intentos en la
puerta de validación (no añade nada a la familia de Holm), no emite decisiones al Observatorio ni
alertas a `op_alerts` (serían duplicados de lo que ya emite la principal) y no late como
`paper.broker` (el vigilante del conjunto no la confunde con la principal).
"""

from __future__ import annotations

import json
from pathlib import Path

from eim.agents.registry import AgentRegistry
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import FOCUS
from eim.paper.desk import PaperDesk
from eim.paper.generate import now_ms
from eim.paper.params import ExecParams, ProfileParams


class SplitStore:
    """Contextos de la base principal (solo lectura) y todo lo demás en la base propia."""

    def __init__(self, ctx: PaperStore, own: PaperStore) -> None:
        self.ctx, self.own = ctx, own

    def asofs(self, symbol: str, timeframe: str) -> set[int]:
        return self.ctx.asofs(symbol, timeframe)

    def load(self, symbol: str, timeframe: str, start: int | None = None) -> list[dict]:
        return self.ctx.load(symbol, timeframe, start)

    def regimes(self, symbol: str, timeframe: str):
        return self.ctx.regimes(symbol, timeframe)

    def stamp(self, symbol: str, timeframe: str):
        return self.ctx.stamp(symbol, timeframe)

    def counts(self, symbol: str, timeframe: str) -> dict[str, int]:
        return self.ctx.counts(symbol, timeframe)

    def save(self, *_a, **_k) -> None:
        raise RuntimeError("la mesa variante no escribe contextos: los genera la principal")

    @property
    def connection(self):
        return self.own.connection

    def execute(self, sql: str, params: list | tuple = ()) -> list[tuple]:
        return self.own.execute(sql, params)

    def executemany(self, sql: str, rows: list[tuple]) -> None:
        self.own.executemany(sql, rows)

    def close(self) -> None:
        self.own.close()


class _Silent:
    """Emisor al Observatorio que no emite: las decisiones ya las emite la mesa principal."""

    def emit_books(self, _books) -> None:
        return None


class VariantDesk(PaperDesk):
    def __init__(self, store: Store, ctx_store: PaperStore, own_store: PaperStore, *, name: str,
                 label: str, exec_params: ExecParams, profiles: tuple[ProfileParams, ...],
                 registry: AgentRegistry | None = None, symbols: tuple[str, ...] = FOCUS,
                 poll_s: float = 300.0) -> None:
        super().__init__(store, SplitStore(ctx_store, own_store), registry,
                         exec_params=exec_params, profiles=profiles, provider=None,
                         symbols=symbols, poll_s=poll_s)
        self.name, self.label = name, label
        self.obs = _Silent()

    def tick(self) -> int:
        """Sin generar ni sincronizar: los contextos y las velas los pone la mesa principal."""
        self.last_tick, self.live_error = now_ms(), ""
        self._beat(0)
        return 0

    def heartbeat_path(self) -> Path:
        return Path(self.store.root) / "paper" / f"heartbeat_{self.name}.json"

    def _beat(self, saved: int) -> None:
        try:
            p = self.heartbeat_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"last_tick": self.last_tick, "name": self.name,
                                     "error": self.live_error}), encoding="utf-8")
        except OSError:
            pass   # el latido nunca tumba el ciclo
