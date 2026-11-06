"""Legend scripts against printed text (legends swapped onto a running game's legend object)."""
import pathlib

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.scripts import script_all
from test_targeting import main_phase, give, unit_at

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


@pytest.fixture(scope="module")
def decks(db):
    return [Deck.load(str(ROOT / "data/decks/tournament/riven_exile.json"), db),
            Deck.load(str(ROOT / "data/decks/tournament/kaisa_void.json"), db)]


def legend(g, db, cid):
    u = g.players[0].legend
    g.objects[u].defn = next(c for c in db if c.id == cid)
    g.objects[u].exhausted = False
    g.bump()
    return u


def activate(g, uid, answers):
    d = g.run()
    acts = [o for o in d.options if o[0] == "activate" and o[1] == uid]
    assert acts, "ability not offered"
    g.choose(acts[0])
    answers = list(answers)
    while True:
        d = g.run()
        if d is None:
            return
        if d.kind == "action":
            if g.chain and ("pass",) in d.options:
                g.choose(("pass",)); continue
            return d
        pick = answers.pop(0) if answers and answers[0] in d.options else d.options[0]
        g.choose(pick)


def test_yasuo_moves_a_unit_from_base_to_a_battlefield_and_back(db, decks):
    g = main_phase(db, decks)
    lg = legend(g, db, "OGN-259")
    u = unit_at(g, 0, ("base", 0))
    activate(g, lg, [u, ("bf", 0)])
    assert g.objects[u].location == ("bf", 0)
    for _ in range(200):                                    # the move opened a showdown there: let it finish
        d = g.run()
        if g.showdown is None and g.combat is None and not g.chain and d.player == 0 and d.kind == "action":
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    if g.objects[u].location != ("bf", 0) or g.turn_player != 0:
        pytest.skip("the unit left the battlefield in the showdown")
    g.objects[lg].exhausted = False
    for r in g.players[0].runes:
        g.objects[r].exhausted = False
    g.pending = None
    g.bump()
    activate(g, lg, [u])
    assert g.objects[u].location == ("base", 0)


def test_lucian_equipment_each_give_assault(db, decks):
    g = main_phase(db, decks)
    legend(g, db, "SFD-183")
    u = unit_at(g, 0, ("base", 0))
    blade = give(g, 0, "Blade of the Exile", db)
    g._to_zone(g.objects[blade], "board", location=("base", 0), controller=0)
    g.do_attach(blade, u, None)
    g.bump()
    assert g.chars(u).kw("assault") >= 1


def test_jax_attaches_a_detached_equipment(db, decks):
    g = main_phase(db, decks)
    lg = legend(g, db, "SFD-193")
    u = unit_at(g, 0, ("base", 0))
    blade = give(g, 0, "Blade of the Exile", db)
    g._to_zone(g.objects[blade], "board", location=("base", 0), controller=0)
    g.bump()
    activate(g, lg, [blade, u])
    assert g.objects[blade].attached_to == u


def test_ezreal_needs_two_enemy_choices_this_turn(db, decks):
    g = main_phase(db, decks)
    lg = legend(g, db, "SFD-199")
    d = g.run()
    assert not any(o[0] == "activate" and o[1] == lg for o in d.options)
    g.turn_memo[("chose_enemy", 0)] = 2
    g.pending = None
    g.bump()
    d = g.run()
    assert any(o[0] == "activate" and o[1] == lg for o in d.options)


def test_enemy_choices_are_counted_from_spells(db, decks):
    g = main_phase(db, decks)
    foe = unit_at(g, 1, ("bf", 0))
    s = give(g, 0, "Stupefy", db)
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == s))
    while g.pending is None or g.pending.kind != "action":
        d = g.run()
        if d.kind == "action":
            break
        g.choose(foe if foe in d.options else d.options[0])
    assert g.turn_memo.get(("chose_enemy", 0)) == 1
