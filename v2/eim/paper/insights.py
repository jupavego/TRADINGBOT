"""Conclusiones en texto a partir de las fichas por estrategia y de los perfiles.

Reglas fijas y honestas: con muestra chica lo dice; compara contra el control aleatorio;
solo llama «significativo» a lo que sobrevive a Holm.
"""

from __future__ import annotations

from collections.abc import Sequence

from eim.paper.feedback import MIN_N_TEST
from eim.paper.params import FAMILIES, FeedbackParams

SMALL_SAMPLE = 30


def _fmt(x: float | None, d: int = 2) -> str:
    return "—" if x is None else f"{x:+.{d}f}".replace(".", ",")


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f} %"


def _by_base(rows: Sequence[dict]) -> dict[str, dict]:
    """Una estrategia sumando sus marcos (R medio ponderado por operaciones)."""
    out: dict[str, dict] = {}
    for r in rows:
        k = r.get("base", r["id"])
        a = out.setdefault(k, {"name": r["name"].split(" · ")[0], "n": 0, "sum_r": 0.0})
        a["n"] += r["n"]
        a["sum_r"] += r["sum_r"]
    for a in out.values():
        a["mean_r"] = a["sum_r"] / a["n"] if a["n"] else None
    return out


SHORT_CAUSE = {"direccion": "dirección equivocada", "sl_rapido": "SL rápido",
               "casi_tp": "casi TP", "tiempo": "por tiempo", "costos": "por costos"}


def _pair(rows: dict[str, dict], a: str, b: str, label: str, what: str) -> dict | None:
    x, y = rows.get(a), rows.get(b)
    if not x or not y or x["n"] < MIN_N_TEST or y["n"] < MIN_N_TEST:
        return None
    better = x["mean_r"] >= y["mean_r"]
    return {"tone": "info", "text": f"{label}: {x['name']} {_fmt(x['mean_r'])} R/op (n={x['n']}) "
            f"vs {y['name']} {_fmt(y['mean_r'])} R/op (n={y['n']}) → "
            f"{what if better else 'no se confirma'}."}


