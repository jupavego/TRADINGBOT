"""La sesión americana de la forja (T208): horario de verano, festivos y cuándo se puede operar."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from eim.forge import session
from tests.forge.conftest import TF, make_series


def _at(s, t_iso: str) -> int:
    t = int(datetime.fromisoformat(t_iso).replace(tzinfo=UTC).timestamp() * 1000)
    i = int(np.searchsorted(s.t, t))
    assert s.t[i] == t, t_iso
    return i


def test_horario_de_verano():
    """09:30 ET son 13:30 UTC en verano y 14:30 UTC en invierno: la máscara lo resuelve sola."""
    ver = make_series(days=4, start="2026-07-06")
    inv = make_series(days=4, start="2026-01-05")
    sv, si = session.build(ver.t), session.build(inv.t)
    assert sv.sid[_at(ver, "2026-07-06T13:30")] >= 0
    assert sv.sid[_at(ver, "2026-07-06T13:25")] < 0
    assert sv.sid[_at(ver, "2026-07-06T19:55")] >= 0
    assert sv.sid[_at(ver, "2026-07-06T20:00")] < 0
    assert si.sid[_at(inv, "2026-01-05T13:30")] < 0
    assert si.sid[_at(inv, "2026-01-05T14:30")] >= 0
    assert si.sid[_at(inv, "2026-01-05T20:55")] >= 0
    assert si.sid[_at(inv, "2026-01-05T21:00")] < 0


def test_78_velas_por_sesion(serie, sesiones):
    largos = np.bincount(sesiones.sid[sesiones.sid >= 0])
    assert set(largos.tolist()) == {78}


def test_fuera_fines_de_semana_festivos_y_medias_sesiones():
    s = make_series(days=12, start="2026-11-23")        # incluye el jueves 26 (festivo de NYSE)
    ss = session.build(s.t)
    assert ss.dates                                     # hay sesiones
    assert "2026-11-26" not in ss.dates                 # Acción de Gracias
    assert "2026-11-27" not in ss.dates                 # media sesión (cierre 13:00 ET)
    assert "2026-11-28" not in ss.dates and "2026-11-29" not in ss.dates   # fin de semana
    assert "2026-11-24" in ss.dates and "2026-11-30" in ss.dates


def test_cuando_se_puede_senalar(serie, sesiones):
    i0 = _at(serie, "2026-03-02T14:30")                 # 09:30 ET (invierno)
    assert sesiones.sid[i0] >= 0
    assert not sesiones.can_signal[i0]                  # la primera vela no dispara
    assert sesiones.can_signal[i0 + 1]                  # 09:35 sí
    assert sesiones.can_signal[_at(serie, "2026-03-02T19:55")]   # 14:55 ET
    assert not sesiones.can_signal[_at(serie, "2026-03-02T20:00")]   # 15:00 ET: ya no
    assert not sesiones.can_signal[_at(serie, "2026-03-02T20:50")]


def test_cierre_forzoso_es_la_ultima_vela(serie, sesiones):
    i = _at(serie, "2026-03-02T14:30")
    last = int(sesiones.last[i])
    assert serie.t[last] == serie.t[i] + 77 * TF        # 15:55 ET
    assert sesiones.sid[last + 1] != sesiones.sid[i]
