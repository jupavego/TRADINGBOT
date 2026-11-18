"""Informe de T164 (`transversal_v1`) sobre el almacén de T181.

    python -m eim.analytics.transversal_report --root data/universe_perps --out reports

Primero la puerta de potencia (sin retornos) y, solo si pasa, la medición única de la combinada.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from eim.analytics import transversal as tv


def markdown(out: dict, uni: dict) -> str:
    g = out["gate"]
    lines = ["# T164 — Carry y momentum transversales (`transversal_v1`)", "",
             f"**Modo: ANÁLISIS.** Generado {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
             "con el pre-registro `PLAN/notas/T164_preregistro.md`, congelado antes de esta corrida.", "",
             "## Universo y cobertura", "",
             f"- Perpetuos USDT en `universe.json`: {uni.get('n')} ({uni.get('by_status')}). "
             "Los retirados hace años no están: **sesgo de supervivencia** (T181).", "",
             "## Puerta de potencia (§4, sin retornos)", "",
             f"- Semanas con ≥ {tv.MIN_N} elegibles: {g['weeks']} desde {g['first']}; "
             f"evaluables tras {tv.VOL_WARM} de calentamiento: **{g['years']} años** frente a "
             f"{g['needed_years']} necesarios → **{'PASA' if g['passes'] else 'NO PASA'}**.", ""]
    if not out["measured"]:
        lines += ["**Veredicto: SIN POTENCIA.** No se calculó ningún retorno ni se gastó el intento."]
        return "\n".join(lines) + "\n"
    s = out["stats"]
    lines += ["## Medición única (combinada, m = 1, z = 1,645)", "",
              f"- Semanas medidas: {out['weeks']} ({out['first']} → {out['last']}).",
              f"- **t de Newey-West = {out['t_nw']:.2f}** (p unilateral {out['p_one_sided']:.4f}) → "
              f"**{out['verdict']}**.",
              f"- Beta semanal frente a BTC: {out['beta_btc']:+.3f}"
              + (" (neutral)" if out["beta_btc"] is not None and abs(out["beta_btc"]) < 0.3
                 else " (**no** neutral)") + f" · correlación carry–momentum {out['rho_cm']:+.2f}.",
              "", "| Cartera | Semanas | Media semanal | Sharpe anual |", "|---|---|---|---|"]
    lines += [f"| {k} | {v['weeks']} | {v['mean_weekly'] * 100:+.3f} % | {v['sharpe']:+.2f} |"
              for k, v in s.items()]
    lines += ["", "Carry y momentum se informan; **solo la combinada se juzga** (◆ del usuario).",
              "La combinada está en unidades de volatilidad (escala de 26 semanas): su media no es un "
              "retorno en %, su Sharpe sí se compara."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eim.analytics.transversal_report", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="data/universe_perps")
    ap.add_argument("--out", default="reports")
    a = ap.parse_args(argv)
    panel, uni = tv.load(a.root)
    out = tv.run(panel)
    dst = Path(a.out)
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "t164_transversal.json").write_text(json.dumps(out, ensure_ascii=False, indent=1,
                                                          default=str), encoding="utf-8")
    md = markdown(out, uni)
    (dst / "t164_transversal.md").write_text(md, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
