"""T95 — el pre-registro de la cantera ya no fija BTCUSDT en el tipo (familias del universo); el
publicado `cantera_v1` sigue siendo BTCUSDT porque lo fija su archivo con huella."""

from __future__ import annotations

from eim.nursery.prereg import Prereg, load_prereg


def test_the_type_no_longer_pins_btc_but_the_published_file_does():
    assert Prereg.model_fields["symbol"].annotation is str
    assert load_prereg().symbol == "BTCUSDT"
