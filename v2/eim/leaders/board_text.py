"""Tablero de líderes en texto (CLI `python -m eim.leaders score`)."""

from __future__ import annotations

from eim.copytrading.board import Board

_V = {"approved": "APROBADO", "watch": "vigilancia", "rejected": "descartado"}


def _f(x: float | None, fmt: str = "{:.2f}") -> str:
    return "—" if x is None else fmt.format(x)


def render_board(b: Board) -> str:
    lines = [f"Tablero de líderes · modo {b.mode} · {b.label}",
             f"{len(b.leaders)} líderes · selección corregida por {b.n_trials} billeteras · "
             f"{len(b.weights)} aprobados"]
    for c in b.leaders:
        a, f, cp = c.all, c.fwd, c.copyability
        lat = cp.latency_ms.get("p50") if cp else None
        lines.append(
            f"#{c.rank} {_V[c.verdict]:10s} {c.address} {c.label}".rstrip()
            + f"\n    capturado: n={a.n} neto={a.net:+,.0f} FB={_f(a.profit_factor)} "
              f"Sharpe/op={_f(a.sharpe)} DSR={_f(a.dsr)} · adelante: n={f.n} "
              f"en {c.forward_days:.2f} d neto={f.net:+,.0f} DSR={_f(f.dsr)}"
            + (f"\n    cartera: {c.portfolio.days:.0f} d PnL={c.portfolio.pnl:+,.0f} "
               f"TWR={_f(c.portfolio.twr, '{:+.1%}')} DD={_f(c.portfolio.max_dd, '{:.1%}')}"
               if c.portfolio else "\n    cartera: sin datos")
            + (f"\n    copia: latencia p50 {_f(lat, '{:.0f}')} ms · cotizadas {cp.trades} "
               f"operaciones · seguidor {cp.follower_net:+,.0f} vs líder {cp.leader_net:+,.0f}"
               if cp else ""))
        lines += [f"    - [{r.kind}] {r.text}" for r in c.reasons]
    co = b.cohorts
    if co:
        lines.append("Cohortes adelante (¿sirve el filtro?): " + " · ".join(
            f"{_V[k]} {v.trades} op {v.net:+,.0f} USD" for k, v in co.items()))
    lines += [f"error: {e}" for e in b.errors]
    return "\n".join(lines)
