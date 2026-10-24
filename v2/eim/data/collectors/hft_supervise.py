"""Vigilante de la captura HFT (T78): el mismo servicio supervisado de T104 (cerrojo, latido,
reinicio con espera creciente, avisos de disco y de flujo) aplicado a `hft_ws`:

    python -m eim.data.collectors.hft_supervise BTCUSDT --root data [--keep-days 45]

Cerrojo `micro_hft/supervisor.lock`, latido `micro_hft/heartbeat.json`, registro en
`micro_hft/logs/`. Cada 10 min, en lugar de la poda de T104, hace el mantenimiento de
`hft_ops.maintain`: QC de las horas cerradas, compactación, retención y resumen. Un fallo de ese
mantenimiento se registra (`mantenimiento_fallido`) sin detener la vigilancia. Solo datos públicos.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from eim.data.collectors import hft_ops
from eim.data.collectors.hft_schema import AREA
from eim.data.collectors.supervise import Maintenance, supervise
from eim.observability.emit import configure

MAINT_EVERY_S = 600.0
LABEL = "Captura HFT"


class HftMaintenance(Maintenance):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **{**kwargs, "prune_every_s": MAINT_EVERY_S})

    def prune(self, now: float) -> None:
        res = hft_ops.maintain(self.root, self.symbol, now, self.keep_days)
        s = res.pop("summary")
        self.log.write("mantenimiento_hft", **res, horas_completas=s["hours_complete"],
                       horas=s["hours"], coincidencia_top10=s["checks"]["match_rate"],
                       mb_dia=s["disk"]["mb_per_day_total"],
                       proyeccion_30d_gb=s["disk"]["projection_30d_gb"])
        if res["no_detectados"] or res["qc_incompletas"]:
            self.log.write("qc_hft_aviso", "warn", incompletas=res["qc_incompletas"],
                           no_detectados=res["no_detectados"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbol", nargs="?", default="BTCUSDT")
    ap.add_argument("--root", default="data")
    ap.add_argument("--keep-days", type=int, default=hft_ops.KEEP_DAYS)
    a = ap.parse_args(argv)
    configure(process="hft_watchdog", spool_dir=Path(a.root) / "obs" / "spool")
    print(supervise(a.root, a.symbol, a.keep_days, module="eim.data.collectors.hft_ws",
                    area=AREA, label=LABEL, maint_cls=HftMaintenance))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
