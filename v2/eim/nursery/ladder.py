"""Escalafón de la cantera (T170, `cantera_v1`): la etapa de cada prospecto en `t`. Puro.

Diseño: `PLAN/notas/T167_cantera.md` §3 (escalafón y sensibilidad) y §10. Umbrales: el
pre-registro `prereg_cantera_v1.json` (forma en `ladder_rules.py`). Solo cuentan operaciones
cerradas en `exit_t ≤ t`, y las etapas **solo cambian en las revisiones fijadas** (días 30, 61, 91,
121, 152 y 182 desde el alta): la lectura semanal de T159 o el panel no son una mirada.

Etapas: guardería → cantera → promesa → primer equipo (candidato; lo confirma o veta el usuario en
T172), y baja en cualquier momento, definitiva, **sin dejar de contar en la familia** (m fijo).

- **Promesa** (capa sensible): rentabilidad neta > 0, e-BH (q = 0,10) sobre el e-proceso de d̃ de
  cada prospecto, consistencia (ninguna operación > 40 % del beneficio), hermano simple (a empate,
  asciende el simple) y contribución marginal. Los requisitos no estadísticos se miran **antes**
  de e-BH: quien no los cumple entra con e = 0, y el e-valor de quien asciende queda congelado.
  Así todo ascenso de la fase pertenece al conjunto de e-BH sobre e-valores detenidos y la FDR de
  las promesas sigue ≤ q aunque se mire seis veces.
- **Baja**: tope de drawdown calibrado, futilidad frente a μ_mín (Bonferroni sobre las seis
  revisiones), 60 días sin operar (sin contar los días con el marco cerrado), claramente negativo
  al salir de guardería, examen físico hacia adelante de los que no tenían historia y fecha límite.
- **Primer equipo**: solo en la última revisión (`ladder_final.first_team`, StepM estricto).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from eim.nursery import evalue
from eim.nursery import ladder_stats as st
from eim.nursery.ladder_rules import LadderRules
from eim.nursery.ladder_stats import DAY_MS, AccountData

GUARDERIA, CANTERA, PROMESA, PRIMER, BAJA = ("guarderia", "cantera", "promesa", "primer_equipo",
                                             "baja")


@dataclass(frozen=True)
class Member:
    """Un prospecto de la familia, tal como lo congela el pre-registro."""

    id: str
    agent_id: str
    timeframe: str
    n_params: int
    band: str                   # banda congelada (medida en T169 o declarada)
    history: bool               # False: examen físico hacia adelante
    theme: str
    sibling: str | None = None  # hermano simple, si este prospecto es más complejo
    generic: str | None = None  # cuenta de control `agente_{id}@marco`
    registered_ms: int | None = None   # reentrada (plaza de reserva): cuenta desde su alta


@dataclass
class Standing:
    id: str
    stage: str = GUARDERIA
    since_ms: int = 0
    reviews: int = 0
    band: str = ""
    exit: dict | None = None
    criteria: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    frozen_e: float | None = None

    def to_json(self) -> dict:
        return {"id": self.id, "stage": self.stage, "since_ms": self.since_ms,
                "reviews": self.reviews, "band": self.band, "exit": self.exit,
                "criteria": self.criteria, "metrics": self.metrics,
                "promoted": self.frozen_e is not None}


def review_times(alta_ms: int, rules: LadderRules) -> list[int]:
    return [alta_ms + d * DAY_MS for d in rules.reviews_days]


def _crit(cid: str, ok: bool | None, motivo: str, value: object = None,
          threshold: object = None) -> dict:
    return {"id": cid, "ok": ok, "value": value, "threshold": threshold, "motivo": motivo}


def _set(s: Standing, stage: str, tau: int) -> None:
    if s.stage != stage:
        s.stage, s.since_ms = stage, tau


def _drop(s: Standing, tau: int, reason: str, motivo: str) -> None:
    _set(s, BAJA, tau)
    s.exit = {"reason": reason, "at_ms": tau, "motivo": motivo}


def _metrics(m: Member, acc: AccountData, s: Standing, rules: LadderRules,
             initial: float) -> dict:
    obs = st.observations(acc, s.band, rules)
    ms = evalue.mean_se(obs, rules.primary.clip_r)
    pnl = st.net_pnl(acc)
    return {"n": len(acc.closed), "obs": len(obs),
            "d_mean": None if ms is None else round(ms[0], 4),
            "d_se": None if ms is None else round(ms[1], 4),
            "evalue": round(evalue.promise_evalue(obs, rules.primary.clip_r,
                                                  rules.primary.lambdas), 4),
            "futility_ub": evalue.futility_bound(obs, rules.primary.clip_r, rules.futility.beta,
                                                 rules.looks),
            "net_pnl_usd": round(pnl, 2), "net_return_pct": round(pnl / initial * 100, 3),
            "max_dd_pct": round(st.max_dd_pct(acc, initial), 3),
            "dd_cap_pct": rules.drawdown.caps_pct.get(m.id)}


def _bajas(m: Member, s: Standing, acc: AccountData, k: dict, rules: LadderRules,
           tau: int, alta: int, spans: Sequence[tuple[int, int]]) -> None:
    """Tope de drawdown, futilidad e inactividad (en ese orden; la primera que salta manda)."""
    cap, dd = k["dd_cap_pct"], k["max_dd_pct"]
    if cap is not None and dd > cap:
        _drop(s, tau, "drawdown", f"drawdown {dd:.1f} % > tope calibrado {cap:.1f} %")
        return
    ub, fut = k["futility_ub"], rules.futility
    if ub is not None and k["obs"] >= fut.min_trades and ub < fut.mu_min_r:
        _drop(s, tau, "futilidad", f"cota superior de d̃ {ub:+.3f} R < μ_mín "
                                   f"{fut.mu_min_r:+.2f} R")
        return
    idle = st.inactive_days(acc, alta, tau, spans, rules.inactivity.gate_closed_counts)
    k["inactive_days"] = round(idle, 1)
    if idle >= rules.inactivity.days:
        _drop(s, tau, "inactividad", f"{idle:.0f} días sin operar (≥ {rules.inactivity.days}; "
                                     "sin contar los días con el marco cerrado)")


def _leave_nursery(m: Member, s: Standing, acc: AccountData, k: dict, rules: LadderRules,
                   tau: int, alta: int, spans: Sequence[tuple[int, int]]) -> None:
    ne, cn = rules.nursery_exit, rules.clearly_negative
    if k["n"] < ne.min_trades and tau - alta < ne.max_days * DAY_MS:
        s.criteria.append(_crit("guarderia", None, f"{k['n']} de {ne.min_trades} operaciones",
                                k["n"], ne.min_trades))
        return
    neg = k["d_mean"] is not None and k["d_mean"] + cn.z * k["d_se"] < 0
    if k["n"] >= cn.min_trades and neg:
        _drop(s, tau, "claramente_negativo", f"d̃ {k['d_mean']:+.3f} + {cn.z:g}·EE < 0 al salir "
                                             "de guardería")
        return
    if not m.history:
        why, band = st.forward_exam(acc, s.band, alta, tau, spans, rules.forward_exam)
        s.band = band
        if why:
            _drop(s, tau, "examen_fisico", "examen físico hacia adelante: " + "; ".join(why))
            return
    _set(s, CANTERA, tau)


def _eligible(m: Member, acc: AccountData, k: dict, data: Mapping[str, AccountData],
              rules: LadderRules, alta: int, tau: int) -> tuple[bool, list[dict]]:
    """Requisitos de Promesa distintos de e-BH, con su motivo."""
    out, p = [], rules.promise
    pnl = k["net_pnl_usd"]
    out.append(_crit("rentabilidad", pnl > 0, f"beneficio neto {pnl:+.2f} USDT", pnl, 0))
    share = st.top_share(acc)
    out.append(_crit("consistencia", share is not None and share <= p.max_trade_share,
                     "sin beneficio" if share is None else
                     f"la mejor operación explica el {share * 100:.0f} % del beneficio "
                     f"(≤ {p.max_trade_share * 100:.0f} %)", share, p.max_trade_share))
    if m.sibling:
        sib = data.get(m.sibling, AccountData()).upto(tau)
        ok, z = st.beats([c.d for c in acc.closed], [c.d for c in sib.closed], rules)
        out.append(_crit("hermano_simple", ok, f"frente a {m.sibling}: z = {z} (a empate, "
                                               "asciende el simple)", z, p.sibling_alpha))
    own = st.daily_pnl(acc, alta, tau)
    for other in (m.sibling, m.generic):
        if other:
            ok, info = st.marginal(own, st.daily_pnl(data.get(other, AccountData()).upto(tau),
                                                     alta, tau), rules)
            out.append(_crit(f"marginal:{other}", ok, f"correlación diaria {info['corr']} con "
                             f"{other}; aporta {info.get('gain_usd_day')} USDT/día", info,
                             p.marginal_corr))
    return all(c["ok"] for c in out), out


def _review(members: Sequence[Member], acct: Mapping[str, AccountData],
            data: Mapping[str, AccountData], spans: Mapping[str, Sequence[tuple[int, int]]],
            stand: dict[str, Standing], rules: LadderRules, alta: int, tau: int, m: int,
            initial: float, final: bool) -> None:
    ek: dict[str, float] = {}
    for mb in members:
        s = stand[mb.id]
        if s.stage in (BAJA, PRIMER):
            continue
        a0 = max(alta, mb.registered_ms or alta)
        if tau <= a0:
            continue
        s.reviews += 1
        s.criteria = []
        acc = acct.get(mb.id, AccountData()).upto(tau)
        k = s.metrics = _metrics(mb, acc, s, rules, initial)
        sp = spans.get(mb.timeframe, ())
        _bajas(mb, s, acc, k, rules, tau, a0, sp)
        if s.stage == GUARDERIA:
            _leave_nursery(mb, s, acc, k, rules, tau, a0, sp)
        if s.stage not in (CANTERA, PROMESA):
            continue
        ok, crit = _eligible(mb, acc, k, data, rules, a0, tau)
        s.criteria.extend(crit)
        if s.frozen_e is not None:
            ek[mb.id] = s.frozen_e
        elif ok:
            ek[mb.id] = k["evalue"]
        if not ok:
            _set(s, CANTERA, tau)
    for mb in members:          # un ascenso es para siempre en e-BH, aunque luego sea baja
        if stand[mb.id].frozen_e is not None:
            ek.setdefault(mb.id, stand[mb.id].frozen_e)
    ids = list(ek)
    rej = {ids[i] for i in evalue.ebh([ek[i] for i in ids], m, rules.promise.q)}
    for mb in members:
        s = stand[mb.id]
        if s.stage not in (CANTERA, PROMESA):
            continue
        hit = mb.id in rej
        eligible = all(c["ok"] for c in s.criteria)
        s.criteria.append(_crit("e_bh", hit, f"e-valor {s.metrics['evalue']:.2f}; e-BH con "
                                             f"q = {rules.promise.q:g} y m = {m}",
                                s.metrics["evalue"], rules.promise.q))
        if hit and eligible:
            if s.frozen_e is None:
                s.frozen_e = s.metrics["evalue"]
            _set(s, PROMESA, tau)
        else:
            _set(s, CANTERA, tau)
    if final:
        for mb in members:
            s = stand[mb.id]
            if s.stage in (GUARDERIA, CANTERA):
                _drop(s, tau, "fecha_limite", "fecha límite de la fase sin llegar a promesa")


def evaluate(members: Sequence[Member], accounts: Mapping[str, AccountData],
             rules: LadderRules, alta_ms: int, t: int, m: int, initial: float,
             controls: Mapping[str, AccountData] | None = None,
             closed_spans: Mapping[str, Sequence[tuple[int, int]]] | None = None,
             first_team=None) -> dict[str, Standing]:
    """La etapa de cada prospecto en `t` (solo con lo cerrado en `exit_t ≤ t`).

    `m` es el tamaño de la familia pre-registrado (inscritos + plazas de reserva): no baja cuando
    alguien se da de baja. `first_team(members, accounts, standings, tau)` decide el primer equipo
    en la última revisión (`ladder_final.first_team`); sin él, las promesas quedan como promesa.
    """
    if len(members) > m:
        raise ValueError(f"{len(members)} prospectos para una familia de {m}")
    data = {**(controls or {}), **accounts}
    stand = {mb.id: Standing(mb.id, since_ms=alta_ms, band=mb.band) for mb in members}
    times = review_times(alta_ms, rules)
    for i, tau in enumerate(times):
        if tau > t:
            break
        final = i == len(times) - 1
        _review(members, accounts, data, closed_spans or {}, stand, rules, alta_ms, tau, m,
                initial, final)
        if final and first_team is not None:
            first_team(members, accounts, stand, tau)
    nxt = next((x for x in times if x > t), None)
    for s in stand.values():
        s.metrics.setdefault("next_review_ms", nxt)
        if s.reviews == 0:
            s.criteria = [_crit("primera_revision", None, "en guardería hasta la primera "
                                                          "revisión mensual", None, times[0])]
    return stand
