"""Cliente mínimo de la API local en marcha (CLI de informes y copias).

DuckDB admite un solo proceso escritor: cuando la API tiene la base abierta, las CLI le piden
el trabajo a ella. Todo POST lleva `X-EIM-Confirm` (ver eim/api/execution.py `confirm`); si
existe `EIM_API_TOKEN` se envía también como `Authorization: Bearer`.
"""

from __future__ import annotations

import json
import os
import urllib.request

DEFAULT_API = "http://127.0.0.1:8000"


def post_local(api: str, path: str, confirm: str, timeout: float = 120.0) -> dict:
    headers = {"X-EIM-Confirm": confirm}
    if os.environ.get("EIM_API_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['EIM_API_TOKEN']}"
    req = urllib.request.Request(f"{api}{path}", method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - API local
        return json.loads(resp.read())
