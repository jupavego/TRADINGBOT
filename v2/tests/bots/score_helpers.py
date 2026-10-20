"""Mercado y posturas sintéticas para probar la puntuación de bots (T59), sin red."""

from __future__ import annotations

import numpy as np

from eim.bots.card import BotCard, Security, default_cards
from eim.core import BotQuality, BotSignal, Candle
from eim.paper.engine import Path
from eim.validation.criteria import load_criteria

H = 3_600_000
M15 = 900_000
T0 = 1_700_000_000_000 // H * H
SHA = "a" * 40
SYMBOL = "BTCUSDT"
CRIT = load_criteria()


def version(tag: str = "0") -> str:
    return SHA + "+" + (tag * 12)[:12]


class Market:
    """Camino de 15 m con tendencias de horas (±) y velas de 1 h agregadas de él.

    `dirs[k]` = dirección de la hora k. El «oráculo» publica en el cierre de la hora k−1 la
    dirección de la hora k (un bot con ventaja por construcción: el test es de la mecánica, no
    una afirmación sobre bots reales).
    """

    def __init__(self, days: int = 160, seed: int = 3, run_h: tuple[int, int] = (6, 18)) -> None:
        rng = np.random.default_rng(seed)
        n = days * 24
        dirs: list[int] = []
        side = 1
        while len(dirs) < n:
            dirs += [side] * int(rng.integers(*run_h))
            side = -side
        self.dirs = dirs[:n]
        p, c15 = 100.0, []
        for k, d in enumerate(self.dirs):
            for j in range(4):
                o = p
                p = o * float(np.exp(d * 0.0012 + rng.normal(0, 0.0012)))
                c15.append(Candle(t=T0 + k * H + j * M15, o=o, h=max(o, p) * 1.0006,
                                  l=min(o, p) * 0.9994, c=p, v=10.0))
        self.c15 = c15
        self.path = Path(c15)
        self.c1h = [Candle(t=T0 + k * H, o=c15[4 * k].o, h=max(c.h for c in c15[4 * k:4 * k + 4]),
                           l=min(c.l for c in c15[4 * k:4 * k + 4]), c=c15[4 * k + 3].c, v=40.0)
                    for k in range(n)]
        self.end = T0 + n * H

    def regime_at(self, asof: int) -> str:
        return "tendencia" if (asof // (24 * H)) % 2 else "rango"


def signal(asof: int, stance: float, ver: str | None = None, status: str = "ok",
           costs: dict | None = None, bot: str = "hummingbot-directional",
           strategy: str = "s1") -> BotSignal:
    return BotSignal(
        bot_id=bot, strategy=strategy, version=ver or version(), asof=asof, timeframe="1h",
        symbol=SYMBOL, stance=stance if status == "ok" else 0.0,
        confidence=None if status != "ok" else 0.8, costs_assumed=costs, status=status,  # type: ignore[arg-type]
        data_quality=BotQuality(bars=500, last_candle_t=asof - H))


def oracle_rows(m: Market, live_days: int = 45, ver: str | None = None, flip: bool = False,
                costs: dict | None = None) -> list[tuple[BotSignal, int]]:
    """Postura en cada cierre de hora = dirección de la hora siguiente (invertida si `flip`)."""
    out = []
    for k in range(1, len(m.dirs)):
        asof = T0 + k * H
        d = m.dirs[k] * (-1 if flip else 1)
        live = asof >= m.end - live_days * 24 * H
        created = asof + 60_000 if live else asof + 10 * H
        out.append((signal(asof, float(d), ver, costs=costs), created))
    return out


def noise_rows(m: Market, seed: int = 9, ver: str | None = None) -> list[tuple[BotSignal, int]]:
    rng = np.random.default_rng(seed)
    side, out = 1, []
    for k in range(1, len(m.dirs)):
        asof = T0 + k * H
        if rng.random() < 0.08:
            side = -side
        out.append((signal(asof, float(side), ver), asof + 10 * H))
    return out


def card(enabled: bool = True) -> BotCard:
    c = default_cards()["hummingbot-directional"]
    if enabled:
        return c
    sec = Security(checks=c.security.checks, notes=c.security.notes, red_alerts=["prueba"],
                   total=c.security.total, enabled=False)
    return c.model_copy(update={"security": sec})
