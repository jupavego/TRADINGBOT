"""Agregación por vela de la microestructura: lo que se calcula una vez y se guarda (T206).

Aquí vive la parte sin disco de `eim.data.micro`, para que la caché de velas cerradas
(`eim.data.micro_cache`) pueda guardar exactamente lo que `combine` calcularía, sumando en el
mismo orden. Dos detalles que no son adorno:

- **Dos OFI por vela.** El OFI empareja cada foto del libro con la anterior. En mitad de una
  ventana, la primera foto de una vela se empareja con la última de la vela anterior
  (`ofi`); en la primera vela con datos de la ventana no hay pareja previa y esa foto no
  aporta (`ofi0`). Guardar los dos deja la caché independiente de dónde empiece la ventana.
- **Firma de huecos.** Un hueco de la captura puede anotarse tarde y cambia el OFI (los pares
  que lo cruzan no cuentan) y `complete`. `gap_signature` cuenta los tramos que tocan la vela y
  la anterior: si cambia, la vela se recalcula en vez de darse por buena.
"""

from __future__ import annotations

from bisect import bisect_right

from eim.core import MicroBar

# (buy, sell, trades, ofi, ofi0, Σ desequilibrio, nº, hubo fotos)
Agg = tuple[float, float, int, float, float, float, int, bool]
EMPTY: Agg = (0.0, 0.0, 0, 0.0, 0.0, 0.0, 0, False)


def ofi_step(prev: tuple, cur: tuple) -> float:
    """Evento OFI entre dos muestras (bid_p, bid_q, ask_p, ask_q) del mejor nivel."""
    bp0, bq0, ap0, aq0 = prev
    bp1, bq1, ap1, aq1 = cur
    e = (bq1 if bp1 >= bp0 else 0.0) - (bq0 if bp1 <= bp0 else 0.0)
    e -= (aq1 if ap1 <= ap0 else 0.0) - (aq0 if ap1 >= ap0 else 0.0)
    return e


def missing_ranges(faltan: list[int]) -> list[tuple[int, int]]:
    """Los índices que faltan, como tramos contiguos `[a, b]` (ambos incluidos)."""
    out: list[tuple[int, int]] = []
    for i in sorted(faltan):
        if out and i == out[-1][1] + 1:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


def gap_signature(spans: list[tuple[int, int]], t0: int, step: int, n: int) -> list[int]:
    """Por vela, cuántos tramos de hueco la tocan a ella o a la anterior (la del encadenado)."""
    sig = [0] * n
    for a, b in spans:
        lo, hi = (a - t0) // step - 1, (b - t0) // step + 1
        if hi < 0 or lo > n - 1:
            continue
        for i in range(max(lo, 0), min(hi, n - 1) + 1):
            sig[i] += 1
    return sig


def entries_from_tops(tops: list[tuple], prev: tuple | None, t0: int, step: int, n: int,
                      gaps_sorted: list[int]) -> dict[int, list]:
    """Agregados de las fotos del libro, vela a vela, en el orden de suma de `combine`.

    `prev` es la última foto **anterior** a la ventana (su `t` y sus cuatro campos), o `None`.
    Devuelve `{i: [ofi, ofi0, Σ desequilibrio, nº, hubo fotos]}` solo de las velas con fotos.
    """
    out: dict[int, list] = {}
    for row in tops:
        t = row[0]
        i = (t - t0) // step
        cur = row[1:5]
        if 0 <= i < n:
            e = out.get(i)
            if e is None:
                e = out[i] = [0.0, 0.0, 0.0, 0, True]
                primera = True
            else:
                primera = False
            bq, aq = row[5], row[6]
            if bq + aq > 0:
                e[2] += (bq - aq) / (bq + aq)
                e[3] += 1
            if prev is not None and (bisect_right(gaps_sorted, t)
                                     == bisect_right(gaps_sorted, prev[0])):
                paso = ofi_step(prev[1], cur)
                e[0] += paso
                if not primera:
                    e[1] += paso
        prev = (t, cur)
    return out


def assemble(aggs: list[Agg], bad: list[bool], t0: int, step: int) -> list[MicroBar]:
    """Las velas publicables: la primera con fotos usa su OFI sin pareja previa (`ofi0`)."""
    primera = next((i for i, a in enumerate(aggs) if a[7]), None)
    return [
        MicroBar(t=t0 + i * step, ofi=a[4] if i == primera else a[3], delta=a[0] - a[1],
                 buy_v=a[0], sell_v=a[1], trades=a[2],
                 depth_imb=a[5] / a[6] if a[6] else None, complete=not bad[i])
        for i, a in enumerate(aggs) if a[2] or a[7]
    ]
