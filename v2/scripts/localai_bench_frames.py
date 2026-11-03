"""Fotogramas sintéticos con respuesta conocida para OCR y visión-lenguaje (T62).

Gráficos de velas y diapositivas como los de un video de trading: activo y marco temporal en el
título, niveles horizontales con su cifra, ejes con precios, cifras en formato es («61.250»,
«3,5 %») o en («61,250», «3.5%»), temas claro/oscuro, una parte a 854×480 y recomprimida en JPEG
(como un video de YouTube a 480p). Deterministas (semilla): no se versionan imágenes, se
regeneran. La verdad va a `truth.json` junto a los PNG.
"""

from __future__ import annotations

import io
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
ASSETS = [("BTCUSDT", "BTC", 58000, 112000), ("ETHUSDT", "ETH", 2200, 4800),
          ("SOLUSDT", "SOL", 110, 260)]
TFS = [("15m", "15"), ("1h", "1H"), ("4h", "4H"), ("1d", "1D"), ("1w", "1W")]
THEMES = {"dark": ("#131722", "#d1d4dc", "#26a69a", "#ef5350", "#2a2e39"),
          "light": ("#ffffff", "#131722", "#089981", "#f23645", "#e0e3eb")}


def _font(size: int, bold: bool = False):
    names = ("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fmt(x: float, lang: str, dec: int = 0) -> str:
    s = f"{x:,.{dec}f}"
    return s.replace(",", "\u0001").replace(".", ",").replace("\u0001", ".") if lang == "es" else s


def _round_level(x: float, lo: float) -> float:
    step = 50 if lo > 10000 else (5 if lo > 1000 else 0.5)
    return round(round(x / step) * step, 2)


def chart(rng: random.Random, lang: str, theme: str) -> tuple[Image.Image, dict]:
    sym, asset, lo, hi = rng.choice(ASSETS)
    tf, tf_label = rng.choice(TFS)
    bg, fg, up, dn, grid = THEMES[theme]
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    base = rng.uniform(lo, hi)
    px, closes = [base], []
    for _ in range(80):
        px.append(px[-1] * (1 + rng.gauss(0, 0.012)))
    pmin, pmax = min(px) * 0.985, max(px) * 1.015
    top, bot, left, right = 80, H - 40, 20, W - 130

    def y(p: float) -> float:
        return top + (pmax - p) / (pmax - pmin) * (bot - top)
    dec = 2 if lo < 1000 else 0
    ticks = [pmin + (pmax - pmin) * i / 6 for i in range(1, 6)]
    for t in ticks:
        d.line([(left, y(t)), (right, y(t))], fill=grid)
        d.text((right + 8, y(t) - 8), fmt(t, lang, dec), fill=fg, font=_font(15))
    cw = (right - left) / len(px)
    for i in range(1, len(px)):
        o, c = px[i - 1], px[i]
        hi_ = max(o, c) * (1 + abs(rng.gauss(0, 0.004)))
        lo_ = min(o, c) * (1 - abs(rng.gauss(0, 0.004)))
        x = left + i * cw
        col = up if c >= o else dn
        d.line([(x, y(hi_)), (x, y(lo_))], fill=col)
        d.rectangle([x - cw * 0.35, y(max(o, c)), x + cw * 0.35, y(min(o, c)) + 1], fill=col)
        closes.append(c)
    levels = sorted({_round_level(rng.uniform(pmin * 1.01, pmax * 0.99), lo)
                     for _ in range(rng.randint(1, 3))})
    names = (["Soporte", "Resistencia", "Objetivo"] if lang == "es"
             else ["Support", "Resistance", "Target"])
    for k, lv in enumerate(levels):
        col = "#f7a600"
        d.line([(left, y(lv)), (right, y(lv))], fill=col, width=2)
        d.rectangle([right + 2, y(lv) - 11, W - 4, y(lv) + 11], fill=col)
        d.text((right + 6, y(lv) - 9), fmt(lv, lang, 2 if lo < 1000 else 0), fill="#000000",
               font=_font(15, True))
        d.text((left + 8, y(lv) - 24), names[k % 3], fill=col, font=_font(16, True))
    title = (f"{sym} · {tf_label} · BINANCE" if rng.random() < 0.6
             else f"{asset} / Tether USD · {tf_label}")
    d.text((left, 22), title, fill=fg, font=_font(26, True))
    last = closes[-1]
    d.text((W - 360, 26), f"{fmt(last, lang, dec)}", fill=up, font=_font(22, True))
    keys = [*levels]
    return img, {"kind": "chart", "asset": asset, "timeframe": tf, "levels": levels,
                 "numbers": keys, "title": title}


def slide(rng: random.Random, lang: str, theme: str) -> tuple[Image.Image, dict]:
    sym, asset, lo, hi = rng.choice(ASSETS)
    bg, fg, up, dn, _ = THEMES[theme]
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    entry = _round_level(rng.uniform(lo, hi), lo)
    target = _round_level(entry * (1 + rng.uniform(0.03, 0.12)), lo)
    stop = _round_level(entry * (1 - rng.uniform(0.02, 0.06)), lo)
    pct = round(rng.uniform(1, 12), 1)
    prob = rng.choice([55, 60, 65, 70])
    dec = 2 if lo < 1000 else 0
    if lang == "es":
        title = f"Plan para {asset} esta semana"
        lines = [f"Entrada: {fmt(entry, lang, dec)} USD", f"Objetivo: {fmt(target, lang, dec)}",
                 f"Stop: {fmt(stop, lang, dec)}", f"Subida esperada: +{fmt(pct, lang, 1)} %",
                 f"Probabilidad del escenario: {prob} %"]
    else:
        title = f"{asset} trade plan this week"
        lines = [f"Entry: ${fmt(entry, lang, dec)}", f"Target: {fmt(target, lang, dec)}",
                 f"Stop loss: {fmt(stop, lang, dec)}", f"Expected move: +{fmt(pct, lang, 1)}%",
                 f"Scenario probability: {prob}%"]
    d.text((80, 70), title, fill=fg, font=_font(48, True))
    for i, line in enumerate(lines):
        d.text((110, 190 + i * 82), "• " + line, fill=up if i == 1 else fg, font=_font(36))
    d.text((W - 260, H - 50), "@canal_ejemplo", fill=fg, font=_font(20))
    return img, {"kind": "slide", "asset": asset, "timeframe": None, "levels": [target],
                 "numbers": [entry, target, stop, pct, float(prob)], "title": title}


def degrade(img: Image.Image, rng: random.Random) -> Image.Image:
    """480p y JPEG de calidad media, como un fotograma de video comprimido."""
    small = img.resize((854, 480), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=rng.choice([55, 65, 75]))
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def make_frames(out_dir: Path, n: int = 36, seed: int = 62) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    truth = []
    for i in range(n):
        lang = "es" if i % 2 == 0 else "en"
        theme = "dark" if i % 3 else "light"
        img, t = (chart if i % 3 != 2 else slide)(rng, lang, theme)
        low = i % 4 == 3
        if low:
            img = degrade(img, rng)
        name = f"f{i:02d}_{t['kind']}_{lang}{'_480p' if low else ''}.png"
        img.save(out_dir / name)
        truth.append({"file": name, "lang": lang, "theme": theme, "low_res": low, **t})
    (out_dir / "truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    return truth
