"""Pasada de agentes del escáner (T94): lista corta → cola `deep_run` → registro → vista.

Toma la lista corta de un barrido de T93 (el último, si no se pide otro), encola un trabajo
`deep_run` por instrumento (como mucho 2 procesos, caché por datos y versiones), guarda en
`scanner.duckdb` el resultado de cada uno (`deep_results`) y las oportunidades candidatas
(`opportunities`), manda al Observatorio un resumen y las oportunidades más fuertes (muestreo) y
publica `data/scanner/view.json` para la API.

La huella de datos del trabajo combina la del panel con la de los agentes (id y versión) y con
lo que alimenta las puntuaciones: si cambia una vela, un agente o el diferencial, la caché no
sirve. Ningún paso envía órdenes ni toca el flujo de operación.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from eim.core import Agent
from eim.core.opportunity import stable_hash
from eim.data import scanner_market as market
from eim.data.scanner_view import build_view, write_view
from eim.data.timeframes import tf_ms, tf_offset
from eim.observability import hooks_service
from eim.scanner import rhythms, universe
from eim.scanner.backends import make_job
from eim.scanner.service import COMPONENT, ScannerError, ScannerService


def _spreads(svc: ScannerService, insts, asof: int) -> dict[str, float]:
    quotes = svc.quotes_fn() if svc.quotes_fn else {}
    return rhythms.spreads_of(quotes, insts, asof, svc.p.quote_max_age_ms)


def deep_pass(svc: ScannerService, *, base_run_id: str | None = None,
              agents: Sequence[Agent] | None = None, deadline_s: float | None = None,
              catalog: tuple | None = None, publish: bool = True) -> dict:
    """Corre los agentes elegibles sobre la lista corta de un barrido y publica la vista."""
    from eim.scanner import deep

    p, started = svc.p, svc.clock()
    base = svc.store.run_info(base_run_id) if base_run_id else None
    if base is None:
        last = svc.store.last_run("profundo")
        base = svc.store.run_info(last["run_id"]) if last else None
    if base is None:
        raise ScannerError("sin barrido: corre antes `python -m eim.scanner sweep --asof latest`")
    tf, asof = base["timeframe"], int(base["asof"])
    short: list[str] = list(base["detail"].get("shortlist") or [])
    insts_all, _ = catalog if catalog is not None else market.read_catalog(svc.data_dir, p.venue)
    insts = {i.id: i for i in insts_all}
    scores = svc.store.scores_of(base["run_id"])
    by_id = {s["instrument_id"]: s for s in scores}
    cut = universe.closed_cut(tf_ms(tf), asof, tf_offset(tf))
    agents = list(agents) if agents is not None else deep.default_agents()
    afp = deep.agents_fingerprint(agents)
    todo = [i for i in short if i in insts and i in by_id]
    spreads = _spreads(svc, [insts[i] for i in todo], asof)
    svc._seq += 1                                    # noqa: SLF001 - mismo contador de corridas
    deep_run_id = f"agentes-{started}-{svc._seq}"    # noqa: SLF001
    jobs = []
    for k, iid in enumerate(todo):
        s = by_id[iid]
        screen = {"score": s["score"], "quality": s["quality"], "rank": s["rank"]}
        sp = spreads.get(iid)
        jobs.append(make_job(
            deep_run_id, "deep_run", iid, tf, "profundo", priority=len(todo) - k, t=svc.clock(),
            data_hash=stable_hash([s["data_hash"], afp, screen,
                                   None if sp is None else round(sp, 1)]),
            payload={"instrument": insts[iid].model_dump(mode="json"), "root": str(svc.root),
                     "timeframe": tf, "n_bars": p.deep_bars, "cut": cut, "asof": asof,
                     "run_id": base["run_id"], "screen": screen, "spread_bps": sp}))
    svc.queue.submit(jobs)
    qs = svc.queue.run_pending(run_id=deep_run_id, deadline_s=deadline_s)
    done = svc.store.by_state("done", deep_run_id)
    failed = svc.store.by_state("failed", deep_run_id)
    results = [j.result for j in sorted(done, key=lambda j: -j.priority) if j.result]
    svc.store.record_deep(deep_run_id, base["run_id"], results)
    opps = [r["opportunity"] for r in results if r.get("opportunity")]
    reasons = Counter(r["reason"].split(" (")[0] for r in results if r.get("reason"))
    summary = {
        "run_id": deep_run_id, "rhythm": "agentes", "started_at": started, "asof": asof,
        "timeframe": tf, "n_shortlist": len(todo), "status": "ok",
        "detail_json": {"base_run": base["run_id"], "n_opportunities": len(opps),
                        "n_without": len(results) - len(opps), "reasons": dict(reasons),
                        "failed": [{"instrument_id": j.instrument_id, "error": j.error}
                                   for j in failed],
                        "agents_fingerprint": afp, "queue": qs.as_json(),
                        "skipped_not_in_catalog": sorted(set(short) - set(todo))}}
    summary["finished_at"] = svc.clock()
    svc.store.record_run(summary)
    _observe(svc, summary, opps)
    if publish:
        publish_view(svc, base, deep_run_id, results, insts)
    svc.write_status({"last_deep": {"run_id": deep_run_id, "base_run": base["run_id"],
                                    "opportunities": len(opps), "failed": len(failed)}})
    return summary | {"opportunities": opps, "results": results}


def publish_view(svc: ScannerService, base: dict, deep_run_id: str, results: list[dict],
                 insts: dict) -> None:
    now = svc.clock()
    state = {i.id: rhythms.market_state(i, now) for i in insts.values()}
    view = build_view(base=base, scores=svc.store.scores_of(base["run_id"]), insts=insts,
                      market_state=state, deep_run={"run_id": deep_run_id, "asof": base["asof"]},
                      results=results, runs=svc.store.recent_runs(20), now=now)
    write_view(svc.data_dir, view)


def _observe(svc: ScannerService, s: dict, opps: list[dict]) -> None:
    d = s["detail_json"]
    hooks_service.service_event(
        COMPONENT, "pasada de agentes", status="degraded" if d["failed"] else "ok",
        detail={"run": s["run_id"], "base_run": d["base_run"], "shortlist": s["n_shortlist"],
                "opportunities": d["n_opportunities"], "failed": len(d["failed"])})
    top = sorted(opps, key=lambda o: -o["scores"]["signal_quality"])[:svc.p.obs_max_alerts]
    for o in top:                     # muestreo: solo las más fuertes, con su trazabilidad
        hooks_service.service_event(
            COMPONENT, "oportunidad candidata (no validada)",
            detail={"opportunity_id": o["opportunity_id"], "instrument": o["instrument_id"],
                    "side": o["side"], "input_hash": o["input_hash"],
                    "agents": [f"{a['agent_id']}@{a['version']}" for a in o["agents"]],
                    "signal_quality": o["scores"]["signal_quality"]})
