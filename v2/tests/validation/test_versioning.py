"""Versiones de estrategia (T49): huella estable de reglas, parámetros y mecánica."""

from __future__ import annotations

import importlib
import sys
import textwrap

import pytest

from eim.paper import versioning
from eim.paper.catalog import CATALOG, generate_ideas
from eim.paper.params import ExecParams
from tests.paper.helpers import H1
from tests.paper.test_strategies import ctx_for, walk

BASE = '''
LIMIT = {limit}


def helper(x):
    return x * {k}


def rule(ctx, _x, _i):
    """Regla de prueba."""
    {comment}
    return helper(ctx["v"]) > LIMIT
'''


def _load(tmp_path, variant: str, **kw):
    """Carga una variante de la regla como módulo `t49m` (mismo nombre, archivo distinto)."""
    src = BASE.format(limit=kw.get("limit", 1.0), k=kw.get("k", 2), comment=kw.get(
        "comment", "# comentario"))
    if kw.get("reformat"):
        src = src.replace('return helper(ctx["v"]) > LIMIT',
                          'return (helper( ctx[ "v" ] )\n            > LIMIT)')
        src = src.replace('"""Regla de prueba."""', '"""Otra documentación."""')
    d = tmp_path / variant
    d.mkdir()
    (d / "t49m.py").write_text(textwrap.dedent(src), encoding="utf-8")
    sys.modules.pop("t49m", None)
    sys.path.insert(0, str(d))
    try:
        return importlib.import_module("t49m")
    finally:
        sys.path.remove(str(d))
        sys.modules.pop("t49m", None)


@pytest.fixture
def scope(monkeypatch):
    monkeypatch.setattr(versioning, "SCOPES", ("t49m",))


def test_stable_under_comments_docstrings_and_formatting(tmp_path, scope):
    a = _load(tmp_path, "a")
    b = _load(tmp_path, "b", comment="# otro comentario distinto", reformat=True)
    assert versioning.rules_fingerprint(a.rule) == versioning.rules_fingerprint(b.rule)


def test_changes_with_constants_and_helpers(tmp_path, scope):
    a = _load(tmp_path, "a")
    b = _load(tmp_path, "b", limit=1.5)               # parámetro de módulo
    c = _load(tmp_path, "c", k=3)                     # regla en una función auxiliar
    fa = versioning.rules_fingerprint(a.rule)
    assert fa != versioning.rules_fingerprint(b.rule)
    assert fa != versioning.rules_fingerprint(c.rule)


def test_closure_values_are_part_of_the_rules():
    tp1, tp2 = CATALOG["plan_tp1"], CATALOG["plan_tp2"]
    assert versioning.rules_fingerprint(tp1.fn) != versioning.rules_fingerprint(tp2.fn)


def test_catalog_versions_distinct_and_deterministic():
    vs = {(s, tf): i.version(tf) for tf in ("15m", "1h", "4h") for s, i in CATALOG.items()}
    assert len(set(vs.values())) == len(vs) == 3 * len(CATALOG)
    assert all(len(v) == versioning.SHORT for v in vs.values())
    assert vs == {(s, tf): i.version(tf) for (s, tf), i in
                  ((k, CATALOG[k[0]]) for k in vs)}


def test_mechanics_version_per_timeframe():
    info = CATALOG["consenso_sintesis"]
    base = ExecParams()
    cheap = ExecParams(costs=base.costs.model_copy(update={"taker_fee": 0.0004}))
    assert all(info.version(tf, base) != info.version(tf, cheap) for tf in ("15m", "1h", "4h"))
    no_be_1h = ExecParams(be_timeframes=("4h",))      # break-even solo cambia el marco 1 h
    assert info.version("1h", base) != info.version("1h", no_be_1h)
    assert info.version("4h", base) == info.version("4h", no_be_1h)
    assert info.version("15m", base) == info.version("15m", no_be_1h)
    # filtros de perfil / tendencia mayor y la lista de marcos no versionan la estrategia
    other = ExecParams(htf={"1h": ("4h", 10, 30)}, timeframes=("1h",))
    assert info.version("1h", base) == info.version("1h", other)


def test_ideas_carry_their_version():
    cs = walk(600)
    ctxs = [ctx_for(c) for c in cs[450:520]]
    ideas = generate_ideas(ctxs, cs, "X", H1, timeframe="1h")
    assert ideas
    for i in ideas:
        assert i.version == CATALOG[i.strategy].version("1h")
        assert i.vid == f"{i.strategy}@1h@{i.version}" and i.to_json()["version"] == i.version
