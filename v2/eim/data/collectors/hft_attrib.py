"""De quién es una hora incompleta: mantenimiento declarado y atribución (T147, T148 E3).

La ventana y la racha viven en `hft_window.py`; aquí está solo la pregunta de la culpa, que T148
tuvo que afinar.

**Por qué cambió (T148).** El 2026-11-09 nuestro proceso murió a las 17:55:42 y la hora
2026-11-09T17 quedó truncada. Sus dos únicas marcas eran `silencio` y no hubo ningún reinicio, así
que la regla de T147 la devolvía **«ajena»**: un proceso que muere se parece por dentro a un
exchange que se calla. Por eso el titular «desde el 6-nov no hay ninguna hora perdida por causa
nuestra» dejó de ser cierto sin que ninguna cifra lo dijera
(`PLAN/notas/T148_apagon_2026-11-09.md`).

**La señal que los separa es lo que NADIE marcó.** Cuando el exchange se calla, el recolector está
vivo y lo anota: el tiempo perdido queda explicado por sus tramos marcados. Cuando el proceso
muere, no queda nadie para anotar, y el tiempo perdido aparece en la cobertura sin ninguna marca
detrás. `unmarked_s` mide exactamente eso: los segundos de la hora sin datos que ningún tramo
marcado explica.

El umbral (`UNMARKED_S`) sale de medir las 241 horas auditadas a 2026-11-09, no de una suposición:
ninguna hora **completa** pasa de 28,8 s sin explicar (la peor es 2026-11-09T16, con un reinicio
declarado), mientras la hora truncada del apagón tiene **267 s**. 120 s deja holgura por los dos
lados.

Las otras dos señales que pide T148 E3:

- **Una hora sin ningún JSON de QC** (`rep` a None) es nuestra: si no hay informe es porque no
  había quien lo escribiera. Ya era así desde T147 y se conserva.
- **Una hora que cae en un hueco del registro de consumo** (`blind_hours`, de
  `eim.operation.usage_gaps`) es nuestra: el registro de consumo es otro de los cinco servicios, y
  si él tampoco estaba, lo que faltó fue el equipo, no el exchange.
"""

from __future__ import annotations

import json
import time
from collections.abc import Container
from pathlib import Path

from eim.data.collectors.hft_read import hour_label
from eim.data.collectors.hft_schema import AREA, HOUR_NS

OUR_CAUSES = ("cola_llena",)
THEIR_CAUSES = ("silencio", "desconexion", "secuencia", "sin_libro")
UNMARKED_S = 120.0       # tiempo perdido que nadie marcó, desde el que la hora se cortó sola


# --------------------------------------------------------------------------- mantenimiento (T147)

def maint_path(root: str | Path, symbol: str) -> Path:
    return Path(root) / AREA / "qc" / f"symbol={symbol}" / "maintenance.json"


