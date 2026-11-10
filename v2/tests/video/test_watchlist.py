"""T64: la lista de vigilancia es inmutable, versionada y con hash."""

import pytest
from pydantic import ValidationError

from eim.video import watchlist as W


def test_v1_loads_with_hash_and_is_frozen():
    wl = W.load()
    assert wl.version == "v1" and len(wl.hash) == 64
    assert 3 <= len(wl.channels) <= 5
    assert all(c.permission == "ninguno" and not c.verified for c in wl.channels)
    assert {t.asset for t in wl.topics if t.asset} == {"BTC", "ETH"}
    with pytest.raises(ValidationError):
        wl.threshold = 0.1
    assert W.load().hash == wl.hash


def test_invalid_lists_are_rejected():
    raw = W.load().model_dump(exclude={"hash"})
    with pytest.raises(ValidationError):
        W.Watchlist.model_validate(raw | {"channels": [raw["channels"][0]] * 2})
    with pytest.raises(ValidationError):
        W.Watchlist.model_validate(raw | {"weights": {"topic": 0.5, "freshness": 0.5,
                                                      "priority": 0.5}})
    with pytest.raises(ValidationError):
        W.Watchlist.model_validate(raw | {"duration_min_s": 99_999})
