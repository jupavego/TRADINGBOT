"""El espacio de recetas de la forja (T208): disparadores por familia, dirección, filtro y salida.

`receta = disparador(familia · variable · periodo · umbral) × dirección × filtro × salida`

Los disparadores son **eventos**, no estados (un cruce, una ruptura, un toque de extremo): un
estado persistente dispararía en cada vela y la receta sería «estar dentro», no una señal. Todos
son simétricos; la dirección decide qué lado se toma. Un disparador devuelve +1 (compra), −1
(venta) o 0 en cada vela, mirando solo variables causales de `features.py`.

Cambiar cualquier cosa de esta rejilla es **otra familia** (`forja_5m_v2`), con su `m` y su
pre-registro: el número de recetas es el número de intentos de las correcciones.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from eim.indicators._core import shift

Feat = dict[str, np.ndarray]
FAMILIES = ("tendencia", "ruptura", "reversion", "momento", "flujo", "volatilidad", "hora")
DIRECTIONS = ("largo", "corto", "ambos")


# --- utilidades de señal (todas causales: comparan `i` con `i−1`) --------------------------
def _ev(up: np.ndarray, dn: np.ndarray) -> np.ndarray:
    return up.astype(np.int8) - dn.astype(np.int8)


def cross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """+1 si `a` cruza `b` al alza en la vela, −1 a la baja, 0 si no."""
    pa, pb = shift(a, 1), shift(b, 1)
    return _ev((pa <= pb) & (a > b), (pa >= pb) & (a < b))


def cross_zero(x: np.ndarray) -> np.ndarray:
    return cross(x, np.zeros_like(x))


def band_break(c: np.ndarray, hi: np.ndarray, lo: np.ndarray) -> np.ndarray:
    """Ruptura de nivel: +1 al cerrar por encima de `hi` por primera vez, −1 por debajo de `lo`."""
    pc = shift(c, 1)
    return _ev((c > hi) & (pc <= shift(hi, 1)), (c < lo) & (pc >= shift(lo, 1)))


def band_fade(x: np.ndarray, lo_th: float, hi_th: float) -> np.ndarray:
    """Toque de extremo: +1 al entrar en sobreventa (`< lo_th`), −1 en sobrecompra (`> hi_th`)."""
    px = shift(x, 1)
    return _ev((x < lo_th) & (px >= lo_th), (x > hi_th) & (px <= hi_th))


def _spike(f: Feat, name: str, mult: float) -> np.ndarray:
    """Pico de una razón (volumen, rango, tamaño): la dirección la pone el cuerpo de la vela."""
    x = f[name]
    ev = (x > mult) & (shift(x, 1) <= mult)
    return (ev * np.sign(f["c"] - f["o"])).astype(np.int8)


def _at_bar(f: Feat, k: int, side: np.ndarray) -> np.ndarray:
    """Disparo en la vela `k` de la sesión, con el lado que diga `side`."""
    return ((f["bars_in"] == k) * np.nan_to_num(np.sign(side))).astype(np.int8)


@dataclass(frozen=True)
class Trigger:
    id: str
    family: str
    fn: Callable[[Feat], np.ndarray]
    params: dict = field(default_factory=dict)


def _triggers() -> tuple[Trigger, ...]:   # noqa: C901 - es un catálogo, no lógica
    out: list[Trigger] = []
    add = lambda i, fam, fn, **p: out.append(Trigger(i, fam, fn, p))  # noqa: E731

    # tendencia: cruces y giros
    for kind in ("ema", "sma", "wma"):
        for a, b in ((5, 20), (10, 50), (20, 100), (9, 21)):
            add(f"{kind}_{a}_{b}", "tendencia",
                lambda f, k=kind, a=a, b=b: cross(f[f"{k}{a}"], f[f"{k}{b}"]), fast=a, slow=b)
    for n in (20, 50):
        add(f"pendiente_ema{n}", "tendencia",
            lambda f, n=n: cross_zero(f[f"slope_ema{n}"]), n=n)
    for n in (10, 20):
        add(f"supertrend{n}", "tendencia", lambda f, n=n: cross_zero(f[f"st{n}_dir"]), n=n)
    add("sar", "tendencia", lambda f: cross_zero(f["sar_dir"]))
    add("dmi_cruce", "tendencia", lambda f: cross(f["pdi14"], f["mdi14"]), n=14)

    # ruptura de nivel
    for n in (10, 20, 40):
        add(f"donchian{n}", "ruptura",
            lambda f, n=n: band_break(f["c"], f[f"dc_hi{n}"], f[f"dc_lo{n}"]), n=n)
    for k in (3, 6, 12):
        add(f"rango_apertura{k}", "ruptura",
            lambda f, k=k: band_break(f["c"], f[f"or_hi{k}"], f[f"or_lo{k}"]), velas=k)
    add("sesion_previa", "ruptura",
        lambda f: band_break(f["c"], f["prev_hi"], f["prev_lo"]))
    for tag, k in (("20", 2.0), ("25", 2.5)):
        add(f"boll_fuera_{tag}", "ruptura",
            lambda f, t=tag: band_break(f["c"], f[f"bb{t}_up"], f[f"bb{t}_dn"]), n=20, k=k)
    add("keltner_fuera", "ruptura",
        lambda f: band_break(f["c"], f["kelt_up"], f["kelt_dn"]), n=20, k=2.0)

    # reversión a la media
    for n in (20, 50, 100):
        for z in (2.0, 2.5):
            add(f"z_ema{n}_{str(z).replace('.', '')}", "reversion",
                lambda f, n=n, z=z: band_fade(f[f"z_ema{n}"], -z, z), n=n, z=z)
    for n, (a, b) in ((7, (30, 70)), (14, (30, 70)), (21, (30, 70)), (14, (20, 80))):
        add(f"rsi{n}_{a}_{b}", "reversion",
            lambda f, n=n, a=a, b=b: band_fade(f[f"rsi{n}"], a, b), n=n, lo=a, hi=b)
    add("stochrsi_20_80", "reversion", lambda f: band_fade(f["srsi_k"], 20, 80))
    add("wr14_80_20", "reversion", lambda f: band_fade(f["wr14"], -80, -20), n=14)
    add("cci14_100", "reversion", lambda f: band_fade(f["cci14"], -100, 100), n=14)
    for k in (1.0, 2.0):
        add(f"vwap_dist{str(k).replace('.', '')}", "reversion",
            lambda f, k=k: band_fade(f["dist_vwap_atr"], -k, k), atr=k)

    # momento
    add("macd_hist", "momento", lambda f: cross_zero(f["macd_hist"]))
    add("mtm", "momento", lambda f: cross(f["mtm"], f["mamtm"]))
    add("trix", "momento", lambda f: cross(f["trix"], f["matrix"]))
    for n in (6, 12, 24):
        add(f"roc{n}", "momento", lambda f, n=n: cross_zero(f[f"roc{n}"]), n=n)
    for n in (3, 4):
        add(f"racha{n}", "momento",
            lambda f, n=n: _ev(f["streak"] == n, f["streak"] == -n), n=n)
    add("kdj", "momento", lambda f: cross(f["kdj_k"], f["kdj_d"]))

    # volumen y flujo de agresores
    for n in (20, 50):
        for mult in (1.5, 2.0):
            add(f"vol_pico{n}_{str(mult).replace('.', '')}", "flujo",
                lambda f, n=n, m=mult: _spike(f, f"vol_rel{n}", m), n=n, mult=mult)
    add("mfi14_20_80", "flujo", lambda f: band_fade(f["mfi14"], 20, 80), n=14)
    add("obv_pendiente", "flujo", lambda f: cross_zero(f["obv_slope"]), n=6)
    for name, th in (("delta1", 0.6), ("delta6", 0.55)):
        add(f"{name}_{str(th).replace('.', '')}", "flujo",
            lambda f, nm=name, th=th: _ev(
                (f[nm] > th) & (shift(f[nm], 1) <= th),
                (f[nm] < 1 - th) & (shift(f[nm], 1) >= 1 - th)), var=name, th=th)
    add("cvd_pendiente", "flujo", lambda f: cross_zero(f["cvd_slope"]), n=6)
    add("tamano_operacion", "flujo", lambda f: _spike(f, "tsize_rel", 2.0), n=20, mult=2.0)
    add("emv", "flujo", lambda f: cross(f["emv"], f["maemv"]), n=14)

    # volatilidad y régimen: compresión y expansión
    add("compresion_atr", "volatilidad",
        lambda f: (band_break(f["c"], f["dc_hi20"], f["dc_lo20"])
                   * (f["atr_ratio"] < 0.7)).astype(np.int8), corto=7, largo=50, ratio=0.7)
    add("squeeze_boll", "volatilidad",
        lambda f: (band_break(f["c"], f["bb20_up"], f["bb20_dn"])
                   * (f["bb_width_pct"] < 0.3)).astype(np.int8), n=20, pct=0.3)
    add("expansion_rango", "volatilidad",
        lambda f: _spike(f, "range_rel", 2.0), n=20, mult=2.0)

    # hora de la sesión (estacionalidad intradía pura)
    for k in (6, 12):
        add(f"hora_apertura{k}", "hora",
            lambda f, k=k: _at_bar(f, k, f["c"] - f["vwap_s"]), vela=k)
    add("ultima_hora", "hora", lambda f: _at_bar(f, 60, f["c"] - f["vwap_s"]), vela=60)
    add("mediodia", "hora", lambda f: _at_bar(f, 30, f["c"] - f["vwap_s"]), vela=30)
    return tuple(out)


TRIGGERS = _triggers()

#: Filtro opcional: deja pasar la señal o no. `None` = sin filtro.
FILTERS: dict[str, Callable[[Feat, np.ndarray], np.ndarray]] = {
    "ninguno": lambda f, s: np.ones(len(s), dtype=bool),
    "h1_favor": lambda f, s: f["h1_side"] == s,
    "adx20": lambda f, s: f["adx14"] >= 20,
    "vol_alta": lambda f, s: f["bb_width_pct"] >= 0.5,
    "vol_baja": lambda f, s: f["bb_width_pct"] < 0.5,
    "vwap_lado": lambda f, s: np.sign(f["c"] - f["vwap_s"]) == s,
    "volumen": lambda f, s: f["vol_rel20"] >= 1.0,
    "delta_favor": lambda f, s: np.sign(f["delta1"] - 0.5) == s,
    "apertura": lambda f, s: f["bars_in"] < 24,
}


@dataclass(frozen=True)
class Exit:
    """Salida de la receta. Todas llevan stop de protección en ATR y el cierre forzoso de sesión."""

    id: str
    kind: Literal["objetivo", "trailing", "tiempo", "giro", "nivel", "sesion"]
    atr_k: float
    tp_r: float | None = None
    bars: int | None = None


EXITS: tuple[Exit, ...] = (
    Exit("atr1_1", "objetivo", 1.0, tp_r=1.0),
    Exit("atr1_2", "objetivo", 1.0, tp_r=2.0),
    Exit("atr15_3", "objetivo", 1.5, tp_r=3.0),
    Exit("atr2_2", "objetivo", 2.0, tp_r=2.0),
    Exit("trailing_atr2", "trailing", 2.0),
    Exit("tiempo12", "tiempo", 1.5, bars=12),
    Exit("tiempo24", "tiempo", 1.5, bars=24),
    Exit("giro", "giro", 1.5),
    Exit("vwap_objetivo", "nivel", 1.5),
    Exit("cierre_sesion", "sesion", 2.0),
)


@dataclass(frozen=True)
class Recipe:
    """Una receta congelada. Su huella firma disparador, parámetros, dirección, filtro y salida."""

    trigger: str
    family: str
    direction: str
    filter: str
    exit: str

    @property
    def id(self) -> str:
        return f"{self.trigger}|{self.direction}|{self.filter}|{self.exit}"

    @property
    def fingerprint(self) -> str:
        blob = json.dumps([self.trigger, self.direction, self.filter, self.exit], sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]


def signal(trig: Trigger, direction: str, filt: str, f: Feat, can: np.ndarray) -> np.ndarray:
    """Señal final de un (disparador, dirección, filtro): ±1 solo donde se puede operar."""
    s = np.asarray(trig.fn(f), dtype=np.int8)
    if direction == "largo":
        s = np.where(s > 0, s, 0).astype(np.int8)
    elif direction == "corto":
        s = np.where(s < 0, s, 0).astype(np.int8)
    ok = FILTERS[filt](f, s.astype(float))
    return np.where((s != 0) & ok & can, s, 0).astype(np.int8)


def enumerate_recipes() -> tuple[Recipe, ...]:
    """Todas las recetas de la rejilla, en orden fijo (sin mirar datos)."""
    return tuple(Recipe(t.id, t.family, d, fl, x.id)
                 for t in TRIGGERS for d in DIRECTIONS for fl in FILTERS for x in EXITS)


def grid_fingerprint() -> str:
    """Huella de la rejilla: disparadores con sus parámetros, direcciones, filtros y salidas."""
    blob = json.dumps({
        "triggers": [[t.id, t.family, {k: v for k, v in sorted(t.params.items())}]
                     for t in TRIGGERS],
        "directions": list(DIRECTIONS), "filters": sorted(FILTERS),
        "exits": [[e.id, e.kind, e.atr_k, e.tp_r, e.bars] for e in EXITS],
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
