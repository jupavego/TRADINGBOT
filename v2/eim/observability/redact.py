"""Redacción de secretos antes de que un evento toque el disco (T72). Puro.

Dos defensas: por NOMBRE de clave (cualquier valor bajo `api_key`, `secret`, `token`… se
reemplaza entero) y por FORMA del valor (cabeceras Bearer, claves tipo `sk-…`, cadenas de 64
caracteres alfanuméricos como las claves y firmas de Binance, JWT, `nombre=valor` sensibles).
Las huellas (`Ref.hash`) no pasan por aquí: son identificadores, no secretos.
"""

from __future__ import annotations

import re
from typing import Any

MASK = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(api[_-]?key|apikey|secret|token|passw(?:or)?d|passphrase|authori[sz]ation|credential|"
    r"private[_-]?key|signature|cookie|hmac|mnemonic|seed[_-]?phrase)", re.I)

_NAME = r"(?:api[_-]?key|apikey|secret|token|passw(?:or)?d|passphrase|signature|authorization)"
_VALUE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(rf"(?i)\b({_NAME}\w*)\s*[=:]\s*[^\s&,;\"']+"), rf"\1={MASK}"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"), f"Bearer {MASK}"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), MASK),
    (re.compile(r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"), MASK),
    (re.compile(r"\b0x[0-9a-fA-F]{64}\b"), MASK),
    (re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9]{64}(?![A-Za-z0-9])"), MASK),
)


def redact_text(s: str) -> str:
    for pat, repl in _VALUE_PATTERNS:
        s = pat.sub(repl, s)
    return s


def redact(v: Any) -> Any:
    """Copia de `v` (dict/lista/escalar) con los secretos enmascarados."""
    if isinstance(v, dict):
        return {k: (MASK if _SENSITIVE_KEY.search(str(k)) and v[k] not in (None, "")
                    else redact(v[k])) for k in v}
    if isinstance(v, list | tuple):
        return [redact(x) for x in v]
    if isinstance(v, str):
        return redact_text(v)
    return v
