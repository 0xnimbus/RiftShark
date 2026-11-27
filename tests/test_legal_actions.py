"""Legal-action audit 2026-11-07 (Derrick: every action must be considered for each player, including passing, Ganking
moves, leaving runes up and gear lines). Each test checks one option the Core Rules give (or forbid) at a decision."""
import pathlib
import random

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.scripts import script_all
from riftsim.core import policies
from test_targeting import main_phase, give
from test_champions import put

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


@pytest.fixture(scope="module")
def decks(db):
    return [Deck.load(str(ROOT / "data/decks/preban/riven_exile.json"), db),
            Deck.load(str(ROOT / "data/decks/preban/kaisa_void.json"), db)]


def fresh(g):
    g.pending = None
    g.dirty = True
    g.restruct()
    return g.run()


def open_showdown(g, db):
    """P0 moves a unit to the empty, uncontrolled battlefield 0: a non-combat showdown opens there (CR 316.8.b.1)
    with P0 holding Focus."""
    u = put(g, db, 0, "Shipyard Skulker", ("base", 0))
    d = fresh(g)
    g.choose(("move", (u,), ("bf", 0)))
    for _ in range(20):
        d = g.run()
        if g.showdown is not None and not g.chain and d.kind == "action":
            return d
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    raise AssertionError("no showdown opened")


# ---------------------------------------------------------------- passing / doing nothing
def test_end_turn_always_offered_with_runes_up(db, decks):
    # CR 316.9: the turn player may end the turn whenever they like, also with every rune ready and cards to play
    g = main_phase(db, decks)
    give(g, 0, "Shipyard Skulker", db)
    d = fresh(g)
    assert ("end_turn",) in d.options and any(o[0] == "play" for o in d.options)
    assert all(not g.objects[r].exhausted for r in g.players[0].runes)


def test_responder_may_pass_or_float_runes(db, decks):
    # CR 313.2 + 164.2: when Focus passes to the other player in a showdown they may pass, or use a rune's Reaction
    # ability, with their runes left untapped (units and gear resolve on finalizing, CR 337.2, so no window there)
    g = main_phase(db, decks)
    g.do_channel(1, 2)
    d = open_showdown(g, db)
    g.choose(("pass",))
    d = g.run()
    assert d.player == 1 and g.focus == 1 and ("pass",) in d.options
    assert any(o[0] == "rune" for o in d.options)
    assert all(not g.objects[r].exhausted for r in g.players[1].runes)


# ---------------------------------------------------------------- Ganking (CR 144.4.c, 810)
def test_ganking_unit_may_move_battlefield_to_battlefield(db, decks):
    g = main_phase(db, decks)
    gank = put(g, db, 0, "Siren of the Shallows", ("bf", 0))
    plain = put(g, db, 0, "Shipyard Skulker", ("bf", 0), exclude=(gank,))
    g.set_bf_controller(0, 0)
    assert g.has_keyword(gank, "ganking") and not g.has_keyword(plain, "ganking")
    d = fresh(g)
    to_bf1 = [o for o in d.options if o[0] == "move" and o[2] == ("bf", 1)]
    assert ("move", (gank,), ("bf", 1)) in to_bf1
    assert all(plain not in o[1] for o in to_bf1)           # without Ganking: base only (CR 144.4.b)
    assert ("move", (plain,), ("base", 0)) in d.options
    assert any(set(o[1]) == {gank, plain} for o in d.options if o[0] == "move" and o[2] == ("base", 0))


# ---------------------------------------------------------------- hiding (CR 811.1.b)
def test_hide_during_own_showdown_with_focus(db, decks):
    # "on your turn during an Open State": a showdown with no chain is a Showdown Open state (CR 307)
    g = main_phase(db, decks)
    put(g, db, 0, "Shipyard Skulker", ("bf", 1))
    g.set_bf_controller(1, 0)
    card = give(g, 0, "Block", db)
    d = open_showdown(g, db)
    assert d.player == 0 and g.focus == 0
    assert ("hide", card, 1) in d.options


def test_no_hide_for_the_opponent_or_in_a_closed_state(db, decks):
    g = main_phase(db, decks)
    put(g, db, 1, "Shipyard Skulker", ("bf", 1))
    g.set_bf_controller(1, 1)
    card = give(g, 1, "Block", db)
    assert not [o for o in g.legal_actions(1) if o[0] == "hide"]     # not P1's turn
    open_showdown(g, db)
    g.focus = g.priority = 1
    assert not [o for o in g.legal_actions(1) if o[0] == "hide" and o[1] == card]


# ---------------------------------------------------------------- gear
def test_deploy_gear_is_played_only_to_a_battlefield(db, decks):
    # CR 830.1.b: Deploy = "This may be played to any battlefield" and "Play this only to a battlefield"
    g = main_phase(db, decks)
    banner = give(g, 0, "Concert Poster", db)
    d = fresh(g)
    locs = {o[2] for o in d.options if o[0] == "play" and o[1] == banner}
    assert locs == {("bf", b.idx) for b in g.battlefields}


def test_quick_draw_equipment_plays_at_reaction_speed_but_equips_in_main(db, decks):
    # CR 819.1.d: Quick-Draw = "[Reaction]" (a card keyword: playing it) + "When you play this, attach it".
    # Equip itself is "[Cost]: Attach this gear to a unit you control" with no timing keyword (CR 818.1.c.2).
    g = main_phase(db, decks)
    sword = put(g, db, 0, "Protector's Shield", ("base", 0))          # Equip [1]
    put(g, db, 0, "Shipyard Skulker", ("base", 0), exclude=(sword,))
    in_hand = give(g, 0, "Cloth Armor", db)                             # [1], Quick-Draw
    d = fresh(g)
    assert any(o[0] == "activate" and o[1] == sword for o in d.options)        # main phase: Equip is fine
    d = open_showdown(g, db)
    assert not any(o[0] == "activate" and o[1] == sword for o in d.options)
    assert any(o[0] == "play" and o[1] == in_hand for o in d.options)            # Quick-Draw card: Reaction


# ---------------------------------------------------------------- AI option pruning
def test_prune_options_keeps_pass_and_every_play():
    moves = [("move", tuple(range(k)), ("bf", 0)) for k in range(1, 80)] + [("move", (i,), ("base", 0)) for i in range(5)]
    opts = [("end_turn",), ("play", 900, ("base", 0)), ("activate", 901, 0), ("hide", 902, 1)] + moves
    out = policies.prune_options(opts, 40, random.Random(1))
    assert len(out) == 40
    for o in opts[:4]:
        assert o in out
    assert ("move", tuple(range(79)), ("bf", 0)) in out          # the all-units group
    assert all(("move", (i,), ("base", 0)) in out for i in range(5))
    assert policies.prune_options(opts[:10], 40, random.Random(1)) == opts[:10]


def test_rules_audit_finds_nothing(db):
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import rules_audit
    assert rules_audit.run(3, 4100, "random") == 0
