"""Reglas de T139: de las señales a ideas, por el mismo camino que el catálogo. Puro.

Usa `generate_ideas` con un catálogo propio, así que estas estrategias nunca entran en `CATALOG` ni
generan ideas en vivo. La salida es la de `control_aleatorio` (`atr_draft`), y el contexto es mínimo
(`t`, `close`, `atr`): ninguna regla necesita agentes, y calcularlos antes de 2023 costaría días.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from eim.core import Candle
from eim.data.timeframes import tf_ms
from eim.paper.catalog import generate_ideas
from eim.paper.ideas import Draft, Idea, StrategyInfo, atr_draft
from eim.paper.params import ExecParams
from eim.paper.versioning import exec_fingerprint
from eim.validation.criteria import file_hash
from eim.validation.hypotheses import signals as sg
from eim.validation.hypotheses.prereg import ExitSpec, Hypothesis, Prereg
from eim.validation.lineage import Version, Window, iso_ms

ORIGIN = "T139"
FAMILY = "hipotesis"
ROUND = 6                       # decimales de `paper.context`
CODE_FILES = (Path(__file__), Path(sg.__file__))


@dataclass(frozen=True)
class Series:
    """Velas de un marco como arreglos, con su ATR."""

    tf: str
    bar_ms: int
    candles: Sequence[Candle]
    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    lo: np.ndarray
    c: np.ndarray
    v: np.ndarray
    taker: np.ndarray
    atr: np.ndarray

    @property
    def close_t(self) -> np.ndarray:
        return self.t + self.bar_ms


def series_of(candles: Sequence[Candle], tf: str) -> Series:
    t = np.array([x.t for x in candles], dtype=np.int64)
    o, h, lo, c, v = (np.array([getattr(x, k) for x in candles], dtype=float)
                      for k in ("o", "h", "l", "c", "v"))
    taker = np.array([np.nan if x.taker_buy_v is None else x.taker_buy_v for x in candles],
                     dtype=float)
    return Series(tf, tf_ms(tf), candles, t, o, h, lo, c, v, taker, sg.atr_series(h, lo, c))


@dataclass(frozen=True)
class Minutes:
    """Velas de 1 min como arreglos: solo H4 las necesita."""

    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    lo: np.ndarray
    c: np.ndarray
    v: np.ndarray


def sides_for(h: Hypothesis, s: Series, funding: Sequence[tuple[int, float]],
              minutes: Minutes | None) -> np.ndarray:
    """El lado por vela de una hipótesis en un marco. Falla si no sabe qué regla es."""
    p = h.params
    if h.strategy == "funding_contra":
        ft = np.array([x for x, _ in funding], dtype=np.int64)
        fr = np.array([x for _, x in funding], dtype=float)
        return sg.funding_sides(ft, fr, s.close_t, s.bar_ms, int(p["window_prints"]),
                                p["q_low"], p["q_high"])
    if h.strategy in ("flujo_sigue", "flujo_revierte"):
        window = int(p["window_days"]) * sg.DAY_MS // s.bar_ms
        z = sg.flow_z(s.v, s.taker, int(p["sum_bars"]), window, p["min_coverage"])
        if h.strategy == "flujo_sigue":
            return sg.flow_sides(z, p["z"])
        return sg.reversal_sides(z, s.o, s.c, s.atr, p["z"], p["min_move_atr"])
    if h.strategy == "cascada_revierte":
        if minutes is None:
            raise ValueError("cascada_revierte necesita las velas de 1 min")
        m = minutes
        hits = sg.cascade_minutes(m.t, m.o, m.h, m.lo, m.v, p["q_range"], p["q_volume"],
                                  int(p["window_days"]), p["min_coverage"])
        return sg.cascade_sides(hits, m.t, m.o, m.c, s.t, s.bar_ms)
    if h.strategy == "momento_1d":
        return sg.momentum_sides(s.c, int(p["lookback_bars"]))
    raise ValueError(f"regla desconocida: {h.strategy}")


def info_of(h: Hypothesis, sides: np.ndarray, ex: ExitSpec) -> StrategyInfo:
    """La estrategia de una hipótesis en un marco: su lado ya calculado y la salida del control."""
    sl, tp, conf, hold, why = ex.sl_atr, ex.tp_atr, ex.conf, ex.hold_bars, f"{h.id}: {h.strategy}"

    def fn(ctx: dict, _x: object, i: int) -> Draft | None:
        side = int(sides[i]) if 0 <= i < len(sides) else 0
        return atr_draft(side, ctx, sl, tp, conf, (why,), hold_h=hold)
    return StrategyInfo(h.strategy, h.strategy, FAMILY, h.rule, fn, h.timeframes)


def minimal_ctxs(s: Series) -> list[dict]:
    """Un contexto por vela cerrada, con el redondeo de `paper.context`. Sin ATR, sin decisión."""
    out = []
    for t, c, a in zip(s.close_t, s.c, s.atr, strict=True):
        out.append({"t": int(t), "close": round(float(c), ROUND),
                    "atr": None if not np.isfinite(a) else round(float(a), ROUND), "regime": None})
    return out


def origin_rule(alta_ms: int):
    """`vivo` solo desde el alta: antes de ella la regla no existía, así que es reconstrucción."""
    def of(ctx: dict) -> str:
        return "vivo" if int(ctx["t"]) >= alta_ms else "backtest"
    return of


def ideas_for(h: Hypothesis, s: Series, sides: np.ndarray, pr: Prereg, ep: ExecParams,
              fingerprint_: str) -> list[Idea]:
    """Las ideas de una clave, con su huella y su origen."""
    info = info_of(h, sides, pr.exit)
    got = generate_ideas(minimal_ctxs(s), s.candles, pr.symbol, s.bar_ms,
                         origin_of=origin_rule(iso_ms(pr.live_rule.alta)),
                         catalog={info.id: info}, timeframe=s.tf, exec_params=ep)
    return [replace(i, version=fingerprint_) for i in got]


def exec_params(pr: Prereg, base: ExecParams | None = None) -> ExecParams:
    """La mecánica vigente con el BE+ extendido a 1 d: la misma salida en todos los marcos."""
    return (base or ExecParams()).model_copy(update={"be_timeframes": pr.exit.be_timeframes})


def code_hash() -> str:
    """Huella del código de las reglas: corregir un defecto cambia la huella, no la clave."""
    return hashlib.sha256("".join(file_hash(p.read_bytes()) for p in CODE_FILES).encode()
                          ).hexdigest()


def fingerprint(pr: Prereg, sid: str, ep: ExecParams) -> str:
    """Huella de una versión: pre-registro + código de las reglas + mecánica del marco."""
    blob = {"prereg": pr.sha256, "sid": sid, "code": code_hash(),
            "exec": exec_fingerprint(ep, sid.split("@")[1])}
    return hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()[:12]


def version_of(pr: Prereg, sid: str, ep: ExecParams) -> Version:
    """La versión en el registro: **nace retirada**, como las de T137. Solo cuenta como intento y
    deja registrada su ventana de ajuste; no toca nada de lo que corre en vivo."""
    alta = iso_ms(pr.live_rule.alta)
    strategy, tf = sid.split("@")
    adj = pr.windows.adjust
    win = Window(iso_ms(adj.from_), iso_ms(adj.to), None, adj.note)
    h = pr.hypothesis(strategy)
    return Version(sid, pr.version_n, fingerprint(pr, sid, ep), strategy, tf, alta, None, ORIGIN,
                   f"T139 {h.id}: {pr.version}", alta, (win,))
