"""T170: construye el pre-registro `cantera_v1` (SIMULADO). Dos pasos, sin mirar rendimiento.

    python scripts/t170_prereg.py calibrate   # por la cola: topes de drawdown, promesas falsas
    python scripts/t170_prereg.py build       # escribe prereg/prereg_cantera_v1.json

La familia sale de los exámenes físicos (T169 y el de los reemplazos de T177) y de las ◆; los
topes de drawdown y las promesas falsas esperadas, de `nursery/calibrate.py` con semilla fija. El
archivo, una vez publicado, no se edita: su SHA-256 queda en `nursery/prereg.py::PUBLISHED`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eim.nursery import calibrate  # noqa: E402
from eim.nursery.ladder_rules import LadderRules  # noqa: E402
from eim.nursery.params import V6_MAX_COST_R, NurseryParams  # noqa: E402
from eim.nursery.prospect import load_prospects  # noqa: E402
from eim.nursery.signals import accounts_for  # noqa: E402
from eim.validation.criteria import PUBLISHED as CRITERIA  # noqa: E402

T169 = ROOT / "reports" / "t169_examen_fisico.json"
CALIB = ROOT / "reports" / "t170_calibracion.json"
OUT = ROOT / "eim" / "validation" / "prereg" / "prereg_cantera_v1.json"
# ◆ 2026-11-16: el usuario eligió las versiones de T177 (`estructura_ruptura_sc02`,
# `tec_acuerdo_tres_marcos`) frente a los rediseños en su sitio de T170, que se revirtieron;
# `reports/t170_reexamen.*` queda solo como registro. No hay rediseños en su sitio.
REDESIGNED: tuple[str, ...] = ()
RESERVE, CEILING = 7, 50      # la reserva puede bajar (--reserve) si entran más reemplazos
THEME = {
    "tendencia": ("niveles_ruptura", "pa_bos", "pa_bos_patron", "estructura_continuacion",
                  "estructura_retroceso", "estructura_ruptura", "tec_ruptura_volumen",
                  "tec_acuerdo_marcos", "vwap_tendencia", "vwap_semanal", "micro_ofi"),
    "reversion": ("ema_elastico", "niveles_rebote", "niveles_canal_extremos", "pa_choch",
                  "pa_patron_zona", "lit_nison_giro", "lit_murphy_rsi", "micro_absorcion"),
    "derivados": ("deriv_funding_contrario", "deriv_oi_tendencia", "deriv_saturacion",
                  "deriv_largos_cortos", "liq_agotamiento", "liq_cascada",
                  "liq_cascada_multibolsa"),
    "consenso": ("lit_consenso", "bots_mayoria", "bots_unanimidad"),
}
LADDER = {
    "reviews_days": [30, 61, 91, 121, 152, 182],
    "nursery_exit": {"min_trades": 30, "max_days": 60},
    "clearly_negative": {"z": 1.0, "min_trades": 30},
    "primary": {"clip_r": 3.0, "lambdas": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
                "day_unit_bands": ["semanal"]},
    "promise": {"q": 0.10, "max_trade_share": 0.40, "sibling_alpha": 0.10,
                "sibling_min_trades": 30, "marginal_corr": 0.70, "marginal_min_days": 10},
    "futility": {"mu_min_r": 0.10, "beta": 0.10, "min_trades": 30},
    "drawdown": {"target_edge_r": 0.25, "sigma_r": 1.3, "p_unfair": 0.05, "risk_pct": 0.01,
                 "n_without_history": 1000, "sims": 100_000, "seed": 170, "caps_pct": {}},
    "inactivity": {"days": 60, "gate_closed_counts": False},
    "forward_exam": {"min_ops_month": {"scalping": 20.0, "intradia": 8.0, "tres_dias": 5.0},
                     "min_pos_days_frac": 0.30, "max_cost_r": V6_MAX_COST_R,
                     "min_closed_for_band": 10, "band_max_hours": [2.0, 24.0, 120.0]},
    "first_team": {"stepm_size": 0.05, "stepm_reps": 10_000, "stepm_seed": 170,
                   "dsr_min": 0.95, "neff_corr": 0.70, "regimes_min": 2,
                   "regime_min_trades": 20, "persistence_min_trades": 10, "min_trades": 100,
                   "min_pos_days": 120, "max_dd": 0.25, "window_days": 30,
                   "window_min_trades": 5, "min_windows": 4, "min_positive_frac": 0.60,
                   "max_cost_r": V6_MAX_COST_R},
}


def _say(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())} UTC] {msg}", flush=True)


def family(exams: tuple[Path, ...] = (), themes: Path | None = None) -> dict:
    """Quién entra y quién no, con su huella, banda, tema, hermano y control.

    `exams`: informes de examen físico adicionales con el formato del de T169 (p. ej., los
    prospectos nuevos de T177 que reemplazan descartados); `themes`: JSON {id: tema} para ellos.
    """
    t169 = json.loads(T169.read_text(encoding="utf-8"))
    original = {r["id"] for r in t169["prospects"]} | {
        r["id"] if isinstance(r, dict) else r for r in t169["without_history"]}
    rows = {r["id"]: r for r in t169["prospects"]}
    for f in exams:
        rows.update({r["id"]: r for r in json.loads(Path(f).read_text(encoding="utf-8"))
                     ["prospects"]})
    theme = {pid: th for th, ids in THEME.items() for pid in ids}
    if themes is not None:      # «reversión» con tilde (T177) es el tema `reversion`
        theme.update({k: v.replace("ó", "o") for k, v in
                      json.loads(Path(themes).read_text(encoding="utf-8")).items()})
    ps = load_prospects()
    by = {p.id: p for p in ps}
    generic = {(a.agent_id, a.timeframe): a.id for a in accounts_for(ps) if a.kind == "control"}
    members, discarded = [], []
    for p in ps:
        r = rows.get(p.id)
        if r is not None and r["verdict"]["discarded"]:
            why = "; ".join(r["verdict"]["reasons"])
            if p.id.startswith("regimen_tramo"):
                why += (". Gemelo físico de " + ("regimen_tramo_estable" if p.id ==
                        "regimen_tramo" else "regimen_tramo") + " (◆ 2026-11-16: cuentan como "
                        "dos prospectos)")
            if p.id.startswith("elliott_"):
                why += (". Imposible por cómo emite el agente (`agents/elliott/compute.py:66` "
                        "etiqueta los pivotes por posición: el último es siempre C); arreglarlo "
                        "exige una versión nueva del agente (BACKLOG; ◆ 2026-11-16: baja)")
            discarded.append({"id": p.id, "fingerprint": p.fingerprint,
                              "stage": "examen_fisico_t169", "reason": why})
            continue
        base = next((q for q in ps if q.agent_id == p.agent_id and q.role == "base"), None)
        sib = base.id if (base and base.id != p.id and len(p.params) > len(base.params)
                          and (rows.get(base.id) is None or
                               not rows[base.id]["verdict"]["discarded"])) else None
        if p.id not in theme:
            raise SystemExit(f"{p.id}: falta su tema (tendencia, reversion, derivados o "
                             "consenso); pásalo con --themes")
        src = "declarada" if r is None else ("medida_t169" if p.id in original and
                                             p.id not in REDESIGNED else "medida_t177")
        members.append({
            "id": p.id, "fingerprint": p.fingerprint, "agent_id": p.agent_id,
            "timeframe": p.timeframe, "role": p.role, "n_params": len(p.params),
            "band": p.horizon if r is None else r["verdict"]["band"], "band_source": src,
            "history": r is not None, "theme": theme[p.id], "sibling": sib,
            "generic": generic[(p.agent_id, p.timeframe)],
            "expected_in_term": None if r is None else
            int(round(r["verdict"]["expected_in_term"]))})
    assert len(members) + len(discarded) == len(by)
    return {"members": members, "discarded": discarded,
            "replacements": [x["id"] for x in members if x["id"] not in original],
            "enrolled_t167": len(original)}


def rules_without_caps(n_members: int) -> LadderRules:
    lad = json.loads(json.dumps(LADDER))
    lad["drawdown"]["caps_pct"] = {f"p{i}": 1.0 for i in range(n_members)}
    return LadderRules(**lad)


def _fam(a: argparse.Namespace) -> dict:
    return family(tuple(Path(x) for x in a.exam), Path(a.themes) if a.themes else None)


def cmd_calibrate(a: argparse.Namespace) -> None:
    fam = _fam(a)
    ms = fam["members"]
    dd = LADDER["drawdown"]
    n_term = {x["id"]: x["expected_in_term"] or dd["n_without_history"] for x in ms}
    rules = rules_without_caps(len(ms))
    t0 = time.time()
    caps = calibrate.caps_for(n_term, rules, a.dd_sims)
    _say(f"topes de drawdown: {len(caps)} en {time.time() - t0:.0f} s")
    t0 = time.time()
    fp = calibrate.false_promises(n_term, rules, len(ms) + a.reserve, a.null_sims, seed=1701)
    _say(f"promesas falsas: {fp} en {time.time() - t0:.0f} s")
    pw = calibrate.power(rules, len(ms) + a.reserve, a.power_sims, seed=1702)
    _say(f"potencia: {pw['by_mu']}")
    CALIB.write_text(json.dumps({"task": "T170", "mode": "SIMULADO", "n_term": n_term,
                                 "caps_pct": caps, "false_promises": fp, "power": pw,
                                 "dd_sims": a.dd_sims or dd["sims"]}, ensure_ascii=False,
                                indent=1), encoding="utf-8")
    _say(f"calibración en {CALIB}")


def cmd_build(a: argparse.Namespace) -> None:
    from t170_prereg_text import document  # texto fijo del pre-registro (mismo directorio)

    fam = _fam(a)
    cal = json.loads(CALIB.read_text(encoding="utf-8"))
    if set(cal["caps_pct"]) != {x["id"] for x in fam["members"]}:
        raise SystemExit("la calibración es de otra familia: corre `calibrate` con la misma lista")
    lad = json.loads(json.dumps(LADDER))
    lad["drawdown"]["caps_pct"] = {x["id"]: cal["caps_pct"][x["id"]] for x in fam["members"]}
    np_ = NurseryParams()
    doc = document(fam, lad, cal, np_, CRITERIA["validation_v1"], a.reserve, CEILING,
                   REDESIGNED, a.not_before)
    LadderRules(**doc["ladder"])
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _say(f"pre-registro en {OUT}")


def main() -> None:
    ap = argparse.ArgumentParser(description="T170: pre-registro cantera_v1")
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--exam", action="append", default=[],
                        help="informe de examen adicional (formato T169), repetible")
    common.add_argument("--themes", default=None, help="JSON {id: tema} de los nuevos")
    common.add_argument("--reserve", type=int, default=RESERVE)
    s = sub.add_parser("calibrate", parents=[common])
    s.add_argument("--dd-sims", type=int, default=None)
    s.add_argument("--null-sims", type=int, default=10_000)
    s.add_argument("--power-sims", type=int, default=20_000)
    s = sub.add_parser("build", parents=[common])
    s.add_argument("--not-before", required=True, help="UTC, p. ej. 2026-11-16T22:00Z")
    a = ap.parse_args()
    {"calibrate": cmd_calibrate, "build": cmd_build}[a.cmd](a)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
