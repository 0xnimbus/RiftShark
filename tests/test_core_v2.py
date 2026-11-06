"""Engine v2 smoke and regression tests (pytest)."""
import json
import pathlib

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.policies import make_policy
from riftsim.core.replay import play_game, verify
from riftsim.core.scripts import script_all

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


@pytest.fixture(scope="module")
def decks(db):
    return [Deck.load(str(ROOT / "data/decks/tournament/kaisa_void.json"), db),
            Deck.load(str(ROOT / "data/decks/tournament/riven_exile.json"), db)]


def test_tournament_decks_are_legal(db, decks):
    for d in decks:
        assert d.validate(db) == []
        assert len(d.main) == 39     # CR 103.3: 40 incl. the chosen champion


def test_every_tournament_card_is_scripted(db, decks):
    for d in decks:
        for cid in [d.legend, d.champion] + d.main + d.battlefields:
            c = db.card(cid)
            assert c.script_status in ("auto", "manual", "vanilla") or not c.text.strip(), (c.id, c.name, c.keywords.get("_unparsed"))


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_random_game_completes_and_verifies(db, decks, seed):
    g, rep = play_game(db, decks, seed, [make_policy("random"), make_policy("random")], record=True)
    assert g.winner in (0, 1) or g.reason == "turn_limit"
    ok, report = verify(db, rep)
    assert ok, report["problems"]


def test_greedy_game_terminates(db, decks):
    g, rep = play_game(db, decks, 5, [make_policy("greedy"), make_policy("greedy")], record=True)
    assert g.decision_count < 2000     # regression: free Equip re-attach loop


def test_on_play_triggers_fire(db, decks):
    g, rep = play_game(db, decks, 0, [make_policy("random"), make_policy("random")], record=True)
    labels = [e.get("label", "") for e in rep["events"] if e["kind"] == "trigger"]
    assert any("When you play me" in l or "Bedeviling" in l for l in labels), labels[:20]


def test_equip_costs_are_not_free(db):
    free = []
    for c in db:
        if c.keywords.get("equip") is not None and c.is_gear:
            ab = [a for a in c.abilities if getattr(a, "is_equip", False)]
            if ab and not (ab[0].cost.get("energy") or ab[0].cost.get("power") or ab[0].cost.get("xp")):
                free.append(c.name)
    assert free == [], free


def test_coverage_floor(db):
    import collections
    c = collections.Counter(x.script_status for x in db)
    assert c["auto"] + c["manual"] >= 600


def test_unscripted_card_makes_deck_illegal(db, decks):
    """Owner rule: no silent simplifications. A deck with a card the engine cannot fully run is rejected."""
    from riftsim.core.deck import Deck, DeckError
    d = decks[0]
    bad = next(c for c in db if c.script_status == "none" and c.type in ("unit", "spell", "gear")
               and c.domains and set(c.domains) <= set(db.card(d.legend).domains))
    d2 = Deck(d.name, d.legend, d.champion, d.main[:-1] + [bad.id], d.runes, d.battlefields)
    errs = d2.validate(db)
    assert any("not fully scripted" in e for e in errs)
    try:
        d2.validate(db, raise_on_error=True)
        assert False, "expected DeckError"
    except DeckError:
        pass
