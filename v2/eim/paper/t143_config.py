"""Configuración de la corrida aparte de T143 (◆ del usuario, 2026-11-10).

T31 sigue con su configuración hasta su cierre (la que dan los valores por defecto de
`ExecParams` y `PROFILES`). Lo que T143 midió y adoptó corre **desde ya** en una segunda mesa en
papel (`eim/paper/variant.py`), con su propio libro, para no cambiar el objeto de T31:

- entrada maker en 1 h y 4 h (`reports/t143_maker.md`);
- puerta de marcos por costo a 0,15 R (`eim/paper/tf_gate.py`);
- riesgo con costo en los cuatro perfiles (la pérdida al SL inicial es la declarada).

Esta es también la frontera de la **automejora sin intervención humana** que fijó el usuario: solo
se adaptan solos el costo y el riesgo, con umbrales escritos aquí que abren y cierran y vuelven
solos según lo medido. Entradas, salidas y pesos de la síntesis siguen pasando por un pre-registro
y por el usuario (T139 P1).
"""

from __future__ import annotations

from eim.paper.params import PROFILES, ExecParams, ProfileParams

NAME = "t143"
LABEL = "Corrida aparte T143 (maker 1 h/4 h · sin marcos caros · riesgo con costo)"

EXEC_T143 = ExecParams(maker_entry_timeframes=("1h", "4h"), tf_max_cost_r=0.15)

PROFILES_T143: tuple[ProfileParams, ...] = tuple(
    p.model_copy(update={"risk_includes_costs": True}) for p in PROFILES)

#: Lo único que se adapta solo, y dónde se decide. Una adaptación nueva entra en esta lista con
#: su umbral y su prueba, o no es automática.
AUTO_ADAPT = {
    "tf_max_cost_r": "marco con costo medido ≥ umbral → no opera; vuelve solo si abarata",
    "maker_entry_timeframes": "marcos con entrada límite medida (T143 entregable 1)",
    "risk_includes_costs": "la cantidad se ajusta para que la pérdida al SL sea la declarada",
}
