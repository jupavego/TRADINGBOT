"""Zigzag, etiquetado 0-1-2-3-4-5-A-B-C y reglas duras de Elliott (puro; equivale a F7)."""

from __future__ import annotations

from collections.abc import Sequence

from eim.agents.elliott.params import CONTINUATION_CONFIDENCE, LABELS, NEXT_LABEL, WAVE_NOTES


def zigzag(
    t: Sequence[int], high: Sequence[float], low: Sequence[float], pct: float
) -> list[dict]:
    """Pivotes alternados H/L por % de reversión; el último es la extensión aún sin confirmar."""
    n = len(high)
    pivots: list[dict] = []
    if n == 0:
        return pivots

    def add(idx: int, price: float, kind: str) -> None:
        pivots.append({"index": int(idx), "t": int(t[idx]), "price": float(price), "type": kind})

    direction = None
    cand_high, cand_high_idx = high[0], 0
    cand_low, cand_low_idx = low[0], 0
    for i in range(1, n):
        hi, lo = high[i], low[i]
        if direction is None:
            if hi > cand_high:
                cand_high, cand_high_idx = hi, i
            if lo < cand_low:
                cand_low, cand_low_idx = lo, i
            move_up = (cand_high - low[0]) / low[0] * 100
            move_down = (high[0] - cand_low) / high[0] * 100
            if move_up >= pct and move_up >= move_down:
                add(0, low[0], "L")
                direction = "up"
            elif move_down >= pct:
                add(0, high[0], "H")
                direction = "down"
        elif direction == "up":
            if hi > cand_high:
                cand_high, cand_high_idx = hi, i
            if (cand_high - lo) / cand_high * 100 >= pct:
                add(cand_high_idx, cand_high, "H")
                direction = "down"
                cand_low, cand_low_idx = lo, i
        else:
            if lo < cand_low:
                cand_low, cand_low_idx = lo, i
            if (hi - cand_low) / cand_low * 100 >= pct:
                add(cand_low_idx, cand_low, "L")
                direction = "up"
                cand_high, cand_high_idx = hi, i
    if direction == "up":
        add(cand_high_idx, cand_high, "H")
    elif direction == "down":
        add(cand_low_idx, cand_low, "L")
    return pivots


def label_waves(pivots: list[dict]) -> list[dict]:
    """Etiqueta los últimos (hasta 9) pivotes con 0..C; devuelve copias etiquetadas."""
    take = min(len(pivots), 9)
    recent = pivots[-take:] if take else []
    labels = LABELS[9 - take:9 - take + take]
    return [{**p, "wave_label": lbl} for lbl, p in zip(labels, recent, strict=True)]


def validate_rules(labeled: list[dict]) -> list[str]:
    """Violaciones de las 3 reglas duras; vacío si el conteo impulsivo aún no está completo."""
    by = {p["wave_label"]: p["price"] for p in labeled}
    if not all(k in by for k in LABELS[:6]):
        return []
    p0, p1, p2, p3, p4, p5 = (by[k] for k in LABELS[:6])
    up = p1 > p0
    out = []
    if not (p2 > p0 if up else p2 < p0):
        out.append("Onda 2 retrocedió más allá del inicio de la Onda 1 (regla dura violada)")
    len1, len3, len5 = abs(p1 - p0), abs(p3 - p2), abs(p5 - p4)
    if len3 == min(len1, len3, len5):
        out.append("Onda 3 es la más corta entre las ondas impulsivas 1/3/5 (regla dura violada)")
    if not (p4 > p1 if up else p4 < p1):
        out.append("Onda 4 se solapó con el territorio de precio de la Onda 1 (regla dura violada)")
    return out


def estimate_probability(labeled: list[dict], violations: list[str]) -> dict:
    """Probabilidad heurística de que el tramo en curso continúe (NO estadística validada)."""
    if not labeled:
        return {"prob_up_pct": 50.0, "prob_down_pct": 50.0,
                "next_expected_label": None, "wave_note": ""}
    last = labeled[-1]
    label = last["wave_label"]
    cont = CONTINUATION_CONFIDENCE.get(label, 50)
    if violations:
        cont = 50 + (cont - 50) * 0.5
    up, down = (cont, 100 - cont) if last["type"] == "H" else (100 - cont, cont)
    return {"prob_up_pct": round(up, 1), "prob_down_pct": round(down, 1),
            "next_expected_label": NEXT_LABEL.get(label), "wave_note": WAVE_NOTES.get(label, "")}
