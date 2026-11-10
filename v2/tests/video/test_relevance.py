"""T64: puntuación pura, reproducible, con desglose y descarte siempre con motivo."""

import pytest

from eim.video.models import VideoMeta
from eim.video.relevance import REASONS, Candidate, admit, score
from tests.video.helpers import CH, NOW, test_watchlist

H = 3_600_000


def meta(**kw) -> VideoMeta:
    base = dict(video_id="v1", channel_id=CH, title="Bitcoin y la Fed", description="",
                published_at=NOW - 6 * H, duration_s=1500, language="es", source="youtube_api")
    return VideoMeta(**(base | kw))


def test_score_is_reproducible_and_explained():
    wl = test_watchlist()
    a, b = score(meta(), wl, NOW), score(meta(), wl, NOW)
    assert a == b
    assert a.candidate and a.reasons == ()
    bd = a.breakdown
    assert set(bd["tema"]["matched"]) == {"btc", "fed"}
    assert bd["tema"]["value"] == 1.0                     # 0,6 + 0,5 con tope 1
    assert bd["actualidad"]["value"] == pytest.approx(0.5 ** (6 / 72), abs=1e-4)
    assert bd["prioridad"]["value"] == 0.8
    expected = 0.5 * 1.0 + 0.25 * bd["actualidad"]["value"] + 0.25 * 0.8
    assert a.total == pytest.approx(expected, abs=1e-4)
    assert a.est_compute_s == 1500 * wl.budget.compute_ratio


def test_description_only_counts_half_and_words_are_whole():
    wl = test_watchlist()
    s = score(meta(title="Resumen semanal", description="hablamos de ethereum"), wl, NOW)
    assert s.breakdown["tema"]["matched"]["eth"] == {"where": "descripcion",
                                                     "keywords": ["ethereum"], "points": 0.3}
    none = score(meta(title="Together with the method", description=""), wl, NOW)
    assert none.breakdown["tema"]["value"] == 0 and "sin_tema" in none.reasons


@pytest.mark.parametrize(("kw", "reason"), [
    ({"duration_s": 58}, "corto"),
    ({"duration_s": 20_000}, "largo"),
    ({"duration_s": None}, "sin_duracion"),
    ({"live": "upcoming"}, "en_vivo"),
    ({"language": "fr"}, "idioma"),
    ({"title": "Receta de arepas"}, "sin_tema"),
    ({"published_at": NOW + H}, "futuro"),
    ({"channel_id": "UCzzzzzzzzzzzzzzzzzzzzzz"}, "canal_fuera"),
])
def test_every_discard_has_a_reason(kw, reason):
    s = score(meta(**kw), test_watchlist(), NOW)
    assert not s.candidate and reason in s.reasons and reason in REASONS


def test_low_score_and_no_permission_are_reasons():
    wl = test_watchlist(permission="ninguno")
    s = score(meta(published_at=NOW - 30 * 24 * H, title="ETH", description=""), wl, NOW)
    assert "sin_permiso" in s.reasons
    low = score(meta(published_at=NOW - 30 * 24 * H, title="Resumen", description="liquidez"),
                test_watchlist(), NOW)
    assert low.reasons == ("bajo_umbral",)


def test_historical_mode_does_not_penalise_age_and_infers_language():
    wl = test_watchlist()
    s = score(meta(published_at=NOW - 400 * 24 * H, language=None), wl, NOW, "historico")
    assert s.breakdown["actualidad"]["value"] == 1.0 and s.candidate
    assert "idioma inferido del canal (es)" in s.notes


def test_admit_never_exceeds_the_daily_cap():
    wl = test_watchlist(compute_hours_per_day=1.0)     # 3600 s
    cands = [Candidate("a", 0.9, 1, 3000), Candidate("b", 0.8, 2, 1000),
             Candidate("c", 0.7, 3, 500), Candidate("d", 0.6, 4, 200)]
    inside, outside = admit(cands, used_s=0, wl=wl)
    assert inside == ["a", "c"] and outside == ["b", "d"]   # 3000+500; 1000 y 200 no caben
    assert admit(cands, used_s=3600, wl=wl) == ([], ["a", "b", "c", "d"])
