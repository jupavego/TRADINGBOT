"""Diario de la protección en la mesa del bróker simulado (T110): se lee ANTES de recalcular la
vista (suelo del SL de cada operación), se pone al día DESPUÉS y avisa.

Avisos: `op_alerts` (los pone la API con `alerts`, el mismo centro de la operación continua, así
llegan a la notificación local y al panel) y el observatorio (contrato de T72): cada fila del
diario y cada recuperación emiten un evento `alert` del componente `paper.broker` con la traza
propia de esa operación (`trace_of`), así el mapa cuenta la historia de una protección.
"""

from __future__ import annotations

import hashlib

from eim.core import Mode
from eim.observability.emit import emit
from eim.observability.events import Ref, new_run_id
from eim.operation.alerts import CRITICAL, INFO, PROTECTION, WARN, Alert, Condition
from eim.paper import protection
from eim.paper.generate import now_ms
from eim.paper.protection import Journal, op_key, split
from eim.paper.protection_sync import PassResult, reconcile, run_pass

COMPONENT = "paper.broker"
HELD_KEY, JOURNAL_KEY, RECOVERED_KEY = ("proteccion_inconsistente", "proteccion_diario",
                                        "proteccion_recuperada")
_EVENT_STATUS = {"recuperacion": "degraded", "inconsistente": "error"}


def trace_of(op_id: str) -> str:
    """Traza determinista de una protección: todos sus eventos comparten este `trace_id`."""
    return "tr_" + hashlib.sha256(f"ppp|{op_id}".encode()).hexdigest()[:16]


def obs_event(what: str, row: dict, status: str = "ok", note: str = "") -> None:
    """Evento del observatorio (nunca lanza ni bloquea: `emit`)."""
    emit("alert", COMPONENT, status=status, run_id=new_run_id(),  # type: ignore[arg-type]
         trace_id=trace_of(row["op_id"]), mode=Mode.SIMULADO,
         outputs=[Ref(type="paper_position", id=row["op_id"][:120])],
         detail={"what": f"proteccion_{what}", "profile": row.get("profile"),
                 "symbol": row.get("symbol"), "idea": row.get("idea_id"),
                 "level": row.get("level"), "stop": row.get("stop"),
                 "status": row.get("status"), "t": row.get("updated_t"),
                 "note": (note or row.get("note") or "")[:200]})


