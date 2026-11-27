"""Ranking, duplicados y multiplicidad tras cada pasada de agentes (T95). Modo ANÁLISIS.

Después de `deep_pass` (T94), con los resultados ya guardados:

1. relee las últimas velas de cada instrumento analizado (σ de su horizonte y correlaciones);
2. **ranking** comparable (`rank.py`) con los pesos vigentes y **grupos** de apuestas
   correlacionadas (`clusters.py`): un representante por grupo con su exposición agregada;
3. **registra los intentos** de la pasada (instrumento × agente × marco × versión × horizonte, la
   síntesis incluida) y **madura** las observaciones cuyo horizonte ya cerró (resultado hacia
   adelante, neto del costo de su clase);
4. recalcula el p bruto de los intentos con maduras nuevas y ajusta **sobre la familia completa**
   (los previos de T49 + los del escáner): Holm, BH y Sharpe deflactado (`multiplicity.py`);
5. marca qué candidatas superan el **umbral del placebo** vigente (`placebo_eval.py`); si el placebo
   falta o es de otras versiones, ninguna se marca.

Nada de esto es una orden ni una validación: la única puerta que valida es la v1 de T49.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence

from eim.data import scanner_market as market
from eim.data.timeframes import tf_ms
from eim.instruments.models import Instrument
from eim.scanner import clusters, multiplicity, placebo_eval, rank
from eim.validation.criteria import load_criteria

RANKING_VERSION = "1.0.0"


def synthesis_version(versions: Mapping[str, str], agents_fp: str) -> str:
    """Versión del intento «síntesis»: la de la síntesis, la etapa profunda, las puntuaciones y
    la huella de los agentes (otro agente o versión = otra hipótesis: la familia crece)."""
    return f"{versions['synthesis']}-d{versions['deep']}-s{versions['scoring']}-a{agents_fp}"


def _windows(svc, results: Sequence[Mapping], insts: Mapping[str, Instrument], tf: str,
             cut: int) -> dict[str, list]:
    need = max(rank.SIGMA_BARS, clusters.CORR_BARS) + 1
    out = {}
    for r in results:
        inst = insts.get(r["instrument_id"])
        if inst is not None:
            out[inst.id] = market.read_window(svc.root, inst.symbol, tf, need, cut)
    return out


def _cost(inst: Instrument, opp: Mapping | None, last) -> float | None:
    if opp is not None:
        return opp["scores"]["components"].get("round_trip_cost")
    from eim.scanner.candidates import round_trip_cost

    return round_trip_cost(inst, last)[0]


def mature(svc, cut: int, step: int) -> int:
    """Madura las observaciones cuyo horizonte ya cerró (cierre de la vela final releído)."""
    pend = svc.store.pending_obs(cut)
    by_sym: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in pend:
        by_sym[(p["symbol"], p["timeframe"])].append(p)
    done = []
    for (sym, tf), rows in by_sym.items():
        st = tf_ms(tf)
        closes = market.read_closes(svc.root, sym, tf, min(r["end_cut_ms"] for r in rows) - st,
                                    max(r["end_cut_ms"] for r in rows))
        for r in rows:
            c_end = closes.get(r["end_cut_ms"] - st)
            if c_end is None or c_end <= 0 or r["close0"] <= 0:
                continue                        # hueco en los datos: sigue pendiente
            o, f = multiplicity.outcome(r["side"], r["close0"], c_end, r["sigma_h"], r["cost"])
            done.append((r["attempt_key"], r["cut_ms"], c_end, o, f))
    return svc.store.mature_obs(done)


def refresh_pvalues(svc, crit) -> int:
    keys = svc.store.stale_keys()
    if not keys:
        return 0
    fam = multiplicity.family_size(len(svc.store.family()))
    series = svc.store.matured_series(keys)
    svc.store.set_stats((k, multiplicity.pvalue(o, f, fam, k, crit), len(o),
                         multiplicity.dsr(o, fam)) for k, (o, f) in series.items())
    return len(keys)


def rank_pass(svc, *, deep_run_id: str, base: Mapping, results: Sequence[Mapping],
              insts: Mapping[str, Instrument], cut: int, agents_fp: str) -> dict:
    from eim.scanner import deep

    tf, step = base["timeframe"], tf_ms(base["timeframe"])
    crit = load_criteria()
    alpha = crit.v3_random.alpha
    wins = _windows(svc, results, insts, tf, cut)
    closes = {k: [c.c for c in v] for k, v in wins.items()}
    series = {k: ([c.t for c in v], [c.c for c in v]) for k, v in wins.items()}
    opps = [r["opportunity"] for r in results if r.get("opportunity")]
    w = rank.load_weights(svc.data_dir)
    ranked = rank.rank(opps, closes, w)
    legs_of = {k: clusters.legs(insts[k].symbol, insts[k].quote_currency, insts[k].underlying)
               for k in wins}
    groups = clusters.cluster(ranked, legs_of, series)
    versions = deep.versions()
    syn_v = synthesis_version(versions, agents_fp)
    by_opp = {r["opportunity_id"]: r for r in ranked}
    atts = []
    for r in results:
        cs, inst = wins.get(r["instrument_id"]), insts.get(r["instrument_id"])
        if not cs or inst is None:
            continue
        sb = rank.bar_sigma([c.c for c in cs])
        opp = r.get("opportunity")
        atts += multiplicity.attempts_of(
            r, horizon_bars=deep.HORIZON, close0=cs[-1].c,
            sigma_h=None if sb is None else sb * math.sqrt(deep.HORIZON),
            cost=_cost(inst, opp, cs[-1]), synthesis_version=syn_v,
            scores=by_opp[opp["opportunity_id"]]["normalized"]["scores"] if opp else None)
    new_obs = svc.store.record_attempts(deep_run_id, cut, step, atts)
    matured = mature(svc, cut, step)
    refreshed = refresh_pvalues(svc, crit)
    fam = svc.store.family()
    total = multiplicity.family_size(len(fam))
    adj = multiplicity.adjust(fam)
    fp = placebo_eval.fingerprint(w, agents_fp, versions)
    thr = placebo_eval.load_threshold(svc.data_dir, fp)
    rep_of = {m["opportunity_id"]: g for g in groups for m in g["members"]}
    keys = {r["instrument_id"]: multiplicity.attempt_key(r["instrument_id"],
                                                          multiplicity.SYNTHESIS_AGENT, tf,
                                                          syn_v, deep.HORIZON) for r in ranked}
    stats = svc.store.attempt_stats(list(keys.values()))
    rows = []
    for r in ranked:
        g = rep_of.get(r["opportunity_id"])
        k = keys[r["instrument_id"]]
        above = (thr["status"] == "vigente" and thr["value"] is not None
                 and r["priority"] is not None and r["priority"] >= thr["value"])
        rows.append(r | {"above_threshold": bool(above),
                         "cluster_id": g["cluster_id"] if g else None,
                         "representative": bool(g and g["representative"] == r["opportunity_id"]),
                         "multiplicity": multiplicity.present(k, stats.get(k), adj, total, alpha)})
    return {
        "version": RANKING_VERSION, "available": True, "mode": "ANALISIS", "deep_run": deep_run_id,
        "weights": w.as_json(), "threshold": thr,
        "family": {"prior": multiplicity.PRIOR_FAMILY, "prior_source": multiplicity.PRIOR_SOURCE,
                   "scanner": len(fam), "total": total, "alpha": alpha,
                   "correction": "Holm (vinculante) y Benjamini–Hochberg (informativa) sobre "
                                 "la familia completa; Sharpe deflactado por su tamaño",
                   "min_obs": multiplicity.MIN_OBS, "new_observations": new_obs,
                   "matured_now": matured, "pvalues_refreshed": refreshed,
                   **svc.store.attempt_counts()},
        "n_comparable": sum(r["priority"] is not None for r in rows),
        "n_above": sum(r["above_threshold"] for r in rows),
        "n_groups": len(groups), "rows": rows, "clusters": groups,
        "rules": "candidata: nº de hipótesis de su familia y p ajustado a la vista; «validada» "
                 "solo si cumple la puerta v1 de T49 (ninguna del escáner la cumple todavía)",
    }


def brief(ranking: Mapping) -> dict:
    if not ranking.get("available"):
        return {"available": False, "error": ranking.get("error")}
    f, t = ranking["family"], ranking["threshold"]
    return {"available": True, "n_comparable": ranking["n_comparable"],
            "n_above": ranking["n_above"], "n_groups": ranking["n_groups"],
            "threshold": t.get("value"), "threshold_status": t["status"],
            "family_total": f["total"], "family_scanner": f["scanner"],
            "new_observations": f["new_observations"], "matured_now": f["matured_now"]}
