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


def test_burn_out_recycles_then_opponent_scores_then_draws(db, decks):
    # CR 432.2 example: empty deck at a draw -> recycle trash, opponent gains 1, then draw 1
    g = main_phase(db, decks)
    ps = g.players[0]
    for u in list(ps.deck):
        g._to_zone(g.objects[u], "trash")
    before = g.players[1].points
    hand = len(ps.hand)
    g.do_draw(0, 1)
    assert g.players[1].points == before + 1 and len(ps.hand) == hand + 1 and not ps.trash


def test_burn_out_repeats_while_deck_and_trash_are_empty(db, decks):
    # CR 432.3: the attempt burns out again and again until an opponent wins
    g = main_phase(db, decks)
    ps = g.players[0]
    for u in list(ps.deck) + list(ps.trash):
        g._to_zone(g.objects[u], "banished")
    g.do_draw(0, 1)
    assert g.players[1].points >= g.victory_score() and g.players[1].points > g.players[0].points
    g.dirty = True; g.pending = None
    g.run()
    assert g.over and g.winner == 1


def test_putting_cards_from_an_empty_deck_into_trash_burns_out(db, decks):
    # CR 432.1.b
    g = main_phase(db, decks)
    ps = g.players[0]
    for u in list(ps.deck)[:-1]:
        g._to_zone(g.objects[u], "trash")
    before = g.players[1].points
    g.do_burn(0, 2)
    assert g.players[1].points == before + 1


@pytest.mark.parametrize("name,kw", [
    ("Master Yi, Tempered", "ganking"), ("Master Yi, Tempered", "deflect"),   # only at [Level 6]
    ("Seal of Discord", "reaction"),        # "[T]: [Reaction] — [Add]" is the ability's timing, not the gear's
    ("Dragonsoul Sage", "reaction"), ("Shadow", "action"),
    ("Ember Monk", "hidden"),               # "When you play a card from [Hidden]"
    ("Carrion Dredger", "deflect"),         # its Bird token has Deflect
    ("Sprite Mother", "temporary"),         # its Sprite token is Temporary
    ("Bilgewater Bully", "ganking"),        # only while buffed
    ("Breakneck Mech", "deflect"),          # granted to Mechs by a static
])
def test_keywords_mentioned_in_text_are_not_the_cards_own(db, name, kw):
    assert not next(c for c in db if c.name == name).keywords.get(kw)


@pytest.mark.parametrize("name,kw", [
    ("Ekko, Revolutionary", "assault"), ("Block", "hidden"), ("Block", "action"), ("Petricite Monument", "temporary"),
    ("Unsung Hero", "deathknell"), ("Kai'Sa, Rebel", "disarm"), ("Sprite Call", "hidden"),
])
def test_printed_keywords_are_kept(db, name, kw):
    assert next(c for c in db if c.name == name).keywords.get(kw)


def test_bilgewater_bully_has_ganking_only_while_buffed(db, decks):
    g = main_phase(db, decks)
    u = put(g, db, 0, "Bilgewater Bully", ("base", 0))
    assert not g.chars(u).keywords.get("ganking")
    g.do_buff(u)
    g.bump()
    assert g.chars(u).keywords.get("ganking")


@pytest.mark.parametrize("name,kw,val", [
    ("Chemtech Enforcer", "assault", 2), ("Needlessly Large Yordle", "shield", 5), ("Sivir, Ambitious", "deflect", 2),
    ("Armored Tusker", "shield", 3), ("Garen, Rugged", "shield", 2), ("Voracious Gromp", "hunt", 3),
])
def test_numbered_keywords_carry_their_number(db, name, kw, val):
    assert next(c for c in db if c.name == name).keywords.get(kw) == val


def _hide_and_wait(g, db, p, name, bf):
    from test_targeting import give
    u = give(g, p, name, db)
    g.set_bf_controller(bf, p)
    assert g.do_hide(p, u, ("bf", bf))
    g.objects[u].facedown_turn = g.turn - 1          # hidden on an earlier turn
    g.bump()
    return u


