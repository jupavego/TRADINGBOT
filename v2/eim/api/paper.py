"""Rutas del bróker simulado (T47). Todo es SIMULADO: ninguna ruta envía órdenes."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from eim.api.execution import confirm
from eim.data.timeframes import SYMBOLS
from eim.paper.desk import PaperDesk

CATS = ("orden", "llenada", "tp", "sl", "tiempo", "cancelada", "rechazada", "aprendizaje")


def _check(symbol: str) -> None:
    if symbol not in SYMBOLS:
        raise HTTPException(400, f"símbolo no soportado: {symbol} (válidos: {list(SYMBOLS)})")


def _profiles(desk: PaperDesk, profile: str | None) -> list[str]:
    ids = [p.id for p in desk.profiles]
    if profile is None:
        return ids
    if profile not in ids:
        raise HTTPException(400, f"perfil desconocido: {profile} (válidos: {ids})")
    return [profile]


def build_paper_router(desk: PaperDesk) -> APIRouter:
    router = APIRouter(prefix="/v2/paper")

    @router.get("")
    def summary(symbol: str = "BTCUSDT") -> dict:
        """Perfiles (cuenta, posiciones, órdenes, curva), estrategias y conclusiones."""
        _check(symbol)
        out = dict(desk.view(symbol).summary)
        out["job"] = desk.job.to_json()
        out["live"] = {"last_tick": desk.last_tick, "error": desk.live_error}
        return out

    @router.get("/trades")
    def trades(symbol: str = "BTCUSDT", profile: str | None = None, strategy: str | None = None,
               limit: int = Query(500, ge=1, le=5000)) -> dict:
        """Libro de operaciones cerradas, más recientes primero."""
        _check(symbol)
        v = desk.view(symbol)
        rows = [{**t, "profile": pid} for pid in _profiles(desk, profile) if pid in v.books
                for t in v.books[pid].trades if strategy is None or t["strategy"] == strategy]
        rows.sort(key=lambda t: -t["exit_t"])
        return {"mode": "SIMULADO", "total": len(rows), "trades": rows[:limit]}

    @router.get("/journal")
    def journal(symbol: str = "BTCUSDT", profile: str | None = None, cat: str | None = None,
                strategy: str | None = None, before: int | None = None,
                limit: int = Query(200, ge=1, le=2000)) -> dict:
        """Bitácora categorizada (orden → llenado → cierre / cancelación / rechazo /
        aprendizaje), más reciente primero; `cat` admite varias separadas por coma."""
        _check(symbol)
        cats = set(cat.split(",")) if cat else set(CATS)
        bad = cats - set(CATS)
        if bad:
            raise HTTPException(400, f"categoría desconocida: {sorted(bad)} (válidas: {CATS})")
        v = desk.view(symbol)
        evs = [e for pid in _profiles(desk, profile) if pid in v.books
               for e in v.books[pid].events]
        counts = {c: 0 for c in CATS}
        for e in evs:
            if strategy is None or e["strategy"] == strategy:
                counts[e["cat"]] += 1
        sel = [e for e in evs if e["cat"] in cats
               and (strategy is None or e["strategy"] == strategy)
               and (before is None or e["t"] < before)]
        sel.sort(key=lambda e: (-e["t"], e["idea"]))
        return {"mode": "SIMULADO", "counts": counts, "total": len(sel), "events": sel[:limit]}

    @router.get("/ideas")
    def ideas(symbol: str = "BTCUSDT", strategy: str | None = None,
              limit: int = Query(300, ge=1, le=5000)) -> dict:
        """Evaluación sombra (igual para todos los perfiles), más recientes primero."""
        _check(symbol)
        os_ = [o.to_json() for o in desk.view(symbol).outcomes
               if strategy is None or o.idea.strategy == strategy]
        os_.sort(key=lambda o: -o["t"])
        return {"mode": "SIMULADO", "total": len(os_), "ideas": os_[:limit]}

    @router.get("/status")
    def status() -> dict:
        return {"job": desk.job.to_json(), "live": {"last_tick": desk.last_tick,
                                                    "error": desk.live_error}}

    @router.post("/backtest")
    def backtest(symbol: str = "BTCUSDT", days: float = Query(30, gt=0, le=365),
                 step: int = Query(1, ge=1, le=24),
                 x_eim_confirm: str | None = Header(None)) -> dict:
        """Reconstruye en segundo plano los contextos de los últimos `days` días (≈1,5 s/vela)."""
        confirm(x_eim_confirm, "paper-backtest")
        _check(symbol)
        try:
            return desk.start_backtest(symbol, days, step)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/backtest/stop")
    def stop(x_eim_confirm: str | None = Header(None)) -> dict:
        confirm(x_eim_confirm, "paper-backtest")
        return desk.stop_backtest()

    return router
