"""Atribución (puro, T42): rendimiento APARENTE del líder vs COPIABLE del seguidor y por qué
difieren. Unidad = viaje del líder (T41) cerrado en la ventana, misma clave que la copia.

Aparente = neto del líder × proporción de la subcuenta (lo que «debería» ganar el seguidor
si copiar fuera gratis e instantáneo). Copiable = neto real de la subcuenta en esos viajes.
Diferencia = suma exacta de causas (cada una es su aporte a «copiable − aparente»):
- latencia: el precio medio se movió entre la ejecución del líder y nuestra orden;
- diferencial: cruzar el libro (ask/bid frente al medio);
- comisiones y funding: los nuestros frente a los del líder a nuestro tamaño;
- no copiadas: viajes que el seguidor no abrió (deslizamiento, mínimo, riesgo, pausa…);
- tamaño: nuestro tamaño real frente a la proporción (topes, redondeo, tope de riesgo);
- resto: lo demás (aumentos omitidos a mitad, cierres por stop, redondeo de cantidades).
Los viajes abiertos al final (de cualquiera de los dos) quedan fuera de la comparación.
"""

from __future__ import annotations

from collections import defaultdict

from eim.copytrading.copy_book import ClosedTrip
from eim.copytrading.copy_models import CopyFill
from eim.copytrading.trades import Trip
from eim.core.market import Frozen

CAUSES = ("latencia", "diferencial", "comisiones", "funding", "no_copiadas", "tamano", "resto")


class TripCompare(Frozen):
    coin: str
    trip_t: int
    ratio: float | None
    copied: bool
    skip: str | None = None
    leader_net: float
    leader_notional: float
    follower_net: float | None = None
    follower_notional: float | None = None
    exit: str = ""  # cómo cerró la copia: lider | stop | kill | …
    causes: dict[str, float] = {}


class Attribution(Frozen):
    leader_id: str
    trips: int = 0  # viajes del líder cerrados en la ventana
    copied: int = 0
    skipped: int = 0
    open_at_end: int = 0
    unregistered: int = 0  # viajes sin registro en la copia (no deberían existir)
    leader_raw: float = 0.0  # neto real del líder (USD) en los viajes comparados
    apparent: float = 0.0  # neto del líder × proporción
    follower: float = 0.0
    causes: dict[str, float] = {}
    skipped_by: dict[str, float] = {}  # aporte de las no copiadas por motivo
    skipped_n: dict[str, int] = {}
    leader_bps: float | None = None  # en los viajes copiados, sobre su nocional máximo
    follower_bps: float | None = None
    rows: list[TripCompare] = []


def _notional_max(fs: list[CopyFill]) -> float:
    pos = best = 0.0
    for f in fs:
        pos += f.side * f.qty
        best = max(best, abs(pos) * f.price)
    return best


def attribute(leader_id: str, trips: list[Trip], fills: list[CopyFill],
              closed: list[ClosedTrip], trip_info: dict[str, dict],
              open_coins: dict[str, int | None]) -> Attribution:
    """`open_coins`: moneda → viaje del líder de cada posición propia aún abierta."""
    by_fills: dict[tuple[str, int], list[CopyFill]] = defaultdict(list)
    for f in fills:
        if f.trip_t is not None:
            by_fills[(f.coin, f.trip_t)].append(f)
    net: dict[tuple[str, int], float] = defaultdict(float)
    for c in closed:
        if c.trip_t is not None:
            net[(c.coin, c.trip_t)] += c.net
    still = {(c, t) for c, t in open_coins.items() if t is not None}
    acc = dict.fromkeys(CAUSES, 0.0)
    skipped_by: dict[str, float] = defaultdict(float)
    skipped_n: dict[str, int] = defaultdict(int)
    rows: list[TripCompare] = []
    n = copied = skipped = open_end = unreg = 0
    raw = app_tot = fol_tot = l_bps_net = l_bps_not = f_bps_net = f_bps_not = 0.0
    for tr in (t for t in trips if t.closed and t.complete):
        key = (tr.symbol, tr.t_open)
        info = trip_info.get(f"{tr.symbol}:{tr.t_open}")
        if info is None:
            unreg += 1
            continue
        fs, ratio = by_fills.get(key, []), info.get("ratio")
        if key in still:
            open_end += 1
            continue
        n += 1
        if not (info.get("copied") and fs):
            code = info.get("excluded") or (info.get("skips") or ["sin_orden"])[0]
            code = code.split(":", 1)[-1] if code.startswith("excluido:") else code
            skipped += 1
            skipped_n[code] += 1
            loss = -tr.net * (ratio or 0.0)
            acc["no_copiadas"] += loss
            skipped_by[code] += loss
            app_tot += tr.net * (ratio or 0.0)
            raw += tr.net
            rows.append(TripCompare(coin=tr.symbol, trip_t=tr.t_open, ratio=ratio, copied=False,
                                    skip=code, leader_net=tr.net,
                                    leader_notional=tr.notional_max,
                                    causes={"no_copiadas": loss}))
            continue
        copied += 1
        ratio = ratio or 0.0
        f_net = net.get(key, 0.0)
        f_fees = sum(f.fee for f in fs)
        f_fund = f_net - (sum(f.realized for f in fs) - f_fees)
        f_not = _notional_max(fs)
        s = f_not / tr.notional_max if tr.notional_max else 0.0
        c = {
            "latencia": -sum((f.mid - f.leader_px) * f.qty * f.side for f in fs
                             if f.mid is not None and f.leader_px is not None),
            "diferencial": -sum((f.price - f.mid) * f.qty * f.side for f in fs
                                if f.mid is not None),
            "comisiones": -(f_fees - tr.fees * s),
            "funding": f_fund - tr.funding * s,
            "tamano": tr.net * (s - ratio),
        }
        app = tr.net * ratio
        c["resto"] = (f_net - app) - sum(c.values())
        for k, v in c.items():
            acc[k] += v
        raw += tr.net
        app_tot += app
        fol_tot += f_net
        l_bps_net, l_bps_not = l_bps_net + tr.net, l_bps_not + tr.notional_max
        f_bps_net, f_bps_not = f_bps_net + f_net, f_bps_not + f_not
        rows.append(TripCompare(coin=tr.symbol, trip_t=tr.t_open, ratio=ratio, copied=True,
                                leader_net=tr.net, leader_notional=tr.notional_max,
                                follower_net=f_net, follower_notional=f_not,
                                exit=fs[-1].kind if fs[-1].kind in ("stop", "kill") else "lider",
                                causes=c))
    return Attribution(
        leader_id=leader_id, trips=n, copied=copied, skipped=skipped, open_at_end=open_end,
        unregistered=unreg, leader_raw=raw, apparent=app_tot, follower=fol_tot, causes=acc,
        skipped_by=dict(skipped_by), skipped_n=dict(skipped_n),
        leader_bps=l_bps_net / l_bps_not * 1e4 if l_bps_not else None,
        follower_bps=f_bps_net / f_bps_not * 1e4 if f_bps_not else None, rows=rows)
