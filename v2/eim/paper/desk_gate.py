"""La mesa y sus puertas de costo (T143 (4), T179): costo vivido y qué toma cada perfil.

Mezcla de `PaperDesk`, como `DeskProtection` y `DeskAudit`. La regla está en `tf_gate`,
`tf_gate_profile` y `tf_calib` (puros); aquí solo se lee el libro fijo y se guardan los tramos.
"""

from __future__ import annotations

from pathlib import Path

from eim.paper import cost_ledger, ledger, tf_calib, tf_gate_profile
from eim.paper.engine import Outcome


class DeskGate:
    def _gate_init(self, path: Path | None = None) -> None:
        """`path`: dónde guardar los tramos cerrados por perfil (solo las mesas con la puerta)."""
        self._gate_path = path
        self._cost_cache: dict[str, tuple[int, dict]] = {}   # T143 (4): por filas del libro
        self._rows_cache: dict[str, tuple[int, list[dict]]] = {}
        self.gate_error = ""

    def _ledger_rows(self, symbol: str) -> tuple[int, list[dict]]:
        """Filas `perfil` del libro fijo; se releen solo si cambió su número."""
        n = ledger.counts(self.pstore).get(f"perfil:{symbol}", 0)
        hit = self._rows_cache.get(symbol)
        if hit is None or hit[0] != n:
            hit = self._rows_cache[symbol] = (n, ledger.query(self.pstore, symbol, "perfil",
                                                              limit=max(n, 1)))
        return hit

    def _cost(self, symbol: str) -> dict:
        """Costo vivido (T143 (4)); se resume solo si cambió el libro."""
        n, rows = self._ledger_rows(symbol)
        hit = self._cost_cache.get(symbol)
        if hit is None or hit[0] != n:
            hit = self._cost_cache[symbol] = (n, cost_ledger.summarize(rows))
        return hit[1]

    def _tradable(self, v, tradable: list[Outcome]) -> dict[str, list[Outcome]]:
        """Lo que cada perfil puede tomar: la puerta de T143 para todos o, con
        `tf_gate_by_profile`, la de T179 por perfil y marco. Un fallo deja la de T143."""
        same = {p.id: tradable for p in self.profiles}
        if not self.ep.tf_gate_by_profile or self._gate_path is None:
            return same
        try:
            cor = tf_calib.corrections(self._ledger_rows(v.symbol)[1], v.outcomes)
            rows = tf_gate_profile.decide(self.tfs, v.outcomes, self.ep, self.profiles, cor)
            at = max((o.idea.t for o in v.outcomes), default=0) + 1   # solo ideas futuras
            closed = tf_gate_profile.update(tf_gate_profile.load(self._gate_path), rows,
                                            v.symbol, at)
            tf_gate_profile.save(self._gate_path, closed)
            v.tf_cost_profiles = rows
            self.gate_error = ""
            return tf_gate_profile.tradable(closed, v.symbol, self.profiles, v.outcomes)
        except Exception as exc:  # noqa: BLE001 - la puerta nunca tumba la vista
            self.gate_error = f"{type(exc).__name__}: {exc}"
            return same
