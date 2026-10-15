"""Fotografías de arbitraje (T39): últimos escaneos `ArbMarket` en `root/arbitrage/`.

Un archivo JSON por escaneo (`scan_<asof>.json`, escritura atómica) y solo los `keep` más
recientes: es la memoria corta del escáner, no un histórico. `at(asof)` nunca devuelve una
fotografía posterior a `asof` (sin mirar al futuro en reproducciones o backtests).
"""

from __future__ import annotations

import os
from pathlib import Path

from eim.core import ArbMarket, MarketSnapshot

ARB_DIR = "arbitrage"
MAX_AGE_MS = 10 * 60_000  # más vieja que esto no entra en el snapshot
SCAN_SYMBOL, SCAN_TF = "BINANCE", "scan"  # snapshot propio del escáner (no es un par/marco)


class ArbStore:
    def __init__(self, root: Path | str, keep: int = 20) -> None:
        self.dir = Path(root) / ARB_DIR
        self.keep = keep

    def _files(self) -> list[tuple[int, Path]]:
        if not self.dir.is_dir():
            return []
        out = []
        for f in self.dir.glob("scan_*.json"):
            try:
                out.append((int(f.stem.removeprefix("scan_")), f))
            except ValueError:
                continue
        return sorted(out)

    def save(self, mkt: ArbMarket) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"scan_{mkt.asof}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(mkt.model_dump_json(), encoding="utf-8")
        os.replace(tmp, path)
        for _, old in self._files()[:-self.keep]:
            old.unlink(missing_ok=True)
        return path

    def latest(self) -> ArbMarket | None:
        files = self._files()
        return self._load(files[-1][1]) if files else None

    def at(self, asof: int, max_age_ms: int = MAX_AGE_MS) -> ArbMarket | None:
        """Escaneo más reciente con `asof − max_age ≤ t ≤ asof`."""
        for t, f in reversed(self._files()):
            if t <= asof:
                return self._load(f) if asof - t <= max_age_ms else None
        return None

    @staticmethod
    def _load(path: Path) -> ArbMarket | None:
        try:
            return ArbMarket.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # borrado o a medio escribir por otro proceso


def arb_sources(mkt: ArbMarket) -> tuple[dict[str, str], dict[str, tuple[int, int]]]:
    """Fuente y cobertura agregadas de la fotografía (clave `arb`)."""
    srcs = sorted(set(mkt.sources.values()))
    return {"arb": "+".join(srcs) or "desconocida"}, {"arb": (mkt.asof, mkt.asof)}


def arb_snapshot(mkt: ArbMarket | None, asof: int) -> MarketSnapshot:
    """Snapshot mínimo para correr el agente `arbitrage` fuera del ciclo de velas."""
    sources, coverage = arb_sources(mkt) if mkt is not None else ({}, {})
    return MarketSnapshot(symbol=SCAN_SYMBOL, timeframe=SCAN_TF, candles=[], arb=mkt,
                          asof=asof, sources=sources, coverage=coverage)
