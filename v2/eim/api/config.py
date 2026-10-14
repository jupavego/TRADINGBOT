"""Configuración de la API por variables de entorno (sin claves en código)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Entorno: EIM_DATA_DIR, EIM_REPORTS_DB, EIM_CORS_ORIGINS, EIM_WS_URL, EIM_HEARTBEAT_S,
    EIM_EXECUTION (off | paper | testnet), EIM_RECON_S (segundos entre reconciliaciones),
    EIM_OPERATE=1 (servicio de operación continua, T31), EIM_OPERATE_TF, EIM_OPERATE_POLL_S,
    EIM_OPERATION_REPORTS (carpeta del informe semanal), EIM_EDGE_RESULTS."""

    data_dir: Path = Path("data")
    reports_db: Path | None = None
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    ws_url: str = "wss://fstream.binance.com/market/ws"
    heartbeat_s: float = 15.0
    snapshot_bars: int = 500
    agent_timeout_s: float = 30.0
    reconnect_max_s: float = 30.0
    auto_history: bool = False  # EIM_AUTO_HISTORY (1 por defecto en from_env)
    execution: str = "off"      # T30: "testnet" activa el broker de testnet (claves por entorno)
    recon_interval_s: float = 30.0
    operate: bool = False       # T31: ciclo continuo datos→…→ejecución dentro del proceso
    operate_tf: str = "1h"
    operate_poll_s: float = 60.0
    operation_reports: Path = Path("reports/operation")
    edge_results: Path = Path("reports/edge/edge_results.json")
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
            auto_history=env.get("EIM_AUTO_HISTORY", "1") != "0",
            execution=env.get("EIM_EXECUTION", d.execution).strip().lower(),
            recon_interval_s=float(env.get("EIM_RECON_S", d.recon_interval_s)),
            operate=env.get("EIM_OPERATE", "0") == "1",
            operate_tf=env.get("EIM_OPERATE_TF", d.operate_tf),
            operate_poll_s=float(env.get("EIM_OPERATE_POLL_S", d.operate_poll_s)),
            operation_reports=Path(env.get("EIM_OPERATION_REPORTS", str(d.operation_reports))),
            edge_results=Path(env.get("EIM_EDGE_RESULTS", str(d.edge_results))),
        )
