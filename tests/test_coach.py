"""The coach never recommends floating resources (exhausting/recycling a rune) as a move, and does not grade it."""
import pathlib

import pytest

from riftsim.core.analysis import analyze, grade_choice
from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.scripts import script_all
from test_targeting import main_phase

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


def test_rune_floats_are_not_recommended_or_graded(db):
    decks = [Deck.load(str(ROOT / "data/decks/preban/riven_exile.json"), db),
             Deck.load(str(ROOT / "data/decks/preban/kaisa_void.json"), db)]
    g = main_phase(db, decks)
    d = g.run()
    floats = [o for o in d.options if o[0] == "rune"]
    assert floats
    an = analyze(g, d, iterations=40, seed=1)
    assert an["best"]["option"][0] != "rune"
    r = grade_choice(an, floats[0])
    assert r["grade"] == "resource" and r["loss_pct"] == 0.0
    real = next(o for o in d.options if o[0] != "rune")
    r = grade_choice(an, real)
    assert r["grade"] in ("best", "good", "inaccuracy", "mistake", "blunder")
    assert r["loss_pct"] <= r["raw_loss_pct"]                 # the search's margin of error is not charged
