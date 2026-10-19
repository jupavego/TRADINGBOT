"""Verifica de extremo a extremo la traza de una vela en `/v2/obs/traces` (T74).

Desde `v2/`:  python scripts/obs_verify_traces.py [--provider futures|spot] [--wait 120]

Arranca la API real (`create_app`) en memoria con ciclo de operación en PAPEL (Simulado: no
envía nada a ningún exchange), carpeta de datos temporal (no toca la tuya) y los agentes
reales, espera un ciclo, indexa y comprueba la traza más reciente con `observability.verify`.
`--provider futures` (por defecto) usa el feed de producción (fapi.binance.com, sin claves);
`--provider spot` usa data-api.binance.vision para redes donde fapi está bloqueada (451).
Código de salida 0 si todo lo obligatorio pasa. Con `--keep` conserva la carpeta de datos.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class SpotKlines:
    """Velas reales de Binance spot (público); solo para redes sin acceso a fapi."""

    name = "binance-spot (data-api.binance.vision)"

    def klines(self, symbol, timeframe, start, end):
        import httpx

        from eim.core import Candle
        from eim.data.timeframes import tf_ms
        out, t, now = [], start, int(time.time() * 1000)
        while t < end:
            rows = httpx.get("https://data-api.binance.vision/api/v3/klines", timeout=20, params={
                "symbol": symbol, "interval": timeframe, "startTime": t, "endTime": end,
                "limit": 1000}).raise_for_status().json()
            out += [Candle(t=int(k[0]), o=float(k[1]), h=float(k[2]), l=float(k[3]),
                           c=float(k[4]), v=float(k[5])) for k in rows if int(k[6]) < now]
            if len(rows) < 1000:
                break
            t = int(rows[-1][0]) + tf_ms(timeframe)
        return out


class Idle:
    """Sin websocket: la prueba solo observa el ciclo de operación."""

    name = "inactivo"

    async def stream(self, symbol, timeframe):
        import asyncio
        while True:
            await asyncio.sleep(3600)
            yield {}


def run(provider: str, wait_s: float, keep: bool) -> int:
    from fastapi.testclient import TestClient

    from eim.api.config import Settings
    from eim.api.main import create_app
    from eim.observability.verify import check_trace, passed, render

    d = Path(tempfile.mkdtemp(prefix="eim_obs_verify_"))
    if provider == "futures":
        from eim.data.providers.binance import BinanceFutures
        prov = BinanceFutures()
    else:
        prov = SpotKlines()
    cfg = Settings(data_dir=d, operate=True, execution="paper", operate_poll_s=3.0,
                   calendar=False, arbitrage=False, paper=False, auto_history=False)
    app = create_app(cfg, source=Idle(), operation_provider=prov)
    rc = 1
    try:
        with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)) as c:
            tid, t_end = None, time.time() + wait_s
            while time.time() < t_end and tid is None:
                time.sleep(3)
                app.state.obs_indexer.run_once()
                items = c.get("/v2/obs/traces").json().get("items", [])
                tid = items[0]["trace_id"] if items else None
            if tid is None:
                st = app.state.operation.status
                print(f"SIN TRAZA tras {wait_s:.0f} s (proveedor {prov.name}). "
                      f"Ciclos: {st['cycles']}, fallos: {st['failures']}. "
                      f"Último error: {st['last_error'] or '(ninguno)'}. "
                      f"Salud: {c.get('/v2/obs/health').json().get('problems')}")
                if provider == "futures":
                    print("Si tu red bloquea fapi.binance.com (HTTP 451), repite con "
                          "`--provider spot`: es el mismo flujo con velas spot reales.")
                return 1
            time.sleep(6)                      # deja terminar la fase de decisión del ciclo
            app.state.obs_indexer.run_once()
            full = c.get(f"/v2/obs/traces/{tid}").json()
            health = c.get("/v2/obs/health").json()
            expected = [a.id for a in app.state.operation.cycle.registry.latest()]
            checks = check_trace(full["events"], expected_agents=expected, mode="SIMULADO",
                                 health_ok=bool(health.get("ok")))
            print(f"proveedor: {prov.name} | traza: {tid} | eventos: {len(full['events'])}")
            print(render(checks))
            rc = 0 if passed(checks) else 1
    finally:
        if keep:
            print(f"datos conservados en {d}")
        else:
            shutil.rmtree(d, ignore_errors=True)
    return rc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--provider", choices=("futures", "spot"), default="futures")
    ap.add_argument("--wait", type=float, default=120.0, help="segundos máximos hasta la traza")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.provider, a.wait, a.keep))
