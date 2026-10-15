"""Balance de operaciones ganadas frente a perdidas (función pura).

Ponderado de los 3 perfiles: cada operación cerrada pesa igual (acierto conjunto = ganadas /
total), más el desglose por perfil y por periodo. Ganada = PnL neto > 0 (después de comisiones,
deslizamiento y funding); el resto cuenta como perdida. Incluye la retroalimentación en texto:
qué funcionó, qué no y qué mejorar.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

DAY_MS = 86_400_000
WINDOWS: tuple[tuple[str, str, int | None], ...] = (
    ("todo", "Todo", None), ("30d", "30 días", 30), ("7d", "7 días", 7), ("24h", "24 h", 1))
MIN_SIDE_N = 20       # operaciones por lado para comparar largos y cortos
SIDE_GAP = 0.10       # diferencia de acierto que merece un aviso
TIME_SHARE = 0.25     # fracción de pérdidas por tiempo que merece un aviso


def _avg(xs: Sequence[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _cost(t: dict) -> float:
    return t["fees"] + t["slip"] + t["funding"]


def _half(ts: Sequence[dict]) -> dict:
    reasons: dict[str, int] = {}
    for t in ts:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    rs = [t["r"] for t in ts if t["r"] is not None]
    return {"n": len(ts), "usd": sum(t["pnl"] for t in ts), "avg_usd": _avg([t["pnl"] for t in ts]),
            "avg_r": _avg(rs), "by_reason": reasons}


def summarize(trades: Sequence[dict]) -> dict:
    """Ganadas, perdidas y las razones que las relacionan (acierto necesario, esperanza, PF)."""
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    n = len(trades)
    w, lo = _half(wins), _half(losses)
    # en R: no depende del tamaño de cada perfil (los USDT de los 3 perfiles no son comparables)
    payoff = (w["avg_r"] / -lo["avg_r"]
              if w["avg_r"] is not None and lo["avg_r"] is not None and lo["avg_r"] < 0 else None)
    return {
        "n": n, "wins": w, "losses": lo,
        "win_rate": len(wins) / n if n else None,
        "net": w["usd"] + lo["usd"],
        "pf": w["usd"] / -lo["usd"] if lo["usd"] < 0 else None,
        "payoff": payoff,
        # acierto mínimo para no perder con esa relación ganancia media / pérdida media
        "breakeven": 1 / (1 + payoff) if payoff else None,
        "expectancy_usd": (w["usd"] + lo["usd"]) / n if n else None,
        "expectancy_r": _avg([t["r"] for t in trades if t["r"] is not None]),
        "costs": sum(_cost(t) for t in trades),
        # perdedoras que habrían ganado antes de costos
        "cost_flips": sum(1 for t in losses if t["pnl"] + _cost(t) > 0),
        "long_wr": _rate([t for t in trades if t["side"] > 0]),
        "short_wr": _rate([t for t in trades if t["side"] < 0]),
    }


def _rate(ts: Sequence[dict]) -> dict:
    return {"n": len(ts), "win_rate": sum(t["pnl"] > 0 for t in ts) / len(ts) if ts else None}


def _pct(x: float) -> str:
    return f"{round(x * 100)} %"


def _abs(x: float) -> str:
    return f"{abs(x):,.0f}".replace(",", ".") + " USDT"


def _usd(x: float) -> str:
    return f"{x:+,.0f}".replace(",", ".") + " USDT"


def feedback(trades: Sequence[dict], s: dict, names: Mapping[str, str]) -> list[dict]:
    """Retroalimentación del periodo: funcionó / no funcionó / mejorar (reglas fijas)."""
    if not trades:
        return [{"kind": "mejorar", "text": "Sin operaciones cerradas en este periodo."}]
    by: dict[str, list[dict]] = {}
    for t in trades:
        by.setdefault(t["strategy"], []).append(t)
    net = sorted(((sum(t["pnl"] for t in ts), k, ts) for k, ts in by.items()), key=lambda x: x[0])
    out: list[dict] = []
    best = net[-1]
    if best[0] > 0:
        wn = sum(t["pnl"] > 0 for t in best[2])
        out.append({"kind": "funciono", "text": f"{names.get(best[1], best[1])}: {wn} de "
                    f"{len(best[2])} ganadas, neto {_usd(best[0])}."})
    else:
        out.append({"kind": "funciono", "text": "Ninguna estrategia terminó en positivo en este "
                    "periodo."})
    worst = net[0]
    if worst[0] < 0:
        ln = sum(t["pnl"] <= 0 for t in worst[2])
        out.append({"kind": "no_funciono", "text": f"{names.get(worst[1], worst[1])}: {ln} de "
                    f"{len(worst[2])} perdidas, neto {_usd(worst[0])}."})
    wr, be = s["win_rate"], s["breakeven"]
    if wr is not None and be is not None:
        if wr < be:
            payoff = f"{s['payoff']:.2f}".replace(".", ",")
            out.append({"kind": "mejorar", "text": f"Con la relación ganancia media / pérdida "
                        f"media actual en R ({payoff}) hay que acertar al menos {_pct(be)} para no "
                        f"perder; se acierta {_pct(wr)}. Subir el R:B (TP más lejos o SL más "
                        "ajustado) o filtrar las señales más débiles."})
        else:
            out.append({"kind": "funciono", "text": f"El acierto ({_pct(wr)}) supera el mínimo "
                        f"necesario ({_pct(be)}) para la relación ganancia/pérdida actual."})
    if s["cost_flips"]:
        out.append({"kind": "mejorar", "text": f"{s['cost_flips']} operaciones perdidas habrían "
                    f"sido ganadas sin costos (comisiones, deslizamiento y funding suman "
                    f"{_abs(s['costs'])}): priorizar entradas límite (maker) y operaciones con "
                    "más recorrido."})
    lt = s["losses"]["by_reason"].get("TIEMPO", 0)
    if s["losses"]["n"] and lt / s["losses"]["n"] >= TIME_SHARE:
        out.append({"kind": "mejorar", "text": f"{_pct(lt / s['losses']['n'])} de las pérdidas "
                    "salen por tiempo: el precio no llega al objetivo en el horizonte; acercar el "
                    "TP o acortar la espera."})
    lg, sh = s["long_wr"], s["short_wr"]
    if (lg["n"] >= MIN_SIDE_N and sh["n"] >= MIN_SIDE_N
            and abs(lg["win_rate"] - sh["win_rate"]) >= SIDE_GAP):
        good, bad = ("largos", "cortos") if lg["win_rate"] > sh["win_rate"] else ("cortos",
                                                                                 "largos")
        out.append({"kind": "mejorar", "text": f"Los largos aciertan {_pct(lg['win_rate'])} y los"
                    f" cortos {_pct(sh['win_rate'])}: dar más peso a los {good} o exigir más "
                    f"confirmación a los {bad}."})
    return out


def balance(trades_by_profile: Mapping[str, Sequence[dict]], names: Mapping[str, str],
            now: int) -> dict:
    """Por periodo: ponderado de todos los perfiles, cada perfil y la retroalimentación."""
    out: dict = {}
    for key, label, days in WINDOWS:
        since = None if days is None else now - days * DAY_MS
        sel = {pid: [t for t in ts if since is None or t["exit_t"] >= since]
               for pid, ts in trades_by_profile.items()}
        pooled = [t for ts in sel.values() for t in ts]
        s = summarize(pooled)
        out[key] = {"label": label, "since": since, "all": s,
                    "profiles": {pid: summarize(ts) for pid, ts in sel.items()},
                    "feedback": feedback(pooled, s, names)}
    return out
