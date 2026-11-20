"""CLI de la lectura visual de video (T66). Desde `v2/`:

    python -m eim.video.visual frames ARCHIVO --video-id ID [--delete-source]
        elige y guarda miniaturas (escenas + muestreo mínimo, sin duplicados, tope de T62)
    python -m eim.video.visual read --video-id ID [--published AAAA-MM-DDTHH:MM] [--no-vlm]
        lee los fotogramas guardados (OCR, visión clásica, modelo visual si está encendido),
        valida contra las velas reales y añade a `video_observations`
    python -m eim.video.visual label-template --video-id ID
        crea etiquetas vacías en tests/fixtures/video/labels/ para rellenar a mano
    python -m eim.video.visual eval [--labels DIR] [--out reports/video_visual_eval.md]
        mide contra la muestra etiquetada y escribe el informe (◆ decide el usuario)
    python -m eim.video.visual stats

Solo con material que la postura de YouTube permite (propio, aportado o con permiso escrito):
aquí no se descarga nada. Motores por `EIM_LOCALAI_*` (todo apagado por defecto).
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

from eim.video.visual import evaluate as E
from eim.video.visual.params import DEFAULT
from eim.video.visual.reader import Frame, FrameReader
from eim.video.visual.report import render

LABELS = Path("tests/fixtures/video/labels")


def _ms(text: str | None) -> int | None:
    if not text:
        return None
    dt = datetime.fromisoformat(text)
    return int((dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp() * 1000)


def _candles():
    import os

    from eim.data.store import Store

    store = Store(os.environ.get("EIM_DATA_DIR", "data"))
    return lambda sym, tf, start, end: store.read_candles(sym, tf, start=start, end=end)


def _reader(no_vlm: bool):
    from eim.localai import LocalAI

    ai = LocalAI.from_env()
    return ai, FrameReader(ai.ocr, None if no_vlm else ai.vision, _candles(), DEFAULT)


def cmd_frames(a: argparse.Namespace) -> int:
    from eim.data.video.frames import extract

    saved, sel = extract(a.file, a.video_id, delete_source=a.delete_source)
    print(f"{len(saved)} fotogramas guardados de {sel.n_samples} muestras · {sel.n_candidates} "
          f"candidatos · {sel.n_duplicates} casi idénticos · {sel.n_over_cap} sobre el tope "
          f"({sel.cap})")
    return 0


def _manifest(video_id: str) -> dict:
    from eim.data.video.frames import frames_root

    path = frames_root() / video_id / "manifest.json"
    if not path.exists():
        raise SystemExit(f"no hay fotogramas de {video_id}: corre antes `frames`")
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_read(a: argparse.Namespace) -> int:
    from eim.data.video.frames import load_image
    from eim.data.video.observations import ObservationStore, observations_path

    man = _manifest(a.video_id)
    ai, reader = _reader(a.no_vlm)
    vlm_left = DEFAULT.frame_cap(man["duration_s"], vlm=True)
    store = ObservationStore(observations_path())
    total = added = 0
    try:
        for f in man["frames"]:
            fr = Frame(a.video_id, f["frame_id"], f["t"], Path(f["path"]), load_image(f["path"]))
            res = reader.read(fr, ref_ms=_ms(a.published), allow_vlm=vlm_left > 0)
            vlm_left -= int(res.vlm_used)
            total += len(res.observations)
            added += store.append(res.observations)
            for w in res.warnings:
                print(f"  {f['frame_id']}: {w}")
    finally:
        store.close()
        ai.close()
    print(f"{total} observaciones leídas, {added} nuevas en video_observations")
    return 0


def cmd_label_template(a: argparse.Namespace) -> int:
    man = _manifest(a.video_id)
    out = Path(a.labels)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in man["frames"]:
        stem = f["frame_id"].replace("@", "_")
        dest = out / f"{stem}.json"
        if dest.exists():
            continue
        shutil.copyfile(f["path"], out / f"{stem}.jpg")
        dest.write_text(json.dumps({
            "frame_id": f["frame_id"], "image": f"{stem}.jpg", "video_id": a.video_id,
            "t": f["t"], "published": None, "is_chart": False, "symbol": None,
            "timeframe": None, "observations": []}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        n += 1
    print(f"{n} etiquetas vacías en {out} (rellénalas a mano; formato en su README)")
    return 0


def cmd_eval(a: argparse.Namespace) -> int:
    from eim.data.video.frames import load_image

    files = sorted(Path(a.labels).glob("*.json"))
    labels, raw = [], []
    for p in files:
        d = json.loads(p.read_text(encoding="utf-8"))
        labels.append(E.parse_label(d))
        raw.append((p, d))
    ai, reader = _reader(a.no_vlm)
    results, charts, ctx = {}, {}, {}
    try:
        for p, d in raw:
            img = p.parent / d["image"]
            fr = Frame(d.get("video_id", "muestra"), d["frame_id"], float(d.get("t", 0.0)), img,
                       load_image(img))
            res = reader.read(fr, ref_ms=_ms(d.get("published")), allow_vlm=not a.no_vlm)
            results[d["frame_id"]] = res.observations
            charts[d["frame_id"]] = res.is_chart
            ctx[d["frame_id"]] = (res.symbol, res.timeframe)
        engines = ", ".join(sorted({o.engine for obs in results.values() for o in obs})) or "—"
    finally:
        ai.close()
    out = E.evaluate(labels, results, charts, ctx)
    md = render(out, params=DEFAULT, engines=engines,
                when=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
                machine=socket.gethostname())
    Path(a.out).write_text(md, encoding="utf-8")
    print(f"{len(labels)} fotogramas medidos · pasan a T67: {', '.join(out.passing) or 'ninguno'}"
          f" · informe en {a.out}")
    return 0


def cmd_stats(a: argparse.Namespace) -> int:
    from eim.data.video.observations import ObservationStore, observations_path

    store = ObservationStore(observations_path())
    for row in store.counts():
        print(f"{row['kind']:<10} {row['validation']:<15} {row['n']}")
    store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m eim.video.visual")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("frames")
    f.add_argument("file")
    f.add_argument("--video-id", required=True)
    f.add_argument("--delete-source", action="store_true")
    r = sub.add_parser("read")
    r.add_argument("--video-id", required=True)
    r.add_argument("--published")
    r.add_argument("--no-vlm", action="store_true")
    t = sub.add_parser("label-template")
    t.add_argument("--video-id", required=True)
    t.add_argument("--labels", default=str(LABELS))
    e = sub.add_parser("eval")
    e.add_argument("--labels", default=str(LABELS))
    e.add_argument("--out", default="reports/video_visual_eval.md")
    e.add_argument("--no-vlm", action="store_true")
    sub.add_parser("stats")
    a = ap.parse_args(argv)
    return {"frames": cmd_frames, "read": cmd_read, "label-template": cmd_label_template,
            "eval": cmd_eval, "stats": cmd_stats}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
