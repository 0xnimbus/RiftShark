"""Kennen, Heart of the Tempest (1st, Riftbound Regional Championship: Europe 2026-11-08): the cards the list added
to the engine. Last Rites' Equip cost includes "Recycle 2 cards from your trash" and its effect plays a unit from the
trash on conquer/hold; Veiled Temple readies (and may detach) a gear; Minefield's mill no longer crashes."""
import pathlib

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.scripts import script_all
from test_champions import put, settle
from test_targeting import give, main_phase

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


def _game(db):
    decks = [Deck.load(str(ROOT / f"data/decks/tournament/{k}.json"), db) for k in ("kennen_tempest", "riven_exile")]
    return main_phase(db, decks)


def _to_trash(g, db, p, name):
    u = give(g, p, name, db)
    g.put_in_trash(u)
    g.restruct()
    return u


def test_kennen_deck_is_fully_scripted(db):
    d = Deck.load(str(ROOT / "data/decks/tournament/kennen_tempest.json"), db)
    assert not d.validate(db)


def test_equip_costs_keep_their_non_resource_parts(db):
    def equip(name):
        return next(a.cost for a in db.card(name).abilities if getattr(a, "is_equip", False))
    assert equip("Last Rites") == {"energy": 0, "power": ["chaos"], "recycle": 2}
    assert equip("Blade of the Ruined King").get("sacrifice") is not None


def test_last_rites_equip_needs_two_cards_in_the_trash_and_recycles_them(db):
    g = _game(db)
    unit = put(g, db, 0, "Traveling Merchant", ("base", 0))
    lr = put(g, db, 0, "Last Rites", ("base", 0))
    for u in list(g.players[0].trash):
        g._to_zone(g.objects[u], "deck")
    g.restruct()
    equip = [a for a in g.legal_actions(0) if a[0] == "activate" and a[1] == lr]
    assert not equip, "Equip offered with an empty trash"
    t1 = _to_trash(g, db, 0, "Gust")
    t2 = _to_trash(g, db, 0, "Rebuke")
    equip = [a for a in g.legal_actions(0) if a[0] == "activate" and a[1] == lr]
    assert equip
    g.pending = None
    g.run()
    g.choose(equip[0])
    settle(g, picks=[unit])
    assert g.objects[lr].attached_to == unit
    assert g.objects[t1].zone == "deck" and g.objects[t2].zone == "deck"


def test_last_rites_conquer_plays_a_unit_from_the_trash_paying_its_cost(db):
    g = _game(db)
    unit = put(g, db, 0, "Traveling Merchant", ("bf", 0))
    lr = put(g, db, 0, "Last Rites", ("base", 0))
    g.do_attach(lr, unit)
    target = _to_trash(g, db, 0, "Trifarian Captain")
    ready_before = sum(1 for u in g.players[0].runes if not g.objects[u].exhausted)
    g._establish_control(0, 0)
    settle(g, picks=[target])
    assert g.objects[target].zone == "board"
    assert sum(1 for u in g.players[0].runes if not g.objects[u].exhausted) < ready_before, "its cost was not paid"


def test_veiled_temple_readies_a_gear_and_may_detach_equipment(db):
    g = _game(db)
    g.objects[g.battlefields[0].uid].defn = db.card("Veiled Temple")
    unit = put(g, db, 0, "Traveling Merchant", ("bf", 0))
    eon = put(g, db, 0, "Edge of Night", ("base", 0))
    g.do_attach(eon, unit)
    g.objects[eon].exhausted = True
    g.restruct()
    g._establish_control(0, 0)
    settle(g, yes=True, picks=[eon])
    assert not g.objects[eon].exhausted
    assert g.objects[eon].attached_to is None


def test_minefield_mills_two_without_crashing(db):
    g = _game(db)
    g.objects[g.battlefields[0].uid].defn = db.card("Minefield")
    put(g, db, 0, "Traveling Merchant", ("bf", 0))
    top = list(g.players[0].deck[:2])
    g._establish_control(0, 0)
    settle(g)
    assert all(g.objects[u].zone == "trash" for u in top)


def test_equipment_conquer_triggers_fire_for_the_equipped_unit(db):
    # "When I conquer" on an Equipment means the unit it is attached to; before 2026-11-09 these never fired
    # (Doran's Ring, Warmog's Armor, Cull, Boneshiver, World Atlas, Trinity Force, Hextech Gauntlets, Last Rites).
    g = _game(db)
    unit = put(g, db, 0, "Traveling Merchant", ("bf", 0))
    wa = put(g, db, 0, "Warmog's Armor", ("base", 0))
    g.do_attach(wa, unit)
    assert g.objects[unit].buffs == 0
    g._establish_control(0, 0)
    settle(g)
    assert g.objects[unit].buffs == 1 and g.objects[wa].buffs == 0
