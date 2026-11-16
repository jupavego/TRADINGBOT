"""Reglas nativas del agente `technical` (multi-marco, familias de indicadores). Puras."""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, num, sign, steady

M = "metrics."
B1, B4, BD = M + "frames.1h.bias", M + "frames.4h.bias", M + "frames.1d.bias"
ADX, RSI, WIDTH = M + "regime.adx", M + "votes.RSI", M + "regime.width_pct"
TREND, VOLUME = M + "families.tendencia", M + "families.volumen"
EXPOSES = frozenset({B1, B4, BD, M + "regime.label", ADX, RSI, TREND, VOLUME, WIDTH})


def _vote(fam: object) -> float | None:
    """Voto de una familia (el contexto guarda sus campos simples: `vote`, `weight`)."""
    return num(fam.get("vote")) if isinstance(fam, dict) else None


def tec_acuerdo_marcos(v: View, p: dict) -> Signal:
    """Los sesgos de 1 h, 4 h y 1 d pasan todos de ±mtf_neutral en el mismo sentido."""
    bs = [num(v.get(k)) for k in (B1, B4, BD)]
    if any(b is None for b in bs):
        return steady(0)
    th = float(p["mtf_neutral"])
    return steady(1 if all(b > th for b in bs) else -1 if all(b < -th for b in bs) else 0)


def tec_rsi_rango(v: View, p: dict) -> Signal:
    """Con ADX < adx_range: el voto del RSI deja la sobreventa (largo) o la sobrecompra (corto).
    El voto es > 0 dentro de la sobreventa y < 0 dentro de la sobrecompra (`technical/rules.py`)."""
    adx, r, r0 = num(v.get(ADX)), num(v.get(RSI)), num(v.get(RSI, 1))
    if adx is None or r is None or r0 is None or adx >= float(p["adx_range"]):
        return NONE
    return Signal(enter=1 if r0 > 0 >= r else -1 if r0 < 0 <= r else 0)


def tec_ruptura_volumen(v: View, p: dict) -> Signal:
    """Con ADX ≥ adx_trend, las familias tendencia y volumen votan el mismo signo."""
    adx, t, vol = num(v.get(ADX)), _vote(v.get(TREND)), _vote(v.get(VOLUME))
    if adx is None or adx < float(p["adx_trend"]):
        return NONE
    s = sign(t)
    return Signal(enter=s if s and s == sign(vol) else 0)


def tec_compresion_bb(v: View, p: dict) -> Signal:
    """El ancho de banda (percentil en su ventana) sale de ≤ squeeze_pct: signo de la tendencia."""
    w, w0 = num(v.get(WIDTH)), num(v.get(WIDTH, 1))
    if w is None or w0 is None:
        return NONE
    sq = float(p["squeeze_pct"])
    return Signal(enter=sign(_vote(v.get(TREND)))) if w0 <= sq < w else NONE


RULES = {"tec_acuerdo_marcos": tec_acuerdo_marcos, "tec_rsi_rango": tec_rsi_rango,
         "tec_ruptura_volumen": tec_ruptura_volumen, "tec_compresion_bb": tec_compresion_bb}
