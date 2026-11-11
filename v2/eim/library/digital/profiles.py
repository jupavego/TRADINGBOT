"""Conocimiento por perfil de riesgo (T156), puro.

Cada perfil del bróker simulado mira la biblioteca con su propia lente: qué categorías pesan más,
qué conceptos siempre revisa y qué exige antes de dar algo por respaldado. La lente reordena y
anota; **no cambia ningún parámetro del perfil** (`eim/paper/params.py` sigue mandando).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Lens:
    profile: str
    name: str
    category_w: dict[str, float]     # categoría temática → multiplicador del peso
    always: tuple[str, ...]           # conceptos que este perfil revisa en toda operación
    require_consensus: bool           # exige consenso «a favor» para llamar respaldada la entrada
    focus: str                        # frase para el panel


LENSES: dict[str, Lens] = {
    "conservador": Lens(
        "conservador", "Conservador", {"C": 1.5, "B": 1.2, "D": 1.1, "E": 0.7, "G": 0.7},
        ("drawdown", "tail_risk", "position_sizing", "multiple_testing"), True,
        "Preservación del capital, control de la caída y confirmación: sin consenso a favor, la "
        "entrada no se considera respaldada."),
    "moderado": Lens(
        "moderado", "Moderado", {}, ("stop_loss", "position_sizing", "execution_costs"), False,
        "Equilibrio: respaldo de la estrategia y control del costo y del tamaño."),
    "agresivo": Lens(
        "agresivo", "Agresivo", {"E": 1.3, "A": 1.1, "F": 1.2, "C": 1.0},
        ("momentum_crash", "liquidation", "vol_targeting", "execution_costs"), False,
        "Momentum y volatilidad, con vigilancia obligada de caídas del momentum y de la "
        "liquidación por su apalancamiento."),
    "ppp_btcusdt": Lens(
        "ppp_btcusdt", "Progressive Profit Protection — BTCUSDT",
        {"C": 1.4, "D": 1.2, "F": 1.1},
        ("trailing_stop", "stop_loss", "disposition", "drawdown"), True,
        "Protección progresiva de la ganancia: literatura de stops dinámicos, efecto disposición "
        "y caídas; entra solo con respaldo."),
}
DEFAULT = LENSES["moderado"]


def lens(profile: str | None) -> Lens:
    return LENSES.get(profile or "", DEFAULT)


def reweigh(evidence: list[dict], category_of: dict[str, str], ln: Lens) -> list[dict]:
    """Reordena fuentes (dicts de `Evidence.to_json`) por peso × multiplicador de categoría."""
    out = []
    for e in evidence:
        m = ln.category_w.get(category_of.get(e["source_id"], ""), 1.0)
        out.append({**e, "profile_weight": round(e["weight"] * m, 3)})
    return sorted(out, key=lambda e: -e["profile_weight"])


def profile_notes(ln: Lens, entry_verdicts: list[str], leverage: float | None,
                  liq_ratio: float | None) -> list[str]:
    """Anotaciones de la lente sobre una operación (no vetan nada)."""
    notes = [ln.focus]
    if ln.require_consensus and "a favor" not in entry_verdicts:
        notes.append("Este perfil pide consenso a favor en la literatura y la entrada no lo "
                     "tiene: queda como no respaldada (la decisión sigue siendo del bróker).")
    if ln.profile == "agresivo" and leverage and leverage >= 5:
        notes.append(f"Apalancamiento {leverage:g}x: la literatura de espirales de liquidez y "
                     "liquidaciones en cripto pesa más en este perfil.")
    if liq_ratio is not None and liq_ratio < 1.5:
        notes.append("El stop está cerca del precio de liquidación aproximado: cualquier hueco "
                     "puede liquidar antes de ejecutar el stop.")
    return notes
