"""Servicio supervisado del recolector de microestructura (T104), patrón de `eim.leaders`:

    python -m eim.data.collectors.supervise BTCUSDT --root data

Un solo vigilante por carpeta de datos (cerrojo `micro/supervisor.lock`); relanza
`eim.data.collectors.binance_ws` si muere o si su latido (`micro/heartbeat.json`) se detiene, con
espera creciente. Cada minuto comprueba salud y disco y avisa en local (registro + notificación);
cada hora poda los diffs de profundidad más viejos que `--depth-keep-days`. Solo datos públicos.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from eim.data.collectors import health
from eim.observability import hooks_service
from eim.observability.emit import configure
from eim.operation.alerts import CRITICAL, SERVICE, Alert
from eim.operation.notify import JsonLog, WindowsToast
from eim.operation.watchdog import Watchdog, instance_lock

CHECK_EVERY_S = 60.0
PRUNE_EVERY_S = 3600.0
REALERT_S = 1800.0      # un mismo aviso no se repite antes de esto


class Maintenance:
    """Avisos de salud/disco y poda, llamados desde el bucle de espera del vigilante."""

    def __init__(self, root: Path, log: JsonLog, keep_days: int, notify: Callable[[Alert], None],
                 clock: Callable[[], float] = time.time,
                 symbol: str = health.DEFAULT_SYMBOL) -> None:
        self.symbol = symbol
        self.root, self.log, self.keep_days = root, log, keep_days
        self.notify, self.clock = notify, clock
        self._next_check = self._next_prune = clock() + health.GRACE_S   # el hijo aún arranca
        self._alerted: dict[str, float] = {}

    def tick(self) -> None:
        now = self.clock()
        if now >= self._next_check:
            self._next_check = now + CHECK_EVERY_S
            self.check(now)
        if now >= self._next_prune:
            self._next_prune = now + PRUNE_EVERY_S
            n = health.prune_depth(self.root, self.keep_days, now)
            if n:
                self.log.write("poda_profundidad", dias_borrados=n, conserva_dias=self.keep_days)
            self.log.write("disco", **health.disk_report(self.root))

    def check(self, now: float) -> list[str]:
        msgs = health.problems(self.root, int(now * 1000), symbol=self.symbol)
        for m in msgs:
            if now - self._alerted.get(m[:40], 0.0) < REALERT_S:
                continue
            self._alerted[m[:40]] = now
            self.log.write("alerta_microestructura", "error", detalle=m)
            hooks_service.service_event("data.micro_collector", m, status="error")
            try:
                self.notify(Alert(int(now * 1000), SERVICE, CRITICAL, "Microestructura", m,
                                  SERVICE))
            except Exception:  # noqa: BLE001, S110 - el aviso nunca frena la vigilancia
                pass
        return msgs


def supervise(root: str | Path, symbol: str, keep_days: int = health.DEPTH_KEEP_DAYS,
              make_watchdog=Watchdog, notify: Callable[[Alert], None] | None = None) -> str:
    root = Path(root)
    mdir = health.micro_dir(root)
    lock = instance_lock(mdir / f"supervisor{health.sfx(symbol)}.lock")
    if lock is None:
        return "Ya hay un vigilante de microestructura en marcha: no se lanza otro."
    try:
        log = JsonLog(mdir / "logs", echo=True)
        maint = Maintenance(mdir.parent, log, keep_days, notify or WindowsToast(), symbol=symbol)

        def sleep(s: float) -> None:
            time.sleep(s)
            maint.tick()

        cmd = [sys.executable, "-m", "eim.data.collectors.binance_ws", symbol.upper(),
               "--root", str(root)]
        log.write("vigilante_iniciado", symbol=symbol.upper(), arranque_ms=int(time.time() * 1000))
        make_watchdog(cmd, dict(os.environ), mdir / health.hb_name(symbol), log,
                      stale_s=health.STALE_S, check_s=15.0, sleep=sleep,
                      title="Microestructura: recolector reiniciado").run()
        return "vigilante de microestructura detenido"
    finally:
        lock.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbol", nargs="?", default="BTCUSDT")
    ap.add_argument("--root", default="data")
    ap.add_argument("--depth-keep-days", type=int, default=health.DEPTH_KEEP_DAYS)
    a = ap.parse_args(argv)
    configure(process="micro_watchdog", spool_dir=Path(a.root) / "obs" / "spool")
    print(supervise(a.root, a.symbol, a.depth_keep_days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
