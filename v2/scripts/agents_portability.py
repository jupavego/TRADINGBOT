"""Prueba de portabilidad de los agentes (T87): los de `candles` sobre series SIN cripto.

Corre, TAL CUAL y sin tocar ningún agente, los agentes que solo declaran `requires={"candles"}`
sobre series diarias reales no cripto que ya están en el almacén por T183 (oro XAUUSDT, S&P 500
y Nasdaq Composite) y, como referencia, sobre BTCUSDT diario del mismo almacén. Dice cuál falla,
cuál degrada y con qué aviso: es el insumo de la fila «agentes» de la matriz de reutilización y
de los supuestos de tiempo/volumen que T91 tiene que declarar.

Uso (desde `v2/`):
  python scripts/agents_portability.py --data-dir data --out reports/t87_portabilidad.md

Solo lectura: no pide red (las series ya están en `data/intermarket/`), no escribe en el
almacén y no importa nada de `eim/agents` que no sea el registro.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents_cost import CHEAP_REQUIRES, build_agents  # noqa: E402

from eim.core import Candle, MarketSnapshot  # noqa: E402
from eim.data.intermarket import read_intermarket  # noqa: E402

# Series no cripto de `data/intermarket/` (T183) y la referencia cripto del mismo almacén.
REFERENCE = "BTCUSDT"
CLASSES: dict[str, str] = {
    "XAUUSDT": "materia prima (perpetuo TradFi de Binance, 24/5 con pausas)",
    "SP500": "índice de renta variable (^GSPC, sesión de Nueva York)",
    "NASDAQ": "índice de renta variable (^IXIC, sesión de Nueva York)",
    REFERENCE: "cripto, referencia (perpetuo 24/7)",
}


@dataclass
class Result:
    asset: str
    agent_id: str
    status: str
    bias: float
    confidence: float
    overlays: int
    warnings: list[str]
    error: str = ""


def series(data_dir: Path, asof: int) -> dict[str, list[Candle]]:
    got = read_intermarket(data_dir, asof)
    if got is None:
        raise SystemExit(f"sin series de intermercado en {data_dir / 'intermarket'} (T183)")
    bars, _sources, _cov = got
    return {k: v for k, v in bars.items() if k in CLASSES}


def snapshot_of(asset: str, candles: list[Candle], asof: int) -> MarketSnapshot:
    """Snapshot mínimo: solo la serie diaria. Todo lo demás queda en None a propósito."""
    return MarketSnapshot(symbol=asset, timeframe="1d", candles=candles, asof=asof,
                          sources={"candles": f"intermarket/{asset}.jsonl (T183)"},
                          coverage={"candles": (candles[0].t, candles[-1].t)})


def run_all(bars: dict[str, list[Candle]], asof: int) -> list[Result]:
    agents = [a for a in build_agents() if set(a.requires) <= CHEAP_REQUIRES]
    out: list[Result] = []
    for asset in CLASSES:
        if asset not in bars:
            continue
        snap = snapshot_of(asset, bars[asset], asof)
        for agent in agents:
            try:
                r = agent.run(snap)
            except Exception as exc:  # noqa: BLE001 - el fallo es el resultado que buscamos
                out.append(Result(asset, agent.id, "EXCEPCIÓN", 0.0, 0.0, 0, [],
                                  f"{type(exc).__name__}: {exc}"))
                continue
            out.append(Result(asset, agent.id, r.status, r.bias, r.confidence,
                              len(r.overlays), list(r.warnings)))
    return out


def _verdict(rows: list[Result]) -> str:
    """Veredicto por agente a partir de lo observado en las series no cripto."""
    noncrypto = [r for r in rows if r.asset != REFERENCE]
    if any(r.status == "EXCEPCIÓN" for r in noncrypto):
        return "**falla**"
    if all(r.status == "ok" for r in noncrypto):
        return "ok"
    if any(r.status == "no_data" for r in noncrypto):
        return "sin datos"
    return "degrada"


def render(bars: dict[str, list[Candle]], rows: list[Result], asof: int) -> str:
    agents = sorted({r.agent_id for r in rows})
    out = ["# T87 — Portabilidad de los agentes de `candles` a series sin cripto", "",
           f"Generado: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} · reproducible con "
           "`python scripts/agents_portability.py` · **ningún agente fue modificado**.", "",
           "## Series usadas (reales, ya en el almacén por T183)", "",
           "| Serie | clase | velas diarias | desde | hasta |", "|---|---|---:|---|---|"]
    for asset, label in CLASSES.items():
        if asset not in bars:
            out.append(f"| `{asset}` | {label} | — | — | no está en el almacén |")
            continue
        cs = bars[asset]
        out.append(f"| `{asset}` | {label} | {len(cs)} | "
                   f"{datetime.fromtimestamp(cs[0].t / 1000, UTC):%Y-%m-%d} | "
                   f"{datetime.fromtimestamp(cs[-1].t / 1000, UTC):%Y-%m-%d} |")
    present = [a for a in CLASSES if a in bars]
    out += ["", "## Resultado por agente y serie", "",
            "`estado` del `AgentReport`: `ok`, `degraded`, `no_data` o `EXCEPCIÓN` (el agente "
            "levantó un error). Entre paréntesis, el nº de avisos.", "",
            "| Agente | " + " | ".join(f"`{a}`" for a in present) + " | veredicto |",
            "|---" * (len(present) + 2) + "|"]
    for agent_id in agents:
        mine = [r for r in rows if r.agent_id == agent_id]
        by_asset = {r.asset: r for r in mine}
        cells = []
        for asset in present:
            r = by_asset.get(asset)
            cells.append("—" if r is None
                         else f"{r.status} ({len(r.warnings)})" if r.warnings else r.status)
        out.append(f"| `{agent_id}` | " + " | ".join(cells) + f" | {_verdict(mine)} |")
    out += ["", "## Avisos y errores, literales", ""]
    for asset in present:
        msgs = [r for r in rows if r.asset == asset and (r.warnings or r.error)]
        if not msgs:
            continue
        out.append(f"### `{asset}`")
        for r in msgs:
            for w in r.warnings:
                out.append(f"- `{r.agent_id}`: {w}")
            if r.error:
                out.append(f"- `{r.agent_id}`: **{r.error}**")
        out.append("")
    out += [f"asof de la corrida: {datetime.fromtimestamp(asof / 1000, UTC):%Y-%m-%d %H:%M UTC}",
            ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Portabilidad de los agentes de candles (T87)")
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--out", type=Path, default=Path("reports/t87_portabilidad.md"))
    a = p.parse_args(argv)

    asof = int(time.time() * 1000)
    bars = series(a.data_dir, asof)
    rows = run_all(bars, asof)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(bars, rows, asof), encoding="utf-8")
    print(f"escrito {a.out}")
    for asset in CLASSES:
        mine = [r for r in rows if r.asset == asset]
        if mine:
            bad = [r for r in mine if r.status != "ok"]
            print(f"  {asset}: {len(mine)} agentes, {len(bad)} no 'ok'"
                  + (f" ({', '.join(sorted({r.agent_id for r in bad}))})" if bad else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
