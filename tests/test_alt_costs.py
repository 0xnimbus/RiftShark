"""Blade of the Exile: [Equip] — [A] or exhaust a friendly unit (both costs are offered)."""
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


def test_blade_of_the_exile_equip_by_exhausting_a_friendly_unit(db, decks):
    g = main_phase(db, decks)
    a = unit_at(g, 0, ("base", 0))
    b = unit_at(g, 0, ("base", 0), exclude=(a,))
    blade = give(g, 0, "Blade of the Exile", db)
    g._to_zone(g.objects[blade], "board", location=("base", 0), controller=0)
    g.bump()
    d = g.run()
    equips = [o for o in d.options if o[0] == "activate" and o[1] == blade]
    labels = [d.labels[d.options.index(o)] for o in equips]
    assert len(equips) == 2 and any("exhaust a friendly unit" in l for l in labels)
    alt = equips[[i for i, l in enumerate(labels) if "exhaust a friendly unit" in l][0]]
    ready_runes = sum(not g.objects[u].exhausted for u in g.players[0].runes)
    g.choose(alt)
    while True:
        d = g.run()
        if d.kind == "action":
            break
        if d.out == "__exh":
            g.choose(b)                                     # pay: exhaust b
        else:
            g.choose(a if a in d.options else d.options[0])  # target: equip a
    while g.chain:
        d = g.run()
        if d.kind == "action":
            if ("pass",) not in d.options:
                break
            g.choose(("pass",))
        else:
            g.choose(d.options[0])          # e.g. the exhausted unit's own "when I become exhausted" trigger
    assert g.objects[blade].attached_to == a
    assert g.objects[b].exhausted and not g.objects[a].exhausted
    assert sum(not g.objects[u].exhausted for u in g.players[0].runes) == ready_runes   # no rune paid


def test_baron_nashor_adds_the_baron_pit_and_enters_there(db, decks):
    g = main_phase(db, decks)
    g.do_channel(0, 4)
    for u in g.players[0].runes:
        g.objects[u].exhausted = False
    g.pending = None
    g.bump()
    n = len(g.battlefields)
    baron = give(g, 0, "Baron Nashor", db)
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == baron))
    while g.chain or g.pending is None or g.pending.kind != "action":
        d = g.run()
        if d is None:
            break
        if d.kind == "action":
            if ("pass",) not in d.options:
                break
            g.choose(("pass",))
        else:
            g.choose(d.options[0])
    assert len(g.battlefields) == n + 1
    pit = g.battlefields[-1]
    assert g.objects[pit.uid].defn.name == "Baron Pit"
    assert g.objects[baron].location == ("bf", pit.idx)
    # "Units can move here from anywhere": a unit at another battlefield can move to the Pit without Ganking
    u = unit_at(g, 0, ("bf", 0))
    if not g.has_keyword(u, "ganking"):
        assert g.valid_destination(u, ("bf", pit.idx), standard=True)
        assert not g.valid_destination(u, ("bf", 1), standard=True)


def test_scuttle_crab_reveal_and_facedown_look_are_real_information(db, decks):
    import random
    from riftsim.core.policies import determinize
    g = main_phase(db, decks)
    crab = unit_at(g, 0, ("base", 0))
    g.objects[crab].defn = next(c for c in db if c.name == "Scuttle Crab")
    g.bump()
    opp_hand = list(g.players[1].hand)
    assert not any(g.knows(0, u) for u in opp_hand)
    g.do_kill([crab], None)
    while g.chain:
        d = g.run()
        if d.kind == "action":
            if ("pass",) not in d.options:
                break
            g.choose(("pass",))
        else:
            g.choose(d.options[0])
    assert all(g.knows(0, u) for u in opp_hand)            # they revealed their hand
    assert g.peek_facedown.get(0) == g.turn                 # and P0 can look at their facedown cards this turn
    for k in range(5):                                      # the AI's determinisation keeps the revealed cards
        h = determinize(g, 0, random.Random(k))
        assert set(opp_hand) <= set(h.players[1].hand)
    assert not any(g.knows(1, u) for u in g.players[0].hand)
