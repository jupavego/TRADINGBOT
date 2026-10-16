"""Tableros de líderes (T41) en `root/leaders/`: memoria corta para la API y el snapshot.

Un JSON por evaluación (`board_<asof>.json`, escritura atómica) y solo los `keep` más
recientes. Lo escribe el proceso del vigilante (único que abre `leaders.duckdb`) y lo leen
otros procesos. `at(asof)` nunca devuelve un tablero posterior a `asof`.
"""

from __future__ import annotations

import os
from pathlib import Path

from eim.copytrading.board import Board
from eim.core import LeaderPosition, LeaderWeight, MarketSnapshot

BOARD_DIR = "leaders"
MAX_AGE_MS = 10 * 60_000  # tablero más viejo no entra en el snapshot


class BoardStore:
    def __init__(self, root: Path | str, keep: int = 20) -> None:
        self.dir = Path(root) / BOARD_DIR
        self.keep = keep

    def _files(self) -> list[tuple[int, Path]]:
        if not self.dir.is_dir():
            return []
        out = []
        for f in self.dir.glob("board_*.json"):
            try:
                out.append((int(f.stem.removeprefix("board_")), f))
            except ValueError:
                continue
        return sorted(out)

    def save(self, board: Board) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"board_{board.asof}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(board.model_dump_json(), encoding="utf-8")
        os.replace(tmp, path)
        for _, old in self._files()[:-self.keep]:
            old.unlink(missing_ok=True)
        return path

    def latest(self) -> Board | None:
        for _, f in reversed(self._files()):
            b = self._load(f)
            if b is not None:
                return b
        return None

    def at(self, asof: int, max_age_ms: int = MAX_AGE_MS) -> Board | None:
        """Tablero más reciente con `asof − max_age ≤ t ≤ asof`."""
        for t, f in reversed(self._files()):
            if t <= asof:
                return self._load(f) if asof - t <= max_age_ms else None
        return None

    @staticmethod
    def _load(path: Path) -> Board | None:
        try:
            return Board.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # borrado o a medio escribir por otro proceso


def snapshot_inputs(board: Board) -> tuple[list[LeaderPosition], list[LeaderWeight],
                                            dict[str, str], dict[str, tuple[int, int]]]:
    """Posiciones (todas las monedas) y pesos de los aprobados, con fuente y cobertura."""
    ws = board.weights
    pos = [x for w in ws for x in board.positions.get(w.leader_id, [])]
    seen = [w.positions_at for w in ws if w.positions_at is not None]
    lo = min(seen) if seen else board.asof
    return pos, ws, {"leaders": board.sources.get("leaders", "hyperliquid")}, {
        "leaders": (lo, board.asof)}


def leaders_snapshot(board: Board | None, symbol: str, asof: int,
                     max_age_ms: int = MAX_AGE_MS) -> MarketSnapshot:
    """Snapshot mínimo para correr `smart_money` fuera del ciclo de velas (API)."""
    fresh = board is not None and 0 <= asof - board.asof <= max_age_ms
    if not fresh:
        return MarketSnapshot(symbol=symbol, timeframe="1h", candles=[], asof=asof)
    pos, ws, src, cov = snapshot_inputs(board)
    return MarketSnapshot(symbol=symbol, timeframe="1h", candles=[], asof=asof, leaders=pos,
                          leader_weights=ws, sources=src, coverage=cov)
