"""Ideas y veredictos sintéticos para los tests del publicador (sin red)."""

from __future__ import annotations

from eim.paper.ideas import Idea

H = 3_600_000
NOW = 1_800_000_000_000 // H * H
T1H = NOW - 10 * 60_000          # última vela cerrada de 1 h (decidida hace 10 min)
PRICE, ATR = 100.0, 2.0


def idea(strategy: str = "ema", tf: str = "1h", side: int = 1, entry: float = PRICE,
         kind: str = "market", t: int = T1H, version: str = "fpA", conf: float = 0.6,
         fill_h: float = 6.0, hold_h: float = 24.0, rr: float = 2.0, sl_d: float = 2.0) -> Idea:
    return Idea(id=f"BTCUSDT:{tf}:{t}:{strategy}", strategy=strategy, family="indicadores",
                symbol="BTCUSDT", t=t, side=side, kind=kind, entry=entry,
                sl=entry - side * sl_d, tp=entry + side * sl_d * rr,
                fill_ms=int(fill_h * H) if kind == "limit" else 0, hold_ms=int(hold_h * H),
                conf=conf, why=("regla A", "regla B"), timeframe=tf, version=version)


def verdict(strategy: str = "ema", tf: str = "1h", verdict: str = "VALIDADA", fp: str = "fpA",
            ci_lo: float = 0.05, n: int = 1, retired: int | None = None) -> dict:
    return {
        "id": f"{strategy}@{tf}@v{n}", "sid": f"{strategy}@{tf}", "n": n, "strategy": strategy,
        "timeframe": tf, "fingerprint": fp, "retired": retired, "verdict": verdict,
        "n_oos": 240, "n_live": 31, "mean_r": ci_lo + 0.1,
        "extras": {"win_rate": 0.47}, "oos": {"from": NOW - 90 * 24 * H, "to": NOW - H},
        "checks": [
            {"id": "V2", "value": {"mean_r": ci_lo + 0.1, "ci": [ci_lo, ci_lo + 0.2]}},
            {"id": "V3", "value": {"p": 0.004, "p_holm": 0.03}},
            {"id": "V4", "value": {"max_dd": 0.18}},
            {"id": "V5", "value": {"n_live": 31, "mean_live": 0.08}},
            {"id": "V6", "value": {"cost_r": 0.12}}]}


def run(ideas, verdicts, **kw):
    from eim.suggestions.publisher import publish
    base = dict(now=NOW, price=PRICE, atr=ATR, last_t={"15m": T1H, "1h": T1H},
                verdicts_asof=NOW - 2 * H, heartbeat=NOW - 60_000)
    return publish(ideas, verdicts, **{**base, **kw})
