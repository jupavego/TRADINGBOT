"""Agente `technical`: confluencia de indicadores (catálogo T34), sin redundancia y multi-marco."""

from __future__ import annotations

import math

import numpy as np

from eim.agents.base import no_data_report
from eim.agents.technical.frame import FrameResult, analyze, neighbors, resample
from eim.agents.technical.params import FAMILIES, REGIMES, TechnicalParams
from eim.agents.technical.rules import NO_VOTE, RULES, Rule
from eim.core import AgentReport, MarketSnapshot, Overlay

_FAM_LABEL = {"tendencia": "Tendencia", "momentum": "Momentum", "volatilidad": "Volatilidad",
              "volumen": "Volumen", "flujo": "Flujo"}


def _num(x: float) -> float | None:
    return None if x is None or math.isnan(x) else round(float(x), 4)


def _sign(b: float, neutral: float) -> int:
    return 0 if abs(b) < neutral else (1 if b > 0 else -1)


class TechnicalAgent:
    id = "technical"
    version = "0.1.0"
    requires = {"candles"}

    def __init__(self, params: TechnicalParams | None = None,
                 rules: dict[str, Rule] | None = None) -> None:
        self.params = params or TechnicalParams()
        self.rules = rules if rules is not None else RULES

    # --- multi-marco -----------------------------------------------------------------------
    def _frames(self, snap: MarketSnapshot) -> tuple[dict[str, dict], list[str]]:
        p = self.params
        lower, upper = neighbors(snap.timeframe, p)
        extra = snap.candles_tf or {}
        frames: dict[str, dict] = {}
        notes: list[str] = []
        for tf in (lower, upper):
            if tf is None:
                continue
            cs, src = extra.get(tf) or [], f"velas {tf} del snapshot"
            if len(cs) < p.min_bars and tf == upper:
                cs = resample(snap.candles, p.tf_minutes[tf] * 60_000)
                src = f"agregado desde {snap.timeframe} (velas completas)"
            if len(cs) < p.min_bars:
                notes.append(f"marco {tf}: {len(cs)} velas (< {p.min_bars}), no se evalúa")
                continue
            b = float(analyze(cs, p, self.rules).bias[-1])
            if not math.isnan(b):
                frames[tf] = {"bias": round(b, 4), "source": src, "bars": len(cs)}
        return frames, notes

    def _agreement(self, base: float, frames: dict[str, dict]) -> float | None:
        if not frames:
            return None
        nb = self.params.mtf_neutral
        s0 = _sign(base, nb)
        scores = []
        for f in frames.values():
            s = _sign(f["bias"], nb)
            scores.append(1.0 if s == s0 else (0.5 if 0 in (s, s0) else 0.0))
        return float(np.mean(scores))

    # --- evidencia y overlays -----------------------------------------------------------------
    def _families(self, fr: FrameResult, weights: dict[str, float]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for fam in FAMILIES:
            ids = [k for k, r in self.rules.items() if r.family == fam]
            rules = sorted(
                ({"id": k, "vote": _num(fr.votes[k][-1]), "info": fr.info[k],
                  "duplicate_of": fr.plan.duplicates.get(k)} for k in ids),
                key=lambda r: -1 if r["vote"] is None else abs(r["vote"]), reverse=True)
            v = fr.families.get(fam)
            out[fam] = {"vote": None if v is None else _num(v[-1]), "weight": weights[fam],
                        "clusters": fr.plan.clusters.get(fam, []), "rules": rules}
        return out

    def _overlays(self, fr: FrameResult, t: int, conf: float, src: str) -> list[Overlay]:
        b, sar, st = fr.ctx.ind("BOLL"), fr.ctx.ind("SAR")["sar"], fr.ctx.ind("SUPER")["st"]
        levels = [("boll:up", "BOLL sup.", b["up"][-1]), ("boll:mb", "BOLL media", b["mb"][-1]),
                  ("boll:dn", "BOLL inf.", b["dn"][-1]), ("sar", "SAR", sar[-1]),
                  ("super", "SuperTrend", st[-1])]
        return [Overlay(id=f"technical:{k}", agent_id=self.id, kind="level", t_from=t,
                        geometry={"p": float(p)}, label=label, confidence=conf,
                        evidence=[f"{label} de la última vela cerrada; fuente {src}"])
                for k, label, p in levels if not math.isnan(p)]

    # --- ejecución ----------------------------------------------------------------------------
    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        n = len(snapshot.candles)
        if n < p.min_bars:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  f"velas insuficientes: {n} < {p.min_bars}")
        fr = analyze(snapshot.candles, p, self.rules)
        bias = float(fr.bias[-1])
        if math.isnan(bias):
            return no_data_report(self.id, self.version, snapshot.asof,
                                  "ningún indicador tiene valor en la última vela")
        src = snapshot.sources.get("candles", "desconocida")
        regime = REGIMES[int(fr.regime[-1])]
        weights = p.family_weights[regime]
        fams = self._families(fr, weights)
        live = {f: d["vote"] for f, d in fams.items() if d["vote"] is not None}
        wsum = sum(weights[f] for f in live)
        fam_agree = 1 - sum(weights[f] * abs(v - bias) for f, v in live.items()) / wsum / 2
        coverage = len(live) / len(FAMILIES)
        frames, notes = self._frames(snapshot)
        agree = self._agreement(bias, frames)
        mtf = 1.0 if agree is None else p.mtf_min_factor + (1 - p.mtf_min_factor) * agree
        magnitude = p.conf_floor + (1 - p.conf_floor) * min(1.0, abs(bias) / p.conf_full_bias)
        confidence = max(0.0, min(p.max_confidence, fam_agree * magnitude * coverage * mtf))

        warnings = list(notes)
        missing = [f for f in FAMILIES if f not in live]
        if missing:
            warnings.append(f"familias sin datos: {', '.join(missing)} (p. ej. flujo requiere "
                            f"taker_buy_v); cobertura {len(live)}/{len(FAMILIES)}")
        if n < p.warmup_bars:
            warnings.append(f"solo {n} velas (< {p.warmup_bars}): calentamiento incompleto")
        if agree is None:
            warnings.append("sin otros marcos con datos: acuerdo multi-marco no medido")
        status = "degraded" if (missing or n < p.warmup_bars) else "ok"

        evidence = [f"Régimen {regime}: ADX {_num(fr.adx[-1])}, ancho BOLL en percentil "
                    f"{_num(fr.width_pct[-1])} → pesos {weights}"]
        for fam, d in fams.items():
            if d["vote"] is None:
                continue
            group = {k: i for i, g in enumerate(d["clusters"]) for k in g}
            top, seen = [], set()
            for r in d["rules"]:  # las más fuertes, una por grupo correlado
                g = group.get(r["id"])
                if r["vote"] is None or g is None or g in seen:
                    continue
                seen.add(g)
                same = [k for k in d["clusters"][g] if k != r["id"]]
                top.append(f"{r['id']}{'≈' + '/'.join(same) if same else ''} {r['vote']:+.2f} "
                           f"({r['info']})")
            body = "; ".join(top[:p.evidence_per_family])
            evidence.append(f"{_FAM_LABEL[fam]} {d['vote']:+.2f} (peso {d['weight']}): {body}")
        tf_txt = ", ".join(f"{tf} {f['bias']:+.2f}" for tf, f in frames.items())
        evidence.append(f"Multi-marco: {snapshot.timeframe} {bias:+.2f}"
                        + (f", {tf_txt}; acuerdo {agree:.2f}" if frames else " (único marco)"))

        t_last = snapshot.candles[-1].t
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=bias,
            confidence=confidence, horizon_bars=p.horizon_bars, evidence=evidence,
            metrics={
                "votes": {k: _num(v[-1]) for k, v in fr.votes.items()},
                "families": fams, "duplicates": fr.plan.duplicates, "no_vote": NO_VOTE,
                "regime": {"label": regime, "adx": _num(fr.adx[-1]),
                           "width_pct": _num(fr.width_pct[-1])},
                "family_agreement": round(fam_agree, 4), "family_coverage": coverage,
                "frames": {snapshot.timeframe: {"bias": round(bias, 4), "source": src,
                                                "bars": n}, **frames},
                "mtf_agreement": agree, "bars": n, "source": src,
                "coverage": snapshot.coverage.get("candles"),
            },
            warnings=warnings, overlays=self._overlays(fr, t_last, confidence, src),
            status=status,  # type: ignore[arg-type]
        )
