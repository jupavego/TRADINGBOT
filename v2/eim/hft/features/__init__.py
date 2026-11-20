"""Variables de microestructura del carril HFT (T80), puras: sin red, sin disco, sin estado.

`book` (microprecio, OFI multinivel, profundidad, spread) · `flow` (desequilibrio del flujo
agresor, intensidad de llegadas, VPIN) · `vol` (RV, bipotencia, parte de salto) · `sampling`
(ventanas hacia atrás y reloj de volumen) · `matrix` (`Panel` y la matriz de variables).

La línea base que hay que superar es el agente `microstructure` v1 (T23/T104): OFI del mejor
nivel, CVD, profundidad top-10 y Parkinson/GK. Sus variables están aquí como casos particulares
(`ofi_top_*`, `flow_imb_*`, `depth_imb`, `rv_bps`).
"""

from eim.hft.features.matrix import Panel, build_matrix, concat, valid_rows
from eim.hft.features.params import FeatureParams

__all__ = ["FeatureParams", "Panel", "build_matrix", "concat", "valid_rows"]
