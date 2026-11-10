"""T64: la lista de vigilancia es inmutable, versionada y con hash."""

import pytest
from pydantic import ValidationError

from eim.video import watchlist as W


def test_v1_loads_with_hash_and_is_frozen():
    wl = W.load("watchlist_v1")
    assert wl.version == "v1" and len(wl.hash) == 64
    assert 3 <= len(wl.channels) <= 5
    assert all(c.permission == "ninguno" and not c.verified for c in wl.channels)
    assert {t.asset for t in wl.topics if t.asset} == {"BTC", "ETH"}
    with pytest.raises(ValidationError):
        wl.threshold = 0.1
    assert W.load("watchlist_v1").hash == wl.hash


def test_v2_is_the_default_with_verified_ids_and_no_permission():
    wl, v1 = W.load(), W.load("watchlist_v1")
    assert wl.version == "v2" and wl.hash != v1.hash
    assert [c.channel_id for c in wl.channels] == [c.channel_id for c in v1.channels]
    assert all(c.verified and c.permission == "ninguno" for c in wl.channels)
    assert wl.budget.backfill_max_pages == 40


def test_invalid_lists_are_rejected():
    raw = W.load().model_dump(exclude={"hash"})
    with pytest.raises(ValidationError):
        W.Watchlist.model_validate(raw | {"channels": [raw["channels"][0]] * 2})
    with pytest.raises(ValidationError):
        W.Watchlist.model_validate(raw | {"weights": {"topic": 0.5, "freshness": 0.5,
                                                      "priority": 0.5}})
    with pytest.raises(ValidationError):
        W.Watchlist.model_validate(raw | {"duration_min_s": 99_999})
