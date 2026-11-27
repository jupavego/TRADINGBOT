"""Bucle supervisado del escáner (T93), con el patrón de T31/T41.

- **Instancia única** (`scanner.lock`): un segundo `run` sale con código 2 sin tocar nada.
- **Reanudación**: al arrancar, los trabajos que quedaron `running` por una caída vuelven a la
  cola (`JobQueue.resume`).
- **Ritmos**: relleno y barrido cada `deep_every_s`, y tras cada barrido la pasada de agentes
  sobre su lista corta si se pide (`agents=True`, lo que hace `python -m eim.scanner run`; T94,
  `deep_service.deep_pass`); pasada rápida cada `fast_every_s`.
- **Un fallo no mata el bucle**: se registra, va al observatorio y se reintenta con espera
  creciente (tope `max_backoff_s`). Sin catálogo o sin datos espera sin contarlo como fallo.
- **Latido** en `data/scanner/heartbeat.json` tras cada vuelta, bien o mal (lo que mira un
  vigilante para saber si el proceso sigue vivo).
- **Parada limpia** (Ctrl+C o `stop`): termina lo que está en curso, cancela lo pendiente y
  cierra la base.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from eim.observability import hooks_service
from eim.operation.watchdog import instance_lock, write_heartbeat
from eim.scanner.deep_service import deep_pass
from eim.scanner.service import COMPONENT, ScannerError, ScannerService

HEARTBEAT = "heartbeat.json"
LOCK = "scanner.lock"


def run_loop(svc: ScannerService, *, once: bool = False, sync: bool = True,
             quotes: bool = True, agents: bool = False, stop: threading.Event | None = None,
             say: Callable[[str], object] = print,
             monotonic: Callable[[], float] = time.monotonic) -> int:
    lock = instance_lock(svc.dir / LOCK)
    if lock is None:
        say("ya hay un escáner en marcha en este directorio de datos (scanner.lock)")
        svc.close()
        return 2
    stop = stop or threading.Event()
    p = svc.p
    st = {"state": "iniciando", "cycles": 0, "consecutive_failures": 0, "last_error": "",
          "resumed": svc.queue.resume()}
    nxt = {"sync": 0.0, "deep": 0.0, "fast": 0.0}
    try:
        while not stop.is_set():
            wait = p.fast_every_s
            try:
                now = monotonic()
                if sync and now >= nxt["sync"]:
                    say(f"relleno: {svc.sync()}")
                    nxt["sync"] = now + p.deep_every_s
                if now >= nxt["deep"]:
                    s = svc.sweep()
                    say(f"barrido {s['run_id']}: {s['n_stage2']}/{s['n_catalog']} puntuados, "
                        f"{s['ms_per_instrument']:.2f} ms/instrumento")
                    if agents:
                        d = deep_pass(svc, base_run_id=s["run_id"])
                        say(f"agentes {d['run_id']}: {len(d['opportunities'])} candidatas de "
                            f"{d['n_shortlist']} (no validadas)")
                    nxt["deep"] = now + p.deep_every_s
                if quotes and now >= nxt["fast"]:
                    f = svc.fast()
                    say(f"rápido: {f.get('alerts', 0)} alertas")
                    nxt["fast"] = now + p.fast_every_s
                st.update(state="operando", consecutive_failures=0)
            except ScannerError as exc:            # falta algo que no es un fallo del código
                st.update(state="esperando", last_error=str(exc)[:300])
                say(f"esperando: {exc}")
            except Exception as exc:  # noqa: BLE001 - el bucle no debe morir
                st["consecutive_failures"] += 1
                st.update(state="reintentando", last_error=f"{type(exc).__name__}: {exc}"[:300])
                wait = min(p.max_backoff_s * 5, p.fast_every_s * 2 ** st["consecutive_failures"])
                hooks_service.service_error(COMPONENT, exc, min_interval_s=p.obs_min_interval_s)
                say(f"fallo ({st['consecutive_failures']} seguidos): {st['last_error']}")
            st["cycles"] += 1
            beat(svc, st)
            if once:
                break
            stop.wait(wait)
    except KeyboardInterrupt:
        say("parada pedida: se termina lo que está en curso")
    finally:
        svc.queue.request_cancel()
        st["cancelled"] = svc.queue.cancel_pending()
        st["state"] = "detenido"
        beat(svc, st)
        svc.close()
        lock.close()
    return 0 if st.get("consecutive_failures", 0) == 0 else 1


def beat(svc: ScannerService, st: dict) -> None:
    row = {"last_heartbeat": svc.clock(), **{k: st.get(k) for k in (
        "state", "cycles", "consecutive_failures", "last_error", "resumed")}}
    if err := write_heartbeat(svc.dir / HEARTBEAT, row):
        hooks_service.service_error(COMPONENT, err)
