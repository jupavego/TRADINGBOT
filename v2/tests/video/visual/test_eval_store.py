"""T66: medición contra etiquetas, informe, tabla solo-añadir y fotogramas de un video real."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from eim.core.video import VisualObservation
from eim.video.visual import evaluate as E
from eim.video.visual.params import DEFAULT, VisualParams
from eim.video.visual.report import render
from tests.video.visual.synth import chart_image, slide_image


def _obs(fid: str, kind: str, value, validation: str = "plausible", unit: str = "precio",
         engine: str = "rapidocr") -> VisualObservation:
    return VisualObservation(video_id="v", t=1.0, frame_id=fid, kind=kind, value=value,
                             unit=unit, quote="x", source="ocr", validation=validation,
                             engine=engine, model="m", weights_sha="s",
                             params_version="visual_v1")


def test_evaluate_precision_recall_and_gate() -> None:
    labels, results = [], {}
    for i in range(40):
        fid = f"f{i}"
        labels.append(E.parse_label({"frame_id": fid, "observations": [
            {"kind": "nivel", "value": 64250, "unit": "precio"},
            {"kind": "titular", "value": "Bitcoin rompe máximos"}]}))
        results[fid] = [_obs(fid, "nivel", 64251.0),                       # dentro del 0,2 %
                        _obs(fid, "titular", "BITCOIN rompe  máximos", unit=""),
                        _obs(fid, "nivel", 99000.0, validation="inconsistente")]
        if i % 4 == 0:
            results[fid].append(_obs(fid, "cifra", 5.0, unit="%"))          # no etiquetada
    res = E.evaluate(labels, results)
    niv = res.by_kind["nivel"]
    assert niv.precision == 1.0 and niv.recall == 1.0 and niv.rejected == 40
    assert res.by_kind["cifra"].precision == 0.0 and res.passes("nivel")
    assert not res.passes("cifra") and not res.passes("indicador")       # sin muestra
    assert res.passing == ["titular", "nivel"]
    short = E.evaluate(labels[:10], results)
    assert short.passing == []                                           # < 40 fotogramas
    md = render(short, params=DEFAULT, engines="rapidocr", when="hoy", machine="test")
    assert "Muestra insuficiente" in md and "Umbral" in md and "◆" in md


def test_label_readme_documents_format() -> None:
    readme = Path(__file__).resolve().parents[2] / "fixtures" / "video" / "labels" / "README.md"
    text = readme.read_text(encoding="utf-8")
    assert "frame_id" in text and "observations" in text and "40" in text


def test_store_is_append_only_and_ignores_repeats(tmp_path: Path) -> None:
    pytest.importorskip("duckdb")
    from eim.data.video.observations import ObservationStore

    st = ObservationStore(tmp_path / "visual.duckdb")
    a = [_obs("f1", "nivel", 64250.0, "confirmada"),
         _obs("f1", "titular", "Hola mundo", "no_verificable", unit="")]
    assert st.append(a, now=1) == 2
    assert st.append(a, now=2) == 0                                       # repetidas
    assert st.append([_obs("f1", "nivel", 64250.0, engine="otro")], now=3) == 1
    rows = st.for_video("v")
    assert len(rows) == 3 and {r["recorded_at"] for r in rows} == {1, 3}
    assert len(st.for_video("v", accepted_only=True)) == 2
    assert {(c["kind"], c["validation"]) for c in st.counts()} >= {("nivel", "confirmada")}
    st.close()


def test_extract_frames_from_local_video(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    from eim.data.video.frames import extract

    src = tmp_path / "clip.avi"
    vw = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"MJPG"), 2.0, (640, 360))
    if not vw.isOpened():
        pytest.skip("este OpenCV no escribe video")
    scenes = [chart_image(seed=1), slide_image(), chart_image(seed=5, level_y=None)]
    for img in scenes:
        small = cv2.resize(img, (640, 360), interpolation=cv2.INTER_AREA)
        for _ in range(20):                                               # 10 s por escena
            vw.write(np.ascontiguousarray(small))
    vw.release()
    p = VisualParams(min_every_s=60.0, thumb_width=320)
    saved, sel = extract(src, "vid1", root=tmp_path / "frames", p=p, delete_source=True)
    assert 2 <= len(saved) <= 3 and sel.n_samples >= 25
    assert all(Path(f.path).exists() and f.width == 320 for f in saved)
    man = json.loads((tmp_path / "frames" / "vid1" / "manifest.json").read_text())
    assert man["cap"] == sel.cap and len(man["frames"]) == len(saved)
    assert not src.exists()                                               # el video no se guarda
    assert not list((tmp_path / "frames").rglob("*.avi"))
