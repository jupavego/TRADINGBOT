"""Instantáneas de la vista del bróker simulado (T118): la foto que se mostró, para auditarla.

La vista se RECALCULA desde todo el almacén en cada consulta (T106 A4), así que una cifra de ayer
no se puede volver a obtener recalculando. Cada cálculo de la vista guarda aquí, solo adición
(`INSERT OR IGNORE`), la foto de lo que muestra el panel: capital y cuenta de cada perfil,
operaciones contadas con su origen, alcance (tramo, techo y huecos), conciliación con el libro
fijo, rechazos por código, versiones de parámetros y de código, estado del almacén y sello de
tiempo. El identificador es la huella SHA-256 del contenido (12 hex): pedirlo devuelve exactamente
las mismas cifras y, al leer, se vuelve a calcular la huella (`intact`), así que una fila alterada
se delata sola. El contenido se guarda como JSON canónico comprimido con zlib (≈ 2,7 KB por foto
frente a ≈ 16 KB en texto, medido en T118 con la vista real de BTCUSDT; con ≈ 200 cálculos al día
son ≈ 16 MB al mes): la huella es la del JSON, no la del comprimido.

Las instantáneas son de ESTA máquina: la experiencia compartida (T61) no las lleva. Todo SIMULADO.
"""

from __future__ import annotations

import hashlib
import json
import math
import zlib
from typing import Any

from eim.data.paper_store import PaperStore

DDL = ("CREATE TABLE IF NOT EXISTS paper_view_snapshot (snapshot_id VARCHAR PRIMARY KEY, "
       "symbol VARCHAR, computed_ms BIGINT, recorded_ms BIGINT, closed VARCHAR, body BLOB)")
# cifras de cada perfil que muestra el panel (tarjeta, cuenta y pestaña Perfiles)
PROFILE_KEYS = ("id", "name", "initial", "balance", "equity", "upnl", "realized", "return_pct",
                "return_base", "max_dd_pct", "dd", "n_closed", "win_rate", "pf", "avg_r", "best",
                "worst", "fees", "slip", "funding", "exhausted", "exhausted_t", "min_equity",
                "margin_used", "reserved", "available", "counts")
TOP_KEYS = ("mode", "symbol", "timeframes", "path_tf", "now", "mark", "coverage", "scope",
            "sources")


def ensure(pstore: PaperStore) -> None:
    pstore.execute(DDL)


def _clean(x: Any) -> Any:
    """JSON estricto: un número no finito no tiene representación estable (se guarda null)."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_clean(v) for v in x]
    return x


def canonical(body: dict) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def pack(body: dict) -> bytes:
    return zlib.compress(canonical(body).encode("utf-8"), 9)


def unpack(raw: bytes) -> dict:
    return json.loads(zlib.decompress(raw).decode("utf-8"))


def digest(body: dict) -> str:
    """Identificador de la instantánea: huella de su contenido."""
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()[:12]


def photo(summary: dict, computed: int, versions: dict, data: dict) -> dict:
    """La foto de una vista: sus cifras tal como las sirve `GET /v2/paper` (función pura)."""
    profiles = [{**{k: p.get(k) for k in PROFILE_KEYS}, "open": len(p.get("positions", ())),
                 "pending": len(p.get("orders", ()))} for p in summary.get("profiles", ())]
    return _clean({**{k: summary.get(k) for k in TOP_KEYS}, "computed": computed,
                   "versions": versions, "data": data, "profiles": profiles})


def record(pstore: PaperStore, body: dict, now: int) -> str:
    """Guarda la foto (nunca reemplaza) y devuelve su identificador."""
    sid = digest(body)
    closed = {p["id"]: p["n_closed"] for p in body["profiles"]}
    pstore.execute("INSERT OR IGNORE INTO paper_view_snapshot VALUES (?, ?, ?, ?, ?, ?)",
                   [sid, body["symbol"], int(body["computed"]), now,
                    json.dumps(closed, sort_keys=True), pack(body)])
    return sid


def get(pstore: PaperStore, sid: str) -> dict | None:
    rows = pstore.execute("SELECT symbol, computed_ms, recorded_ms, body FROM paper_view_snapshot "
                          "WHERE snapshot_id = ?", [sid])
    if not rows:
        return None
    symbol, computed, recorded, raw = rows[0]
    try:
        body = unpack(raw)
    except (zlib.error, ValueError, TypeError):   # ilegible = alterada: se dice, no se inventa
        return {"id": sid, "symbol": symbol, "computed": int(computed), "recorded": int(recorded),
                "intact": False, "snapshot": None}
    return {"id": sid, "symbol": symbol, "computed": int(computed), "recorded": int(recorded),
            "intact": digest(body) == sid, "snapshot": body}


def listing(pstore: PaperStore, symbol: str | None = None, limit: int = 50) -> list[dict]:
    """Instantáneas más recientes primero, con las operaciones que contaba cada perfil."""
    sql = ("SELECT snapshot_id, symbol, computed_ms, recorded_ms, closed FROM paper_view_snapshot"
           + (" WHERE symbol = ?" if symbol else "") + " ORDER BY computed_ms DESC LIMIT ?")
    rows = pstore.execute(sql, [symbol, limit] if symbol else [limit])
    return [{"id": i, "symbol": s, "computed": int(c), "recorded": int(r),
             "closed": json.loads(n)} for i, s, c, r, n in rows]


def largest(pstore: PaperStore, symbol: str) -> dict[str, dict]:
    """Por perfil, la instantánea anterior que más operaciones contaba (`n`, `id`, `computed`)."""
    best: dict[str, dict] = {}
    for sid, computed, closed in pstore.execute(
            "SELECT snapshot_id, computed_ms, closed FROM paper_view_snapshot WHERE symbol = ?",
            [symbol]):
        for pid, n in json.loads(closed).items():
            if n > best.get(pid, {}).get("n", -1):
                best[pid] = {"n": int(n), "id": sid, "computed": int(computed)}
    return best