def insights(rows: Sequence[dict], fams: Sequence[dict], profiles: Sequence[dict],
             counts: dict[str, int], p: FeedbackParams | None = None) -> list[dict]:
    p = p or FeedbackParams()
    out: list[dict] = []
    total = sum(r["n"] for r in rows)
    if total == 0:
        return [{"tone": "warn", "text": "Aún no hay operaciones cerradas: lanza un backtest o "
                 "espera a que el servicio en vivo acumule velas."}]
    live = sum(r["origin_live"] for r in rows)
    out.append({"tone": "warn" if total < SMALL_SAMPLE * 3 else "info",
                "text": f"{total} operaciones sombra cerradas ({live} decididas en vivo, el resto "
                        f"reconstruidas) sobre {counts.get('vivo', 0) + counts.get('backtest', 0)}"
                        " velas. Con muestras chicas las conclusiones son provisionales."})
    by = _by_base(rows)
    ctrl = by.get("control_aleatorio")
    ok = [r for r in rows if r["n"] >= p.n_min and r["family"] != "control"]
    if ctrl and ctrl["n"] >= MIN_N_TEST:
        beat = [r for r in ok if r["mean_r"] > ctrl["mean_r"]]
        out.append({"tone": "info", "text": f"Control aleatorio: {_fmt(ctrl['mean_r'])} R/op "
                    f"(n={ctrl['n']}). {len(beat)} de {len(ok)} estrategias con muestra "
                    f"suficiente lo superan; lo demás no se distingue de la suerte."})
    ranked = sorted(ok, key=lambda r: r["judgement"]["m"], reverse=True)
    for r in ranked[:3]:
        if r["judgement"]["m"] > 0:
            out.append({"tone": "good", "text": f"Destaca {r['name']}: {_fmt(r['judgement']['m'])}"
                        f" R/op contraído (bruto {_fmt(r['mean_r'])}, n={r['n']}, acierto "
                        f"{_pct(r['win_rate'])}, PF {_fmt(r['pf'])})."})
    for r in [x for x in ranked[::-1] if x["judgement"]["state"] == "pausa"][:3]:
        out.append({"tone": "bad", "text": f"{r['name']} pierde de forma consistente "
                    f"({_fmt(r['mean_r'])} R/op, n={r['n']}): en pausa hasta que se recupere "
                    "en la evaluación sombra."})
    sig = [r for r in rows if r["p_holm"] is not None and r["p_holm"] < 0.05]
    out.append({"tone": "good" if sig else "warn", "text": (
        "Significativas tras corregir por comparaciones múltiples (Holm, 5 %): "
        + ", ".join(r["name"] for r in sig) + "."
        if sig else "Ninguna estrategia es significativamente positiva tras corregir por "
        "comparaciones múltiples (Holm, 5 %): lo que destaca puede ser azar.")})
    for pr in (_pair(by, "sugerencia_1", "sugerencia_3", "Orden de las sugerencias",
                     "el ranking acierta"),
               _pair(by, "plan_tp2", "plan_tp1", "Plan: TP2 frente a TP1",
                     "compensa esperar al TP2"),
               _pair(by, "consenso_sintesis", "contra_sintesis", "Síntesis frente a su contraria",
                     "el consenso aporta dirección")):
        if pr:
            out.append(pr)
    tfs: dict[str, list[float]] = {}
    for r in rows:
        if r.get("timeframe") and r["n"]:
            a = tfs.setdefault(r["timeframe"], [0, 0.0])
            a[0] += r["n"]
            a[1] += r["sum_r"]
    if len(tfs) > 1:
        best_tf = max(tfs, key=lambda k: tfs[k][1] / tfs[k][0])
        out.append({"tone": "info", "text": "Por temporalidad: " + "; ".join(
            f"{k} {_fmt(v[1] / v[0])} R/op (n={v[0]})" for k, v in sorted(tfs.items()))
            + f". La mejor hoy es {best_tf}."})
    causes: dict[str, int] = {}
    for r in rows:
        for k, n in (r.get("by_cause") or {}).items():
            causes[k] = causes.get(k, 0) + n
    if sum(causes.values()) >= MIN_N_TEST:
        tot = sum(causes.values())
        out.append({"tone": "info", "text": "Por qué se pierde: " + ", ".join(
            f"{SHORT_CAUSE.get(k, k)} {_pct(n / tot)}"
            for k, n in sorted(causes.items(), key=lambda kv: -kv[1])) + "."})
    fam = [f for f in fams if f["n"] >= MIN_N_TEST and f["family"] != "control"]
    if len(fam) >= 2:
        best, worst = fam[0], fam[-1]
        out.append({"tone": "info", "text": f"Por familia: mejor {FAMILIES[best['family']]} "
                    f"({_fmt(best['mean_r'])} R/op, n={best['n']}), peor "
                    f"{FAMILIES[worst['family']]} ({_fmt(worst['mean_r'])} R/op, n={worst['n']})."})
    reg: dict[str, tuple[str, float, int]] = {}
    for r in ok:
        for k, v in r["by_regime"].items():
            if v["n"] >= MIN_N_TEST and (k not in reg or v["mean_r"] > reg[k][1]):
                reg[k] = (r["name"], v["mean_r"], v["n"])
    if reg:
        out.append({"tone": "info", "text": "Mejor por régimen: " + "; ".join(
            f"{k}: {name} ({_fmt(m)} R/op, n={n})" for k, (name, m, n) in sorted(reg.items()))
            + "."})
    for pr in profiles:
        cost = pr["fees"] + pr["slip"] + pr["funding"]
        if pr["n_closed"] >= SMALL_SAMPLE and pr["realized"] < 0 < cost:
            share = ("más que toda la pérdida" if cost >= -pr["realized"]
                     else f"{_pct(cost / -pr['realized'])} de la pérdida")
            usdt = f"{cost:,.0f}".replace(",", ".")
            gross = f"{pr['realized'] + cost:+,.0f}".replace(",", ".")
            out.append({"tone": "warn", "text": f"Costos en {pr['name']}: comisiones, deslizamiento"
                        f" y funding suman {usdt} USDT ({share}); antes de costos el resultado"
                        f" sería {gross} USDT."})
    if profiles:
        best = max(profiles, key=lambda x: x["return_pct"])
        calm = max(profiles, key=lambda x: x["return_pct"] / max(x["max_dd_pct"], 0.01))
        out.append({"tone": "good" if best["return_pct"] > 0 else "bad",
                    "text": f"Perfil más rentable: {best['name']} ({_fmt(best['return_pct'] * 100)}"
                            f" %); mejor rentabilidad por drawdown: {calm['name']} (DD máx. "
                            f"{_pct(calm['max_dd_pct'])})."})
    return out
