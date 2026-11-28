"""T222: ¿sale 15 m de la mesa principal? La regla congelada del pre-registro, en código puro.

La regla es la de `PLAN/T222.md` §3 (huella `PREREG_SHA256`; `tests/analytics/test_tf_retire.py`
falla si el bloque cambia). Este módulo no lee red ni disco: recibe filas del libro fijo (con
`machine` si se conoce, T196) y devuelve el veredicto de una mirada.

Interpretaciones de lo que el bloque no precisa, declaradas el 2026-11-28, antes de la primera
mirada (2027-02-28) y sin haber leído ninguna operación del tramo de prueba:
- Los días son días UTC del cierre (`exit_t`). D cuenta los días con algún cierre de cualquier marco
  medido (15 m, 1 h o 4 h); un día sin cierres de un grupo aporta 0 a su suma.
- «Mitades con el mismo número de días»: con D impar, el día central no entra en ninguna de las dos.
  Una mitad sin operaciones de 15 m o sin 1 h + 4 h no cumple el signo.
- «Tramo posterior al último cambio de régimen»: las operaciones abiertas en ese instante o después.
  Solo cuentan los cambios dentro de `[T0_MS, mirada)`.
- En la 2.ª mirada, sin operaciones en algún grupo no se puede pasar: NO PASA.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import NormalDist

from eim.paper import accounting, universe

T0_MS = 1795824000000                       # 2026-11-28 00:00 UTC: inicio del tramo de prueba
LOOKS_MS = {1: 1803772800000,               # 2027-02-28 00:00 UTC
            2: 1811462400000}               # 2027-05-28 00:00 UTC (tope de 6 meses)
DAY_MS = 86_400_000
ALPHA = 0.05
N_LOOKS = 2
MIN_FAMILY = 1142                           # familia ampliada de Holm el 2026-11-28 con T222
MIN_15, MIN_REST, MIN_DAYS = 600, 600, 60   # mínimo para decidir en la 1.ª mirada
REGIME_MIN = 100                            # operaciones de 15 m para exigir el tramo vigente
SYMBOL, TF, REST = "BTCUSDT", "15m", ("1h", "4h")
PASS, FAIL, OPEN = "PASA", "NO PASA", "EN CURSO"
PREREG_SHA256 = "511e9e3796ba064a9991a521814e908e87a36a5b8e0fb88ec86dc83f3401f7e3"
_START, _END = "<!-- T222-prereg:inicio", "<!-- T222-prereg:fin"


def prereg_fingerprint(text: str) -> str:
    """SHA-256 del bloque congelado de `PLAN/T222.md`, con finales de línea LF (§3)."""
    t = text.replace("\r", "")
    return hashlib.sha256(t[t.index(_START):t.index(_END)].encode()).hexdigest()


def num(x: object) -> float | None:
    """Número o None: el CSV del libro trae cadenas y `''` donde la base tiene NULL."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def z_crit(m: int) -> float:
    """Umbral de z (unilateral): Φ⁻¹(1 − α / (miradas · m)), con m la familia del día."""
    if m < MIN_FAMILY:
        raise ValueError(f"la familia de Holm no puede ser menor que {MIN_FAMILY} (dada {m})")
    return NormalDist().inv_cdf(1 - ALPHA / (N_LOOKS * m))


def guard(look: int, now_ms: int) -> None:
    """Nada se calcula antes de la fecha de la mirada: el tramo de prueba no se mira antes."""
    if look not in LOOKS_MS:
        raise ValueError(f"mirada desconocida: {look} (válidas: {sorted(LOOKS_MS)})")
    if now_ms < LOOKS_MS[look]:
        raise PermissionError(f"la mirada {look} no se puede calcular antes de su fecha "
                              f"({LOOKS_MS[look]} ms); ahora es {now_ms} ms")


def measured(rows: Iterable[Mapping], look: int) -> list[Mapping]:
    """Lo que cuenta (T144) en BTCUSDT, 15 m, 1 h y 4 h, abierto desde T0 y cerrado antes de la mirada."""
    t1 = LOOKS_MS[look]
    opened = [r for r in rows if r.get("symbol") == SYMBOL
              and r.get("timeframe") in (TF, *REST)
              and (t := num(r.get("opened_t"))) is not None and T0_MS <= t < t1]
    return universe.result_rows(accounting.window(opened, T0_MS, t1))


