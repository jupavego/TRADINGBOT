"""Parámetros de las variables de microestructura (T80). Sin números mágicos en la lógica."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FeatureParams(BaseModel):
    """Ventanas y niveles de las variables. Todas las ventanas son hacia atrás (en cubos).

    Un cubo es el paso de muestreo del panel (`step_ms`, 1 s por defecto): `ofi_windows` de
    (1, 5, 30) son 1 s, 5 s y 30 s de flujo acumulado hasta el cierre del cubo, nunca después.
    """

    model_config = ConfigDict(frozen=True)

    levels: int = Field(default=5, ge=1, le=10)      # niveles del libro (OFI multinivel 1–5)
    ofi_windows: tuple[int, ...] = (1, 5, 30)        # cubos de OFI acumulado
    flow_windows: tuple[int, ...] = (5, 30)          # cubos de flujo de operaciones
    rv_window: int = 60                              # cubos para RV/bipower
    intensity_window: int = 30                       # cubos para la intensidad de llegadas
    intensity_ref: int = 600                         # referencia larga de la intensidad
    vpin_bucket: float = 20.0                        # volumen (BTC) de cada cubo de VPIN
    vpin_buckets: int = 50                           # cubos de volumen de la ventana de VPIN
    depth_levels: int = 5                            # niveles del desequilibrio de profundidad
    eps: float = 1e-12

    @property
    def history_buckets(self) -> int:
        """Cubos de historia que necesita la ventana más larga por tiempo.

        Una fila solo vale si esos cubos son contiguos: una ventana que cruza una hora que no se
        capturó mezclaría datos de antes y después del hueco (`matrix.contiguous_history`). El
        VPIN se mide en cubos de VOLUMEN, que pueden abarcar más tiempo: queda declarado en el
        informe y es la única ventana que puede arrastrar historia de antes de un hueco.
        """
        return max(self.rv_window, self.intensity_window, self.intensity_ref,
                   max(self.ofi_windows), max(self.flow_windows))
