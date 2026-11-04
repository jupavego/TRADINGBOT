"""Los ocho criterios de §5.4 aplicados tal cual a cada variante (T134).

Nada de «la mejor del banco»: una política se aprueba **solo** si cumple los ocho, y si falla uno
se dice cuál y con qué cifra. Tres cosas que este módulo no hace y conviene tener claras:

- No elige: devuelve APROBADA, RECHAZADA o PENDIENTE con su motivo, y quien decide es el usuario.
- No relaja nada por falta de datos: lo que no se puede juzgar queda **pendiente**, que no es
  aprobado. El criterio 7 (prospectivo en papel) es siempre pendiente aquí, porque su dato no
  existe hasta T135.
- No convierte un «no se midió» en un «cumple». El estrés de costos (criterio 8) solo se mide en
  las variantes que pasan el criterio 1; las demás quedan rechazadas por el 1 y su 8 es pendiente.

Puro: sin red y sin disco.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

APPROVED, REJECTED, PENDING = "APROBADA", "RECHAZADA", "PENDIENTE"
# Estado propio de T134: pasa todo lo que se puede medir aquí y solo le falta el criterio 7, el
# prospectivo, cuyo dato nace en T135. No es lo mismo que «pendiente» de algo que no se pudo
# medir, y confundirlos sería presentar como aprobable lo que nadie ha comprobado.
CANDIDATE = "CANDIDATA A T135"
NAMES = {
    1: "ΔE[R] frente a las dos bases, con IC y corregido",
    2: "cociente ganancia/pérdida y profit factor",
    3: "drawdown y CVaR",
    4: "pliegues y años naturales",
    5: "meseta de parámetros y PBO",
    6: "control aleatorio",
    7: "prospectivo en papel (T135)",
    8: "sigue cumpliendo el 1 con el deslizamiento ×1,5",
}


@dataclass(frozen=True)
class Check:
    n: int
    ok: bool | None            # None = pendiente (no se puede juzgar con lo que hay)
    value: str

    def to_json(self) -> dict:
        return {"n": self.n, "name": NAMES[self.n], "ok": self.ok, "value": self.value}


def _c1(deltas: Mapping[str, Mapping], alpha: float, n: int = 1) -> Check:
    """ΔE[R] > 0 frente a M0 **y** a M1, con el IC sobre 0 y el p corregido por Romano-Wolf.

    `n` permite reutilizarlo para el criterio 8, que es el mismo contraste con los costos de
    estrés: si el 1 y el 8 no fueran la misma cuenta, no se podrían comparar."""
    if not deltas:
        return Check(n, None, "sin comparaciones")
    bits, ok = [], True
    for base, d in deltas.items():
        lo = (d.get("ci") or [None, None])[0]
        p = d.get("p_rw")
        good = (d.get("delta") is not None and d["delta"] > 0 and lo is not None
                and lo == lo and lo > 0 and p is not None and p < alpha)
        ok = ok and good
        bits.append(f"{base}: Δ {_n(d.get('delta'))}, IC inf {_n(lo)}, "
                    f"p_RW {_n(p, 4)}{'' if good else ' ✗'}")
    return Check(n, ok, "; ".join(bits))


def _c2(m: Mapping, bases: Mapping[str, Mapping], pf_min: float, ratio_min: float) -> Check:
    ratio, pf = m.get("win_loss_ratio"), m.get("pf")
    if ratio is None or pf is None:
        return Check(2, None, "sin cociente o sin PF")
    need = [b.get("pf") for b in bases.values() if b.get("pf") is not None]
    worst = max(need) * pf_min if need else None
    ok = ratio >= ratio_min and (worst is None or pf >= worst)
    return Check(2, ok, f"cociente {_n(ratio, 2)} (≥ {ratio_min:g}), PF {_n(pf, 3)}"
                 + ("" if worst is None else f" (≥ {worst:.3f} = {pf_min:g}× la peor base)"))


def _c3(m: Mapping, bases: Mapping[str, Mapping], dd_max: float) -> Check:
    dd, cv = m.get("max_dd_r"), m.get("cvar95_r")
    if dd is None or cv is None:
        return Check(3, None, "sin drawdown o sin CVaR")
    dds = [b["max_dd_r"] for b in bases.values() if b.get("max_dd_r") is not None]
    cvs = [b["cvar95_r"] for b in bases.values() if b.get("cvar95_r") is not None]
    lim = min(dds) * dd_max if dds else None
    floor = max(cvs) if cvs else None               # «no peor» = no más negativo que la mejor base
    ok = (lim is None or dd <= lim) and (floor is None or cv >= floor)
    return Check(3, ok, f"DD {_n(dd, 1)} R"
                 + ("" if lim is None else f" (≤ {lim:.1f})")
                 + f", CVaR {_n(cv)}" + ("" if floor is None else f" (≥ {floor:+.4f})"))


def _c4(folds: Sequence[float | None], years: Mapping[str, float | None],
        frac_min: float) -> Check:
    seen = [x for x in folds if x is not None]
    if not seen or not years:
        return Check(4, None, "sin pliegues o sin años")
    pos = sum(1 for x in seen if x > 0)
    frac = pos / len(seen)
    bad_years = [y for y, v in years.items() if v is None or v <= 0]
    ok = frac >= frac_min and not bad_years
    return Check(4, ok, f"{pos}/{len(seen)} pliegues con Δ > 0 (≥ {frac_min:.0%})"
                 + ("; todos los años positivos" if not bad_years
                    else f"; años que fallan: {', '.join(bad_years)}"))


def _c5(plateau: bool | None, pbo: float | None, pbo_max: float) -> Check:
    if plateau is None or pbo is None:
        return Check(5, None, f"meseta {plateau}, PBO {pbo}")
    ok = bool(plateau) and pbo < pbo_max
    return Check(5, ok, f"meseta {'sí' if plateau else 'NO'}, PBO {pbo:.2f} (< {pbo_max:g})")


def _c6(control: Mapping | None) -> Check:
    if not control or control.get("ok") is None:
        return Check(6, None, "sin control medido" if not control else control.get("reason", ""))
    return Check(6, bool(control["ok"]), control.get("reason", ""))


def _c8(stress: Mapping | None, alpha: float) -> Check:
    """El criterio 1 repetido con el deslizamiento de los stops ×1,5 (E4a)."""
    if not stress:
        return Check(8, None, "no se midió (solo se mide si pasa el criterio 1)")
    return _c1(stress, alpha, n=8)


@dataclass(frozen=True)
class Verdict:
    variant: str
    family: str
    status: str
    reason: str
    checks: tuple[Check, ...]

    def to_json(self) -> dict:
        return {"variant": self.variant, "family": self.family, "status": self.status,
                "reason": self.reason, "checks": [c.to_json() for c in self.checks]}


def judge(variant: str, family: str, m: Mapping, bases: Mapping[str, Mapping],
          deltas: Mapping[str, Mapping], fold_deltas: Sequence[float | None],
          years: Mapping[str, float | None], plateau: bool | None, pbo: float | None,
          control: Mapping | None, stress: Mapping | None, accept) -> Verdict:
    """Veredicto de una variante con los ocho criterios. `accept` es el bloque del pre-registro."""
    alpha = 0.05
    checks = (
        _c1(deltas, alpha),
        _c2(m, bases, accept.pf_vs_base_min, accept.win_loss_ratio_min),
        _c3(m, bases, accept.max_dd_vs_base_max),
        _c4(fold_deltas, years, accept.folds_positive_frac_min),
        _c5(plateau, pbo, accept.pbo_max),
        _c6(control),
        Check(7, None, f"se mide en T135: ≥ {accept.prospective_weeks_min} semanas en papel con "
                       "la potencia calculada (E9)"),
        _c8(stress, alpha),
    )
    failed = [c.n for c in checks if c.ok is False]
    pend = [c.n for c in checks if c.ok is None]
    if failed:
        status = REJECTED
        reason = "falla el criterio " + ", ".join(f"{n} ({NAMES[n]})" for n in failed)
    elif pend == [7]:
        status = CANDIDATE
        reason = ("cumple los siete criterios medibles aquí; solo le falta el 7, el prospectivo, "
                  "que se mide en papel en T135")
    elif pend:
        status = PENDING
        reason = "pendiente del criterio " + ", ".join(f"{n} ({NAMES[n]})" for n in pend)
    else:
        status = APPROVED
        reason = "cumple los ocho criterios de §5.4"
    return Verdict(variant, family, status, reason, checks)


def _n(x, k: int = 4) -> str:
    return "—" if x is None or x != x else f"{x:+.{k}f}"
