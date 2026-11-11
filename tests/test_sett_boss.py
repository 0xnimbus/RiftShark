"""Sett, The Boss (Origins errata): If a buffed unit you control would die, you may pay [C], exhaust me, and spend its
buff to heal it, exhaust it, and recall it instead. When you conquer, ready me. [C] = Body or Order power."""
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
    return [Deck.load(str(ROOT / "data/decks/tournament/sett_the_boss.json"), db),
            Deck.load(str(ROOT / "data/decks/tournament/kaisa_void.json"), db)]


def _setup(db, decks):
    g = main_phase(db, decks)
    unit = put(g, db, 0, "Pit Rookie", ("bf", 0))
    g.do_buff(unit)
    g.bump()
    return g, g.players[0].legend, unit


def _kill_and_answer(g, unit, pick):
    g.do_kill([unit], None)
    asked = []
    for _ in range(20):
        d = g.run()
        if d is None or d.kind != "optional_replacement":
            return asked, d
        asked.append(d)
        g.choose(pick(d))
    raise AssertionError("loop")


def test_sett_legend_is_scripted(db):
    assert db.card("Sett, The Boss").script_status == "manual"


def test_pay_and_recall_buffed_unit(db, decks):
    g, sett, unit = _setup(db, decks)
    ready_runes = sum(1 for u in g.players[0].runes if not g.objects[u].exhausted)
    asked, _ = _kill_and_answer(g, unit, lambda d: d.options[1])
    assert len(asked) == 1 and asked[0].player == 0
    o = g.objects[unit]
    assert o.zone == "board" and o.location[0] == "base"
    assert o.exhausted and o.buffs == 0 and o.damage == 0
    assert g.objects[sett].exhausted
    after = sum(1 for u in g.players[0].runes if not g.objects[u].exhausted)
    assert after < ready_runes or len(g.players[0].runes) < 12      # one rune paid (exhausted or recycled)


def test_decline_lets_it_die(db, decks):
    g, sett, unit = _setup(db, decks)
    asked, _ = _kill_and_answer(g, unit, lambda d: "decline")
    assert len(asked) == 1
    assert g.objects[unit].zone == "trash" and not g.objects[sett].exhausted


def test_no_offer_when_unbuffed_or_sett_exhausted(db, decks):
    g, sett, unit = _setup(db, decks)
    g.objects[sett].exhausted = True
    g.bump()
    asked, _ = _kill_and_answer(g, unit, lambda d: "decline")
    assert asked == [] and g.objects[unit].zone == "trash"
    g, sett, unit = _setup(db, decks)
    g.do_spend_buff(unit)
    asked, _ = _kill_and_answer(g, unit, lambda d: "decline")
    assert asked == [] and g.objects[unit].zone == "trash"


def test_no_offer_without_body_or_order_power(db, decks):
    g, sett, unit = _setup(db, decks)
    fury = next(c for c in db if c.name == "Fury Rune")
    for u in g.players[0].runes:
        g.objects[u].defn, g.objects[u].domain = fury, "fury"
    g.players[0].energy, g.players[0].power = 0, []
    g.bump()
    asked, _ = _kill_and_answer(g, unit, lambda d: "decline")
    assert asked == [] and g.objects[unit].zone == "trash"


def test_conquer_readies_sett(db, decks):
    g, sett, unit = _setup(db, decks)
    g.objects[sett].exhausted = True
    g.bump()
    g.emit("conquer", player=0, loc=("bf", 0), units=[unit])
    for _ in range(20):
        d = g.run()
        if d is None or (d.kind == "action" and not g.chain):
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert not g.objects[sett].exhausted
