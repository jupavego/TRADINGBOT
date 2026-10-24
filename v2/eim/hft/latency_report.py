"""Informe del banco de latencia (T77): fusiona corridas (JSON) y escribe el Markdown.

Puro: recibe los dicts que deja `scripts/hft_latency.py run` y devuelve texto. Los percentiles
de «todas las corridas» salen de fusionar los histogramas, no de promediar percentiles.
"""

from __future__ import annotations

from eim.hft.latency import Hist

KINDS = ("depth", "bookTicker", "aggTrade", "markPrice")
TOP = ("rest_rtt", "ws_api_ping", "ws_api_time", "loop_lag")
# regla de T77: Rust solo si el proceso Python p99 supera el 20 % del presupuesto
RUST_SHARE = 0.20


def merge(runs: list[dict]) -> dict[str, Hist]:
    """Histogramas fusionados con clave `flujo.métrica` o nombre de nivel superior."""
    out: dict[str, Hist] = {}
    for r in runs:
        h = r.get("hists", {})
        flat = {k: h[k] for k in TOP if k in h}
        for kind in KINDS:
            for m, d in h.get(kind, {}).items():
                flat[f"{kind}.{m}"] = d
        for k, d in flat.items():
            x = Hist.from_json(d)
            out[k] = out[k].merge(x) if k in out else x
    return out


def _q(h: Hist | None, q: float) -> float | None:
    return None if h is None else h.quantile(q)


def _fmt(v: float | None, nd: int = 0) -> str:
    if v is None:
        return "—"
    return f"{v:,.{nd}f}".replace(",", " ").replace(".", ",")


def _trio(h: Hist | None, nd: int = 0) -> str:
    return " / ".join(_fmt(_q(h, q), nd) for q in (0.5, 0.95, 0.99))


def budget(m: dict[str, Hist], data: str = "bookTicker") -> dict[str, dict[str, float]]:
    """Reacción a un evento del libro: antigüedad `T` del flujo `data` (Binance → aquí) + proceso
    Python + retraso del bucle + ida de la orden (RTT del WS API / 2). Suma de percentiles del
    mismo nivel: conservadora (las colas no coinciden siempre). Con `bookTicker` los percentiles
    pesan por evento (las ráfagas cuentan mucho); con `depth` (10 por s fijos), ≈ por tiempo."""
    parts = {"datos": m.get(f"{data}.age_T"), "bucle": m.get("loop_lag"),
             "orden_ida": m.get("ws_api_ping")}
    proc = m.get("depth.proc_us")
    out: dict[str, dict[str, float]] = {}
    for q in (0.5, 0.95, 0.99):
        row = {"datos": _q(parts["datos"], q) or 0.0, "bucle": max(_q(parts["bucle"], q) or 0, 0),
               "orden_ida": (_q(parts["orden_ida"], q) or 0.0) / 2,
               "proceso": (_q(proc, q) or 0.0) / 1000}
        row["total"] = sum(row.values())
        out[f"p{round(q * 100)}"] = row
    return out


