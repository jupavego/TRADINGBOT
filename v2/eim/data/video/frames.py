"""Fotogramas candidatos de un video local (T66, I/O): escenas, muestreo mínimo, duplicados, tope.

Dos pasadas sobre un archivo que el usuario aporta (postura de YouTube de T62: nada se descarga):
1. recorre el video cada `sample_every_s` con una copia reducida y calcula dHash y rejilla;
2. `eim.video.visual.sampling.select` elige (cortes de escena + uno cada `min_every_s`, sin casi
   idénticos, tope de T62) y solo esos se guardan como miniatura JPEG en
   `data/video/frames/<video_id>/` (fuera de git) con un `manifest.json`.
El video completo **no se conserva**: no se copia y, con `delete_source=True`, se borra al
terminar (para audio/video temporal que se aporte solo para leerlo).

OpenCV (`opencv-python-headless`, extra `[video]`) se importa solo aquí y solo al usarse.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from eim.video.visual.imageops import dhash, grid
from eim.video.visual.params import DEFAULT, VisualParams
from eim.video.visual.sampling import Sample, Selection, select


def frames_root(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("EIM_DATA_DIR", "data")) / "video" / "frames"


def frame_id(video_id: str, t: float) -> str:
    return f"{video_id}@{int(round(t * 1000)):09d}"


@dataclass(frozen=True)
class SavedFrame:
    frame_id: str
    t: float
    path: str
    reason: str
    width: int
    height: int


def _cv2():
    try:
        import cv2
    except ImportError as e:     # pragma: no cover - depende del entorno
        raise RuntimeError("falta OpenCV: instala el extra [video] (opencv-python-headless)") from e
    return cv2


def _thumb(img: np.ndarray, width: int = 320) -> np.ndarray:
    cv2 = _cv2()
    h, w = img.shape[:2]
    if w <= width:
        return img
    return cv2.resize(img, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)


def scan(path: Path, p: VisualParams = DEFAULT) -> tuple[list[Sample], float]:
    """Pasada 1: muestras `(t, hash, rejilla)` y duración en segundos."""
    cv2 = _cv2()
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"no se pudo abrir el video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    duration = n / fps if fps > 0 else 0.0
    step = max(1, int(round(fps * p.sample_every_s))) if fps > 0 else 1
    samples: list[Sample] = []
    i = 0
    try:
        while True:
            ok = cap.grab()
            if not ok:
                break
            if i % step == 0:
                ok, img = cap.retrieve()
                if ok and img is not None:
                    small = _thumb(img)
                    t = i / fps if fps > 0 else float(len(samples)) * p.sample_every_s
                    samples.append(Sample(t, dhash(small, p.hash_size), grid(small)))
            i += 1
    finally:
        cap.release()
    if duration <= 0 and samples:
        duration = samples[-1].t + p.sample_every_s
    return samples, duration


def extract(path: str | Path, video_id: str, *, root: Path | None = None,
            p: VisualParams = DEFAULT, delete_source: bool = False) -> tuple[list[SavedFrame],
                                                                              Selection]:
    """Elige y guarda las miniaturas de un video. Devuelve lo guardado y las cifras de la
    selección (muestras, candidatos, duplicados, sobre el tope)."""
    cv2 = _cv2()
    src = Path(path)
    samples, duration = scan(src, p)
    sel = select(samples, duration, p)
    out_dir = (root or frames_root()) / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(src))
    saved: list[SavedFrame] = []
    try:
        for c in sel.chosen:
            cap.set(cv2.CAP_PROP_POS_MSEC, c.t * 1000)
            ok, img = cap.read()
            if not ok or img is None:
                continue
            th = _thumb(img, p.thumb_width)
            fid = frame_id(video_id, c.t)
            dest = out_dir / f"{fid.split('@')[1]}.jpg"
            cv2.imwrite(str(dest), th, [cv2.IMWRITE_JPEG_QUALITY, 90])
            saved.append(SavedFrame(fid, round(c.t, 3), str(dest), c.reason, th.shape[1],
                                    th.shape[0]))
    finally:
        cap.release()
    manifest = {"video_id": video_id, "duration_s": round(duration, 3),
                "params": p.version, "params_sha": p.fingerprint(),
                "samples": sel.n_samples, "candidates": sel.n_candidates,
                "duplicates": sel.n_duplicates, "over_cap": sel.n_over_cap, "cap": sel.cap,
                "frames": [asdict(f) for f in saved]}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    if delete_source:
        src.unlink(missing_ok=True)
    return saved, sel


def load_image(path: str | Path) -> np.ndarray:
    """Miniatura en memoria (BGR, como la guarda OpenCV); Pillow si no hay OpenCV."""
    try:
        cv2 = _cv2()
        img = cv2.imread(str(path))
        if img is not None:
            return img
    except RuntimeError:
        pass
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB"))[:, :, ::-1]
