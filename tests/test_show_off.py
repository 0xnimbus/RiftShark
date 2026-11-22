"""[Show Off] (CR 832): decided while finalizing; the shown-off card's information is locked in."""
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


def _play_until(g, uid, answer):
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == uid))
    seen = []
    while True:
        d = g.run()
        if d is None or d.kind == "action":
            return seen, d
        seen.append(d.kind)
        g.choose(answer(d))


def _resolve(g):
    while g.chain:
        d = g.run()
        if d.kind == "action":
            if ("pass",) not in d.options:
                return
            g.choose(("pass",))
        else:                                               # "up to" choices: take the most
            g.choose(max(d.options, key=lambda o: len(o) if isinstance(o, tuple) else 0))


def test_battle_preparations_show_off_gear_readies_runes(db, decks):
    g = main_phase(db, decks)
    mine = unit_at(g, 0, ("base", 0))
    gear = give(g, 0, "Blade of the Exile", db)
    s = give(g, 0, "Battle Preparations", db)
    shown = []

    def answer(d):
        if d.kind == "show_off":
            assert d.options[0] is None and gear in d.options and s not in d.options
            shown.append(gear)
            return gear
        if d.kind == "pay":
            return d.options[0]
        if d.kind == "choose_many":                         # the runes are targets, chosen as it is played
            picked.extend(max(d.options, key=lambda o: len(o) if isinstance(o, tuple) else 0))
            return tuple(picked)
        return mine if mine in d.options else d.options[0]
    picked = []
    seen, _ = _play_until(g, s, answer)
    assert seen[0] == "show_off" and shown                  # decided first, while finalizing
    assert len(picked) == 2
    for u in picked:                                        # exhaust them so the ready is visible
        g.objects[u].exhausted = True
    _resolve(g)
    assert not any(g.objects[u].exhausted for u in picked)
    assert g.objects[gear].zone == "hand"                   # revealed, not spent


def test_battle_preparations_without_show_off_does_not_ready(db, decks):
    g = main_phase(db, decks)
    mine = unit_at(g, 0, ("base", 0))
    s = give(g, 0, "Battle Preparations", db)
    _play_until(g, s, lambda d: None if d.kind == "show_off" else (d.options[0] if d.kind == "pay" else (mine if mine in d.options else d.options[0])))
    before = sum(g.objects[u].exhausted for u in g.players[0].runes)
    _resolve(g)
    assert sum(g.objects[u].exhausted for u in g.players[0].runes) == before


def test_empyrean_predicts_the_shown_off_cards_power_then_draws_2(db):
    dk = [Deck.load(str(ROOT / "data/decks/tournament/nasus_curator.json"), db),
          Deck.load(str(ROOT / "data/decks/tournament/kaisa_void.json"), db)]
    g = main_phase(db, dk)
    g.do_channel(0, 4)
    for u in g.players[0].runes:
        g.objects[u].exhausted = False
    g.pending = None
    g.restruct()
    e = give(g, 0, "The Empyrean", db)
    shown = give(g, 0, "Unchecked Power", db)               # Power cost 2
    assert g.objects[shown].defn.power == 2
    seen, _ = _play_until(g, e, lambda d: shown if d.kind == "show_off" else d.options[0])
    assert seen[0] == "show_off"
    hand = len(g.players[0].hand)
    predicted = []
    while g.chain:
        d = g.run()
        if d.kind == "action":
            if ("pass",) not in d.options:
                break
            g.choose(("pass",))
        else:
            if d.kind == "predict":
                predicted.append(max(len(o) for o in d.options))
            g.choose(d.options[0])
    assert predicted == [2]                                 # [Predict] equal to its Power cost
    assert len(g.players[0].hand) == hand + 2               # then draw 2
