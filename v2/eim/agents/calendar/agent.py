"""Agente `calendar`: cuantifica el riesgo de evento a partir de `snapshot.events` (sin I/O).

Es un agente de RIESGO, no direccional: `bias` es siempre 0. Su información va en `metrics`
(próximo evento de alto impacto, minutos restantes, ventana pre/post activa, `blackout` que el
motor de riesgo convierte en veto, sorpresa cuando ya salió el dato). `confidence` mide qué tan
completo y fresco es el calendario, no una convicción de mercado.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from eim.agents.base import no_data_report
from eim.agents.calendar.params import CalendarParams
from eim.core import AgentReport, EconEvent, MarketSnapshot, Overlay

_MIN_MS = 60_000
_HOUR_MS = 60 * _MIN_MS
_RANK = {"bajo": 0, "medio": 1, "alto": 2}
NO_CONSENSUS = ("consenso no disponible: las fuentes oficiales gratuitas no publican previsión "
                "(T33); la sorpresa frente al previsto no se calcula")


def _utc(t: int) -> str:
    return datetime.fromtimestamp(t / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")


def _dur(ms: int) -> str:
    m = max(0, math.ceil(ms / _MIN_MS))
    d, h, mi = m // 1440, m % 1440 // 60, m % 60
    return f"{d} d {h} h" if d else f"{h} h {mi} min" if h else f"{mi} min"


def _src(e: EconEvent) -> str:
    return e.id.split(":", 1)[0]


def _brief(e: EconEvent, asof: int) -> dict:
    return {"id": e.id, "name": e.name, "t_utc": e.t_utc, "impact": e.impact,
            "country": e.country, "minutes": round((e.t_utc - asof) / _MIN_MS),
            "source": e.source}


class CalendarAgent:
    id = "calendar"
    version = "1.1.0"
    requires = {"events"}

    def __init__(self, params: CalendarParams | None = None) -> None:
        self.params = params or CalendarParams()

    # --- calidad del calendario ---------------------------------------------
    def _quality(self, snap: MarketSnapshot) -> tuple[float, dict, list[str]]:
        p, asof = self.params, snap.asof
        state, problems, scores = {}, [], []
        for s in p.expected_sources:
            cov = snap.coverage.get(f"events:{s}")
            if cov is None:
                state[s] = {"present": False}
                problems.append(f"fuente {s} sin consultas correctas: calendario incompleto")
                scores.append(0.0)
                continue
            fetched, t_last = cov
            age_h = (asof - fetched) / _HOUR_MS
            fresh = age_h <= p.stale_hours
            frac = min(1.0, max(0.0, (t_last - asof) / (p.horizon_days * 24 * _HOUR_MS)))
            state[s] = {"present": True, "fetched_at": fetched, "age_h": round(age_h, 1),
                        "fresh": fresh, "known_until": t_last, "horizon_frac": round(frac, 3)}
            if not fresh:
                problems.append(f"fuente {s} obsoleta: última consulta hace {age_h:.0f} h "
                                f"(> {p.stale_hours:.0f} h)")
            elif frac < 1:
                problems.append(f"fuente {s} solo conoce eventos hasta {_utc(t_last)}: "
                                f"cobertura parcial de los próximos {p.horizon_days:.0f} d")
            scores.append(frac if fresh else 0.0)
        return (sum(scores) / len(scores) if scores else 0.0), state, problems

    # --- ventanas de riesgo --------------------------------------------------
    def _windows(self, events: list[EconEvent]) -> list[tuple[EconEvent, int, int, bool, str]]:
        """(evento, inicio, fin, abre blackout, base) de cada ventana de riesgo.

        Publicaciones medidas en T37 usan su ventana por evidencia (`event_windows`); una
        ventana (0, 0) significa "no mueve el mercado" y no genera ventana. El resto usa la
        ventana por impacto (solo medio/alto)."""
        p, out = self.params, []
        for e in events:
            if (w := p.event_windows.get(e.name)) is not None:
                if w.pre or w.post:
                    out.append((e, e.t_utc - w.pre * _MIN_MS, e.t_utc + w.post * _MIN_MS,
                                w.blackout, f"evidencia T37: {w.evidence}"))
                continue
            pre, post = p.pre_minutes.get(e.impact), p.post_minutes.get(e.impact)
            if pre is None or post is None:
                continue
            if e.impact == "alto":
                post = max(post, p.post_minutes_by_source.get(_src(e), 0))
            out.append((e, e.t_utc - pre * _MIN_MS, e.t_utc + post * _MIN_MS,
                        e.impact in p.blackout_impacts, "por defecto (impacto, sin evidencia)"))
        return out

    @staticmethod
    def _bar_ms(snap: MarketSnapshot) -> int:
        cs = snap.candles
        return cs[-1].t - cs[-2].t if len(cs) >= 2 else 0

    def _surprise(self, released: list[EconEvent]) -> dict | None:
        """Último dato de alto impacto ya publicado (−24 h): real vs previsto, estandarizado."""
        if not released:
            return None
        e = released[-1]
        out = {"event": e.name, "t_utc": e.t_utc, "actual": e.actual, "forecast": e.forecast,
               "previous": e.previous, "revised": e.revised, "unit": e.unit, "z": None}
        if e.actual is None:
            out["note"] = "valor real no disponible (sin clave FRED o aún no reflejado)"
        elif e.forecast is None:
            out["note"] = NO_CONSENSUS
        elif (sd := self.params.surprise_sd.get(e.name)) and sd > 0:
            out["z"] = round((e.actual - e.forecast) / sd, 3)
            out["note"] = f"(real − previsto) / σ histórica {sd}"
        else:
            out["diff"] = e.actual - e.forecast
            out["note"] = "sin σ histórica de la sorpresa (T37): diferencia sin estandarizar"
        return out

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p, asof = self.params, snapshot.asof
        events = snapshot.events
        if events is None:
            return no_data_report(self.id, self.version, asof,
                                  "calendario económico sin sincronizar a la fecha del "
                                  "snapshot: riesgo de evento desconocido")
        confidence, state, problems = self._quality(snapshot)
        relevant = [e for e in events if e.impact in ("medio", "alto")]
        future_high = [e for e in events if e.impact == "alto" and e.t_utc > asof]
        released_high = [e for e in events if e.impact == "alto" and e.t_utc <= asof]
        nxt = min(future_high, key=lambda e: e.t_utc, default=None)
        wins = self._windows(events)
        order = sorted(wins, key=lambda w: (-_RANK[w[0].impact], abs(w[0].t_utc - asof)))
        active = [(e, "pre" if asof < e.t_utc else "post") for e, a, b, _k, _s in order
                  if a <= asof < b]
        # El reporte vale hasta la próxima vela: una ventana que empieza antes también bloquea.
        until = asof + p.lookahead_bars * self._bar_ms(snapshot)
        blocking = [(e, "pre" if asof < e.t_utc else "post") for e, a, b, k, _s in order
                    if k and a <= max(asof, until - 1) and asof < b]
        top = active[0] if active else None
        reason = ""
        if blocking:
            e, ph = blocking[0]
            when = (f"en {_dur(e.t_utc - asof)}" if ph == "pre"
                    else f"hace {_dur(asof - e.t_utc)}")
            reason = (f"ventana {ph}-evento de alto impacto: {e.name} ({e.country}) "
                      f"{_utc(e.t_utc)}, {when}")
        surprise = self._surprise(released_high)
        metrics = {
            "next_high_impact": _brief(nxt, asof) if nxt else None,
            "minutes_to_next_high": math.ceil((nxt.t_utc - asof) / _MIN_MS) if nxt else None,
            "window": top[1] if top else None,
            "window_event": _brief(top[0], asof) if top else None,
            "blackout": bool(blocking), "blackout_reason": reason,
            "risk_windows": [{"id": e.id, "name": e.name, "impact": e.impact, "start": a,
                              "end": b, "blackout": k, "basis": basis}
                             for e, a, b, k, basis in wins if b > asof],
            "surprise": surprise,
            "upcoming": [_brief(e, asof) for e in relevant if e.t_utc > asof][:p.upcoming_max],
            "recent": [_brief(e, asof) | {"actual": e.actual, "previous": e.previous,
                                          "revised": e.revised, "unit": e.unit}
                       for e in relevant if e.t_utc <= asof],
            "counts": {k: sum(e.impact == k for e in events) for k in ("alto", "medio", "bajo")},
            "sources": state, "coverage": snapshot.coverage.get("events"),
            "source": snapshot.sources.get("events", ""), "consensus_available": False,
        }
        hi = metrics["coverage"][1] if metrics["coverage"] else asof
        evidence = [
            (f"Próximo evento de alto impacto: {nxt.name} ({nxt.country}) {_utc(nxt.t_utc)}, "
             f"en {_dur(nxt.t_utc - asof)}") if nxt else
            f"Sin eventos de alto impacto conocidos hasta {_utc(hi)}",
            f"{len(events)} eventos en −24 h … +7 d (alto {metrics['counts']['alto']}, "
            f"medio {metrics['counts']['medio']}); fuentes: {metrics['source']}",
        ]
        warnings = list(problems)
        if reason:
            evidence.insert(0, reason[0].upper() + reason[1:])
            warnings.insert(0, f"Riesgo de evento: {reason} — sin entradas nuevas")
        elif top:
            e, ph = top
            warnings.insert(0, f"Ventana {ph}-evento de impacto {e.impact}: {e.name} "
                               f"{_utc(e.t_utc)} (volatilidad esperada)")
        if surprise is not None:
            warnings.append(f"{surprise['event']}: {surprise['note']}")
        last = snapshot.candles[-1].c if snapshot.candles else None
        overlays = [
            Overlay(id=f"calendar:event:{e.id}", agent_id=self.id, kind="marker",
                    t_from=e.t_utc, geometry={"t": e.t_utc, "p": last, "action": "evento",
                                              "impact": e.impact},
                    label=f"{e.name} · {e.impact}", confidence=confidence,
                    evidence=[e.source], valid_until=b)
            for e, _a, b, _k, _s in wins
        ]
        return AgentReport(
            agent_id=self.id, version=self.version, asof=asof, bias=0.0,
            confidence=round(confidence, 4), horizon_bars=p.horizon_bars, evidence=evidence,
            metrics=metrics, warnings=warnings, overlays=overlays,
            status="degraded" if problems else "ok",
        )
