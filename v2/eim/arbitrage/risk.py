"""Puntuaciones de riesgo 0..1 (heurísticas declaradas; cada una deja su explicación)."""

from __future__ import annotations

import math

from eim.arbitrage.params import ArbParams
from eim.core import Book, Leg, Risk


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def legging(legs: list[Leg], *, sequential: bool) -> tuple[float, str]:
    """Patas no atómicas: base 0.2 (simultáneas) o 0.5 (secuenciales); +0.3 si alguna recorre
    más de un nivel del libro; 1 si alguna no cabe en el libro visible."""
    opens = [lg for lg in legs if lg.action == "open"]
    if any(not lg.complete for lg in legs):
        return 1.0, "pata incompleta: el libro visible no cubre la cantidad"
    score = 0.5 if sequential else 0.2
    deep = [lg.symbol for lg in opens if lg.levels > 1]
    if deep:
        score += 0.3
    kind = "secuenciales" if sequential else "simultáneas"
    note = f"{len(opens)} patas de entrada {kind}"
    return _clamp(score), note + (f"; recorren varios niveles: {', '.join(deep)}" if deep else "")


def liquidity(used: list[tuple[Leg, Book]]) -> tuple[float, str]:
    """Fracción del libro visible que consume la pata de entrada más exigente."""
    worst, where = 0.0, ""
    for lg, book in used:
        if lg.action != "open":
            continue
        side = book.asks if lg.side == "buy" else book.bids
        depth = sum(q for _, q in side)
        frac = lg.qty / depth if depth > 0 else 1.0
        if frac >= worst:
            worst, where = frac, lg.symbol
    return _clamp(worst), f"la pata {where} consume {worst:.1%} del libro visible"


def liquidation(p: ArbParams, horizon_h: float, *, leveraged: bool) -> tuple[float, str]:
    """Movimiento adverso plausible (`daily_move`·√días) frente a la distancia a liquidación
    de una pata de futuros a `perp_leverage` (1/L − mmr)."""
    if not leveraged:
        return 0.0, "sin patas apalancadas"
    dist = 1.0 / p.perp_leverage - p.mmr
    move = p.daily_move * math.sqrt(max(horizon_h, 1.0) / 24.0)
    return _clamp(move / dist if dist > 0 else 1.0), (
        f"movimiento plausible {move:.1%} en {horizon_h:.0f} h vs liquidación a {dist:.1%} "
        f"(×{p.perp_leverage:g}); reponer margen evita el cierre forzado")


def basis(shock_usd: float, gross: float, note: str, *, floor: float = 0.0) -> tuple[float, str]:
    """Qué parte del bruto borraría un cambio de base de `shock_usd`."""
    score = shock_usd / abs(gross) if abs(gross) > 1e-12 else 1.0
    return _clamp(max(score, floor)), note


def build(leg_r: tuple[float, str], basis_r: tuple[float, str], liq_r: tuple[float, str],
          liqd_r: tuple[float, str]) -> Risk:
    return Risk(legging=leg_r[0], basis=basis_r[0], liquidation=liq_r[0], liquidity=liqd_r[0],
                notes={"legging": leg_r[1], "basis": basis_r[1], "liquidation": liq_r[1],
                       "liquidity": liqd_r[1]})
