"""T169: el plan de muestreo es el declarado en la ficha y queda congelado."""

from __future__ import annotations

from pathlib import Path

import pytest

from eim.nursery.exam import plan
from eim.nursery.prospect import load_prospects

H1, M15, H4 = 3_600_000, 900_000, 4 * 3_600_000
LAST = {"4h": 1_793_721_600_000, "1h": 1_793_728_800_000, "15m": 1_793_728_800_000}  # banco T131


def test_epoch_is_april_2023_and_blocks_are_aligned() -> None:
    assert plan.EPOCH_MS == 1_680_307_200_000          # 2023-04-01T00:00Z
    for k in (0, 7, 45):
        assert plan.block_of(plan.block_start(k)) == k
        assert plan.block_of(plan.block_start(k + 1) - 1) == k


def test_one_block_in_three_over_the_bank() -> None:
    ks = plan.sampled_blocks(LAST["1h"])
    assert ks == list(range(0, 46, 3)) and len(ks) == 16


def test_stretches_match_the_declared_sizes() -> None:
    ss = plan.stretches(LAST)
    assert len(ss["1h"]) == len(ss["15m"]) == 16 and len(ss["4h"]) == 1
    assert {len(s.asofs()) for s in ss["1h"]} == {28 * 24}
    assert {len(s.asofs()) for s in ss["15m"]} == {14 * 96}
    a4 = ss["4h"][0].asofs()
    assert a4[0] == plan.EPOCH_MS + H4 and a4[-1] == LAST["4h"]
    assert all(s.start == plan.block_start(s.block) for s in ss["1h"] + ss["15m"])
    first = ss["1h"][0].asofs()
    assert first[0] == plan.EPOCH_MS + H1 and first[-1] == plan.block_start(1)


def test_32_of_43_prospects_have_history() -> None:
    ps = load_prospects()
    hist = plan.with_history(ps)
    assert len(ps) == 43 and len(hist) == 32
    assert {p.agent_id for p in ps} - {p.agent_id for p in hist} == plan.HISTORYLESS
    agents = plan.agents_by_tf(ps)
    assert agents["15m"] == ["vwap"]
    assert not set().union(*map(set, agents.values())) & plan.HISTORYLESS


def _plan(tmp: Path) -> dict:
    (tmp / "candles").mkdir(parents=True)
    (tmp / "candles" / "data.parquet").write_bytes(b"x")
    return plan.build(load_prospects(), LAST, tmp, plan.bank_files(tmp))


def test_freeze_is_idempotent_and_refuses_another_window(tmp_path: Path) -> None:
    pl = _plan(tmp_path / "banco")
    f = tmp_path / "plan.json"
    assert plan.freeze(f, pl) == pl
    assert plan.freeze(f, pl) == pl                      # relanzar con la misma ventana
    other = dict(pl, last_asof={**pl["last_asof"], "4h": LAST["4h"] + H4})
    with pytest.raises(ValueError, match="otra ventana"):
        plan.freeze(f, other)
    st = plan.stretches_of(pl)
    assert [s.block for s in st["1h"]] == list(range(0, 46, 3))
    assert len(pl["prospects"]) == 32 and len(pl["without_history"]) == 11
