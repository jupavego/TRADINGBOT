"""Estrategias sobre el contexto de los agentes: consenso, plan, sugerencias, escenarios,
contrarias y el control aleatorio. Funciones puras de (contexto, indicadores, índice)."""

from __future__ import annotations

import hashlib

from eim.paper.ideas import Draft, StrategyInfo, atr_draft, finite, sign

# Umbrales (explícitos; la retroalimentación decide luego cuánto peso darles)
SYN_BIAS = 0.2
SYN_CONF = 0.2
STRONG_BIAS = 0.35
STRONG_AGREE = 0.55
SCEN_P = 0.4          # probabilidad mínima del escenario dominante
SCEN_EDGE = 0.1       # ventaja mínima sobre el escenario opuesto
RANDOM_RATE = 0.2     # fracción de velas en que el control aleatorio opera
SETUP_FILL_H = 12.0   # = SetupParams.fill_hours
SETUP_HOLD_H = 36.0   # = SetupParams.max_hours


def _bar_h(ctx: dict) -> float:
    return float(ctx.get("bar_h") or 1.0)


def _syn(ctx: dict, bias: float, conf: float) -> tuple[int, dict] | None:
    s = ctx.get("syn")
    if not s or abs(s["bias"]) < bias or s["conf"] < conf:
        return None
    return sign(s["bias"]), s


def _syn_why(s: dict) -> str:
    return f"Síntesis {s['bias']:+.2f} · confianza {s['conf']:.0%} · acuerdo {s['agree']:.0%}"


def consenso_sintesis(ctx: dict, _x: object, _i: int) -> Draft | None:
    got = _syn(ctx, SYN_BIAS, SYN_CONF)
    return got and atr_draft(got[0], ctx, 1.5, 2.5, got[1]["conf"], (_syn_why(got[1]),))


def consenso_fuerte(ctx: dict, _x: object, _i: int) -> Draft | None:
    got = _syn(ctx, STRONG_BIAS, SYN_CONF)
    if not got or got[1]["agree"] < STRONG_AGREE:
        return None
    return atr_draft(got[0], ctx, 1.2, 3.0, min(1.0, got[1]["conf"] * 1.5),
                     (_syn_why(got[1]), "Consenso fuerte: sesgo alto y agentes de acuerdo"),
                     hold_h=36)


def contra_sintesis(ctx: dict, _x: object, _i: int) -> Draft | None:
    got = _syn(ctx, SYN_BIAS, SYN_CONF)
    return got and atr_draft(-got[0], ctx, 1.5, 2.5, got[1]["conf"],
                             (_syn_why(got[1]), "Contraria: apuesta a que el consenso se equivoca"))


def _plan(tp_index: int):
    def fn(ctx: dict, _x: object, _i: int) -> Draft | None:
        p = ctx.get("plan")
        if not p or p.get("status") != "VIGENTE" or len(p["tp"]) <= tp_index:
            return None
        side = 1 if p["side"] == "long" else -1
        return Draft(side=side, sl=p["sl"], tp=p["tp"][tp_index], conf=p.get("conf") or 0.5,
                     why=(f"Plan del agente: entrada {p['entry']:.2f}, SL {p['sl']:.2f}, "
                          f"TP{tp_index + 1} {p['tp'][tp_index]:.2f}",
                          "SL estructural con colchón ATR (agente plan)"),
                     entry=ctx["close"], hold_h=48, key=f"plan:{p.get('created_t')}")
    return fn