def day_of(r: Mapping) -> int:
    return int((num(r.get("exit_t")) or 0) // DAY_MS)


def r_of(r: Mapping) -> float:
    return num(r.get("r")) or 0.0


@dataclass(frozen=True)
class Estimate:
    """Medias de 15 m y del resto, su diferencia y los errores típicos robustos por día."""

    n15: int
    n_rest: int
    days: int
    mu15: float | None
    mu_rest: float | None
    delta: float | None
    se15: float | None
    se_delta: float | None

    @property
    def z15(self) -> float | None:
        return self.mu15 / self.se15 if self.mu15 is not None and self.se15 else None

    @property
    def z_delta(self) -> float | None:
        return self.delta / self.se_delta if self.delta is not None and self.se_delta else None

    def negative(self) -> bool:
        return (self.mu15 is not None and self.delta is not None
                and self.mu15 < 0 and self.delta < 0)

    def to_json(self) -> dict:
        return {"n15": self.n15, "n_rest": self.n_rest, "days": self.days, "mu15": self.mu15,
                "mu_rest": self.mu_rest, "delta": self.delta, "se15": self.se15,
                "se_delta": self.se_delta, "z15": self.z15, "z_delta": self.z_delta}


def estimate(kept: Sequence[Mapping]) -> Estimate:
    """§3.3: μ̂ = S/N por grupo y ET² = D/(D−1)·Σ_d e_d², con los dos grupos en el mismo día."""
    by: dict[int, list[float]] = {}
    for r in kept:
        g = by.setdefault(day_of(r), [0.0, 0, 0.0, 0])
        k = 0 if r.get("timeframe") == TF else 2
        g[k] += r_of(r)
        g[k + 1] += 1
    days = len(by)
    n15 = sum(int(g[1]) for g in by.values())
    nr = sum(int(g[3]) for g in by.values())
    mu15 = sum(g[0] for g in by.values()) / n15 if n15 else None
    mur = sum(g[2] for g in by.values()) / nr if nr else None
    delta = mu15 - mur if mu15 is not None and mur is not None else None
    se15 = se_d = None
    if days > 1 and mu15 is not None:
        c = days / (days - 1)
        e15 = [(g[0] - mu15 * g[1]) / n15 for g in by.values()]
        se15 = math.sqrt(c * sum(e * e for e in e15))
        if mur is not None:
            ed = [a - (g[2] - mur * g[3]) / nr for a, g in zip(e15, by.values(), strict=True)]
            se_d = math.sqrt(c * sum(e * e for e in ed))
    return Estimate(n15, nr, days, mu15, mur, delta, se15, se_d)


def halves(kept: Sequence[Mapping]) -> tuple[Estimate, Estimate]:
    """Las dos mitades por días con cierres (con D impar, el día central queda fuera)."""
    days = sorted({day_of(r) for r in kept})
    h = len(days) // 2
    first, second = set(days[:h]), set(days[len(days) - h:])
    return (estimate([r for r in kept if day_of(r) in first]),
            estimate([r for r in kept if day_of(r) in second]))


def regime_tail(kept: Sequence[Mapping], changes: Iterable[int], look: int
                ) -> tuple[int | None, Estimate | None]:
    """El tramo vigente: lo abierto desde el último cambio de régimen dentro de la ventana."""
    inside = [int(c) for c in changes if T0_MS <= int(c) < LOOKS_MS[look]]
    if not inside:
        return None, None
    last = max(inside)
    return last, estimate([r for r in kept if (num(r.get("opened_t")) or 0) >= last])


def verdict(rows: Iterable[Mapping], look: int, m: int, changes: Iterable[int] = ()) -> dict:
    """El veredicto de una mirada según §3.5. No comprueba la fecha: eso es `guard`."""
    zc = z_crit(m)
    kept = measured(rows, look)
    est = estimate(kept)
    h1, h2 = halves(kept)
    change, tail = regime_tail(kept, changes, look)
    tail_applies = tail is not None and tail.n15 >= REGIME_MIN
    checks = {
        "z15": est.z15 is not None and est.z15 <= -zc,
        "z_delta": est.z_delta is not None and est.z_delta <= -zc,
        "halves": h1.negative() and h2.negative(),
        "regime": (not tail_applies) or tail.negative(),
    }
    minimum = est.n15 >= MIN_15 and est.n_rest >= MIN_REST and est.days >= MIN_DAYS
    passed = all(checks.values())
    if look == 1 and not minimum:
        status, why = OPEN, "sin el mínimo de la 1.ª mirada"
    elif passed:
        status, why = PASS, "las tres condiciones de §3.5"
    elif look == 1 and (est.mu15 is None or est.delta is None
                        or est.mu15 >= 0 or est.delta >= 0):
        status, why = FAIL, "futilidad en la 1.ª mirada (μ̂₁₅ ≥ 0 o Δ̂ ≥ 0)"
    elif look == 1:
        status, why = OPEN, "ni pasa ni para por futilidad"
    else:
        status, why = FAIL, "la 2.ª mirada no pasa"
    return {"look": look, "look_ms": LOOKS_MS[look], "t0_ms": T0_MS, "family_m": m,
            "z_crit": zc, "status": status, "why": why, "minimum_met": minimum,
            "checks": checks, "estimate": est.to_json(),
            "halves": [h1.to_json(), h2.to_json()],
            "regime": {"last_change_ms": change, "applies": tail_applies,
                       "tail": tail.to_json() if tail else None},
            "counted": len(kept), "counted_digest": accounting.digest(kept),
            "prereg_sha256": PREREG_SHA256}
