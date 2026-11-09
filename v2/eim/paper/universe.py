"""El universo oficial de la contabilidad (T144): UNA sola función decide qué cuenta.

Antes de T144 había dos contabilidades que no contaban lo mismo y en ningún sitio se decía cuál
mandaba: el informe semanal de T31 veía 1, 0 y 1 operación con resultado en W43–W45 (mide el carril
de ejecución del servicio) mientras el libro fijo de los perfiles cerraba 43, 30, 118 y 23 con
peso. T31 es la puerta al dinero real, así que la diferencia decide algo.

**◆ Decisión del usuario (2026-11-09):** el universo oficial de T31 es el **libro fijo de los
cuatro perfiles** (`paper_ledger`, `scope = perfil`) **excluyendo las filas `retro`**. La corrida
de operación del servicio queda como **vista declarada**, nunca como cifra oficial: es el mismo
modo SIMULADO en otro carril de ejecución, con su propia muestra, y mezclar las dos fue justo lo
que produjo la doble contabilidad.

Quien publique una cifra de resultado pasa por `counts_as_result` y declara `declaration()`: el
informe semanal (`eim.operation.weekly`), el panel (`eim.paper.summary` vía `eim.paper.desk`), el
libro (`eim.api.paper`) y el escuadrón (`eim.bots.scorecard`, que declara que puntúa en SOMBRA y
por tanto nunca publica cifra oficial). Lo prohíbe `tests/paper/test_universe_single.py`.

Nada se borra: una fila que no cuenta se puede consultar con su etiqueta y su motivo
(`tally()["excluded"]`, `retro_rows()`), pero no suma a acierto, esperanza, capital ni drawdown.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from eim.paper.params import PROFILES as _PROFILE_PARAMS

OFFICIAL = "libro_perfiles"          # universo oficial de T31 (◆ 2026-11-09)
SHADOW = "sombra"                    # ideas evaluadas solas, sin peso: aprendizaje, no resultado
OPERATION_VIEW = "corrida_operacion"  # carril de ejecución del servicio: vista, no cifra oficial

PROFILE_SCOPE = "perfil"
LIVE_ORIGIN = "vivo"

#: Qué es el universo oficial, en una frase que viaja con cada cifra publicada.
UNIVERSE_LABEL = ("libro fijo de los cuatro perfiles del bróker simulado (`paper_ledger`, "
                  "`scope = perfil`), operaciones cerradas en vivo y con peso, EXCLUIDAS las "
                  "marcadas `retro`")

#: La regla, dimensión a dimensión. Es la declaración que se publica, no un comentario.
RULE: tuple[tuple[str, str], ...] = (
    ("alcance", "`scope = perfil`: la operación del libro de un perfil, con su tamaño y su PnL en "
                "USDT. La evaluación en sombra (`scope = sombra`) no tiene peso ni dinero: sirve "
                "para aprender y para puntuar al escuadrón, y nunca es cifra de resultado."),
    ("origen", "`origin = vivo`: decidida en tiempo real. Lo reconstruido por backtest no ocurrió "
               "y el libro ya no lo admite."),
    ("perfil", "uno de los cuatro perfiles del bróker simulado (`conservador`, `moderado`, "
               "`agresivo`, `ppp_btcusdt`). Un perfil que no existe hoy se cuenta aparte en vez "
               "de sumarse a ciegas."),
    ("peso", "`weight > 0`: sin peso no hay dinero comprometido, así que no hay resultado."),
    ("retro", "`retro = false`. Una fila `retro` se registró más de 2 h después de su cierre: la "
              "trajo el estreno del libro o un recálculo posterior (T142), y no hay constancia de "
              "que se viviera cuando se cerró. Se puede consultar con su etiqueta; no suma."),
    ("cerrada", "`exit_t` con `r` y `pnl_usdt`: una operación sin resultado calculable se cuenta "
                "como existente pero no entra en acierto ni en esperanza."),
    ("entradas de suelo", "`floor_trade` SÍ cuenta: es dinero vivido igual que el resto. Se "
                          "informa aparte (`floor_trades`) porque la abrió el mínimo de apertura "
                          "(`min_open`) y no una señal, así que su mezcla cambia la lectura."),
)

#: Código de exclusión → por qué queda fuera. Toda cifra publicada lleva este desglose.
EXCLUSIONS: dict[str, str] = {
    SHADOW: "evaluación en sombra: sin peso ni dinero (aprendizaje y puntuación del escuadrón)",
    "no_vivo": "no se decidió en tiempo real (reconstruida por backtest)",
    "perfil_desconocido": "perfil que no está entre los cuatro del bróker simulado",
    "sin_peso": "sin peso: no se comprometió dinero",
    "retro": "registrada más de 2 h después de su cierre (`retro`): nadie la vivió entonces",
    "sin_resultado": "cerrada sin resultado calculable (`r` o `pnl_usdt` ausentes)",
    "abierta": "todavía abierta: no tiene cierre",
    "sin_declarar": "la fila no declara si es `retro`: sin esa columna no se puede saber si se "
                    "vivió, y lo que no se declara no cuenta",
    OPERATION_VIEW: "carril de ejecución del servicio: vista declarada, no cifra oficial",
}

COUNTS_CODE = "cuenta"
#: Los perfiles del bróker simulado, tomados de su definición para que no puedan divergir; que
#: sigan siendo estos cuatro lo fija `tests/paper/test_universe.py`, así que añadir uno es una
#: decisión explícita y no un cambio silencioso del universo oficial.
PROFILES: tuple[str, ...] = tuple(p.id for p in _PROFILE_PARAMS)


@dataclass(frozen=True, slots=True)
class Verdict:
    """¿Esta operación cuenta como resultado? `code` es el motivo, siempre explícito."""

    counts: bool
    code: str

    @property
    def why(self) -> str:
        return ("cuenta como resultado en el universo oficial" if self.counts
                else EXCLUSIONS.get(self.code, self.code))

    def to_json(self) -> dict:
        return {"counts": self.counts, "code": self.code, "why": self.why}


_COUNTS = Verdict(True, COUNTS_CODE)


def _num(x: object) -> float | None:
    """Número o None; el CSV del libro trae cadenas y `''` donde la base tiene NULL."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, int | float):
        return float(x)
    s = str(x).strip()
    if s in ("", "None", "NULL", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def flag(x: object) -> bool:
    """Booleano tolerante: `True`/`'true'`/`'True'`/`1` son verdad; `''` y None, falso."""
    if isinstance(x, bool):
        return x
    if x is None:
        return False
    if isinstance(x, int | float):
        return bool(x)
    return str(x).strip().lower() in ("true", "t", "1", "yes", "sí", "si")


def is_retro(row: Mapping) -> bool:
    """La fila la trajo el estreno del libro o un recálculo, no el momento en que se cerró."""
    return flag(row.get("retro"))


def counts_as_result(row: Mapping, profiles: Sequence[str] = PROFILES) -> Verdict:
    """La ÚNICA respuesta a «¿esta operación cuenta como resultado?».

    `row` es una fila del libro fijo (`eim.paper.ledger.COLS`) o cualquier diccionario que declare
    esas mismas claves; lo que no se declara no cuenta, en vez de colarse por omisión (una fila
    sin columna `retro` no puede saberse vivida, así que queda fuera). Una fila que venga de otro
    carril lo dice con `lane`, y entonces queda fuera por su propio motivo, declarado.
    """
    if (lane := row.get("lane")) and lane != OFFICIAL:
        return Verdict(False, str(lane) if lane in EXCLUSIONS else OPERATION_VIEW)
    scope = row.get("scope")
    if scope != PROFILE_SCOPE:
        return Verdict(False, SHADOW)
    if row.get("origin") != LIVE_ORIGIN:
        return Verdict(False, "no_vivo")
    if row.get("profile") not in profiles:
        return Verdict(False, "perfil_desconocido")
    if (w := _num(row.get("weight"))) is None or w <= 0:
        return Verdict(False, "sin_peso")
    if "retro" not in row:
        return Verdict(False, "sin_declarar")
    if is_retro(row):
        return Verdict(False, "retro")
    if _num(row.get("exit_t")) is None:
        return Verdict(False, "abierta")
    if _num(row.get("r")) is None or _num(row.get("pnl_usdt")) is None:
        return Verdict(False, "sin_resultado")
    return _COUNTS


def result_rows(rows: Iterable[Mapping], profiles: Sequence[str] = PROFILES) -> list[Mapping]:
    """Las filas que cuentan, y solo esas. Toda cifra de resultado sale de aquí."""
    return [r for r in rows if counts_as_result(r, profiles).counts]


def retro_rows(rows: Iterable[Mapping]) -> list[Mapping]:
    """Las `retro`, visibles aparte con su etiqueta (nunca suman)."""
    return [r for r in rows if is_retro(r)]


def tally(rows: Iterable[Mapping], profiles: Sequence[str] = PROFILES) -> dict:
    """Recuento declarado: cuántas existen, cuántas cuentan y por qué quedan fuera las demás."""
    rows = list(rows)
    excluded: dict[str, int] = {}
    counted = 0
    for r in rows:
        v = counts_as_result(r, profiles)
        if v.counts:
            counted += 1
        else:
            excluded[v.code] = excluded.get(v.code, 0) + 1
    return {"universe": OFFICIAL, "n_total": len(rows), "n_counted": counted,
            "excluded": dict(sorted(excluded.items())),
            "excluded_why": {k: EXCLUSIONS.get(k, k) for k in sorted(excluded)},
            "retro": sum(1 for r in rows if is_retro(r))}


def declaration() -> dict:
    """La regla escrita, tal como se publica en la API y en el informe."""
    return {"universe": OFFICIAL, "label": UNIVERSE_LABEL,
            "rule": [{"dimension": d, "regla": t} for d, t in RULE],
            "exclusions": dict(EXCLUSIONS), "profiles": list(PROFILES),
            "decided": "◆ del usuario, 2026-11-09 (T144): el libro de los cuatro perfiles manda; "
                       "la corrida de operación es una vista dentro de él, no la cifra oficial.",
            "source": "data/paper.duckdb · tabla paper_ledger (solo adición, T47/T118)"}
