"""Informe de calibración (JSON + Markdown) y parámetros versionados."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from eim.calibration.space import SPACE, build

DEFAULT_DIR = Path("reports") / "calibration"
VERSIONS_DIR = Path(__file__).parent / "versions"


def _d(t: int) -> str:
    return datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d")


def _f(x: object, nd: int = 2) -> str:
    return "—" if x is None else f"{x:+.{nd}f}" if isinstance(x, float) else str(x)


def to_markdown(rep: dict) -> str:
    m, res = rep["meta"], rep["result"]
    dec = res["decision"]
    L = [f"# Calibración T26 — {m['symbol']} {m['timeframe']} (modo SIMULADO)", "",
         f"Datos: {m['source']} · {m['n_candles']} velas {_d(m['first_t'])}→{_d(m['last_t'])} · "
         f"hash `{m['data_hash']}` · control cruzado: {m.get('control') or 'ninguno'}", "",
         f"Objetivo por pliegue: {m['objective']}", "",
         f"**Decisión: {'ACEPTADOS' if dec['accepted'] else 'SE MANTIENEN LOS VALORES PREVIOS'}"
         f"** (gana en {dec['fold_wins']} de {len(res['folds'])} pliegues de prueba)."]
    L += [f"- {r}" for r in dec["reasons"]]
    L += ["", "## Dentro vs fuera de muestra por pliegue (mediana de Sharpe por ventana)", "",
          "| Prueba | Vigente train | Calib. train | Vigente test | Calib. test | "
          "Degradación calib. (test−train) | Control vigente | Control calib. |",
          "|---|---|---|---|---|---|---|---|"]
    for f in res["folds"]:
        tr, te, c = f["train"], f["test"], f.get("control", {})
        ms = {k: v["median_sharpe"] for k, v in
              (("trd", tr["default"]), ("trc", tr["calibrated"]), ("ted", te["default"]),
               ("tec", te["calibrated"]))}
        L.append(f"| {_d(f['test_from_t'])}→{_d(f['test_to_t'])} | {_f(ms['trd'])} | "
                 f"{_f(ms['trc'])} | {_f(ms['ted'])} | {_f(ms['tec'])} | "
                 f"{_f(ms['tec'] - ms['trc'])} | "
                 f"{_f(c.get('default', {}).get('median_sharpe'))} | "
                 f"{_f(c.get('calibrated', {}).get('median_sharpe'))} |")
    L += ["", "## Agregado fuera de muestra (ventanas de prueba encadenadas)", "",
          "| Métrica | Vigente | Calibrado | Diferencia |", "|---|---|---|---|"]
    for scope, title in (("oos", ""), ("control", " (control)")):
        g = res["aggregate"].get(scope)
        if not g:
            continue
        for k in ("median_window_sharpe", "sharpe", "total_return", "max_drawdown",
                  "expectancy_r", "win_rate", "n_trades"):
            a, b = g["default"].get(k), g["calibrated"].get(k)
            diff = b - a if isinstance(a, int | float) and isinstance(b, int | float) else None
            L.append(f"| {k}{title} | {_f(a)} | {_f(b)} | {_f(diff)} |")
    L += ["", "## Parámetros (último pliegue) y estabilidad ±10 %", "",
          "| Parámetro | Vigente | Último pliegue | Rango | Justificación |",
          "|---|---|---|---|---|"]
    last = res["folds"][-1]
    for d in SPACE:
        L.append(f"| `{d.name}` | {res['base'][d.name]} | {_r(last['values'][d.name])} | "
                 f"[{d.low}, {d.high}] | {d.why} |")
    st = last.get("stability")
    if st:
        L += ["", f"Peor perturbación: `{st['worst_label']}` → objetivo {_f(st['worst'])} "
              f"({'PICUDA' if st['peaked'] else 'estable'})."]
    else:
        L += ["", "Último pliegue: ningún candidato superó al vigente en su peor caso ±10 %."]
    fid = rep.get("fidelity")
    if fid:
        L += ["", "## Fidelidad del caché de insumos", "",
              f"Ventana de {fid['bars']} velas: {fid['trades_cached']} operaciones con caché vs "
              f"{fid['trades_full']} con el agente completo ({fid['same_entries']} entradas "
              f"idénticas); retorno {_f(fid['return_cached'], 4)} vs {_f(fid['return_full'], 4)}."]
    L += ["", "## Notas", ""] + [f"- {n}" for n in rep["notes"]]
    return "\n".join(L) + "\n"


def _r(v: object) -> object:
    return round(v, 3) if isinstance(v, float) else v


def write_report(rep: dict, name: str, out_dir: Path | str = DEFAULT_DIR) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pj, pm = out / f"{name}.json", out / f"{name}.md"
    pj.write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    pm.write_text(to_markdown(rep), encoding="utf-8")
    return pj, pm


def write_version(rep: dict, version: str, out_dir: Path | str = VERSIONS_DIR) -> Path:
    """Parámetros versionados: los del último pliegue con su estado (aceptado o no) y trazas."""
    res = rep["result"]
    accepted = res["decision"]["accepted"]
    values = res["folds"][-1]["values"] if accepted else res["base"]
    doc = {"version": version, "created": datetime.now(UTC).isoformat(timespec="seconds"),
           "status": "aceptado" if accepted else "rechazado: se mantienen los vigentes",
           "values": values, "candidate": res["folds"][-1]["values"],
           "reasons": res["decision"]["reasons"], "data_hash": rep["meta"]["data_hash"],
           "symbol": rep["meta"]["symbol"], "timeframe": rep["meta"]["timeframe"]}
    p = Path(out_dir) / f"{version}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    return p


def load_version(path: Path | str):
    """(PlanParams, SynthesisParams, tp_index) de un archivo versionado (campo `values`)."""
    return build(json.loads(Path(path).read_text(encoding="utf-8"))["values"])
