"""Expedientes de la cantera (T167): forma, presupuesto y reglas de la casa, sin red.

El contrato pydantic llega con T168; mientras tanto, esta prueba fija lo que T167 promete:
19 agentes con expediente o motivo, 2–4 prospectos con hermano simple, ≤ 3 parámetros citados,
obras que existen en el catálogo T151 y ningún rendimiento calculado.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "eim"
DOSSIERS = ROOT / "nursery" / "dossiers"
AGENTS = sorted(p.name for p in (ROOT / "agents").iterdir()
                if p.is_dir() and (p / "agent.py").exists())
CATALOG = {r["id"] for r in json.loads(
    (ROOT / "library" / "digital" / "catalog.json").read_text(encoding="utf-8"))["refs"]}
EXITS = {"atr_ladder", "rule_flip", "mean_target", "time_stop"}
EXAMS = {"banco_t131", "senales_guardadas", "solo_adelante"}
TIMEFRAMES = {"15m", "1h", "4h"}
# Banda de horizonte → marcos admitidos (nota §3, «Horizontes»).
HORIZONS = {"scalping": {"15m"}, "intradia": {"15m", "1h"}, "tres_dias": {"1h", "4h"},
            "semanal": {"4h"}}
# Palabras de rendimiento que un expediente no puede contener como clave (T167: sin rendimiento).
PERF_KEYS = {"pnl", "sharpe", "win_rate", "hit_rate", "profit_factor", "mean_r", "net_r",
             "return_pct", "equity", "drawdown"}
CEILING = 50


def _load() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in DOSSIERS.glob("*.json")}


def _keys(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _keys(v)}
    return set()


def test_every_agent_has_a_dossier():
    docs = _load()
    assert sorted(docs) == AGENTS
    for aid, d in docs.items():
        assert d["agent_id"] == aid and d["performance_computed"] is False
        assert d["status"] in {"inscrito", "excluido", "control"}
        if d["status"] == "inscrito":
            assert 2 <= len(d["prospects"]) <= 4, aid
        else:
            assert not d["prospects"] and d["exclusion_reason"], aid


def test_no_performance_fields():
    for aid, d in _load().items():
        assert not (_keys(d) & PERF_KEYS), aid


@pytest.mark.parametrize("aid", [a for a, d in _load().items() if d["status"] == "inscrito"])
def test_prospects_follow_house_rules(aid):
    d = _load()[aid]
    declared = {v["name"] for v in d["variables"]}
    ids = {p["id"] for p in d["prospects"]}
    bases = [p for p in d["prospects"] if p["role"] == "base"]
    assert len(bases) == 1 and bases[0]["n_params"] <= 2, "un hermano simple de 1–2 parámetros"
    for p in d["prospects"]:
        assert p["role"] in {"base", "candidato"}
        assert 1 <= p["n_params"] == len(p["params"]) <= 3, p["id"]
        assert all(v["source"].strip() for v in p["params"].values()), "parámetro sin cita"
        assert set(p["variables"]) <= declared, f"{p['id']} lee variables no declaradas"
        assert p["exit_template"] in EXITS and p["history_exam"] in EXAMS
        assert p["timeframe"] in TIMEFRAMES
        assert p["timeframe"] in HORIZONS[p["horizon"]], f"{p['id']}: marco fuera de su banda"
        assert p["horizon"] != "scalping" or p.get("max_bars"), "scalping sin tope de velas"
        assert p["opposite_of"] is None or p["opposite_of"] in ids
        assert set(p["literature"]) <= CATALOG, f"{p['id']} cita obras fuera del catálogo"
    assert {e["id"] for e in d["literature"]} <= CATALOG


def test_family_fits_the_ceiling():
    prospects = [p for d in _load().values() for p in d["prospects"]]
    assert len({p["id"] for p in prospects}) == len(prospects), "ids de prospecto repetidos"
    assert len(prospects) <= CEILING


def test_every_horizon_band_is_present():
    bands = {p["horizon"] for d in _load().values() for p in d["prospects"]}
    assert bands == set(HORIZONS), "la cantera cubre de scalping a semanal (pedido del usuario)"
