"""Rules audit 2026-11-06: options must be the full legal set (combat damage assignment, discard/recycle, moves),
victory before trigger ordering, Channel Phase counts."""
import pathlib

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.scripts import script_all
from test_targeting import main_phase
from test_champions import put

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


@pytest.fixture(scope="module")
def decks(db):
    return [Deck.load(str(ROOT / "data/decks/tournament/riven_exile.json"), db),
            Deck.load(str(ROOT / "data/decks/tournament/kaisa_void.json"), db)]


def units(g, db, p, names, loc):
    out = []
    for n in names:
        out.append(put(g, db, p, n, loc, exclude=tuple(out)))
    return out


def test_damage_assignment_lethal_in_full_first(db, decks):
    # CR 467.2.c.3 example: 5 damage among four 3 [M] units -> 3 to one and 2 to another, never 2/1/1/1
    g = main_phase(db, decks)
    us = units(g, db, 1, ["Shipyard Skulker"] * 4, ("bf", 0))
    plans = g._damage_plans(us, 5, 0)
    assert all(sorted(p, reverse=True) == [3, 2, 0, 0] for p in plans)
    assert len(plans) == 12                      # which unit gets 3 x which gets 2


def test_damage_assignment_not_more_than_lethal(db, decks):
    # CR 467.2.c.4 example: each already has 1 damage -> nobody may get more than 2
    g = main_phase(db, decks)
    us = units(g, db, 1, ["Shipyard Skulker"] * 4, ("bf", 0))
    for u in us:
        g.objects[u].damage = 1
    plans = g._damage_plans(us, 5, 0)
    assert all(max(p) <= 2 and sorted(p, reverse=True) == [2, 2, 1, 0] for p in plans)


def test_damage_assignment_excess_can_go_anywhere(db, decks):
    # CR 467.2.c.4: once every unit has lethal, the excess is the player's to split
    g = main_phase(db, decks)
    us = units(g, db, 1, ["Shipyard Skulker"] * 2, ("bf", 0))
    plans = set(g._damage_plans(us, 8, 0))
    assert plans == {(3 + a, 3 + 2 - a) for a in range(3)}


def test_damage_assignment_counts_doubling(db, decks):
    # CR 467.2.c.4.a example: a 3 [M] unit whose damage is doubled is lethal at 2 assigned
    g = main_phase(db, decks)
    a, b = units(g, db, 1, ["Shipyard Skulker"] * 2, ("bf", 0))
    g.add_mod(a, "double_damage", 1, "turn")
    plans = set(g._damage_plans([a, b], 3, 0))
    assert (2, 1) in plans and (3, 0) not in plans and (0, 3) in plans


def test_damage_assignment_counts_prevention(db, decks):
    # CR 467.2.c.5 example (scaled): a 3 [M] unit that prevents 3 needs 6 assigned
    g = main_phase(db, decks)
    a, b = units(g, db, 1, ["Shipyard Skulker"] * 2, ("bf", 0))
    g.add_mod(a, "prevent", 3, "turn")
    assert g._lethal_need(a, 6, 0) == 6
    assert set(g._damage_plans([a, b], 6, 0)) == {(6, 0), (3, 3)}
    assert g.objects[a].mods and g.objects[a].mods[-1].value == 3       # previewing used nothing up


def test_backline_and_assigned_last_share_a_priority(db, decks):
    # CR 467.2.c.7: Soraka ("I must be assigned combat damage last") and a Backline unit: any order between them
    g = main_phase(db, decks)
    bf = ("bf", 0)
    sor = put(g, db, 1, "Soraka, Wanderer", bf)
    bl = put(g, db, 1, "Enthusiastic Promoter", bf, exclude=(sor,))
    plans = g._damage_plans([sor, bl], 1, 0)
    assert set(plans) == {(1, 0), (0, 1)}


def test_discard_offers_every_distinct_choice(db, decks):
    from riftsim.core import ops
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    hand = g.players[0].hand
    while len(hand) < 9:
        g._draw_raw(0)
    d = ops.Discard(2, player=None).run(g, Context(0, None))
    names = {tuple(sorted(g.objects[u].defn.id for u in o)) for o in d.options}
    assert len(names) == len(d.options)          # no duplicates of identical outcomes
    from itertools import combinations
    assert names == {tuple(sorted(g.objects[u].defn.id for u in c)) for c in combinations(hand, 2)}


def test_recycle_from_trash_is_not_truncated(db, decks):
    from riftsim.core import ops
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    deck = g.players[0].deck
    for u in list(deck[:20]):
        g._to_zone(g.objects[u], "trash")
    g.bump()
    pool = [u for u, o in g.objects.items() if o.zone == "trash" and o.owner == 0]
    d = ops.Recycle(n=3).run(g, Context(0, None))
    from itertools import combinations
    want = {tuple(sorted(g.objects[u].defn.id for u in c)) for c in combinations(pool, 3)}
    assert len(d.options) == len(want) and len(want) > 60


def test_victory_is_checked_before_trigger_ordering(db, decks):
    g = main_phase(db, decks)
    g.players[1].points = g.victory_score()
    g.reorder_requests.append({"player": 0, "items": [], "order": []})
    g.dirty = True
    g.pending = None
    g.run()
    assert g.over and g.winner == 1
