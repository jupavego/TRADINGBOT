"""Etiquetas del marco de evaluación (T80). Puras y sin mirar más allá del horizonte.

Tres etiquetas por horizonte, de la más simple a la más realista:
- **Δmid** (`forward_mid_bps`): retorno del mid en pb, con su máscara de validez (el destino
  existe, es reciente y no hay ningún cubo incompleto entre origen y destino).
- **Dirección neta de costos** (`net_direction`): +1/−1 solo si |Δmid| supera el costo de ida y
  vuelta; 0 si no paga. Es la etiqueta que decide si hay algo que capturar.
- **Triple barrera** (`triple_barrier`): primera barrera tocada por el CAMINO del mid dentro del
  horizonte (±barrera de costo, o 0 si expira). Es la que se parece a una operación.

`passive_fill` responde a la otra mitad del problema: una entrada pasiva solo existe si la cola
se llena. Con cola pesimista (al final de la cola visible, sin avanzar por cancelaciones, como
fija T77 H5): se llena si el volumen agresor contrario que llega mientras el precio sigue ahí
supera la cantidad que había delante.
"""

from __future__ import annotations

import numpy as np

ROUND_TRIPS_BPS = {"taker": 10.0, "mixto": 7.0, "maker": 4.0}   # CostParams VIP 0 (5 / 2 pb)


def _steps(horizon_ms: int, step_ms: int) -> int:
    if step_ms <= 0:
        raise ValueError("step_ms > 0")
    return max(1, int(round(horizon_ms / step_ms)))


def asof_index(t: np.ndarray, offset_ms: int, max_stale_ms: int
               ) -> tuple[np.ndarray, np.ndarray]:
    """(índice de la última fila con t ≤ t_i + offset, válido) sin acortar nunca el desplazamiento.

    Inválido si esa fila está rancia (más de `max_stale_ms` antes del instante pedido) o si el
    instante pedido cae más allá del final de los datos.
    """
    tt = np.asarray(t, dtype=np.int64)
    n = tt.shape[0]
    if n == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, bool)
    j = np.clip(np.searchsorted(tt, tt + offset_ms, side="right") - 1, 0, n - 1)
    fresh = ((tt + offset_ms - tt[j]) <= max_stale_ms) & (tt + offset_ms <= tt[-1])
    return j, fresh


def forward_window_bps(t: np.ndarray, mid: np.ndarray, lag_ms: int, horizon_ms: int,
                       complete: np.ndarray | None = None, max_stale_ms: int = 2_000
                       ) -> tuple[np.ndarray, np.ndarray]:
    """(Δmid en pb entre t+lag y t+lag+horizonte, válido) visto desde la fila t.

    `lag_ms` es la reacción medida en T77 (dato → orden en Binance): la señal se forma al cierre
    del cubo y la entrada ocurre `lag_ms` después, así que el tramo que se puede capturar empieza
    ahí. Una fila solo vale si los dos extremos existen, son recientes, el destino es posterior al
    origen y no hay ningún cubo incompleto desde la fila hasta el destino.
    """
    m = np.asarray(mid, float)
    n = m.shape[0]
    out = np.full(n, np.nan)
    if n < 2:
        return out, np.zeros(n, bool)
    j1, f1 = asof_index(t, lag_ms, max_stale_ms)
    j2, f2 = asof_index(t, lag_ms + horizon_ms, max_stale_ms)
    ok = f1 & f2 & (j2 > j1)
    if complete is not None:
        bad = np.concatenate([[0], np.cumsum(~np.asarray(complete, bool))])
        ok &= (bad[j2 + 1] - bad[np.arange(n)]) == 0
    out[ok] = (m[j2[ok]] / m[j1[ok]] - 1.0) * 1e4
    return out, ok


def forward_mid_bps(t: np.ndarray, mid: np.ndarray, horizon_ms: int,
                    complete: np.ndarray | None = None, max_stale_ms: int = 2_000
                    ) -> tuple[np.ndarray, np.ndarray]:
    """Δmid del horizonte sin reacción (cota de arriba): `forward_window_bps` con lag 0."""
    return forward_window_bps(t, mid, 0, horizon_ms, complete, max_stale_ms)


def net_direction(dmid_bps: np.ndarray, cost_bps: float) -> np.ndarray:
    """+1/−1 si el movimiento paga el ida y vuelta; 0 si no (NaN cuenta como 0)."""
    d = np.nan_to_num(np.asarray(dmid_bps, float), nan=0.0)
    return np.where(np.abs(d) > cost_bps, np.sign(d), 0.0)


