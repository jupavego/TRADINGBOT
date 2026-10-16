"""Señales en vivo (T48c): cada decisión tomada en tiempo real, su estado en la evaluación
sombra y qué hizo cada perfil con ella y por qué (función pura).

Una decisión es «en vivo» si su vela se analizó a lo sumo una vela después de cerrar
(`origin == "vivo"`); las reconstruidas por el backtest no aparecen aquí.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from eim.paper.book import ProfileState
from eim.paper.engine import Outcome

CLOSES = ("tp", "be", "sl", "tiempo")
ACTION_LABEL = {"rechazada": "Rechazada", "orden": "Orden pendiente", "abierta": "Abierta",
                "cancelada": "Cancelada", "tp": "Cerrada en TP", "be": "Cerrada en break-even +",
                "sl": "Cerrada en SL", "tiempo": "Cerrada por tiempo",
                "fuera": "No la evalúa"}


def _action(evs: Sequence[dict]) -> dict:
    """Resumen de lo que hizo un perfil con una idea a partir de sus eventos."""
    if not evs:
        return {"action": "fuera", "label": ACTION_LABEL["fuera"],
                "text": "familia fuera del universo del perfil o señal sin órdenes"}
    cats = [e["cat"] for e in evs]
    last = evs[-1]
    if "rechazada" in cats:
        e = next(x for x in evs if x["cat"] == "rechazada")
        return {"action": "rechazada", "label": ACTION_LABEL["rechazada"], "text": e["text"]}
    for c in CLOSES:
        if c in cats:
            e = next(x for x in evs if x["cat"] == c)
            return {"action": c, "label": ACTION_LABEL[c], "text": e["text"],
                    "pnl": e.get("pnl"), "r": e.get("r")}
    if "cancelada" in cats:
        return {"action": "cancelada", "label": ACTION_LABEL["cancelada"], "text": last["text"]}
    if "llenada" in cats:
        return {"action": "abierta", "label": ACTION_LABEL["abierta"],
                "text": f"posición abierta a {last.get('price')}"}
    o = next(x for x in evs if x["cat"] == "orden")
    return {"action": "orden", "label": ACTION_LABEL["orden"],
            "text": f"orden {o['text']} · {o.get('leverage')}x · riesgo {o.get('risk_usd', 0):.2f}"
                    " USDT"}


def live_feed(outcomes: Sequence[Outcome], books: Mapping[str, ProfileState],
              live_ctx: Sequence[tuple[str, int]], limit: int = 100) -> dict:
    """Decisiones en vivo (más recientes primero), velas analizadas en vivo y resumen."""
    by_idea: dict[str, dict[str, list[dict]]] = {}
    for pid, st in books.items():
        for e in st.events:
            if e.get("origin") == "vivo" and e["cat"] != "aprendizaje":
                by_idea.setdefault(e["idea"], {}).setdefault(pid, []).append(e)
    live = sorted((o for o in outcomes if o.idea.origin == "vivo"),
                  key=lambda o: (-o.idea.t, o.idea.sid))
    rows = []
    for o in live[:limit]:
        evs = by_idea.get(o.idea.id, {})
        rows.append({**o.to_json(),
                     "profiles": {pid: _action(sorted(evs.get(pid, []), key=lambda e: e["t"]))
                                  for pid in books}})
    per_candle: dict[tuple[str, int], int] = {}
    for o in live:
        k = (o.idea.timeframe, o.idea.t)
        per_candle[k] = per_candle.get(k, 0) + 1
    candles = [{"timeframe": tf, "t": t, "signals": per_candle.get((tf, t), 0)}
               for tf, t in sorted(live_ctx, key=lambda x: -x[1])][:60]
    status: dict[str, int] = {}
    for o in live:
        status[o.status] = status.get(o.status, 0) + 1
    profiles: dict[str, dict] = {}
    for pid in books:
        acts: dict[str, int] = {}
        reasons: dict[str, int] = {}
        for o in live:
            a = _action(sorted(by_idea.get(o.idea.id, {}).get(pid, []), key=lambda e: e["t"]))
            acts[a["action"]] = acts.get(a["action"], 0) + 1
            if a["action"] == "rechazada":
                k = a["text"].split(":")[0].split("(")[0].strip()
                reasons[k] = reasons.get(k, 0) + 1
        taken = sum(n for k, n in acts.items() if k not in ("rechazada", "fuera"))
        profiles[pid] = {"actions": acts, "taken": taken,
                         "top_reasons": sorted(reasons.items(), key=lambda kv: -kv[1])[:3]}
    return {"mode": "SIMULADO", "total": len(live), "candles": candles,
            "candles_total": len(live_ctx), "status": status, "profiles": profiles,
            "decisions": rows}
