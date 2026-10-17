"""Supuestos de la simulación de arbitraje (T43). Todo lo que no se mide se declara aquí y
se imprime en el informe; nada de esto es un dato de mercado."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SimParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_every_h: int = Field(default=8, ge=1)  # cadencia de decisión (funding de 8 h)
    decision_offset_h: int = Field(default=1, ge=0)  # decidir esta cantidad de horas antes
    # Pata incompleta: probabilidad de que la 2.ª pata no se ejecute en una ejecución de dos
    # patas (supuesto; T45 lo medirá en testnet) y tiempo que una pata queda sin cubrir.
    p_fail: float = Field(default=0.01, ge=0, le=1)
    latency_ms: float = Field(default=250.0, gt=0)
    # Profundidad: 1 = libro capturado; < 1 = libro más delgado (prueba de sensibilidad).
    depth_scale: float = Field(default=1.0, gt=0)
    vol_scale_min: float = Field(default=0.2, gt=0, le=1)  # adelgazamiento máximo por volumen
    # Margen: con spot + futuro corto se repone margen al caer a esta fracción del objetivo
    # (vende spot, recompra futuro: reduce ambas patas). Futuro/futuro: margen cruzado.
    rebalance_frac: float = Field(default=0.5, gt=0, lt=1)
    min_days_to_expiry: float = Field(default=3.0, ge=0)  # no entrar a un trimestral con menos
    related_exit_bps: float = 0.0  # perpetuos relacionados: salir si la diferencia cierra
    hurdle_apr: float = Field(default=0.04, ge=0)  # umbral de referencia (supuesto, no dato)
    mc_paths: int = Field(default=200, ge=10)  # simulaciones de pata incompleta por operación
    seed: int = 0
