"""Suelo de protección recuperado (T110): lo que el diario guardó de una operación abierta con
escalera, aplicado al recalcularla.

La vista del libro se recalcula desde contextos y velas en cada consulta. Si al recalcular (otro
proceso, velas de 1 min que ya no están, parámetros nuevos) el SL vigente queda POR DEBAJO del que
se guardó en vivo, se adopta el guardado desde el instante en que se confirmó (`Floor.t`): el
nivel protegido es siempre el mayor de los dos y nunca baja en silencio (`recovered` lo cuenta).

Una operación queda «estado inconsistente» (`hold`) cuando lo guardado no deja reconstruirla con
seguridad: la instantánea falta o está corrupta (lo decide `protection.load` antes de simular), no
cuadra con la operación recalculada (lado, entrada o cantidad), el recálculo la cerraría ANTES del
instante en que la instantánea la vio viva, o las velas guardadas no llegan hasta ese instante.
Mientras dure, la simulación no la cierra (sin cierre inventado) y el SL no se mueve por lo
guardado; la resuelve una persona (`python -m eim.paper proteccion reconciliar`).

Puro: sin I/O. `run` es el `_Run` de `ladder.py` (estado vivo de la escalera).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from eim.paper.ladder_math import level_of


@dataclass(frozen=True)
class Floor:
    """Último estado guardado válido de una operación abierta (fila del diario)."""

    seq: int                       # fila del diario de la que sale
    t: int                         # instante (ms) en que se confirmó ese SL
    side: int
    fill: float
    qty: float
    stop: float
    level: int
    protected_usd: float | None    # neto protegido del SL guardado (nominal del escalón o BE+)
    max_float_usd: float | None
    source: str = ""               # origen del SL guardado: inicial | escalon | be | recuperado


@dataclass(frozen=True)
class Guard:
    """Lo que el diario sabe de una operación al recalcularla."""

    floor: Floor | None = None     # suelo del SL (último estado guardado válido)
    hold: str = ""                 # motivo del estado inconsistente ("" = consistente)


def _iso(t: int) -> str:
    return datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d %H:%M")


def mismatch(f: Floor, side: int, fill: float, qty: float, tick: float) -> str:
    """Por qué la instantánea no es la misma operación que la recalculada ("" = cuadra)."""
    if f.side != side:
        return f"lado guardado {f.side:+d} ≠ recalculado {side:+d}"
    if abs(f.fill - fill) > max(tick / 2, 1e-9 * abs(fill)):
        return f"entrada guardada {f.fill:g} ≠ recalculada {fill:g}"
    if abs(f.qty - qty) > 1e-6 * max(abs(qty), 1e-12):
        return f"cantidad guardada {f.qty:g} ≠ recalculada {qty:g}"
    return ""


def arm(run, guard: Guard | None, tick: float) -> str:
    """Prepara el suelo de `run`; devuelve el motivo de estado inconsistente ("" si no hay)."""
    if guard is None:
        return ""
    if guard.floor is not None:
        why = mismatch(guard.floor, run.s, run.fill, run.qty, tick)
        if why:
            return guard.hold or f"la instantánea no cuadra con el recálculo ({why})"
        run.floor, run.floor_due = guard.floor, True
    return guard.hold


def adopt(run, t: int) -> None:
    """Aplica el suelo pendiente en `t` (inicio de vela o de minuto ≥ `Floor.t`): si el SL guardado
    protege más que el recalculado, manda el guardado. Nunca baja el SL vigente."""
    f = run.floor
    if not run.floor_due or t < f.t:
        return
    run.floor_due = False
    if (f.stop - run.stop) * run.s <= 0:
        return                                   # el recálculo ya protege igual o más
    lvl = max(run.level, f.level if f.protected_usd is None
              else level_of(f.protected_usd, run.first, run.step_usd))
    run.recovered = {"t": t, "saved_t": f.t, "seq": f.seq, "from_stop": run.stop,
                     "from_level": run.level, "to_stop": f.stop, "to_level": lvl,
                     "saved_level": f.level}
    if f.max_float_usd is not None:
        run.max_float = max(run.max_float, f.max_float_usd)
    run.stop, run.level, run.source = f.stop, lvl, "recuperado"
    run.hist.append({"t": t, "level": lvl, "nominal": f.protected_usd or 0.0, "stop": f.stop,
                     "max_float": run.max_float, "source": "recuperado"})


def early(run, exit_t: int) -> str:
    """Motivo si el recálculo cerraría la operación antes del instante en que lo guardado la vio
    viva (los datos ya no permiten reconstruirla: no se inventa ese cierre)."""
    f = run.floor
    if not run.floor_due or exit_t > f.t:
        return ""
    return (f"el recálculo la cerraría a las {_iso(exit_t)} UTC, antes del estado guardado "
            f"({_iso(f.t)} UTC, SL {f.stop:g}) que la vio viva")


def settle_close(run, reason: str, ex: float, lo: float, hi: float) -> tuple[str, float, str]:
    """Cierre DESPUÉS del instante guardado pero dentro de la vela que lo contiene (suelo aún sin
    aplicar): manda el SL guardado si es mejor y el precio de esa vela pasó por él. Si el cierre
    recalculado fue un hueco a la apertura o la vela no llega al SL guardado, los datos contradicen
    lo guardado: no se inventa ese cierre (motivo de estado inconsistente en el tercer valor)."""
    if not run.floor_due:
        return reason, ex, ""
    gap = (ex - run.stop) * run.s < -1e-9            # salió peor que su propio SL: hueco
    adopt(run, run.floor.t)
    if (run.stop - ex) * run.s <= 0:
        return reason, ex, ""
    if gap or not lo <= run.stop <= hi:
        return "", ex, (f"el recálculo cerraría a {ex:g} sin pasar por el SL guardado "
                        f"({run.stop:g}) en la vela que contiene el estado guardado")
    return "SLD", run.stop, ""


def finish(run, last_end: int) -> str:
    """Al final del camino: aplica el suelo que siga pendiente; motivo de estado inconsistente si
    las velas guardadas no llegan hasta el instante de la instantánea."""
    if not run.floor_due:
        return ""
    t = run.floor.t
    adopt(run, t)
    return ("" if t <= last_end else f"las velas guardadas terminan ({_iso(last_end)} UTC) antes "
            f"del estado guardado ({_iso(t)} UTC)")
