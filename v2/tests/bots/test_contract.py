"""Contrato `BotSignal` y fichas tipadas (T57): un bot solo puede emitir una postura."""

import pytest
from pydantic import ValidationError

from eim.bots.card import BotCard, card_of, default_cards, load_cards
from eim.core import BotQuality, BotSignal

SHA = "9af100d6822da7d2d0291a906c730ef172284ee2"
VER = f"{SHA}+0123456789ab"


def make(**kw) -> BotSignal:
    base = dict(bot_id="b", strategy="s", version=VER, asof=2000, timeframe="1h",
                symbol="ETHUSDT", stance=1.0, data_quality=BotQuality(bars=10, last_candle_t=1000))
    return BotSignal(**(base | kw))


@pytest.mark.parametrize("field", ["order", "side", "size", "qty", "leverage", "api_key",
                                   "execution_authorized", "stop_loss", "take_profit"])
def test_contract_rejects_order_fields(field):
    with pytest.raises(ValidationError):
        make(**{field: 1})


def test_contract_has_no_order_size_or_key_fields():
    forbidden = {"order", "orders", "size", "qty", "quantity", "leverage", "api_key", "secret",
                 "execution_authorized", "sl", "tp"}
    assert not forbidden & set(BotSignal.model_fields)
    assert not forbidden & set(BotQuality.model_fields)


def test_stance_confidence_and_version_are_validated():
    assert make(confidence=None).confidence is None      # no se inventa
    for bad in (dict(stance=1.5), dict(stance=-1.1), dict(confidence=1.2), dict(version="v1"),
                dict(horizon_bars=0)):
        with pytest.raises(ValidationError):
            make(**bad)


def test_signal_cannot_use_candles_after_its_asof():
    with pytest.raises(ValidationError):
        make(asof=999, data_quality=BotQuality(bars=1, last_candle_t=1000))


def test_no_data_means_flat_and_without_confidence():
    make(stance=0.0, status="no_data")
    for bad in (dict(stance=1.0), dict(confidence=0.5, stance=0.0)):
        with pytest.raises(ValidationError):
            make(status="no_data", **bad)


def test_signal_is_immutable():
    with pytest.raises(ValidationError):
        make().stance = -1.0


def test_catalog_cards_load_validated():
    cards = default_cards()
    assert len(cards) >= 45 and all(isinstance(c, BotCard) for c in cards.values())
    assert {k for k, c in cards.items() if c.usable} == {
        "hummingbot-directional", "freqtrade", "freqtrade-strategies", "passivbot",
        "nostalgia-for-infinity", "jesse-example-strategies", "trendrider-strategy"}
    assert card_of("hummingbot-directional").integration_mode == "A"
    assert card_of("freqtrade-strategies").integration_mode == "B"
    with pytest.raises(KeyError):
        card_of("no-existe")


def test_card_with_extra_or_inconsistent_fields_is_rejected(tmp_path):
    import json
    src = card_of("hummingbot-directional").model_dump()
    (tmp_path / "hummingbot-directional.json").write_text(json.dumps({**src, "extra": 1}))
    with pytest.raises(ValidationError):
        load_cards(tmp_path)
    bad = {**src, "security": {**src["security"], "enabled": False}}
    (tmp_path / "hummingbot-directional.json").write_text(json.dumps(bad))
    with pytest.raises(ValidationError):
        load_cards(tmp_path)
    (tmp_path / "otro.json").write_text(json.dumps(src))
    (tmp_path / "hummingbot-directional.json").unlink()
    with pytest.raises(ValueError):
        load_cards(tmp_path)
