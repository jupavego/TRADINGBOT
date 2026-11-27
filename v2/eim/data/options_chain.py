"""Colector de baja frecuencia de las cadenas de opciones de Deribit (T213). Todo el I/O aquí.

Fuente aprobada por el usuario a nivel 1 (◆ de T213, `PLAN/notas/T213_terminos.md`): solo uso
personal, nada se publica ni se reenvía. Solo información sobre la volatilidad: no se operan
opciones y nada de esto toca síntesis, plan, riesgo ni bróker.

Cada toma es **una** llamada por moneda (`DeribitPublic.option_book_summary`) y deja dos archivos:

    data/options/<MONEDA>/<AAAA-MM-DD>/<HH>.jsonl.gz      una fila por opción viva (UTC)
    data/options/<MONEDA>/<AAAA-MM-DD>/<HH>.quality.json  calidad por vencimiento y metadatos

Se escriben con un nombre temporal y se renombran: una toma está entera o no está. Si la hora
ya tiene toma, no se repite (la tarea programada puede relanzarse sin duplicar). No arranca
ningún servicio: se lanza desde `scripts/opciones_colector.ps1` (tarea programada, prioridad de
lote) o a mano:

    python -m eim.data.options_chain snapshot --data data --currency BTC
    python -m eim.data.options_chain measure --currency BTC,ETH      (volumen, sin guardar nada)
    python -m eim.data.options_chain record-fixture --out tests/fixtures/options/x.json
    python -m eim.data.options_chain coverage --data data --currency BTC
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from eim.data.options_parse import by_expiry, normalize, parse_name, snapshot_quality
from eim.data.providers.deribit import BASE_URL, BOOK_PATH, DeribitPublic

SOURCE = "deribit-options"
DIR = "options"
UNITS = ("bid/ask/mark en la moneda base (opciones inversas de Deribit); mark_iv en %; "
         "oi en moneda base con 8 h de retraso; expiry y ts en ms UTC")
BUDGET_MB_DAY = 1.0          # presupuesto declarado de disco para las cadenas (◆ T213 §4)
CADENCES = (1, 2, 3, 4, 6, 8, 12, 24)
BACKUP_KEEP = 14             # copias diarias que se conservan (EIM_BACKUP_KEEP por defecto)
Clock = Callable[[], int]


def _now_ms() -> int:
    return int(time.time() * 1000)


def snapshot_paths(data_dir: Path, currency: str, taken_ms: int) -> tuple[Path, Path]:
    d = datetime.fromtimestamp(taken_ms / 1000, UTC)
    folder = Path(data_dir) / DIR / currency.upper() / d.strftime("%Y-%m-%d")
    return folder / f"{d:%H}.jsonl.gz", folder / f"{d:%H}.quality.json"


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def encode_rows(rows: Sequence[dict]) -> bytes:
    text = "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows)
    return gzip.compress(text.encode("utf-8"), compresslevel=9, mtime=0)


def read_rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_snapshot(raw: Sequence[dict], currency: str, taken_ms: int) -> tuple[bytes, bytes, dict]:
    """(filas comprimidas, calidad en JSON, resumen) de una respuesta cruda. Sin disco."""
    rows, dropped = normalize(raw)
    if not rows:
        raise ValueError(f"{currency}: la respuesta no trae ninguna fila completa "
                         f"({len(raw)} filas crudas, descartes {dropped})")
    q = snapshot_quality(rows, dropped, taken_ms)
    meta = {"source": SOURCE, "endpoint": BASE_URL + BOOK_PATH, "currency": currency.upper(),
            "taken_at": _iso(taken_ms), "taken_ms": taken_ms, "n_raw": len(raw), "units": UNITS,
            "level": 1, "use": "solo uso personal (◆ T213); nada se publica ni se reenvía"}
    data = encode_rows(rows)
    quality = json.dumps({**meta, **q}, ensure_ascii=False, indent=1).encode("utf-8")
    summary = {"currency": currency.upper(), "taken_at": meta["taken_at"], "rows": q["n_rows"],
               "dropped": q["n_dropped"], "expiries": q["n_expiries"], "by_status": q["by_status"],
               "bytes": len(data), "quality_bytes": len(quality)}
    return data, quality, summary


def take_snapshot(data_dir: Path, currency: str, provider: DeribitPublic | None = None,
                  clock: Clock = _now_ms, overwrite: bool = False) -> dict:
    """Toma y guarda la cadena de `currency` en la hora UTC en curso; devuelve un resumen."""
    taken = clock()
    data_path, quality_path = snapshot_paths(data_dir, currency, taken)
    if data_path.exists() and quality_path.exists() and not overwrite:
        return {"currency": currency.upper(), "taken_at": _iso(taken), "already": True,
                "path": str(data_path)}
    raw = (provider or DeribitPublic()).option_book_summary(currency)
    data, quality, summary = build_snapshot(raw, currency, taken)
    _write_atomic(data_path, data)
    _write_atomic(quality_path, quality)
    return {**summary, "already": False, "path": str(data_path)}


def choose_cadence(bytes_per_snapshot: float, budget_mb_day: float = BUDGET_MB_DAY) -> int | None:
    """Menor cadencia (horas entre tomas) que cabe en el presupuesto; `None` si ni una al día."""
    for h in CADENCES:
        if bytes_per_snapshot * 24 / h / 1e6 <= budget_mb_day:
            return h
    return None


def plan_volume(sizes: dict[str, int], budget_mb_day: float = BUDGET_MB_DAY,
                keep: int = BACKUP_KEEP) -> dict:
    """Recomendación a partir del tamaño medido de una toma por moneda (datos + calidad).

    BTC primero (es el alcance); se reduce la **frecuencia**, nunca los campos ni la calidad.
    ETH entra solo si cabe junto a BTC con la misma cadencia."""
    if "BTC" not in sizes:
        raise ValueError("hace falta medir BTC")
    hours = choose_cadence(sizes["BTC"], budget_mb_day)
    chosen = ["BTC"]
    if hours is not None and "ETH" in sizes:
        both = sizes["BTC"] + sizes["ETH"]
        if both * 24 / hours / 1e6 <= budget_mb_day:
            chosen.append("ETH")
    per_snap = sum(sizes[c] for c in chosen)
    mb_day = per_snap * 24 / hours / 1e6 if hours else None
    return {"budget_mb_day": budget_mb_day, "bytes_per_snapshot": dict(sizes),
            "currencies": chosen if hours else [], "every_hours": hours,
            "mb_day": _r2(mb_day), "mb_year": _r2(mb_day * 365 if mb_day else None),
            "backups_mb_after_one_year": _r2(mb_day * 365 * keep if mb_day else None),
            "note": (f"la copia diaria guarda todo data/options y se conservan {keep} copias: "
                     "lo de backups es la cota al cabo de un año")}


def measure(currencies: Sequence[str], provider: DeribitPublic | None = None,
            clock: Clock = _now_ms, budget_mb_day: float = BUDGET_MB_DAY) -> dict:
    """Mide una toma real por moneda **sin guardarla** y propone cadencia y monedas."""
    p = provider or DeribitPublic()
    per: dict[str, dict] = {}
    for cur in currencies:
        _, _, s = build_snapshot(p.option_book_summary(cur), cur, clock())
        per[cur.upper()] = s
    plan = plan_volume({c: s["bytes"] + s["quality_bytes"] for c, s in per.items()},
                       budget_mb_day)
    return {"measured_at": _iso(clock()), "per_currency": per, "plan": plan}


def record_fixture(out: Path, currency: str = "BTC", provider: DeribitPublic | None = None,
                   clock: Clock = _now_ms) -> dict:
    """Graba un recorte REAL de la respuesta para las pruebas sin red: todas las filas de dos
    vencimientos (el más cercano con ≥ 1 día y el primero con ≥ 20 días)."""
    taken = clock()
    raw = (provider or DeribitPublic()).option_book_summary(currency)
    rows, _ = normalize(raw)
    expiries = list(by_expiry(rows))
    near = next((e for e in expiries if e - taken >= 86_400_000), None)
    far = next((e for e in expiries if e - taken >= 20 * 86_400_000), None)
    keep = sorted({e for e in (near, far) if e is not None})
    if not keep:
        raise ValueError("no hay vencimientos con al menos un día de plazo")
    kept = [r for r in raw if (p := parse_name(str(r.get("instrument_name", ""))))
            and p[1] in keep]
    doc = {"recorded_at": _iso(taken), "recorded_ms": taken, "endpoint": BASE_URL + BOOK_PATH,
           "params": {"currency": currency.upper(), "kind": "option"},
           "note": ("recorte real grabado por aplicar_t213 (◆ T213: uso personal); todas las "
                    "filas de los vencimientos de `expiries_kept`, sin tocar"),
           "n_live_total": len(raw), "expiries_kept": [_iso(e) for e in keep], "result": kept}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"out": str(out), "rows": len(kept), "n_live_total": len(raw),
            "expiries_kept": doc["expiries_kept"]}


def coverage(data_dir: Path, currency: str) -> dict:
    """Tomas guardadas de una moneda: cuántas, primera, última y bytes en disco."""
    root = Path(data_dir) / DIR / currency.upper()
    files = sorted(root.glob("*/*.jsonl.gz")) if root.exists() else []
    if not files:
        return {"source": SOURCE, "currency": currency.upper(), "snapshots": 0, "first": None,
                "last": None, "bytes": 0}
    stamp = [f"{f.parent.name}T{f.name[:2]}:00Z" for f in files]
    size = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    return {"source": SOURCE, "currency": currency.upper(), "snapshots": len(files),
            "first": stamp[0], "last": stamp[-1], "bytes": size}


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _r2(x: float | None) -> float | None:
    return None if x is None else round(x, 2)


def _currencies(s: str) -> list[str]:
    return [c.strip().upper() for c in s.split(",") if c.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eim.data.options_chain", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot", help="toma y guarda la cadena de la hora en curso")
    s.add_argument("--data", required=True, type=Path)
    s.add_argument("--currency", default="BTC")
    s.add_argument("--overwrite", action="store_true")
    m = sub.add_parser("measure", help="mide el volumen de una toma sin guardarla")
    m.add_argument("--currency", default="BTC,ETH")
    m.add_argument("--budget-mb-dia", type=float, default=BUDGET_MB_DAY)
    f = sub.add_parser("record-fixture", help="graba un recorte real para las pruebas")
    f.add_argument("--out", required=True, type=Path)
    f.add_argument("--currency", default="BTC")
    c = sub.add_parser("coverage", help="tomas guardadas")
    c.add_argument("--data", required=True, type=Path)
    c.add_argument("--currency", default="BTC")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):          # consola de Windows (cp1252)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.cmd == "snapshot":
        p = DeribitPublic()
        out: object = [take_snapshot(a.data, cur, p, overwrite=a.overwrite)
                       for cur in _currencies(a.currency)]
    elif a.cmd == "measure":
        out = measure(_currencies(a.currency), budget_mb_day=a.budget_mb_dia)
    elif a.cmd == "record-fixture":
        out = record_fixture(a.out, a.currency.upper())
    else:
        out = [coverage(a.data, cur) for cur in _currencies(a.currency)]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
