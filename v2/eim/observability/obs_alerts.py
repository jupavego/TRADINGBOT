"""Alertas de salud mínima del observatorio (T75): reglas versionadas → `Condition`. Y el aviso
explícito del LLM local configurado que no puede arrancar (T128, `llm_conditions`).

Reutiliza `AlertCenter` (op_alerts + notificación local): sin canal nuevo y por transición.
Si el propio observatorio no se puede leer, se alerta como indexador atrasado; el mapa pasa a
«sin datos», nunca a verde.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from eim.observability import catalog
from eim.observability import thresholds as T
from eim.operation.alerts import WARN, Condition

RULES_PATH = Path(__file__).parent / "alert_rules" / "obs_alerts_v1.json"

# Tipos que solo se emiten cuando pasa algo. Un componente cuyo único producto es uno de
# estos está callado mientras todo va bien: su silencio es la señal sana, no una avería.
POR_SUCESO = frozenset({"alert"})
# Solo emiten con la interfaz abierta (un cliente suscrito al WebSocket; T128). Hasta que alguien
# se conecta en este arranque, su último evento es del proceso anterior: callar es lo sano. Una
# vez abierto, el canal sigue aunque el cliente se vaya, así que callar desde entonces sí avisa.
CON_CLIENTE = frozenset({"data.live_ticks", "api.hub"})
LLM, LLM_EVERY_MS = "llm_local", 600_000
_llm: dict[str, Any] = {"at": None, "why": None}


def load_rules(path: Path = RULES_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def obs_conditions(con: Any, lock: threading.Lock, now: int,
                   index_lag_s: float | None = None, rules: dict | None = None,
                   started_ms: int | None = None) -> list[Condition]:
    """Condiciones del ciclo. `con`/`lock`: base del observatorio. Solo vigila lo construido
    con cadencia declarada (a demanda no tiene umbral). `started_ms`: arranque de este proceso,
    para no vigilar `CON_CLIENTE` antes de que alguien se conecte."""
    r = (rules or load_rules())["rules"]
    out: list[Condition] = []
    try:
        with lock:
            rows = con.execute("SELECT component_id, max(ts_utc) FROM events "
                               "GROUP BY component_id").fetchall()
            fetch = con.execute("SELECT max(ts_utc) FROM events WHERE kind='data_fetch'"
                                ).fetchone()
            lp = con.execute("SELECT value FROM meta WHERE key='last_pass_ms'").fetchone()
        if index_lag_s is None and lp:
            index_lag_s = (now - int(lp[0])) / 1000
        seen = dict(rows)
        fail = False
    except Exception:  # noqa: BLE001 - observatorio ilegible
        seen, fetch, fail = {}, None, True
    s = r["sin_latido"]
    for c in catalog.COMPONENTS:
        if c.built != "construido" or c.cadence_s is None:
            continue
        # Vigilar por silencio a uno que solo avisa de averías se muerde la cola: la propia
        # alerta de «sin latido» es un evento suyo, que la da por resuelta, y vuelve a
        # saltar unas cadencias después. Afecta a operation.alerts, operation.watchdog y
        # execution.reconcile.
        if c.produces and set(c.produces) <= POR_SUCESO:
            continue
        limit = max(s["min_s"], s["cadences"] * c.cadence_s)
        last = seen.get(c.id)
        if (c.id in CON_CLIENTE and started_ms is not None and last is not None
                and last < started_ms):
            last = None
        # sin ningún evento nunca: es «sin datos» en el mapa, no una avería nueva
        on = (not fail) and last is not None and (now - last) / 1000 > limit
        out.append(Condition(f"{s['kind']}:{c.id}", s["kind"], on, s["level"],
                             f"{s['titulo']}: {c.title_es}", s["texto"].format(n=s["cadences"])))
    d = r["dato_obsoleto"]
    last_fetch = fetch[0] if fetch else None
    out.append(Condition(d["kind"], d["kind"],
                         last_fetch is not None and (now - last_fetch) / 1000 > d["max_age_s"],
                         d["level"], d["titulo"], d["texto"].format(n=d["max_age_s"])))
    i = r["indexador_atrasado"]
    late = fail or (index_lag_s is not None and index_lag_s > T.INDEX_LAG_S_MAX)
    out.append(Condition(i["kind"], i["kind"], late, i["level"], i["titulo"], i["texto"]))
    return out


def llm_conditions(now: int, check: Callable[[], str | None] | None = None) -> list[Condition]:
    """Aviso si el LLM local configurado (`EIM_OLLAMA_EXE`) no puede arrancar en esta sesión: si
    no, Contexto queda «sin datos» en silencio (T126: `Z:`). Mira como mucho cada 10 min."""
    if _llm["at"] is None or now - _llm["at"] >= LLM_EVERY_MS:
        if check is None:
            from eim.data.providers.local_context import ollama_problem as check
        _llm.update(at=now, why=check())
    why = _llm["why"]
    return [Condition(LLM, LLM, why is not None, WARN, "LLM local no disponible", why or "")]
