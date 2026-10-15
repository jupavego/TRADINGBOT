"""Agente `arbitrage`: expone el motor de oportunidades netas de T38 sobre `snapshot.arb`.

Neutral al mercado: `bias` es SIEMPRE 0 y el agente está excluido de la síntesis direccional
(`SynthesisParams.excluded`; T44 lo prohíbe). Su información va en `metrics`: mejores
oportunidades con costos desglosados, funding actual/próximo por símbolo, base anualizada y
por qué se descartó el resto. `confidence` mide la calidad de la fotografía (frescura,
profundidad del libro y cobertura de las estrategias), no una convicción de mercado.
Modo ANÁLISIS: no envía órdenes (T45).
"""

from __future__ import annotations

from eim.agents.arbitrage.params import ArbAgentParams
from eim.agents.arbitrage.rows import (
    REJECT,
    STRATEGY,
    basis_table,
    funding_table,
    ranked_row,
    rejected_summary,
    scans_summary,
)
from eim.agents.base import no_data_report
from eim.arbitrage.scan import ArbResult, scan_all
from eim.core import AgentReport, ArbMarket, MarketSnapshot

LABEL = "neto estimado, no garantizado"
SCAN_WEIGHT = {"ok": 1.0, "degraded": 0.5, "no_data": 0.0}


