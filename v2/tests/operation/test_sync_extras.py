"""El ciclo sincroniza derivados, liquidaciones y titulares a su ritmo, sin que un fallo lo frene."""

from types import SimpleNamespace

from eim.data.store import Store
from eim.operation import cycle as cy


def _fake(tmp_path):
    logs = []
    p = SimpleNamespace(timeframe="1h", history_bars=100)
    log = SimpleNamespace(write=lambda *a, **k: logs.append((a, k)))
    return SimpleNamespace(store=Store(tmp_path), provider=object(), p=p, log=log,
                           _extras_at={}), logs


def test_extras_se_sincronizan_una_vez_por_ventana_y_los_fallos_no_cortan(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cy, "sync_derivatives", lambda *a: calls.append("deriv"))
    monkeypatch.setattr(cy, "sync_liquidations", lambda *a: calls.append("liq"))

    def boom(*a):
        calls.append("news")
        raise OSError("sin red")

    monkeypatch.setattr(cy, "sync_headlines", boom)
    me, logs = _fake(tmp_path)
    cy.OperationCycle._sync_extras(me, "BTCUSDT", 1_000_000)
    assert calls == ["deriv", "liq", "news"] and logs[0][0][0] == "datos_extra_fallidos"
    cy.OperationCycle._sync_extras(me, "BTCUSDT", 1_000_000 + 60_000)  # < 10 min: nada
    assert len(calls) == 3
    cy.OperationCycle._sync_extras(me, "BTCUSDT", 1_000_000 + 601_000)
    assert len(calls) == 6
