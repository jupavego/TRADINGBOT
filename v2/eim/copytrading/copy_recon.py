"""Reconciliación de la copia (puro): posición propia vs objetivo, cada diferencia explicada.

Objetivo de una moneda = posición REAL del líder (foto del exchange) × proporción del viaje
(0 si el viaje está excluido o sin proporción). Dos fuentes de divergencia:
1. El líder no está donde la copia cree (señales perdidas): la foto ≠ lo visto en señales.
2. La posición propia ≠ objetivo más allá de la tolerancia (un paso, el mínimo del exchange
   o `recon_tol_frac` del objetivo) sin un motivo registrado (`CoinCopy.note`: tope,
   deslizamiento, mínimo, veto de riesgo…).
Una señal pendiente de ejecutar explica cualquier diferencia de su moneda. Lo no explicado
lo decide el motor (pausa + alerta tras `recon_confirm` comprobaciones seguidas): aquí
nunca se propone operar para «arreglarlo».
"""

from __future__ import annotations

from typing import Literal

from eim.copytrading.copy_params import CopyParams, ExchangeSpec
from eim.copytrading.replicator import CoinCopy, same
from eim.core.market import Frozen

Status = Literal["ok", "explicada", "no_explicada"]


class ReconDiff(Frozen):
    coin: str
    leader_seen: float  # posición del líder según las señales procesadas
    leader_real: float  # foto del exchange
    own: float
    target: float
    diff_usd: float
    status: Status
    why: str = ""


class Recon(Frozen):
    t: int
    ok: bool  # sin diferencias no explicadas
    checked: int
    diffs: list[ReconDiff] = []  # solo monedas con diferencia

    @property
    def unexplained(self) -> list[ReconDiff]:
        return [d for d in self.diffs if d.status == "no_explicada"]


def _fmt(x: float) -> str:
    return f"{x:+.6g}"


def reconcile(t: int, coins: dict[str, CoinCopy], own: dict[str, float],
              photo: dict[str, float], pending: set[str], marks: dict[str, float],
              spec: ExchangeSpec, p: CopyParams) -> Recon:
    diffs: list[ReconDiff] = []
    names = sorted(set(coins) | {c for c, v in own.items() if v} | set(photo))
    for coin in names:
        c = coins.get(coin) or CoinCopy(coin)
        seen, real, mine = c.leader, photo.get(coin, 0.0), own.get(coin, 0.0)
        px = marks.get(coin) or c.leader_entry or 1.0
        leader_ok = same(seen, real)
        target = c.target(real)
        diff_usd = abs(mine - target) * px
        tol = max(spec.min_notional, p.recon_tol_frac * abs(target) * px,
                  (spec.step(coin) or 0.0) * px)
        if leader_ok and diff_usd <= tol:
            continue
        if coin in pending:
            status, why = "explicada", "señal del líder pendiente de ejecutar"
        elif not leader_ok:
            status, why = "no_explicada", (f"el líder tiene {_fmt(real)} y la copia vio "
                                           f"{_fmt(seen)}: señal perdida")
        elif c.note:
            status, why = "explicada", c.note
        else:
            status, why = "no_explicada", (f"posición propia {_fmt(mine)} vs objetivo "
                                           f"{_fmt(target)} sin motivo registrado")
        diffs.append(ReconDiff(coin=coin, leader_seen=seen, leader_real=real, own=mine,
                               target=target, diff_usd=diff_usd, status=status, why=why))
    return Recon(t=t, ok=all(d.status != "no_explicada" for d in diffs), checked=len(names),
                 diffs=diffs)
