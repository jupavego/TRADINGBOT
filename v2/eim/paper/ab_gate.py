"""Criterios de T49 aplicados TAL CUAL a los escenarios del A/B (T111), sin relajarlos.

Cada escenario (perfil × salida × umbral) se mide como un intento más: sus operaciones cerradas
del libro del perfil, netas de costos, pasan por `measure` y `validate` de la puerta con los
criterios publicados (`validation_v1`), y su p de V3 se ajusta por Holm junto a TODOS los intentos
ya registrados. La réplica de V3 (lado al azar) simula el lado contrario de cada operación con la
MISMA salida del escenario: TP/BE+/tiempo en A, escalera con la misma cantidad en B.

Fuera de muestra estricto (el de T49): una operación cuenta solo si su decisión cae fuera de las
ventanas de ajuste de la versión de SU estrategia (y de sus ancestros) y fuera de la ventana en la
que se diseñó la salida. Sin I/O: las versiones, las ventanas y los p previos llegan como datos.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from eim.paper.engine import Outcome, simulate
from eim.paper.ladder import simulate_ladder
from eim.paper.ladder_book import LadderSim
from eim.paper.ladder_metrics import cost_of, risk_of
from eim.paper.params import ProfileParams, spec_for
from eim.validation.criteria import Criteria
from eim.validation.evidence import Trade, flip_idea, flip_r, ref_price
from eim.validation.gate import holm_family, measure, validate
from eim.validation.lineage import Version, Window, out_of_sample, tuning_windows


def gate_trades(trades: Sequence[dict], outcomes: Mapping[str, Outcome], sim: LadderSim,
                p: ProfileParams) -> list[Trade]:
    """Operaciones cerradas del libro → evidencia de la puerta, con el R del lado contrario
    simulado con la salida de `p` (escalera si `p.exit_mode == "ladder"`)."""
    out = []
    for t in trades:
        o = outcomes[t["id"]]
        i = o.idea
        flip = flip_idea(i, ref_price(o, sim.path))
        fo = (simulate_ladder(flip, sim.path, sim.ep, p.ladder, t["qty"], sim.fine,
                              spec=spec_for(i.symbol))
              if p.exit_mode == "ladder" else simulate(flip, sim.path, sim.ep))
        risk = risk_of(t)
        out.append(Trade(t=i.t, exit_t=int(t["exit_t"]), r=float(t["r"]), r_flip=flip_r(fo),
                         cost_r=cost_of(t) / risk if risk else 0.0,
                         regime=i.regime or "sin dato", origin=i.origin, side=i.side,
                         mfe_r=float(t.get("mfe_r") or 0.0), mae_r=float(t.get("mae_r") or 0.0)))
    return out


def strict_oos(trades: Sequence[dict], outcomes: Mapping[str, Outcome],
               versions: Sequence[Version], exit_windows: Sequence[Window],
               symbol: str) -> tuple[list[dict], dict]:
    """(operaciones fuera de muestra según T49, recuento de excluidas por motivo). Una idea cuya
    huella no está registrada no tiene tramo fuera de muestra declarado: se excluye."""
    fam: dict[str, list[Version]] = {}
    for v in versions:
        fam.setdefault(v.sid, []).append(v)
    keep, why = [], {"ventana_estrategia_o_salida": 0, "sin_version_registrada": 0}
    for t in trades:
        i = outcomes[t["id"]].idea
        v = next((x for x in fam.get(i.sid, []) if x.fingerprint == i.version), None)
        if v is None:
            why["sin_version_registrada"] += 1
            continue
        wins = (*tuning_windows(v, fam[i.sid]), *exit_windows)
        if out_of_sample(i.t, symbol, wins):
            keep.append(t)
        else:
            why["ventana_estrategia_o_salida"] += 1
    return keep, why


def gate_verdicts(items: Sequence[tuple[str, list[Trade]]], prior: Mapping[str, float | None],
                  crit: Criteria, symbol: str, asof: int,
                  prices: tuple[np.ndarray, np.ndarray] | None = None) -> list[dict]:
    """Veredicto de cada escenario (etiqueta, evidencia ya filtrada fuera de muestra) con Holm
    sobre la familia completa: los intentos registrados (`prior`) más estos escenarios."""
    attempts = len(prior) + len(items)
    ms = {lab: measure(f"{symbol}|{lab}", tr, (), symbol, asof, crit, attempts, prices)
          for lab, tr in items}
    adj = holm_family({m.label: m.p_raw for m in ms.values()}, prior)
    out = []
    for lab, m in ms.items():
        v = Version(lab, 1, "", lab.split("|")[0], "perfil", asof, None, "T111")
        x = validate(v, m, None if m.p_raw is None else adj[m.label], crit)
        j = x.to_json()
        out.append({"id": lab, "verdict": j["verdict"], "reason": j["reason"], "n_oos": m.n,
                    "mean_r": j["mean_r"], "p_raw": j["p_raw"], "p_holm": j["p_holm"],
                    "checks": j["checks"], "extras": j["extras"], "attempts": attempts,
                    "oos": {"from": m.span[0], "to": m.span[1]}})
    return out
