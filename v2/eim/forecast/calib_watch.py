"""Vigía de calibración (T184): juicio automático de la calibración y prueba en sombra. Puro.

La calibración (T19) solo se calculaba al abrir su pestaña. Con el vigía se revisa sola cada
6 h (`eim/api/calib_watch.py`) con reglas fijadas aquí antes de mirar ningún resultado:

- **Control.** `assess` da ok, vigilar o alerta: bandas 50/80/90 lejos de su cobertura nominal,
  error de calibración (ECE) alto o probabilidades claramente peores que la caminata aleatoria.
  Sin muestra efectiva suficiente no hay veredicto, igual que en la pestaña.
- **Retroalimentación, en sombra.** `shadow` vuelve a medir con lo vivido las dos recalibraciones
  pre-registradas de T160 (M1 corrección de priors, M2 isotónica), walk-forward y con Holm sobre
  la misma familia de 2. **Nunca cambia el pronóstico:** T160 cerró la línea porque ninguna pasó
  y en vivo empeoraban, y cambiar las probabilidades a mitad de la corrida de T31 cambiaría su
  objeto. Si una empieza a pasar de forma sostenida, el vigía lo dice y la adopción vuelve a ser
  una decisión con un pre-registro nuevo (`PLAN/T184.md`).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from eim.forecast.calibration import MIN_EVAL, Outcome
from eim.forecast.recal import MIN_FIT, REFIT, Obs, fit_isotonic, fit_priors, walk_forward
from eim.forecast.recal_eval import holm, score

OK, WATCH, ALERT, SUSTAINED, NO_VERDICT = ("ok", "vigilar", "alerta", "alerta_sostenida",
                                           "sin_veredicto")


class WatchParams(BaseModel):
    """Reglas declaradas del vigía (cambiarlas es una versión nueva, no un ajuste mirando datos)."""

    model_config = ConfigDict(frozen=True)

    interval_ms: int = 6 * 3_600_000     # una revisión cada 6 h
    horizon: int = 25                    # el horizonte que publica el panel (DEFAULT_HORIZON)
    min_effective: float = 20.0          # muestra efectiva mínima (n / horizonte) para juzgar
    band_warn: float = 0.05              # |cobertura terminal − nominal| que pide vigilar
    band_alert: float = 0.10             # … que es alerta (las bandas son el rango de la idea)
    ece_warn: float = 0.05               # el mismo umbral de la frase «calibración imperfecta»
    ece_alert: float = 0.10
    skill_floor: float = -0.05           # Brier skill bajo esto: peor que la caminata aleatoria
    shadow_min_eval: int = 100           # evaluaciones recalibradas mínimas tras el ajuste


def assess(rep: dict, p: WatchParams, prev: str | None = None) -> dict:
    """Estado y motivos de un informe de `summarize`; `prev` es el estado de la revisión anterior
    (dos alertas seguidas = alerta sostenida, la única que pinta el mapa en ámbar)."""
    n, ne = rep.get("n_evaluated", 0), rep.get("n_effective") or 0
    if n < MIN_EVAL or ne < p.min_effective:
        return {"state": NO_VERDICT, "level": 0,
                "reasons": [f"muestra insuficiente: {n} evaluados, efectiva ≈ {ne} "
                            f"(mínimo {MIN_EVAL} y {p.min_effective:g})"]}
    level, reasons = 0, []
    for k, c in (rep.get("coverage") or {}).items():
        t = c.get("terminal")
        if t is None:
            continue
        dev = t - c["nominal"]
        if abs(dev) > p.band_warn:
            lv = 2 if abs(dev) > p.band_alert else 1
            level = max(level, lv)
            reasons.append(f"banda {k} %: cubre {t:.0%} frente a {c['nominal']:.0%} nominal")
    ece = rep.get("ece")
    if ece is not None and ece > p.ece_warn:
        level = max(level, 2 if ece > p.ece_alert else 1)
        reasons.append(f"error de calibración {ece:.1%}")
    bs = rep.get("brier_skill")
    if bs is not None and bs < p.skill_floor:
        level = max(level, 1)
        reasons.append(f"probabilidades peores que la caminata aleatoria (skill {bs:+.1%})")
    state = (OK, WATCH, ALERT)[level]
    if level == 2 and prev in (ALERT, SUSTAINED):
        state = SUSTAINED
    return {"state": state, "level": level,
            "reasons": reasons or ["bandas, error de calibración y skill dentro de lo declarado"]}


def to_obs(outs: Sequence[Outcome], horizon: int, step_ms: int) -> list[Obs]:
    """Resultados evaluados → observaciones de T160. El horizonte se da por terminado una vela
    después de la última del camino: el ajuste walk-forward nunca ve un resultado aún abierto."""
    return sorted((Obs(made_at=o.made_at, end_t=o.made_at + (horizon + 1) * step_ms,
                       probs=dict(o.probs), realized=o.realized) for o in outs),
                  key=lambda o: o.made_at)


def shadow(obs: Sequence[Obs], horizon: int, p: WatchParams) -> dict:
    """M1 y M2 de T160 medidas en vivo, sin tocar nada: Brier emparejado, t de una cola en la
    submuestra sin solape (1 de cada `horizon`) y Holm sobre la familia de 2."""
    need = MIN_FIT + p.shadow_min_eval
    if len(obs) < need:
        return {"state": "insuficiente", "n": len(obs), "need": need,
                "note": f"hacen falta {need} pronósticos evaluados ({MIN_FIT} para ajustar y "
                        f"{p.shadow_min_eval} para medir); hay {len(obs)}"}
    res: dict[str, dict] = {}
    for name, fit in (("M1_priors", fit_priors), ("M2_isotonica", fit_isotonic)):
        sc = score(walk_forward(obs, fit, min_fit=MIN_FIT, refit=REFIT), stride=horizon)
        res[name] = {"n": sc["n"], "brier_raw": sc["brier_raw"], "brier_recal": sc["brier_recal"],
                     "d_mean": sc["d_mean_all"], "p": sc["test"]["p"], "ci95": sc["test"]["ci95"],
                     "ece_raw": sc["ece_raw"], "ece_recal": sc["ece_recal"]}
    passed = holm({k: v["p"] for k, v in res.items()})
    for k, v in res.items():
        v["pasa_holm"] = bool(passed[k] and (v["d_mean"] or 0) > 0)
    better = [k for k, v in res.items() if v["pasa_holm"]]
    return {"state": "mejora_en_sombra" if better else "no_mejora", "methods": res,
            "better": better,
            "note": ("en sombra: " + ", ".join(better) + " mejora el Brier con Holm; adoptarla "
                     "exige un pre-registro nuevo (T160 cerró la línea)") if better else
                    "ninguna recalibración mejora en vivo con Holm: el pronóstico sigue igual"}


def shadow_streak(history: Sequence[dict], current: dict) -> int:
    """Revisiones seguidas (con la actual) en que alguna recalibración pasa en sombra."""
    k = 1 if current.get("state") == "mejora_en_sombra" else 0
    if not k:
        return 0
    for h in reversed(history):
        if (h.get("shadow") or {}).get("state") != "mejora_en_sombra":
            break
        k += 1
    return k