def load_maint(root: str | Path, symbol: str) -> list[dict]:
    """Tramos de mantenimiento declarados (lista vacía si no hay archivo o está roto)."""
    try:
        d = json.loads(maint_path(root, symbol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    ws = d.get("windows") if isinstance(d, dict) else None
    return [w for w in ws if "from_h" in w and "to_h" in w] if isinstance(ws, list) else []


def declare_maint(root: str | Path, symbol: str, h0: int, h1: int, note: str,
                  now_s: float | None = None) -> dict:
    """Declara [h0, h1] (horas UTC, ambas incluidas) como mantenimiento conocido.

    Idempotente por tramo: declarar el mismo dos veces lo deja una sola vez. Solo escribe el
    archivo de mantenimiento; no toca ningún JSON de QC ni la captura.

    Es para cortes **previstos**. Declarar a posteriori las horas de un apagón imprevisto para
    salvar una ventana es falsearla, y por eso queda guardado el instante en que se declaró
    (`at`): las 6 horas del apagón del 2026-11-09 se quedaron perdidas y contadas."""
    if h1 < h0:
        raise ValueError("la hora final del mantenimiento es anterior a la inicial")
    w = {"from": hour_label(h0), "to": hour_label(h1), "from_h": h0, "to_h": h1,
         "hours": h1 - h0 + 1, "note": str(note)[:300],
         "at": int((now_s if now_s is not None else time.time()) * 1000)}
    ws = [x for x in load_maint(root, symbol) if (x["from_h"], x["to_h"]) != (h0, h1)]
    ws.append(w)
    ws.sort(key=lambda x: x["from_h"])
    p = maint_path(root, symbol)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"symbol": symbol, "windows": ws}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(p)
    return {"declared": w, "windows": len(ws)}


def is_maint(hour: int, maint: list[dict]) -> bool:
    return any(w["from_h"] <= hour <= w["to_h"] for w in maint)


# --------------------------------------------------------------------- tiempo perdido sin marcar

def _marked_s(rep: dict, hour: int) -> float:
    """Segundos de la hora cubiertos por algún tramo marcado, contando la UNIÓN.

    Los tramos son por flujo y se solapan (el mismo silencio deja marca en `depth` y en `mark`):
    sumarlos explicaría más tiempo del que falta y taparía un corte de verdad."""
    h0, h1 = hour * HOUR_NS, (hour + 1) * HOUR_NS
    spans = []
    for g in (rep.get("gaps_marked") or {}).get("list") or []:
        try:
            a, b = max(int(g["start_ns"]), h0), min(int(g["end_ns"]), h1)
        except (KeyError, TypeError, ValueError):
            continue
        if b > a:
            spans.append((a, b))
    total, end = 0, h0
    for a, b in sorted(spans):
        a = max(a, end)
        if b > a:
            total += b - a
            end = b
    return total / 1e9


def unmarked_s(rep: dict, hour: int | None = None) -> float:
    """Segundos de la hora sin datos que NINGÚN tramo marcado explica.

    La parte de la hora en que el proceso estuvo vivo se estima con la mejor cobertura de sus
    flujos: que un flujo se calle es cosa del exchange, pero un proceso muerto los calla todos a
    la vez. `liq` no cuenta (las liquidaciones son esporádicas y no miden presencia)."""
    streams = {k: v for k, v in (rep.get("streams") or {}).items()
               if k != "liq" and isinstance(v, dict)}
    if not streams:
        return 0.0
    alive = max((s.get("coverage") or 0.0) for s in streams.values())
    h = rep.get("hour_index") if hour is None else hour
    if h is None:
        return 0.0
    return max(0.0, (1.0 - alive) * 3600.0 - _marked_s(rep, int(h)))


# --------------------------------------------------------------------------- atribución (T148 E3)

def attribute(rep: dict | None, hour: int, maint: list[dict] | None = None,
              blind_hours: Container[int] | None = None,
              unmarked_min: float = UNMARKED_S) -> str:
    """De quién es una hora incompleta: «mantenimiento», «nuestra», «ajena» o «sin causa».

    `rep` a None = la hora no tiene QC (proceso caído), que es deuda nuestra salvo mantenimiento.
    `blind_hours`: horas que el registro de consumo no vio (T148 E2); si él tampoco estaba, lo
    que faltó fue el equipo."""
    if maint and is_maint(hour, maint):
        return "mantenimiento"
    if rep is None:
        return "nuestra"
    causes = (rep.get("gaps_marked") or {}).get("by_cause") or {}
    ours = (rep.get("restarts") or 0) or (rep.get("runs") or 1) > 1 \
        or (rep.get("overflow_dropped") or 0) or ((rep.get("clock") or {}).get("jumps") or 0) \
        or any(causes.get(c) for c in OUR_CAUSES) \
        or unmarked_s(rep, hour) >= unmarked_min \
        or (blind_hours is not None and hour in blind_hours)
    if ours:
        return "nuestra"
    return "ajena" if any(causes.get(c) for c in THEIR_CAUSES) else "sin causa"


def why(rep: dict | None, hour: int, maint: list[dict] | None = None,
        blind_hours: Container[int] | None = None) -> str:
    """La razón de la atribución, para poder discutirla sin releer los JSON."""
    if maint and is_maint(hour, maint):
        return "mantenimiento declarado"
    if rep is None:
        return "sin JSON de QC: no había quien lo escribiera"
    if rep.get("restarts") or (rep.get("runs") or 1) > 1:
        return f"{rep.get('restarts') or 0} reinicios, {rep.get('runs') or 1} tramos"
    if rep.get("overflow_dropped"):
        return f"{rep['overflow_dropped']} mensajes descartados por cola llena"
    if (rep.get("clock") or {}).get("jumps"):
        return f"{rep['clock']['jumps']} saltos de reloj"
    if (u := unmarked_s(rep, hour)) >= UNMARKED_S:
        return f"{u:.0f} s perdidos que ningún tramo marcado explica"
    if blind_hours is not None and hour in blind_hours:
        return "el registro de consumo tampoco vio esta hora"
    causes = (rep.get("gaps_marked") or {}).get("by_cause") or {}
    if marked := [c for c in THEIR_CAUSES if causes.get(c)]:
        return f"solo tramos del exchange marcados: {', '.join(marked)}"
    return "sin causa identificable"
