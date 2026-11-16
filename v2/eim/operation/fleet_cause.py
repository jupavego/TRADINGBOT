"""Las tres razones por las que relanzar no sirve de nada (T173).

El 2026-11-10 el vigilante del conjunto (T148) hizo exactamente lo que se le pidió y no sirvió de
nada. El bróker simulado dejó de latir a las ~20:05 y él lo detectó a las 20:19:22; gastó sus
cuatro intentos (20:19, 20:24, 20:44, 21:14) y se rindió a las 21:19. Los cuatro estaban perdidos
de antemano por tres motivos distintos, y el conjunto no sabía ninguno:

1. **Había una causa externa en marcha.** De 20:07:55 a 23:46:33 UTC este equipo se quedó sin
   resolución de nombres: 164 `datos_fallidos` con `red: ... getaddrinfo failed`. El EIM ya lo
   había dicho en una alerta crítica `desconexion:BTCUSDT` a las **20:12:03**, siete minutos antes
   del primer intento. Un proceso bloqueado esperando red tiene el mismo síntoma que uno muerto
   —el latido parado— y el remedio opuesto: esperar, no relanzar.
2. **El servicio vive dentro de otro.** El bróker simulado es una tarea del proceso de la API
   (`eim/paper/service.py`). Con la API viva escuchando en el 8000, `servicio_continuo.ps1` no
   lanza nada (su guardia de idempotencia), así que devolvió `rc=0` cuatro veces sin tocar nada.
   Levantarlo exige reiniciar la API, y eso **no se hace solo**: ahí vive la corrida de T31
   (`v2/docs/RUNBOOK.md` §16).
3. **Un latido fresco no prueba que haya datos.** La captura HFT siguió latiendo cada ~28 s durante
   todo el corte y las horas 21 y 22 salieron con `runs: 0` y `book_usable 0.0`. Relanzar a quien
   ya late no arregla que no produzca.

Todo lo que hay aquí **solo lee** lo que el EIM ya escribió; nada de esto decide ni actúa. Se lee
la cola del registro de operación en vez del archivo entero (400 KB al día) porque esta pasada
corre cada 5 minutos, y se construyen las rutas del QC a mano en vez de importar
`eim.data.collectors.qc` para no arrastrar numpy y pandas en cada pasada.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

NET_MARK = "red: "          # el marcador que ponen los proveedores del EIM a un error de red
NET_WINDOW_S = 900.0        # fallos de red más viejos que esto ya no cuentan como «en marcha»
NET_HOUR_S = 120.0          # corte de red dentro de una hora desde el que la hora es nuestra
TAIL_BYTES = 262_144        # cola del registro del día: ~1,5 h de operación normal
DISCONNECT = "desconexion"
NO_BOOK = 0.50              # libro útil por debajo de esto, con el latido al día, es no producir
# Servicios que no tienen proceso propio: viven dentro de otro, así que el guion de arranque no
# puede levantarlos por separado (T173 E3). El valor es el servicio que los aloja.
INSIDE = {"bróker simulado": "API"}


def _tail_rows(path: Path, tail_bytes: int = TAIL_BYTES) -> list[dict]:
    """Las últimas líneas legibles de un JSONL, sin cargarlo entero.

    La primera línea del trozo puede venir cortada por la mitad: se descarta."""
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > tail_bytes:
                f.seek(size - tail_bytes)
                f.readline()
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for line in raw.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("t"), (int, float)):
            out.append(row)
    return out


def ops_days(data_dir: Path, days: list[str]) -> list[dict]:
    """Los eventos COMPLETOS de los días pedidos, para reatribuir el pasado (T173 E5).

    Aquí no se lee la cola: una reatribución tiene que ver todo el día, y corre a mano, no cada
    5 minutos."""
    logs = Path(data_dir) / "operation" / "logs"
    rows: list[dict] = []
    for day in days:
        rows += _tail_rows(logs / f"op-{day}.jsonl", tail_bytes=1 << 62)
    rows.sort(key=lambda r: r["t"])
    return rows


def local_net_spans(rows: list[dict], join_s: float = 600.0) -> list[dict]:
    """Los tramos en que la red de ESTE equipo estuvo caída, según lo que el EIM ya anotó.

    Se arman con los `datos_fallidos` que llevan el marcador `red: ` de los proveedores: fallos
    separados por menos de `join_s` son el mismo corte. El final se estira hasta el «Resuelta» de
    la alerta `desconexion` si cae dentro del corte, porque ese es el instante en que de verdad
    volvió la red (el 2026-11-10, las 23:46:33).

    No se usan las alertas `desconexion` por sí solas: esas saltan igual cuando el que se calla es
    el exchange, y separar las dos cosas es justamente lo que hace falta."""
    fails = sorted(r["t"] for r in rows if r.get("event") == "datos_fallidos"
                   and NET_MARK in str(r.get("error") or ""))
    spans: list[dict] = []
    for t in fails:
        if spans and t - spans[-1]["t1"] <= join_s * 1000:
            spans[-1]["t1"], spans[-1]["fails"] = t, spans[-1]["fails"] + 1
        else:
            spans.append({"t0": t, "t1": t, "fails": 1})
    cleared = [r["t"] for r in rows if r.get("event") == "alerta"
               and r.get("kind") == DISCONNECT and r.get("resolved")]
    for sp in spans:
        for t in cleared:
            if sp["t1"] <= t <= sp["t1"] + join_s * 1000:
                sp["t1"] = max(sp["t1"], t)
    return spans


def net_hours(spans: list[dict], min_s: float = NET_HOUR_S) -> set[int]:
    """Horas UTC (índice de hora desde la época) con al menos `min_s` de corte de red local.

    Mismo índice que el `hour_index` del QC, para poder cruzarlos."""
    out: set[int] = set()
    for sp in spans:
        t0, t1 = int(sp["t0"]), int(sp["t1"])
        for h in range(t0 // 3_600_000, t1 // 3_600_000 + 1):
            if min(t1, (h + 1) * 3_600_000) - max(t0, h * 3_600_000) >= min_s * 1000:
                out.add(h)
    return out


def local_net_hours(root: Path | str, now_s: float, days: int = 45) -> set[int]:
    """Horas con un corte de la red de este equipo en los últimos `days` días (T173 E5).

    Lo usa la atribución de T78 (`hft_ops.window`). Nunca lanza: sin registro de operación
    devuelve un conjunto vacío y la atribución se queda con las demás señales."""
    try:
        now_ms = int(now_s * 1000)
        first = now_ms - (days - 1) * 86_400_000
        day_list = sorted({time.strftime("%Y-%m-%d", time.gmtime((first + i * 86_400_000) / 1000))
                           for i in range(days)})
        return net_hours(local_net_spans(ops_days(Path(root), day_list)))
    except Exception:  # noqa: BLE001 - una atribución sin esta señal es peor, no imposible
        return set()


def recent_ops(data_dir: Path, now_s: float) -> list[dict]:
    """Eventos recientes del registro de operación (hoy y, en el cambio de día, ayer)."""
    logs = Path(data_dir) / "operation" / "logs"
    rows: list[dict] = []
    for off in (86_400, 0):
        day = time.strftime("%Y-%m-%d", time.gmtime(now_s - off))
        rows += _tail_rows(logs / f"op-{day}.jsonl")
    rows.sort(key=lambda r: r["t"])
    return rows


# ------------------------------------------------------------------- (1) hay una causa externa

def network_cause(rows: list[dict], now_ms: int, window_s: float = NET_WINDOW_S,
                  trust_open_alert: bool = True) -> dict | None:
    """¿Hay un corte de red en marcha, según lo que el EIM ya anotó? (None si no).

    Dos señales, y basta una:

    - una alerta `desconexion:<símbolo>` **abierta**: la emitió el ciclo de operación al pasar su
      umbral y todavía no ha llegado su «Resuelta»;
    - `datos_fallidos` con el marcador de red de los proveedores (`red: `) en los últimos
      `window_s`: cubre el rato que va desde que la red falla hasta que la alerta salta (el
      2026-11-10 fueron 4 min), y también los cortes demasiado cortos para alertar.

    `since_ms` es desde cuándo, para poder decirlo en el aviso sin volver a leer nada.
    `trust_open_alert=False` ignora la alerta abierta: si la API murió con ella abierta, nadie la
    va a cerrar, y tomarla por un corte en marcha dejaría al conjunto sin levantar para siempre."""
    open_since: int | None = None
    by_key: dict[str, dict] = {}
    for r in rows:
        if r.get("event") == "alerta" and r.get("kind") == DISCONNECT and r.get("key"):
            by_key[r["key"]] = r
    for r in by_key.values() if trust_open_alert else ():
        if not r.get("resolved"):
            open_since = r["t"] if open_since is None else min(open_since, r["t"])
    fails = [r for r in rows if r.get("event") == "datos_fallidos"
             and NET_MARK in str(r.get("error") or "")
             and now_ms - r["t"] <= window_s * 1000]
    if open_since is None and not fails:
        return None
    since = min([x for x in (open_since, fails[0]["t"] if fails else None) if x is not None])
    detail = (str(fails[-1].get("error"))[:160] if fails else
              "alerta de desconexión abierta en el registro de operación")
    return {"kind": "red", "since_ms": since, "alert_open": open_since is not None,
            "fails": len(fails), "detail": detail,
            "for_s": round((now_ms - since) / 1000, 1)}


# ------------------------------------------------------------- (2) el servicio vive dentro de otro

def not_liftable(down: list[str], seen: dict[str, float | None], down_s: float) -> list[str]:
    """De los que faltan, los que el guion de arranque no puede levantar: viven dentro de otro
    que está vivo. Si el anfitrión también falta, levantarlo sí sirve (arrastra a sus hijos)."""
    return [k for k in down if (host := INSIDE.get(k)) is not None
            and host in seen and seen[host] is not None and seen[host] < down_s]


def host_hint(names: list[str]) -> str:
    """Qué haría falta de verdad, para decirlo en el aviso en vez de callarlo."""
    hosts = sorted({INSIDE[k] for k in names if k in INSIDE})
    return (f"{', '.join(names)} corre dentro de {', '.join(hosts)}: el guion de arranque no puede "
            f"levantarlo por separado y hay que reiniciar {', '.join(hosts)} a mano "
            f"(RUNBOOK §16); no se hace solo porque ahí vive la corrida de T31")


# -------------------------------------------------------- (3) late pero no produce (captura HFT)

def _qc_path(data_dir: Path, symbol: str, hour_ms: int) -> Path:
    day = time.strftime("%Y-%m-%d", time.gmtime(hour_ms / 1000))
    hh = time.strftime("%H", time.gmtime(hour_ms / 1000))
    return (Path(data_dir) / "micro_hft" / "qc" / f"symbol={symbol}" / f"date={day}"
            / f"hour={hh}.json")


def not_producing(data_dir: Path, now_s: float, symbol: str = "BTCUSDT",
                  floor: float = NO_BOOK) -> dict | None:
    """La captura late pero la última hora auditada no trajo datos (None si todo bien).

    Se mira la hora cerrada más reciente que ya tenga QC (se audita con unos minutos de margen),
    y solo las dos últimas: más atrás es historia, no un aviso."""
    hour_ms = (int(now_s * 1000) // 3_600_000) * 3_600_000
    for back in (1, 2):
        p = _qc_path(Path(data_dir), symbol, hour_ms - back * 3_600_000)
        try:
            rep = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        usable, runs = rep.get("book_usable"), rep.get("runs")
        if runs == 0 or (isinstance(usable, (int, float)) and usable < floor):
            return {"hour": rep.get("hour"), "book_usable": usable, "runs": runs,
                    "detail": (f"la hora {rep.get('hour')} cerró con libro útil "
                               f"{(usable or 0) * 100:.0f} % y {runs} corridas, con el latido al "
                               f"día: late pero no captura")}
        return None
    return None
