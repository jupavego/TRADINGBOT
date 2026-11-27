"""Prueba de portabilidad de T87, repetida con capacidades y elegibilidad (T91).

Las mismas series reales de T87 (oro XAUUSDT, S&P 500, Nasdaq y BTCUSDT diario de referencia,
ya en `data/intermarket/` por T183), ahora con **los 20 agentes** pasando por
`eim.agents.eligibility.run_eligible` con la ficha de cada instrumento (T89). Para cada agente y
serie pone lado a lado lo que daba en T87 (el agente tal cual) y lo que da ahora: elegible,
degradado con aviso o no elegible con su motivo. Es el criterio de aceptación de T91.

Uso (desde `v2/`):
  python scripts/agents_eligibility.py --data-dir data --out reports/t91_portabilidad.md \
      [--summary resumen.txt]

Solo lectura: no pide red, no escribe en el almacén y `context` corre sin LLM.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents_cost import build_agents  # noqa: E402
from agents_portability import CLASSES, REFERENCE, series, snapshot_of  # noqa: E402

from eim.agents.eligibility import run_eligible  # noqa: E402
from eim.instruments.registry import resolve  # noqa: E402

SILENT = "acierto silencioso de T87"


def _cell(before, after) -> str:
    b = "EXCEPCIÓN" if before is None else before.status
    if after.metrics.get("eligibility", {}).get("eligible") is False:
        return f"{b} → **no elegible**"
    return f"{b} → {after.status}"


def run(data_dir: Path, asof: int) -> tuple[dict, list]:
    bars = series(data_dir, asof)
    agents = build_agents()
    rows: dict[str, dict[str, tuple]] = {}
    for asset in CLASSES:
        if asset not in bars:
            continue
        snap = snapshot_of(asset, bars[asset], asof)
        inst = resolve(asset)
        after = run_eligible(agents, snap, inst)
        for agent, rep in zip(agents, after, strict=True):
            try:
                before = agent.run(snap)
            except Exception:  # noqa: BLE001 - en T87 una excepción era un resultado
                before = None
            rows.setdefault(agent.id, {})[asset] = (before, rep, inst.id)
    return rows, [a for a in CLASSES if a in bars]


def _counts(rows: dict) -> Counter:
    c: Counter = Counter()
    for by_asset in rows.values():
        for asset, (_b, rep, _i) in by_asset.items():
            if asset == REFERENCE:
                continue
            elig = rep.metrics.get("eligibility", {})
            if elig.get("eligible") is False:
                c["no elegible con motivo"] += 1
            elif rep.status == "degraded":
                c["degradado con aviso"] += 1
            elif rep.status == "no_data":
                c["sin datos con motivo"] += 1
            else:
                c["elegible"] += 1
            if any(w.startswith("error:") for w in rep.warnings):
                c["excepción"] += 1
    return c


def render(rows: dict, present: list[str], asof: int) -> tuple[str, str]:
    counts = _counts(rows)
    out = ["# T91 — Portabilidad de los agentes, con capacidades y elegibilidad", "",
           f"Generado: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} · reproducible con "
           "`python scripts/agents_eligibility.py` · mismas series que "
           "`reports/t87_portabilidad.md`, ahora con los 20 agentes por `run_eligible`.", "",
           "Cada celda: estado en T87 (el agente tal cual) → estado con T91. «no elegible» = no "
           "corre y sale `no_data` con el motivo escrito.", "",
           "| Agente | " + " | ".join(f"`{a}` ({rows[next(iter(rows))][a][2]})" for a in present)
           + " |", "|---" * (len(present) + 1) + "|"]
    for agent_id in sorted(rows):
        cells = [_cell(*rows[agent_id][a][:2]) if a in rows[agent_id] else "—" for a in present]
        out.append(f"| `{agent_id}` | " + " | ".join(cells) + " |")
    out += ["", "## Resumen en las series no cripto", ""]
    out += [f"- {k}: **{v}**" for k, v in sorted(counts.items())]
    vw = [rows["vwap"][a][1] for a in present if a in ("SP500", "NASDAQ") and a in rows["vwap"]]
    if vw:
        fixed = all(r.status != "ok" for r in vw)
        out += ["", f"- `vwap` en los índices ({SILENT}: `ok` con un ancla muerta): "
                + ("**corregido**, ya no publica `ok`" if fixed else "**SIGUE en `ok`**")]
    out += ["", "## Motivos y avisos de T91, literales", ""]
    for asset in present:
        lines = []
        for agent_id in sorted(rows):
            if asset not in rows[agent_id]:
                continue
            rep = rows[agent_id][asset][1]
            elig = rep.metrics.get("eligibility")
            if elig and elig.get("reason") != "elegible":
                lines.append(f"- `{agent_id}`: {elig['reason']}")
        if lines:
            out += [f"### `{asset}`", *lines, ""]
    out += [f"asof de la corrida: {datetime.fromtimestamp(asof / 1000, UTC):%Y-%m-%d %H:%M UTC}",
            ""]
    total = sum(counts[k] for k in ("elegible", "degradado con aviso", "no elegible con motivo",
                                    "sin datos con motivo"))
    summary = (f"portabilidad T87 repetida en {len(present)} series ({total} celdas no cripto): "
               f"{counts['elegible']} elegibles, {counts['degradado con aviso']} degradadas con "
               f"aviso, {counts['no elegible con motivo']} no elegibles con motivo, "
               f"{counts['sin datos con motivo']} sin datos con motivo, "
               f"{counts['excepción']} excepciones")
    return "\n".join(out), summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Portabilidad con elegibilidad (T91)")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--out", default="reports/t91_portabilidad.md")
    p.add_argument("--summary", default=None, help="archivo con el resumen de una línea")
    a = p.parse_args(argv)
    asof = int(time.time() * 1000)
    try:
        rows, present = run(Path(a.data_dir), asof)
    except SystemExit as exc:         # sin series de intermercado en este equipo
        text = f"no medida: {exc}"
        if a.summary:
            Path(a.summary).write_text(text, encoding="utf-8")
        print(text)
        return 0
    text, summary = render(rows, present, asof)
    Path(a.out).write_text(text, encoding="utf-8")
    if a.summary:
        Path(a.summary).write_text(summary, encoding="utf-8")
    print(summary)
    print(f"informe: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