def _setup(rank: int | None):
    """`rank` = posición en el top 3; None = la mejor alineada con la síntesis y con EV > 0."""
    def fn(ctx: dict, _x: object, _i: int) -> Draft | None:
        ss = ctx.get("setups") or []
        if rank is None:
            ss = [s for s in ss if s["aligned"] and (s["ev_r"] or 0) > 0]
            s = ss[0] if ss else None
        else:
            s = ss[rank] if len(ss) > rank else None
        if not s:
            return None
        return Draft(side=1 if s["side"] == "long" else -1, sl=s["sl"], tp=s["tp"],
                     conf=s["p_tp"] or 0.0, kind="limit", entry=s["entry"],
                     fill_h=SETUP_FILL_H, hold_h=SETUP_HOLD_H, scale=False,
                     why=(s["basis"], f"P(llenado) {s['p_fill']:.0%} · P(TP antes que SL) "
                                      f"{s['p_tp']:.0%} · EV {s['ev_r']:+.2f} R · "
                                      f"confluencia {s['conf_n']}"))
    return fn


def _dominant(fc: dict) -> tuple[int, dict] | None:
    bull, bear = fc.get("bull") or {}, fc.get("bear") or {}
    pb, pr = bull.get("p") or 0.0, bear.get("p") or 0.0
    if pb >= SCEN_P and pb >= pr + SCEN_EDGE:
        return 1, bull
    if pr >= SCEN_P and pr >= pb + SCEN_EDGE:
        return -1, bear
    return None


def escenario_dominante(ctx: dict, _x: object, _i: int) -> Draft | None:
    fc = ctx.get("fc")
    got = fc and _dominant(fc)
    if not got:
        return None
    side, sc = got
    c, a = ctx["close"], ctx["atr"]
    if not finite(sc.get("end"), sc.get("inv"), a) or (sc["end"] - c) * side < 0.5 * a:
        return None
    return Draft(side=side, sl=sc["inv"], tp=sc["end"], conf=sc["p"], entry=c,
                 hold_h=fc["h"] * _bar_h(ctx), scale=False,
                 why=(f"Escenario {'alcista' if side > 0 else 'bajista'} dominante "
                      f"({sc['p']:.0%}); TP en su mediana, SL en su invalidación",))


def escenario_retroceso(ctx: dict, _x: object, _i: int) -> Draft | None:
    """Entrada límite en un retroceso (cuantil 25/75 del cierre simulado) a favor del dominante."""
    fc = ctx.get("fc")
    got = fc and _dominant(fc)
    q = (fc or {}).get("q") or {}
    if not got or not finite(q.get("25"), q.get("75"), q.get("10"), q.get("90")):
        return None
    side, sc = got
    c, a = ctx["close"], ctx["atr"]
    entry = q["25"] if side > 0 else q["75"]
    sl = (q["10"] if side > 0 else q["90"]) - side * 0.25 * a
    if not finite(sc.get("end")) or (c - entry) * side < 0.25 * a:
        return None
    return Draft(side=side, sl=sl, tp=sc["end"], conf=sc["p"] * 0.8, kind="limit", entry=entry,
                 fill_h=fc["h"] * _bar_h(ctx) / 2, hold_h=fc["h"] * _bar_h(ctx), scale=False,
                 why=(f"Retroceso al cuantil {'25' if side > 0 else '75'} del cierre simulado "
                      f"a favor del escenario dominante ({sc['p']:.0%})",))


def escenario_rango(ctx: dict, _x: object, _i: int) -> Draft | None:
    """Escenario neutral dominante: límite en el borde de su banda más cercano, TP en la mediana."""
    fc = ctx.get("fc")
    nt = (fc or {}).get("neutral") or {}
    p = nt.get("p") or 0.0
    if not fc or p < SCEN_P or not finite(nt.get("lo"), nt.get("hi"), nt.get("end")):
        return None
    c, mid = ctx["close"], nt["end"]
    side = 1 if abs(c - nt["lo"]) <= abs(nt["hi"] - c) else -1
    entry = nt["lo"] if side > 0 else nt["hi"]
    if (mid - entry) * side <= 0:
        return None
    sl = entry - side * 0.5 * abs(mid - entry)
    return Draft(side=side, sl=sl, tp=mid, conf=p, kind="limit", entry=entry,
                 fill_h=fc["h"] * _bar_h(ctx) / 2, hold_h=fc["h"] * _bar_h(ctx), scale=False,
                 why=(f"Escenario neutral dominante ({p:.0%}): reversión desde el borde de "
                      "su banda hacia la mediana",))


