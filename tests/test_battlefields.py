"""Battlefields of the tournament decks behave as printed (Derrick's report 2026-11-06: 'battlefields do not
have their effects in play'). Each test builds the situation on a real game and drives the engine through it."""
import pathlib

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.game import Game
from riftsim.core.scripts import script_all
from riftsim.core.vm import Context

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


@pytest.fixture(scope="module")
def decks(db):
    return [Deck.load(str(ROOT / "data/decks/preban/kaisa_void.json"), db),
            Deck.load(str(ROOT / "data/decks/preban/riven_exile.json"), db)]


def _card(db, name):
    return next(c for c in db if c.name == name)


def setup(db, decks, bf_name, seed=0):
    """A game on P0's first main phase where battlefield 0 is `bf_name` and P0 has 8 ready runes."""
    g = Game(db, decks, seed=seed, first_player=0)
    g.run()
    bf = g.battlefields[0]
    g.objects[bf.uid].defn = _card(db, bf_name)
    g.do_channel(0, 6)
    for u in g.players[0].runes:
        g.objects[u].exhausted = False
    g.restruct()
    return g, bf


def put_unit(g, p, loc, ready=True, min_might=1, exclude=()):
    ps = g.players[p]
    u = next(u for u in ps.deck if g.objects[u].defn.is_unit and not g.objects[u].defn.is_champion
             and (g.objects[u].defn.might or 0) >= min_might and u not in exclude)
    g._to_zone(g.objects[u], "board", location=loc, controller=p)
    g.objects[u].exhausted = not ready
    g.restruct()
    return u


def hand_unit(g, p, max_cost=8):
    ps = g.players[p]
    u = next(u for u in ps.deck if g.objects[u].defn.is_unit and not g.objects[u].defn.is_champion
             and (g.objects[u].defn.energy or 0) <= max_cost and not g.objects[u].defn.power)
    g._to_zone(g.objects[u], "hand")
    g.restruct()
    return u


def drive(g, until, pick=None, max_steps=600):
    """Advance the game; `pick(d)` may return an option, otherwise pass / end turn / yes / first option."""
    if g.pending is not None and g.pending.kind == "action":
        g.pending = None          # the scenario changed the board: recompute the legal actions
    for _ in range(max_steps):
        if until(g):
            return True
        d = g.run()
        if d is None:
            return until(g)
        ch = pick(d) if pick else None
        if ch is None:
            for pref in (("pass",), ("end_turn",)):
                if pref in d.options:
                    ch = pref
                    break
        if ch is None:
            ch = d.options[0]
        g.choose(ch)
    return until(g)


def test_frozen_fortress_deals_1_to_each_unit_here_at_each_beginning_phase(db, decks):
    g, bf = setup(db, decks, "Frozen Fortress")
    u = put_unit(g, 1, ("bf", bf.idx), min_might=3)
    g.set_bf_controller(bf.idx, 1)
    assert g.objects[u].damage == 0
    assert drive(g, lambda g: g.turn == 2 and g.phase not in ("awaken", "beginning") and not g.chain)
    assert g.objects[u].damage == 1


def test_void_gate_adds_1_bonus_damage_to_spells_and_abilities_here(db, decks):
    g, bf = setup(db, decks, "Void Gate")
    here = put_unit(g, 1, ("bf", bf.idx), min_might=4)
    there = put_unit(g, 1, ("bf", g.battlefields[1].idx), min_might=4, exclude=(here,))
    spell = next(u for u in g.players[0].deck if "spell" in g.objects[u].defn.types)
    ctx = Context(0, spell)
    g.do_deal([here], 2, ctx, source_uid=spell)
    g.do_deal([there], 2, ctx, source_uid=spell)
    assert g.objects[here].damage == 3
    assert g.objects[there].damage == 2


def test_rockfall_path_units_cant_be_played_here(db, decks):
    g, bf = setup(db, decks, "Rockfall Path")
    u = hand_unit(g, 0)
    g.add_turn_effect(Context(0), "play_anywhere", {"filter": None})
    locs = g._play_locations(0, u, "hand")
    assert ("bf", bf.idx) not in locs
    assert ("bf", g.battlefields[1].idx) in locs


def _play_to(g, u, loc):
    def pick(d):
        if d.kind == "action" and ("play", u, loc) in d.options:
            return ("play", u, loc)
        return None
    return pick


