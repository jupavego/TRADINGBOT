"""T151: el catálogo versionado cumple lo prometido (≈100 obras verificadas, sin duplicados)."""

from __future__ import annotations

from collections import Counter

from eim.data.library import Registry
from eim.data.library_digital import load_cards, load_catalog, load_seed
from eim.library.bm25 import fold
from eim.library.digital.schema import CATEGORY_NAMES
from eim.library.digital.taxonomy import CONCEPTS


def test_seed_size_categories_and_ids():
    seed = load_seed()
    assert 95 <= len(seed) <= 130
    assert len({s.id for s in seed}) == len(seed)
    per_cat = Counter(s.curated.category for s in seed)
    assert set(per_cat) == set(CATEGORY_NAMES)
    assert min(per_cat.values()) >= 8, per_cat


def test_concepts_and_stances_use_the_taxonomy():
    for s in load_seed():
        assert all(c in CONCEPTS for c in s.curated.concepts), s.id
        assert all(x.concept in CONCEPTS for x in s.curated.stances), s.id


def test_no_duplicate_works_and_none_from_local_library():
    refs = load_catalog()
    keys = [s.locator.doi or s.locator.arxiv or s.locator.url for s in refs]
    assert len(set(keys)) == len(keys)
    local = {fold(b.title) for b in Registry.load().books.values()}
    titles = [fold(r.verified.title) for r in refs if r.verified]
    assert not local & set(titles)
    assert len(set(titles)) == len(titles)


def test_every_ref_verified_with_link_date_and_honest_access():
    refs = load_catalog()
    assert len(refs) == len(load_seed())
    for r in refs:
        assert r.ok, (r.id, r.problem)
        v = r.verified
        assert v.url.startswith("http") and v.verified_at
        if v.access == "suscripcion":
            assert v.availability != "texto_completo" and v.oa_url is None, r.id
        if v.availability == "texto_completo":
            assert v.oa_url, r.id


def test_cards_never_claim_more_than_was_read():
    refs = {r.id: r for r in load_catalog()}
    for rid, c in load_cards().items():
        assert rid in refs
        if c.coverage == "metadatos":
            assert not c.findings and not c.stances_verified
        for f in c.findings + c.limitations:
            assert len(f.text.split()) <= 25 and f.where == c.coverage
        assert set(c.stances_verified) <= {s.concept for s in refs[rid].curated.stances}
        assert c.level != "validada_eim"
