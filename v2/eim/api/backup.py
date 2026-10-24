"""Copias de seguridad en caliente (`/v2/backup`): la API tiene abiertas `reports.duckdb`,
`paper.duckdb` y el observatorio, así que la copia se hace aquí (T32, T115); `leaders.duckdb` se
la pide al servicio de líderes. Lógica en `eim/data/backup.py`. Con el servicio de operación en
marcha, `reports.duckdb` y el estado del servicio (libro, cursores) se copian entre dos ciclos:
quedan consistentes entre sí."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Header

from eim.api.execution import confirm
from eim.api.reports_db import ReportStore
from eim.data import backup


def build_backup_router(reports: ReportStore, data_dir: Path, dest: Path, keep: int,
                        op_ref: Callable[[], object | None] = lambda: None,
                        extra_dbs: dict | None = None) -> APIRouter:
    r = APIRouter(prefix="/v2/backup", tags=["backup"])

    @r.get("")
    def list_backups() -> dict:
        return {"dest": str(dest), "keep": keep,
                "backups": [p.name for p in backup.listing(dest)]}

    @r.post("")
    def make_backup(with_market: bool = False,
                    x_eim_confirm: str | None = Header(None)) -> dict:
        confirm(x_eim_confirm, "backup")
        op = op_ref()
        if op is not None and getattr(op, "backup_dir", None) is not None:
            out = op.backup_now(with_market=with_market)
        else:
            con, lock = reports.connection
            out = backup.create(data_dir, dest, con=con, lock=lock, with_market=with_market,
                                keep=keep, extra_dbs=extra_dbs)
        return backup.summary(out)      # bases con filas por tabla y las ausentes con motivo

    return r
