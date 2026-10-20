"""Conexión del analizador LLM al registro: opt-in por clave, caché y presupuesto diario."""

from eim.agents.registry import default_registry
from eim.core import NewsItem
from eim.data.providers.claude_context import (
    CachedContextAnalyzer,
    ClaudeContextAnalyzer,
    CostGuard,
    make_context_analyzer,
)

DAY = 86_400


def _items(*ids):
    return [NewsItem(id=i, t=1, title=f"t {i}", source="S") for i in ids]


class _Inner(ClaudeContextAnalyzer):
    def __init__(self, out):
        super().__init__(api_key="k", guard=CostGuard(0.02))
        self.out, self.calls = out, 0

    def __call__(self, items):
        self.calls += 1
        return self.out


def test_sin_clave_no_hay_analizador_y_con_clave_si(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert make_context_analyzer() is None
    assert default_registry().get("context").analyzer is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert isinstance(default_registry().get("context").analyzer, CachedContextAnalyzer)


def test_mismos_titulares_no_repiten_la_llamada_y_los_fallos_se_reintentan():
    t = [0.0]
    inner = _Inner({"ok": 1})
    a = CachedContextAnalyzer(inner, clock=lambda: t[0])
    a(_items("a", "b")); a(_items("b", "a"))  # noqa: E702 - mismo conjunto, otro orden
    assert inner.calls == 1
    a(_items("c"))
    assert inner.calls == 2
    inner.out = None
    a(_items("d")); a(_items("d"))  # noqa: E702 - None no se cachea
    assert inner.calls == 4


def test_presupuesto_se_reinicia_cada_dia_utc():
    t = [0.0]
    inner = _Inner(None)
    inner.guard.spent = 1.0
    a = CachedContextAnalyzer(inner, clock=lambda: t[0])
    a(_items("a"))
    assert inner.guard.spent == 1.0
    t[0] = DAY + 1
    a(_items("a"))
    assert inner.guard.spent == 0.0


def test_segundo_plano_no_bloquea_y_entrega_cuando_termina():
    import threading

    gate = threading.Event()

    class Slow(_Inner):
        def __call__(self, items):
            gate.wait(5)
            return super().__call__(items)

    t = [0.0]
    inner = Slow({"ok": 1})
    a = CachedContextAnalyzer(inner, clock=lambda: t[0], background=True)
    assert a(_items("a")) is None  # no espera al LLM
    assert a(_items("a")) is None and inner.calls == 0  # una sola llamada en vuelo
    gate.set()
    a._thread.join(5)
    assert a(_items("a")) == {"ok": 1} and inner.calls == 1
    t[0] = 7 * 3600  # titulares nuevos: sirve el último vigente solo dentro del TTL
    assert a(_items("b")) is None
