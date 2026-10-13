"""
EIM-F7 | Módulo 8: Ondas de Elliott (heurística)
==================================================
IMPORTANTE: no existe una forma 100% objetiva de contar ondas de Elliott —
cualquier algoritmo es una heurística sujeta a re-conteo, igual que le pasa
a cualquier analista humano. Este módulo:

  1. Extrae pivotes vía zigzag (umbral % de reversión configurable).
  2. Etiqueta los últimos hasta-9 pivotes como un conteo TENTATIVO
     (impulso 0-1-2-3-4-5 + corrección A-B-C).
  3. Valida el conteo contra las 3 reglas duras de Elliott y reporta
     violaciones explícitas en vez de forzar un conteo que no cumple.

Tratar el resultado como una hipótesis de trabajo, no como un hecho —
la UI debe dejarlo igual de claro que con los umbrales θ del BRM.
"""

import pandas as pd


class EIMElliott:
    LABELS = ["0", "1", "2", "3", "4", "5", "A", "B", "C"]

    NEXT_LABEL = {
        "0": "1", "1": "2", "2": "3", "3": "4", "4": "5",
        "5": "A", "A": "B", "B": "C", "C": None,
    }

    # Confianza de que el tramo AÚN EN FORMACIÓN (el último pivote, sin
    # confirmar) siga extendiéndose en su dirección actual antes de revertir —
    # según las características clásicas de cada onda de Elliott (la onda 3
    # suele ser la más extensa, la 5 suele agotarse, las correcciones 2/4/B
    # suelen estar acotadas por Fibonacci). Base 50 = sin lectura clara.
    CONTINUATION_CONFIDENCE = {
        "0": 50, "1": 55, "2": 40, "3": 65, "4": 40, "5": 35,
        "A": 55, "B": 40, "C": 50,
    }

    WAVE_NOTES = {
        "0": "Punto de partida del conteo — sin lectura direccional todavía.",
        "1": "Onda 1 (impulso inicial) — puede extenderse o revertir pronto; lectura poco definida.",
        "2": "Onda 2 (corrección) — típicamente acotada por Fibonacci; probable que revierta pronto retomando la tendencia.",
        "3": "Onda 3 (impulso, suele ser la más extensa) — mayor probabilidad de que el movimiento actual continúe.",
        "4": "Onda 4 (corrección) — típicamente acotada; probable que revierta pronto retomando la tendencia.",
        "5": "Onda 5 (impulso final, suele mostrar agotamiento/divergencia) — mayor probabilidad de reversión próxima.",
        "A": "Onda A (inicio de corrección) — puede extenderse o revertir; lectura poco definida.",
        "B": "Onda B (rebote dentro de la corrección) — típicamente acotada; probable reversión retomando la corrección.",
        "C": "Onda C (cierre de la corrección) — punto de mayor incertidumbre; posible inicio de un nuevo ciclo.",
    }

    def __init__(self, df: pd.DataFrame, threshold_pct: float = 3.0):
        self.df = df.copy().reset_index(drop=True)
        self.threshold_pct = threshold_pct
        self.pivots = []
        self.labeled = []

    # ── Zigzag: extrae pivotes alternados por % de reversión ───────
    def compute_zigzag(self) -> list:
        df = self.df
        n = len(df)
        pct = self.threshold_pct
        pivots = []
        if n == 0:
            self.pivots = pivots
            return pivots

        highs, lows = df["high"], df["low"]
        direction = None          # None | 'up' | 'down'
        cand_high, cand_high_idx = highs.iloc[0], 0
        cand_low,  cand_low_idx  = lows.iloc[0], 0

        def add_pivot(idx, price, kind):
            pivots.append({
                "index": int(idx),
                "timestamp": str(df["timestamp"].iloc[idx]),
                "price": float(price),
                "type": kind,   # 'H' | 'L'
            })

        for i in range(1, n):
            hi, lo = highs.iloc[i], lows.iloc[i]

            if direction is None:
                if hi > cand_high: cand_high, cand_high_idx = hi, i
                if lo < cand_low:  cand_low,  cand_low_idx  = lo, i
                move_up   = (cand_high - lows.iloc[0])  / lows.iloc[0]  * 100
                move_down = (highs.iloc[0] - cand_low)  / highs.iloc[0] * 100
                if move_up >= pct and move_up >= move_down:
                    add_pivot(0, lows.iloc[0], "L")
                    direction = "up"
                elif move_down >= pct:
                    add_pivot(0, highs.iloc[0], "H")
                    direction = "down"

            elif direction == "up":
                if hi > cand_high:
                    cand_high, cand_high_idx = hi, i
                retrace = (cand_high - lo) / cand_high * 100
                if retrace >= pct:
                    add_pivot(cand_high_idx, cand_high, "H")
                    direction = "down"
                    cand_low, cand_low_idx = lo, i

            elif direction == "down":
                if lo < cand_low:
                    cand_low, cand_low_idx = lo, i
                rally = (hi - cand_low) / cand_low * 100
                if rally >= pct:
                    add_pivot(cand_low_idx, cand_low, "L")
                    direction = "up"
                    cand_high, cand_high_idx = hi, i

        # Pivote final: la extensión vigente, todavía sin confirmar (puede seguir moviéndose)
        if direction == "up":
            add_pivot(cand_high_idx, cand_high, "H")
        elif direction == "down":
            add_pivot(cand_low_idx, cand_low, "L")

        self.pivots = pivots
        return pivots

    # ── Etiqueta los últimos (hasta 9) pivotes como 0-1-2-3-4-5-A-B-C ─
    def label_waves(self) -> list:
        n = len(self.pivots)
        take = min(n, 9)
        recent = self.pivots[-take:] if take else []
        offset = 9 - take
        labels = self.LABELS[offset:offset + take]
        for lbl, piv in zip(labels, recent):
            piv["wave_label"] = lbl
        self.labeled = recent
        return recent

    # ── Valida contra las 3 reglas duras de Elliott ─────────────────
    def validate_rules(self) -> list:
        by_label = {p["wave_label"]: p["price"] for p in self.labeled}
        violations = []
        needed = ["0", "1", "2", "3", "4", "5"]
        if not all(l in by_label for l in needed):
            return violations   # aún no hay conteo impulsivo completo que validar

        p0, p1, p2, p3, p4, p5 = (by_label[l] for l in needed)
        uptrend = p1 > p0

        retrace_ok = (p2 > p0) if uptrend else (p2 < p0)
        if not retrace_ok:
            violations.append("Onda 2 retrocedió más allá del inicio de la Onda 1 (regla dura violada)")

        len1, len3, len5 = abs(p1 - p0), abs(p3 - p2), abs(p5 - p4)
        if len3 == min(len1, len3, len5):
            violations.append("Onda 3 es la más corta entre las ondas impulsivas 1/3/5 (regla dura violada)")

        overlap_ok = (p4 > p1) if uptrend else (p4 < p1)
        if not overlap_ok:
            violations.append("Onda 4 se solapó con el territorio de precio de la Onda 1 (regla dura violada)")

        return violations

    # ── Lectura direccional heurística del tramo en formación ───────
    def estimate_probability(self, violations: list) -> dict:
        """
        Probabilidad de que el precio siga la dirección del tramo en curso
        (el último pivote, aún sin confirmar) vs. que revierta pronto.
        Se apoya en CONTINUATION_CONFIDENCE por onda y se "encoge" hacia 50
        si el conteo actual viola alguna regla dura (menos confiable).
        NO es una probabilidad estadística validada — es una heurística
        explícita, igual que los umbrales θ del BRM.
        """
        if not self.labeled:
            return {"prob_up_pct": 50.0, "prob_down_pct": 50.0,
                     "next_expected_label": None, "wave_note": ""}

        last = self.labeled[-1]
        label = last["wave_label"]
        cont_conf = self.CONTINUATION_CONFIDENCE.get(label, 50)
        if violations:
            cont_conf = 50 + (cont_conf - 50) * 0.5   # conteo cuestionado → menos confianza

        if last["type"] == "H":
            prob_up, prob_down = cont_conf, 100 - cont_conf
        else:
            prob_down, prob_up = cont_conf, 100 - cont_conf

        return {
            "prob_up_pct":         round(prob_up, 1),
            "prob_down_pct":       round(prob_down, 1),
            "next_expected_label": self.NEXT_LABEL.get(label),
            "wave_note":           self.WAVE_NOTES.get(label, ""),
        }

    def run_all(self) -> dict:
        self.compute_zigzag()
        self.label_waves()
        violations = self.validate_rules()
        prob = self.estimate_probability(violations)
        return {
            "pivots":          self.labeled,
            "threshold_pct":   self.threshold_pct,
            "rule_violations": violations,
            "valid_count":     len(violations) == 0,
            **prob,
        }
