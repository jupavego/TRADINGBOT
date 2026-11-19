"""Informe de calidad de la captura de líderes (T40): latencia real de la señal,
coincidencia con el exchange en cada reconciliación, huecos y eventos guardados."""

from __future__ import annotations

from eim.data.leader_store import LeaderStore

_INF = 2**62


def _pct(xs: list[int], q: float) -> int | None:
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(q * (len(xs) - 1)))]


_DAILY = (
    "SELECT leader_id, sum(checks), sum(size_ok), sum(matched), sum(resynced), "
    "sum(coins_checked), sum(coins_skipped), sum(after_retry), sum(offset_sum), sum(offset_n), "
    "max(offset_max), count(*) FROM leader_recon_daily WHERE first_at >= ? AND last_at < ? "
    "GROUP BY 1 ORDER BY 1")
_FIELDS = ("checks", "size_ok", "match", "resynced", "coins_checked", "coins_skipped",
           "after_retry")


def _add_daily(store: LeaderStore, w: list, rec: dict) -> dict:
    """Suma los días cuyo detalle borró la retención de T178 (`leader_recon_daily`). De esos
    días no hay valores sueltos: el desfase de reloj va como media y máximo."""
    off_sum = off_n = days = 0
    maxima = []
    for r in store.query(_DAILY, w):
        row = rec.setdefault(r[0], {"leader": r[0], "summarized": 0,
                                    **dict.fromkeys(_FIELDS, 0)})
        for i, k in enumerate(_FIELDS, start=1):
            row[k] = (row.get(k) or 0) + int(r[i] or 0)
        row["summarized"] += int(r[11] or 0)
        off_sum, off_n, days = off_sum + int(r[8] or 0), off_n + int(r[9] or 0), days + int(r[11])
        if r[10] is not None:
            maxima.append(int(r[10]))
    off_max = max(maxima, default=None)
    if not days:
        return {}
    return {"days": days, "clock_offset_mean_ms": round(off_sum / off_n) if off_n else None,
            "clock_offset_max_ms": off_max}


def summary(store: LeaderStore, since: int, until: int | None = None) -> dict:
    w = [since, until or _INF]
    lat = [int(r[0]) for r in store.query(
        "SELECT observed_at - t FROM leader_fills WHERE channel = 'ws' "
        "AND observed_at >= ? AND observed_at < ?", w)]
    recon = store.query(
        "SELECT leader_id, count(*), sum(size_ok::INT), sum(match::INT), sum(resynced::INT), "
        "sum(checked), sum(skipped), sum((size_ok AND coalesce(retries, 0) > 0)::INT) "
        "FROM leader_recon WHERE observed_at >= ? AND observed_at < ? "
        "GROUP BY leader_id ORDER BY leader_id", w)
    off = [int(r[0]) for r in store.query(
        "SELECT clock_offset_ms FROM leader_recon WHERE observed_at >= ? AND observed_at < ? "
        "AND clock_offset_ms IS NOT NULL", w)]
    rec = {r[0]: {"leader": r[0], "checks": r[1], "size_ok": r[2], "match": r[3],
                  "resynced": r[4], "coins_checked": r[5], "coins_skipped": r[6],
                  "after_retry": r[7], "summarized": 0} for r in recon}
    summarized = _add_daily(store, w, rec)
    return {
        "since": since, "until": until, "clock_offset_ms": _pct(off, 0.5),
        "latency_ms": {"n": len(lat), "min": min(lat, default=None), "p50": _pct(lat, 0.5),
                       "p90": _pct(lat, 0.9), "p99": _pct(lat, 0.99),
                       "max": max(lat, default=None)},
        "fills_by_channel": dict(store.query(
            "SELECT channel, count(*) FROM leader_fills WHERE observed_at >= ? "
            "AND observed_at < ? GROUP BY channel ORDER BY channel", w)),
        "fills_by_action": dict(store.query(
            "SELECT action, count(*) FROM leader_fills WHERE observed_at >= ? "
            "AND observed_at < ? GROUP BY action ORDER BY action", w)),
        "funding": store.query("SELECT count(*), coalesce(sum(usdc), 0) FROM leader_funding "
                               "WHERE observed_at >= ? AND observed_at < ?", w)[0],
        "leverage_changes": store.query("SELECT count(*) FROM leader_leverage WHERE "
                                        "observed_at >= ? AND observed_at < ?", w)[0][0],
        "recon": [rec[k] for k in sorted(rec)],
        "recon_summarized": summarized,
        "gaps": [{"cause": c, "n": n, "recovered": rec} for c, n, rec in store.query(
            "SELECT cause, count(*), sum(recovered) FROM leader_gaps WHERE observed_at >= ? "
            "AND observed_at < ? GROUP BY cause ORDER BY cause", w)],
        "mismatches": [{"leader": a, "observed_at": b, "diffs": c} for a, b, c in store.query(
            "SELECT leader_id, observed_at, diffs FROM leader_recon WHERE NOT match "
            "AND observed_at >= ? AND observed_at < ? ORDER BY observed_at LIMIT 20", w)],
    }


def render(s: dict) -> str:
    lat = s["latency_ms"]
    checks = sum(r["checks"] for r in s["recon"])
    ok = sum(r["size_ok"] for r in s["recon"])
    full = sum(r["match"] for r in s["recon"])
    lines = [
        "Captura de líderes · Hyperliquid (API pública oficial) · solo lectura",
        f"Latencia WS (observado − exchange): n={lat['n']} p50={lat['p50']} ms "
        f"p90={lat['p90']} ms p99={lat['p99']} ms máx={lat['max']} ms "
        f"(reloj local corregido {s['clock_offset_ms']} ms frente al servidor)",
        f"Ejecuciones por canal: {s['fills_by_channel']}",
        f"Ejecuciones por acción: {s['fills_by_action']}",
        f"Funding: {s['funding'][0]} pagos, neto {s['funding'][1]:+.2f} USDC · "
        f"cambios de apalancamiento: {s['leverage_changes']}",
        f"Reconciliaciones: {checks} · tamaño coincide {ok}/{checks} (de ellas "
        f"{sum(r['after_retry'] for r in s['recon'])} tras re-comprobar) · todo coincide "
        f"{full}/{checks} · resincronizaciones {sum(r['resynced'] for r in s['recon'])}",
    ]
    if s.get("recon_summarized"):
        d = s["recon_summarized"]
        lines.append(f"  incluye {d['days']} días cuyo detalle ya se resumió (T178): desfase de "
                     f"reloj medio {d['clock_offset_mean_ms']} ms, máximo "
                     f"{d['clock_offset_max_ms']} ms")
    lines += [f"  {r['leader']}: {r['size_ok']}/{r['checks']} tamaño "
              f"({r['after_retry']} tras re-comprobar), {r['match']}/{r['checks']} completo, "
              f"monedas comparadas {r['coins_checked']} (por delante {r['coins_skipped']})"
              for r in s["recon"]]
    lines += [f"Huecos {g['cause']}: {g['n']} (ejecuciones recuperadas {g['recovered']})"
              for g in s["gaps"]] or ["Huecos: ninguno"]
    lines += [f"  difiere {m['leader']} @ {m['observed_at']}: {m['diffs']}"
              for m in s["mismatches"]]
    return "\n".join(lines)
