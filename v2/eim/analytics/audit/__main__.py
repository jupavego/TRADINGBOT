"""Consola de la auditoría periódica (T159). Ver `eim/analytics/audit/__init__.py`."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.analytics.audit import render, sources
from eim.analytics.audit.build import build


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eim.analytics.audit",
                                 description="Auditoría de rentabilidad y calibración (SIMULADO).")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--data-dir", default="data", type=Path)
    ap.add_argument("--out", default="reports/audit", type=Path)
    ap.add_argument("--ledger", type=Path, help="libro en CSV en vez de la API (sin variantes)")
    ap.add_argument("--sin-red", action="store_true", help="no consultar el funding público")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    now_ms = int(time.time() * 1000)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = stamp[:10]
    variant_rows: dict[str, list[dict]] = {}
    try:
        if a.ledger:
            rows = sources.read_csv(a.ledger)
        else:
            rows = sources.fetch_csv(a.api, "/v2/paper/ledger.csv")
            for name in sources.variants(a.api):
                variant_rows[name] = sources.fetch_csv(a.api, f"/v2/paper/variant/{name}/ledger.csv")
    except Exception as e:                  # noqa: BLE001 — se informa y se sale con código 2
        print(f"ERROR: no se pudo leer el libro ({e}). ¿API en marcha en {a.api}?")
        return 2
    funding = ({s: None for s in ("BTCUSDT", "ETHUSDT")} if a.sin_red
               else sources.funding_apr(("BTCUSDT", "ETHUSDT"), now_ms))
    a.out.mkdir(parents=True, exist_ok=True)
    audit = build(rows, now_ms, stamp, variant_rows=variant_rows, funding=funding,
                  hft=sources.hft_quality(a.data_dir),
                  calibration={} if a.ledger else sources.calibration(a.api),
                  prev=sources.previous(a.out, today))
    base = a.out / f"audit_{today}"
    audit["paths"] = {"json": str(base.with_suffix(".json")), "md": str(base.with_suffix(".md"))}
    base.with_suffix(".json").write_text(json.dumps(audit, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    base.with_suffix(".md").write_text(render.markdown(audit), encoding="utf-8")
    print(render.console(audit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
