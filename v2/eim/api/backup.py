"""Copias de seguridad en caliente (`/v2/backup`): la API tiene la base abierta, así que la
copia se hace aquí, bajo el cerrojo de los escritores (T32). Lógica en `eim/data/backup.py`."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Header

from eim.api.execution import confirm
from eim.api.reports_db import ReportStore
from eim.data import backup


def build_backup_router(reports: ReportStore, data_dir: Path, dest: Path, keep: int) -> APIRouter:
    r = APIRouter(prefix="/v2/backup", tags=["backup"])

    @r.get("")
    def list_backups() -> dict:
        return {"dest": str(dest), "keep": keep,
                "backups": [p.name for p in backup.listing(dest)]}

    @r.post("")
    def make_backup(with_market: bool = False,
                    x_eim_confirm: str | None = Header(None)) -> dict:
        confirm(x_eim_confirm, "backup")
        con, lock = reports.connection
        out = backup.create(data_dir, dest, con=con, lock=lock, with_market=with_market,
                            keep=keep)
        return {"path": str(out), "problems": backup.verify(out)}

    return r
