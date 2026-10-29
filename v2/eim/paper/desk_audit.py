"""Auditoría de cada cálculo de la vista del bróker (T118): libro fijo, alcance e instantánea.

Tras calcular la vista, `PaperDesk._compute` llama a `_audit`, que (1) concilia las operaciones
en vivo de cada perfil con el libro fijo (`ledger.reconcile`, en `counts.ledger`), (2) declara el
alcance (`scope`: tramo, techo y huecos con su porqué, `view_scope.scope_of`) y (3) guarda la foto
de lo que el panel va a mostrar (`snapshot.record`) y pone su identificador en `snapshot`. Nada de
esto puede tumbar la vista: un fallo queda en `snapshot.error` / `ledger_error`.
"""

from __future__ import annotations

import functools
import hashlib
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from eim.core.authority import params_fingerprint
from eim.paper import ledger, snapshot
from eim.paper.generate import now_ms
from eim.paper.policy import POLICY_VERSION
from eim.paper.view_scope import scope_of

if TYPE_CHECKING:
    from eim.paper.desk import View

PKG = Path(__file__).resolve().parents[1]
ALL_ROWS = 10_000_000


@functools.lru_cache(maxsize=1)
def code_version() -> str | None:
    """Commit del código que corre, con «+cambios» si el paquete `eim` difiere de ese commit (una
    vez por proceso; None fuera de un repositorio git)."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=PKG,
                             capture_output=True, text=True, timeout=5)
        if out.returncode != 0 or not out.stdout.strip():
            return None
        dirty = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "."], cwd=PKG,
                               capture_output=True, timeout=10).returncode == 1
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() + ("+cambios" if dirty else "")


class DeskAudit:
    def _audit_init(self) -> None:
        snapshot.ensure(self.pstore)
        self.snapshot_error = ""
        self._largest: dict[str, dict[str, dict]] = {}   # por símbolo: lo más contado antes

    def versions(self) -> dict:
        """Versión de todo lo que decide las cifras: perfiles, mecánica, política y código."""
        return {"profiles": {p.id: params_fingerprint(p) for p in self.profiles},
                "exec": hashlib.sha256(self.ep.model_dump_json().encode()).hexdigest()[:12],
                "policy": POLICY_VERSION, "code": code_version()}

    def _data(self, v: View) -> dict:
        ctx, bounds, funding = v.stamp
        return {"contexts": {tf: list(s) for tf, s in zip(self.tfs, ctx, strict=True)},
                "candles": list(bounds) if bounds else None, "funding_last": funding}

    def _reconcile(self, v: View, payload: dict) -> None:
        try:
            rec = ledger.reconcile(ledger.query(self.pstore, v.symbol, "perfil", None, ALL_ROWS),
                                   v.books)
        except Exception as exc:  # noqa: BLE001 - conciliar nunca tumba la vista
            self.ledger_error, rec = f"{type(exc).__name__}: {exc}", {}
        for p in payload["profiles"]:
            p["counts"]["ledger"] = rec.get(p["id"])

    def _prior(self, symbol: str) -> dict[str, dict]:
        if symbol not in self._largest:
            try:
                self._largest[symbol] = snapshot.largest(self.pstore, symbol)
            except Exception as exc:  # noqa: BLE001 - sin historia previa, la vista sigue
                self.snapshot_error = f"{type(exc).__name__}: {exc}"
                return {}
        return self._largest[symbol]

    def _audit(self, v: View, payload: dict) -> None:
        self._reconcile(v, payload)
        ver = self.versions()
        # cada idea que la sombra no rechazó la puede tomar un perfil una vez (la escalera
        # re-simula su salida, así que no basta con las que la sombra ya cerró)
        ceiling = sum(1 for o in v.outcomes if o.status != "RECHAZADA")
        payload["coverage"]["takeable"] = ceiling
        prior = self._prior(v.symbol)
        try:      # el alcance es accesorio: si falla, la foto se guarda igual y lo dice
            more = {pr["id"] for p in payload["profiles"]
                    if (pr := prior.get(p["id"])) and pr["n"] > p["n_closed"]}
            bodies = {sid: (snapshot.get(self.pstore, sid) or {}).get("snapshot")
                      for sid in more}
            payload["scope"] = scope_of(payload, ceiling, prior, bodies, ver)
        except Exception as exc:  # noqa: BLE001
            payload["scope"] = {"error": f"{type(exc).__name__}: {exc}", "complete": False,
                                "gaps": [], "ceiling": ceiling}
        try:
            body = snapshot.photo(payload, v.computed, ver, self._data(v))
            sid = snapshot.record(self.pstore, body, now_ms())
            for p in body["profiles"]:
                if p["n_closed"] > prior.get(p["id"], {}).get("n", -1):
                    prior[p["id"]] = {"n": p["n_closed"], "id": sid, "computed": v.computed}
            self.snapshot_error = ""
            payload["snapshot"] = {"id": sid, "computed": v.computed, "error": ""}
        except Exception as exc:  # noqa: BLE001 - sin instantánea la vista se sirve y lo dice
            self.snapshot_error = f"{type(exc).__name__}: {exc}"
            payload["snapshot"] = {"id": None, "computed": v.computed,
                                   "error": self.snapshot_error}
