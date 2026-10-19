"""Instantánea en caliente para exportar la experiencia (T61): `POST /v2/share/snapshot`.

La API tiene abiertas `reports.duckdb` y `paper.duckdb`; para exportarlas sin detenerla, la CLI
(`python -m eim.data.share export`) pide aquí una copia coherente, hecha bajo el cerrojo de los
escritores, a `data/share/_snapshot/`. La CLI la lee, exporta a Parquet y la borra. Solo escribe
dentro de `data/`; la exportación a la carpeta de la nube la hace la CLI. `leaders.duckdb` lo
tiene el servicio de líderes (se le pide su propia instantánea, ver `copy_store`).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Header

from eim.api.execution import confirm
from eim.api.reports_db import ReportStore
from eim.data.backup import copy_db_hot
from eim.data.paper_store import PaperStore


def build_share_router(reports: ReportStore, paper: PaperStore, data_dir: Path) -> APIRouter:
    r = APIRouter(prefix="/v2/share", tags=["share"])

    @r.post("/snapshot")
    def snapshot(x_eim_confirm: str | None = Header(None)) -> dict:
        confirm(x_eim_confirm, "share")
        out = data_dir / "share" / "_snapshot"
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        tables = {}
        for name, store in (("reports.duckdb", reports), ("paper.duckdb", paper)):
            con, lock = store.connection
            tables[name] = copy_db_hot(con, lock, out / name)
        return {"dir": str(out), "files": sorted(tables), "tables": tables}

    return r
