"""Cota del oráculo de la salida adaptativa M4 (E6 de §8 de `PLAN/notas/T129_sl_dinamico.md`).

T111 vio que la escalera gana en días laterales y la salida A en días de tendencia, pero la
etiqueta de régimen que se conoce AL ENTRAR no separa los casos. Antes de construir rasgos conviene
saber **cuánto se podría ganar como máximo** si el régimen se conociera con certeza: un predictor
real solo recupera una parte de eso, así que si el techo ya es bajo, M4 se descarta sin más trabajo.

Se calculan dos cotas, de menor a mayor optimismo:

- **Oráculo por día** (`oracle`): con las etiquetas **ex post** del día (`ab_conditions`), se toma
  M0 en los días laterales y M1 en los de tendencia. Los días «intermedio» y «sin_dato» van a la
  política que diga el mapa, y hay que declararla: es media rejilla de decisión.
- **Envolvente por operación** (`envelope`): para cada entrada se toma **la mejor de las dos**
  salidas. No es alcanzable ni con un oráculo de régimen —exige acertar operación a operación, no
  día a día—, así que es el **techo absoluto de cualquier selector** entre M0 y M1. Si la
  envolvente no cumple los criterios 1–3 de §5.4, **ningún** selector puede cumplirlos y M4 muere.

Puro: sin red y sin disco. No decide nada; da la cota y su veredicto frente a los criterios.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace

from eim.paper.exits.bench import Bench, BenchTrade

TREND, RANGE, MIDDLE = "tendencia", "lateral", "intermedio"
NO_DATA = "sin_dato"


def pick_by_day(bench: Bench, labeler: Callable[[int], tuple[str, ...]],
                policy_of: Mapping[str, str], oracle_id: str = "M4_oraculo",
                ) -> tuple[list[BenchTrade], dict[str, int]]:
    """Oráculo por día: de cada entrada emparejada se toma la salida que diga `policy_of`.

    `policy_of` asocia cada etiqueta de tendencia del día (`tendencia`, `lateral`, `intermedio`,
    `sin_dato`) con el id de una política del banco. La etiqueta es **ex post**: solo sirve para
    medir el techo, nunca para decidir. Devuelve las operaciones y el reparto por etiqueta.
    """
    out, counts = [], {}
    for row in bench.paired():
        label = next((x for x in labeler(row.t) if x in policy_of), NO_DATA)
        pid = policy_of.get(label)
        counts[label] = counts.get(label, 0) + 1
        if pid is None or (t := row.by_policy.get(pid)) is None:
            continue
        out.append(replace(t, policy=oracle_id))
    return out, counts


def pick_best(bench: Bench, policies: Sequence[str],
              envelope_id: str = "M4_envolvente") -> tuple[list[BenchTrade], dict[str, int]]:
    """Envolvente por operación: la mejor de `policies` en cada entrada (techo inalcanzable)."""
    out, wins = [], dict.fromkeys(policies, 0)
    for row in bench.paired():
        cands = [(row.by_policy[p], p) for p in policies if row.by_policy.get(p) is not None]
        if not cands:
            continue
        best, pid = max(cands, key=lambda x: x[0].r)
        wins[pid] += 1
        out.append(replace(best, policy=envelope_id))
    return out, wins


def diffs_vs(trades: Sequence[BenchTrade], base: Sequence[BenchTrade]) -> list[tuple[int, float]]:
    """(día, ΔR) emparejado por id de idea frente a la base; solo las entradas comunes."""
    by_id = {t.id: t for t in base}
    return [(t.day, t.r - by_id[t.id].r) for t in trades if t.id in by_id]


def criteria_1_to_3(cand: Mapping, base: Mapping, ci: tuple[float, float],
                    pf_min: float, dd_max: float) -> dict:
    """Criterios 1–3 de §5.4 de una candidata frente a UNA base. `ci` es el IC del ΔE[R]."""
    d_exp = (None if cand.get("expectancy_r") is None or base.get("expectancy_r") is None
             else cand["expectancy_r"] - base["expectancy_r"])
    lo = ci[0] if ci[0] == ci[0] else None            # NaN = sin IC
    c1 = None if d_exp is None or lo is None else bool(d_exp > 0 and lo > 0)
    ratio, pf = cand.get("win_loss_ratio"), cand.get("pf")
    b_pf = base.get("pf")
    c2 = (None if ratio is None or pf is None or b_pf is None
          else bool(ratio >= 0.5 and pf >= pf_min * b_pf))
    dd, b_dd = cand.get("max_dd_r"), base.get("max_dd_r")
    cv, b_cv = cand.get("cvar95_r"), base.get("cvar95_r")
    c3 = (None if None in (dd, b_dd, cv, b_cv)
          else bool(dd <= b_dd * dd_max and cv >= b_cv))
    return {
        "delta_expectancy_r": d_exp, "ci": [ci[0], ci[1]],
        "c1_delta_positivo": c1,
        "c2_cociente_y_pf": c2,
        "c3_dd_y_cvar": c3,
        "detalle": {
            "win_loss_ratio": ratio, "pf": pf, "pf_base": b_pf,
            "pf_exigido": None if b_pf is None else pf_min * b_pf,
            "max_dd_r": dd, "max_dd_base": b_dd,
            "max_dd_permitido": None if b_dd is None else b_dd * dd_max,
            "cvar95_r": cv, "cvar95_base": b_cv},
        "cumple_1_a_3": bool(c1 and c2 and c3),
    }


def verdict(checks: Mapping[str, Mapping], oracle_id: str = "M4_oraculo") -> str:
    """Veredicto de E6, que se juzga con el **oráculo por día**, no con la envolvente.

    E6 define la cota como «E[R] de M4 si el régimen se conociera con certeza (M0 en días
    laterales y M1 en días de tendencia, etiquetas ex post)». La envolvente por operación es
    contexto: elige la mejor de las dos salidas sabiendo ya cómo acabó cada operación, así que no
    es una cota de un selector de régimen y cumplir los criterios con ella no prueba nada.
    """
    orc = checks.get(oracle_id, {})
    if not orc:
        return "sin datos para concluir"
    failed = [b for b, v in orc.items() if not v.get("cumple_1_a_3")]
    if not failed:
        return ("el oráculo por día CUMPLE los criterios 1–3 frente a las dos bases: hay techo "
                "y merece la pena buscar rasgos, sabiendo que un predictor real recupera solo "
                "una parte de él")
    why = []
    for b in failed:
        v = orc[b]
        bad = [n for n, k in (("1 (ΔE[R] e IC)", "c1_delta_positivo"),
                              ("2 (cociente y PF)", "c2_cociente_y_pf"),
                              ("3 (DD y CVaR)", "c3_dd_y_cvar")) if v.get(k) is False]
        why.append(f"frente a {b} falla el criterio {' y el '.join(bad) or 'alguno'}")
    return ("M4 SE DESCARTA (E6): ni conociendo el régimen con certeza cumpliría los criterios "
            f"1–3 de §5.4 — {'; '.join(why)}. Un predictor real recupera solo una fracción de "
            "ese techo, así que no hay nada que recuperar y no se construyen rasgos")
