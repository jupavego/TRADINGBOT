"""Órdenes `deep`, `verify` (T94) y `calibrate` (T95) del escáner. Modo ANÁLISIS: nada de esto
envía órdenes."""

from __future__ import annotations

import json
import sys

from eim.data import scanner_market as market
from eim.instruments.models import Instrument
from eim.scanner.service import ScannerService


def deep_cmd(svc: ScannerService, a) -> int:
    from eim.scanner.deep_service import deep_pass

    out = deep_pass(svc, base_run_id=a.run)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        return 0
    d = out["detail_json"]
    opps = out["opportunities"]
    print(f"pasada {out['run_id']} sobre el barrido {d['base_run']}: {out['n_shortlist']} "
          f"instrumentos, {len(opps)} oportunidades candidatas (no validadas), "
          f"{len(d['failed'])} fallidos")
    for why, n in sorted(d["reasons"].items()):
        print(f"  sin oportunidad: {why} ×{n}")
    for o in sorted(opps, key=lambda o: -o["scores"]["signal_quality"])[:10]:
        s = o["scores"]
        print(f"  {o['opportunity_id']}  {o['symbol']:<14} {o['side']:<5} señal "
              f"{s['signal_quality']:.2f} · viabilidad {s['viability']:.2f} · riesgo/costos "
              f"{s['risk_cost']:.2f} · {len(o['agents'])} agentes · datos {o['input_hash']}")
    ran = [len(r["ran"]) for r in out["results"]]
    skipped = [len(r["skipped"]) for r in out["results"]]
    if ran:
        print(f"  agentes por instrumento: corrieron {min(ran)}–{max(ran)}, omitidos "
              f"{min(skipped)}–{max(skipped)} (con su motivo en la vista)")
    rk = _ranking_line(out.get("ranking") or {})
    print(rk)
    print(f"vista publicada: {svc.data_dir / 'scanner' / 'view.json'}")
    if getattr(a, "summary", None):
        from pathlib import Path

        why = ", ".join(f"{k} ×{n}" for k, n in sorted(d["reasons"].items())) or "—"
        span = f"{min(ran)}–{max(ran)}" if ran else "0"
        Path(a.summary).write_text(
            f"pasada de agentes sobre el barrido {d['base_run']}: {out['n_shortlist']} "
            f"instrumentos de la lista corta, {len(opps)} oportunidades candidatas (no "
            f"validadas), {len(d['failed'])} fallidos; agentes elegibles por instrumento "
            f"{span}; sin oportunidad: {why}; {rk}", encoding="utf-8")
    return 0


def _ranking_line(r: dict) -> str:
    """Una línea con el ranking de T95 (para la consola y el plan)."""
    if not r.get("available"):
        return f"ranking T95: NO disponible ({r.get('error') or r.get('reason') or 'sin datos'})"
    t, f = r["threshold"], r["family"]
    thr = (f"umbral del placebo {t['value']:.3f} ({t['status']}, {t.get('replicas')} réplicas)"
           if t.get("value") is not None else f"umbral del placebo: {t['status']}")
    return (f"ranking T95: {r['n_comparable']} comparables en {r['n_groups']} apuestas "
            f"independientes; {thr}; sobre el umbral: {r['n_above']}; familia de hipótesis "
            f"{f['total']} ({f['prior']} previas de T49 + {f['scanner']} del escáner), "
            f"{f['new_observations']} observaciones nuevas, {f['matured']} maduras en total")


def calibrate_cmd(svc: ScannerService, a) -> int:
    """T95: pesos del ranking fuera de muestra con los resultados maduros de la síntesis."""
    from eim.scanner import rank

    res = rank.calibrate(svc.store.synthesis_matured())
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if res["adopted"] and not a.dry_run:
        w = rank.Weights(res["weights"], True, f"calibrados fuera de muestra ({res['n']} "
                                               "resultados maduros, T95)")
        print(f"pesos adoptados: {rank.save_weights(svc.data_dir, w, res)} — el umbral del "
              "placebo queda desactualizado: repite `python scripts/scanner_placebo.py`")
    return 0


def verify_cmd(svc: ScannerService, a) -> int:
    from eim.scanner.deep import verify

    opp = svc.store.opportunity(a.opportunity_id)
    if opp is None:
        print(f"no hay oportunidad {a.opportunity_id} en scanner.duckdb", file=sys.stderr)
        return 5
    ref = opp["input_ref"]
    cs = market.read_window(svc.root, ref["symbol"], ref["timeframe"], ref["n_bars"], ref["cut"])
    insts, _ = market.read_catalog(svc.data_dir, svc.p.venue)
    inst: Instrument | None = next((i for i in insts if i.id == opp["instrument_id"]), None)
    out = verify(opp, cs, inst=inst)
    ok = out["hash_ok"] and out.get("reproduced", False)
    line = (f"{a.opportunity_id} ({opp['symbol']}, {opp['side']}): hash de datos "
            f"{'igual' if out['hash_ok'] else 'DISTINTO'} ({out['input_hash']}); reproducida: "
            f"{'sí' if ok else 'NO'} ({ref['n_bars']} velas {ref['timeframe']} de {ref['symbol']} "
            f"releídas del almacén del universo)")
    print(line)
    if getattr(a, "summary", None):
        from pathlib import Path

        Path(a.summary).write_text(line, encoding="utf-8")
    return 0 if ok else 4
