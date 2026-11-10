"""Rutas de solo lectura de la corrida aparte en papel (T143, ◆ 2026-11-10). Todo SIMULADO.

`GET /v2/paper/variant/{nombre}` da el mismo resumen que `GET /v2/paper`, pero de la mesa
variante, y `.../ledger.csv` exporta su libro fijo. Sin POST: la variante no lanza backtests ni
resuelve protecciones (sus contextos son los de la principal).
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Response

from eim.api.paper import _check, _view
from eim.paper import ledger, universe
from eim.paper.variant import VariantDesk


def build_variant_router(desks: dict[str, VariantDesk]) -> APIRouter:
    router = APIRouter(prefix="/v2/paper/variant")

    def _desk(name: str) -> VariantDesk:
        d = desks.get(name)
        if d is None:
            raise HTTPException(404, f"corrida aparte desconocida: {name} (hay: {sorted(desks)})")
        return d

    @router.get("")
    def variants() -> dict:
        """Corridas aparte encendidas en esta API, con lo que cambian."""
        return {"mode": "SIMULADO", "variants": [
            {"name": d.name, "label": d.label, "live": d.live_status(),
             "timeframes": list(d.tfs)} for d in desks.values()]}

    @router.get("/{name}")
    def summary(name: str, symbol: str = "BTCUSDT") -> dict:
        _check(symbol)
        d = _desk(name)
        v = _view(d, symbol)
        return {**v.summary, "variant": {"name": d.name, "label": d.label},
                "live": d.live_status(), "view": d.view_state(v)}

    @router.get("/{name}/ledger.csv")
    def ledger_csv(name: str, symbol: str | None = None) -> Response:
        d = _desk(name)
        if symbol is not None:
            _check(symbol)
        rows = ledger.query(d.pstore, symbol, None, None, 1_000_000)
        buf = io.StringIO()
        cols = [c for c in ledger.COLS if c != "payload"] + ["counts_as_result", "exclusion"]
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        for r in rows:
            vd = universe.counts_as_result(r)
            w.writerow({**r, "counts_as_result": vd.counts,
                        "exclusion": "" if vd.counts else vd.code})
        return Response(buf.getvalue(), media_type="text/csv", headers={
            "Content-Disposition": f"attachment; filename=paper_ledger_{name}.csv"})

    return router


def make_variants(names: tuple[str, ...], store, data_dir, ctx_store, registry) -> dict:
    """Mesas variantes pedidas por `EIM_PAPER_VARIANTS`, cada una con su base propia."""
    from eim.data.paper_store import PaperStore
    from eim.paper import t143_config

    known = {t143_config.NAME: (t143_config.LABEL, t143_config.EXEC_T143,
                                t143_config.PROFILES_T143)}
    out: dict[str, VariantDesk] = {}
    for n in names:
        if n not in known:
            raise ValueError(f"EIM_PAPER_VARIANTS: corrida aparte desconocida {n!r} "
                             f"(hay: {sorted(known)})")
        label, ep, profiles = known[n]
        out[n] = VariantDesk(store, ctx_store, PaperStore(data_dir / f"paper_{n}.duckdb"),
                             name=n, label=label, exec_params=ep, profiles=profiles,
                             registry=registry)
        out[n].hooks.add("libro", out[n].ledger_tick)    # su libro fijo, en su base
    return out
