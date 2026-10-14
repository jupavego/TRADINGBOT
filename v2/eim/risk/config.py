"""Configuración del motor de riesgo: inmutable, cargada de un archivo versionado.

Un cambio de límites es un archivo nuevo en `eim/risk/versions/` (nunca se edita uno publicado
ni se modifica en caliente): la `RiskConfig` es `frozen` y lleva su versión y el hash SHA-256
del archivo, que quedan en cada `RiskDecision`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSIONS_DIR = Path(__file__).parent / "versions"
DEFAULT_VERSION = "risk_v1"


class RiskConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    description: str = ""
    sha256: str = ""                                   # hash del archivo de origen
    # tamaño
    risk_per_trade: float = Field(gt=0, le=0.02)       # fracción del capital hasta el SL
    max_leverage: float = Field(ge=1, le=20)           # apalancamiento (margen aislado)
    max_notional_frac: float = Field(gt=0, le=20)      # nocional ≤ capital × esto
    mmr: float = Field(ge=0, lt=0.1)                   # margen de mantenimiento
    min_liq_sl_ratio: float = Field(ge=1.2)            # dist(liquidación) ≥ k · dist(SL)
    min_sl_frac: float = Field(gt=0)                   # SL demasiado cerca = ruido
    max_sl_frac: float = Field(gt=0, lt=0.5)
    min_rr: float = Field(ge=0)
    # pérdidas y exposición
    max_daily_loss: float = Field(gt=0, lt=1)          # fracción del capital al inicio del día
    max_weekly_loss: float = Field(gt=0, lt=1)
    max_open_trades: int = Field(ge=0)
    max_open_per_symbol: int = Field(ge=0)
    max_consecutive_losses: int = Field(ge=1)
    cooldown_ms: int = Field(ge=0)
    # calidad de datos
    max_data_age_bars: float = Field(gt=0)             # última vela cerrada ≤ esto × marco
    max_plan_age_bars: float = Field(gt=0)             # reporte del plan ≤ esto × marco
    max_degraded_agents: int = Field(ge=0)
    critical_agents: tuple[str, ...] = ()
    allowed_modes: tuple[str, ...] = ("ANALISIS", "SIMULADO", "TESTNET")
    # kill-switch automático
    kill_max_drawdown: float = Field(gt=0, lt=1)
    kill_max_disconnect_ms: int = Field(gt=0)
    kill_max_recon_drift: float = Field(gt=0)

    @model_validator(mode="after")
    def _coherent(self) -> RiskConfig:
        if self.min_sl_frac >= self.max_sl_frac:
            raise ValueError("min_sl_frac debe ser < max_sl_frac")
        if self.max_daily_loss > self.max_weekly_loss:
            raise ValueError("max_daily_loss no puede superar max_weekly_loss")
        if "REAL" in self.allowed_modes:
            raise ValueError("modo REAL prohibido hasta superar la puerta de edge (T27/T31)")
        return self


def load_config(path: str | Path | None = None, version: str = DEFAULT_VERSION) -> RiskConfig:
    """Lee y valida un archivo de configuración; su nombre debe coincidir con `version`."""
    p = Path(path) if path is not None else VERSIONS_DIR / f"{version}.json"
    raw = p.read_bytes()
    data = json.loads(raw)
    if data.get("version") != p.stem:
        raise ValueError(f"versión '{data.get('version')}' no coincide con el archivo {p.name}")
    # Hash sobre fin de línea LF: el mismo archivo da el mismo hash en todo equipo (T32).
    return RiskConfig(**data, sha256=hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest())
