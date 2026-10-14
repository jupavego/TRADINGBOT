"""Reglas de voto: cada indicador del catálogo (T34) → serie de votos −1..+1 (NaN = sin dato).

Las reglas son vectoriales y causales (el voto en `t` usa solo datos ≤ `t`): el agente toma el
último valor y `eim.analytics.technical_ic` mide la serie completa. Cada regla devuelve también
una frase con los valores de la última vela (evidencia).

Reglas (umbrales en `RuleParams`):
- MA/EMA/WMA: ½·media(signo(cierre − línea)) + ½·orden de las líneas (7>25>99 = +1).
- SAR: signo(cierre − SAR). SUPER: dirección (+1/−1).
- DMI: (PDI − MDI)/(PDI + MDI) · min(1, ADX/adx_full).
- MACD: ½·signo(DIF) + ½·signo(histograma). MTM/TRIX: ½·signo(línea) + ½·signo(línea − su media).
- Osciladores (RSI-12, KDJ-K, StochRSI-K, WR, CCI, MFI): fuera de la zona de sobrecompra/sobreventa
  votan en contra del extremo (proporcional a la penetración); dentro de la zona, 0. RSI suma
  divergencias: nuevo máximo de precio sin máximo del RSI → −divergence_weight (simétrico).
- BOLL: reversión a la media según %b: −clip(2·(%b − ½)) (banda superior → −1, inferior → +1).
- VOL: signo(cambio de cierre en vol_lookback) · (1 si MA5 > MA10, ½ si no).
- OBV/EMV: ½·signo(línea − su media) + ½·signo(pendiente o nivel).
- VWAP: (cierre − VWAP)/(atr_scale·ATR), recortado a ±1.
- BS.Vol / Delta: desequilibrio agresor Σ(buy − sell)/ΣV en la ventana · flow_gain.
- TakerRatio: ln(Σbuy/Σsell) · flow_gain/2. CVD: ½·signo(ΔCVD) + ½·divergencia con el precio.
No votan (sin dirección o nivel arbitrario): ATR (régimen/escala), TradeSize, AVL (depende del
inicio de la carga), Basis (lo consume el agente `derivatives`; sin klines de índice).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from eim.agents.technical.params import RuleParams
from eim.indicators import compute
from eim.indicators._core import rolling_max, rolling_min, rolling_sum, shift

NO_VOTE: dict[str, str] = {
    "ATR": "sin dirección: se usa para escala y régimen",
    "TradeSize": "sin dirección (tamaño medio por operación)",
    "AVL": "nivel acumulado desde la primera vela cargada: depende del inicio de la carga",
    "Basis": "lo consume el agente derivatives; sin klines de índice en el snapshot",
}


@dataclass
class Ctx:
    """Arreglos de velas + caché de indicadores para un marco."""

    data: dict[str, np.ndarray]
    rp: RuleParams
    _cache: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)

    def ind(self, indicator_id: str) -> dict[str, np.ndarray]:
        if indicator_id not in self._cache:
            self._cache[indicator_id] = compute(indicator_id, self.data)
        return self._cache[indicator_id]

    @property
    def close(self) -> np.ndarray:
        return self.data["close"]


RuleFn = Callable[[Ctx], tuple[np.ndarray, str]]


@dataclass(frozen=True)
class Rule:
    id: str  # id del indicador en el catálogo
    family: str
    fn: RuleFn


def _keep_nan(v: np.ndarray, *srcs: np.ndarray) -> np.ndarray:
    bad = np.zeros(len(v), dtype=bool)
    for s in srcs:
        bad |= np.isnan(s)
    return np.where(bad, np.nan, v)


def _f(x: float, fmt: str = ".2f") -> str:
    return "n/d" if np.isnan(x) else format(x, fmt)


def zone(x: np.ndarray, ob: float, os_: float, lo: float, hi: float) -> np.ndarray:
    """Voto de oscilador: sobrecompra → negativo, sobreventa → positivo, 0 dentro de la zona."""
    with np.errstate(invalid="ignore"):
        v = np.where(x > ob, -(x - ob) / (hi - ob), np.where(x < os_, (os_ - x) / (os_ - lo), 0.0))
    return _keep_nan(np.clip(v, -1, 1), x)


def divergence(close: np.ndarray, osc: np.ndarray, n: int) -> np.ndarray:
    """−1: nuevo máximo de precio sin máximo del oscilador; +1: lo simétrico; 0 si no."""
    pmax, pmin = shift(rolling_max(close, n), 1), shift(rolling_min(close, n), 1)
    omax, omin = shift(rolling_max(osc, n), 1), shift(rolling_min(osc, n), 1)
    with np.errstate(invalid="ignore"):
        bear = (close > pmax) & (osc < omax)
        bull = (close < pmin) & (osc > omin)
    return _keep_nan(np.where(bear, -1.0, np.where(bull, 1.0, 0.0)), close, osc, pmax, omax)


def _lines(indicator_id: str) -> RuleFn:
    def fn(ctx: Ctx) -> tuple[np.ndarray, str]:
        lines = list(ctx.ind(indicator_id).values())
        c = ctx.close
        pos = np.mean([np.sign(c - x) for x in lines], axis=0)
        order = np.mean([np.sign(a - b) for a, b in zip(lines, lines[1:], strict=False)], axis=0)
        v = 0.5 * pos + 0.5 * order
        above = sum(int(c[-1] > x[-1]) for x in lines)
        return v, f"precio sobre {above}/{len(lines)} líneas, orden {order[-1]:+.1f}"
    return fn


def _sar(ctx: Ctx) -> tuple[np.ndarray, str]:
    s = ctx.ind("SAR")["sar"]
    return np.sign(ctx.close - s), f"SAR {_f(s[-1])} vs cierre {_f(ctx.close[-1])}"


def _super(ctx: Ctx) -> tuple[np.ndarray, str]:
    o = ctx.ind("SUPER")
    return o["dir"].copy(), f"dirección {_f(o['dir'][-1], '+.0f')}, línea {_f(o['st'][-1])}"


def _dmi(ctx: Ctx) -> tuple[np.ndarray, str]:
    o = ctx.ind("DMI")
    p, m, a = o["pdi"], o["mdi"], o["adx"]
    with np.errstate(invalid="ignore", divide="ignore"):
        v = (p - m) / (p + m) * np.minimum(1.0, a / ctx.rp.adx_full)
    return v, f"PDI {_f(p[-1], '.1f')} / MDI {_f(m[-1], '.1f')}, ADX {_f(a[-1], '.1f')}"


def _two_sign(indicator_id: str, line: str, ref: str) -> RuleFn:
    def fn(ctx: Ctx) -> tuple[np.ndarray, str]:
        o = ctx.ind(indicator_id)
        x, y = o[line], o[ref]
        v = _keep_nan(0.5 * np.sign(x) + 0.5 * np.sign(x - y), x, y)
        return v, f"{line.upper()} {_f(x[-1], '.4g')} vs {ref.upper()} {_f(y[-1], '.4g')}"
    return fn


def _macd(ctx: Ctx) -> tuple[np.ndarray, str]:
    o = ctx.ind("MACD")
    v = 0.5 * np.sign(o["dif"]) + 0.5 * np.sign(o["hist"])
    return v, f"DIF {_f(o['dif'][-1], '.4g')}, histograma {_f(o['hist'][-1], '.4g')}"


def _rsi(ctx: Ctx) -> tuple[np.ndarray, str]:
    rp = ctx.rp
    r = ctx.ind("RSI")["rsi12"]
    div_ = divergence(ctx.close, r, rp.divergence_lookback)
    v = np.clip(zone(r, rp.rsi_ob, rp.rsi_os, 0, 100) + rp.divergence_weight * div_, -1, 1)
    tag = {1.0: ", divergencia alcista", -1.0: ", divergencia bajista"}.get(float(div_[-1]), "")
    return v, f"RSI12 {_f(r[-1], '.1f')} (zona {rp.rsi_os:.0f}/{rp.rsi_ob:.0f}){tag}"


def _osc(indicator_id: str, line: str, kind: str) -> RuleFn:
    def fn(ctx: Ctx) -> tuple[np.ndarray, str]:
        rp = ctx.rp
        x = ctx.ind(indicator_id)[line]
        if kind == "wr":
            v, z = zone(x, rp.wr_ob, rp.wr_os, -100, 0), (rp.wr_os, rp.wr_ob)
        elif kind == "cci":
            e = rp.cci_ext
            v, z = zone(x, e, -e, -3 * e, 3 * e), (-e, e)
        else:
            v, z = zone(x, rp.stoch_ob, rp.stoch_os, 0, 100), (rp.stoch_os, rp.stoch_ob)
        return v, f"{line.upper()} {_f(x[-1], '.1f')} (zona {z[0]:.0f}/{z[1]:.0f})"
    return fn


def _boll(ctx: Ctx) -> tuple[np.ndarray, str]:
    o = ctx.ind("BOLL")
    with np.errstate(invalid="ignore", divide="ignore"):
        pb = (ctx.close - o["dn"]) / (o["up"] - o["dn"])
    v = _keep_nan(-np.clip(2 * (pb - 0.5), -1, 1), pb)
    return v, f"%b {_f(pb[-1])} (banda {_f(o['dn'][-1])}–{_f(o['up'][-1])})"


def _vol(ctx: Ctx) -> tuple[np.ndarray, str]:
    o = ctx.ind("VOL")
    k = ctx.rp.vol_lookback
    chg = ctx.close - shift(ctx.close, k)
    conf = np.where(o["ma5"] > o["ma10"], 1.0, 0.5)
    v = _keep_nan(np.sign(chg) * conf, chg, o["ma5"], o["ma10"])
    ratio = o["ma5"][-1] / o["ma10"][-1]
    return v, f"cambio {k} velas {_f(chg[-1], '+.4g')}, MA5/MA10 vol {_f(ratio)}"


def _obv(ctx: Ctx) -> tuple[np.ndarray, str]:
    o = ctx.ind("OBV")
    x, m = o["obv"], o["maobv"]
    slope = x - shift(x, ctx.rp.vol_lookback)
    v = _keep_nan(0.5 * np.sign(x - m) + 0.5 * np.sign(slope), m, slope)
    side = "sobre" if x[-1] > m[-1] else "bajo"
    return v, f"OBV {side} su media 30, pendiente {_f(slope[-1], '+.4g')}"


def _vwap(ctx: Ctx) -> tuple[np.ndarray, str]:
    w = ctx.ind("VWAP")["vwap"]
    a = ctx.ind("ATR")["atr"]
    with np.errstate(invalid="ignore", divide="ignore"):
        v = np.clip((ctx.close - w) / (ctx.rp.atr_scale * a), -1, 1)
    return v, f"VWAP diario {_f(w[-1])} vs cierre {_f(ctx.close[-1])}"


def _imbalance(ctx: Ctx, n: int) -> np.ndarray:
    d = ctx.ind("Delta")["delta"]
    with np.errstate(invalid="ignore", divide="ignore"):
        return rolling_sum(d, n) / rolling_sum(ctx.data["volume"], n)


def _bsvol(ctx: Ctx) -> tuple[np.ndarray, str]:
    n = ctx.rp.flow_window
    imb = _imbalance(ctx, n)
    txt = f"desequilibrio agresor {n} velas {_f(imb[-1], '+.3f')}"
    return np.clip(ctx.rp.flow_gain * imb, -1, 1), txt


def _delta(ctx: Ctx) -> tuple[np.ndarray, str]:
    n = ctx.rp.delta_window
    imb = _imbalance(ctx, n)
    txt = f"delta {n} velas / volumen {_f(imb[-1], '+.3f')}"
    return np.clip(ctx.rp.flow_gain * imb, -1, 1), txt


def _taker_ratio(ctx: Ctx) -> tuple[np.ndarray, str]:
    n = ctx.rp.flow_window
    r = compute("TakerRatio", ctx.data, n=n)["takerratio"]
    with np.errstate(invalid="ignore", divide="ignore"):
        v = np.clip(np.log(r) * ctx.rp.flow_gain / 2, -1, 1)
    return v, f"compra/venta agresora {n} velas {_f(r[-1], '.3f')}"


def _cvd(ctx: Ctx) -> tuple[np.ndarray, str]:
    n = ctx.rp.flow_window
    c = ctx.ind("CVD")["cvd"]
    slope = c - shift(c, n)
    div_ = divergence(ctx.close, c, n)
    v = _keep_nan(np.clip(0.5 * np.sign(slope) + 0.5 * div_, -1, 1), slope, div_)
    return v, f"ΔCVD {n} velas {_f(slope[-1], '+.4g')}"


RULES: dict[str, Rule] = {r.id: r for r in (
    Rule("MA", "tendencia", _lines("MA")),
    Rule("EMA", "tendencia", _lines("EMA")),
    Rule("WMA", "tendencia", _lines("WMA")),
    Rule("SAR", "tendencia", _sar),
    Rule("SUPER", "tendencia", _super),
    Rule("DMI", "tendencia", _dmi),
    Rule("MACD", "momentum", _macd),
    Rule("MTM", "momentum", _two_sign("MTM", "mtm", "mamtm")),
    Rule("TRIX", "momentum", _two_sign("TRIX", "trix", "matrix")),
    Rule("RSI", "momentum", _rsi),
    Rule("KDJ", "momentum", _osc("KDJ", "k", "stoch")),
    Rule("StochRSI", "momentum", _osc("StochRSI", "k", "stoch")),
    Rule("WR", "momentum", _osc("WR", "wr", "wr")),
    Rule("CCI", "momentum", _osc("CCI", "cci", "cci")),
    Rule("BOLL", "volatilidad", _boll),
    Rule("VOL", "volumen", _vol),
    Rule("OBV", "volumen", _obv),
    Rule("MFI", "volumen", _osc("MFI", "mfi", "stoch")),
    Rule("EMV", "volumen", _two_sign("EMV", "emv", "maemv")),
    Rule("VWAP", "volumen", _vwap),
    Rule("BS.Vol", "flujo", _bsvol),
    Rule("Delta", "flujo", _delta),
    Rule("TakerRatio", "flujo", _taker_ratio),
    Rule("CVD", "flujo", _cvd),
)}


def evaluate(ctx: Ctx, rules: dict[str, Rule]) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    """Serie de votos y descripción de la última vela por regla (en el orden de `rules`)."""
    votes: dict[str, np.ndarray] = {}
    info: dict[str, str] = {}
    for rid, rule in rules.items():
        v, txt = rule.fn(ctx)
        votes[rid] = np.clip(np.asarray(v, dtype=float), -1, 1)
        info[rid] = txt
    return votes, info
