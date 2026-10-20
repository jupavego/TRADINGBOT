"""Candidatos desde el ranking público de Hyperliquid (puro, sin red).

El ranking NO es API oficial (T33 §1): se usa solo para **proponer** candidatos; quien decide es
el scorecard (T41) con datos propios capturados adelante. Aquí solo se filtra lo copiable:
rentable en mes, semana y todo el historial, cuenta con tamaño, y sin perfil de bot de alta
frecuencia. Una fila rota o con campos faltantes se descarta (nunca se inventa un valor).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from eim.core.leaders import Leader, leader_id
from eim.leaders import params as P

_EVM = re.compile(r"^0x[0-9a-f]{40}$")


def _window(row: dict, name: str) -> dict[str, float] | None:
    for key, val in row.get("windowPerformances") or []:
        if key == name:
            try:
                return {k: float(val[k]) for k in ("pnl", "roi", "vlm")}
            except (KeyError, TypeError, ValueError):
                return None
    return None


def pick(rows: Iterable[dict], now: int, *, top: int = P.DISCOVERY_TOP,
         exclude: Iterable[str] = P.EXCLUDED) -> list[Leader]:
    """Los `top` mejores por ROI mensual (topado) y ganancia histórica entre los filtrados."""
    skip = {a.lower() for a in exclude}
    scored: list[tuple[float, float, Leader]] = []
    for row in rows:
        try:
            addr, equity = str(row["ethAddress"]).lower(), float(row["accountValue"])
        except (KeyError, TypeError, ValueError):
            continue
        m, w, a = _window(row, "month"), _window(row, "week"), _window(row, "allTime")
        if (addr in skip or not _EVM.match(addr) or not (m and w and a)
                or equity < P.RANKING_MIN_ACCOUNT_USD or a["pnl"] < P.RANKING_MIN_ALLTIME_PNL
                or m["pnl"] < P.RANKING_MIN_MONTH_PNL_PCT * equity or w["pnl"] <= 0
                or m["roi"] <= 0
                or m["vlm"] / equity > P.RANKING_MAX_VOLUME_TO_EQUITY):
            continue
        score = min(m["roi"], P.RANKING_ROI_CAP)
        scored.append((score, a["pnl"], Leader(
            id=leader_id("hyperliquid", addr), venue="hyperliquid", address=addr, origin="ranking",
            discovered_at=now, source=f"{P.SOURCE}:stats-data.leaderboard (no oficial)",
            evidence={"account_usd": round(equity, 2), "month_roi": round(m["roi"], 4),
                      "month_pnl": round(m["pnl"], 2), "week_pnl": round(w["pnl"], 2),
                      "alltime_pnl": round(a["pnl"], 2), "month_vlm": round(m["vlm"], 2)})))
    # empates (muchos topan el ROI): gana quien más acumuló en todo el historial, no el azar
    scored.sort(key=lambda x: (-x[0], -x[1], x[2].address))
    return [ld for _, _, ld in scored[:top]]
