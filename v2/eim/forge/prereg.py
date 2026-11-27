"""Pre-registro inmutable de la familia `forja_5m_v1` (T208).

Se declara **antes** de calcular un solo rendimiento: la rejilla, su `m` (que es el número de
intentos de todas las correcciones), la sesión, las normas de la cuenta, los tramos, la reserva,
los criterios de supervivencia y la semilla. `FINGERPRINT` está fijada en el código: si alguien
cambia cualquier valor, la prueba `tests/forge/test_prereg.py` falla y lo que salga es otra
familia (`forja_5m_v2`), con reloj nuevo y sin recalcular el pasado.

    python -m eim.forge prereg --write     # escribe el JSON que se commitea
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from eim.core.fees import USDM_MAKER, USDM_TAKER
from eim.forge import space

VERSION = "forja_5m_v1"
DECLARED = "2026-11-21"
PATH = Path(__file__).resolve().parents[1] / "validation" / "prereg" / f"prereg_{VERSION}.json"

#: Huella del pre-registro, fijada a mano al declararlo (ver `python -m eim.forge prereg`).
FINGERPRINT = "573b4e4602d5f084"

HOLDOUT_FROM = "2026-05-04"      # reserva intacta: se mira una sola vez, al final
CRITERIA = {
    "min_trades": 200,
    "alpha_rw": 0.05,
    "dsr_min": 0.95,
    "pbo_max": 0.20,
    "cost_stress": [1.5, 2.0],
    "cost_stress_must_pass": 1.5,
    "bootstrap_reps": 1000,
    "cscv_splits": 8,
    "seed": 20261121,
}


def declaration() -> dict:
    """El pre-registro completo (sin ninguna cifra de rendimiento)."""
    return {
        "version": VERSION,
        "declared": DECLARED,
        "description": (
            "Pre-registro de la forja (fase 33, T208): perfil BTCUSDT de 5 m, intradía, sesión "
            "americana, con la rejilla completa de recetas congelada ANTES de medir. El número de "
            "recetas es el m de Romano-Wolf, Holm y e-BH y el attempts del Sharpe deflactado. "
            "Familia propia: no toca la cantera (prereg_cantera_v1) ni su techo de 50."),
        "mode": "ANALISIS",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "data": {
            "source": "banco de T131 (copia inmutable), 1 m 2022-12-31 -> 2026-11-03, 0 huecos",
            "aggregation": "5 m agregado del 1 m, solo grupos completos de 5 velas",
            "funding": "tasas reales del banco; se cobran si la posicion cruza su liquidacion",
            "not_available": ["libro y microestructura HFT", "interes abierto", "ratio largo/corto",
                              "DVOL", "liquidaciones", "noticias y calendario macro"],
        },
        "session": {
            "zone": "America/New_York", "hours": "09:30-16:00", "weekdays": "lunes a viernes",
            "excluded": "festivos de NYSE y medias sesiones (cierre 13:00 ET)",
            "signals_in": "[09:35, 15:00)", "forced_flat": "cierre de la ultima vela (16:00 ET)",
            "bars_per_session": 78,
        },
        "rules": {
            "equity": 10_000.0, "compounding": False, "risk_frac": 0.01, "r_dollar": 100.0,
            "max_leverage": 10.0, "max_notional": 100_000.0,
            "size": "q = R / |entrada - stop|, recortada al tope de nocional (riesgo <= 1 %)",
            "entry": "a mercado en la apertura de la vela siguiente a la senal",
            "taker_fee": USDM_TAKER, "maker_fee": USDM_MAKER,
            "slippage": "CostParams del proyecto; entradas 0,1 pb; salidas a mercado 1 pb + "
                        "0,10*(h-l)/o + impacto, tope 100 pb; el objetivo es limite (maker)",
            "intrabar": "si caben stop y objetivo en la misma vela, se asume el stop primero",
            "exit_flip": ("la salida por giro mira el disparador CRUDO (sin direccion ni filtro) "
                          "y sale a mercado al cierre de la vela de la senal contraria"),
            "one_position_at_a_time": True,
        },
        "grid": {
            "fingerprint": space.grid_fingerprint(),
            "triggers": len(space.TRIGGERS),
            "families": {f: sum(1 for t in space.TRIGGERS if t.family == f)
                         for f in space.FAMILIES},
            "directions": list(space.DIRECTIONS),
            "filters": sorted(space.FILTERS),
            "exits": [e.id for e in space.EXITS],
            "m": len(space.enumerate_recipes()),
        },
        "windows": {
            "in_sample": f"primera vela del banco -> {HOLDOUT_FROM} (excluido)",
            "holdout": f"{HOLDOUT_FROM} -> ultima vela del banco, mirada UNA vez al final",
            "blocks": "un dia de sesion (todos los remuestreos)",
        },
        "criteria": CRITERIA,
        "primary_metric": "R medio neto por operacion (E[R])",
        "corrections": {"main": "Romano-Wolf (StepM)", "reference": ["Holm", "e-BH q=0,10"],
                        "deflated_sharpe": "attempts = m", "pbo": "CSCV, 8 tramos"},
        "controls": ["entradas al azar con la misma cadencia y las mismas salidas",
                     "valor esperado del maximo nulo publicado junto al mejor resultado"],
        "promotion": ("ningun superviviente entra en la cantera por si solo: se propone con ◆ para "
                      "una plaza de reserva y, si se aprueba, opera hacia adelante desde cero"),
    }


def fingerprint(decl: dict | None = None) -> str:
    blob = json.dumps(decl or declaration(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def write(path: Path | None = None) -> Path:
    decl = declaration()
    out = {**decl, "fingerprint": fingerprint(decl)}
    p = path or PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p
