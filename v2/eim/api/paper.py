"""Rutas del bróker simulado (T47). Todo es SIMULADO: ninguna ruta envía órdenes."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Header, HTTPException, Query, Response

from eim.api.execution import confirm
from eim.data.timeframes import SYMBOLS
from eim.paper import ledger
from eim.paper.desk import PaperDesk, View
from eim.paper.live_feed import live_feed

CATS = ("orden", "llenada", "tp", "be", "sl", "tiempo", "cancelada", "rechazada", "aprendizaje",
        "violacion")
VIEW_WAIT_S = 10.0      # espera máxima por un recálculo; después se entrega la vista anterior


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


def _tfs(desk: PaperDesk, tf: str | None) -> set[str] | None:
    if tf is None:
        return None
    sel = set(tf.split(","))
    if sel - set(desk.tfs):
        raise HTTPException(400, f"marco desconocido: {sorted(sel - set(desk.tfs))} "
                                 f"(válidos: {list(desk.tfs)})")
    return sel


def _view(desk: PaperDesk, symbol: str) -> View:
    """Vista sin colgar la petición: la al día si se calcula a tiempo, si no la anterior; 503
    solo mientras se calcula la primera (la interfaz reintenta sola)."""
    v = desk.cached_view(symbol, VIEW_WAIT_S)
    if v is None:
        err = f" Último error: {desk.view_error}" if desk.view_error else ""
        raise HTTPException(503, "Calculando la vista del bróker simulado con todo el historial;"
                                 f" se actualiza sola en unos segundos.{err}")
    return v


def build_paper_router(desk: PaperDesk) -> APIRouter:
    router = APIRouter(prefix="/v2/paper")

    @router.get("")
    def summary(symbol: str = "BTCUSDT") -> dict:
        """Perfiles (cuenta, posiciones, órdenes, curva), estrategias y conclusiones."""
        _check(symbol)
        v = _view(desk, symbol)
        out = dict(v.summary)
        out["job"] = desk.job.to_json()
        out["live"] = desk.live_status()
        out["view"] = desk.view_state(v)
        return out

    @router.get("/trades")
    def trades(symbol: str = "BTCUSDT", profile: str | None = None, strategy: str | None = None,
               tf: str | None = None, limit: int = Query(500, ge=1, le=5000)) -> dict:
        """Libro de operaciones cerradas, más recientes primero (`tf`: 15m,1h,4h)."""
        _check(symbol)
        tfs = _tfs(desk, tf)
        v = _view(desk, symbol)
        rows = [{**t, "profile": pid} for pid in _profiles(desk, profile) if pid in v.books
                for t in v.books[pid].trades
                if (strategy is None or strategy in (t["strategy"], t["sid"]))
                and (tfs is None or t["timeframe"] in tfs)]
        rows.sort(key=lambda t: -t["exit_t"])
        return {"mode": "SIMULADO", "total": len(rows), "trades": rows[:limit]}

    @router.get("/ledger")
    def ledger_rows(symbol: str | None = None,
                    scope: str | None = Query(None, pattern="^(perfil|sombra)$"),
                    profile: str | None = None, limit: int = Query(500, ge=1, le=20000)) -> dict:
        """Libro de registro fijo (solo adición): operaciones cerradas en vivo, tal como ocurrieron.
        A diferencia de `/trades`, no se recalcula al cambiar reglas o costos."""
        if symbol is not None:
            _check(symbol)
        return {"mode": "SIMULADO", "counts": ledger.counts(desk.pstore),
                "error": desk.ledger_error,
                "rows": ledger.query(desk.pstore, symbol, scope, profile, limit)}

    @router.get("/ledger.csv")
    def ledger_csv(symbol: str | None = None,
                   scope: str | None = Query(None, pattern="^(perfil|sombra)$"),
                   profile: str | None = None) -> Response:
        """Exportación del libro fijo para entrenamiento/análisis externo."""
        if symbol is not None:
            _check(symbol)
        rows = ledger.query(desk.pstore, symbol, scope, profile, 1_000_000)
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=[c for c in ledger.COLS if c != "payload"])
        w.writeheader()
        w.writerows(rows)
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=paper_ledger.csv"})

    @router.get("/journal")
    def journal(symbol: str = "BTCUSDT", profile: str | None = None, cat: str | None = None,
                strategy: str | None = None, tf: str | None = None, before: int | None = None,
                limit: int = Query(200, ge=1, le=2000)) -> dict:
        """Bitácora categorizada (orden → llenado → cierre / cancelación / rechazo /
        aprendizaje), más reciente primero; `cat` admite varias separadas por coma."""
        _check(symbol)
        cats = set(cat.split(",")) if cat else set(CATS)
        bad = cats - set(CATS)
        if bad:
            raise HTTPException(400, f"categoría desconocida: {sorted(bad)} (válidas: {CATS})")
        tfs = _tfs(desk, tf)
        v = _view(desk, symbol)
        evs = [e for pid in _profiles(desk, profile) if pid in v.books
               for e in v.books[pid].events
               if (strategy is None or strategy in (e["strategy"], e["sid"]))
               and (tfs is None or e["timeframe"] in tfs)]
        counts = {c: 0 for c in CATS}
        for e in evs:
            counts[e["cat"]] += 1
        sel = [e for e in evs if e["cat"] in cats and (before is None or e["t"] < before)]
        sel.sort(key=lambda e: (-e["t"], e["idea"]))
        return {"mode": "SIMULADO", "counts": counts, "total": len(sel), "events": sel[:limit]}

    @router.get("/ideas")
    def ideas(symbol: str = "BTCUSDT", strategy: str | None = None, tf: str | None = None,
              limit: int = Query(300, ge=1, le=5000)) -> dict:
        """Evaluación sombra (igual para todos los perfiles), más recientes primero."""
        _check(symbol)
        tfs = _tfs(desk, tf)
        os_ = [o.to_json() for o in _view(desk, symbol).outcomes
               if (strategy is None or strategy in (o.idea.strategy, o.idea.sid))
               and (tfs is None or o.idea.timeframe in tfs)]
        os_.sort(key=lambda o: -o["t"])
        return {"mode": "SIMULADO", "total": len(os_), "ideas": os_[:limit]}

    @router.get("/live")
    def live(symbol: str = "BTCUSDT", limit: int = Query(100, ge=1, le=1000)) -> dict:
        """Señales en vivo: cada decisión en tiempo real, su estado en la sombra y qué hizo
        cada perfil con ella y por qué (las reconstruidas por el backtest no aparecen)."""
        _check(symbol)
        v = _view(desk, symbol)
        out = live_feed(v.outcomes, v.books, v.live_ctx, limit)
        out["live"] = desk.live_status()
        out["view"] = desk.view_state(v)
        return out

    @router.get("/status")
    def status() -> dict:
        return {"job": desk.job.to_json(), "live": desk.live_status()}

    @router.post("/backtest")
    def backtest(symbol: str = "BTCUSDT", days: float = Query(30, gt=0, le=2000),
                 step: int = Query(1, ge=1, le=24), tf: str | None = None,
                 x_eim_confirm: str | None = Header(None)) -> dict:
        """Reconstruye en segundo plano los contextos de los últimos `days` días en los marcos
        pedidos (`tf`: 15m,1h,4h; por defecto los tres; ≈1,5 s/vela por proceso). Hasta 2000
        días: todo el almacén (T49, historia para la validación); las ya hechas se saltan."""
        confirm(x_eim_confirm, "paper-backtest")
        _check(symbol)
        tfs = _tfs(desk, tf)
        try:
            return desk.start_backtest(symbol, days, step,
                                       tuple(t for t in desk.tfs if t in tfs) if tfs else None)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/backtest/stop")
    def stop(x_eim_confirm: str | None = Header(None)) -> dict:
        confirm(x_eim_confirm, "paper-backtest")
        return desk.stop_backtest()

    return router
