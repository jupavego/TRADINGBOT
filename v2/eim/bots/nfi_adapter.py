"""Adaptador modo B de `nostalgia-for-infinity` (GPL-3.0, uso privado aprobado 2026-10-20).

NFI (`NostalgiaForInfinityX7`) corre en el entorno aparte de Python 3.12 con Freqtrade (el mismo
de `freqtrade-strategies`), dentro del ejecutor aislado, sobre velas de **5 min** que EIM agrega
desde el almacén de 1 min. Un `DataProvider` de mentira (`scripts/nfi_signal.py`) le entrega los
informativos 15m/1h/4h/1d que arma este módulo (solo barras completas, con su propia historia: el
diario de NFI pide ~50 días); sin red ni órdenes. La postura sale de las banderas
`enter_long/exit_long/enter_short/exit_short` con la regla de entrada de Freqtrade
(`ft_adapter.positions`), con `can_short` activo (futuros).

LO QUE UNA POSTURA POR VELA NO PUEDE REPRESENTAR (queda dicho en cada señal): NFI no es solo
«entrar y salir»: reajusta la posición (rebuy/grind = promediado a la baja,
`adjust_trade_position`),
sale por ROI/stoploss/«derisk» según el beneficio de la posición y la modula con el número de
operaciones abiertas. Nada de eso se simula; la postura es el sentido de las banderas de entrada y
salida. Por eso el resultado puntúa «las señales de NFI», no «el sistema NFI completo».

Relleno histórico: NFI sobre 6 meses de 5 min (~53 000 velas) no cabe en una corrida (memoria y
tiempo), así que `history` corre por tramos de `CHUNK` velas con `WARM` velas previas de
arranque y concatena las banderas; cada vela solo ve su pasado, así que el resultado es el mismo
que en una sola corrida (se comprobó con el bot real; ver `docs/BOTS.md`).
"""

from __future__ import annotations

import json
from pathlib import Path

from eim.agents.technical.frame import resample
from eim.bots.card import BotCard, card_of
from eim.bots.ft_adapter import FreqtradeAdapter
from eim.core import Candle, MarketSnapshot
from eim.data.bots.runner import Limits, RunSpec, run_isolated
from eim.data.timeframes import tf_ms

BOT_ID = "nostalgia-for-infinity"
STRATEGY = "NostalgiaForInfinityX7"
SCRIPT = Path(__file__).resolve().parents[1] / "data" / "bots" / "scripts" / "nfi_signal.py"
NFI_DIR_ENV = "EIM_BOT_NFI_DIR"      # checkout de NFI en el SHA de la ficha
WARM = 800                           # `startup_candle_count` de NFI, en velas de 5 min
CHUNK = 3_000                        # velas de 5 min por corrida del relleno
INFO_DAYS = 56                       # historia de los informativos antes de la primera vela
NOTE_EXITS = ("posturas de las banderas de NFI; sus reajustes de posición (rebuy/grind), ROI, "
              "stoploss y «derisk» no caben en una postura por vela y no se simulan")
DAY = 86_400_000


def informatives(base: list[Candle], extra: dict[str, list[Candle]] | None) -> dict[str, list]:
    """Marcos 15m/1h/4h/1d para las velas base: solo barras CERRADAS al cierre de la última vela
    base y con `INFO_DAYS` de historia previa. Usa `extra` ({«15m»,«1h»}) si lo hay; si no, agrega
    de las velas base (el 4h y el 1d salen siempre de la serie de 1 h)."""
    if not base:
        return {}
    extra = extra or {}
    end = base[-1].t + tf_ms("5m")
    start = base[0].t - INFO_DAYS * DAY
    c15 = extra.get("15m") or resample(base, 15 * 60_000)
    c1h = extra.get("1h") or resample(base, 3_600_000)
    frames = {"15m": (c15, 15 * 60_000), "1h": (c1h, 3_600_000)}
    frames["4h"] = (resample(c1h, 4 * 3_600_000), 4 * 3_600_000)
    frames["1d"] = (resample(c1h, DAY), DAY)
    return {tf: [[c.t, c.o, c.h, c.l, c.c, c.v] for c in cs if start <= c.t and c.t + step <= end]
            for tf, (cs, step) in frames.items()}


class NfiAdapter(FreqtradeAdapter):
    bot_id = BOT_ID
    strategy_subdir = ""
    max_bars = WARM + 1_200            # velas de 5 min por corrida en vivo
    note_exits = NOTE_EXITS
    timeframes = ("5m",)
    warm = WARM
    chunk = CHUNK

    def __init__(self, python: Path, checkout: Path, engine_version: str,
                 strategies: tuple[str, ...] = (STRATEGY,), limits: Limits | None = None,
                 card: BotCard | None = None, runner=run_isolated, script: Path = SCRIPT) -> None:
        super().__init__(python, checkout, engine_version, strategies,
                         limits or Limits(timeout_s=1800.0, memory_mb=6144, cpu_s=1800,
                                          max_output_bytes=40_000_000),
                         card or card_of(BOT_ID), runner, script)

    def _spec(self, snap: MarketSnapshot, strategy: str, max_bars: int | None = None) -> RunSpec:
        spec = super()._spec(snap, strategy, max_bars)
        base = snap.candles[-(max_bars or self.max_bars):]
        info = informatives(base, snap.candles_tf)
        return RunSpec(
            python=spec.python, script=spec.script, limits=spec.limits, request=spec.request,
            files={**spec.files, "info.json": json.dumps(info)}, bot_dir=spec.bot_dir,
            expected_sha=spec.expected_sha)

    def _run_all(self, snap: MarketSnapshot, strategy: str) -> dict | None:
        """Corre por tramos y junta las banderas (ver el docstring del módulo)."""
        cs, n = snap.candles, len(snap.candles)
        flags: dict[str, list[int]] = {}
        first: dict | None = None
        for a in range(0, n, self.chunk):
            lo, b = max(0, a - self.warm), min(n, a + self.chunk)
            sub = snap.model_copy(update={"candles": cs[lo:b], "asof": cs[b - 1].t + tf_ms("5m")})
            res = self.runner(self._spec(sub, strategy, b - lo))
            out = res.output
            if res.status != "ok" or out is None:
                return None
            if [int(t) for t in out["times"]] != [c.t for c in cs[lo:b]] \
                    or int(out["startup_candle_count"]) > self.warm:
                return None
            first = first or out
            for k, v in out["flags"].items():
                flags.setdefault(k, [0] * n)[a:b] = [int(x) for x in v[a - lo:]]
        if first is None:
            return None
        return {**first, "times": [c.t for c in cs], "flags": flags,
                "startup_candle_count": self.warm}
