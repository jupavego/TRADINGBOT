"""Carril de simulación de `passivbot` (clase L, modo B; dominio público, Unlicense).

Passivbot gestiona órdenes e inventario (entradas con trailing, reentradas, grid): no tiene una
postura direccional, así que **no es un `SignalAdapter` y nunca vota**. Este adaptador corre su
propio backtester (el mismo motor Rust que usa en vivo) sobre velas de 1 min locales, en un proceso
aislado (`eim/data/bots/runner.py`: sin claves, sin red del bot, SHA fijado, tiempo acotado), y
devuelve una `SimRun`: fills y curva de capital **simulados**. Solo largos, un símbolo.

Costos: la comisión se fija aquí con las tarifas de EIM (`CostParams`, T25) y se declara en
`costs_assumed`; los del README del bot no se aceptan. El motor del bot aplica su propio modelo de
fills y deslizamiento de órdenes a mercado; T59 vuelve a costear los fills con el modelo de T25.
La versión = SHA del bot + hash de (estrategia, configuración, comisiones, saldo, calentamiento).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from eim.backtest.params import CostParams
from eim.bots.adapter import params_hash, version_of
from eim.bots.card import BotCard, card_of
from eim.core import BotQuality, Candle, SimEquityPoint, SimFill, SimRun
from eim.data.bots.runner import Limits, RunResult, RunSpec, run_isolated

BOT_ID = "passivbot"
SCRIPT = Path(__file__).resolve().parents[1] / "data" / "bots" / "scripts" / "passivbot_sim.py"
MINUTE = 60_000
# estrategia → configuración de ejemplo del bot (en el checkout fijado, solo lectura)
CONFIGS = {"trailing_martingale": "configs/examples/btc_long.json",
           "ema_anchor": "configs/examples/ema_anchor.json"}
# Reglas de BTCUSDT perpetuo en Binance (filtros públicos de la bolsa)
MARKET = {"qty_step": 0.001, "price_step": 0.1, "min_qty": 0.001, "min_cost": 100.0}
FILL_FIELDS = ("index", "timestamp", "coin", "pnl", "fee_paid", "usd_total_balance",
               "btc_cash_wallet", "usd_cash_wallet", "btc_price", "qty", "price", "psize",
               "pprice", "type", "liquidity", "wallet_exposure")


def ymd(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d")


class PassivbotSimAdapter:
    """Carril de simulación: `simulate(velas de 1 min)` → `SimRun`. Jamás lanza."""

    bot_id = BOT_ID

    def __init__(self, python: Path, checkout: Path, engine_version: str = "0.1.0",
                 limits: Limits | None = None, card: BotCard | None = None,
                 costs: CostParams | None = None,
                 runner: Callable[[RunSpec], RunResult] = run_isolated,
                 script: Path = SCRIPT) -> None:
        self.python, self.checkout = Path(python), Path(checkout).resolve()
        self.engine_version = engine_version   # `resolve`: el bot corre en otro directorio
        self.limits = limits or Limits(timeout_s=900.0, memory_mb=3072, cpu_s=1800,
                                       max_output_bytes=50_000_000)
        self.card = card or card_of(BOT_ID)
        self.costs, self.runner, self.script = costs or CostParams(), runner, Path(script)

    @property
    def strategies(self) -> tuple[str, ...]:
        return tuple(CONFIGS)

    def _params(self, strategy: str, balance: float, warmup: int, overrides: dict) -> dict:
        return {"strategy": strategy, "config": CONFIGS[strategy], "balance": balance,
                "warmup_min": warmup, "maker": self.costs.maker_fee, "taker": self.costs.taker_fee,
                "market": MARKET, "overrides": overrides, "engine": self.engine_version}

    def version(self, strategy: str, balance: float = 10_000.0, warmup: int = 1440,
                overrides: dict | None = None) -> str:
        return version_of(self.card.commit_sha, self._params(strategy, balance, warmup,
                                                             overrides or {}))

    def simulate(self, symbol: str, candles: list[Candle], strategy: str = "trailing_martingale",
                 balance: float = 10_000.0, warmup_minutes: int = 1440,
                 overrides: dict | None = None) -> SimRun:
        overrides = overrides or {}
        if strategy not in CONFIGS:
            raise KeyError(f"estrategia sin configuración: {strategy}")
        ver = self.version(strategy, balance, warmup_minutes, overrides)
        if not candles:
            return self._empty(symbol, strategy, ver, [], balance, warmup_minutes, "no_data",
                               "sin velas")
        problem = self._check(candles)
        if problem:
            return self._empty(symbol, strategy, ver, candles, balance, warmup_minutes,
                               "no_data", problem)
        res = self.runner(self._spec(symbol, candles, strategy, balance, warmup_minutes,
                                     overrides))
        if res.status != "ok" or res.output is None:
            return self._empty(symbol, strategy, ver, candles, balance, warmup_minutes,
                               "degraded", "; ".join(res.warnings) or "el bot no respondió")
        try:
            return self._parse(symbol, candles, strategy, ver, balance, warmup_minutes, res)
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            return self._empty(symbol, strategy, ver, candles, balance, warmup_minutes,
                               "degraded", f"salida del bot inválida: {type(exc).__name__}: {exc}")

    @staticmethod
    def _check(candles: list[Candle]) -> str | None:
        if len(candles) < 2:
            return "se necesitan al menos 2 velas de 1 min"
        if any(b.t - a.t != MINUTE for a, b in zip(candles, candles[1:], strict=False)):
            return "las velas deben ser de 1 min consecutivas, sin huecos"
        return None

    def _spec(self, symbol: str, candles: list[Candle], strategy: str, balance: float,
              warmup: int, overrides: dict) -> RunSpec:
        request = {"bot_dir": str(self.checkout), "config": CONFIGS[strategy],
                   "coin": symbol[:-4] if symbol.endswith("USDT") else symbol,
                   "start_date": ymd(candles[0].t), "end_date": ymd(candles[-1].t),
                   "starting_balance": balance, "maker_fee": self.costs.maker_fee,
                   "taker_fee": self.costs.taker_fee, "warmup_minutes": warmup,
                   "overrides": overrides, "bot_sha": self.card.commit_sha, **MARKET}
        rows = [[c.t, c.o, c.h, c.l, c.c, c.v] for c in candles]
        return RunSpec(python=self.python, script=self.script, limits=self.limits,
                       request=request, files={"candles.json": json.dumps(rows)},
                       bot_dir=self.checkout, expected_sha=self.card.commit_sha)

    def _quality(self, candles: list[Candle], *notes: str) -> BotQuality:
        return BotQuality(bars=len(candles), last_candle_t=candles[-1].t if candles else None,
                          source="almacén local 1m", coverage=1.0 if candles else None,
                          notes=list(notes))

    def _empty(self, symbol: str, strategy: str, ver: str, candles: list[Candle], balance: float,
               warmup: int, status: str, reason: str) -> SimRun:
        t0 = candles[0].t if candles else 0
        t1 = candles[-1].t + MINUTE if candles else MINUTE
        return SimRun(bot_id=BOT_ID, strategy=strategy, version=ver, symbol=symbol, timeframe="1m",
                      start=t0, end=t1, warmup_minutes=warmup, starting_balance=balance,
                      data_quality=self._quality(candles, reason), status=status,  # type: ignore[arg-type]
                      evidence=[reason])

    def _parse(self, symbol: str, candles: list[Candle], strategy: str, ver: str, balance: float,
               warmup: int, res: RunResult) -> SimRun:
        out = res.output or {}
        if out["bot_version"] != self.card.commit_sha:
            raise ValueError("la salida declara otra versión del bot")
        if out["engine"] != self.engine_version:
            raise ValueError(f"motor {out['engine']} ≠ el fijado {self.engine_version}")
        if int(out["n_candles"]) != len(candles):
            raise ValueError("el bot usó otro número de velas que las enviadas")
        cols = out["fill_columns"]
        if tuple(cols[:len(FILL_FIELDS)]) != FILL_FIELDS:
            raise ValueError("columnas de fills inesperadas")
        fills = []
        for row in out["fills"]:
            r = dict(zip(cols, row, strict=False))
            fills.append(SimFill(
                t=int(r["timestamp"]), kind=str(r["type"]), qty=float(r["qty"]),
                price=float(r["price"]), psize_after=float(r["psize"]), pnl=float(r["pnl"]),
                fee_paid=float(r["fee_paid"]), liquidity=r["liquidity"],
                wallet_exposure=float(r["wallet_exposure"])))
        eq = [SimEquityPoint(t=int(r[0]), equity=float(r[1])) for r in out["equity"]]
        metrics = {k: v for k, v in out.get("analysis", {}).items()
                   if isinstance(v, (int, float, bool))}
        costs = {"maker_fee": self.costs.maker_fee, "taker_fee": self.costs.taker_fee}
        first = eq[0].t if eq else None
        ev = [f"{strategy}: {len(fills)} fills simulados sobre {len(candles)} velas de 1 min; "
              "solo largos; comisión fijada por EIM (T25), no la del README del bot; "
              "simulación, no operaciones"]
        if first is not None:
            ev.append(f"el bot empezó a operar en {first} (calentamiento propio de sus EMA)")
        return SimRun(
            bot_id=BOT_ID, strategy=strategy, version=ver, symbol=symbol, timeframe="1m",
            start=candles[0].t, end=candles[-1].t + MINUTE, warmup_minutes=warmup,
            starting_balance=balance, fills=fills, equity=eq, metrics=metrics,
            costs_assumed=costs, data_quality=self._quality(candles), status="ok", evidence=ev)


def run_hash(run: SimRun) -> str:
    """Huella de lo que hizo el bot (fills + capital): sirve para comprobar reproducibilidad."""
    body = {"fills": [f.model_dump() for f in run.fills],
            "equity": [e.model_dump() for e in run.equity]}
    return params_hash(body)
