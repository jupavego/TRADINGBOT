"""Informe de la medición visual (T66 ◆) en markdown: `v2/reports/video_visual_eval.md`.

Lo escribe la CLI (`python -m eim.video.visual eval`). Copia los umbrales fijados antes de medir
(`evaluate.THRESHOLDS`) y dice qué tipos pasan a T67 y cuáles se descartan por poco fiables.
"""

from __future__ import annotations

from eim.video.visual import evaluate as E
from eim.video.visual.params import VisualParams


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.0%}"


def render(res: E.EvalResult, *, params: VisualParams, engines: str, when: str,
           machine: str) -> str:
    lines = [
        "# T66 — Medición de la lectura visual de video",
        "",
        f"Fecha: {when} · Equipo: `{machine}` · Parámetros: `{params.version}` "
        f"(huella `{params.fingerprint()}`) · Motores: {engines}",
        "",
        "## Umbrales (fijados antes de medir, en `eim/video/visual/evaluate.py`)",
        "",
        "Un tipo pasa a T67 si, con al menos "
        f"{E.MIN_FRAMES} fotogramas etiquetados y {E.MIN_SUPPORT} observaciones aceptadas, la "
        "precisión de lo aceptado llega a su umbral:",
        "",
        "| Tipo | Umbral de precisión |",
        "|---|---|",
        *[f"| {k} | {E.THRESHOLDS[k]:.0%} |" for k in E.KINDS],
        "",
        "## Resultado",
        "",
    ]
    if res.frames < E.MIN_FRAMES:
        lines += [f"**Muestra insuficiente:** {res.frames} fotogramas etiquetados de "
                  f"{E.MIN_FRAMES}. Ningún tipo pasa a T67 hasta completarla.", ""]
    lines += ["| Tipo | Etiquetas | Aceptadas | Precisión | Cobertura | Rechazadas por la "
              "validación | ¿Pasa a T67? |", "|---|---|---|---|---|---|---|"]
    for k in E.KINDS:
        s = res.by_kind[k]
        lines.append(f"| {k} | {s.labels} | {s.accepted} | {_pct(s.precision)} | "
                     f"{_pct(s.recall)} | {s.rejected} | {'sí' if res.passes(k) else 'no'} |")
    lines.append("")
    if res.symbol_n or res.tf_n:
        lines += [f"Contexto: activo {res.symbol_ok}/{res.symbol_n} · marco "
                  f"{res.tf_ok}/{res.tf_n} · gráfico detectado bien en "
                  f"{res.chart_ok}/{res.frames} fotogramas.", ""]
    lines += ["## Errores típicos", ""]
    for k in E.KINDS:
        s = res.by_kind[k]
        if s.false_examples or s.missed_examples:
            lines.append(f"- **{k}** — aceptadas falsas: {'; '.join(s.false_examples) or '—'} · "
                         f"no halladas: {'; '.join(s.missed_examples) or '—'}")
    lines += ["", "## Qué pasa y qué se descarta", ""]
    passing = res.passing
    lines.append(f"- Pasan a T67: {', '.join(passing) if passing else 'ninguno'}.")
    lines.append(f"- Se descartan por poco fiables (o sin muestra suficiente): "
                 f"{', '.join(k for k in E.KINDS if k not in passing) or 'ninguno'}.")
    lines += ["", "**◆ El usuario decide si la lectura visual es suficientemente fiel.**", ""]
    return "\n".join(lines)
