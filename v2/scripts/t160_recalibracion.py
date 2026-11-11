"""T160 — recalibración de las probabilidades de escenario, tal como se pre-registró.

Pre-registro: `PLAN/notas/T160_preregistro.md` (commit anterior a este script). Banco de T131
(BTCUSDT 1 h) con pronósticos walk-forward cada 4 velas; en vivo, los pronósticos persistidos de una
copia de `reports.duckdb` con el modelo ajustado sobre el banco completo y congelado.

Uso (por la cola; 1 proceso):
    python scripts/t160_recalibracion.py --banco backups/t131_banco \
        --live-reports backups/<copia>/reports.duckdb --live-data data
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eim.core import ForecastSet  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.forecast import recal, recal_eval  # noqa: E402
from eim.forecast.backfill import backfill  # noqa: E402
from eim.forecast.base_engine import BaseEngine  # noqa: E402
from eim.forecast.calibration import evaluate_forecast  # noqa: E402

HORIZON, STEP, STRIDE_NO_OVERLAP = 25, 4, 7      # 7 orígenes × 4 velas = 28 ≥ 25


def to_obs(fs: ForecastSet, closes: dict[int, float]) -> recal.Obs | None:
    o = evaluate_forecast(fs, closes)
    if o is None:
        return None
    end_t = [t for t, _ in next(s for s in fs.scenarios if s.id == "neutral").path][-1]
    return recal.Obs(made_at=fs.made_at, end_t=end_t, probs=o.probs, realized=o.realized)


def bank_obs(root: Path) -> list[recal.Obs]:
    candles = Store(root).read_candles("BTCUSDT", "1h")
    closes = {c.t: c.c for c in candles}
    out = []
    for fs in backfill(BaseEngine(), candles, symbol="BTCUSDT", timeframe="1h",
                       horizon=HORIZON, stride=STEP):
        if (o := to_obs(fs, closes)) is not None:
            out.append(o)
    return out


def live_obs(reports: Path, data: Path) -> tuple[list[recal.Obs], list[bool]]:
    from eim.api.forecast_db import ForecastStore
    from eim.api.reports_db import ReportStore

    with tempfile.TemporaryDirectory() as tmp:          # nunca se abre la copia original
        cp = Path(tmp) / "reports.duckdb"
        shutil.copy2(reports, cp)
        rs = ReportStore(cp)
        fcs = ForecastStore(*rs.connection).horizon_all("BTCUSDT", "1h", HORIZON)
        rs.connection[0].close()
    closes = {c.t: c.c for c in Store(data).read_candles("BTCUSDT", "1h")}
    obs, is_backfill = [], []
    for fs in fcs:
        if (o := to_obs(fs, closes)) is not None:
            obs.append(o)
            is_backfill.append(any("backfill" in w for w in fs.warnings))
    return obs, is_backfill


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", type=Path, default=Path("backups/t131_banco"))
    ap.add_argument("--live-reports", type=Path, required=True)
    ap.add_argument("--live-data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=Path("reports/t160_recalibracion.json"))
    a = ap.parse_args()

    bank = bank_obs(a.banco)
    res: dict = {"preregistro": "PLAN/notas/T160_preregistro.md", "horizon": HORIZON,
                 "bank": {"n_obs": len(bank), "first": bank[0].made_at, "last": bank[-1].made_at},
                 "methods": {}}
    for name, fit in recal.METHODS.items():
        ev = recal.walk_forward(bank, fit)
        res["methods"][name] = {"bank": recal_eval.score(ev, STRIDE_NO_OVERLAP)}
    pv = {k: v["bank"]["test"]["p"] for k, v in res["methods"].items()}
    res["holm"] = recal_eval.holm(pv)

    live, bf = live_obs(a.live_reports, a.live_data)
    res["live"] = {"n_obs": len(live), "n_backfill": sum(bf), "source": str(a.live_reports)}
    # «Fuera de muestra puro» (pre-registro §3): el modelo congelado solo ve resultados del banco
    # cuyo horizonte terminó antes del primer pronóstico en vivo.
    t_live = min((o.made_at for o in live), default=2 ** 62)
    frozen = [o for o in bank if o.end_t < t_live]
    res["live"]["fit_n"] = len(frozen)
    for name, fit in recal.METHODS.items():
        model = fit(frozen)
        ev = [(o, model(o.probs)) for o in live]
        evl = [(o, model(o.probs)) for o, b in zip(live, bf, strict=True) if not b]
        m = res["methods"][name]
        m["live"] = recal_eval.score(ev, 1)              # la media manda; la prueba no decide
        m["live_only_vivo"] = recal_eval.score(evl, 1) if evl else {"n": 0}
        b = m["bank"]
        m["criteria"] = {
            "a_holm_banco": res["holm"][name],
            "b_vivo_media_d_pos": (m["live"]["d_mean_all"] or 0) > 0,
            "c_ece_banco_no_empeora": b["ece_recal"] <= b["ece_raw"],
        }
        m["passes"] = all(m["criteria"].values())
    passing = [k for k, v in res["methods"].items() if v["passes"]]
    res["adopted"] = (max(passing, key=lambda k: res["methods"][k]["bank"]["test"]["mean"])
                      if passing else None)
    a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: {"bank_d": v["bank"]["test"]["mean"], "p": v["bank"]["test"]["p"],
                          "live_d": v["live"]["d_mean_all"], "criteria": v["criteria"]}
                      for k, v in res["methods"].items()}, ensure_ascii=False, indent=1))
    print("ADOPTADO:", res["adopted"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
