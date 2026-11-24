"""Patrón de apertura de sesión (T211): medición hacia delante, con criterios congelados.

Mide, en velas de 1 m, qué hace el precio tras la apertura de cada plaza y qué habría dado
operar las reglas que el usuario describió. Los criterios NO se eligen aquí: vienen del
pre-registro `prereg_apertura_v1.json`, congelado con su huella antes de acumular muestra, para
que la medición hacia delante no se pueda ajustar a lo que vaya saliendo (patrón de T137/T139).

Tramo A = las `k` primeras velas desde la apertura (cierre de la k-ésima / apertura de la 1.ª).
Variantes evaluadas, todas con entrada en la apertura de la vela k+1:
  - `contra_a`: en contra del tramo A, salida a `h` minutos;
  - `canal_rebote`: límite en el borde del canal de apertura (alto/bajo de las k velas),
    objetivo en el borde opuesto, stop a una anchura;
  - `canal_ruptura`: entrada al romper el borde, objetivo una anchura, stop en el medio.
Funciones puras sobre arrays; el I/O y el informe viven en `apertura_report.py`.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from eim.core import Candle

MIN_MS = 60_000
PREREG_DIR = Path(__file__).resolve().parents[1] / "validation" / "prereg"
DEFAULT_VERSION = "prereg_apertura_v1"
# SHA-256 (fin de línea LF) de cada versión publicada. Solo se añaden entradas: cambiar un
# criterio es un archivo nuevo con reloj nuevo, nunca una edición del publicado.
PUBLISHED: dict[str, str] = {
    "prereg_apertura_v1": "0411f8fc4069465432d6d78e431342e2022d57a9d5a7eb16941847c545d1f572",
}
SENTIDOS = ("revirtio", "continuo")
# Ventana de las variantes de canal, tal como la fija el pre-registro: 30 min para que el
# límite se llene y un tope de 240 min (4 h) a la operación abierta.
VENTANA_LLENADO = 30
TOPE_MIN = 240


def file_hash(raw: bytes) -> str:
    """Huella sobre fin de línea LF: el mismo archivo da la misma en todo equipo (T32)."""
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


@dataclass(frozen=True)
class Bars:
    """Rejilla de minutos completa; los huecos quedan NaN y nunca se rellenan."""

    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    low: np.ndarray
    c: np.ndarray

    def __len__(self) -> int:
        return int(self.t.size)


def bars_from_candles(candles: Sequence[Candle]) -> Bars:
    """Construye la rejilla de 1 m entre la primera y la última vela, sin inventar nada."""
    if not candles:
        return Bars(*(np.array([], dtype=float) for _ in range(5)))
    xs = sorted(candles, key=lambda c: c.t)
    t0, t1 = xs[0].t, xs[-1].t
    grid = np.arange(t0, t1 + MIN_MS, MIN_MS, dtype=np.int64)
    pos = {int(t): i for i, t in enumerate(grid)}
    arrs = {k: np.full(grid.size, np.nan) for k in ("o", "h", "low", "c")}
    for cd in xs:
        i = pos.get(cd.t)
        if i is None:
            continue
        arrs["o"][i], arrs["h"][i], arrs["low"][i], arrs["c"][i] = cd.o, cd.h, cd.l, cd.c
    return Bars(grid, arrs["o"], arrs["h"], arrs["low"], arrs["c"])


def opens(bars: Bars, tz: str, hh: int, mm: int, weekdays_only: bool = True) -> np.ndarray:
    """Índices de los minutos de apertura, en hora local de la plaza (respeta el verano)."""
    if len(bars) == 0:
        return np.array([], dtype=int)
    zone = ZoneInfo(tz)
    out = []
    for i, ms in enumerate(bars.t):
        loc = _local(int(ms), zone)
        if loc[3] == hh and loc[4] == mm and (not weekdays_only or loc[6] < 5):
            out.append(i)
    return np.array(out, dtype=int)


def _local(ms: int, zone: ZoneInfo) -> tuple[int, int, int, int, int, int, int]:
    from datetime import UTC, datetime

    d = datetime.fromtimestamp(ms / 1000, UTC).astimezone(zone)
    return (d.year, d.month, d.day, d.hour, d.minute, d.second, d.weekday())


def leg_a(bars: Bars, i0: int, k: int) -> float:
    """Tramo A en tanto por uno; NaN si falta alguna vela."""
    if i0 + k - 1 >= len(bars):
        return float("nan")
    o, c = bars.o[i0], bars.c[i0 + k - 1]
    return float(c / o - 1.0) if np.isfinite(o) and np.isfinite(c) and o else float("nan")


def contra_a(bars: Bars, i0: int, k: int, h: int, costo_bps: float) -> dict | None:
    """Operación en contra del tramo A, salida a `h` minutos. bps netos de coste."""
    a = leg_a(bars, i0, k)
    if not np.isfinite(a) or a == 0.0 or i0 + k + h - 1 >= len(bars):
        return None
    ent, sal = bars.o[i0 + k], bars.c[i0 + k + h - 1]
    if not (np.isfinite(ent) and np.isfinite(sal) and ent):
        return None
    lado = -1.0 if a > 0 else 1.0
    bruto = 1e4 * lado * (sal / ent - 1.0)
    return {"a_bps": 1e4 * a, "lado": lado, "entrada": float(ent),
            "bruto_bps": float(bruto), "neto_bps": float(bruto - costo_bps),
            "sentido": SENTIDOS[0] if bruto > 0 else SENTIDOS[1]}


def canal(bars: Bars, i0: int, k: int) -> tuple[float, float] | None:
    """Alto y bajo de las k primeras velas: el canal de apertura."""
    if i0 + k > len(bars):
        return None
    alto, bajo = np.nanmax(bars.h[i0:i0 + k]), np.nanmin(bars.low[i0:i0 + k])
    if not (np.isfinite(alto) and np.isfinite(bajo)) or alto <= bajo:
        return None
    return float(alto), float(bajo)


def _primer(cond: np.ndarray) -> int:
    return int(np.argmax(cond)) if cond.any() else 10**9


def _salida(bars: Bars, s: int, e: int, lado: float, obj: float, stop: float) -> tuple[float, int, str]:
    """Primer toque entre objetivo y stop; empate en el mismo minuto se cuenta como stop."""
    ah, ab, cc = bars.h[s:e], bars.low[s:e], bars.c[s:e]
    if lado > 0:
        i_obj, i_stop = _primer(ah >= obj), _primer(ab <= stop)
    else:
        i_obj, i_stop = _primer(ab <= obj), _primer(ah >= stop)
    if min(i_obj, i_stop) == 10**9:
        return float(cc[-1]), int(cc.size), "tope"
    if i_stop <= i_obj:
        return stop, i_stop + 1, "stop"
    return obj, i_obj + 1, "objetivo"


def ventana_cerrada(bars: Bars, i0: int, k: int, ventana: int = VENTANA_LLENADO,
                    tope: int = TOPE_MIN) -> bool:
    """¿Cabe entera en la rejilla la ventana de esa apertura?

    Mientras no quepa, la apertura no está medida sino a medias: las variantes de canal
    devolverían vacío por falta de vela, no por lo que hizo el precio. Quien acumula muestra
    debe esperar a la corrida siguiente en vez de congelar una fila incompleta.
    """
    return i0 + k + ventana + tope < len(bars)


def canal_op(bars: Bars, i0: int, k: int, modo: str, ventana: int, tope: int,
             costo_bps: float) -> dict | None:
    """`rebote` (límite en el borde) o `ruptura` (entrada al romperlo). None si falta vela."""
    bordes = canal(bars, i0, k)
    if bordes is None or i0 + k + ventana + tope >= len(bars):
        return None
    alto, bajo = bordes
    ancho, medio = alto - bajo, 0.5 * (alto + bajo)
    fill = None
    for i in range(i0 + k, i0 + k + ventana):
        if not (np.isfinite(bars.h[i]) and np.isfinite(bars.low[i])):
            continue
        if modo == "rebote":
            baja, sube = bars.low[i] < bajo, bars.h[i] > alto
            if baja and sube:
                return {"lleno": False, "ambigua": True, "ancho_bps": 1e4 * ancho / medio}
            if baja:
                fill = (i, +1.0, bajo)
            elif sube:
                fill = (i, -1.0, alto)
        else:
            if bars.h[i] > alto and bars.low[i] < bajo:
                return {"lleno": False, "ambigua": True, "ancho_bps": 1e4 * ancho / medio}
            if bars.h[i] > alto:
                fill = (i, +1.0, alto)
            elif bars.low[i] < bajo:
                fill = (i, -1.0, bajo)
        if fill:
            break
    if fill is None:
        return {"lleno": False, "ambigua": False, "ancho_bps": 1e4 * ancho / medio}
    i, lado, ent = fill
    if modo == "rebote":
        obj, stop = (alto if lado > 0 else bajo), ent - lado * ancho
    else:
        obj, stop = ent + lado * ancho, medio
    sal, dur, motivo = _salida(bars, i + 1, i + 1 + tope, lado, obj, stop)
    bruto = 1e4 * lado * (sal / ent - 1.0)
    return {"lleno": True, "ambigua": False, "ancho_bps": 1e4 * ancho / medio, "lado": lado,
            "entrada": float(ent), "espera_min": i - (i0 + k) + 1, "dur_min": dur,
            "motivo": motivo, "bruto_bps": float(bruto), "neto_bps": float(bruto - costo_bps)}


def resumen(xs: Sequence[float]) -> dict:
    """n, media, mediana, sd, t de Student contra cero, aciertos y acumulado (en bps)."""
    r = np.asarray([x for x in xs if np.isfinite(x)], dtype=float)
    n = int(r.size)
    if n == 0:
        return {"n": 0}
    sd = float(r.std(ddof=1)) if n > 1 else 0.0
    return {"n": n, "media_bps": float(r.mean()), "mediana_bps": float(np.median(r)),
            "sd_bps": sd, "t": float(r.mean() / (sd / math.sqrt(n))) if sd else 0.0,
            "aciertos_pct": 100.0 * float((r > 0).mean()), "total_bps": float(r.sum())}


def n_necesaria(sd_bps: float, filo_bps: float) -> float:
    """Aperturas para distinguir `filo` de cero al 95 % con potencia del 80 %."""
    if not filo_bps:
        return float("inf")
    return (2.80 * sd_bps / abs(filo_bps)) ** 2


def veredicto(s: dict, base: dict, umbral_t: float) -> str:
    """Compara lo medido hacia delante con la línea base congelada del pre-registro."""
    if s.get("n", 0) < base.get("n_minima", 0):
        return f"sin veredicto: {s.get('n', 0)} de {base.get('n_minima', 0)} aperturas"
    if s["media_bps"] > 0 and s["t"] >= umbral_t:
        return "PASA: filo positivo neto de coste y significativo hacia delante"
    if s["media_bps"] <= 0:
        return "NO PASA: la media hacia delante es negativa o nula, como en la línea base"
    return f"NO CONCLUYE: media {s['media_bps']:+.2f} bps con t = {s['t']:+.2f}"


def load_prereg(version: str = DEFAULT_VERSION, path: str | Path | None = None,
                strict: bool = True) -> dict:
    """Lee el pre-registro y comprueba su huella si está publicada."""
    p = Path(path) if path is not None else PREREG_DIR / f"{version}.json"
    raw = p.read_bytes()
    data = json.loads(raw)
    if data.get("version") != p.stem:
        raise ValueError(f"versión '{data.get('version')}' no coincide con {p.name}")
    digest = file_hash(raw)
    pinned = PUBLISHED.get(p.stem)
    if strict and pinned and pinned != digest:
        raise ValueError(f"{p.name} fue modificado después de publicarse: cualquier cambio es "
                         f"una versión nueva con reloj nuevo, no una edición. Huella: {digest}")
    data["sha256"] = digest
    return data
