"""T222: la regla congelada de «¿sale 15 m?» sobre libros sintéticos (sin red ni disco real)."""

from __future__ import annotations

import csv
import importlib.util
import json
import random
from pathlib import Path

import pytest

from eim.analytics import tf_retire as tr
from eim.analytics import tf_retire_report as rep

V2 = Path(__file__).resolve().parents[2]
DAY, T0 = tr.DAY_MS, tr.T0_MS


def _row(day: int, tf: str, r: float, k: int, **kw) -> dict:
    opened = T0 + day * DAY + 3_600_000 + k * 1000
    base = {"ledger_id": f"perfil|moderado|BTCUSDT|{tf}:{day}:{k}", "scope": "perfil",
            "profile": "moderado", "symbol": "BTCUSDT", "idea_id": f"{tf}:{day}:{k}",
            "timeframe": tf, "origin": "vivo", "weight": 1.0, "retro": False,
            "opened_t": opened, "fill_t": opened, "exit_t": opened + 1_800_000, "r": r,
            "pnl_usdt": r * 10.0, "fees": 0.6, "slip": 0.4, "funding": 0.0,
            "notional": 1000.0, "kind": "market", "reason": "SLD"}
    return {**base, **kw}


def _book(days: range, mu15: float, mu_rest: float, per_day: int = 8, sd: float = 0.3,
          seed: int = 1) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for d in days:
        for k in range(per_day):
            out.append(_row(d, "15m", mu15 + rng.gauss(0, sd), k))
            out.append(_row(d, "1h" if k % 2 else "4h", mu_rest + rng.gauss(0, sd), 100 + k))
    return out


def test_la_huella_del_bloque_congelado_no_cambia():
    text = (V2.parent / "PLAN" / "T222.md").read_text(encoding="utf-8")
    assert tr.prereg_fingerprint(text) == tr.PREREG_SHA256


def test_umbral_de_holm_con_la_familia_del_dia():
    assert tr.z_crit(1142) == pytest.approx(4.087, abs=1e-3)
    assert tr.z_crit(2000) > tr.z_crit(1142)
    with pytest.raises(ValueError):
        tr.z_crit(1141)


def test_no_se_calcula_antes_de_la_fecha():
    with pytest.raises(PermissionError):
        tr.guard(1, tr.LOOKS_MS[1] - 1)
    tr.guard(1, tr.LOOKS_MS[1])
    with pytest.raises(ValueError):
        tr.guard(3, tr.LOOKS_MS[2])


def test_solo_cuenta_lo_abierto_en_el_tramo_y_cerrado_antes_de_la_mirada():
    ok = _row(1, "15m", -0.5, 0)
    rows = [ok,
            _row(-1, "15m", -0.5, 1),                                   # abierta antes de T0
            _row(1, "15m", -0.5, 2, exit_t=tr.LOOKS_MS[1] + 1),         # cierra después
            _row(1, "15m", -0.5, 3, retro=True),
            _row(1, "15m", -0.5, 4, symbol="ETHUSDT"),
            _row(1, "15m", -0.5, 5, scope="sombra"),
            _row(1, "1d", -0.5, 6),
            _row(1, "15m", -0.5, 7, weight=0.0)]
    assert [r["ledger_id"] for r in tr.measured(rows, 1)] == [ok["ledger_id"]]


def test_error_tipico_por_dia_a_mano():
    rows = [_row(0, "15m", -1.0, 0), _row(0, "15m", 0.5, 1), _row(1, "15m", -1.0, 2),
            _row(0, "1h", 1.0, 3), _row(1, "4h", 0.0, 4), _row(1, "1h", 1.0, 5)]
    e = tr.estimate(rows)
    assert (e.n15, e.n_rest, e.days) == (3, 3, 2)
    assert e.mu15 == pytest.approx(-0.5)
    assert e.mu_rest == pytest.approx(2 / 3)
    assert e.delta == pytest.approx(-7 / 6)
    assert e.se15 == pytest.approx(1 / 3)          # e_d = ±1/6, D/(D−1) = 2
    assert e.se_delta == pytest.approx(1 / 9)      # e_d = ±1/18


def test_15m_claramente_peor_pasa_en_la_primera_mirada():
    v = tr.verdict(_book(range(91), -0.30, 0.05), 1, 1142)
    assert v["minimum_met"] and v["status"] == tr.PASS
    assert all(v["checks"].values())