def test_rakelstake_first_unit_played_here_each_turn_predicts(db, decks):
    g, bf = setup(db, decks, "Rakelstake")
    u = hand_unit(g, 0)
    g.add_turn_effect(Context(0), "play_anywhere", {"filter": None})
    seen = []

    def pick(d):
        seen.append(d.kind)
        return _play_to(g, u, ("bf", bf.idx))(d)
    drive(g, lambda g: "predict" in seen or g.turn > 1, pick)
    assert "predict" in seen


def test_star_spring_lets_the_player_move_another_unit_here_to_base(db, decks):
    g, bf = setup(db, decks, "Star Spring")
    old = put_unit(g, 0, ("bf", bf.idx))
    g.set_bf_controller(bf.idx, 0)
    u = hand_unit(g, 0)
    g.add_turn_effect(Context(0), "play_anywhere", {"filter": None})

    def pick(d):
        ch = _play_to(g, u, ("bf", bf.idx))(d)
        if ch is not None:
            return ch
        if d.kind == "yesno" and True in d.options:
            return True
        if old in d.options:
            return old
        return None
    drive(g, lambda g: g.objects[old].location == ("base", 0) or g.turn > 1, pick)
    assert g.objects[old].location == ("base", 0)


def test_emperors_dais_conquer_bounces_a_unit_for_a_sand_soldier(db, decks):
    g, bf = setup(db, decks, "Emperor's Dais")
    u = put_unit(g, 0, ("base", 0))
    dest = ("bf", bf.idx)

    def pick(d):
        if d.kind == "action":
            for o in d.options:
                if o[0] == "move" and o[2] == dest and u in o[1]:
                    return o
        if d.kind == "yesno" and True in d.options:
            return True
        if u in d.options:
            return u
        return None
    soldiers = lambda g: [x for x in g.units_at(dest, 0) if g.objects[x].defn.name == "Sand Soldier"]
    drive(g, lambda g: soldiers(g) or g.turn > 1, pick)
    assert g.objects[u].zone == "hand"
    assert soldiers(g)


def test_emperors_dais_does_not_offer_the_payment_without_energy(db, decks):
    # "you may pay [1] and ...": with nothing to pay with, no choice is offered (CR 445.2)
    g, bf = setup(db, decks, "Emperor's Dais")
    u = put_unit(g, 0, ("base", 0))
    dest = ("bf", bf.idx)
    asked = []

    def pick(d):
        if d.kind == "action":
            for o in d.options:
                if o[0] == "move" and o[2] == dest and u in o[1]:
                    for r in g.players[0].runes:          # spend everything first: no energy or power left
                        g.objects[r].exhausted = True
                    for r in list(g.players[0].runes):
                        g._to_zone(g.objects[r], "rune_deck")
                    g.restruct()
                    return o
        if d.kind == "yesno":
            asked.append(d.labels)
            return True
        return None
    drive(g, lambda g: any(e["kind"] == "event:conquer" for e in g.events) and not g.chain or g.turn > 1, pick)
    assert any(e["kind"] == "event:conquer" for e in g.events)
    assert not any("Sand Soldier" in " ".join(map(str, l)) for l in asked)
    assert g.objects[u].zone == "board"


def test_emperors_dais_returns_the_unit_as_a_cost_when_the_trigger_is_finalized(db, decks):
    """Emperor's Dais (errata, Vendetta): "you may pay [1] and return a unit you control here to its owner's hand to
    play a 2 [M] Sand Soldier unit token here." Paying [1] and returning the unit are the base cost (CR 383.3.b): the
    unit is already in hand while the trigger waits on the chain, and the Sand Soldier still comes afterwards."""
    g, bf = setup(db, decks, "Emperor's Dais")
    u = put_unit(g, 0, ("base", 0))
    dest = ("bf", bf.idx)
    seen = {}

    def pick(d):
        it = next((x for x in g.chain if x.kind == "trigger" and "Dais" in (x.label or "")), None)
        if it is not None and it.finalized and "zone" not in seen:
            seen["zone"] = g.objects[u].zone
        if d.kind == "action":
            for o in d.options:
                if o[0] == "move" and o[2] == dest and u in o[1]:
                    return o
        if d.kind == "yesno" and True in d.options:
            return True
        if u in d.options:
            return u
        return None
    soldiers = lambda g: [x for x in g.units_at(dest, 0) if g.objects[x].defn.name == "Sand Soldier"]
    drive(g, lambda g: soldiers(g) or g.turn > 1, pick)
    assert seen.get("zone") == "hand"
    assert soldiers(g)

