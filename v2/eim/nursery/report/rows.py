"""Del libro guardado de la cantera a las entradas del escalafón (T172). Puro.

Lee las filas tal como las guarda `nursery/store.py` (`nursery_trades`, `nursery_accounts`,
`nursery_events`) y reconstruye lo mismo que calcula la mesa en vivo (`ladder_io.standings`):
solo cuentan las operaciones **contabilizadas** (no las sombras de la puerta de costo) y cerradas
en `exit_t ≤ t`. Así el informe no depende de que la API esté reiniciada con código nuevo: basta
el libro, en vivo o en una copia de seguridad.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from eim.nursery.ladder import Standing, evaluate
from eim.nursery.ladder_final import make_first_team
from eim.nursery.ladder_io import FILLED, closed_spans
from eim.nursery.ladder_stats import DAY_MS, AccountData, Closed
from eim.nursery.prereg import Prereg


@dataclass
class Snapshot:
    """Lo que el informe necesita del libro de la cantera, ya leído."""

    prereg: Prereg
    alta_ms: int
    asof_ms: int
    accounts: list[dict]                 # account_id, kind, prospect_id, fingerprint, timeframe
    trades: list[dict]                   # filas de `nursery_trades`
    events: list[dict] = field(default_factory=list)
    buy_hold: dict | None = None
    regimes: Mapping[str, Mapping[int, str]] | None = None
    source: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def initial(self) -> float:
        return float(self.prereg.accounts.initial_equity_usdt)

    def account_of(self) -> dict[str, str]:
        """Cuenta de cada prospecto del pre-registro (la de su huella congelada)."""
        fp = {x.id: x.fingerprint for x in self.prereg.family.members}
        out: dict[str, str] = {}
        for a in self.accounts:
            pid = a.get("prospect_id")
            if pid in fp and (a.get("fingerprint") in (None, fp[pid]) or pid not in out):
                out[pid] = a["account_id"]
        return out

    def controls(self) -> list[str]:
        return [a["account_id"] for a in self.accounts if a.get("kind") == "control"]


def _booked(tr: dict) -> bool:
    return bool(tr.get("booked")) and tr.get("status") in FILLED


def account_data(snap: Snapshot) -> dict[str, AccountData]:
    """`AccountData` de cada cuenta (prospectos y controles), como `ladder_io.account_data`."""
    out: dict[str, tuple[list, list]] = {a["account_id"]: ([], []) for a in snap.accounts}
    tf_of = {a["account_id"]: a.get("timeframe") for a in snap.accounts}
    for tr in snap.trades:
        if not _booked(tr) or tr["account_id"] not in out:
            continue
        closed, fills = out[tr["account_id"]]
        done = tr["status"] == "CERRADA" and tr.get("exit_t") is not None
        fills.append((int(tr["fill_t"]), int(tr["exit_t"]) if done else None))
        if done and tr.get("d_r") is not None:
            reg = (snap.regimes or {}).get(tf_of[tr["account_id"]] or "", {}).get(int(tr["t"]))
            closed.append(Closed(int(tr["t"]), int(tr["fill_t"]), int(tr["exit_t"]),
                                 float(tr["d_r"]), float(tr.get("pnl_usd") or 0.0),
                                 tr.get("cost_r"), tr.get("r"), reg))
    return {k: AccountData(tuple(sorted(c, key=lambda x: x.exit_t)), tuple(sorted(f)))
            for k, (c, f) in out.items()}


def standings(snap: Snapshot, data: Mapping[str, AccountData] | None = None,
              t: int | None = None) -> dict[str, Standing]:
    """Etapa de cada prospecto del pre-registro en `t` (por defecto, `asof`)."""
    data = account_data(snap) if data is None else data
    pr, acc_of = snap.prereg, snap.account_of()
    members = pr.members()
    accounts = {mb.id: data.get(acc_of.get(mb.id, ""), AccountData()) for mb in members}
    controls = {c: data[c] for c in snap.controls() if c in data}
    at = snap.asof_ms if t is None else t
    return evaluate(members, accounts, pr.ladder, snap.alta_ms, at, pr.m, snap.initial,
                    controls=controls, closed_spans=closed_spans(snap.events, at),
                    first_team=make_first_team(pr.ladder, snap.alta_ms, pr.m, snap.initial))


def closed_rows(snap: Snapshot, account: str) -> list[dict]:
    """Operaciones contabilizadas y cerradas de una cuenta, por hora de cierre."""
    rows = [tr for tr in snap.trades if tr["account_id"] == account and _booked(tr)
            and tr["status"] == "CERRADA" and tr.get("exit_t") is not None]
    return sorted(rows, key=lambda tr: int(tr["exit_t"]))


def _ci(xs: Sequence[float]) -> dict:
    x = np.asarray([v for v in xs if v is not None], float)
    if not len(x):
        return {"n": 0, "mean": None, "lo": None, "hi": None}
    m = float(x.mean())
    if len(x) < 2:
        return {"n": 1, "mean": round(m, 4), "lo": None, "hi": None}
    h = 1.96 * float(x.std(ddof=1)) / np.sqrt(len(x))
    return {"n": int(len(x)), "mean": round(m, 4), "lo": round(m - h, 4), "hi": round(m + h, 4)}


def account_metrics(snap: Snapshot, account: str) -> dict:
    """Rentabilidad neta, drawdown, acierto, R neto y bruto, costo y d con su IC (descriptivo)."""
    rows = closed_rows(snap, account)
    bal, peak, dd = snap.initial, snap.initial, 0.0
    daily: dict[int, float] = {}
    for tr in rows:
        pnl = float(tr.get("pnl_usd") or 0.0)
        bal += pnl
        peak = max(peak, bal)
        dd = max(dd, (peak - bal) / peak if peak > 0 else 0.0)
        day = int(tr["exit_t"]) // DAY_MS
        daily[day] = daily.get(day, 0.0) + pnl / snap.initial * 100
    rs = [tr.get("r") for tr in rows]
    costs = [tr.get("cost_r") for tr in rows]
    gross = [r + (c or 0.0) for r, c in zip(rs, costs, strict=True) if r is not None]
    days = max(1, (snap.asof_ms - snap.alta_ms) // DAY_MS + 1)
    series = np.zeros(int(days))
    for d, v in daily.items():
        i = d - snap.alta_ms // DAY_MS
        if 0 <= i < days:
            series[i] += v
    return {
        "n": len(rows), "balance": round(bal, 2),
        "net_return_pct": round((bal / snap.initial - 1) * 100, 3),
        "max_dd_pct": round(dd * 100, 3),
        "hit_rate": round(sum(1 for tr in rows if (tr.get("pnl_usd") or 0) > 0) / len(rows), 4)
        if rows else None,
        "r_net": _ci(rs), "r_gross": _ci(gross), "cost_r": _ci(costs),
        "d": _ci([tr.get("d_r") for tr in rows]),
        "daily_vol_pct": round(float(series.std(ddof=1)), 4) if days > 1 else None,
        "per_day": round(len(rows) / days, 4),
        "by_side": {lab: round(sum(float(tr.get("pnl_usd") or 0) for tr in rows
                                   if int(tr.get("side") or 0) == s), 2)
                    for lab, s in (("largo", 1), ("corto", -1))},
    }