def test_15m_igual_que_el_resto_para_por_futilidad():
    rows = []
    for d in range(91):
        for k in range(8):
            x = -0.1 + 0.05 * ((d + k) % 5)
            rows += [_row(d, "15m", x, k), _row(d, "1h", x, 100 + k)]
    v = tr.verdict(rows, 1, 1142)
    assert v["estimate"]["delta"] == pytest.approx(0.0, abs=1e-12)
    assert v["status"] == tr.FAIL and "futilidad" in v["why"]


def test_sin_el_minimo_la_primera_queda_en_curso_y_la_segunda_decide():
    rows = _book(range(30), -0.30, 0.05, per_day=3)
    assert tr.verdict(rows, 1, 1142)["status"] == tr.OPEN
    assert tr.verdict(rows, 2, 1142)["status"] in (tr.PASS, tr.FAIL)
    assert tr.verdict([], 2, 1142)["status"] == tr.FAIL


def test_un_regimen_nuevo_de_signo_contrario_impide_pasar():
    rows = _book(range(150), -0.40, 0.05, seed=2) + _book(range(150, 180), 0.30, 0.05, seed=3)
    assert tr.verdict(rows, 2, 1142)["status"] == tr.PASS
    change = T0 + 150 * DAY
    v = tr.verdict(rows, 2, 1142, changes=[change])
    assert v["regime"]["applies"] and v["regime"]["last_change_ms"] == change
    assert not v["checks"]["regime"] and v["status"] == tr.FAIL
    # un cambio fuera de la ventana no cuenta
    assert tr.verdict(rows, 2, 1142, changes=[T0 - 1])["regime"]["last_change_ms"] is None


def test_mitades_con_d_impar_dejan_fuera_el_dia_central():
    rows = [_row(d, tf, -0.1, k) for d in range(3) for k, tf in enumerate(("15m", "1h"))]
    h1, h2 = tr.halves(rows)
    assert (h1.days, h2.days) == (1, 1)
    assert (h1.n15, h2.n15) == (1, 1)


def test_rechazos_por_cupo_con_15m_abierta():
    rows = [_row(0, "15m", -0.1, 0, fill_t=T0 + 1000, exit_t=T0 + 5000)]
    ev = {"cat": "rechazada", "code": "cupo", "origin": "vivo", "profile": "moderado"}
    events = [{**ev, "timeframe": "1h", "t": T0 + 2000},                   # cuenta y coincide
              {**ev, "timeframe": "4h", "t": T0 + 6000},                   # sin 15 m abierta
              {**ev, "timeframe": "15m", "t": T0 + 2000},                  # marco que no se mira
              {**ev, "timeframe": "1h", "t": T0 + 2000, "code": "capital"},
              {**ev, "timeframe": "1h", "t": T0 + 2000, "origin": "reconstruido"},
              {**ev, "timeframe": "1h", "t": T0 + 2000, "profile": "agresivo"}]
    c = rep.cupo_blocked(events, rows, 1)
    assert (c["cupo_1h4h"], c["with_15m_open"]) == (3, 1)
    assert c["by_profile"]["agresivo"] == {"cupo_1h4h": 1, "with_15m_open": 0}


def test_bootstrap_descriptivo_reproducible():
    kept = tr.measured(_book(range(20), -0.2, 0.0), 1)
    assert rep.boot_se(kept, reps=300) == rep.boot_se(kept, reps=300)


def _script():
    path = V2 / "scripts" / "t222_marco_15m.py"
    spec = importlib.util.spec_from_file_location("t222_script", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_el_script_no_mira_antes_de_tiempo_ni_reescribe(tmp_path):
    rows = _book(range(10), -0.3, 0.0, per_day=2)
    path = tmp_path / "ledger.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    out = tmp_path / "t222"
    args = ["--look", "1", "--family", "1142", "--csv", str(path), "--out", str(out)]
    mod = _script()
    with pytest.raises(PermissionError):
        mod.main(args, now_ms=tr.LOOKS_MS[1] - 1)
    assert not out.with_suffix(".json").exists()
    assert mod.main(args, now_ms=tr.LOOKS_MS[1]) == 0
    saved = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert saved["looks"]["1"]["verdict"]["status"] == tr.OPEN
    assert "Mirada 1" in out.with_suffix(".md").read_text(encoding="utf-8")
    assert mod.main(args, now_ms=tr.LOOKS_MS[1]) == 2              # el primero no se revisa
