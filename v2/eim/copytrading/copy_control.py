"""Control de la subcuenta de copia (T42): funding, kill-switch propio, reconciliación y pausa.

Se mezcla en `CopyEngine`. La divergencia no explicada que persiste `recon_confirm`
comprobaciones seguidas pausa la copia y avisa; solo una reanudación manual la levanta.
En pausa no se abre ni aumenta nada; sí se reduce o cierra siguiendo al líder (salir nunca
se veta).
"""

from __future__ import annotations

from eim.copytrading.copy_models import ExecQuote
from eim.copytrading.copy_recon import Recon, reconcile
from eim.copytrading.replicator import Action, CoinCopy, same, sgn


class EngineControl:
    """Métodos de control; los atributos los define `CopyEngine.__init__`."""

    def on_funding(self, coin: str, t: int, rate: float, px: float) -> float | None:
        amount = self.account.apply_funding(coin, t, rate, px)
        if amount is not None:
            self.log("funding", f"funding {coin} {amount:+,.4f} USD (tasa {rate:+.6%})",
                     coin=coin, t_funding=t, rate=rate, px=px, amount=amount)
        return amount

    def _after(self, now: int) -> None:
        """Kill-switch de la subcuenta por caída: cierre ordenado de todo a la marca."""
        if self.risk.kill.active:
            return
        why = self.risk.check_kill(self.account, now)
        if not why:
            return
        self._now = now
        self._count("kills")
        self.log("kill", "kill-switch de la subcuenta: " + "; ".join(why), code="drawdown")
        self._alert("critical", f"Copia {self.label or self.leader_id}: kill-switch",
                    "; ".join(why) + " · se cierran las posiciones")
        for coin in list(self.account.positions):
            px = self.account.mark(coin) or self.account.positions[coin].entry
            self._exit(coin, "kill", ExecQuote(t=now, at=now, mid=px, src="marca"), now,
                       "cierre ordenado por kill-switch")

    def reconcile(self, t: int, photo: dict[str, float], pending: set[str] | None = None,
                  state_t: int | None = None) -> Recon:
        """`t` = cuándo vimos la foto; `state_t` = hora del exchange de ese estado. Lo que el
        líder hizo después de `state_t` (ya procesado) o que sigue en camino (`pending`) no es
        una señal perdida."""
        self._now = max(self._now, t)
        gap = self.gap or (self.feed_t is not None and t - self.feed_t > self.p.recon_gap_ms
                           and (self.feed_t, t))
        if gap:
            self._resync(t, photo, state_t, f"hueco de captura de {(gap[1] - gap[0]) / 60_000:.0f}"
                         " min sin confirmar el flujo del líder")
        elif self.resync:
            self._resync(t, photo, state_t, "reanudación manual")
        self.feed_t = max(self.feed_t or 0, t)  # la foto también confirma el flujo
        pending = set(pending or ())
        if state_t is not None:
            pending |= {c for c, st in self.last_sig_t.items() if st > state_t}
        acc = self.account
        marks = {c: m[1] for c, m in acc.marks.items()}
        own = {c: p.size for c, p in acc.positions.items()}
        r = reconcile(t, self.coins, own, photo, pending, marks, self.spec, self.p)
        self.last_recon = r
        self._count("recon")
        bad = {d.coin for d in r.unexplained}
        self.mismatch = {c: n for c, n in self.mismatch.items() if c in bad}
        for coin in bad:
            self.mismatch[coin] = self.mismatch.get(coin, 0) + 1
        if r.diffs:
            self._count("recon_diff")
            if r.unexplained:
                self._count("recon_unexplained")
                self.last_bad_t = t
            self.log("recon", "; ".join(f"{d.coin}: {d.why}" for d in r.diffs),
                     code="ok" if r.ok else "no_explicada",
                     diffs=[d.model_dump() for d in r.diffs])
        confirmed = [d for d in r.unexplained if self.mismatch[d.coin] >= self.p.recon_confirm]
        if confirmed and not self.paused:
            self._count("pauses")
            self.pause("divergencia no explicada: " + "; ".join(
                f"{d.coin} {d.why}" for d in confirmed), t)
        return r

    def pause(self, reason: str, t: int) -> None:
        self._now = max(self._now, t)
        self.paused = reason
        self.log("pause", f"copia en pausa: {reason}", code="divergencia")
        self._alert("critical", f"Copia {self.label or self.leader_id} en pausa", reason)

    def resume(self, t: int, by: str = "manual") -> None:
        """Solo manual: levanta la pausa y el kill-switch de la subcuenta."""
        self._now = max(self._now, t)
        self.paused = None
        self.mismatch.clear()
        if self.risk.kill.active:
            self.risk.kill.deactivate(t, by="manual", reason=by)
        self.resync = True
        self.log("resume", f"copia reanudada ({by}): la próxima foto del líder fija su vista",
                 code="manual")

    def _resync(self, t: int, photo: dict[str, float], state_t: int | None, why: str) -> None:
        """La vista del líder pasa a ser su foto real (tras reanudar a mano o tras un hueco de
        captura conocido). Si el líder ya no tiene nuestro lado, se cierra (seguir su salida);
        lo que abrió sin que lo viéramos no se copia a medias. Nunca se abre ni aumenta para
        «cuadrar». Las ejecuciones anteriores a esa foto que lleguen después se ignoran."""
        self.resync, self.gap = False, None
        self.state_t = max(self.state_t, state_t if state_t is not None else t)
        acc, done = self.account, []
        for coin in sorted(set(self.coins) | set(photo) | set(acc.positions)):
            real, c = photo.get(coin, 0.0), self.coins.get(coin) or CoinCopy(coin)
            if (same(c.leader, real) and coin in self.coins) or (
                    state_t is not None and self.last_sig_t.get(coin, 0) > state_t):
                continue  # ya cuadra, o la vista es más nueva que la foto
            own = acc.size(coin)
            if own and (real == 0 or sgn(real) != sgn(own)):
                px = acc.mark(coin) or acc.positions[coin].entry
                a = Action(coin=coin, kind="close", side=-sgn(own), qty=abs(own), target=0.0)
                self._execute(a, None, ExecQuote(t=t, at=t, mid=px, src="marca"), t,
                              acc.positions[coin].trip_t)
                own = 0.0
            if real == 0:
                self.coins.pop(coin, None)
            elif own:
                c.leader, c.note = real, f"vista del líder resincronizada ({why})"
                self.coins[coin] = c
            else:
                self.coins[coin] = CoinCopy(coin, leader=real, leader_entry=acc.mark(coin) or 0.0,
                                            trip_t=t, excluded="apertura_no_vista")
            done.append(f"{coin} {c.leader:+.6g} → {real:+.6g}")
        self._count("resyncs")
        self.log("recon", f"vista resincronizada con la foto ({why})" +
                 (": " + "; ".join(done) if done else ": sin cambios"), code="resync")
