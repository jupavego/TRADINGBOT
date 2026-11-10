"""T143, entregable 5: antes y después sobre las mismas operaciones vividas.

    python scripts/t143_antes_despues.py --ledger <ledger.csv> [--out reports/t143_antes_despues]

`ledger.csv` es `GET /v2/paper/ledger.csv` de la API viva (solo lectura). Escribe `.json` y `.md`.
El método y lo que no cubre están en `eim/paper/cost_whatif.py`.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from eim.paper.cost_whatif import LABELS, STEPS, compare, shadow


def _n(x, fmt: str = "{:+.3f}") -> str:
    return "—" if x is None else fmt.format(x)


def render(res: dict) -> str:
    st = res["steps"]
    a, z = st["antes"], st["sin_15m_maker_riesgo"]
    out = ["# T143 — Antes y después, sobre las mismas operaciones vividas (entregable 5)", "",
           f"**Modo: SIMULADO.** Libro vivo leído {res['generado']} (`GET /v2/paper/ledger.csv`): "
           f"{res['lived']} operaciones de perfil sin `retro`, {res['excluded']} sin riesgo "
           "reconstruible. Método del diagnóstico de la fase 24 (riesgo = |pnl| / |r|, bruto = "
           "neto + costo). El «después» es un **contrafactual** sobre esas mismas operaciones, no "
           "algo vivido: el cambio no se despliega mientras T31 cuente semanas.", "",
           "## 1. El número", "",
           "| Paso | Operaciones | Costo medio R | Costo mediana R | E[R] neto | ± EE | E[R] bruto |",
           "|---|--:|--:|--:|--:|--:|--:|"]
    for s in STEPS:
        x = st[s]
        out.append(f"| {LABELS[s]} | {x['n']} | {_n(x['cost_r'], '{:.3f}')} | "
                   f"{_n(x['cost_r_median'], '{:.3f}')} | {_n(x['net_r'])} | "
                   f"{_n(x['net_se'], '{:.3f}')} | {_n(x['gross_r'])} |")
    out += ["", "## 2. Por marco", "",
            "| Paso | Marco | n | Costo R | E[R] neto | ± EE | E[R] bruto |", "|---|---|--:|--:|--:|--:|--:|"]
    for s in STEPS:
        for tf, x in st[s]["by_tf"].items():
            if x["n"]:
                out.append(f"| {LABELS[s]} | {tf} | {x['n']} | {_n(x['cost_r'], '{:.3f}')} | "
                           f"{_n(x['net_r'])} | {_n(x['net_se'], '{:.3f}')} | {_n(x['gross_r'])} |")
    q = st["antes"]["by_tf"].get("15m", {})
    out += ["", "## 3. Lectura", "",
            f"- **El costo baja de {a['cost_r']:.3f} R a {z['cost_r']:.3f} R** por operación "
            f"({(1 - z['cost_r'] / a['cost_r']):.0%} menos). No llega a los ~0,06 R que estimó "
            "el diagnóstico: el ahorro maker solo toca la comisión de entrada de las `market` de "
            "1 h y 4 h, y el riesgo con costo escala, no elimina.",
            f"- **La esperanza neta no mejora: {a['net_r']:+.3f} → {z['net_r']:+.3f} R.** Lo que "
            "ahorran maker y el riesgo con costo lo devuelve la salida de 15 m.",
            f"- **15 m era el marco con mejor resultado vivido**: bruto {_n(q.get('gross_r'))} R y "
            f"neto {_n(q.get('net_r'))} ± {_n(q.get('net_se'), '{:.3f}')} R con n = {q.get('n')}. "
            "Con ese error estándar no se distingue de 1 h ni de 4 h. **La sombra, con veinte veces "
            "más muestra, dice lo contrario** (tabla siguiente): 15 m es el peor marco. Lo vivido en "
            "15 m es ruido de pocas operaciones y la salida de 15 m se sostiene, aunque en este "
            "contrafactual le cueste esperanza al libro.",
            "", "| Sombra (sin peso, sin `retro`) | n | E[R] neto | ± EE |", "|---|--:|--:|--:|",
            *[f"| {tf} | {x['n']} | {_n(x['net_r'])} | {_n(x['net_se'], '{:.3f}')} |"
              for tf, x in res["shadow"].items()], "",
            "- **T143 no crea ventaja, como decía su enunciado.** Lo que sí deja: el riesgo declarado "
            "es el real, el costo baja un tercio y se ve en el panel y en el informe semanal.", "",
            "## 4. Lo que este contrafactual no cubre", "",
            "- La no ejecución de las límite (0,2 % de intentos en el banco) y la selección adversa "
            "(bruto −0,001 R por intento en el banco): están medidas en `reports/t143_maker.md` §2 "
            "y son pequeñas frente al ahorro.",
            "- Quitar 15 m también cambia el capital disponible y los topes de las demás: aquí cada "
            "operación de 1 h y 4 h se queda como se vivió.",
            "- Las cifras son medias por operación con peso igual, como el diagnóstico; no son "
            "USDT del libro.", ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out", default="reports/t143_antes_despues")
    a = ap.parse_args()
    rows = list(csv.DictReader(Path(a.ledger).open(encoding="utf-8")))
    res = {"generado": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), **compare(rows),
           "shadow": shadow(rows)}
    out = Path(a.out)
    out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    out.with_suffix(".md").write_text(render(res), encoding="utf-8")
    print(f"escrito {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