def test_hidden_unit_play_effect_targets_at_its_battlefield(db, decks):
    # CR 811.1.d.3 (Blastcone Fae example): the play effect must target a unit at the battlefield it was played to
    g = main_phase(db, decks)
    fae = _hide_and_wait(g, db, 0, "Blastcone Fae", 0)
    mine = put(g, db, 0, "Shipyard Skulker", ("bf", 0))
    far = put(g, db, 1, "Shipyard Skulker", ("bf", 1))
    g.pending = None
    d = g.run()
    acts = [a for a in d.options if a[0] == "play" and a[1] == fae]
    assert acts
    g.choose(acts[0])
    seen = None
    for _ in range(20):
        d = g.run()
        if d is None:
            break
        if d.kind in ("choose", "choose_many"):
            seen = set(x for x in d.options if x is not None)
            break
        if d.kind == "action":
            break
        g.choose(d.options[0])
    # either asked among units at bf 0 only, or auto-picked one there
    if seen is not None:
        assert far not in seen
    assert g.chars(far).might == g.objects[far].defn.might


def test_hidden_spell_without_target_at_its_battlefield_cannot_be_played(db, decks):
    # CR 811.1.d: no valid target at that battlefield -> cannot be played from facedown
    from riftsim.core.selectors import Sel
    g = main_phase(db, decks)
    assert g._could_target_at_bf(Sel("unit", side="enemy"))
    assert not g._could_target_at_bf(Sel("unit", where="base"))


def _swap_hidden_hand(g, p):
    """Same public information, different hidden hand for player p (hand cards swapped with deck cards)."""
    ps = g.players[p]
    k = min(len(ps.hand), len(ps.deck))
    new_hand, new_deck = ps.deck[:k] + ps.hand[k:], ps.hand[:k] + ps.deck[k:]
    for u in new_hand:
        g.objects[u].zone = "hand"
    for u in new_deck:
        g.objects[u].zone = "deck"
    ps.hand, ps.deck = new_hand, new_deck
    g.bump()


@pytest.mark.parametrize("spec", ["advanced", "expert", "mcts:30"])
def test_ai_decisions_do_not_depend_on_the_opponents_hidden_hand(db, decks, spec):
    from riftsim.core.policies import make_policy
    g = main_phase(db, decks)
    put(g, db, 1, "Shipyard Skulker", ("bf", 0))
    g.pending = None
    d = g.run()
    assert d.player == 0 and len(d.options) > 2
    h = g.clone()
    _swap_hidden_hand(h, 1)
    assert sorted(g.players[1].hand) != sorted(h.players[1].hand)
    pa, pb = make_policy(spec, seed=5), make_policy(spec, seed=5)
    if spec.startswith("mcts"):
        ra, rb = pa.search(g, g.pending), pb.search(h, h.pending)
        va = sorted((str(c.option), c.visits, round(c.value, 6)) for c in ra.children)
        vb = sorted((str(c.option), c.visits, round(c.value, 6)) for c in rb.children)
    else:
        va, vb = pa.evaluate(g, g.pending, list(g.pending.options)), pb.evaluate(h, h.pending, list(h.pending.options))
    assert va == vb


def test_determinize_keeps_public_and_known_cards(db, decks):
    import random
    from riftsim.core.policies import determinize
    g = main_phase(db, decks)
    opp = g.players[1]
    trash = list(opp.trash)
    seen = g.determinize_check = None
    known = opp.hand[0]
    g.known.setdefault(0, {})[known] = g.objects[known].entered_stamp
    for s in range(5):
        x = determinize(g, 0, random.Random(s))
        assert known in x.players[1].hand and x.players[1].trash == trash
        assert len(x.players[1].hand) == len(opp.hand) and x.players[1].champion == opp.champion


def test_gold_pays_power_while_paying(db, decks):
    # Gold: "Kill this, [T]: [Add] [A]" is an Add ability usable while paying a cost (CR 357.1.a)
    g = main_phase(db, decks)
    for r in list(g.players[0].runes):
        g._to_zone(g.objects[r], "rune_deck")
    g.bump()
    assert not g.can_pay(0, 0, ["any"], purpose={"kind": "play", "types": {"spell"}})
    gold = g.play_token(0, "Gold", ("base", 0))
    gold = gold[0] if isinstance(gold, (list, tuple)) else gold
    g.objects[gold].exhausted = False
    g.bump()
    plans = g.payment_plans(0, 0, ["fury"], {"kind": "play", "types": {"spell"}})
    assert plans and any(a[0] == "ab" for a in plans[0][0])
    g.apply_payment(0, plans[0], None, {"kind": "play", "types": {"spell"}})
    assert g.objects[gold].zone == "trash" or g.objects[gold].zone in (None, "gone")
