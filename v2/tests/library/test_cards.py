"""Guardas sobre las fichas versionadas (`eim/library/cards/`) y sobre el repositorio (T52).

No necesitan los libros: validan contra el registro versionado `eim/library/books.json`.
La comprobación contra el texto de los libros es `python -m eim.library verify` (local).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from eim.data.library import CARDS_DIR, Registry, load_card_files, load_cards
from eim.library.schema import MAX_CLAIM_CHARS, MAX_QUOTE_WORDS

V2 = Path(__file__).resolve().parents[2]


def test_all_cards_pass_the_guards():
    cards = load_cards()                      # lanza si alguna guarda falla
    assert len(cards) >= 100
    for c in cards:
        assert len(c.claim) <= MAX_CLAIM_CHARS
        assert c.quote is None or len(c.quote.split()) <= MAX_QUOTE_WORDS
        if c.verification == "verificada_en_texto":
            assert c.citations and all(x.pages for x in c.citations)


def test_every_catalogued_book_has_cards():
    files = load_card_files()
    books = Registry.load().books
    per_book = {b: len(files[b].cards) for b in books if b in files}
    assert set(per_book) == set(books), f"libros sin fichas: {set(books) - set(per_book)}"
    for b in ("nison_candles", "murphy_ta"):           # lo codificable del primer lote
        testable = [c for c in files[b].cards if c.testable]
        assert len(testable) >= 20, b
    for b in set(books) - {"nison_candles", "murphy_ta"}:
        assert per_book[b] >= 5, b


def test_card_files_are_named_after_their_book():
    for stem, cf in load_card_files().items():
        assert cf.book_id in (stem, None)
        if cf.book_id is None:                          # fichas entre autores
            assert all(len(c.book_ids) >= 2 for c in cf.cards)


def test_cross_author_contradictions_are_linked():
    cards = {c.id: c for c in load_cards()}
    contradictions = [(c.id, r.id) for c in cards.values() for r in c.related
                      if r.relation == "contradice"]
    assert contradictions, "debe haber al menos una contradicción enlazada"
    assert all(b in cards for _, b in contradictions)


def test_no_book_files_tracked_by_git():
    """Los libros (PDF/EPUB) y el índice local nunca entran al repositorio."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("git no disponible")
    out = subprocess.run([git, "ls-files"], cwd=V2, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("no es un checkout de git")
    tracked = out.stdout.splitlines()
    assert not [f for f in tracked if f.lower().endswith((".pdf", ".epub", ".crdownload"))]
    assert not [f for f in tracked if f.startswith("data/library/")]


def test_cards_dir_contains_only_json():
    assert {p.suffix for p in CARDS_DIR.iterdir() if p.is_file()} <= {".json"}


def test_mark_cards_changes_only_selected(tmp_path):
    from eim.data.library import mark_cards

    d = tmp_path / "cards"
    shutil.copytree(CARDS_DIR, d)
    before = {p.name: p.read_text(encoding="utf-8") for p in d.glob("*.json")}
    lef_before = {c.id: c.status for c in load_card_files(d)["lefevre_reminiscences"].cards}
    new = "descartada"                       # ninguna ficha versionada está descartada
    assert new not in lef_before.values()
    changed = mark_cards(["lefevre_sitting_tight", "douglas_zone"], new, d)
    files = load_card_files(d)
    assert "lefevre_sitting_tight" in changed
    assert len(changed) == 1 + len(files["douglas_zone"].cards)
    assert {c.status for c in files["douglas_zone"].cards} == {new}
    lef = {c.id: c.status for c in files["lefevre_reminiscences"].cards}
    assert lef["lefevre_sitting_tight"] == new
    assert all(lef[i] == s for i, s in lef_before.items() if i != "lefevre_sitting_tight")
    untouched = set(before) - {"lefevre_reminiscences.json", "douglas_zone.json"}
    assert all((d / n).read_text(encoding="utf-8") == before[n] for n in untouched)
    assert mark_cards(["douglas_zone"], new, d) == []      # idempotente
