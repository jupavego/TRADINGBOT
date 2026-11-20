"""Interpretación pura del texto leído en un fotograma (T66): cifras, activo, marco e indicadores.

Formatos de cifra admitidos: «61.250» / «61,250» (miles), «3,5» / «3.5» (decimal), «61,250.50»
y «61.250,50» (el último separador es el decimal), sufijos k/M, moneda ($, USD, USDT) y «%».
Un separador seguido de exactamente tres cifras (y nada más) se lee como miles. Lo que no encaja
no se adivina: no produce cifra.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUM = re.compile(
    r"(?P<cur>\$|US\$)?\s?(?P<num>[+-−]?\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d+)?|[+-−]?\d+(?:[.,]\d+)?)"
    r"\s?(?P<suf>[kKmM](?![a-zA-Z]))?\s?(?P<unit>%|USDT|USD)?")
_SYMBOLS = {
    "BTCUSDT": ("BTCUSDT", "BTC/USDT", "BTCUSD", "BTC/USD", "XBTUSD", "BITCOIN", "BTC"),
    "ETHUSDT": ("ETHUSDT", "ETH/USDT", "ETHUSD", "ETH/USD", "ETHEREUM", "ETH"),
    "SOLUSDT": ("SOLUSDT", "SOL/USDT", "SOLUSD", "SOLANA"),
}
_TF = re.compile(r"(?<![\w.])(\d{1,2})\s?(m|min|h|H|D|d|W|w|M)(?![\w])")
_TF_UNIT = {"m": "m", "min": "m", "h": "h", "H": "h", "D": "d", "d": "d", "W": "w", "w": "w",
            "M": "M"}
_IND = re.compile(
    r"(?P<name>RSI|EMA|SMA|MA|VWAP)\s?\(?\s?(?P<period>\d{1,3})?\s?(?:,\s?close\s?)?\)?\s*[:=]?\s*"
    r"(?P<val>\d[\d.,]*)", re.IGNORECASE)


@dataclass(frozen=True)
class Number:
    value: float
    unit: str          # "%", "USD" o ""
    raw: str


def parse_number(raw: str) -> float | None:
    s = raw.replace("−", "-").replace(" ", "")
    neg = s.startswith("-")
    s = s.lstrip("+-")
    seps = [c for c in s if c in ".,"]
    if not seps:
        out = float(s)
    elif len(set(seps)) == 2:                       # «61,250.50» o «61.250,50»
        dec = s[max(s.rfind("."), s.rfind(","))]
        out = float(s.replace("." if dec == "," else ",", "").replace(dec, "."))
    else:
        sep = seps[0]
        parts = s.split(sep)
        if len(parts) > 2 or (len(parts[-1]) == 3 and parts[0] not in ("", "0")):
            if not all(len(x) == 3 for x in parts[1:]):
                return None
            out = float("".join(parts))              # miles
        else:
            out = float(s.replace(sep, "."))         # decimal
    return -out if neg else out


def numbers(text: str) -> list[Number]:
    out: list[Number] = []
    for m in _NUM.finditer(text):
        raw = m.group("num")
        if re.fullmatch(r"\d{1,2}", raw.strip()) and not m.group("unit") and not m.group("cur"):
            continue                                  # «1», «15»: rótulos, no cifras
        val = parse_number(raw)
        if val is None:
            continue
        suf = (m.group("suf") or "").lower()
        val *= {"k": 1e3, "m": 1e6}.get(suf, 1.0)
        unit = m.group("unit") or ""
        if m.group("cur") or unit in ("USDT", "USD"):
            unit = "USD"
        out.append(Number(round(val, 8), unit, m.group(0).strip()))
    return out


def symbol_of(text: str) -> str | None:
    up = text.upper()
    for sym, names in _SYMBOLS.items():
        for n in names:
            if re.search(rf"(?<![A-Z]){re.escape(n)}(?![A-Z])", up):
                return sym
    return None


def timeframe_of(text: str) -> str | None:
    m = _TF.search(text)
    if not m:
        return None
    unit = _TF_UNIT[m.group(2)]
    if unit == "M" and m.group(2) == "M" and int(m.group(1)) > 12:
        return None
    return f"{int(m.group(1))}{unit}"


@dataclass(frozen=True)
class IndicatorText:
    name: str          # rsi | ema | sma | vwap
    period: int | None
    value: float
    raw: str

    @property
    def unit(self) -> str:
        return self.name if self.period is None else f"{self.name}:{self.period}"


def indicators(text: str) -> list[IndicatorText]:
    out: list[IndicatorText] = []
    for m in _IND.finditer(text):
        val = parse_number(m.group("val").rstrip(".,"))
        if val is None:
            continue
        name = m.group("name").lower()
        name = "sma" if name == "ma" else name
        period = int(m.group("period")) if m.group("period") else None
        out.append(IndicatorText(name, period, val, m.group(0).strip()))
    return out


def letters(text: str) -> int:
    return sum(ch.isalpha() for ch in text)
