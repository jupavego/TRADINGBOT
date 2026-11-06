"""Motor de gestión de la posición en el libro (T135): `exit_mode="adaptativo"`.

Lleva al bróker simulado una política de T132 (M2, M3, M5, M6 o M7) con la jerarquía de §4.2 de
`PLAN/notas/T129_sl_dinamico.md`:

1. **Controles duros:** la autoridad de T114 (`policy.decide`) y la liquidación del libro siguen.
2. **Trinquete:** el stop nunca se afloja (`exits/trail.py`) y el suelo del diario T110 se respeta.
3. **Una sola política por posición,** fijada por el perfil. Nunca el máximo de varias (H5).
4. **Límites del candidato:** piso de ruido y redondeo al tick en contra del operador.
5. **Agentes:** ninguno escribe stops. Los rasgos salen de las velas por `ExitFeatures` versionado.

El motor reutiliza `simulate_trail`, el mismo código que T134 midió en el banco. Aquí solo se añade
lo que el libro necesita: cuánto vale cada stop en USDT, en qué fase y por qué está donde está, y la
versión de la política. Todo eso va en `Outcome.ladder`, que ya leen el resumen y el diario; la
base de datos no cambia.

**Ningún perfil usa esto hoy.** T134 rechazó las 87 variantes, así que no hay salida aprobada que
encender (criterios de §5.4). Puro: sin red, sin disco y sin estado global.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import replace

from eim.paper.engine import Outcome, Path
from eim.paper.exits import features
from eim.paper.exits.candidates import HtfExit, TimeExit, TrailExit
from eim.paper.exits.policy import ExitContext, ExitPolicy
from eim.paper.exits.trail import TrailLimits
from eim.paper.ideas import Idea
from eim.paper.ladder_audit import (
    ALLOWED_CLOSE,
    FORBIDDEN_CLOSE,
    audit_outcome,
    check_close_request,
)
from eim.paper.ladder_book import LadderSim
from eim.paper.ladder_math import costs_for, floor_qty, net_usd
from eim.paper.params import ExecParams, ProfileParams, spec_for
from eim.paper.versioning import exit_fingerprint

OWN_CLOSE = {"M6": "TIEMPO", "M7": "HTF"}    # el único cierre extra que cada política pre-registra
STOP_CLOSES = ("SL", "SLD")
RECENT_VIOLATIONS = 10


def exit_identity(p: ProfileParams) -> dict:
    """Lo que define la salida de `p`: entra en su versión y, con ella, en la huella de T49."""
    ap = p.adaptive
    knobs = ap.knobs()
    if ap.policy == "M5":
        knobs = {**knobs, "est_cost_frac": p.est_cost_frac}   # el BE+ de M5 los incluye
    return {"policy": ap.policy, "params": knobs, "features": features.VERSION}


def exit_version(p: ProfileParams) -> str:
    return exit_fingerprint(exit_identity(p))


def build_policy(p: ProfileParams, path: Path, fine: Path | None = None, htf: Path | None = None,
                 cache: dict | None = None) -> ExitPolicy:
    """La política del perfil sobre este camino. `cache` evita repetir rasgos entre perfiles."""
    ap = p.adaptive
    key = (ap.sigma, ap.swing_bars, htf is not None)
    cache = {} if cache is None else cache
    feats = cache.get(key)
    if feats is None:
        feats = cache[key] = features.build(path, ap.sigma, swing_bars=ap.swing_bars, fine=fine,
                                            htf=htf)
    vid = f"{ap.policy}@{exit_version(p)}"
    lim = TrailLimits(floor_n=ap.floor_n)
    if ap.policy == "M2":
        return TrailExit(vid, vid, feats, "M2", {"k": ap.k, "activate_r": ap.activate_r}, lim)
    if ap.policy == "M3":
        return TrailExit(vid, vid, feats, "M3", {"buffer_sigma": ap.buffer_sigma}, lim)
    if ap.policy == "M5":
        return TrailExit(vid, vid, feats, "M5",
                         {"k": ap.k, "buffer_sigma": ap.buffer_sigma, "trail": ap.trail,
                          "survival_r": ap.survival_r, "a_r": ap.a_r, "b_r": ap.b_r,
                          "est_cost_frac": p.est_cost_frac}, lim)
    if ap.policy == "M6":
        return TimeExit(vid, vid, feats, bars=ap.bars, min_r=ap.min_r)
    return HtfExit(vid, vid, feats)


def policies_for(profiles: Iterable[ProfileParams], symbol: str, path: Path, fine: Path | None,
                 read_htf: Callable[[], Path] | None = None) -> dict[str, ExitPolicy]:
    """Política de cada perfil adaptativo de `symbol`. Sin ninguno no se calcula ni se lee nada."""
    out: dict[str, ExitPolicy] = {}
    cache: dict = {}
    for p in profiles:
        if p.adaptive is None or (p.symbols and symbol not in p.symbols):
            continue
        htf = read_htf() if p.adaptive.policy == "M7" and read_htf is not None else None
        out[p.id] = build_policy(p, path, fine, htf, cache)
    return out


def _limit_text(p: ProfileParams) -> str:
    ap = p.adaptive
    if ap.policy == "M6":
        cond = f" si no llegó a {ap.min_r:g} R" if ap.min_r > 0 else ""
        return f"; cierra a las {ap.bars} velas{cond}"
    return "; cierra si el marco mayor se invierte" if ap.policy == "M7" else ""


def motive(p: ProfileParams, hist: list[dict]) -> str:
    """Por qué el stop vigente está donde está, en palabras."""
    ap = p.adaptive
    if not hist:
        return "SL inicial de la idea" + _limit_text(p)
    last = hist[-1]
    if last["source"] == "recuperado":
        return "suelo recuperado del diario: el stop no se afloja"
    if last.get("phase") == "equilibrio_mas":
        return f"BE+: entrada + costos + {ap.b_r:g} R"
    if ap.policy == "M3" or (ap.policy == "M5" and ap.trail == "M3"):
        return (f"arrastre: último swing confirmado de {ap.swing_bars} velas − "
                f"{ap.buffer_sigma:g}·σ ({ap.sigma})")
    return f"arrastre: extremo − {ap.k:g}·σ ({ap.sigma})"


def _finite(x: float | None) -> float | None:
    return x if x is not None and math.isfinite(x) else None


def decorate(o: Outcome, p: ProfileParams, ep: ExecParams) -> Outcome:
    """`Outcome` del motor con lo que el libro, el diario y la interfaz leen de él."""
    lad = o.ladder
    if lad is None:
        return o
    s, qty, fill = o.idea.side, lad["qty"], o.fill
    closed = o.status == "CERRADA"
    c = costs_for(o.fee_in, o.slip, ep)
    if closed:
        c = replace(c, slip_out=0.0)      # `Outcome.slip` de un cierre ya lleva el de salida

    def net(price: float) -> float:
        return net_usd(s, qty, fill, price, o.funding, c)

    ver, hist = exit_version(p), []
    for h in lad["stop_history"]:
        mf = _finite(h.get("max_float"))
        if mf is None and h.get("extreme") is not None:
            mf = net(h["extreme"])
        hist.append({**h, "nominal": _finite(h.get("nominal")), "max_float": mf,
                     "active": (h["stop"] - fill) * s > 0, "motive": motive(p, [*hist, h]),
                     "version": ver, "features": features.VERSION})
    stop = lad["stop"]
    info = {**lad, "stop_history": hist, "active": (stop - fill) * s > 0, "first_usd": 0.0,
            "step_usd": 0.0, "nominal_usd": 0.0, "levels": [],
            "max_float_usd": net(lad["extreme"]),
            "exit": {"mode": "adaptativo", "policy": p.adaptive.policy, "version": ver,
                     "features": features.VERSION, "phase": lad["phase"],
                     "motive": motive(p, hist), "source": lad["stop_source"]}}
    if closed:
        info["protected_est_usd"] = net(stop) if hist else None
    else:
        info |= {"float_usd": net(o.mark if o.mark is not None else fill),
                 "stop_est_usd": net(stop)}
    return replace(o, ladder=info)


def simulate_adaptive(p: ProfileParams, sim: LadderSim, i: Idea, qty: float,
                      *, guarded: bool = True) -> Outcome:
    """La idea con la salida de `p`: con el suelo del diario y las velas de 1 m del vivo.

    `guarded=False` es para una operación que no ocurrió, como la réplica de lado contrario de
    `ab_gate`: lleva el identificador de la real, y el suelo de esa no es suyo.
    """
    pol = sim.exits.get(p.id)
    if pol is None:
        raise ValueError(f"el perfil {p.id} (adaptativo) no tiene política en esta mesa")
    guard = sim.guards.get((p.id, i.id)) if guarded else None
    ctx = ExitContext(sim.path, sim.ep, spec_for(i.symbol), sim.fine, guard)
    return decorate(pol.simulate(i, ctx, qty), p, sim.ep)


def open_adaptive(p: ProfileParams, sim: LadderSim, i: Idea, qty: float) -> tuple[float, Outcome]:
    """Cantidad al paso del instrumento y resultado con esa cantidad, como `open_ladder`."""
    spec = spec_for(i.symbol)
    q = floor_qty(qty, spec.qty_step)
    if q < spec.min_qty:
        return q, Outcome(i, "RECHAZADA", "CANTIDAD")
    return q, simulate_adaptive(p, sim, i, q)


def close_violation(p: ProfileParams, reason: str) -> str | None:
    """Motivo si `reason` no puede cerrar una posición de este perfil. Una señal contraria nunca."""
    if p.exit_mode == "ladder":
        return check_close_request(reason)
    if p.exit_mode != "adaptativo":
        return None
    if reason in ALLOWED_CLOSE or reason == OWN_CLOSE.get(p.adaptive.policy):
        return None
    return FORBIDDEN_CLOSE.get(reason, f"motivo de cierre no pre-registrado «{reason}»")


def audit_adaptive(o: Outcome, p: ProfileParams) -> list[str]:
    """Violaciones de las reglas en un resultado adaptativo (vacío = limpio)."""
    info, i = o.ladder, o.idea
    if not info:
        return ["resultado sin estado de la salida adaptativa"]
    s, hist, out = i.side, info["stop_history"], []
    if o.status == "CERRADA":
        if why := close_violation(p, o.reason):
            out.append(why)
        if o.reason == "SLD" and not hist:
            out.append("cierre por SL dinámico sin que el stop se moviera")
        if o.reason == "SL" and hist:
            out.append("cierre por SL inicial con el stop ya movido")
        if (o.reason in STOP_CLOSES and o.exit is not None
                and (o.exit - info["stop"]) * s > 0):
            out.append("la salida quedó mejor que el SL vigente (cierre que no fue el stop)")
        if o.exit_t is not None and o.fill_t is not None and o.exit_t < o.fill_t:
            out.append("el cierre es anterior a la apertura")
        if info.get("incident"):
            out.append("cierre normal con una incidencia técnica pendiente")
    prev = i.sl
    for h in hist:
        if (h["stop"] - prev) * s <= 0:
            out.append("el SL retrocedió o no avanzó: el trinquete se rompió")
        prev = h["stop"]
    return out


def audit_close(p: ProfileParams, o: Outcome) -> list[str]:
    """Auditoría del cierre según la salida del perfil (la sombra no tiene estado que auditar)."""
    if p.exit_mode == "ladder":
        return audit_outcome(o)
    return audit_adaptive(o, p) if p.exit_mode == "adaptativo" else []


def exit_text(o: Outcome) -> str:
    """Texto del cierre para la bitácora."""
    e = o.ladder["exit"]
    return (f"cierre por {o.reason} · fase {e['phase']} · {e['motive']} "
            f"({e['policy']}@{e['version']})")


def adaptive_summary(st, positions: list[dict]) -> dict:
    """Bloque del perfil para la vista: la política, sus rasgos y lo que está pasando."""
    p = st.p
    phases = Counter(x["ladder"]["exit"]["phase"] for x in positions if x.get("ladder"))
    return {"policy": p.adaptive.policy, "version": exit_version(p), **exit_identity(p),
            "feature_info": st.exit_info, "open_phases": dict(phases),
            "closes": dict(Counter(t["reason"] for t in st.trades)),
            "contrary_signals": st.contrary,
            "violations_recent": st.violations[-RECENT_VIOLATIONS:]}
