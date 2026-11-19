"""Pre-registro de T187–T189: la asimetría ganancias/pérdidas, medida en sombra (2026-11-18).

Se escribió **antes de mirar** ningún resultado de estas reglas: lo que el usuario vio el 18-nov
(87 operaciones del libro, del 24-oct al 18-nov) queda fuera de la medición, porque solo cuentan
las operaciones abiertas desde `START`. La nota humana es `PLAN/notas/T187_preregistro.md` y
lleva la misma huella que `fingerprint()`; una prueba falla si alguien cambia un valor aquí sin
publicar una versión nueva (cambiar las reglas después de ver los datos es ajustar el resultado).

Las cuatro reglas que se miden (cada operación viva contra lo que habría pasado con la regla):

- **T187a** pérdida acotada a 1 R con costos (`risk_includes_costs`). Ya decidida: se enciende
  sola al cerrar T31 (`PHASE2_FROM`); aquí solo se informa, sin veredicto.
- **T187b** una idea, un solo riesgo: en un perfil, varias entradas en la misma vela y el mismo
  sentido son una sola apuesta; cuenta solo la primera.
- **T187c** el peso no sube por rasguños: por encima de 1 solo con `n ≥ 20` y `m − se > 0` de los
  cierres propios de esa estrategia@marco; si no, el peso se queda en 1.
- **T188** corredor: la mitad sale con la escalera y la otra mitad sigue con el stop inicial,
  break-even tras +1 R y stop móvil a 1 R del extremo, con plazo máximo por marco.
- **T189** entrada límite por defecto: cada idea viva a mercado contra la misma idea como orden
  límite al precio pedido (`maker_ab.pair_up`), por marco, con el criterio de T143.

Puro: sin red, sin disco y sin estado.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

VERSION = "t187_asimetria_v1"
DAY_MS = 86_400_000


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).astimezone(UTC).timestamp() * 1000)


START_ISO = "2026-11-19T00:00:00+00:00"     # solo cuentan operaciones abiertas desde aquí
START_MS = _ms(START_ISO)
T31_CLOSE_ISO = "2026-11-28T00:00:00+00:00"  # = `api.config.T31_CLOSE_UTC` (lo fija una prueba)
T31_CLOSE_MS = _ms(T31_CLOSE_ISO)

# Tres miradas fijas, y solo tres: con una mirada semanal y un IC al 95 % una regla sin efecto
# «pasaría» mucho más del 5 % de las veces. Cada mirada usa α = 0,05/3 (Bonferroni).
CHECKPOINT_DAYS = (28, 56, 84)
LEVEL = 1.0 - 0.05 / len(CHECKPOINT_DAYS)
REPS = 5000
SEED = 187

# Mínimos para que una mirada pueda dar veredicto (si no se cumplen, sigue EN CURSO; en la última
# mirada, sin mínimos o sin IC por encima de 0, NO PASA: se queda lo de hoy).
MIN_N_BOOK = 60          # operaciones de perfil emparejadas (T187b, T187c, T188)
MIN_DAYS = 15            # días distintos con operaciones
MIN_N_IDEAS = 200        # ideas emparejadas por marco (T189)

# T187c
WEIGHT_CAP = 1.0
WEIGHT_MIN_N = 20
WEIGHT_Z = 1.0

# T188
RUNNER_SHARE = 0.5
RUNNER_BE_R = 1.0        # a partir de +1 R el stop del corredor pasa a la entrada + costo
RUNNER_TRAIL_R = 1.0     # y sigue al extremo a 1 R de distancia
RUNNER_MAX_HOLD_MS = {"15m": 2 * DAY_MS, "1h": 5 * DAY_MS, "4h": 14 * DAY_MS}

# T189 (el criterio es el de T143 §4, el mismo con el que se adoptó maker en 1 h y 4 h)
MAKER_BARS = 1.0
MAKER_MIN_COST_DROP_R = 0.04
MAKER_TIMEFRAMES = ("15m", "1h", "4h")

# Fase 2 (◆ del usuario 2026-11-18): al cerrar T31 se encienden solos el riesgo con costos y el
# freno gradual en lugar del todo o nada. Tramos de la rejilla de T136 con parada en 10 %, y el
# último tramo a ×0,25 en vez de 0: el perfil nunca se detiene del todo (◆ del usuario).
PHASE2_DD_STEPS: tuple[tuple[float, float], ...] = ((0.05, 0.5), (0.10, 0.25))

# Fase 3: lo que se adopta solo si PASA. La regla del usuario (T143): solo el costo y el riesgo se
# adaptan solos. T188 cambia la salida, así que aunque pase lo decide el usuario.
AUTO_RULES = ("t187b", "t187c", "t189_15m", "t189_1h", "t189_4h")
USER_RULES = ("t188",)
VERDICT_RULES = ("t187b", "t187c", "t188", "t189_15m", "t189_1h", "t189_4h")
INFO_RULES = ("t187a",)


def checkpoints_ms() -> tuple[int, ...]:
    return tuple(START_MS + d * DAY_MS for d in CHECKPOINT_DAYS)


def frozen() -> dict:
    """Todo lo que fija el pre-registro, en JSON estable."""
    return {"version": VERSION, "start": START_ISO, "t31_close": T31_CLOSE_ISO,
            "checkpoint_days": list(CHECKPOINT_DAYS), "level": LEVEL, "reps": REPS,
            "seed": SEED, "min_n_book": MIN_N_BOOK, "min_days": MIN_DAYS,
            "min_n_ideas": MIN_N_IDEAS, "weight_cap": WEIGHT_CAP, "weight_min_n": WEIGHT_MIN_N,
            "weight_z": WEIGHT_Z, "runner_share": RUNNER_SHARE, "runner_be_r": RUNNER_BE_R,
            "runner_trail_r": RUNNER_TRAIL_R, "runner_max_hold_ms": RUNNER_MAX_HOLD_MS,
            "maker_bars": MAKER_BARS, "maker_min_cost_drop_r": MAKER_MIN_COST_DROP_R,
            "maker_timeframes": list(MAKER_TIMEFRAMES),
            "phase2_dd_steps": [list(s) for s in PHASE2_DD_STEPS],
            "auto_rules": list(AUTO_RULES), "user_rules": list(USER_RULES)}


def fingerprint() -> str:
    raw = json.dumps(frozen(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


#: Huella publicada en `PLAN/notas/T187_preregistro.md`. Si esta prueba falla, alguien cambió el
#: pre-registro: eso exige `VERSION` nueva y una nota nueva, no editar la cifra.
FINGERPRINT = "0d4977fad3a63bb403ee6938578ca5332f7503fca18decec809686d2aafcd286"
