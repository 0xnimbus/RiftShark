"""Targets are chosen when a spell or ability is played, not when it resolves (CR 355.5, 355.14.b), and a target
that became illegal before resolution is unaffected while the rest of the spell still happens (CR 359.3.e)."""
import pathlib

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.game import Game
from riftsim.core.scripts import script_all

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


@pytest.fixture(scope="module")
def decks(db):
    return [Deck.load(str(ROOT / "data/decks/tournament/kaisa_void.json"), db),
            Deck.load(str(ROOT / "data/decks/tournament/riven_exile.json"), db)]


def main_phase(db, decks, seed=0):
    g = Game(db, decks, seed=seed, first_player=0)
    d = g.run()
    while g.phase != "main" or g.turn_player != 0:
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
        d = g.run()
    g.do_channel(0, 6)
    for u in g.players[0].runes:
        g.objects[u].exhausted = False
    g.pending = None
    g.bump()
    return g


def give(g, p, name, db):
    """Put a fresh copy of card `name` into player p's hand (re-using a deck object)."""
    ps = g.players[p]
    u = ps.deck[-1]
    g.objects[u].defn = next(c for c in db if c.name == name)
    g._to_zone(g.objects[u], "hand")
    g.bump()
    return u


def unit_at(g, p, loc, exclude=()):
    ps = g.players[p]
    u = next(u for u in ps.deck if g.objects[u].defn.is_unit and not g.objects[u].defn.is_champion and u not in exclude
             and (g.objects[u].defn.might or 0) >= 3)
    g._to_zone(g.objects[u], "board", location=loc, controller=p)
    g.objects[u].exhausted = False
    g.bump()
    return u


def play(g, uid, picks):
    """Play `uid` from P0's hand; answer choose decisions from `picks` (list), pay with the first plan."""
    d = g.run()
    act = next(o for o in d.options if o[0] == "play" and o[1] == uid)
    g.choose(act)
    picks = list(picks)
    while True:
        d = g.run()
        if d.kind in ("choose", "choose_many") and picks:
            g.choose(picks.pop(0))
        elif d.kind == "pay":
            g.choose(d.options[0])
        elif d.kind == "yesno":
            g.choose(True)
        else:
            return d


def test_spell_target_is_chosen_on_play_and_visible_before_reactions(db, decks):
    g = main_phase(db, decks)
    bf = ("bf", 0)
    foe = unit_at(g, 1, bf)
    s = give(g, 0, "Stupefy", db)
    d = play(g, s, [foe])
    it = g.chain[-1]
    assert it.uid == s and it.finalized
    assert it.ctx.vars.get("t") == foe                    # chosen while finalizing, before anyone can react
    assert any(e["kind"] == "event:target" and foe in e.get("targets", ()) for e in g.events) or \
        any(n == "t" for n, _ in it.ctx.vars.get("__targets", []))
    assert d.player == 1 or ("pass",) in d.options        # opponent now gets to respond with the target known


def test_illegal_target_is_unaffected_but_rest_of_spell_happens(db, decks):
    g = main_phase(db, decks)
    bf = ("bf", 0)
    foe = unit_at(g, 1, bf)
    s = give(g, 0, "Stupefy", db)
    hand_before = len(g.players[0].hand)
    play(g, s, [foe])
    g.do_kill([foe], None)                                 # e.g. killed by a reaction before Stupefy resolves
    g.objects[foe].zone == "trash"
    g._to_zone(g.objects[foe], "board", location=bf, controller=1)   # a new object, even if it comes back
    g.bump()
    while g.chain:
        d = g.run()
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert all(m.kind != "might" for m in g.objects[foe].mods)       # not affected
    assert len(g.players[0].hand) == hand_before                    # cast Stupefy (-1), drew 1 (+1)


def test_bellows_breath_hits_up_to_three_units_at_the_same_location(db, decks):
    g = main_phase(db, decks)
    bf = ("bf", 0)
    a = unit_at(g, 1, bf)
    b = unit_at(g, 1, bf, exclude=(a,))
    c = unit_at(g, 1, ("base", 1), exclude=(a, b))
    s = give(g, 0, "Bellows Breath", db)
    d = g.run()
    act = next(o for o in d.options if o[0] == "play" and o[1] == s)
    g.choose(act)
    d = g.run()
    while d.kind not in ("choose_many",):
        g.choose(d.options[0]); d = g.run()
    assert all(len({g.objects[u].location for u in o}) <= 1 for o in d.options)
    assert (a, b) in d.options or (b, a) in d.options
    g.choose((a, b) if (a, b) in d.options else (b, a))
    while g.chain:
        d = g.run()
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    hit = [g.objects[u].damage >= 1 or g.objects[u].zone != "board" for u in (a, b)]
    assert all(hit)                                       # (Void Gate there may add 1 bonus damage)
    assert g.objects[c].damage == 0


def test_repeat_executes_the_spell_again_with_its_own_choices(db, decks):
    # CR 820: Bellows Breath with Repeat paid: the second execution has its own targets (here: the same two units)
    g = main_phase(db, decks)
    bf = ("bf", 0)
    a = unit_at(g, 1, bf)
    b = unit_at(g, 1, bf, exclude=(a,))
    s = give(g, 0, "Bellows Breath", db)
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == s))
    picks = 0
    for _ in range(40):
        d = g.run()
        if d.kind == "choose_many":
            g.choose(next(o for o in d.options if set(o) == {a, b})); picks += 1; continue
        if d.kind == "additional_cost":
            g.choose(True); continue
        if d.kind == "action" and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert picks == 2
    hits = [e for e in g.events if e["kind"] == "damage" and e.get("uid") in (a, b)]
    assert len(hits) == 4 or all(g.objects[u].zone != "board" for u in (a, b))
