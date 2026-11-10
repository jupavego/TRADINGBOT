"""Aviso temprano de que la carga ajena está ahogando a la API (T141, entregable 3).

Lo vigila el registro de consumo, no la API: cuando hace falta avisar, ella es la que no responde.
Los umbrales salen de 4,6 días de `data/usage` (2 al 6-nov; `PLAN/notas/T141_carga_ajena.md`).
Repasados con este mismo código, los 3 reinicios «latido detenido» se habrían avisado 11, 45 y
16 min antes de llegar a los 900 s, igual que 8 de los 10 ciclos de más de 120 s (los otros dos
duraron 131 y 146 s). Son 11 avisos en esos días (2,4 al día). Los 5 tramos que no acabaron en un
ciclo lento también fueron presión real, con la API por debajo de 140 MB y la captura de 88 MB.

Cada condición cubre un caso que las otras no ven:
- memoria comprometida ≥ 36 GB: no saltó nunca lejos de un bloqueo, y la memoria es lo que daña a
  la captura, que con la CPU llena sigue sana;
- RAM de la API ≤ 200 MB, cuando tiene unos 2,4 GB reservados: Windows ya se la ha quitado;
- CPU del equipo ≥ 95 % con la API por debajo del 0,3 %: se queda sin turno aunque conserve la
  RAM, el caso del 6-nov 01:41, en el que las otras dos no saltan;
- latido de la API parado ≥ 300 s: última red, por si aparece un patrón que aquí no se vio. No
  pudo repasarse sobre el pasado, porque el latido no se guardaba.

Entra con 3 muestras seguidas y sale con 10 limpias. Cada tramo avisa: silenciar los cercanos
dejaba sin aviso el de las 04:03 del 5-nov, justo antes de un reinicio y tras un «resuelta».
El registro de operación y el observatorio viajan en las copias, así que solo reciben las causas;
la orden del programa culpable va solo a la notificación y a `data/usage` (T141, entregable 1).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from eim.observability import hooks_service
from eim.operation import usage_jobs
from eim.operation.alerts import INFO, SERVICE, WARN, Alert
from eim.operation.notify import JsonLog, WindowsToast

COMMIT_MB = 36_000
API_RAM_MB = 200
FULL_CPU, API_STARVED_CPU = 95.0, 0.3
BEAT_AGE_S, BEAT_STALE_S = 300.0, 3600.0   # con más de 1 h, el motor está parado, no ahogado
CONFIRM, CLEAR = 3, 10
KEY = "carga_ajena"
TITLE = "La API se está quedando sin equipo"
COMPONENT = "operation.usage"

Sink = Callable[[Alert], None]


def causes(rec: Mapping) -> list[str]:
    """Motivos de aviso que se cumplen en una muestra del registro de consumo."""
    m, api, out = rec["machine"], rec.get("roles", {}).get("api"), []
    if (commit := m.get("commit_mb") or 0) >= COMMIT_MB:
        out.append(f"memoria comprometida {commit / 1024:.0f} GB")
    if api is None:                            # arrancando o parada: no hay API que vigilar
        return out
    if api["ram_mb"] <= API_RAM_MB:
        out.append(f"la API solo conserva {api['ram_mb']:.0f} MB de RAM")
    if m["cpu"] >= FULL_CPU and api["cpu"] <= API_STARVED_CPU:
        out.append(f"CPU del equipo al {m['cpu']:.0f} % y la API al {api['cpu']:.2f} %")
    age = rec.get("api_beat_age_s")
    if age is not None and BEAT_AGE_S <= age <= BEAT_STALE_S:
        out.append(f"latido de la API parado {age:.0f} s")
    return out


def _day(t_ms: int) -> str:
    return datetime.fromtimestamp(t_ms / 1000, UTC).strftime("%Y-%m-%d")


def culprit(rec: Mapping, runs: list[dict] | None = None) -> str:
    """Quién carga más, por memoria si el problema es la memoria y si no por CPU. Si ese programa
    tiene un árbol identificado, se da su orden y su carpeta; si el árbol es el ejecutor de la
    cola, el trabajo que aloja (T149, `runs` de `usage_jobs.load_runs`)."""
    api = rec.get("roles", {}).get("api")
    memory = ((rec["machine"].get("commit_mb") or 0) >= COMMIT_MB
              or (api is not None and api["ram_mb"] <= API_RAM_MB))
    key = "commit_mb" if memory else "cpu"
    foreign = [usage_jobs.relabel(t, runs or [], rec["t"]) for t in rec.get("foreign") or []]
    rows = [*rec.get("others", ()), *foreign]
    if not rows:
        return "sin identificar"
    top = max(rows, key=lambda o: o.get(key, 0))
    same = [t for t in foreign if t["name"].lower() == top["name"].lower()]
    t = max(same, key=lambda o: o.get(key, 0)) if same else top
    where = f" en {t['cwd']}" if t.get("cwd") else ""
    size = t.get("commit_mb", t.get("ram_mb", 0))
    what = t.get("cmd") or t["name"]
    if t.get("job"):
        what = f"trabajo de la cola «{t['job']}» ({what})"
    return (f"{what}{where} ({t['n']} procesos, {t['cpu']:.0f} % de CPU, "
            f"{size:.0f} MB)")


class EarlyWarning:
    """Avisa al entrar en la condición y otra vez al salir."""

    def __init__(self, sinks: Iterable[Sink] = (), toast: Sink | None = None,
                 data_dir: Path | None = None) -> None:
        self.sinks, self.toast, self.data_dir = list(sinks), toast, data_dir
        self.errors: list[str] = []
        self.active = False
        self._hits, self._clear = 0, 0

    def _send(self, sink: Sink, a: Alert) -> None:
        try:
            sink(a)
        except Exception as e:  # noqa: BLE001 - un canal roto no para el registro
            self.errors = [*self.errors[-9:], f"{type(e).__name__}: {e}"]

    def _emit(self, a: Alert, rec: Mapping) -> None:
        for sink in self.sinks:
            self._send(sink, a)
        if self.toast is not None:
            runs = (usage_jobs.load_runs(self.data_dir, [_day(rec["t"])])
                    if self.data_dir is not None and not a.resolved else None)
            full = f"{a.detail}. Más carga: {culprit(rec, runs)}" if not a.resolved else a.detail
            self._send(self.toast, dataclasses.replace(a, detail=full))

    def update(self, rec: Mapping) -> Alert | None:
        """Procesa una muestra; devuelve el aviso emitido, si lo hubo."""
        why = causes(rec)
        self._hits = self._hits + 1 if why else 0
        self._clear = 0 if why else self._clear + 1
        now = rec["t"]
        if not self.active and self._hits >= CONFIRM:
            self.active = True
            a = Alert(now, SERVICE, WARN, TITLE, "; ".join(why), KEY)
            self._emit(a, rec)
            return a
        if self.active and self._clear >= CLEAR:
            self.active = False
            a = Alert(now, SERVICE, INFO, f"Resuelta: {TITLE}",
                      "el equipo vuelve a dejar sitio a la API", KEY, resolved=True)
            self._emit(a, rec)
            return a
        return None


def observatory(a: Alert) -> None:
    hooks_service.service_event(COMPONENT, a.title, status="ok" if a.resolved else "degraded",
                                detail={"causes": a.detail, "kind": a.kind})


def for_service(data_dir: Path) -> EarlyWarning:
    """El aviso del servicio: registro de operación, observatorio y notificación de Windows."""
    log = JsonLog(Path(data_dir) / "operation" / "logs")
    return EarlyWarning([log.alert_sink, observatory], WindowsToast(), data_dir)
