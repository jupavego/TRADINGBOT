"""T135 — A/B prospectivo de M8 frente a la escalera, sobre una COPIA y sin tocar el vivo.

    python scripts/t135_ab_m8.py regress --data backups/t131_banco
    python scripts/t135_ab_m8.py freeze --data backups/t135_ab --start 2026-11-08
    python scripts/t135_ab_m8.py report --data backups/t135_ab

`regress` comprueba que este camino reproduce las cifras de T134 y mide la dispersión por día, que
es lo que decide la potencia con ideas agrupadas. `freeze` congela la tabla de M8, el inicio y la
potencia en `eim/paper/exits/versions/t135_ab_m8_v1.json`, y se niega a reescribirlos. `report`
escribe el informe semanal. Por la cola, que es trabajo pesado:

    python -m eim.operation.jobs --data-dir data submit --name t135-ab --min-ram-mb 2500 -- \
        python scripts/t135_ab_m8.py report --data backups/t135_ab
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.paper.desk import PaperDesk
from eim.paper.engine import Path as PricePath
from eim.paper.exits import ab_live, bench, experiment, features, grid, power, winners_mae
from eim.paper.exits import walkforward as wf
from eim.paper.exits.policy import ExitContext
from eim.paper.exits.prereg import load_prereg
from eim.paper.params import LADDER_BY_PROFILE, spec_for

HTF_OF = {"15m": "1h", "1h": "4h", "4h": "4h"}
FROZEN = Path("eim/paper/exits/versions/t135_ab_m8_v1.json")
REGRESS = Path("reports/t135_regress.json")
T134_REPORT = Path("reports/exits_ab.json")
EPS = 1e-9
RATE_WEEKS = 4       # con cuántas semanas recientes se estima el ritmo de ideas en vivo


def _fine(store: Store, sym: str, tf: str) -> PricePath | None:
    if store.bounds(sym, tf) is None:
        return None
    return PricePath.from_arrays(store.read_arrays(sym, tf), tf_ms(tf))


class World:
    """La copia abierta: ideas, caminos, rasgos y contexto, como los monta T134."""

    def __init__(self, data: Path, prereg: str | None = None) -> None:
        self.pr = load_prereg(prereg) if prereg else load_prereg()
        sym = self.pr.symbol
        store, ps = Store(data), PaperStore(data / "paper.duckdb")
        self.desk = PaperDesk(store, ps, profiles=())
        v = self.desk.view(sym)
        if not v.outcomes or v.path is None:
            raise SystemExit("la copia no tiene contextos guardados")
        self.path = v.path
        self.fine = _fine(store, sym, self.pr.design.fine_timeframe)
        htf = _fine(store, sym, HTF_OF.get(self.pr.design.path_timeframe, "1h"))
        self.feats = {n: features.build(v.path, n, swing_bars=5, fine=self.fine, htf=htf)
                      for n in ab_live.SIGMAS}
        tfs = set(self.pr.design.decision_timeframes)
        self.ideas = sorted((o.idea for o in v.outcomes
                             if o.idea.strategy != bench.CONTROL_STRATEGY
                             and o.idea.timeframe in tfs), key=lambda x: (x.t, x.id))
        self.ladder = LADDER_BY_PROFILE["moderado"]
        self.ctx = ExitContext(path=v.path, ep=self.desk.ep, spec=spec_for(sym), fine=self.fine)

    def variants(self, quantile_for=None) -> list[grid.Variant]:
        out, _ = grid.expand(self.pr, self.feats, self.ladder, self.path.t,
                             quantile_for=quantile_for, est_cost_frac=self.desk.ep.est_cost_frac)
        return out

    def bases(self) -> list[grid.Variant]:
        allv = self.variants()
        m0 = next(x for x in allv if x.family == "M0" and x.knobs.get("first_r") == 0.1)
        m1 = next(x for x in allv if x.family == "M1" and x.knobs.get("be_trigger_r") == 1.0
                  and x.knobs.get("be_lock_r") == 0.1)
        return [m0, m1]

    def ratio_of(self):
        """riesgo en precio / σ de cada operación: pasa el MAE de R a σ, como T134."""
        f, t, by_id = self.feats[ab_live.RATIO_SIGMA], self.path.t, {i.id: i for i in self.ideas}

        def of(tr):
            i = by_id.get(tr.id)
            if i is None or not i.entry:
                return None
            j = int(np.searchsorted(t, i.t)) - 1
            if j < 0 or j >= len(f.sigma_abs):
                return None
            s, risk = float(f.sigma_abs[j]), abs(i.entry - i.sl)
            return None if not np.isfinite(s) or s <= 0 or risk <= 0 else risk / s
        return of


def _refuse_live(data: Path) -> None:
    """El almacén vivo se reconoce por su latido, no por la ruta: puede llegar con otra."""
    if data.resolve() == Path("data").resolve() or (data / "operation/heartbeat.json").exists():
        raise SystemExit("no se corre sobre el almacén vivo: usa una copia")


def _mechanics(w: World) -> dict:
    return ab_live.mechanics_of(w.desk.ep, w.ladder, w.pr.design.decision_timeframes)


def _coverage(data: Path, last: int, ideas: int) -> str:
    """Fuente y cobertura reales de la copia. Sin el archivo, se dice: nada se da por cubierto."""
    src = data / "cobertura.json"
    if not src.exists():
        series = "**sin `cobertura.json`: la cobertura no está comprobada**"
    else:
        cov = json.loads(src.read_text(encoding="utf-8"))
        series = "; ".join(
            f"{tf} {v['coverage'] * 100:.2f} %, {v['gaps']} huecos"
            for tf, v in cov["coverage"].items() if v.get("coverage") is not None)
        series = f"{cov.get('provider', 'proveedor sin dato')}: {series}"
    return (f"copia `{data}`, velas hasta {wf.iso(last)}; {series}; {ideas} ideas desde el inicio. "
            f"Commit {_commit()}.")


def _sd_daily(diffs: list[tuple[int, float]]) -> float:
    """Dispersión del ΔR medio por día: con ideas agrupadas, esa es la unidad independiente."""
    days: dict[int, list[float]] = {}
    for d, x in diffs:
        days.setdefault(d, []).append(x)
    return float(np.std([np.mean(v) for v in days.values()], ddof=1))


def regress(a) -> int:
    """Con los pliegues de T134 tienen que salir sus mismas cifras: si no, esto mide otra cosa."""
    data = Path(a.data)
    _refuse_live(data)
    t0 = time.perf_counter()
    w = World(data)
    pr = w.pr
    bases = w.bases()
    b0 = bench.run(w.ideas, [x.policy for x in bases], w.ctx, pr.risk_usd)
    embargo = wf.embargo_for([t for x in bases for t in b0.trades(x.id)],
                             feature_ms=int(pr.design.embargo_feature_hours * 3_600_000),
                             q=pr.design.embargo_quantile)
    lo, hi = wf.from_iso(pr.design.start), wf.from_iso(pr.design.end)
    if b0.rows:
        lo, hi = max(lo, b0.rows[0].t), min(hi, b0.rows[-1].t)
    fs = wf.folds(lo, hi, embargo, pr.design.fit_months, pr.design.test_months,
                  pr.design.step_months)
    ref = next(x for x in bases if x.family == "M1")
    by_fold = winners_mae.build(b0.trades(ref.id, paired_only=False), fs, w.ratio_of(),
                                reference=ref.id, quantile=ab_live.QUANTILE,
                                min_trades=pr.winners_mae.min_trades)
    del b0
    qof = by_fold.quantile_of()
    vs = w.variants(lambda q: qof if q == ab_live.QUANTILE else None)
    _, cand = ab_live.pick(vs)
    tot = experiment.run_batch(w.ideas, bases, [cand], w.ctx, pr, fs,
                               np.random.default_rng(pr.seed))
    got = {"expectancy_m8": tot[ab_live.CANDIDATE].test["expectancy_r"],
           "expectancy_m0": tot[ab_live.BASE].test["expectancy_r"],
           "n_m8": tot[ab_live.CANDIDATE].test["n"]}
    want_all = json.loads(T134_REPORT.read_text(encoding="utf-8"))
    want = {"expectancy_m8": want_all["metrics"][ab_live.CANDIDATE]["test"]["expectancy_r"],
            "expectancy_m0": want_all["metrics"][ab_live.BASE]["test"]["expectancy_r"],
            "n_m8": want_all["metrics"][ab_live.CANDIDATE]["test"]["n"]}
    diffs = tot[ab_live.CANDIDATE].diffs[ab_live.BASE]
    ok = all(abs(got[k] - want[k]) <= EPS for k in want)
    res = {"ok": ok, "got": got, "want": want, "folds": len(fs), "embargo_ms": embargo,
           "sd_paired": float(np.std([x for _, x in diffs], ddof=1)),
           "sd_daily": _sd_daily(diffs), "days": len({d for d, _ in diffs}),
           "delta": got["expectancy_m8"] - got["expectancy_m0"],
           "seconds": round(time.perf_counter() - t0, 1)}
    REGRESS.parent.mkdir(parents=True, exist_ok=True)
    REGRESS.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1, sort_keys=True), flush=True)
    return 0 if ok else 1


def _commit() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,  # noqa: S607
                          text=True, check=False).stdout.strip()


def _freeze(a) -> int:
    data = Path(a.data)
    _refuse_live(data)
    reg = json.loads(REGRESS.read_text(encoding="utf-8"))
    if not reg["ok"]:
        raise SystemExit("la regresión contra T134 no cuadra: no se congela nada")
    start = wf.from_iso(a.start)
    now = int(time.time() * 1000)
    if start <= now:
        raise SystemExit(f"el inicio ({a.start}) tiene que ser futuro: es un pre-registro")
    w = World(data)
    pr = w.pr
    bases = w.bases()
    ref = next(x for x in bases if x.family == "M1")
    last = int(w.path.t[-1])
    cutoff = min(last, now)
    fit_from = wf.add_months(cutoff, -pr.design.fit_months)
    ideas = [i for i in w.ideas if i.t >= fit_from]
    b = bench.run(ideas, [ref.policy], w.ctx, pr.risk_usd)
    trades = b.trades(ref.id, paired_only=False)
    embargo = wf.embargo_for(trades, feature_ms=int(pr.design.embargo_feature_hours * 3_600_000),
                             q=pr.design.embargo_quantile)
    table = ab_live.fit_table(trades, w.ratio_of(), cutoff, embargo, pr)
    # Las que cierran, no todas las ideas: las límite que no se llenan nunca se emparejan.
    recent = [t for t in trades if t.t >= cutoff - RATE_WEEKS * ab_live.WEEK_MS]
    rate = len(recent) / RATE_WEEKS
    src = f"{T134_REPORT} · σ emparejada de T134 y cierres de las últimas {RATE_WEEKS} semanas"
    commit = _commit()
    if not commit:
        raise SystemExit("sin commit no se congela: no se sabría con qué código se fijó")
    plan = power.power_plan(ab_live.CANDIDATE, ab_live.BASE, reg["sd_paired"], reg["delta"], rate,
                            source=src)
    frozen = ab_live.freeze(table, start=start, cutoff=cutoff, plan=plan,
                            sd_daily=reg["sd_daily"],
                            t134={"delta": reg["delta"], "n": reg["got"]["n_m8"],
                                  "expectancy_candidate": reg["got"]["expectancy_m8"],
                                  "report": str(T134_REPORT)},
                            pr=pr, commit=commit, mechanics=_mechanics(w),
                            data_note="copia reconstruida con scripts/t131_history.py")
    path = ab_live.save_frozen(frozen, a.out)
    print(json.dumps({k: frozen[k] for k in ("start_iso", "fit_cutoff_iso", "required_n",
                                             "required_days", "sd_daily_r", "fingerprint")},
                     indent=1), flush=True)
    print(f"tabla: {len(frozen['table']['sids'])} estrategia@marco; {table.n_fit} operaciones de "
          f"ajuste, {table.n_winners} ganadoras. Ritmo {rate:.0f} cierres/semana. "
          f"Guardado en {path}")
    return 0


def report(a) -> int:
    data = Path(a.data)
    _refuse_live(data)
    frozen = ab_live.load_frozen(a.frozen)
    w = World(data, frozen["prereg"])
    ideas = ab_live.counted_ideas(w.ideas, frozen)
    of = ab_live.quantile_of(frozen)
    base, cand = ab_live.pick(w.variants(lambda q: of if q == ab_live.QUANTILE else None))
    b = bench.run(ideas, [base.policy, cand.policy], w.ctx, w.pr.risk_usd)
    last = int(w.path.t[-1])
    ev = ab_live.evaluate(b, frozen, last, _mechanics(w))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    v = ab_live.settled(ab_live.verdict(ev, frozen), ev, out / "veredicto.json")
    md = ab_live.render(ev, frozen, _coverage(data, last, len(ideas)), v)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    (out / f"semana_{stamp}.md").write_text(md, encoding="utf-8")
    (out / f"semana_{stamp}.json").write_text(
        json.dumps({"evaluation": ev, "verdict": v, "frozen": frozen["fingerprint"]},
                   indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(md, flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("regress", help="reproducir T134 y medir la dispersión por día")
    r.add_argument("--data", required=True)
    f = sub.add_parser("freeze", help="congelar tabla, inicio y potencia")
    f.add_argument("--data", required=True)
    f.add_argument("--start", required=True, help="primera fecha que cuenta, futura (ISO UTC)")
    f.add_argument("--out", default=str(FROZEN))
    p = sub.add_parser("report", help="informe semanal")
    p.add_argument("--data", required=True)
    p.add_argument("--frozen", default=str(FROZEN))
    p.add_argument("--out", default="reports/t135_ab")
    a = ap.parse_args()
    return {"regress": regress, "freeze": _freeze, "report": report}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
