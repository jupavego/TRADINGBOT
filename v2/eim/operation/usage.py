"""Registro de consumo del equipo (T127, entregable 1).

Cada 30 s anota la CPU, la RAM privada y la prioridad de cada parte del EIM, de los programas
que más gastan aparte del EIM y del equipo entero, más el estado de la cola de la captura HFT.
Lo escribe en `data/usage/AAAA-MM-DD.jsonl` (fuera de `data/operation`, que la copia diaria
copia entero), comprime los días cerrados y conserva 30. Sirve para saber, cuando la captura
pierde una hora, si el equipo estaba saturado y quién lo saturaba (`usage_summary.py`).

Quién es quién sin la línea de órdenes (la de los servicios de la sesión 0 no se lee desde la
sesión del usuario): el archivo `obs/spool/<papel>.<día>.<pid>.jsonl` de cada proceso Python
del EIM, si se escribió después de nacer el proceso (un PID reutilizado no hereda el papel);
el dueño de los puertos 8000 (API), 5173 (interfaz) y 8765 (hoja de ruta), y el parentesco:
un `python.exe` cuyo único hijo Python tiene papel es su lanzador del venv (casi no reserva
memoria) o su vigilante (`watchdog`, `micro_watchdog`, `hft_watchdog`, que casi no emiten
eventos); los `cmd`/`node` sobre la interfaz y los hijos de un proceso del EIM heredan su
papel. «Equipo despierto» y el icono (PowerShell; apenas gastan) cuentan entre los demás.

    python -m eim.operation.usage run [--every 30] [--keep-days 30]   # el servicio
    python -m eim.operation.usage run --once                           # una muestra, a mano
    python -m eim.operation.usage summary [--days 7]                   # resumen por día
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from eim.observability import hooks_service
from eim.observability.emit import configure
from eim.operation import usage_win
from eim.operation.priority import apply_role
from eim.operation.usage_win import Proc
from eim.operation.watchdog import instance_lock

COMPONENT = "operation.usage"
EVERY_S = 30
KEEP_DAYS = 30
TOP = 5                                    # programas ajenos al EIM que se anotan por CPU
PORT_ROLES = {8000: "api", 5173: "web", 8765: "roadmap"}
NAME_ROLES = {"ollama.exe": "ollama", "ollama_llama_server.exe": "ollama"}
WATCHDOG_OF = {"collector": "micro_watchdog", "hft_collector": "hft_watchdog"}  # si no, watchdog
PYTHON = ("python.exe", "pythonw.exe")
LAUNCHER_MAX_COMMIT = 4 << 20              # el lanzador del venv reserva < 1 MB; Python, > 10 MB
_WEB_UP = ("cmd.exe", "node.exe")          # padres de la interfaz que comparten su papel


def usage_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "usage"


def spool_roles(spool: Path, procs: Mapping[int, Proc]) -> dict[int, str]:
    """PID → papel según los archivos de observabilidad de los procesos vivos."""
    out: dict[int, str] = {}
    try:
        entries = list(os.scandir(spool))
    except OSError:
        return out
    for e in entries:
        role, _, pid = e.name.removesuffix(".jsonl").rpartition(".")
        role = role.rpartition(".")[0]
        p = procs.get(int(pid)) if pid.isdigit() else None
        if not role or p is None or p.name.lower() not in PYTHON:
            continue
        try:
            if e.stat().st_mtime >= p.created_s - 1:
                out[p.pid] = role
        except OSError:
            continue
    return out


def attribute(procs: Mapping[int, Proc], spool: Mapping[int, str],
              ports: Mapping[int, int]) -> dict[int, str]:
    """PID → papel de cada proceso del EIM (los que no aparecen son del resto del equipo)."""
    roles = dict(spool)
    for pid, p in procs.items():
        if (r := NAME_ROLES.get(p.name.lower())) and pid not in roles:
            roles[pid] = r
    for port, pid in ports.items():
        if pid in procs and port in PORT_ROLES:
            roles.setdefault(pid, PORT_ROLES[port])
    kids: dict[int, list[int]] = {}
    for pid, p in procs.items():
        par = procs.get(p.ppid)
        if par is not None and p.ppid != pid and par.created <= p.created:  # padre verdadero
            kids.setdefault(p.ppid, []).append(pid)
    changed = True
    while changed:
        changed = False
        for pid, p in procs.items():
            if pid in roles:
                continue
            name, ch = p.name.lower(), kids.get(pid, [])
            up = {roles[c] for c in ch if c in roles}
            py = [c for c in ch if procs[c].name.lower() in PYTHON]
            if name in PYTHON and len(py) == 1 and py[0] in roles:
                child = roles[py[0]]
                roles[pid] = child if p.commit < LAUNCHER_MAX_COMMIT else (  # lanzador del venv
                    WATCHDOG_OF.get(child, "watchdog"))                       # o su vigilante
            elif name in _WEB_UP and up == {"web"}:
                roles[pid] = "web"
            elif p.ppid in roles and pid in kids.get(p.ppid, []):
                roles[pid] = roles[p.ppid]                 # hijo de un proceso del EIM
            else:
                continue
            changed = True
    return roles


def _mb(b: float) -> float:
    return round(b / (1 << 20), 1)


def record(now_s: float, dt_s: float, procs: Mapping[int, Proc], prev_cpu: Mapping[tuple, int],
           prev_wall: float, roles: Mapping[int, str], machine_cpu: float, mem: dict,
           hft: dict | None, ncpu: int, top: int = TOP) -> dict:
    """Una muestra. La CPU se da en % del equipo entero (con 4 núcleos, un hilo lleno = 25 %)."""
    scale = 100 / (dt_s * 1e7 * max(1, ncpu))

    def pct(p: Proc) -> float:
        base = prev_cpu.get((p.pid, p.created))
        if base is None:                   # nació después de la muestra anterior, o es nuevo
            base = 0 if p.created_s >= prev_wall else p.cpu
        return max(0.0, (p.cpu - base) * scale)

    groups: dict[str, dict] = {}
    others: dict[str, dict] = {}
    for pid, p in procs.items():
        if pid == 0:
            continue
        role = roles.get(pid)
        g = (groups if role else others).setdefault(
            role or p.name, {"n": 0, "cpu": 0.0, "ram_mb": 0.0, "commit_mb": 0.0, "prio": 0,
                             "pids": []})
        g["n"] += 1
        g["cpu"] += pct(p)
        g["ram_mb"] += p.ram
        g["commit_mb"] += p.commit
        g["prio"] = max(g["prio"], p.prio)
        g["pids"].append(pid)

    def tidy(g: dict, pids: bool) -> dict:
        out = {"n": g["n"], "cpu": round(g["cpu"], 2), "ram_mb": _mb(g["ram_mb"]),
               "commit_mb": _mb(g["commit_mb"]), "prio": g["prio"]}
        return {**out, "pids": sorted(g["pids"])} if pids else out

    by_cpu = sorted(others, key=lambda k: -others[k]["cpu"])[:top]
    by_ram = [k for k in sorted(others, key=lambda k: -others[k]["ram_mb"]) if k not in by_cpu][:3]
    eim = list(groups.values())
    return {
        "t": int(now_s * 1000),
        "ts": datetime.fromtimestamp(now_s, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dt_s": round(dt_s, 1),
        "machine": {"cpu": round(machine_cpu, 2), **mem},
        "eim": {"n": sum(g["n"] for g in eim), "cpu": round(sum(g["cpu"] for g in eim), 2),
                "ram_mb": _mb(sum(g["ram_mb"] for g in eim))},
        "roles": {k: tidy(g, True) for k, g in sorted(groups.items())},
        "others": [{"name": k, **tidy(others[k], False)} for k in by_cpu + by_ram],
        "hft": hft,
    }


def hft_state(data_dir: Path, now_s: float) -> dict | None:
    """Cola y frescura de la captura HFT según su latido (None si no hay captura)."""
    try:
        hb = json.loads((Path(data_dir) / "micro_hft" / "heartbeat.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    def age(ms: int | None) -> float | None:
        return None if not ms else round(now_s - ms / 1000, 1)

    return {"queue": hb.get("queue"), "backlog": hb.get("write_backlog"),
            "dropped": hb.get("dropped"), "msg_age_s": age(hb.get("last_msg_ms")),
            "beat_age_s": age(hb.get("last_heartbeat"))}


class Sampler:
    """Toma muestras; la primera solo fija la referencia de los contadores de CPU."""

    def __init__(self, data_dir: Path, backend=usage_win, ncpu: int | None = None) -> None:
        self.data_dir, self.backend = Path(data_dir), backend
        self.ncpu = ncpu or os.cpu_count() or 1
        self.prev: tuple[float, int, int, dict] | None = None

    def sample(self, now_s: float | None = None) -> dict | None:
        now = time.time() if now_s is None else now_s
        procs = self.backend.snapshot()
        busy, total = self.backend.system_times()
        prev = self.prev
        self.prev = (now, busy, total, {(p.pid, p.created): p.cpu for p in procs.values()})
        if prev is None or now <= prev[0] or total <= prev[2]:
            return None
        roles = attribute(procs, spool_roles(self.data_dir / "obs" / "spool", procs),
                          self.backend.listeners(frozenset(PORT_ROLES)))
        return record(now, now - prev[0], procs, prev[3], prev[0], roles,
                      100 * (busy - prev[1]) / (total - prev[2]), self.backend.memory(),
                      hft_state(self.data_dir, now), self.ncpu)


def append(data_dir: Path, rec: dict) -> Path:
    d = usage_dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{rec['ts'][:10]}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def prune(data_dir: Path, keep_days: int, now_s: float) -> int:
    """Comprime los días ya cerrados (`.jsonl.gz`, unas diez veces menos) y borra los de más de
    `keep_days`. Solo toca archivos `AAAA-MM-DD.jsonl*`; devuelve cuántos borró."""
    now = datetime.fromtimestamp(now_s, UTC)
    today, cut = now.strftime("%Y-%m-%d"), (now - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    n = 0
    for f in sorted(usage_dir(data_dir).glob("????-??-??.jsonl*")):
        day = f.name[:10]
        if day < cut:
            f.unlink(missing_ok=True)
            n += 1
        elif f.suffix == ".jsonl" and day < today:
            tmp = f.with_name(f.name + ".gz.tmp")
            with f.open("rb") as src, gzip.open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst)
            os.replace(tmp, f.with_name(f.name + ".gz"))
            f.unlink()
    return n


def run(data_dir: Path, every_s: float = EVERY_S, keep_days: int = KEEP_DAYS,
        once: bool = False) -> int:
    if not usage_win.supported():
        print("El registro de consumo solo funciona en Windows.", file=sys.stderr)
        return 2
    data_dir = Path(data_dir)
    lock = None if once else instance_lock(usage_dir(data_dir) / "usage.lock")
    if not once and lock is None:
        print("Ya hay un registro de consumo en marcha.", file=sys.stderr)
        return 4
    s = Sampler(data_dir)
    s.sample()
    if once:                               # a mano: ni latidos ni archivo
        time.sleep(min(every_s, 5))
        rec = s.sample()
        print(json.dumps(rec, ensure_ascii=False, indent=1))
        return 0 if rec else 1
    configure(process="usage", spool_dir=data_dir / "obs" / "spool")
    apply_role("usage")                    # T126: nivel de prioridad del proceso
    last_prune = 0.0
    try:
        while True:
            time.sleep(every_s)
            try:
                if (rec := s.sample()) is not None:
                    append(data_dir, rec)
                    hooks_service.beat(COMPONENT, min_interval_s=60, detail={
                        "cpu": rec["machine"]["cpu"], "eim_cpu": rec["eim"]["cpu"]})
                if time.time() - last_prune > 3600:
                    prune(data_dir, keep_days, time.time())
                    last_prune = time.time()
            except Exception as e:  # noqa: BLE001 - una muestra fallida no para el registro
                hooks_service.service_error(COMPONENT, e)
                print(f"muestra fallida: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    finally:
        if lock is not None:
            lock.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eim.operation.usage", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="registra el consumo cada --every segundos")
    r.add_argument("--data-dir", default="data")
    r.add_argument("--every", type=float, default=EVERY_S)
    r.add_argument("--keep-days", type=int, default=KEEP_DAYS)
    r.add_argument("--once", action="store_true", help="una sola muestra, por pantalla")
    s = sub.add_parser("summary", help="resumen por día, cruzado con la captura HFT")
    s.add_argument("--data-dir", default="data")
    s.add_argument("--days", type=int, default=7)
    s.add_argument("--symbol", default="BTCUSDT")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return run(Path(a.data_dir), a.every, a.keep_days, a.once)
    from eim.operation import usage_summary

    print(json.dumps(usage_summary.recent(Path(a.data_dir), a.days, a.symbol, time.time()),
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
