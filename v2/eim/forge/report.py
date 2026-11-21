"""Informe de la forja (T208): JSON con todo y un Markdown que se pueda leer de un tirón.

El informe dice siempre, junto al mejor resultado, **lo que daría la mejor de `m` recetas por puro
azar**: un número que salió de miles de intentos no se puede leer sin eso.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

DIR = Path("reports/forge")


def _f(x: object, nd: int = 4) -> str:
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def _rows_md(rows: list[dict], n: int = 20) -> list[str]:
    out = ["| receta | familia | n | R medio | t | p bruto | p RW | DSR | costo R |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in rows[:n]:
        out.append(f"| `{r['id']}` | {r['family']} | {r['n']} | {_f(r['mean_r'])} | "
                   f"{_f(r['t'], 2)} | {_f(r['p_raw'], 3)} | {_f(r['p_rw'], 3)} | "
                   f"{_f(r['dsr'], 3)} | {_f(r['cost_r'])} |")
    return out


def by_family(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        d = out.setdefault(r["family"], {"recipes": 0, "trades": 0, "sum_r": 0.0, "best": None})
        d["recipes"] += 1
        d["trades"] += r["n"]
        d["sum_r"] += r["mean_r"] * r["n"]
        if d["best"] is None or r["mean_r"] > d["best"]["mean_r"]:
            d["best"] = {"id": r["id"], "mean_r": r["mean_r"], "n": r["n"]}
    for d in out.values():
        d["mean_r"] = d["sum_r"] / d["trades"] if d["trades"] else None
        d.pop("sum_r")
    return out


def build(res: dict, prereg: dict, coverage: dict, control: dict,
          stress: dict | None, hold: dict | None) -> dict:
    return {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prereg": {"version": prereg["version"], "fingerprint": prereg.get("fingerprint"),
                   "grid_fingerprint": prereg["grid"]["fingerprint"]},
        "mode": "ANALISIS", "coverage": coverage,
        "family": {k: res[k] for k in ("m", "distinct_signals", "with_min_trades", "days",
                                       "trades_total", "seconds", "reps", "seed")},
        "pbo": res["pbo"], "expected_max_z": res["expected_max_z"],
        "t_null_max_mean": res["t_null_max_mean"],
        "best": res["best"], "survivors": res["survivors"],
        "by_family": by_family(res["rows"]),
        "top": res["rows"][:50], "worst": res["rows"][-10:],
        "random_control": control, "cost_stress": stress, "holdout": hold,
    }


def to_markdown(rep: dict) -> str:
    f = rep["family"]
    best = rep["best"] or {}
    L = [f"# Forja 5 m · sesión americana — {rep['generated']}", "",
         f"**Modo ANALISIS.** Pre-registro `{rep['prereg']['version']}` "
         f"(huella `{rep['prereg']['fingerprint']}`, "
         f"rejilla `{rep['prereg']['grid_fingerprint']}`).",
         "",
         f"- **{f['m']} recetas** ({f['distinct_signals']} series de señal distintas), "
         f"{f['with_min_trades']} con operaciones suficientes, "
         f"{f['trades_total']} operaciones en {f['days']} sesiones.",
         f"- Datos: {rep['coverage'].get('candles')} velas de 5 m, "
         f"{rep['coverage'].get('gaps')} huecos.",
         f"- Umbral del azar: con {f['m']} intentos, el máximo nulo esperado es "
         f"**z = {_f(rep['expected_max_z'], 2)}** "
         f"(t del máximo nulo remuestreado: {_f(rep['t_null_max_mean'], 2)}).",
         f"- PBO: **{_f((rep['pbo'] or {}).get('pbo'), 2)}** "
         f"({(rep['pbo'] or {}).get('reason', 'CSCV')}).", ""]
    if rep["survivors"]:
        L += [f"## Sobreviven {len(rep['survivors'])}", ""] + \
             [f"- `{i}`" for i in rep["survivors"]] + [""]
    else:
        L += ["## No sobrevive ninguna", "",
              "Ninguna receta pasa los cuatro criterios del pre-registro. Con miles de intentos "
              "esto es lo esperable: el umbral del azar sube con `m`, y la mejor de la rejilla no "
              "lo alcanza.", ""]
    L += ["## Mejor receta de la rejilla (leer con el umbral del azar al lado)", "",
          f"`{best.get('id', '—')}` · n = {best.get('n', '—')} · R medio = "
          f"{_f(best.get('mean_r'))} · t = {_f(best.get('t'), 2)} · p RW = "
          f"{_f(best.get('p_rw'), 3)} · DSR = {_f(best.get('dsr'), 3)}", "",
          "## Las 20 mejores", ""] + _rows_md(rep["top"]) + ["", "## Por familia", "",
          "| familia | recetas | operaciones | R medio | mejor |", "|---|---|---|---|---|"]
    for fam, d in sorted(rep["by_family"].items()):
        b = d["best"] or {}
        L.append(f"| {fam} | {d['recipes']} | {d['trades']} | {_f(d['mean_r'])} | "
                 f"`{b.get('id', '—')}` ({_f(b.get('mean_r'))}) |")
    L += ["", "## Control de entradas al azar (debe dar ≈ −costo)", "",
          "| salida | operaciones | R medio |", "|---|---|---|"]
    for k, v in rep["random_control"].items():
        L.append(f"| {k} | {v['trades']} | {_f(v['mean_r'])} |")
    if rep.get("cost_stress"):
        L += ["", "## Estrés de costos", "", "| receta | ×1 | ×1,5 | ×2 |", "|---|---|---|---|"]
        for k, v in rep["cost_stress"].items():
            L.append(f"| `{k}` | {_f(v.get('1.0'))} | {_f(v.get('1.5'))} | {_f(v.get('2.0'))} |")
    if rep.get("holdout"):
        L += ["", "## Reserva (mirada una sola vez)", "", "| receta | n | R medio |",
              "|---|---|---|"]
        for k, v in rep["holdout"].items():
            L.append(f"| `{k}` | {v['n']} | {_f(v['mean_r'])} |")
    L += ["", "---", "", "Nada de esto opera: la forja solo propone. Un superviviente entra en la "
          "cantera con ◆ del usuario y empieza su cuenta desde cero, hacia adelante."]
    return "\n".join(L) + "\n"


def write(rep: dict, out_dir: Path | None = None, tag: str | None = None) -> tuple[Path, Path]:
    d = out_dir or DIR
    d.mkdir(parents=True, exist_ok=True)
    name = f"forja_5m_{tag or datetime.now(UTC).strftime('%Y%m%d-%H%M')}"
    j, m = d / f"{name}.json", d / f"{name}.md"
    j.write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    m.write_text(to_markdown(rep), encoding="utf-8")
    return j, m