def _contiguous(t: np.ndarray, step_ms: int, complete: np.ndarray | None,
                k: int) -> np.ndarray:
    """Filas cuyo cubo i+k existe, es contiguo (paso exacto) y está completo de i a i+k."""
    tt = np.asarray(t, dtype=np.int64)
    n = tt.shape[0]
    ok = np.zeros(n, bool)
    if k >= n:
        return ok
    ok[:n - k] = tt[k:] - tt[:n - k] == k * step_ms
    if complete is not None:
        c = np.asarray(complete, bool)
        bad = np.concatenate([[0], np.cumsum(~c)])
        tail = np.zeros(n, bool)
        tail[:n - k] = (bad[k + 1:n + 1] - bad[:n - k]) == 0
        ok &= tail
    return ok


def triple_barrier(t: np.ndarray, mid: np.ndarray, horizon_ms: int, barrier_bps: float,
                   step_ms: int, complete: np.ndarray | None = None, lag_steps: int = 0
                   ) -> tuple[np.ndarray, np.ndarray]:
    """(etiqueta, válido) de la primera barrera tocada: +1 arriba, −1 abajo, 0 si expira.

    El camino se recorre cubo a cubo hasta el horizonte y una fila solo vale si TODO el tramo es
    contiguo y completo (conservador: se pierden filas, nunca se inventa un camino).

    Límite declarado: el camino se mira al cierre de cada cubo, así que un toque y vuelta dentro
    del mismo cubo (1 s) no se ve. Eso hace la etiqueta OPTIMISTA para la barrera y es otra razón
    para que la decisión de T80 no cuelgue de ella, sino del Δmid neto de costos.
    """
    m = np.asarray(mid, float)
    n = m.shape[0]
    if lag_steps:                      # la entrada ocurre `lag_steps` cubos después de la señal
        lab, val = triple_barrier(t[lag_steps:], m[lag_steps:], horizon_ms, barrier_bps, step_ms,
                                  None if complete is None else complete[lag_steps:])
        pad = np.zeros(lag_steps)
        label = np.concatenate([lab, pad])[:n]
        valid = np.concatenate([val, pad.astype(bool)])[:n]
        return label, valid & _contiguous(t, step_ms, complete, lag_steps)
    k_max = _steps(horizon_ms, step_ms)
    label = np.zeros(n)
    done = np.zeros(n, bool)
    valid = _contiguous(t, step_ms, complete, k_max)
    if complete is not None:
        valid &= np.asarray(complete, bool)
    for k in range(1, k_max + 1):
        step_ok = _contiguous(t, step_ms, complete, k)
        r = np.full(n, np.nan)
        r[:n - k] = (m[k:] / m[:n - k] - 1.0) * 1e4
        hit_up = step_ok & ~done & (r >= barrier_bps)
        hit_dn = step_ok & ~done & (r <= -barrier_bps)
        label[hit_up] = 1.0
        label[hit_dn] = -1.0
        done |= hit_up | hit_dn
    return label, valid


def passive_fill(bid_q: np.ndarray, ask_q: np.ndarray, bid_p: np.ndarray, ask_p: np.ndarray,
                 buy_v: np.ndarray, sell_v: np.ndarray, wait_steps: int, side: int
                 ) -> np.ndarray:
    """¿Se llena una orden pasiva puesta al mejor precio, con cola pesimista?

    `side` = +1 compra al bid, −1 venta al ask. Se acumula el volumen agresor contrario de los
    `wait_steps` cubos siguientes mientras el mejor precio no mejore (si mejora, la orden deja de
    estar al frente y se da por no llena). Se llena si lo acumulado supera la cola que había
    delante al llegar.
    """
    q0 = np.asarray(bid_q if side > 0 else ask_q, float)
    p0 = np.asarray(bid_p if side > 0 else ask_p, float)
    hit = np.asarray(sell_v if side > 0 else buy_v, float)
    n = q0.shape[0]
    acc = np.zeros(n)
    alive = np.ones(n, bool)
    filled = np.zeros(n, bool)
    for k in range(1, max(wait_steps, 1) + 1):
        if k >= n:
            break
        pk = np.concatenate([p0[k:], np.full(k, np.nan)])
        hk = np.concatenate([hit[k:], np.full(k, np.nan)])
        away = (pk > p0) if side > 0 else (pk < p0)       # el precio mejoró: ya no vamos al frente
        alive &= ~np.nan_to_num(away, nan=True).astype(bool)
        acc += np.where(alive, np.nan_to_num(hk, nan=0.0), 0.0)
        filled |= alive & (acc >= q0)
    return filled
