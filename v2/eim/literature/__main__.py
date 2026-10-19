"""CLI de T54 (desde `v2/`; con la API detenida: DuckDB admite un solo proceso escritor).

    python -m eim.literature ctx    [--symbol BTCUSDT] [--tf 1h --tf 4h] [--data data]
    python -m eim.literature report [--symbol BTCUSDT] [--data data] [--out reports/literature]
                                    [--max-origins N] [--no-tilt]

`ctx` completa los contextos guardados con `lit` (aciertos del agente `literature`) sin regenerar
los agentes. `report` calcula, con la puerta T49 y los criterios sin tocar, lo observado por regla,
evalúa el ajuste de escenarios (apagado) y escribe `reports/literature/lit_v1_<fecha>.md` + `.json`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from eim.data.timeframes import SYMBOLS

PREREG = "PLAN/notas/T54_preregistro.md"
CTX_TFS = ("1h", "4h")


def _stores(data: str):
    from eim.data.paper_store import PaperStore
    from eim.data.store import Store

    return Store(data), PaperStore(Path(data) / "paper.duckdb")


def _ctx(a: argparse.Namespace) -> int:
    from eim.literature.ctx import complete

    store, ps = _stores(a.data)
    try:
        for tf in a.tf or CTX_TFS:
            r = complete(store, ps, a.symbol, tf, lambda n, tot, tf=tf: (
                print(f"{tf}: {n}/{tot}", flush=True) if n % 1000 == 0 else None))
            print(r)
    finally:
        ps.close()
    return 0


def _claims() -> dict[str, dict]:
    from eim.data.library import load_cards
    from eim.paper.strategies_lit import CITE

    cards = {c.id: c for c in load_cards()}
    out = {}
    for cid, cite in CITE.items():           # solo las 7 fichas preregistradas
        c = cards.get(cid)
        if c is None or c.status != "codificada":
            continue
        d = c.expected_effect.direction if c.expected_effect else "—"
        claim = c.claim if len(c.claim) <= 260 else c.claim[:257] + "…"
        out[cid] = {"cite": cite, "claim": f"({d}) {claim}",
                    "evidence": c.author_evidence or "—"}
    return out


def _commit() -> str:
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%h", "--", f"../{PREREG}"],  # noqa: S603,S607
                           capture_output=True, text=True, timeout=10, check=False)
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _notes(ps, symbol: str, tilt_on: bool) -> list[str]:
    notes = []
    for tf in CTX_TFS:
        ctxs = ps.load(symbol, tf)
        with_lit = sum(1 for c in ctxs if c.get("lit"))
        notes.append(f"Contextos {tf}: {len(ctxs)}, con aciertos de `literature` (`lit`): "
                     f"{with_lit}" + ("" if with_lit == len(ctxs) else
                                      " — completar con `python -m eim.literature ctx`") + ".")
    notes += [
        "En 1 h el agente evalúa 500 velas y la regla de 4 semanas necesita 673: solo corre en 4 h "
        "(preregistro).",
        "Los agentes no entran en la huella de versión (BACKLOG T49 (4)): `lit` se declara con "
        "`CTX_VERSION` 2; las estrategias de la familia se versionan por su código.",
        "Las 9 versiones nuevas elevan los intentos de Holm de la puerta (costo declarado en el "
        "preregistro).",
        "Los pares espejo (martillo/estrella fugaz, estrellas de la mañana/vespertina) comparten "
        "versión: la tabla por ficha es descriptiva, no un intento adicional de la puerta."]
    if tilt_on:
        notes.append("El ajuste se mide sobre el motor base (como T19), sin la deriva de la "
                     "síntesis que lleva el pronóstico en vivo.")
    return notes


def _report(a: argparse.Namespace) -> int:
    from eim.data.validation_store import ValidationStore
    from eim.forecast.lit_tilt import load_config
    from eim.literature import report, tilt_eval
    from eim.paper.desk import PaperDesk
    from eim.paper.generate import now_ms
    from eim.validation.service import Validator

    store, ps = _stores(a.data)
    try:
        desk = PaperDesk(store, ps)
        val = Validator(desk, ValidationStore(ps))
        payload = val.compute(a.symbol)
        view, now = desk.view(a.symbol), now_ms()
        by_card = report.trades_by_card(view.outcomes, val.current_versions(now),
                                        val.vstore.versions(), a.symbol, payload["asof"] or now)
        tilt: dict = {}
        if not a.no_tilt:
            cfg = load_config()
            candles = store.read_candles(a.symbol, cfg.sample.timeframe)
            if candles:
                print(f"ajuste de escenarios: {len(candles)} velas…", flush=True)
                rows = tilt_eval.run_backfill(candles, cfg, a.symbol, a.max_origins)
                tilt = tilt_eval.evaluate_tilt(rows, cfg)
        meta = {"date": datetime.now(UTC).strftime("%Y-%m-%d"), "symbol": a.symbol,
                "asof": payload["asof"], "prereg_commit": a.commit or _commit(),
                "notes": _notes(ps, a.symbol, bool(tilt))}
        res = report.build(payload, by_card, _claims(), tilt, meta)
        md, js = report.write(res, Path(a.out))
    finally:
        ps.close()
    print("\n".join(res["conclusion"]))
    print(f"informe: {md}\ndatos:   {js}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eim.literature")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("ctx", "report"):
        sp = sub.add_parser(name)
        sp.add_argument("--symbol", default="BTCUSDT", choices=SYMBOLS)
        sp.add_argument("--data", default="data")
        if name == "ctx":
            sp.add_argument("--tf", action="append", choices=CTX_TFS)
        else:
            sp.add_argument("--out", default="reports/literature")
            sp.add_argument("--max-origins", type=int, default=None)
            sp.add_argument("--no-tilt", action="store_true")
            sp.add_argument("--commit", default="", help="commit del preregistro")
    a = ap.parse_args(argv)
    return _ctx(a) if a.cmd == "ctx" else _report(a)


if __name__ == "__main__":
    sys.exit(main())