def _runs_table(runs: list[dict]) -> list[str]:
    lines = ["| Corrida | Inicio (UTC) | Min | Equipo | REST RTT p50/p95/p99 (ms) | "
             "WS API `ping` p50/p95/p99 (ms) | Desfase ini→fin (ms) | Deriva (ppm) | "
             "Incertidumbre (±ms) | Reconexiones | Bucle p99 (ms) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        h = r.get("hists", {})
        c = r.get("clock", {})
        rec = sum(v.get("reconnects", 0) for v in r.get("connections", {}).values())
        rest = Hist.from_json(h["rest_rtt"]) if "rest_rtt" in h else None
        ping = Hist.from_json(h["ws_api_ping"]) if "ws_api_ping" in h else None
        lag = Hist.from_json(h["loop_lag"]) if "loop_lag" in h else None
        lines.append(
            f"| {r.get('run_id', '?')} | {r.get('started_utc', '?')[:16]} | "
            f"{_fmt(r.get('minutes'), 0)} | {r.get('label', '?')} | {_trio(rest)} | "
            f"{_trio(ping)} | {_fmt(c.get('offset_ms_first'), 1)} → "
            f"{_fmt(c.get('offset_ms_last'), 1)} | {_fmt(c.get('drift_ppm'), 1)} | "
            f"{_fmt(c.get('uncertainty_ms'), 1)} | {rec} | {_fmt(_q(lag, 0.99), 1)} |")
    return lines


def _streams_table(m: dict[str, Hist], runs: list[dict]) -> list[str]:
    secs = sum(r.get("duration_s", 0) for r in runs) or 1
    lines = ["| Flujo | msg/s | Antigüedad `E` p50/p95/p99 (ms) | Antigüedad `T` p50/p95/p99 (ms)"
             " | `E − T` p50/p99 (ms) | Entre llegadas p50/p99 (ms) | Jitter p95−p50 (ms) | "
             "Proceso Python p50/p99 (µs) | Silencios ≥ 5 s |",
             "|---|---|---|---|---|---|---|---|---|"]
    for k in KINDS:
        n = sum(r.get("streams", {}).get(k, {}).get("msgs", 0) for r in runs)
        stalls = sum(r.get("streams", {}).get(k, {}).get("stalls_5s", 0) for r in runs)
        age = m.get(f"{k}.age_E")
        jit = None if age is None else _q(age, 0.95) - _q(age, 0.5)
        et, ia, pr = m.get(f"{k}.E_minus_T"), m.get(f"{k}.interarrival"), m.get(f"{k}.proc_us")
        lines.append(
            f"| `{k}` | {_fmt(n / secs, 1)} | {_trio(age)} | {_trio(m.get(f'{k}.age_T'))} | "
            f"{_fmt(_q(et, 0.5))} / {_fmt(_q(et, 0.99))} | {_fmt(_q(ia, 0.5))} / "
            f"{_fmt(_q(ia, 0.99))} | {_fmt(jit)} | {_fmt(_q(pr, 0.5))} / {_fmt(_q(pr, 0.99))} | "
            f"{stalls} |")
    return lines


def _per_run(runs: list[dict]) -> list[str]:
    lines = ["| Corrida | Hora UTC | " + " | ".join(f"`{k}` edad E p50/p95/p99" for k in KINDS)
             + " |", "|---|---|" + "---|" * len(KINDS)]
    for r in runs:
        cells = []
        for k in KINDS:
            d = r.get("hists", {}).get(k, {}).get("age_E")
            cells.append(_trio(Hist.from_json(d)) if d else "—")
        lines.append(f"| {r.get('run_id', '?')} | {r.get('started_utc', '?')[11:13]} h | "
                     + " | ".join(cells) + " |")
    return lines


def render(runs: list[dict]) -> str:
    runs = sorted(runs, key=lambda r: r.get("started_utc", ""))
    m = merge(runs)
    views = {"bookTicker": budget(m, "bookTicker"), "depth": budget(m, "depth")}
    mins = sum(r.get("duration_s", 0) for r in runs) / 60
    hours = sorted({r.get("started_utc", "?")[11:13] for r in runs})
    out = ["# Banco de latencia HFT (T77)", "",
           f"Generado por `python scripts/hft_latency.py report` con {len(runs)} corrida(s), "
           f"{mins:.0f} min en total, horas de inicio UTC: {', '.join(hours)}. Fuente: Binance "
           "USDⓈ-M **producción**, solo flujos públicos (`/public`: `depth@100ms`, `bookTicker`; "
           "`/market`: `aggTrade`, `markPrice@1s`), `GET /fapi/v1/time` y el WS API de órdenes "
           "**solo con `ping`/`time`** (sin claves; ninguna orden). Repetible en otro equipo o "
           "VPS con `python scripts/hft_latency.py run --minutes 60 --label <equipo>`.", "",
           "Definiciones: antigüedad = reloj local corregido con `serverTime` − `E` (emisión) o "
           "− `T` (transacción); su valor absoluto tiene la incertidumbre de la columna "
           "«Incertidumbre» (RTT/2: no se sabe si la ida y la vuelta son simétricas), pero su "
           "dispersión (jitter) no. `E − T` usa solo relojes de Binance. Proceso Python = "
           "`json.loads` + aplicar el diff al libro local (`depth`) o leer el mensaje (resto).", "",
           "## Corridas", "", *_runs_table(runs), "",
           "## Flujos (todas las corridas fusionadas)", "", *_streams_table(m, runs), "",
           "## Antigüedad por corrida y hora", "", *_per_run(runs), "",
           "## Presupuesto de reacción derivado (ms)", "",
           "Evento del libro en Binance → orden de vuelta en Binance = antigüedad `T` del flujo + "
           "proceso Python (`depth`) + retraso del bucle asyncio + ida de la orden (RTT del WS API "
           "/ 2). No incluye la cola del motor de emparejamiento (no medible sin enviar órdenes). "
           "Suma de percentiles: conservadora. Dos vistas de los datos: `bookTicker` pondera por "
           "evento (las ráfagas, cuando más importa reaccionar, pesan mucho); `depth` llega 10 "
           "veces por segundo pase lo que pase y pondera ≈ por tiempo. «Silencios» = 5 s sin "
           "mensajes del flujo (las reconexiones se cuentan aparte).", "",
           "| Vista | Nivel | Datos | Proceso | Bucle | Orden (ida) | **Total** |",
           "|---|---|---|---|---|---|---|"]
    for view, b in views.items():
        for lvl, row in b.items():
            out.append(f"| `{view}` | {lvl} | {_fmt(row['datos'], 1)} | "
                       f"{_fmt(row['proceso'], 2)} | {_fmt(row['bucle'], 1)} | "
                       f"{_fmt(row['orden_ida'], 1)} | **{_fmt(row['total'], 1)}** |")
    # la regla se aplica al presupuesto MENOR (la vista más exigente para Python)
    p99 = min((b["p99"] for b in views.values()), key=lambda r: r["total"])
    hot = p99["proceso"] + p99["bucle"]
    share = hot / p99["total"] if p99["total"] else 0.0
    verdict = ("**supera** el umbral → evaluar Rust para la ruta caliente." if share > RUST_SHARE
               else "**no** lo supera → Python basta; Rust no aporta en esta ruta.")
    out += ["", f"Regla Python vs Rust: proceso + bucle p99 = {_fmt(hot, 1)} ms = "
            f"**{_fmt(share * 100, 1)} %** del menor presupuesto p99 ({_fmt(p99['total'], 1)} ms;"
            f" umbral {_fmt(RUST_SHARE * 100)} %): {verdict}", ""]
    return "\n".join(out)
