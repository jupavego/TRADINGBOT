"""Servicio del escáner global (T93): un barrido del embudo completo y la pasada rápida.

`sweep` (ritmo profundo): catálogo → etapa 1 → panel (una consulta) → etapa 2 → etapa 3 →
registro en `scanner.duckdb` → lista corta a la cola. `fast` (ritmo rápido): alertas de precio
y diferencial sobre lo ya puntuado. `sync`: relleno de velas del universo por la cola, con su
límite de tasa. El bucle supervisado (latido, reintentos) está en `runner.py`.

**Sin órdenes.** El escáner no importa nada de ejecución, riesgo ni papel: solo lee datos,
puntúa y prepara. El flujo de operación existente no cambia.
"""

from __future__ import annotations

import json
import time
import warnings
from collections.abc import Callable, Mapping
from pathlib import Path

import numpy as np

from eim.data import scanner_market as market
from eim.data.timeframes import tf_ms, tf_offset
from eim.observability import hooks_service
from eim.scanner import rhythms, screen, universe
from eim.scanner.params import DAY_MS, DEFAULT_PARAMS, ScannerParams
from eim.scanner.queue import JobQueue

COMPONENT = "scanner.service"
STATUS_FILE = "status.json"


class ScannerError(RuntimeError):
    """El escáner no puede barrer (catálogo vacío, sin datos): se dice y no se inventa."""


def _now() -> int:
    return int(time.time() * 1000)


def data_stats(panel, p: ScannerParams) -> dict[str, universe.DataStats]:
    """Estadísticas por instrumento del panel para la etapa 2 (vectorizadas)."""
    out: dict[str, universe.DataStats] = {}
    k = p.liquidity_bars
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)     # fila sin velas: mediana NaN
        qv = panel.v[:, -k:] * panel.c[:, -k:] if panel.size else np.zeros((0, k))
        med = np.nanmedian(qv, axis=1) if panel.size else np.zeros(0)
    for i, iid in enumerate(panel.ids):
        n = int(panel.n[i])
        out[iid] = universe.DataStats(
            n_bars=n, last_t=int(panel.t[i, -1]) if n else None,
            last_close=float(panel.c[i, -1]) if n else None,
            median_quote_volume=float(med[i]) if n and np.isfinite(med[i]) else None)
    return out


