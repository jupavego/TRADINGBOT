"""Calcula y guarda la potencia de un A/B en papel, antes de la primera operación (T135, E9).

    python scripts/t135_potencia.py --candidate "M2 k=3 activate_r=1" --base "M0 first_r=0.1" \
        --effect 0.05 --trades-per-week 40 --out reports/t135_potencia_m2.json

σ sale de `reports/exits_ab.json`, el informe de T134. El efecto y el ritmo se piden a mano a
propósito: el efecto es el que T134 estimó para ESA salida y el ritmo tiene que ser el del libro en
vivo, no el del banco. Hoy no hay salida aprobada, así que no hay ningún plan confirmado.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eim.paper.exits.power import inputs_from_report, power_plan, write_plan


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", default="reports/exits_ab.json")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--effect", type=float, required=True, help="efecto a detectar, en R")
    ap.add_argument("--trades-per-week", type=float, required=True,
                    help="ritmo real del libro en vivo, no el del banco")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    report = json.loads(Path(a.report).read_text(encoding="utf-8"))
    sd = inputs_from_report(report, a.candidate, a.base)
    plan = power_plan(a.candidate, a.base, sd, a.effect, a.trades_per_week,
                      source=f"{a.report} · σ de {a.candidate} frente a {a.base}")
    path = write_plan(plan, a.out)
    print(f"{plan['required_n']} operaciones emparejadas · {plan['weeks']} semanas · "
          f"huella {plan['fingerprint'][:12]} · {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
