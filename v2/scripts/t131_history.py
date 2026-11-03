"""T131 — reconstruye en una COPIA la historia que necesita el banco de salidas.

    python scripts/t131_history.py --out backups/t131_banco --from 2023-01-01

En `juanpablo-cpu` el almacén vivo solo cubre el tramo reciente (1 m desde 2026-10-15, 15 m desde
2026-10-17, 1 h desde 2026-08-20, 4 h desde 2026-05-08), mientras los contextos de 1 h de
`paper.duckdb` llegan a 2023-01-11: sin velas no se puede reproducir T111 ni correr el banco. Este
script descarga en una carpeta APARTE (nunca en `data/`) las velas de 1 m, 15 m, 1 h y 4 h y el
funding con el proveedor del proyecto (`BinanceFutures`, el mismo de T111), y copia el
`paper.duckdb` de una copia de seguridad para llevarse los contextos. No toca nada del almacén
vivo ni ningún servicio: solo lee la copia de seguridad y escribe en `--out`.

La descarga va por ventanas y se escribe por lotes (`--batch` filas) para no cargar millones de
velas en memoria ni reescribir el Parquet en cada ventana. Es incremental: repetirlo solo baja lo
que falta. Al terminar escribe la cobertura REAL por serie (`cobertura.json` y `.md` en la copia):
primer y último dato, filas, filas esperadas, huecos y proveedor. Nada se da por cubierto.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.core import Candle
from eim.data.providers.binance import BinanceFutures
from eim.data.store import Store
from eim.data.timeframes import tf_ms

TFS = ("4h", "1h", "15m", "1m")        # de la más barata a la más cara
WINDOW_BARS = 1500                     # velas por petición (límite del proveedor)
BATCH_ROWS = 250_000                   # filas acumuladas antes de escribir el Parquet
DAY_MS = 86_400_000


def ms(day: str) -> int:
    """Fecha ISO (día o instante UTC) → ms."""
    s = day.replace("Z", "+00:00")
    d = datetime.fromisoformat(s if "T" in s else f"{s}T00:00:00+00:00")
    return int((d if d.tzinfo else d.replace(tzinfo=UTC)).timestamp() * 1000)


def iso(t: int | None) -> str | None:
    return None if t is None else datetime.fromtimestamp(t / 1000, UTC).isoformat(
        timespec="minutes")


def newest_backup(root: Path) -> Path | None:
    """`paper.duckdb` de la copia completa local más reciente (la que trae los contextos)."""
    found = sorted((p for p in root.glob("eim_*/paper.duckdb")), key=lambda p: p.parent.name)
    return found[-1] if found else None


def missing_ranges(store: Store, symbol: str, tf: str, start: int, end: int) -> list[tuple]:
    """Tramos [a, b) que faltan en la copia: antes del primer dato, los huecos y la cola."""
    step = tf_ms(tf)
    start -= start % step
    bounds = store.bounds(symbol, tf)
    if bounds is None:
        return [(start, end)]
    out = [(start, bounds[0])] if bounds[0] > start else []
    out += [(g0, g1 + step) for g0, g1 in store.find_gaps(symbol, tf)]
    out.append((bounds[1] + step, end))
    return [(a, b) for a, b in out if a < b]


def fetch_tf(store: Store, prov: BinanceFutures, symbol: str, tf: str, start: int, end: int,
             batch_rows: int, log) -> dict:
    """Descarga y guarda las velas que falten del marco `tf`. Devuelve el resumen de la pasada."""
    step = tf_ms(tf)
    span = WINDOW_BARS * step
    pending: list[Candle] = []
    fetched = calls = 0
    t0 = time.perf_counter()

    def flush() -> None:
        nonlocal pending
        if pending:
            store.upsert_candles(symbol, tf, pending, prov.name)
            pending = []

    for a, b in missing_ranges(store, symbol, tf, start, end):
        cursor = a
        while cursor < b:
            hi = min(cursor + span, b)
            got = prov.klines(symbol, tf, cursor, hi)
            calls += 1
            pending += got
            fetched += len(got)
            cursor = hi
            if len(pending) >= batch_rows:
                flush()
                log(f"  {tf}: {fetched} velas, hasta {iso(cursor)} "
                    f"({time.perf_counter() - t0:.0f} s)")
    flush()
    return {"fetched": fetched, "calls": calls, "seconds": round(time.perf_counter() - t0, 1)}


def fetch_funding(store: Store, prov: BinanceFutures, symbol: str, start: int, end: int) -> dict:
    """Funding desde `start` (el tramo que falte por delante del último guardado)."""
    have = store.read_series("funding", symbol)
    frm = have[-1][0] + 1 if have else start
    rows = prov.funding_rates(symbol, frm, end) if frm < end else []
    if rows:
        store.upsert_series("funding", symbol, "-", rows, prov.name)
    return {"fetched": len(rows), "from": iso(frm)}


def coverage(store: Store, symbol: str, tfs: tuple[str, ...], start: int, end: int) -> dict:
    """Cobertura REAL por serie en la copia: filas, esperadas, huecos y proveedor."""
    out: dict[str, dict] = {}
    for tf in tfs:
        step = tf_ms(tf)
        bounds = store.bounds(symbol, tf)
        rows = store.count(symbol, tf)
        gaps = store.find_gaps(symbol, tf)
        expect = max(0, (end - start) // step)
        out[tf] = {
            "from": iso(bounds[0] if bounds else None), "to": iso(bounds[1] if bounds else None),
            "rows": rows, "expected_in_window": expect,
            "coverage": round(rows / expect, 6) if expect else None,
            "gaps": len(gaps), "missing_bars": sum((b - a) // step + 1 for a, b in gaps),
            "worst_gap_bars": max(((b - a) // step + 1 for a, b in gaps), default=0),
            "source": store.source("candles", symbol, tf),
        }
    f = store.read_series("funding", symbol)
    out["funding"] = {"from": iso(f[0][0] if f else None), "to": iso(f[-1][0] if f else None),
                      "rows": len(f), "expected_in_window": (end - start) // (8 * 3_600_000),
                      "source": store.source("funding", symbol, "-")}
    return out


def render(meta: dict) -> str:
    """Cobertura en markdown (la cifra de cada serie con su fuente; nada supuesto)."""
    cov = meta["coverage"]
    lines = [f"# T131 — cobertura de la copia `{meta['out']}`", "",
             f"Reconstruida el {meta['built']} desde `{meta['provider']}` para "
             f"**{meta['symbol']}** en la ventana {meta['from']} → {meta['to']}.",
             f"Contextos: `{meta['paper_src'] or 'no copiado'}`.", "",
             "| Serie | Desde | Hasta | Filas | Esperadas | Cobertura | Huecos | Velas que "
             "faltan | Hueco mayor | Proveedor |", "|---|---|---|--:|--:|--:|--:|--:|--:|---|"]
    for name, c in cov.items():
        pct = "—" if c.get("coverage") is None else f"{c['coverage']:.2%}"
        lines.append(
            f"| {name} | {c['from'] or '—'} | {c['to'] or '—'} | {c['rows']} | "
            f"{c['expected_in_window']} | {pct} | {c.get('gaps', '—')} | "
            f"{c.get('missing_bars', '—')} | {c.get('worst_gap_bars', '—')} | "
            f"{c['source'] or '—'} |")
    lines += ["", "Las velas que faltan son las que el proveedor no devolvió (paradas del "
              "exchange): quedan como hueco declarado, nunca rellenadas.", ""]
    for tf, r in meta["runs"].items():
        lines.append(f"- {tf}: {r}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="carpeta de la copia (fuera de data/)")
    ap.add_argument("--from", dest="frm", default="2023-01-01")
    ap.add_argument("--to", default="", help="por defecto, ahora")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--timeframes", nargs="+", default=list(TFS))
    ap.add_argument("--batch", type=int, default=BATCH_ROWS)
    ap.add_argument("--paper", default="", help="paper.duckdb a copiar (contextos)")
    ap.add_argument("--backups", default="backups")
    ap.add_argument("--no-funding", action="store_true")
    a = ap.parse_args()

    out = Path(a.out)
    if out.resolve() == Path("data").resolve():
        print("la copia no puede ser el almacen vivo", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    start, end = ms(a.frm), ms(a.to) if a.to else int(time.time() * 1000)

    def log(msg: str) -> None:
        print(msg, flush=True)

    dst = out / "paper.duckdb"
    src = Path(a.paper) if a.paper else newest_backup(Path(a.backups))
    if src is not None and src.exists() and not dst.exists():
        log(f"contextos: copiando {src} -> {dst}")
        shutil.copy2(src, dst)
    elif not dst.exists():
        log("AVISO: sin paper.duckdb en la copia: no habra contextos ni ideas")

    store, prov = Store(out), BinanceFutures()
    runs = {}
    for tf in a.timeframes:
        log(f"{a.symbol} {tf}: {iso(start)} -> {iso(end)}")
        runs[tf] = fetch_tf(store, prov, a.symbol, tf, start, end, a.batch, log)
        log(f"  {tf}: {runs[tf]}")
    if not a.no_funding:
        runs["funding"] = fetch_funding(store, prov, a.symbol, start, end)
        log(f"  funding: {runs['funding']}")

    meta = {"out": str(out), "symbol": a.symbol, "from": iso(start), "to": iso(end),
            "built": iso(int(time.time() * 1000)), "provider": prov.name,
            "paper_src": str(src) if src is not None and dst.exists() else None,
            "runs": runs, "coverage": coverage(store, a.symbol, tuple(a.timeframes), start, end)}
    (out / "cobertura.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    (out / "cobertura.md").write_text(render(meta), encoding="utf-8")
    log(f"cobertura en {out / 'cobertura.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
