"""El registro de consumo detecta su propio silencio (T148, entregable 2).

El 2026-11-09 los cinco servicios estuvieron parados de 17:55:42 a 23:21 UTC y
`usage incidents --days 1` dio **cero incidentes** después de las 17:00: el registro de consumo
mide desde dentro, así que murió con los demás y no quedó nadie para anotar nada
(`PLAN/notas/T148_apagon_2026-11-09.md`). La herramienta que T141 hizo para cruzar cada bloqueo
con la carga del equipo era ciega justo en el caso peor.

La vuelta es leer la **ausencia**: un hueco entre dos muestras consecutivas de `data/usage/` es un
incidente por sí mismo, con su duración y lo que se sabe de los bordes (la última muestra antes y
la primera después). No hace falta que nadie lo anote mientras pasa; se deduce después, que es
precisamente lo que un proceso muerto no puede hacer por sí mismo.

Dos límites honestos, para no inventar:

- **Antes de la primera muestra no se declara nada.** Que el 2026-11-02 no haya registro no
  significa que el registro se cayera: significa que no estaba instalado. Solo los huecos
  *interiores* y el que llega hasta ahora (el registro calló y no ha vuelto) son incidentes.
- **Las horas ciegas se dicen, no se rellenan.** `blind_hours` da las horas que un hueco tapa, para
  que la atribución de una hora de captura incompleta sepa que ahí no hay testigo (T148, E3).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime

# 8 ciclos de 30 s seguidos sin muestra. Medido sobre todo el registro (2026-11-02 → 11-10): solo
# 3 huecos llegan a 240 s y los tres son apagones; el segundo apagón del conjunto
# (2026-11-10 00:33:49, levantado por el parche provisional) dejó 284 s, que un umbral de 300 s
# no veía. Por debajo de 240 s solo quedan atascos del propio registro bajo carga (182 s el 5-nov).
GAP_S = 240.0
HOUR_MS = 3_600_000
BLIND_S = 60.0       # solape mínimo para dar una hora por ciega
KIND = "apagon_registro"
EDGE_KEYS = ("ts", "t", "dt_s")


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _edge(rec: Mapping | None) -> dict | None:
    """Lo poco que se sabe del borde de un hueco: cuándo fue y cómo estaba el equipo."""
    if rec is None:
        return None
    out = {k: rec[k] for k in EDGE_KEYS if k in rec}
    if (m := rec.get("machine")) is not None:
        out["machine"] = {k: m[k] for k in ("cpu", "ram_free_mb", "commit_mb") if k in m}
    for k in ("api_beat_age_s", "hft"):
        if rec.get(k) is not None:
            out[k] = rec[k]
    if (roles := rec.get("roles")) is not None:
        out["services"] = sorted(roles)
    return out


def gaps(samples: Sequence[Mapping], until_ms: int | None = None,
         gap_s: float = GAP_S) -> list[dict]:
    """Huecos del registro de consumo: {t0, t1, before, after}, en milisegundos.

    `samples` tiene que venir ordenado por `t`. Con `until_ms`, un registro que calló y no ha
    vuelto da un hueco abierto hasta ahí (`after` a None): es el apagón que está pasando.
    """
    out: list[dict] = []
    ms = gap_s * 1000
    for a, b in zip(samples, samples[1:], strict=False):
        if b["t"] - a["t"] >= ms:
            out.append({"t0": a["t"], "t1": b["t"], "before": _edge(a), "after": _edge(b)})
    if until_ms is not None and samples and until_ms - samples[-1]["t"] >= ms:
        out.append({"t0": samples[-1]["t"], "t1": until_ms,
                    "before": _edge(samples[-1]), "after": None})
    return out


def as_incidents(found: Iterable[Mapping]) -> list[dict]:
    """Los huecos, en el mismo formato que los demás incidentes de `usage incidents`.

    `samples: 0` no es un descuido: en un hueco no hay ninguna muestra que cruzar, y eso es
    justamente lo que el incidente dice. Lo que se sabe va en `edges`.
    """
    out = []
    for g in found:
        dur = round((g["t1"] - g["t0"]) / 1000)
        out.append({
            "kind": KIND, "from": _iso(g["t0"]), "to": _iso(g["t1"]), "dur_s": dur,
            "detail": (f"el registro de consumo no tomó ninguna muestra durante "
                       f"{dur / 3600:.2f} h" + ("" if g.get("after") else "; sigue callado")),
            "samples": 0,
            "edges": {"last_before": g.get("before"), "first_after": g.get("after")},
        })
    return out


def blind_hours(found: Iterable[Mapping], blind_s: float = BLIND_S) -> set[int]:
    """Horas UTC (índice de hora desde la época) que un hueco tapa al menos `blind_s`.

    Mismo índice que el QC de la captura (`hour_index`), para poder cruzarlos.
    """
    out: set[int] = set()
    for g in found:
        t0, t1 = int(g["t0"]), int(g["t1"])
        for h in range(t0 // HOUR_MS, t1 // HOUR_MS + 1):
            if min(t1, (h + 1) * HOUR_MS) - max(t0, h * HOUR_MS) >= blind_s * 1000:
                out.add(h)
    return out


def coverage(samples: Sequence[Mapping], day_t0_ms: int, day_t1_ms: int,
             gap_s: float = GAP_S) -> dict:
    """Cobertura real de un tramo: cuánto estuvo midiendo el registro y cuánto calló.

    `measured_s` es el tramo pedido menos los huecos y menos lo que queda fuera de las muestras,
    así que un día con 5 horas en blanco no se lee como si estuviera medido.
    """
    span = max(0, day_t1_ms - day_t0_ms)
    if not samples:
        return {"measured_s": 0, "blind_s": round(span / 1000), "coverage": 0.0, "gaps": []}
    found = gaps(samples, None, gap_s)
    inside = [{"from": _iso(g["t0"]), "to": _iso(g["t1"]),
               "dur_s": round((g["t1"] - g["t0"]) / 1000)} for g in found]
    blind = sum(g["t1"] - g["t0"] for g in found)
    blind += max(0, samples[0]["t"] - day_t0_ms) + max(0, day_t1_ms - samples[-1]["t"])
    blind = min(blind, span)
    return {"measured_s": round((span - blind) / 1000), "blind_s": round(blind / 1000),
            "coverage": round((span - blind) / span, 3) if span else 0.0, "gaps": inside}