class DeskProtection:
    """Mezcla para `PaperDesk`: espera `pstore`, `ep`, `_lock` y `_cache`. `alerts` (centro de
    `op_alerts`) lo pone la API; sin él los avisos quedan en el resumen y en el observatorio."""

    alerts = None

    def _protection_init(self) -> None:
        protection.ensure(self.pstore)
        self.protection_error = ""
        self._journals: dict[str, Journal | None] = {}
        self._prot_started: set[str] = set()     # símbolos ya recuperados en este proceso
        self._prot_seen: set[str] = set()        # operaciones cuya recuperación ya se avisó

    def _guards(self, symbol: str) -> dict:
        """Suelo de cada operación para la simulación; sin diario legible, ninguno (y se avisa)."""
        try:
            j = protection.load(self.pstore, symbol)
        except Exception as exc:  # noqa: BLE001 - la vista se calcula igual, marcada sin verificar
            self._journals[symbol] = None
            self.protection_error = f"{type(exc).__name__}: {exc}"
            return {}
        self._journals[symbol] = j
        return j.guards

    def _sync_protection(self, v) -> None:
        """Pone al día el diario tras recalcular `v`; nunca tumba la vista."""
        now = now_ms()
        j = self._journals.pop(v.symbol, None)
        res = None
        if j is not None:
            try:
                res = run_pass(self.pstore, j, v.books, self.ep, now,
                               startup=v.symbol not in self._prot_started, seen=self._prot_seen)
                self._prot_started.add(v.symbol)
                self.protection_error = ""
            except Exception as exc:  # noqa: BLE001
                self.protection_error = f"{type(exc).__name__}: {exc}"
        v.protection = self._state(v, res)
        try:
            self._notify(v.symbol, res, now)
        except Exception as exc:  # noqa: BLE001 - un aviso roto no tumba la vista
            self.protection_error = f"avisos: {type(exc).__name__}: {exc}"

    def _state(self, v, res: PassResult | None) -> dict:
        if res is None:
            return {"verified": False, "error": self.protection_error or "diario no leído",
                    "held": {}, "n_inconsistent": None}
        return {"verified": True, "error": "", "journal": "paper_protection",
                "first_ms": res.first_ms, "written": len(res.rows),
                "open": len(res.open_ids - set(res.held)), "held": dict(res.held),
                "n_inconsistent": len(res.held),
                "inconsistent": [{"op_id": k, "profile": (split(k) or ("",))[0], "why": w}
                                 for k, w in sorted(res.held.items())],
                "recovered": res.recovered, "ahead": res.ahead}

    def _notify(self, symbol: str, res: PassResult | None, now: int) -> None:
        a = self.alerts
        if res is not None:
            for row in res.rows:
                obs_event(row["event"], row, _EVENT_STATUS.get(row["event"], "ok"))
            logged = {r["op_id"] for r in res.rows if r["event"] == "recuperacion"}
            for r in (r for r in res.recovered if r["op_id"] not in logged):
                obs_event("recuperacion", {**r, **_ids(r["op_id"]), "level": r["to_level"],
                                           "stop": r["to_stop"], "status": "recuperada",
                                           "updated_t": r["saved_t"]}, "degraded", r["note"])
        if a is None:
            return
        conds = [Condition(f"{JOURNAL_KEY}:{symbol}", PROTECTION, res is None, CRITICAL,
                           f"Diario de protección sin verificar ({symbol})",
                           self.protection_error[:300])]
        if res is None:
            a.update(now, conds)
            return
        for r in res.recovered:
            ids = _ids(r["op_id"])
            a.emit(Alert(now, PROTECTION, WARN, f"Protección recuperada del diario: "
                         f"{ids['profile']} {ids['symbol']}", f"{ids['idea_id']}: {r['note']}",
                         f"{RECOVERED_KEY}:{r['op_id']}"))
        for r in res.ahead:
            ids = _ids(r["op_id"])
            a.emit(Alert(now, PROTECTION, INFO, f"Protección por delante de lo guardado: "
                         f"{ids['profile']} {ids['symbol']}",
                         f"{ids['idea_id']}: al arrancar el recálculo va en el escalón "
                         f"{r['to_level']} y lo guardado en el {r['from_level']}; se adopta el "
                         f"recálculo (el mayor) y se registran {r['changes']} cambio(s)",
                         f"{RECOVERED_KEY}:{r['op_id']}"))
        for op_id, why in sorted(res.held.items()):
            conds.append(_held_condition(op_id, True, why))
        for key in _active(a):
            op_id = key.split(":", 1)[1] if key.startswith(f"{HELD_KEY}:") else ""
            if op_id and _ids(op_id)["symbol"] == symbol and op_id not in res.held:
                conds.append(_held_condition(op_id, False, "reconciliada"))
        a.update(now, conds)

    def annotate_protection(self, v, profiles: list[dict]) -> None:
        """Contadores por perfil en el resumen y estado de cada posición abierta."""
        held = (v.protection or {}).get("held", {})
        for p in profiles:
            mine = {k: w for k, w in held.items() if (split(k) or ("",))[0] == p["id"]}
            for x in p.get("positions", []):
                k = op_key(p["id"], v.symbol, x["id"])
                if k in mine:
                    x["protection_state"], x["protection_why"] = "inconsistente", mine[k]
                elif (x.get("ladder") or {}).get("recovered"):
                    x["protection_state"] = "recuperada"
            p["protection"] = {
                "verified": (v.protection or {}).get("verified"), "inconsistent": len(mine),
                "recovered": sum(1 for x in p.get("positions", [])
                                 if x.get("protection_state") == "recuperada")}

    # --- consulta y reconciliación (API y CLI) -----------------------------------------
    def protection_overview(self, symbol: str | None = None, status: str | None = None,
                            limit: int = 500) -> dict:
        rows = protection.overview(self.pstore, symbol, limit=1_000_000)
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        sel = [r for r in rows if status is None or r["status"] == status]
        return {"counts": counts, "error": self.protection_error, "total": len(sel),
                "rows": sel[:limit]}

    def resolve_protection(self, op_id: str, decision: str, note: str) -> dict:
        """Reconciliación manual de una operación inconsistente (`protection_sync.reconcile`)."""
        ids = split(op_id)
        if ids is None:
            raise LookupError(f"identificador de operación ilegible: {op_id}")
        with self._lock:
            row = reconcile(self.pstore, op_id, decision, note, now_ms())
            v = self._cache.get(ids[1])
            if v is not None:                 # desfasada: se rehace sin dejar la API sin vista
                v.stamp = ()
        obs_event("reconciliada", row)
        return row


def _active(a) -> list[str]:
    """Claves vigentes del centro de alertas; lo comparte el hilo del supervisor, que puede
    mutarlas mientras se recorren."""
    for _ in range(3):
        try:
            return list(a.active)
        except RuntimeError:
            continue
    return []


def _held_condition(op_id: str, on: bool, why: str) -> Condition:
    ids = _ids(op_id)
    return Condition(f"{HELD_KEY}:{op_id}", PROTECTION, on, CRITICAL,
                     f"Protección en estado inconsistente: {ids['profile']} {ids['symbol']}",
                     f"{ids['idea_id']}: {why}"[:500])


def _ids(op_id: str) -> dict:
    p, s, i = split(op_id) or ("", "", op_id)
    return {"op_id": op_id, "profile": p, "symbol": s, "idea_id": i}