class ScannerService:
    def __init__(self, data_dir: str | Path, params: ScannerParams = DEFAULT_PARAMS, *,
                 store=None, universe_root: str | Path | None = None,
                 quotes_fn: Callable[[], Mapping] | None = None, procs: int | None = None,
                 clock: Callable[[], int] = _now) -> None:
        from eim.data.scanner_store import open_scanner_store

        self.data_dir, self.p, self.clock = Path(data_dir), params, clock
        self.root = Path(universe_root) if universe_root else market.universe_root(data_dir)
        self.store = store if store is not None else open_scanner_store(data_dir)
        self.queue = JobQueue(self.store, self.store, procs=procs or params.max_procs,
                              max_attempts=params.max_attempts, backoff_s=params.backoff_s,
                              max_backoff_s=params.max_backoff_s, rate_limits=params.rate_limits)
        self.quotes_fn = quotes_fn
        self.dir = self.data_dir / "scanner"
        self.last: dict = {}
        self._seq = 0

    def close(self) -> None:
        self.queue.close()
        self.store.close()

    # --- ritmo profundo -----------------------------------------------------------------------
    def sweep(self, asof: int | None = None, *, catalog: tuple | None = None,
              process_deep: bool = True, deep_deadline_s: float | None = None) -> dict:
        p, started = self.p, self.clock()
        asof = started if asof is None else int(asof)
        self._seq += 1
        run_id = f"barrido-{started}-{self._seq}"
        tm: dict[str, float] = {}
        t0 = time.perf_counter()
        insts, events = catalog if catalog is not None else market.read_catalog(
            self.data_dir, p.venue, events_since=asof - p.lifecycle_days * DAY_MS)
        if not insts:
            raise ScannerError("catálogo vacío: corre `python -m eim.scanner sync --discover` "
                               "(descubrimiento de T89, 1 llamada pública)")
        tm["catalog_s"] = time.perf_counter() - t0
        t = time.perf_counter()
        k1, x1 = universe.stage1(insts, p, asof)
        tm["stage1_s"] = time.perf_counter() - t
        step, off = tf_ms(p.timeframe), tf_offset(p.timeframe)
        cut = universe.closed_cut(step, asof, off)
        t = time.perf_counter()
        panel = market.load_panel(self.root, {i.symbol: i.id for i in k1}, p.timeframe,
                                  p.n_bars, cut)
        tm["load_s"] = time.perf_counter() - t
        t = time.perf_counter()
        quotes = self.quotes_fn() if self.quotes_fn else {}     # red: fuera del presupuesto
        tm["quotes_s"] = time.perf_counter() - t
        t = time.perf_counter()
        stats = data_stats(panel, p)
        for iid, s in rhythms.spreads_of(quotes, k1, asof, p.quote_max_age_ms).items():
            st = stats.get(iid)
            if st is not None:
                stats[iid] = universe.DataStats(st.n_bars, st.last_t, st.last_close,
                                                st.median_quote_volume, s)
        k2, x2, notes = universe.stage2(k1, stats, p, step, asof, off)
        tm["stage2_s"] = time.perf_counter() - t
        t = time.perf_counter()
        pos = {iid: r for r, iid in enumerate(panel.ids)}
        sub = panel.take([pos[i.id] for i in k2])
        res = screen.screen(sub, [i.asset_class.value for i in k2])
        tm["screen_s"] = time.perf_counter() - t
        funnel_s = sum(tm[k] for k in ("catalog_s", "stage1_s", "load_s", "stage2_s",
                                       "screen_s"))
        # Por instrumento que llega a la etapa 2 (el que se lee del almacén): la cuenta estricta;
        # las bajas de la etapa 1 no cuestan casi nada y diluirían el costo.
        ms_per = funnel_s * 1000 / len(k1) if k1 else 0.0
        rows = res.rows()
        for r in rows:
            i = pos[r["instrument_id"]]
            r.update(data_hash=panel.hashes[i], last_t=int(panel.t[i, -1]),
                     last_close=float(panel.c[i, -1]))
        short = res.shortlist(p.shortlist_size, p.min_score)
        t = time.perf_counter()
        exclusions = x1 + x2
        summary = {
            "run_id": run_id, "rhythm": "profundo", "started_at": started, "asof": asof,
            "timeframe": p.timeframe, "n_catalog": len(insts), "n_stage1": len(k1),
            "n_stage2": len(k2), "n_scored": len(rows), "n_shortlist": len(short),
            "screen_version": res.version, "params_json": p.model_dump(mode="json"),
            "ms_per_instrument": round(ms_per, 4), "budget_ms": p.budget_ms_per_instrument,
            "within_budget": ms_per <= p.budget_ms_per_instrument,
            "fingerprint": res.fingerprint(), "status": "ok",
            "detail_json": {"exclusions": universe.UniverseResult(k2, exclusions).counts,
                            "notes": dict(notes), "lifecycle": universe.lifecycle(
                                events, asof, p.lifecycle_days),
                            "screen_ms_per_instrument": round(res.ms_per_instrument, 5),
                            "shortlist": short, "panel_bytes": panel.nbytes()}}
        self.store.record_exclusions(run_id, [(e.instrument_id, e.stage, e.reason, e.detail)
                                              for e in exclusions])
        self.store.record_scores(run_id, rows)
        tm["persist_s"] = time.perf_counter() - t
        t = time.perf_counter()
        insts_by_id = {i.id: i for i in k2}
        jobs = rhythms.deep_jobs(run_id, short, insts_by_id, {r["instrument_id"]: r["data_hash"]
                                                              for r in rows},
                                 root=str(self.root), timeframe=p.timeframe, n_bars=p.deep_bars,
                                 cut=cut, asof=asof, t=self.clock())
        self.queue.submit(jobs)
        qs = self.queue.run_pending(deadline_s=deep_deadline_s, run_id=run_id) \
            if process_deep else None
        tm["deep_s"] = time.perf_counter() - t
        tm["total_s"] = time.perf_counter() - t0
        summary.update(finished_at=self.clock(),
                       timings_json={k: round(v, 4) for k, v in tm.items()})
        summary["detail_json"]["queue"] = qs.as_json() if qs else None
        self.store.record_run(summary)
        self._observe_sweep(summary, qs)
        self.last = summary
        self.write_status({"last_sweep": _brief(summary)})
        return summary

    # --- ritmo rápido -------------------------------------------------------------------------
    def fast(self, asof: int | None = None, *, catalog: tuple | None = None) -> dict:
        p, started = self.p, self.clock()
        asof = started if asof is None else int(asof)
        last = self.store.last_run("profundo")
        if last is None:
            return {"rhythm": "rapido", "status": "sin_barrido", "alerts": 0}
        insts, _ = catalog if catalog is not None else market.read_catalog(self.data_dir, p.venue)
        quotes = self.quotes_fn() if self.quotes_fn else {}
        res = rhythms.fast_pass(self.store.scores_of(last["run_id"]), quotes,
                                {i.id: i for i in insts}, asof, p)
        self._seq += 1
        run_id = f"rapido-{started}-{self._seq}"
        self.store.record_alerts(run_id, res.alerts)
        out = {"run_id": run_id, "rhythm": "rapido", "started_at": started, "asof": asof,
               "timeframe": p.timeframe, "status": "ok", "finished_at": self.clock(),
               "detail_json": {"base_run": last["run_id"], "checked": res.checked,
                               "alerts": len(res.alerts), "skipped": dict(res.skipped)}}
        self.store.record_run(out)
        top = sorted(res.alerts, key=lambda a: -abs(a["value"]))[:p.obs_max_alerts]
        for a in top:                    # muestreo: solo las más fuertes llegan al observatorio
            hooks_service.service_event(COMPONENT, f"alerta {a['kind']}", status="degraded",
                                        detail={"instrument": a["instrument_id"],
                                                "value": a["value"]})
        self.write_status({"last_fast": {"run_id": run_id, "asof": asof,
                                         "alerts": len(res.alerts), "checked": res.checked}})
        return out | {"alerts": len(res.alerts)}

    # --- relleno ------------------------------------------------------------------------------
    def sync(self, *, limit: int | None = None, now: int | None = None,
             discover: bool = False) -> dict:
        """Pone al día las velas de los perpetuos activos del universo (lo más viejo antes)."""
        p, now = self.p, self.clock() if now is None else now
        out: dict = {}
        if discover:
            out["catalog"] = market.refresh_catalog(self.data_dir)
        insts, _ = market.read_catalog(self.data_dir, p.venue)
        k1, _ = universe.stage1(insts, p, now)
        panel = market.load_panel(self.root, {i.symbol: i.id for i in k1}, p.timeframe, 1,
                                  universe.closed_cut(tf_ms(p.timeframe), now,
                                                      tf_offset(p.timeframe)))
        last = dict(zip(panel.ids, panel.last_t().tolist(), strict=True))
        newest = universe.closed_cut(tf_ms(p.timeframe), now, tf_offset(p.timeframe)) \
            - tf_ms(p.timeframe)                   # apertura de la última vela ya cerrada
        todo = sorted((i for i in k1 if last.get(i.id, 0) < newest),   # al día: sin llamada
                      key=lambda i: (last.get(i.id, 0), i.id))
        jobs = rhythms.sync_jobs(f"relleno-{now}", todo, root=str(self.root),
                                 timeframe=p.timeframe, now=now, days=p.sync_days,
                                 limit=limit if limit is not None else p.sync_per_cycle)
        self.queue.submit(jobs)
        qs = self.queue.run_pending(run_id=jobs[0].run_id if jobs else None)
        return out | {"symbols": len(jobs), "up_to_date": len(k1) - len(todo),
                      "queue": qs.as_json()}

    # --- estado y observatorio ----------------------------------------------------------------
    def write_status(self, patch: dict) -> None:
        f = self.dir / STATUS_FILE
        try:
            cur = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except (OSError, ValueError):
            cur = {}
        cur.update(patch, queue=self.store.counts(), updated_at=self.clock())
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(f)
        except OSError:
            pass                          # el estado es informativo: nunca tumba un barrido

    def _observe_sweep(self, s: dict, qs) -> None:
        hooks_service.beat(COMPONENT, status="ok" if s["within_budget"] else "degraded",
                           duration_ms=s["timings_json"]["total_s"] * 1000,
                           min_interval_s=self.p.obs_min_interval_s, detail=_brief(s))
        if qs is not None and qs.failed:
            hooks_service.service_error(COMPONENT, f"{qs.failed} trabajos fallidos",
                                        min_interval_s=self.p.obs_min_interval_s)


def _brief(s: dict) -> dict:
    return {k: s.get(k) for k in ("run_id", "asof", "n_catalog", "n_stage1", "n_stage2",
                                  "n_scored", "n_shortlist", "ms_per_instrument",
                                  "within_budget", "fingerprint")}
