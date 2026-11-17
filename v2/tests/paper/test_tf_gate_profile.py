"""T179: la puerta de costo por perfil y marco, con la sombra calibrada con el libro.

El caso que la motiva (corrida t143, 2026-11-17): en 15 m la sombra que el agresivo aceptaría
costaba 0,132 R y su libro pagaba 0,185; el moderado, 0,106 frente a 0,136. Con un solo número
por marco la puerta de T143 no cerraba nada; por perfil, y calibrada, cierra solo al agresivo.
"""

from __future__ import annotations

from dataclasses import replace

from eim.paper import tf_calib as cal
from eim.paper import tf_gate_profile as gp
from eim.paper.engine import Outcome
from eim.paper.params import PROFILES
from eim.paper.t143_config import EXEC_T143
from tests.paper.helpers import H1, T0, idea

EP = EXEC_T143
TFS = EP.timeframes
AGR = next(p for p in PROFILES if p.id == "agresivo")       # veto 0,20 R
MOD = next(p for p in PROFILES if p.id == "moderado")       # veto 0,15 R
SYM = "X"


def out(tf: str, cost: float, sl: float, t: int = T0, iid: str | None = None) -> Outcome:
    """Cerrada en `tf` con costo `cost` en R y el stop en `sl` (entrada 100)."""
    risk = abs(100.0 - sl) / 100.0
    i = replace(idea(sl=sl, t=t, iid=iid), timeframe=tf)
    return Outcome(i, "CERRADA", "SL", t, 100.0, t + 1, sl, fee_in=cost * risk / 2,
                   fee_out=cost * risk / 2)


def row(o: Outcome, profile: str, cost_r: float) -> dict:
    """Una fila del libro fijo que cuenta como resultado (T144), con su costo vivido en R."""
    return {"scope": "perfil", "origin": "vivo", "profile": profile, "weight": 1.0,
            "retro": False, "exit_t": o.exit_t, "r": -1.0, "pnl_usdt": -100.0,
            "fees": cost_r * 100.0, "slip": 0.0, "funding": 0.0, "notional": 10_000.0,
            "idea_id": o.idea.id, "timeframe": o.idea.timeframe}


def _shadow(n: int = 120) -> list[Outcome]:
    """Sombra de 15 m: stops de 0,9 % (solo los acepta el agresivo) y de 1,4 % (los dos)."""
    tight = [out("15m", 0.13, 99.1, T0 + i * H1, f"t{i}") for i in range(n)]
    wide = [out("15m", 0.10, 98.6, T0 + i * H1 + 1, f"w{i}") for i in range(n)]
    return tight + wide


# ---------------------------------------------------------------------------- calibración

def test_el_factor_es_el_cociente_de_lo_vivido_entre_su_gemela_de_la_sombra():
    sh = _shadow()
    rows = [row(o, "agresivo", 0.18) for o in sh[:40]]           # 0,18 vivido frente a 0,13
    f = cal.factors(rows, sh)
    assert f["agresivo@15m"]["n"] == 40
    assert abs(f["agresivo@15m"]["factor"] - 0.18 / 0.13) < 1e-3
    assert cal.factor_for(f, "agresivo", "15m")[1].startswith("propio")


def test_con_pocas_parejas_propias_se_usa_el_del_marco_y_sin_ninguna_uno():
    sh = _shadow()
    rows = [row(o, "agresivo", 0.18) for o in sh[:20]] + [row(o, "moderado", 0.12)
                                                         for o in sh[120:135]]
    f = cal.factors(rows, sh)
    assert "agresivo@15m" not in f and "moderado@15m" not in f and f["*@15m"]["n"] == 35
    assert cal.factor_for(f, "moderado", "15m")[1].startswith("del marco")
    assert cal.factor_for({}, "moderado", "1h") == (1.0, "sin parejas con el libro")


def test_el_factor_esta_acotado_y_no_cuenta_lo_que_no_es_resultado():
    sh = _shadow()
    rows = [row(o, "agresivo", 5.0) for o in sh[:40]]
    assert cal.factors(rows, sh)["agresivo@15m"]["factor"] == cal.BOUNDS[1]
    retro = [r | {"retro": True} for r in rows]
    assert cal.factors(retro, sh) == {}


