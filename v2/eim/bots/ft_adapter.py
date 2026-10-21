"""Adaptador modo B de `freqtrade-strategies` (GPL-3.0, uso privado aprobado en T56).

El código del bot NO se importa desde `eim/`: corre en su propio entorno (Python con freqtrade y
TA-Lib) dentro de `eim/data/bots/runner.py` — sin claves, sin red, con tiempo y memoria acotados —
y devuelve solo banderas por vela (`enter_long/exit_long/enter_short/exit_short`). La postura se
deriva aquí, con la regla de entrada de Freqtrade (`get_entry_signal`): una entrada solo vale si
no choca con la salida ni con la entrada contraria; la posición se mantiene hasta su salida o hasta
una entrada opuesta. Stoploss, ROI y trailing del bot son de ejecución y NO se simulan: la salida
es solo por señal (queda dicho en la evidencia). La versión = SHA de las estrategias + hash de
(estrategia, versión del motor Freqtrade); si el motor instalado difiere, no se acepta la salida.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from eim.bots.adapter import empty_signal, quality_of, version_of
from eim.bots.card import BotCard, card_of
from eim.core import BotQuality, BotSignal, MarketSnapshot
from eim.data.bots.runner import Limits, RunResult, RunSpec, run_isolated
from eim.data.timeframes import tf_ms

BOT_ID = "freqtrade-strategies"
SCRIPT = Path(__file__).resolve().parents[1] / "data" / "bots" / "scripts" / "freqtrade_signal.py"
FUTURES_DIR = "user_data/strategies/futures"
MAX_BARS = 1500  # velas que se entregan al bot (más no cambia el último valor y cuesta tiempo)
NOTE_EXITS = ("salida solo por señal: el stoploss, el ROI y el trailing del bot son de "
              "ejecución y no se simulan")


def positions(flags: dict[str, list[int]], can_short: bool, startup: int) -> list[int]:
    """Postura (+1/0/−1) tras cada vela según las banderas del bot, como `get_entry_signal`.

    Antes de `startup` velas el bot aún no tiene indicadores: postura 0. Función pura de las
    banderas hasta esa vela (no mira el futuro), por lo que truncar las velas no la cambia.
    """
    n = len(flags["enter_long"])
    out, state = [], 0
    for i in range(n):
        el, xl = flags["enter_long"][i] == 1, flags["exit_long"][i] == 1
        es = can_short and flags["enter_short"][i] == 1
        xs = can_short and flags["exit_short"][i] == 1
        if i < startup:
            state = 0
        elif el and not (xl or es):
            state = 1
        elif es and not (xs or el):
            state = -1
        elif (state > 0 and xl) or (state < 0 and xs):
            state = 0
        out.append(state)
    return out


def ft_pair(symbol: str) -> str:
    """BTCUSDT → BTC/USDT:USDT (perpetuo lineal en la nomenclatura de Freqtrade)."""
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    return f"{base}/USDT:USDT"


class FreqtradeAdapter:
    """Modo B: una ejecución aislada por estrategia; un fallo de una no afecta a las otras."""

    bot_id = BOT_ID
    strategy_subdir = FUTURES_DIR    # subcarpeta del checkout con las estrategias
    max_bars = MAX_BARS
    min_startup = 0                  # arranque mínimo propio (informativos largos), en velas
    note_exits = NOTE_EXITS

    def __init__(self, python: Path, checkout: Path, engine_version: str,
                 strategies: tuple[str, ...] = ("FSupertrendStrategy",),
                 limits: Limits | None = None, card: BotCard | None = None,
                 runner: Callable[[RunSpec], RunResult] = run_isolated,
                 script: Path = SCRIPT) -> None:
        self.python, self.checkout = Path(python), Path(checkout).resolve()
        self.engine_version = engine_version
        self.strategies, self.limits, self.runner = strategies, limits or Limits(), runner
        self.script = Path(script)
        self.card = card or card_of(BOT_ID)

    def version(self, strategy: str) -> str:
        # `hyperopt`: desde 2026-10-21 se aplican buy_params/sell_params de la estrategia (antes
        # corría con los valores por defecto de los parámetros): es otra versión del bot
        params = {"strategy": strategy, "engine": self.engine_version, "hyperopt": "aplicado"}
        return version_of(self.card.commit_sha, params)

    def signals(self, snapshot: MarketSnapshot) -> list[BotSignal]:
        return [self._one(snapshot, s) for s in self.strategies]

    def _spec(self, snap: MarketSnapshot, strategy: str, max_bars: int | None = None) -> RunSpec:
        rows = [[c.t, c.o, c.h, c.l, c.c, c.v] for c in snap.candles[-(max_bars or self.max_bars):]]
        return RunSpec(
            python=self.python, script=self.script, limits=self.limits,
            request={"strategy": strategy,
                     "strategy_dir": str(self.checkout / self.strategy_subdir),
                     "timeframe": snap.timeframe, "pair": ft_pair(snap.symbol)},
            files={"candles.json": json.dumps(rows)},
            bot_dir=self.checkout, expected_sha=self.card.commit_sha)

    def _one(self, snap: MarketSnapshot, strategy: str) -> BotSignal:
        ver = self.version(strategy)
        if not snap.candles:
            return empty_signal(self.card, strategy, ver, snap, "no_data", "sin velas")
        res = self.runner(self._spec(snap, strategy))
        if res.status != "ok" or res.output is None:
            return empty_signal(self.card, strategy, ver, snap, "degraded",
                                "; ".join(res.warnings) or "el bot no respondió")
        try:
            return self._parse(snap, strategy, ver, res)
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            return empty_signal(self.card, strategy, ver, snap, "degraded",
                                f"salida del bot inválida: {type(exc).__name__}: {exc}")

    def _parse(self, snap: MarketSnapshot, strategy: str, ver: str, res: RunResult) -> BotSignal:
        out = res.output or {}
        engine = out["engine"]
        if engine != self.engine_version:
            return empty_signal(self.card, strategy, ver, snap, "degraded",
                                f"motor Freqtrade {engine} ≠ el fijado {self.engine_version}")
        flags = {k: [int(x) for x in v] for k, v in out["flags"].items()}
        sent = snap.candles[-self.max_bars:]
        if [int(t) for t in out["times"]] != [c.t for c in sent]:
            raise ValueError("las velas devueltas no coinciden con las enviadas")
        startup = max(int(out["startup_candle_count"]), self.min_startup)
        if len(sent) <= startup:
            return empty_signal(self.card, strategy, ver, snap, "no_data",
                                f"velas insuficientes: {len(sent)} ≤ arranque {startup}",
                                startup + 1)
        pos = positions(flags, bool(out["can_short"]), startup)
        stance = float(pos[-1])
        held = next((k for k in range(len(pos)) if pos[len(pos) - 1 - k] != pos[-1]), len(pos))
        last = {k: v[-1] for k, v in flags.items()}
        net = "con red aislada" if res.network_isolated else "sin aislamiento de red del sistema"
        return BotSignal(
            bot_id=self.card.id, strategy=strategy, version=ver, asof=snap.asof,
            timeframe=snap.timeframe, symbol=snap.symbol, stance=stance, confidence=None,
            evidence=[f"{strategy}: postura {stance:g} (banderas de la última vela {last}; "
                      f"mantenida {held} velas); {self.note_exits}"],
            raw={"flags_last": last, "held_bars": held, "engine": engine,
                 "startup_candle_count": startup, "can_short": bool(out["can_short"]),
                 "run_s": round(res.duration_s, 3), "isolation": net},
            data_quality=quality_of(snap, startup + 1, self.note_exits), status="ok")

    def _run_all(self, snap: MarketSnapshot, strategy: str) -> dict | None:
        """Salida del bot sobre TODAS las velas del snapshot (una corrida); None si falla."""
        res = self.runner(self._spec(snap, strategy, max_bars=len(snap.candles)))
        return res.output if res.status == "ok" else None

    def history(self, snap: MarketSnapshot, strategy: str, from_asof: int) -> list[BotSignal]:
        """Relleno histórico: UNA corrida del bot sobre todas las velas del snapshot y una señal
        por cierre de vela con `asof` ≥ `from_asof` (en vez de una corrida por vela).

        Es equivalente a correr vela a vela solo si el indicador de la estrategia no mira hacia
        adelante: eso lo comprueba `tests/bots/test_ft_adapter.py` (truncar no cambia posturas
        pasadas) y la verificación con el bot real. Falla ⇒ lista vacía (no lanza)."""
        ver = self.version(strategy)
        out = self._run_all(snap, strategy)
        if out is None:
            return []
        try:
            if out["engine"] != self.engine_version:
                return []
            flags = {k: [int(x) for x in v] for k, v in out["flags"].items()}
            cs, step = snap.candles, tf_ms(snap.timeframe)
            if [int(t) for t in out["times"]] != [c.t for c in cs]:
                return []
            startup = max(int(out["startup_candle_count"]), self.min_startup)
            pos = positions(flags, bool(out["can_short"]), startup)
            sigs = []
            for i in range(startup, len(cs)):
                asof = cs[i].t + step
                if asof < from_asof:
                    continue
                last = {k: v[i] for k, v in flags.items()}
                sigs.append(BotSignal(
                    bot_id=self.card.id, strategy=strategy, version=ver, asof=asof,
                    timeframe=snap.timeframe, symbol=snap.symbol, stance=float(pos[i]),
                    confidence=None,
                    evidence=[f"{strategy}: postura {pos[i]:g} (banderas {last}); relleno "
                              f"histórico de una sola corrida; {self.note_exits}"],
                    raw={"flags_last": last, "engine": out["engine"], "backfill": True},
                    data_quality=BotQuality(
                        bars=i + 1, last_candle_t=cs[i].t,
                        source=snap.sources.get("candles", "desconocida"), coverage=1.0,
                        notes=[self.note_exits]),
                    status="ok"))
            return sigs
        except (KeyError, TypeError, ValueError, IndexError):
            return []
