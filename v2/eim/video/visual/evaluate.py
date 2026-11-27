"""Medición de la lectura visual contra una muestra etiquetada a mano (T66 ◆), pura.

Etiqueta por fotograma (`tests/fixtures/video/labels/*.json`, formato en su README):
`{frame_id, image, video_id, t, is_chart, symbol, timeframe, observations: [{kind, value, unit}]}`.
Por tipo se mide la **precisión de lo aceptado** (de lo que el sistema daría por bueno, cuánto es
cierto) y la **cobertura** (de lo etiquetado, cuánto encuentra aceptado). Los umbrales se fijan
AQUÍ, antes de medir, y el informe los copia; solo pasan a T67 los tipos que los superan con
muestra suficiente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from eim.core.video import ObsKind, VisualObservation

KINDS: tuple[ObsKind, ...] = ("cifra", "titular", "nivel", "indicador", "dibujo")
# Fijados el 2026-11-20, antes de cualquier medición real (no se tocan tras ver resultados).
THRESHOLDS: dict[str, float] = {"cifra": 0.95, "nivel": 0.90, "indicador": 0.90,
                                "titular": 0.85, "dibujo": 0.80}
MIN_SUPPORT = 10          # observaciones aceptadas mínimas por tipo para poder pasar
MIN_FRAMES = 40           # fotogramas etiquetados mínimos para que el informe valga
NUM_REL = 0.002           # cifra/nivel: coincide a ≤ 0,2 %
RSI_ABS = 0.5             # indicador en puntos (RSI) …
IND_REL = 0.002           # … o relativo (medias, VWAP)


@dataclass(frozen=True)
class Label:
    kind: str
    value: float | str
    unit: str = ""


@dataclass(frozen=True)
class LabeledFrame:
    frame_id: str
    observations: tuple[Label, ...]
    is_chart: bool = False
    symbol: str | None = None
    timeframe: str | None = None


def parse_label(d: dict) -> LabeledFrame:
    obs = tuple(Label(o["kind"], o["value"], o.get("unit", "")) for o in d.get("observations", []))
    return LabeledFrame(d["frame_id"], obs, bool(d.get("is_chart", False)), d.get("symbol"),
                        d.get("timeframe"))


def _norm(s: str) -> str:
    return " ".join(str(s).lower().split())


def matches(o: VisualObservation, lab: Label) -> bool:
    if o.kind != lab.kind:
        return False
    if o.kind in ("titular", "dibujo"):
        ratio = SequenceMatcher(None, _norm(o.value), _norm(lab.value)).ratio()
        return ratio >= (0.8 if o.kind == "titular" else 0.6)
    try:
        lv = float(lab.value)
    except (TypeError, ValueError):
        return False
    v = float(o.value)
    if o.kind == "indicador":
        if o.unit.split(":")[0] != lab.unit.split(":")[0]:
            return False
        if o.unit.startswith("rsi"):
            return abs(v - lv) <= RSI_ABS
        return abs(v - lv) <= IND_REL * max(abs(lv), 1e-9)
    return abs(v - lv) <= NUM_REL * max(abs(lv), 1e-9)


@dataclass
class KindStats:
    labels: int = 0
    accepted: int = 0
    accepted_ok: int = 0
    found: int = 0                       # etiquetas halladas entre lo aceptado
    rejected: int = 0                    # lecturas que la validación no aceptó
    false_examples: list[str] = field(default_factory=list)
    missed_examples: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float | None:
        return self.accepted_ok / self.accepted if self.accepted else None

    @property
    def recall(self) -> float | None:
        return self.found / self.labels if self.labels else None


@dataclass
class EvalResult:
    frames: int
    by_kind: dict[str, KindStats]
    symbol_ok: int = 0
    symbol_n: int = 0
    tf_ok: int = 0
    tf_n: int = 0
    chart_ok: int = 0

    def passes(self, kind: str) -> bool:
        s = self.by_kind[kind]
        return (self.frames >= MIN_FRAMES and s.accepted >= MIN_SUPPORT
                and s.precision is not None and s.precision >= THRESHOLDS[kind])

    @property
    def passing(self) -> list[str]:
        return [k for k in KINDS if self.passes(k)]


def evaluate(labels: list[LabeledFrame], results: dict[str, list[VisualObservation]],
             charts: dict[str, bool] | None = None,
             context: dict[str, tuple[str | None, str | None]] | None = None) -> EvalResult:
    by = {k: KindStats() for k in KINDS}
    out = EvalResult(len(labels), by)
    for lf in labels:
        obs = results.get(lf.frame_id, [])
        acc = [o for o in obs if o.accepted]
        for o in obs:
            if o.kind in by and not o.accepted:
                by[o.kind].rejected += 1
        for o in acc:
            s = by[o.kind]
            s.accepted += 1
            if any(matches(o, lab) for lab in lf.observations):
                s.accepted_ok += 1
            elif len(s.false_examples) < 5:
                s.false_examples.append(f"{lf.frame_id}: {o.value} {o.unit} ({o.source})")
        for lab in lf.observations:
            if lab.kind not in by:
                continue
            s = by[lab.kind]
            s.labels += 1
            if any(matches(o, lab) for o in acc):
                s.found += 1
            elif len(s.missed_examples) < 5:
                s.missed_examples.append(f"{lf.frame_id}: {lab.value} {lab.unit}")
        if charts is not None and charts.get(lf.frame_id, False) == lf.is_chart:
            out.chart_ok += 1
        if context is not None:
            sym, tf = context.get(lf.frame_id, (None, None))
            if lf.symbol:
                out.symbol_n += 1
                out.symbol_ok += sym == lf.symbol
            if lf.timeframe:
                out.tf_n += 1
                out.tf_ok += tf == lf.timeframe
    return out
