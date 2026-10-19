from __future__ import annotations

import json
import re

import eim.observability.emit as E
from eim.observability.redact import MASK, redact, redact_text

BINANCE_KEY = "vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A"
HL_PRIV = "0x" + "ab" * 32
JWT = ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
       "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")
SECRETS = [BINANCE_KEY, HL_PRIV, "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWx",
           "Bearer abc123def456ghi789", JWT]


def test_by_key_name():
    d = redact({"api_key": "x", "Secret": "y", "nested": {"X-MBX-APIKEY": "z", "token": "t"},
                "price": 10.5, "empty_token": ""})
    assert d["api_key"] == d["Secret"] == MASK
    assert d["nested"]["X-MBX-APIKEY"] == d["nested"]["token"] == MASK
    assert d["price"] == 10.5 and d["empty_token"] == ""


def test_by_value_shape():
    for s in SECRETS:
        assert s not in redact_text(f"fallo con {s} en la llamada"), s
    out = redact_text("GET /fapi?symbol=ETH&signature=9f86d081884c7d659a2feaa0c55ad015a3bf4f1b"
                      "&timestamp=1")
    assert "9f86d081" not in out and "symbol=ETH" in out


def test_leader_address_and_plain_text_survive():
    addr = "0x" + "1f" * 20  # dirección pública de un líder: no es un secreto
    assert redact_text(f"líder {addr} neto 12.5 R") == f"líder {addr} neto 12.5 R"


def test_nothing_secret_reaches_the_disk(spool):
    for s in SECRETS:
        E.emit("alert", "operation.alerts", status="error",
               detail={"msg": f"error con {s}", "api_secret": s, "url": f"https://x?token={s}"},
               source=f"origen {s}")
    assert E.flush()
    raw = "\n".join(f.read_text(encoding="utf-8") for f in spool.glob("*.jsonl"))
    assert raw.count("\n") == len(SECRETS)
    for s in SECRETS:
        assert s not in raw
    assert not re.search(r"[A-Za-z0-9]{64}", raw)
    assert all(json.loads(line) for line in raw.splitlines())
