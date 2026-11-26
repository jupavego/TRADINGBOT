"""Línea de órdenes del escáner global (T93). Desde `v2/`:

    python -m eim.scanner run                  # servicio: relleno, barrido y ritmo rápido
    python -m eim.scanner run --once           # una vuelta y sale
    python -m eim.scanner status               # latido, último barrido y cola (no abre la base)
    python -m eim.scanner sweep --asof latest  # un barrido (reproducible con la última vela)
    python -m eim.scanner sync --discover      # catálogo (1 llamada) + velas que faltan
    python -m eim.scanner budget               # mide y escribe reports/scanner_budget.md
    python -m eim.scanner deep                 # T94: agentes sobre la lista corta del último
                                               #      barrido → oportunidades candidatas + vista
    python -m eim.scanner verify OPP_ID        # T94: relee sus velas, comprueba el hash y la
                                               #      vuelve a calcular (mismo id y cifras)
    python -m eim.scanner calibrate            # T95: pesos del ranking fuera de muestra con lo
                                               #      madurado (solo adopta si mejora)

Modo ANÁLISIS: nada de esto envía órdenes. Códigos de salida de `budget`: 0 dentro del
presupuesto y reproducible; 3 fuera del presupuesto; 4 no reproducible; 5 sin catálogo o datos.
`verify`: 0 reproducida; 4 no reproducida; 5 sin esa oportunidad.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from eim.data import scanner_market as market
from eim.data.timeframes import tf_ms
from eim.scanner.params import DEFAULT_PARAMS


def parse_asof(value: str | None, root: Path, timeframe: str) -> int | None:
    """`latest` = justo tras la última vela guardada; un entero = ms; si no, fecha ISO (UTC)."""
    if value is None:
        return None
    if value == "latest":
        last = market.latest_t(root, timeframe)
        if last is None:
            raise SystemExit(f"sin velas {timeframe} en {root}: corre `sync --discover` antes")
        return last + tf_ms(timeframe)
    if value.isdigit():
        return int(value)
    d = dt.datetime.fromisoformat(value)
    d = d if d.tzinfo else d.replace(tzinfo=dt.UTC)
    return int(d.timestamp() * 1000)


def _status(data_dir: Path) -> int:
    base = data_dir / "scanner"
    for name in ("heartbeat.json", "status.json"):
        f = base / name
        print(f"— {name}:")
        print(f.read_text(encoding="utf-8") if f.exists() else "  (no existe todavía)")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")      # consola cp1252: sin reventar
    ap = argparse.ArgumentParser(prog="eim.scanner", description="Escáner global (T93)")
    ap.add_argument("--data-dir", default=os.environ.get("EIM_DATA_DIR", "data"))
    ap.add_argument("--universe-root", help="almacén del universo (por defecto "
                                            "<data-dir>/universe_perps, el de T181)")
    ap.add_argument("--procs", type=int, default=DEFAULT_PARAMS.max_procs)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="servicio supervisado")
    r.add_argument("--once", action="store_true")
    r.add_argument("--no-sync", action="store_true", help="no descarga velas")
    r.add_argument("--no-quotes", action="store_true", help="sin cotizaciones ni ritmo rápido")
    r.add_argument("--no-agents", action="store_true", help="sin la pasada de agentes (T94)")
    sub.add_parser("status", help="estado sin abrir la base")
    s = sub.add_parser("sweep", help="un barrido del embudo")
    s.add_argument("--asof")
    s.add_argument("--no-deep", action="store_true")
    s.add_argument("--json", action="store_true")
    y = sub.add_parser("sync", help="relleno de velas del universo")
    y.add_argument("--discover", action="store_true", help="antes, el descubrimiento de T89")
    y.add_argument("--max", type=int, help="como mucho N símbolos (por defecto, todos)")
    d = sub.add_parser("deep", help="agentes sobre la lista corta (T94)")
    d.add_argument("--run", help="barrido base (por defecto, el último)")
    d.add_argument("--json", action="store_true")
    d.add_argument("--summary", help="archivo con una línea de resumen (para el plan)")
    v = sub.add_parser("verify", help="reproduce una oportunidad desde sus datos (T94)")
    v.add_argument("opportunity_id")
    v.add_argument("--summary", help="archivo con una línea de resumen (para el plan)")
    c = sub.add_parser("calibrate", help="pesos del ranking fuera de muestra (T95)")
    c.add_argument("--dry-run", action="store_true", help="calcula sin adoptar")
    b = sub.add_parser("budget", help="mide el presupuesto")
    b.add_argument("--asof", default="latest")
    b.add_argument("--out", default="reports/scanner_budget.md")
    b.add_argument("--summary", help="archivo con una línea de resumen (para el plan)")
    a = ap.parse_args(argv)

    data_dir = Path(a.data_dir)
    if a.cmd == "status":
        return _status(data_dir)
    from eim.scanner.service import ScannerError, ScannerService

    root = Path(a.universe_root) if a.universe_root else market.universe_root(data_dir)
    if a.cmd == "budget":
        return _budget(a, data_dir, root)
    quotes = None if a.cmd != "run" or a.no_quotes else market.book_tickers
    svc = ScannerService(data_dir, universe_root=root, procs=a.procs, quotes_fn=quotes)
    if a.cmd == "run":
        from eim.observability.emit import configure
        from eim.operation import priority
        from eim.scanner.runner import run_loop

        configure(process="scanner", spool_dir=data_dir / "obs" / "spool")
        priority.apply_role("scanner")  # T126: prescindible, prioridad baja (si EIM_PRIORITY)
        return run_loop(svc, once=a.once, sync=not a.no_sync, quotes=not a.no_quotes,
                        agents=not a.no_agents)
    try:
        if a.cmd in ("deep", "verify", "calibrate"):
            from eim.scanner import deep_cli

            return {"deep": deep_cli.deep_cmd, "verify": deep_cli.verify_cmd,
                    "calibrate": deep_cli.calibrate_cmd}[a.cmd](svc, a)
        if a.cmd == "sync":
            out = svc.sync(limit=a.max if a.max is not None else 100_000, discover=a.discover)
        else:
            out = svc.sweep(parse_asof(a.asof, root, svc.p.timeframe), process_deep=not a.no_deep)
            if not a.json:
                out = {k: out[k] for k in ("run_id", "asof", "n_catalog", "n_stage1", "n_stage2",
                                           "n_shortlist", "ms_per_instrument", "within_budget",
                                           "fingerprint")} | {
                    "exclusions": out["detail_json"]["exclusions"],
                    "shortlist": out["detail_json"]["shortlist"][:10]}
        print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        return 0
    except ScannerError as exc:
        print(f"no se puede: {exc}", file=sys.stderr)
        return 5
    finally:
        svc.close()


def _budget(a, data_dir: Path, root: Path) -> int:
    from eim.data.scanner_store import ScannerStore
    from eim.scanner import budget
    from eim.scanner.service import ScannerError, ScannerService

    svc = ScannerService(data_dir, universe_root=root, procs=a.procs,
                         store=ScannerStore(":memory:"))
    try:
        m = budget.measure(svc, parse_asof(a.asof, root, svc.p.timeframe))
    except ScannerError as exc:
        print(f"no se puede medir: {exc}", file=sys.stderr)
        return 5
    finally:
        svc.close()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(budget.render(m), encoding="utf-8")
    c = m["cold"]
    line = (f"barrido de {c['n_catalog']} instrumentos del catálogo ({c['n_stage1']} leídos, "
            f"{c['n_stage2']} puntuados, {c['n_shortlist']} a la lista corta) en "
            f"{m['funnel_s']:.2f} s = "
            f"{m['ms_per_instrument']:.2f} ms/instrumento (presupuesto T87 {m['budget_ms']:g} ms: "
            f"{'dentro' if m['within_budget'] else 'FUERA'}); reproducible: "
            f"{'sí' if m['reproducible'] else 'NO'}; caché en caliente "
            f"{budget._pct(m['cache_warm'])}; 10 000 instrumentos ≈ "
            f"{m['projection'][-1]['total_s']} s")
    print(line)
    print(f"informe: {out}")
    if a.summary:
        Path(a.summary).write_text(line, encoding="utf-8")
    if not m["within_budget"]:
        return 3
    return 0 if m["reproducible"] else 4


if __name__ == "__main__":      # pragma: no cover
    sys.exit(main())
