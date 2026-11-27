"""T214 — estado de la muestra hacia adelante y potencia a priori (no evalúa nada).

    python scripts/t214_superficie.py --data data [--out reports/t214_superficie.json]

Lee las tomas de BTC de T213 (`data/options/BTC`), calcula los rasgos de cada una con
`eim/options/surface.py` y cuenta los **días válidos** según el pre-registro
(`PLAN/notas/T214_preregistro.md` §2-§3: toma con calidad `ok` en [22:00, 24:00) UTC del día
anterior). Con eso proyecta la fecha de la revisión de potencia (250 días válidos) y deja la tabla
de potencia a priori. No calcula ninguna pérdida ni ningún pronóstico: eso solo se hace en la
revisión y en la evaluación que fija el pre-registro.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eim.data.options_chain import read_rows  # noqa: E402
from eim.options import surface_power as sp  # noqa: E402
from eim.options.surface import SURFACE_VERSION, surface_features  # noqa: E402


def _taken(path: Path) -> int | None:
    q = path.with_name(path.name.replace(".jsonl.gz", ".quality.json"))
    try:
        return int(json.loads(q.read_text(encoding="utf-8"))["taken_ms"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def coverage(data_dir: Path) -> dict:
    """Tomas, su calidad y los días válidos para la evaluación."""
    root = data_dir / "options" / "BTC"
    files = sorted(root.glob("*/*.jsonl.gz")) if root.exists() else []
    by_status: dict[str, int] = {}
    per_day: dict[str, str] = {}                 # día d → estado de su toma de las 22-24 h de d−1
    last: dict | None = None
    for f in files:
        taken = _taken(f)
        if taken is None:
            by_status["ilegible"] = by_status.get("ilegible", 0) + 1
            continue
        feats = surface_features(read_rows(f), taken)
        by_status[feats.status] = by_status.get(feats.status, 0) + 1
        t = datetime.fromtimestamp(taken / 1000, UTC)
        if t.hour >= 22:
            day = (t.date() + timedelta(days=1)).isoformat()
            if per_day.get(day) != "ok":         # la última válida de la ventana basta
                per_day[day] = feats.status
        last = {"taken_at": t.strftime("%Y-%m-%dT%H:%MZ"), **feats.metrics()}
    valid = sorted(d for d, s in per_day.items() if s == "ok")
    first = date.fromisoformat(valid[0]) if valid else sp.START
    span = max(1, (date.today() - sp.START).days)
    rate = len(valid) / span if valid else 0.0
    review = (sp.START + timedelta(days=int(sp.WARMUP_DAYS / rate)) if rate > 0 else None)
    return {"snapshots": len(files), "by_status": by_status, "valid_days": len(valid),
            "first_valid_day": first.isoformat() if valid else None,
            "candidate_days": len(per_day), "valid_rate": round(rate, 4),
            "power_review_estimate": max(review, sp.START + timedelta(days=sp.WARMUP_DAYS))
            .isoformat() if review else None, "last_snapshot": last}


def power() -> dict:
    fam = sp.FAMILY_T95 + sp.N_ATTEMPTS
    n = sp.days_needed(sp.S_CENTRAL, sp.delta_min(), fam)
    first = sp.first_evaluation(n)
    return {"delta": round(sp.delta_min(), 5), "delta_rel": sp.DELTA_REL,
            "a2_qlike_t165": sp.A2_QLIKE_T165, "family": fam, "z": round(sp.z_holm(fam), 4),
            "warmup_days": sp.WARMUP_DAYS, "cap": sp.CAP.isoformat(),
            "central": {"s": sp.S_CENTRAL, "days_scored": round(n),
                        "first_evaluation": first.isoformat() if first else None},
            "max_s_for_cap": round(sp.max_s_for_cap(sp.delta_min(), fam), 4),
            "table": [c.to_json() for c in sp.power_table()]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = {"generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "surface_version": SURFACE_VERSION, "preregistro": "PLAN/notas/T214_preregistro.md",
           "coverage": coverage(a.data), "power": power()}
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
