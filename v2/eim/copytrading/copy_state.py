"""Estado persistente y resumen de la subcuenta de copia (T42). Se mezcla en `CopyEngine`.

`to_state` → JSON (lo guarda el servicio en `leaders.duckdb`); `load_state` lo restaura tras
un reinicio: la subcuenta sigue con su saldo, posiciones, stops, pausa y kill-switch.
`summary` es lo que ven la API, la UI y el informe (modo SIMULADO siempre).
"""

from __future__ import annotations

from eim.copytrading.copy_book import Account
from eim.copytrading.copy_models import MODE
from eim.copytrading.copy_recon import Recon
from eim.copytrading.replicator import CoinCopy

SEEN_KEEP = 5_000
TRIPS_KEEP = 300


class EngineState:
    """Persistencia y resumen; los atributos los define `CopyEngine.__init__`."""

    def to_state(self) -> dict:
        kill = self.risk.kill.state()
        return {
            "leader_id": self.leader_id, "label": self.label, "measure": self.measure,
            "approved": self.approved, "started_t": self.started_t, "state_t": self.state_t,
            "seq": self.seq,
            "account": self.account.to_dict(),
            "coins": {k: c.to_dict() for k, c in self.coins.items()},
            "leader_av": self.leader_av, "feed_t": self.feed_t, "feed_down": self.feed_down,
            "paused": self.paused, "counts": self.counts, "mismatch": self.mismatch,
            "gap": self.gap, "last_sig_t": self.last_sig_t, "last_bad_t": self.last_bad_t,
            "trip_info": dict(list(self.trip_info.items())[-TRIPS_KEEP:]),
            "seen": list(self.seen)[-SEEN_KEEP:],
            "kill": {k: kill[k] for k in ("active", "reason", "since", "by")},
            "last_recon": self.last_recon.model_dump() if self.last_recon else None,
            "now": self._now,
        }

    def load_state(self, d: dict) -> None:
        self.label = d.get("label") or self.label
        self.measure, self.approved = bool(d.get("measure")), bool(d.get("approved", True))
        self.started_t, self.seq = int(d["started_t"]), int(d.get("seq", 0))
        self.state_t = int(d.get("state_t") or self.started_t)
        self.account = Account.from_dict(d["account"])
        self.coins = {k: CoinCopy(**v) for k, v in (d.get("coins") or {}).items()}
        self.leader_av, self.feed_t = d.get("leader_av"), d.get("feed_t")
        self.feed_down, self.paused = d.get("feed_down"), d.get("paused")
        self.counts = dict(d.get("counts") or {})
        self.mismatch = dict(d.get("mismatch") or {})
        self.gap = tuple(d["gap"]) if d.get("gap") else None
        self.last_bad_t = d.get("last_bad_t")
        self.last_sig_t = {k: int(v) for k, v in (d.get("last_sig_t") or {}).items()}
        self.trip_info = dict(d.get("trip_info") or {})
        self.seen = dict.fromkeys(d.get("seen") or [])
        k = d.get("kill") or {}
        if k.get("active"):
            self.risk.kill.activate(str(k.get("reason", "")), int(k.get("since") or 0),
                                    by=str(k.get("by") or "regla:drawdown"))
        lr = d.get("last_recon")
        self.last_recon = Recon.model_validate(lr) if lr else None
        self._now = int(d.get("now") or self.started_t)

    def positions_view(self) -> list[dict]:
        acc, out = self.account, []
        for coin in sorted(set(acc.positions) | set(self.coins)):
            pos, c = acc.positions.get(coin), self.coins.get(coin) or CoinCopy(coin)
            size = pos.size if pos else 0.0
            if not size and not c.leader:
                continue
            mark = acc.mark(coin)
            out.append({
                "coin": coin, "size": size, "entry": pos.entry if pos else None,
                "mark": mark, "stop": pos.stop if pos else None,
                "upnl": size * (mark - pos.entry) if pos and mark is not None else None,
                "notional": abs(size) * (mark or (pos.entry if pos else 0.0)),
                "leader": c.leader, "leader_entry": c.leader_entry or None,
                "target": c.target(), "ratio": c.ratio, "excluded": c.excluded,
                "note": c.note})
        return out

    def summary(self, journal_tail: int = 40) -> dict:
        acc = self.account
        eq = acc.equity()
        kill = self.risk.kill.state()
        rejects = {k.split(":", 1)[1]: v for k, v in self.counts.items()
                   if k.startswith("rechazo:")}
        r = self.last_recon
        return {
            "leader_id": self.leader_id, "label": self.label, "mode": MODE,
            "measure": self.measure, "approved": self.approved, "paused": self.paused,
            "kill": {"active": kill["active"], "reason": kill["reason"], "since": kill["since"]},
            "started_t": self.started_t, "now": self._now, "equity0": acc.equity0,
            "equity": eq, "pnl": eq - acc.equity0,
            "ret": eq / acc.equity0 - 1 if acc.equity0 else None,
            "realized": acc.realized, "unrealized": acc.unrealized(), "fees": acc.fees,
            "funding": acc.funding, "max_dd": acc.max_dd, "trips": acc.trips,
            "wins": acc.wins, "notional": acc.notional(), "leader_av": self.leader_av,
            "feed_t": self.feed_t, "feed_down": self.feed_down,
            "last_unexplained_t": self.last_bad_t,
            "positions": self.positions_view(),
            "counts": {k: v for k, v in self.counts.items() if not k.startswith("rechazo:")},
            "rejects": rejects,
            "last_recon": {"t": r.t, "ok": r.ok, "checked": r.checked,
                           "diffs": [d.model_dump() for d in r.diffs]} if r else None,
            "curve": acc.curve[-300:],
            "journal": [e.model_dump() for e in self.journal[-journal_tail:]],
        }
