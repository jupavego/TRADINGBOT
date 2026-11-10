"""Rutas del bróker simulado (T47). Todo es SIMULADO: ninguna ruta envía órdenes.

Auditoría (T118): `GET /v2/paper` lleva el identificador de la instantánea de esa vista
(`snapshot.id`) y su alcance (`scope`); `GET /v2/paper/snapshot/{id}` devuelve exactamente
las cifras de entonces aunque el almacén haya cambiado, y `/trades` dice qué tramo devuelve.
"""

from __future__ import annotations

import csv
import io
import re

from fastapi import APIRouter, Header, HTTPException, Query, Response

from eim.api.execution import confirm
from eim.data.timeframes import SYMBOLS
from eim.paper import accounting, ledger, protection, snapshot, universe
from eim.paper.desk import PaperDesk, View
from eim.paper.exit_quality import desk_exit_quality
from eim.paper.live_feed import live_feed

CATS = ("orden", "llenada", "tp", "be", "sl", "tiempo", "liquidacion", "salvaguarda", "cuenta",
        "cancelada", "rechazada", "aprendizaje", "violacion")
VIEW_WAIT_S = 10.0      # espera máxima por un recálculo; después se entrega la vista anterior
SNAPSHOT_ID = re.compile(r"[0-9a-f]{12}")


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
        shown = rows[:limit]
        # la lista puede ser un tramo de las más recientes: se dice cuál, nunca pasa por el total
        return {"mode": "SIMULADO", "total": len(rows), "shown": len(shown),
                "shown_from": shown[-1]["exit_t"] if shown else None,
                "shown_to": shown[0]["exit_t"] if shown else None,
                "snapshot": (v.summary.get("snapshot") or {}).get("id"), "trades": shown}

    @router.get("/exits")
    def exits(symbol: str = "BTCUSDT") -> dict:
        """Calidad de la salida por perfil y A/B en vivo frente a la sombra (T130)."""
        _check(symbol)
        v = _view(desk, symbol)
        return {"mode": "SIMULADO", "symbol": symbol,
                "snapshot": (v.summary.get("snapshot") or {}).get("id"),
                "view": desk.view_state(v), "profiles": desk_exit_quality(v.books, v.outcomes)}

    @router.get("/snapshot/{sid}")
    def snapshot_get(sid: str) -> dict:
        """La foto de una vista ya mostrada, tal como se guardó (T118); `intact` = su huella
        coincide con el identificador (nadie la alteró)."""
        if not SNAPSHOT_ID.fullmatch(sid):
            raise HTTPException(400, f"identificador de instantánea inválido: {sid!r} (12 hex)")
        got = snapshot.get(desk.pstore, sid)
        if got is None:
            raise HTTPException(404, f"la instantánea {sid} no está en este almacén: las "
                                     "instantáneas son de la máquina que las calculó y la "
                                     "experiencia compartida no las lleva")
        return {"mode": "SIMULADO", **got}

    @router.get("/snapshots")
    def snapshot_list(symbol: str | None = None,
                      limit: int = Query(50, ge=1, le=1000)) -> dict:
        """Instantáneas guardadas, más recientes primero, con las operaciones de cada perfil."""
        if symbol is not None:
            _check(symbol)
        return {"mode": "SIMULADO", "error": desk.snapshot_error,
                "snapshots": snapshot.listing(desk.pstore, symbol, limit)}

    @router.get("/ledger")
    def ledger_rows(symbol: str | None = None,
                    scope: str | None = Query(None, pattern="^(perfil|sombra)$"),
                    profile: str | None = None, limit: int = Query(500, ge=1, le=20000)) -> dict:
        """Libro de registro fijo (solo adición): operaciones cerradas en vivo, tal como ocurrieron.
        A diferencia de `/trades`, no se recalcula al cambiar reglas o costos."""
        if symbol is not None:
            _check(symbol)
        rows = ledger.query(desk.pstore, symbol, scope, profile, limit)
        # T144: el libro también declara el universo oficial y su recuento; cada fila lleva por
        # qué cuenta o por qué no, así que nadie tiene que deducirlo (ni excluir `retro` a mano).
        return {"mode": "SIMULADO", "counts": ledger.counts(desk.pstore),
                "error": desk.ledger_error, "universe": universe.declaration(),
                "tally": universe.tally(rows),
                "rows": [{**r, "counts_as_result": universe.counts_as_result(r).to_json()}
                         for r in rows]}

    @router.get("/accounting")
    def official_accounting(symbol: str | None = None, from_t: int | None = None,
                            to_t: int | None = None) -> dict:
        """Cifras de resultado del universo OFICIAL de T31 (T144): solo lo que cuenta.

        Una sola función decide qué entra (`eim.paper.universe.counts_as_result`) y la respuesta
        lleva la regla escrita, el recuento (cuántas existen, cuántas cuentan, por qué quedan
        fuera las demás) y las `retro` aparte con su etiqueta. Sin `from_t`/`to_t`, todo el libro.
        """
        if symbol is not None:
            _check(symbol)
        t0, t1 = from_t or 0, to_t or 2 ** 62
        return {"mode": "SIMULADO", "symbol": symbol, "from_t": from_t, "to_t": to_t,
                "error": desk.ledger_error,
                **accounting.from_store(desk.pstore, symbol, t0, t1)}

    @router.get("/ledger.csv")
    def ledger_csv(symbol: str | None = None,
                   scope: str | None = Query(None, pattern="^(perfil|sombra)$"),
                   profile: str | None = None) -> Response:
        """Exportación del libro fijo para entrenamiento/análisis externo."""
        if symbol is not None:
            _check(symbol)
        rows = ledger.query(desk.pstore, symbol, scope, profile, 1_000_000)
        buf = io.StringIO()
        # T144: la exportación lleva el veredicto del universo oficial para que un análisis
        # externo no tenga que deducirlo ni excluir las `retro` a mano.
        cols = [c for c in ledger.COLS if c != "payload"] + ["counts_as_result", "exclusion"]
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        for r in rows:
            v = universe.counts_as_result(r)
            w.writerow({**r, "counts_as_result": v.counts,
                        "exclusion": "" if v.counts else v.code})
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

    @router.get("/protection")
    def protection_journal(symbol: str | None = None, status: str | None = None,
                           limit: int = Query(500, ge=1, le=20000)) -> dict:
        """Diario de la protección (T110): estado vigente de cada operación con escalera (escalón,
        máximo neto, SL vigente, costos, historial de cambios del stop) e inconsistencias."""
        if symbol is not None:
            _check(symbol)
        if status is not None and status not in protection.STATUSES:
            raise HTTPException(400, f"estado desconocido: {status} "
                                     f"(válidos: {list(protection.STATUSES)})")
        return {"mode": "SIMULADO", **desk.protection_overview(symbol, status, limit)}

    @router.get("/protection/history")
    def protection_history(op_id: str) -> dict:
        """Todas las filas de una operación en el diario (solo adición), de la primera a la
        vigente."""
        rows = protection.history(desk.pstore, op_id)
        if not rows:
            raise HTTPException(404, f"el diario no tiene la operación {op_id}")
        return {"mode": "SIMULADO", "op_id": op_id, "rows": rows}

    @router.post("/protection/resolve")
    def protection_resolve(op_id: str,
                           decision: str = Query(..., pattern="^(recalculo|descartar)$"),
                           note: str = Query(..., min_length=3, max_length=300),
                           x_eim_confirm: str | None = Header(None)) -> dict:
        """Reconciliación manual de una operación en estado inconsistente: `recalculo` (el
        recálculo pasa a mandar) o `descartar` (el diario deja de seguirla). Queda anotada."""
        confirm(x_eim_confirm, "paper-protection")
        try:
            return {"mode": "SIMULADO", "row": desk.resolve_protection(op_id, decision, note)}
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

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