def control_aleatorio(ctx: dict, _x: object, _i: int) -> Draft | None:
    """Lado al azar (determinista por vela) con las mismas salidas que «Síntesis a favor»."""
    h = int(hashlib.sha256(f"{ctx.get('symbol', '')}:{ctx['t']}".encode()).hexdigest()[:8], 16)
    if (h % 1000) / 1000 >= RANDOM_RATE:
        return None
    side = 1 if (h >> 12) & 1 else -1
    return atr_draft(side, ctx, 1.5, 2.5, 0.5, ("Control: lado al azar; mide la suerte",))


CORE: tuple[StrategyInfo, ...] = (
    StrategyInfo("consenso_sintesis", "Síntesis a favor", "consenso",
                 f"Sigue el sesgo de la síntesis si |sesgo| ≥ {SYN_BIAS} y confianza ≥ "
                 f"{SYN_CONF:.0%}; a mercado, SL 1,5 ATR, TP 2,5 ATR.", consenso_sintesis),
    StrategyInfo("consenso_fuerte", "Consenso fuerte", "consenso",
                 f"Solo con |sesgo| ≥ {STRONG_BIAS} y acuerdo ≥ {STRONG_AGREE:.0%}; SL 1,2 ATR, "
                 "TP 3 ATR.", consenso_fuerte),
    StrategyInfo("plan_tp1", "Plan del agente (TP1)", "consenso",
                 "Cada plan VIGENTE del agente plan, una vez, con su SL estructural y TP1.",
                 _plan(0)),
    StrategyInfo("plan_tp2", "Plan del agente (TP2)", "consenso",
                 "Igual que el anterior pero apuntando al TP2: ¿compensa esperar más?", _plan(1)),
    StrategyInfo("sugerencia_1", "Sugerencia #1", "sugerencias",
                 "La operación intradía mejor valorada (orden límite, 12 h para llenarse).",
                 _setup(0)),
    StrategyInfo("sugerencia_2", "Sugerencia #2", "sugerencias",
                 "La segunda sugerencia: ¿el orden de las sugerencias acierta?", _setup(1)),
    StrategyInfo("sugerencia_3", "Sugerencia #3", "sugerencias", "La tercera sugerencia.",
                 _setup(2)),
    StrategyInfo("sugerencia_alineada", "Sugerencia alineada", "sugerencias",
                 "La mejor sugerencia a favor de la síntesis y con valor esperado positivo.",
                 _setup(None)),
    StrategyInfo("escenario_dominante", "Escenario dominante", "escenarios",
                 f"Escenario alcista o bajista con prob. ≥ {SCEN_P:.0%}: TP en su mediana y SL "
                 "en su invalidación.", escenario_dominante),
    StrategyInfo("escenario_retroceso", "Retroceso del escenario", "escenarios",
                 "Límite en el cuantil 25/75 del cierre simulado a favor del dominante.",
                 escenario_retroceso),
    StrategyInfo("escenario_rango", "Rango del escenario neutral", "escenarios",
                 "Si domina el neutral: límite en el borde de su banda, TP en la mediana.",
                 escenario_rango),
    StrategyInfo("contra_sintesis", "Contra la síntesis", "contrarias",
                 "Lo opuesto a «Síntesis a favor»: si gana, el consenso está mal calibrado.",
                 contra_sintesis),
    StrategyInfo("control_aleatorio", "Control aleatorio", "control",
                 f"Lado al azar en ~{RANDOM_RATE:.0%} de las velas con las mismas salidas: la "
                 "vara para saber si algo supera a la suerte.", control_aleatorio),
)
