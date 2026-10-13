"""Configuración de la API por variables de entorno (sin claves en código)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Entorno: EIM_DATA_DIR, EIM_REPORTS_DB, EIM_CORS_ORIGINS, EIM_WS_URL, EIM_HEARTBEAT_S."""

    data_dir: Path = Path("data")
    reports_db: Path | None = None
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    ws_url: str = "wss://fstream.binance.com/ws"
    heartbeat_s: float = 15.0
    snapshot_bars: int = 500
    agent_timeout_s: float = 30.0
    reconnect_max_s: float = 30.0
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def reports_path(self) -> Path:
        return self.reports_db or self.data_dir / "reports.duckdb"

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        origins = env.get("EIM_CORS_ORIGINS")
        d = cls()
        return cls(
            data_dir=Path(env.get("EIM_DATA_DIR", str(d.data_dir))),
            reports_db=Path(env["EIM_REPORTS_DB"]) if env.get("EIM_REPORTS_DB") else None,
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip())
            if origins else d.cors_origins,
            ws_url=env.get("EIM_WS_URL", d.ws_url),
            heartbeat_s=float(env.get("EIM_HEARTBEAT_S", d.heartbeat_s)),
            snapshot_bars=int(env.get("EIM_SNAPSHOT_BARS", d.snapshot_bars)),
        )
