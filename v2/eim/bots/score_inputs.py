"""Qué datos leyó una puntuación del escuadrón (T124): instantáneas ligeras de cada serie.

La puntuación T59 se recalcula cada 4 h sobre datos que crecen, así que no se congela una copia
cada vez: se registra la identidad (rango, nº de velas, hash) de exactamente lo que se leyó y el
resultado (`bot_scorecard`) con sus ids. Si registrar falla (base ocupada, disco), la puntuación
sigue igual y se declara **no reproducible** con el motivo: nunca se tumba por esto.
"""

from __future__ import annotations

import logging

from eim.core import Candle
from eim.data.results import ResultStore
from eim.data.snapshots import FUNDING, SnapshotInfo, SnapshotStore
from eim.data.timeframes import tf_ms
from eim.repro.code import fingerprint
from eim.repro.stamp import stamp

log = logging.getLogger("eim.bots")


class ScoreInputs:
    def __init__(self, store, symbol: str, now: int, enabled: bool = True) -> None:
        self.store, self.symbol, self.now = store, symbol, now
        self.snaps = SnapshotStore(store.root) if enabled else None
        self.infos: list[SnapshotInfo] = []
        self.error = "" if enabled else "registro de instantáneas apagado"

    def _keep(self, tf: str, kind: str, start: int, candles: list[Candle],
              funding: list[tuple[int, float]], last_t: int | None, step: int) -> None:
        if self.snaps is None or self.error:
            return
        end = max(self.now, (last_t + step) if last_t is not None else self.now)
        try:
            src = self.store.source(kind, self.symbol, tf) or "desconocida"
            self.infos.append(self.snaps.register(
                kind, self.symbol, tf, start, end, candles, funding, src,
                src if kind == FUNDING else "", freeze=False, origin="bots.scorer",
                store_dir=".").info)
        except Exception as exc:  # noqa: BLE001 - la puntuación no depende de esto
            self.error = f"{type(exc).__name__}: {exc}"
            log.warning("puntuación de bots sin instantánea (T124): %s", self.error)

    def candles(self, tf: str, start: int, end: int | None = None) -> list[Candle]:
        """Las mismas lecturas de siempre; la instantánea fija exactamente lo leído."""
        cs = self.store.read_candles(self.symbol, tf, start=start, end=end)
        self._keep(tf, "candles", start, cs, [], cs[-1].t if cs else None, tf_ms(tf))
        return cs

    def funding(self, start: int) -> list[tuple[int, float]]:
        rows = self.store.read_series(FUNDING, self.symbol, start=start)
        self._keep("-", FUNDING, start, [], rows, rows[-1][0] if rows else None, 1)
        return rows

    def stamp(self, out: dict, criteria: str) -> dict:
        """Registra el resultado y devuelve su sello (`reproducibility`)."""
        if self.error or not self.infos:
            return stamp([], None, f"no se pudieron fijar los datos: {self.error or 'sin datos'}")
        try:
            states = {b["id"]: b["state"] for b in out.get("bots", [])}
            rec = ResultStore(self.store.root).register(
                "bot_scorecard", f"puntuación de bots {self.symbol} ({criteria})",
                [i.id for i in self.infos],
                {"symbol": self.symbol, "criteria": criteria, "asof": out.get("asof")},
                fingerprint(), {"states": states}, "reports.duckdb:bot_scorecard")
        except Exception as exc:  # noqa: BLE001
            log.warning("puntuación de bots sin registro (T124): %s", exc)
            return stamp([], None, f"no se pudo registrar el resultado: {exc}")
        return stamp(self.infos, rec.id)