# ------------------------------------------------------------------------------- decisión

def test_por_perfil_y_calibrada_cierra_15m_solo_para_el_agresivo():
    sh = _shadow()
    fac = {"agresivo@15m": {"factor": 1.25, "n": 41}, "moderado@15m": {"factor": 1.14, "n": 45}}
    rows = {(r["profile"], r["timeframe"]): r for r in gp.decide(TFS, sh, EP, [AGR, MOD], fac)}
    a, m = rows[("agresivo", "15m")], rows[("moderado", "15m")]
    # el agresivo acepta las dos mitades: (0,13 + 0,10) / 2 × 1,25 ≈ 0,144 < 0,15, y abre; con
    # un tercio más de stops pegados pasa de 0,15; el moderado solo acepta las de 1,4 %: 0,10 × 1,14
    assert m["shadow_cost_r"] < a["shadow_cost_r"]
    assert m["admitted"] and abs(m["cost_r"] - 0.10 * 1.14) < 1e-3
    sh_cara = sh + [out("15m", 0.16, 99.15, T0 + i * H1 + 2, f"c{i}") for i in range(120)]
    dec = gp.decide(TFS, sh_cara, EP, [AGR, MOD], fac)
    rows2 = {(r["profile"], r["timeframe"]): r for r in dec}
    assert not rows2[("agresivo", "15m")]["admitted"] and rows2[("moderado", "15m")]["admitted"]


def test_sin_muestra_del_perfil_manda_la_linea_base_de_t136():
    rows = gp.decide(TFS, [out("1h", 0.5, 98.6)], EP, [MOD], {})
    r1h = next(r for r in rows if r["timeframe"] == "1h")
    assert r1h["source"].startswith("T136") and r1h["admitted"]     # 1 h: 0,123 < 0,15
    r15 = next(r for r in rows if r["timeframe"] == "15m")
    assert not r15["admitted"]                                       # 15 m: 0,157 ≥ 0,15


# --------------------------------------------------------- tramos: cerrar no reescribe lo vivido

def test_cerrar_solo_bloquea_las_ideas_posteriores_y_reabrir_no_resucita_el_tramo():
    cerrado = [{"profile": "agresivo", "timeframe": "15m", "admitted": False}]
    abierto = [{"profile": "agresivo", "timeframe": "15m", "admitted": True}]
    antes, durante, despues = (out("15m", 0.1, 99.0, T0 + k * H1, f"i{k}") for k in (0, 5, 9))
    c = gp.update({}, cerrado, SYM, T0 + 3 * H1)
    assert c == {"X|agresivo@15m": [[T0 + 3 * H1, None]]}
    assert gp.update(c, cerrado, SYM, T0 + 4 * H1) == c          # seguir cerrado no abre otro
    c = gp.update(c, abierto, SYM, T0 + 7 * H1)
    t = gp.tradable(c, SYM, [AGR, MOD], [antes, durante, despues])
    assert [o.idea.id for o in t["agresivo"]] == ["i0", "i9"]
    assert len(t["moderado"]) == 3                                 # otro perfil, sin tocar


def test_los_tramos_sobreviven_a_un_reinicio_y_un_archivo_roto_es_nada_cerrado(tmp_path):
    p = tmp_path / "paper" / "tf_gate_t143.json"
    c = {"X|agresivo@15m": [[T0, None]]}
    gp.save(p, c)
    assert gp.load(p) == c
    p.write_text("{a medio", encoding="utf-8")
    assert gp.load(p) == {}
    assert gp.load(tmp_path / "no_existe.json") == {}


def test_t31_no_cambia_la_puerta_por_perfil_esta_apagada_por_defecto():
    from eim.paper.params import ExecParams
    from eim.paper.versioning import exec_fingerprint
    assert ExecParams().tf_gate_by_profile is False and EP.tf_gate_by_profile is True
    # no entra en la huella de la mecánica: la evidencia de la sombra no se parte
    assert exec_fingerprint(ExecParams(), "15m") == exec_fingerprint(
        ExecParams(tf_gate_by_profile=True), "15m")
