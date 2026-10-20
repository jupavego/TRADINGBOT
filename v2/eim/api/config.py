"""Configuración de la API por variables de entorno (sin claves en código)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from eim.api.security import LOOPBACK_HOSTS


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(x.strip() for x in (value or "").split(",") if x.strip())


@dataclass(frozen=True)
class Settings:
    """Entorno: EIM_DATA_DIR, EIM_REPORTS_DB, EIM_CORS_ORIGINS, EIM_WS_URL, EIM_HEARTBEAT_S,
    EIM_EXECUTION (off | paper | testnet), EIM_RECON_S (segundos entre reconciliaciones),
    EIM_OPERATE=1 (servicio de operación continua, T31), EIM_OPERATE_TF, EIM_OPERATE_POLL_S,
    EIM_OPERATION_REPORTS (carpeta del informe semanal), EIM_EDGE_RESULTS,
    EIM_ALLOWED_HOSTS (cabeceras Host aceptadas; solo bucle local por defecto) y
    EIM_API_TOKEN (sin él, ningún cliente remoto entra; ver eim/api/security.py),
    EIM_BACKUP_DIR / EIM_BACKUP_KEEP (copias de seguridad; diaria automática con EIM_OPERATE=1),
    EIM_CALENDAR=0 desactiva el calendario económico en vivo (T36), EIM_CALENDAR_S (segundos
    entre consultas) y EIM_FRED_API_KEY (opcional: valores reales; la lee `providers/fred.py`);
    EIM_ARBITRAGE=0 desactiva el escáner de arbitraje (T39), EIM_ARBITRAGE_S (segundos entre
    escaneos), EIM_ARB_ALERT_SCORE (umbral de alerta, pb/día ajustados) y EIM_ARB_ALERT_S
    (segundos seguidos sobre el umbral antes de avisar); EIM_PAPER=0 desactiva el servicio en vivo
    del bróker simulado (T47) y EIM_PAPER_S fija los segundos entre ciclos; EIM_ARB_ASSETS
    (p. ej. "BTC" o "BTC,ETH") elige los activos del escáner de arbitraje y EIM_ARB_TRI_ASSETS
    los de sus ciclos triangulares (foco actual: BTC, sin ETH)."""

    data_dir: Path = Path("data")
    reports_db: Path | None = None
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    allowed_hosts: tuple[str, ...] = LOOPBACK_HOSTS
    api_token: str | None = field(default=None, repr=False)
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
    operate_extra_tfs: tuple[str, ...] = ("4h",)   # EIM_OPERATE_EXTRA_TFS="" los desactiva
    operate_poll_s: float = 60.0
    operation_reports: Path = Path("reports/operation")
    edge_results: Path = Path("reports/edge/edge_results.json")
    backup_dir: Path = Path("backups")
    backup_keep: int = 14
    calendar: bool = False      # T36: refresco del calendario (1 por defecto en from_env)
    calendar_interval_s: float = 6 * 3600
    arbitrage: bool = False     # T39: escáner de arbitraje (1 por defecto en from_env)
    arbitrage_interval_s: float = 10.0  # pausa entre escaneos (cada uno tarda ~1-2 s)
    arb_alert_score: float = 3.0
    arb_alert_hold_s: float = 60.0
    arb_assets: tuple[str, ...] = ("BTC", "ETH")  # from_env: solo BTC (foco 2026-10-15)
    arb_tri_assets: tuple[str, ...] | None = None  # None = los del cargador
    arb_execution: str = "off"  # T45: "testnet" ejecuta arbitrajes en spot + futuros testnet
    arb_exec_interval_s: float = 60.0
    paper: bool = False         # T47: bróker simulado en vivo (1 por defecto en from_env)
    paper_poll_s: float = 60.0
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
            cors_origins=_csv(origins) or d.cors_origins,
            allowed_hosts=_csv(env.get("EIM_ALLOWED_HOSTS")) or d.allowed_hosts,
            api_token=env.get("EIM_API_TOKEN") or None,
            ws_url=env.get("EIM_WS_URL", d.ws_url),
            heartbeat_s=float(env.get("EIM_HEARTBEAT_S", d.heartbeat_s)),
            snapshot_bars=int(env.get("EIM_SNAPSHOT_BARS", d.snapshot_bars)),
            auto_history=env.get("EIM_AUTO_HISTORY", "1") != "0",
            execution=env.get("EIM_EXECUTION", d.execution).strip().lower(),
            recon_interval_s=float(env.get("EIM_RECON_S", d.recon_interval_s)),
            operate=env.get("EIM_OPERATE", "0") == "1",
            operate_tf=env.get("EIM_OPERATE_TF", d.operate_tf),
            operate_extra_tfs=tuple(x for x in env.get(
                "EIM_OPERATE_EXTRA_TFS", ",".join(d.operate_extra_tfs)).split(",") if x),
            operate_poll_s=float(env.get("EIM_OPERATE_POLL_S", d.operate_poll_s)),
            operation_reports=Path(env.get("EIM_OPERATION_REPORTS", str(d.operation_reports))),
            edge_results=Path(env.get("EIM_EDGE_RESULTS", str(d.edge_results))),
            backup_dir=Path(env.get("EIM_BACKUP_DIR", str(d.backup_dir))),
            backup_keep=int(env.get("EIM_BACKUP_KEEP", d.backup_keep)),
            calendar=env.get("EIM_CALENDAR", "1") != "0",
            calendar_interval_s=float(env.get("EIM_CALENDAR_S", d.calendar_interval_s)),
            arbitrage=env.get("EIM_ARBITRAGE", "1") != "0",
            arbitrage_interval_s=float(env.get("EIM_ARBITRAGE_S", d.arbitrage_interval_s)),
            arb_alert_score=float(env.get("EIM_ARB_ALERT_SCORE", d.arb_alert_score)),
            arb_alert_hold_s=float(env.get("EIM_ARB_ALERT_S", d.arb_alert_hold_s)),
            arb_assets=_csv(env.get("EIM_ARB_ASSETS", "BTC")) or d.arb_assets,
            arb_tri_assets=_csv(env.get("EIM_ARB_TRI_ASSETS", "USDT,BTC,BNB,SOL,XRP")) or None,
            arb_execution=env.get("EIM_ARB_EXECUTION", d.arb_execution).strip().lower(),
            arb_exec_interval_s=float(env.get("EIM_ARB_EXEC_S", d.arb_exec_interval_s)),
            paper=env.get("EIM_PAPER", "1") != "0",
            paper_poll_s=float(env.get("EIM_PAPER_S", d.paper_poll_s)),
        )
