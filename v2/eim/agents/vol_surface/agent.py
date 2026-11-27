"""Agente `vol_surface` (T214): superficie de volatilidad implícita de BTC. Informante, sin I/O.

Lee del snapshot la última toma de la cadena de opciones de Deribit (T213; nivel 1, solo uso
personal) y describe lo que el mercado de opciones está pagando: σ ATM a 7 y 30 días y su
pendiente, el sesgo 25-delta y 90/110 a 30 días y la prima de varianza frente a la realizada
de las velas del snapshot. Los rasgos salen de `eim/options/surface.py` (puro, versión fijada en
el pre-registro `PLAN/notas/T214_preregistro.md`).

**Nunca vota dirección**: sesgo 0 siempre, y en la síntesis es no direccional (`NON_DIRECTIONAL`)
ni aunque se le diera peso. Corre **en sombra** hasta la evaluación pre-registrada: no entra en el
cono, las bandas ni el tamaño de los stops. Como `intermarket` (T183), nunca devuelve `degraded`:
sin cadena, vieja o incompleta es `no_data` con el motivo, y una toma de calidad «degradada» sale
`ok` con la calidad en las métricas y el aviso escrito. Así el motor de riesgo
(`max_degraded_agents`) y las alertas de agentes no lo cuentan y la corrida de T31 no cambia.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from eim.agents.base import no_data_report
from eim.agents.vol_surface.params import VolSurfaceParams
from eim.core import AgentReport, Candle, MarketSnapshot
from eim.options.realized import realized_vol
from eim.options.surface import SURFACE_VERSION, surface_features

ROLE_NOTE = ("Informante (T214): describe la volatilidad, nunca vota dirección; en sombra hasta "
             "la evaluación pre-registrada (PLAN/notas/T214_preregistro.md).")


def _pct(x: float) -> str:
    return f"{x * 100:.1f} %".replace(".", ",")


def _pts(x: float) -> str:
    return f"{x * 100:+.1f}".replace(".", ",")


class VolSurfaceAgent:
    id = "vol_surface"
    version = "0.1.0"
    requires = {"option_chain"}

    def __init__(self, params: VolSurfaceParams | None = None) -> None:
        self.params = params or VolSurfaceParams()

    def _realized(self, snapshot: MarketSnapshot, days: int) -> float | None:
        """σ realizada (cierre a cierre) con la serie más fina del snapshot que cubra el plazo."""
        series: list[Sequence[Candle]] = [snapshot.candles, *(snapshot.candles_tf or {}).values()]
        for cs in sorted((s for s in series if len(s) > 2), key=lambda s: s[1].t - s[0].t):
            rv = realized_vol([c.t for c in cs], [c.c for c in cs], days, snapshot.asof,
                              self.params.rv_min_coverage)
            if rv is not None:
                return rv
        return None

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p, asof, oc = self.params, snapshot.asof, snapshot.option_chain
        if oc is None or not oc.rows:
            return no_data_report(self.id, self.version, asof,
                                  "sin cadena de opciones en el snapshot (las tomas de Deribit de "
                                  "T213 viven en la portátil, data/options)")
        age_min = (asof - oc.taken_ms) / 60_000
        if age_min < 0:
            return no_data_report(self.id, self.version, asof,
                                  "la toma de opciones es posterior al corte del snapshot")
        if age_min > p.max_age_minutes:
            return no_data_report(self.id, self.version, asof,
                                  f"la última toma de opciones tiene {age_min / 60:.0f} h")
        realized = {d: self._realized(snapshot, d) for d in p.tenors_days}
        f = surface_features([r.model_dump() for r in oc.rows], oc.taken_ms, realized,
                             p.surface())
        if f.status == "no_data":
            return no_data_report(self.id, self.version, asof,
                                  "superficie sin medir: " + "; ".join(f.warnings))
        short, long_ = p.tenors_days
        a_s, a_l = f.atm[short], f.atm[long_]
        assert a_s is not None and a_l is not None and f.term_slope is not None
        shape = ("invertida: el plazo corto paga más (tensión inmediata)" if f.term_slope > 0
                 else "normal: el plazo largo paga más")
        taken = datetime.fromtimestamp(oc.taken_ms / 1000, UTC).strftime("%Y-%m-%d %H:%M UTC")
        evidence = [f"σ implícita ATM: {_pct(a_s)} a {short} días y {_pct(a_l)} a {long_} días; "
                    f"estructura {shape}."]
        if f.rr25 is not None:
            side = ("las puts (protección bajista) cuestan más que las calls" if f.rr25 > 0
                    else "las calls cuestan más que las puts")
            mny = "" if f.skew_90_110 is None else f"; 90/110: {_pts(f.skew_90_110)} puntos"
            evidence.append(f"Sesgo 25Δ a {p.skew_tenor_days} días: {_pts(f.rr25)} puntos, "
                            f"{side}{mny}.")
        for d in p.tenors_days:
            rv, iv = realized.get(d), f.atm[d]
            if rv is not None and iv is not None:
                evidence.append(f"Prima de varianza a {d} días: implícita {_pct(iv)} frente a "
                                f"realizada {_pct(rv)} (cierre a cierre de las velas).")
        evidence.append(f"Fuente: {oc.source}; toma {taken} (hace {age_min:.0f} min), "
                        f"{f.n_rows} opciones en {f.n_expiries} vencimientos; calidad {f.status}.")
        evidence.append(ROLE_NOTE)
        warnings = list(f.warnings)
        if age_min > p.stale_minutes:
            warnings.append(f"toma de hace {age_min:.0f} min (el colector toma cada hora): "
                            "lectura vieja")
        missing = [d for d in p.tenors_days if realized.get(d) is None]
        if missing:
            warnings.append("prima de varianza sin medir a "
                            + ", ".join(f"{d} d" for d in missing)
                            + ": las velas del snapshot no cubren el plazo")
        metrics = {**f.metrics(), "age_min": round(age_min, 1), "source": oc.source,
                   "currency": oc.currency,
                   "realized": {f"{d}d": None if v is None else round(v, 6)
                                for d, v in realized.items()},
                   "role": "informante", "votes": False, "surface_version": SURFACE_VERSION}
        return AgentReport(agent_id=self.id, version=self.version, asof=asof, bias=0.0,
                           confidence=1.0 if f.status == "ok" else 0.5, horizon_bars=0,
                           evidence=evidence, metrics=metrics, warnings=warnings, status="ok")
