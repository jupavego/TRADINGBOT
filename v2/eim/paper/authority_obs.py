"""Decisiones del bróker simulado en el Observatorio (T114): una traza por idea en vivo y perfil.

Para que T76 cuente «por qué se abrió (o se rechazó) esta operación» igual que con el plan de
los agentes, cada decisión de una idea en vivo deja en su traza (`proposal_trace`, una por idea
y perfil) la propuesta (`plan`), la decisión de la autoridad (`risk_decision`, con la fuente,
su versión, los datos usados y el motivo) y, si se abrió, el llenado y el cierre (`fill`).
Las ideas reconstruidas del histórico no se emiten (no son decisiones en tiempo real).

El libro se recalcula entero en cada vista: los `event_id` son deterministas (misma idea, mismo
perfil, misma versión de parámetros, mismo resultado → mismo id), así que recalcular o reiniciar
no duplica en la base; y en el proceso se recuerda lo ya emitido para no reescribir el spool.
"""

from __future__ import annotations

from collections import OrderedDict

from eim.core import Mode
from eim.core.authority import params_fingerprint
from eim.observability import hooks
from eim.observability.emit import emit
from eim.observability.events import Ref, new_run_id, proposal_trace
from eim.paper.book import ProfileState
from eim.paper.policy import AUTHORITY, PaperDecision

MAX_SEEN = 50_000


class DecisionEmitter:
    def __init__(self, max_seen: int = MAX_SEEN) -> None:
        self._seen: OrderedDict[str, None] = OrderedDict()
        self.max_seen = max_seen

    def _done(self, key: str, queued: bool) -> bool:
        """Recuerda `key` solo si su evento quedó en cola: lo descartado (cola llena, disco) se
        reintenta en el próximo cálculo, y como el `event_id` es fijo no se duplica."""
        if queued:
            self._seen[key] = None
            while len(self._seen) > self.max_seen:
                self._seen.popitem(last=False)
        return queued

    def emit_books(self, books: dict[str, ProfileState]) -> int:
        """Emite lo nuevo de todos los perfiles; devuelve cuántos eventos salieron."""
        n = 0
        for st in books.values():
            fp = params_fingerprint(st.p)
            closed = {t["id"]: t for t in st.trades} if st.decisions else {}
            for d in st.decisions:
                n += self._emit(st, d, fp, closed.get(d.o.idea.id))
        return n

    def _emit(self, st: ProfileState, d: PaperDecision, fp: str, closed: dict | None) -> int:
        i, p = d.o.idea, st.p
        base = f"paper|{p.id}|{fp}|{i.id}|{'ok' if d.approved else 'no'}"
        tid, n = None, 0
        if base not in self._seen:
            rec = d.as_record(p)
            tid = proposal_trace(rec.proposal, scope=p.id)
            rid = new_run_id()
            ok = emit("plan", AUTHORITY, run_id=rid, trace_id=tid, mode=Mode.SIMULADO,
                      ts_utc=i.t, event_key=base + "|plan",
                      inputs=hooks.proposal_refs(rec.proposal),
                      outputs=[Ref(type="plan", id=i.id[:120])],
                      detail={"side": i.side, "entry": i.entry, "sl": i.sl, "rr": round(i.rr, 2),
                              "status": "PROPUESTA", "strategy": i.sid,
                              "source": "paper.strategies", "profile": p.id,
                              "confidence": i.conf, "symbol": i.symbol,
                              "timeframe": i.timeframe, "expires_at": i.t + i.fill_ms})
            hooks.remember(f"plan:{i.id}", rid)
            ok = bool(hooks.risk_decided(rec, always=True, key=base + "|decision", ts=i.t + 1,
                                         trace_id=tid)) and ok
            n += 2 * self._done(base, ok)
        o = d.o
        if d.approved and o.fill_t is not None and base + "|fill" not in self._seen:
            n += self._fill_event(st, d, base + "|fill", tid, o.fill_t,
                                  "entrada (posición abierta)", o.fill)
        if closed is not None and base + "|exit" not in self._seen:
            n += self._fill_event(st, d, base + "|exit", tid, closed["exit_t"],
                                  f"cierre por {closed['reason']}", closed["exit"],
                                  pnl=closed["pnl"], r=closed["r"])
        return n

    def _fill_event(self, st: ProfileState, d: PaperDecision, key: str, tid: str | None, t: int,
                    what: str, price: float | None, **extra) -> int:
        """Llenado o cierre. Una orden a mercado se llena en la apertura que sigue al cierre de
        la decisión (mismo ms): el evento va al menos 2 ms después, para que la traza respete
        la causalidad; el instante real queda en `detail.t`."""
        i = d.o.idea
        if tid is None:
            tid = proposal_trace(i.as_proposal(), scope=st.p.id)
        ok = emit("fill", AUTHORITY, run_id=new_run_id(), trace_id=tid, mode=Mode.SIMULADO,
                  ts_utc=max(t, i.t + 2), event_key=f"{key}|{t}",
                  inputs=[Ref(type="plan", id=i.id[:120])],
                  detail={"what": what, "qty": d.qty, "price": price, "t": t, "profile": st.p.id,
                          "symbol": i.symbol, "timeframe": i.timeframe, **extra})
        return int(self._done(key, ok))
