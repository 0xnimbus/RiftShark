"""Optional death replacements ("you may ... instead", CR 369-372): Mordekaiser, Twice Slain.

Derrick's question (2026-11-10): with Mordekaiser and Whirling Twirligig and a Recruit in base, kill Mordekaiser as
Twirligig's cost; his replacement kills the Recruit instead, and the cost still counts as paid (CR 203.2, 357.2.a),
so a Mech is played and Mordekaiser survives exhausted in base."""
import pathlib

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.scripts import script_all
from test_champions import put
from test_targeting import main_phase

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


@pytest.fixture(scope="module")
def decks(db):
    return [Deck.load(str(ROOT / "data/decks/preban/riven_exile.json"), db),
            Deck.load(str(ROOT / "data/decks/preban/kaisa_void.json"), db)]


def _setup(db, decks, morde_loc=("base", 0)):
    g = main_phase(db, decks)
    for u, o in list(g.objects.items()):            # an empty board for player 0
        if o.zone == "board" and o.controller == 0 and "unit" in g.chars(u).types:
            g._to_zone(o, "trash")
    morde = put(g, db, 0, "Mordekaiser, Twice Slain", morde_loc)
    twirl = put(g, db, 0, "Whirling Twirligig", ("base", 0), exclude=(morde,))
    recruit = g.play_token(0, "Recruit", ("base", 0))
    if isinstance(recruit, (list, tuple)):
        recruit = recruit[0]
    g.restruct()
    return g, morde, twirl, recruit


def _units(g, p, name):
    return [u for u, o in g.objects.items() if o.zone == "board" and o.controller == p and o.defn.name == name]


def _activate_mech(g, twirl):
    d = g.run()
    act = next(o for o in d.options if o[0] == "activate" and o[1] == twirl and o[2] == 2)
    g.choose(act)
    return act


def _drive(g, pick, limit=40):
    seen = []
    for _ in range(limit):
        d = g.run()
        if d is None:
            return seen
        seen.append(d.kind)
        c = pick(d)
        if c is not None:
            g.choose(c)
            continue
        if d.kind == "action" and not g.chain and g.showdown is None and g.combat is None:
            return seen
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    raise AssertionError("did not settle")


def test_mordekaiser_is_scripted(db):
    m = next(c for c in db if c.name == "Mordekaiser, Twice Slain")
    assert m.script_status == "manual"


def test_kill_mordekaiser_for_twirligig_saves_him_and_makes_a_mech(db, decks):
    g, morde, twirl, recruit = _setup(db, decks)
    _activate_mech(g, twirl)
    asked = []

    def pick(d):
        if d.kind in ("choose", "target") and morde in d.options:
            return morde                                   # pay the cost with Mordekaiser himself
        if d.kind == "optional_replacement":
            asked.append(d)
            assert d.player == 0 and recruit in d.options and "decline" in d.options
            return recruit
        if d.kind in ("choose", "location", "choose_location") and ("base", 0) in d.options:
            return ("base", 0)
        return None
    _drive(g, pick)
    assert asked, "Mordekaiser's controller was never asked"
    assert g.objects[morde].zone == "board" and g.objects[morde].location == ("base", 0)
    assert g.objects[morde].exhausted
    assert g.objects[morde].damage == 0
    assert g.objects[recruit].zone != "board"
    assert len(_units(g, 0, "Mech")) == 1                  # the cost counts as paid (CR 203.2)
    assert g.objects[twirl].exhausted


def test_declining_lets_mordekaiser_die_and_still_makes_a_mech(db, decks):
    g, morde, twirl, recruit = _setup(db, decks)
    _activate_mech(g, twirl)

    def pick(d):
        if d.kind in ("choose", "target") and morde in d.options:
            return morde
        if d.kind == "optional_replacement":
            return "decline"
        return None
    _drive(g, pick)
    assert g.objects[morde].zone == "trash"
    assert g.objects[recruit].zone == "board"
    assert len(_units(g, 0, "Mech")) == 1


def test_once_each_turn(db, decks):
    g, morde, twirl, recruit = _setup(db, decks, morde_loc=("bf", 0))
    other = g.play_token(0, "Recruit", ("base", 0))
    other = other[0] if isinstance(other, (list, tuple)) else other
    asked = []

    def pick(d):
        if d.kind == "optional_replacement":
            asked.append(d)
            return d.options[1]
        return None
    g.do_kill([morde])
    _drive(g, pick)
    assert len(asked) == 1 and g.objects[morde].zone == "board" and g.objects[morde].location == ("base", 0)
    g.do_kill([morde])                                     # second death this turn: no replacement
    _drive(g, pick)
    assert len(asked) == 1 and g.objects[morde].zone == "trash"


def test_no_other_friendly_unit_means_no_question(db, decks):
    g, morde, twirl, recruit = _setup(db, decks)
    g._to_zone(g.objects[recruit], "trash")
    g.restruct()
    kinds = []
    g.do_kill([morde])
    _drive(g, lambda d: kinds.append(d.kind) or None)
    assert "optional_replacement" not in kinds and g.objects[morde].zone == "trash"


def test_lethal_damage_offers_the_save(db, decks):
    g, morde, twirl, recruit = _setup(db, decks, morde_loc=("bf", 0))
    g.objects[morde].damage = 99
    g.dirty = True
    asked = []

    def pick(d):
        if d.kind == "optional_replacement":
            asked.append(d)
            return recruit
        return None
    _drive(g, pick)
    assert asked and g.objects[morde].zone == "board" and g.objects[morde].damage == 0
    assert g.objects[morde].location == ("base", 0) and g.objects[recruit].zone != "board"