class ArbitrageAgent:
    id = "arbitrage"
    version = "1.0.0"
    requires = {"arb"}

    def __init__(self, params: ArbAgentParams | None = None) -> None:
        self.params = params or ArbAgentParams()

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        return self.analyze(snapshot)[1]

    # --- calidad de la fotografía ------------------------------------------
    def _freshness(self, age_s: float) -> float:
        p = self.params
        if age_s <= p.fresh_s:
            return 1.0
        return max(0.0, 1.0 - (age_s - p.fresh_s) / max(p.stale_s - p.fresh_s, 1e-9))

    def _depth(self, mkt: ArbMarket, res: ArbResult) -> tuple[float, dict]:
        """Niveles visibles por libro (respecto de `min_book_levels`) × fracción de
        oportunidades cuyas patas caben en el libro."""
        books = list(mkt.spot_books.values()) + list(mkt.futures_books.values())
        lv = [min(len(b.bids), len(b.asks)) for b in books]
        book_score = (sum(min(1.0, n / self.params.min_book_levels) for n in lv) / len(lv)
                      if lv else 0.0)
        opps = [o for s in res.scans for o in s.opportunities]
        execu = sum(o.executable for o in opps) / len(opps) if opps else 0.0
        liq = max((o.risk.liquidity for o in opps), default=None)
        return book_score * execu, {"books": len(books), "min_levels": min(lv, default=0),
                                    "book_score": round(book_score, 3),
                                    "executable_frac": round(execu, 3),
                                    "max_liquidity_used": liq}

    # --- análisis ----------------------------------------------------------
    def analyze(self, snapshot: MarketSnapshot) -> tuple[ArbResult | None, AgentReport]:
        """Resultado completo del motor (tabla de la API) y reporte del agente."""
        p, mkt = self.params, snapshot.arb
        if mkt is None:
            return None, no_data_report(
                self.id, self.version, snapshot.asof,
                "sin fotografía de arbitraje: el escáner no ha corrido o tiene > 10 min")
        res = scan_all(mkt, p.cost_model, p.engine)
        scan_warns = [f"{STRATEGY[s.strategy]}: falta {m}" for s in res.scans for m in s.missing]
        scan_warns += [f"{STRATEGY[s.strategy]}: {w}" for s in res.scans for w in s.warnings]
        if all(s.status == "no_data" for s in res.scans):
            rep = no_data_report(self.id, self.version, snapshot.asof,
                                 "ninguna estrategia pudo valorarse con la fotografía")
            return res, rep.model_copy(update={"warnings": rep.warnings + scan_warns})
        age_s = max(0.0, (snapshot.asof - mkt.asof) / 1000)
        fresh = self._freshness(age_s)
        depth, depth_info = self._depth(mkt, res)
        cover = sum(SCAN_WEIGHT[s.status] for s in res.scans) / len(res.scans)
        confidence = round(fresh * depth * cover, 4)
        warnings = list(dict.fromkeys(scan_warns))
        if age_s > p.fresh_s:
            warnings.insert(0, f"fotografía de hace {age_s:.0f} s (precios de libro vigentes "
                               f"{p.engine.quote_ttl_s} s): confianza reducida")
        if mkt.errors:
            warnings.append("piezas no cargadas: " + ", ".join(sorted(mkt.errors)))
        degraded = (bool(mkt.errors) or age_s >= p.stale_s
                    or any(s.status != "ok" for s in res.scans))
        metrics = self._metrics(mkt, res, age_s, fresh, depth, depth_info, cover)
        rep = AgentReport(agent_id=self.id, version=self.version, asof=snapshot.asof, bias=0,
                          confidence=confidence, horizon_bars=0,
                          evidence=self._evidence(res, metrics), metrics=metrics,
                          warnings=warnings, status="degraded" if degraded else "ok")
        return res, rep

    def _metrics(self, mkt: ArbMarket, res: ArbResult, age_s: float, fresh: float,
                 depth: float, depth_info: dict, cover: float) -> dict:
        p, cm = self.params, self.params.cost_model
        by_code, rejected = rejected_summary(res)
        n_valued = sum(len(s.opportunities) for s in res.scans)
        return {
            "mode": "ANALISIS", "label": LABEL, "neutral": True,
            "scan_asof": mkt.asof, "age_s": round(age_s, 1),
            "quality": {"freshness": round(fresh, 3), "depth": round(depth, 3),
                        "coverage": round(cover, 3), **depth_info},
            "notional_usd": p.engine.notional_usd,
            "cost_model": {"spot_vip": cm.spot_vip, "futures_vip": cm.futures_vip,
                           "bnb_discount": cm.bnb_discount, "role": cm.role,
                           "source": cm.source},
            "counts": {"valued": n_valued, "selected": len(res.selection.selected),
                       "rejected": len(res.selection.rejected)},
            "best": [ranked_row(r, full=False) for r in res.selection.selected[:p.top_n]],
            "rejected_by_code": by_code, "rejected": rejected,
            "funding": funding_table(mkt, p.funding_hist_n),
            "basis": basis_table(mkt, p.engine.assets),
            "scans": scans_summary(res), "errors": dict(mkt.errors),
            "sources": {"arb": "+".join(sorted(set(mkt.sources.values()))) or "desconocida"},
        }

    @staticmethod
    def _evidence(res: ArbResult, m: dict) -> list[str]:
        ev = ["Neutral al mercado: sesgo 0, fuera de la síntesis direccional; modo Análisis "
              "(no envía órdenes)"]
        best = m["best"]
        if best:
            b = best[0]
            ann = f", {b['annualized']:.2%} anual" if b["annualized"] is not None else ""
            ev.append(f"Mejor: {STRATEGY[b['strategy']]} {b['asset']} ({b['variant']}) — "
                      f"{LABEL} {b['net']:+.2f} USD ({b['net_bps']:+.1f} pb{ann}) sobre "
                      f"{b['capital']:,.0f} USD de capital")
        else:
            ev.append("Ninguna oportunidad supera costos, riesgo y umbrales")
        c = m["counts"]
        why = ", ".join(f"{REJECT[k]}: {v}" for k, v in sorted(
            m["rejected_by_code"].items(), key=lambda kv: -kv[1]))
        ev.append(f"{c['valued']} valoradas · {c['selected']} seleccionadas · "
                  f"{c['rejected']} descartadas" + (f" ({why})" if why else ""))
        fund = [f"{s} {f['predicted']:+.4%}/{f['interval_h']:g} h" for s, f in m["funding"].items()
                if f.get("predicted") is not None and s.endswith("USDT")]
        if fund:
            ev.append("Funding previsto: " + " · ".join(fund))
        return ev
