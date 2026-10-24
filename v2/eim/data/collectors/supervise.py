"""Servicio supervisado del recolector de microestructura (T104), patrón de `eim.leaders`:

    python -m eim.data.collectors.supervise BTCUSDT --root data

Un solo vigilante por carpeta de datos (cerrojo `micro/supervisor.lock`); relanza
`eim.data.collectors.binance_ws` si muere o si su latido (`micro/heartbeat.json`) se detiene, con
espera creciente. Cada minuto comprueba salud y disco y avisa en local (registro + notificación);
cada hora poda los diffs de profundidad más viejos que `--depth-keep-days`. Un fallo de ese
mantenimiento se registra (`mantenimiento_fallido`) sin detener la vigilancia. Solo datos públicos.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
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
                 symbol: str = health.DEFAULT_SYMBOL, area: str = "micro",
                 label: str = "Microestructura", prune_every_s: float = PRUNE_EVERY_S) -> None:
        self.symbol, self.area, self.label, self.prune_every_s = symbol, area, label, prune_every_s
        self.root, self.log, self.keep_days = root, log, keep_days
        self.notify, self.clock = notify, clock
        self._next_check = self._next_prune = clock() + health.GRACE_S   # el hijo aún arranca
        self._alerted: dict[str, float] = {}

    def tick(self) -> None:
        now = self.clock()
        if now >= self._next_check:
            self._next_check = now + CHECK_EVERY_S
            self._safe("check", now, self.check)
        if now >= self._next_prune:
            self._next_prune = now + self.prune_every_s
            self._safe("poda", now, self.prune)

    def prune(self, now: float) -> None:
        n = health.prune_depth(self.root, self.keep_days, now)
        if n:
            self.log.write("poda_profundidad", dias_borrados=n, conserva_dias=self.keep_days)
        self.log.write("disco", **health.disk_report(self.root))

    def _safe(self, step: str, now: float, fn: Callable[[float], object]) -> None:
        """Un fallo de mantenimiento se registra y avisa (sin repetir) y la vigilancia sigue.

        Solo `Exception`: Ctrl+C llega intacto al Watchdog, y sus propios fallos no pasan por aquí.
        """
        try:
            fn(now)
        except Exception as e:  # noqa: BLE001 - el mantenimiento nunca tumba al vigilante
            key = f"mantenimiento:{step}:{type(e).__name__}"
            if now - self._alerted.get(key, 0.0) < REALERT_S:
                return
            self._alerted[key] = now
            err = f"{type(e).__name__}: {e}"
            self.log.write("mantenimiento_fallido", "error", paso=step, error=err,
                           traza=traceback.format_exc()[-1500:])
            hooks_service.service_event("data.micro_collector", f"mantenimiento fallido ({step})",
                                        status="error", detail={"error": err})

    def check(self, now: float) -> list[str]:
        msgs = health.problems(self.root, int(now * 1000), symbol=self.symbol, area=self.area,
                               label=self.label)
        for m in msgs:
            if now - self._alerted.get(m[:40], 0.0) < REALERT_S:
                continue
            self._alerted[m[:40]] = now
            self.log.write("alerta_microestructura", "error", detalle=m)
            hooks_service.service_event("data.micro_collector", m, status="error")
            try:
                self.notify(Alert(int(now * 1000), SERVICE, CRITICAL, self.label, m, SERVICE))
            except Exception:  # noqa: BLE001, S110 - el aviso nunca frena la vigilancia
                pass
        return msgs


def supervise(root: str | Path, symbol: str, keep_days: int = health.DEPTH_KEEP_DAYS,
              make_watchdog=Watchdog, notify: Callable[[Alert], None] | None = None,
              module: str = "eim.data.collectors.binance_ws", area: str = "micro",
              label: str = "Microestructura", maint_cls: type[Maintenance] = Maintenance,
              extra_args: tuple[str, ...] = ()) -> str:
    """Vigila un recolector (`module`) del área `area`; T78 lo reutiliza para la captura HFT."""
    root = Path(root)
    mdir = health.area_dir(root, area)
    lock = instance_lock(mdir / f"supervisor{health.sfx(symbol)}.lock")
    if lock is None:
        return f"Ya hay un vigilante de {label.lower()} en marcha: no se lanza otro."
    try:
        log = JsonLog(mdir / "logs", echo=True)
        maint = maint_cls(mdir.parent, log, keep_days, notify or WindowsToast(), symbol=symbol,
                          area=area, label=label)

        def sleep(s: float) -> None:
            time.sleep(s)
            maint.tick()

        cmd = [sys.executable, "-m", module, symbol.upper(), "--root", str(root), *extra_args]
        log.write("vigilante_iniciado", symbol=symbol.upper(), arranque_ms=int(time.time() * 1000))
        make_watchdog(cmd, dict(os.environ), mdir / health.hb_name(symbol), log,
                      stale_s=health.STALE_S, check_s=15.0, sleep=sleep,
                      title=f"{label}: recolector reiniciado").run()
        return f"vigilante de {label.lower()} detenido"
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
