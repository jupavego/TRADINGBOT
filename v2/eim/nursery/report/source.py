"""Entradas del informe de la cantera (T172): el libro, el precio y los regímenes. Solo lectura.

El libro vive en `data/paper_cantera.duckdb`, que tiene abierto el servicio del bróker (DuckDB
admite un solo proceso escritor; en Windows otro proceso no puede ni leerlo). Por eso se intenta,
en orden: la base que se pida (`--db`), la viva en solo lectura y, si está bloqueada, la de la copia
de seguridad más reciente (`backups/eim_*/paper_cantera.duckdb`, que la API copia en caliente cada
día). El informe dice siempre de cuál salió y de qué hora es su última operación.

El precio para comprar y mantener sale del almacén Parquet (lectura sin bloqueo) y los regímenes,
que solo pide la mirada final (d con signo coherente en ≥ 2 regímenes), del `paper.duckdb` que
acompaña a la base usada. Sin ellos se sigue y se avisa.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from eim.nursery.ladder_stats import DAY_MS
from eim.nursery.params import NurseryParams
from eim.nursery.prereg import Prereg
from eim.nursery.report.rows import Snapshot

DB_NAME = "paper_cantera.duckdb"
TRADE_COLS = ("account_id", "t", "side", "booked", "status", "reason", "fill_t", "fill",
              "exit_t", "exit", "qty", "risk_usd", "balance_before", "pnl_usd", "r", "cost_r",
              "markout_bps", "twin_k", "twin_long", "twin_r_long", "twin_r_short",
              "twin_mean_r", "d_r", "maker")
ACCOUNT_COLS = ("account_id", "kind", "prospect_id", "fingerprint", "timeframe",
                "registered_ms")


def _open(path: Path):
    import duckdb

    return duckdb.connect(str(path), read_only=True)


def candidates(data_dir: Path, backup_dir: Path, db: Path | None) -> list[Path]:
    """Bases a probar, en orden: la pedida; si no, la viva y las copias, de la más nueva."""
    if db is not None:
        return [db]
    backups = sorted(backup_dir.glob(f"eim_*/{DB_NAME}"), reverse=True) \
        if backup_dir.exists() else []
    return [data_dir / DB_NAME, *backups]


def open_book(paths: list[Path], opener: Callable = _open):
    """(conexión, ruta) de la primera base que abra; los fallos se acumulan en el error."""
    errors = []
    for p in paths:
        if not p.exists():
            errors.append(f"{p}: no existe")
            continue
        try:
            return opener(p), p
        except Exception as exc:            # noqa: BLE001 — bloqueada: se prueba la siguiente
            errors.append(f"{p}: {type(exc).__name__}: {exc!s:.120}")
    raise FileNotFoundError("no se pudo abrir el libro de la cantera: " + " | ".join(errors))


def read_book(con, pr: Prereg) -> tuple[int | None, list[dict], list[dict], list[dict]]:
    """(alta, cuentas, operaciones, eventos) tal como los guarda `nursery/store.py`."""
    alta = con.execute("SELECT alta_ms FROM nursery_prereg WHERE version = ? AND sha256 = ?",
                       [pr.version, pr.sha256]).fetchall()
    accounts = [dict(zip(ACCOUNT_COLS, r, strict=True)) for r in con.execute(
        f"SELECT {', '.join(ACCOUNT_COLS)} FROM nursery_accounts").fetchall()]
    trades = [dict(zip(TRADE_COLS, r, strict=True)) for r in con.execute(
        f"SELECT {', '.join(TRADE_COLS)} FROM nursery_trades").fetchall()]
    events = [json.loads(p) for (p,) in con.execute(
        "SELECT payload FROM nursery_events ORDER BY t").fetchall()]
    return (int(alta[0][0]) if alta else None), accounts, trades, events


def regimes(paper_db: Path, symbol: str, tfs: set[str], start: int,
            opener: Callable = _open) -> dict[str, dict[int, str]] | None:
    """Etiqueta de `regime` de cada contexto (para la mirada final); None si no se puede leer."""
    if not paper_db.exists():
        return None
    try:
        con = opener(paper_db)
    except Exception:                       # noqa: BLE001 — bloqueada: se sigue sin regímenes
        return None
    try:
        out: dict[str, dict[int, str]] = {}
        for tf in sorted(tfs):
            rows = con.execute("SELECT asof_ms, json_extract_string(ctx, '$.regime') FROM "
                               "paper_ctx WHERE symbol = ? AND timeframe = ? AND asof_ms >= ?",
                               [symbol, tf, int(start)]).fetchall()
            out[tf] = {int(t): r for t, r in rows if r}
        return out
    finally:
        con.close()


def buy_hold(data_dir: Path, symbol: str, alta: int, asof: int, tf: str = "15m",
             sl_atr: float | None = None) -> dict | None:
    """Comprar y mantener desde el alta: en % y en unidades de riesgo (1 R = 1,5 ATR de 15 m)."""
    from eim.data.store import Store
    from eim.data.timeframes import tf_ms
    from eim.indicators.volatility import atr

    k = sl_atr if sl_atr is not None else NurseryParams().sl_atr
    try:
        a = Store(data_dir).read_arrays(symbol, tf, start=alta - 40 * tf_ms(tf))
    except Exception:                       # noqa: BLE001 — sin velas: sin comprar y mantener
        return None
    t = np.asarray(a["t"])
    if not len(t):
        return None
    j0 = int(np.searchsorted(t, alta))
    j1 = int(np.searchsorted(t, asof, side="right")) - 1
    if j0 >= len(t) or j1 <= j0:
        return None
    w = atr(a["h"][:j0 + 1], a["l"][:j0 + 1], a["c"][:j0 + 1])
    risk = k * float(w[-1]) if len(w) and np.isfinite(w[-1]) else 0.0
    p0, p1 = float(a["o"][j0]), float(a["c"][j1])
    return {"from_t": int(t[j0]), "to_t": int(t[j1]), "price_from": p0, "price_to": p1,
            "return_pct": round((p1 / p0 - 1) * 100, 3),
            "r_long": round((p1 - p0) / risk, 3) if risk > 0 else None,
            "r_short": round((p0 - p1) / risk, 3) if risk > 0 else None,
            "basis": f"1 R = {k:g} ATR({tf}) en el alta"}


def now_ms() -> int:
    return int(time.time() * 1000)


def copy_time(db: Path) -> int | None:
    """Hora de una copia `eim_AAAAMMDD-HHMMSS` (UTC) por su carpeta; None si no lo es."""
    try:
        stamp = db.parent.name.removeprefix("eim_")[:15]
        return int(datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
                   .timestamp() * 1000)
    except ValueError:
        return None


def load(pr: Prereg, data_dir: Path, backup_dir: Path, db: Path | None = None,
         asof_ms: int | None = None, with_regimes: bool | None = None,
         opener: Callable = _open) -> Snapshot:
    """El `Snapshot` del informe a partir de la primera base de la cantera que se pueda leer.

    `with_regimes=None` los lee solo si la lectura llega a la fecha límite (mirada final).
    """
    con, used = open_book(candidates(data_dir, backup_dir, db), opener)
    try:
        alta, accounts, trades, events = read_book(con, pr)
    finally:
        con.close()
    warnings = []
    if alta is None:
        raise ValueError(f"{used} no tiene alta de {pr.version} con la huella publicada: la "
                         "cantera no ha arrancado con este pre-registro")
    taken = copy_time(used) if used.parent != data_dir else None
    asof = asof_ms if asof_ms is not None else taken if taken is not None else now_ms()
    if used.parent != data_dir:
        warnings.append(f"libro leído de la copia {used.parent.name} (la base viva estaba en "
                        "uso o no existe): las cifras llegan hasta la hora de esa copia")
    regs = None
    final = asof >= alta + pr.ladder.deadline_days * DAY_MS
    if with_regimes if with_regimes is not None else final:
        regs = regimes(used.parent / "paper.duckdb", pr.symbol,
                       {a["timeframe"] for a in accounts if a.get("timeframe")}, alta, opener)
        if regs is None:
            warnings.append("sin regímenes (paper.duckdb no legible): el criterio de ≥ 2 "
                            "regímenes de la mirada final no se puede comprobar")
    bh = buy_hold(data_dir, pr.symbol, alta, asof)
    if bh is None:
        warnings.append("sin velas de 15 m en el almacén: comprar y mantener sin medir")
    return Snapshot(pr, alta, asof, accounts, trades, events, bh, regs, str(used), warnings)
