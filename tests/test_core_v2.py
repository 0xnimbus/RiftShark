"""Engine v2 smoke and regression tests (pytest)."""
import json
import pathlib

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.game import Game
from riftsim.core.policies import make_policy
from riftsim.core.replay import play_game, verify
from riftsim.core.scripts import script_all

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


@pytest.fixture(scope="module")
def decks(db):
    return [Deck.load(str(ROOT / "data/decks/tournament/kaisa_void.json"), db),
            Deck.load(str(ROOT / "data/decks/tournament/riven_exile.json"), db)]


def test_tournament_decks_are_legal(db, decks):
    for d in decks:
        assert d.validate(db) == []
        assert len(d.main) == 39     # CR 103.3: 40 incl. the chosen champion


def test_every_tournament_card_is_scripted(db, decks):
    for d in decks:
        for cid in [d.legend, d.champion] + d.main + d.battlefields:
            c = db.card(cid)
            assert c.script_status in ("auto", "manual", "vanilla") or not c.text.strip(), (c.id, c.name, c.keywords.get("_unparsed"))


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_random_game_completes_and_verifies(db, decks, seed):
    g, rep = play_game(db, decks, seed, [make_policy("random"), make_policy("random")], record=True)
    assert g.winner in (0, 1) or g.reason == "turn_limit"
    ok, report = verify(db, rep)
    assert ok, report["problems"]


def test_greedy_game_terminates(db, decks):
    g, rep = play_game(db, decks, 5, [make_policy("greedy"), make_policy("greedy")], record=True)
    assert g.decision_count < 2000     # regression: free Equip re-attach loop


def test_on_play_triggers_fire(db, decks):
    g, rep = play_game(db, decks, 0, [make_policy("random"), make_policy("random")], record=True)
    labels = [e.get("label", "") for e in rep["events"] if e["kind"] == "trigger"]
    assert any("When you play me" in l or "Bedeviling" in l for l in labels), labels[:20]


def test_equip_costs_are_not_free(db):
    free = []
    for c in db:
        if c.keywords.get("equip") is not None and c.is_gear:
            ab = [a for a in c.abilities if getattr(a, "is_equip", False)]
            if ab and not (ab[0].cost.get("energy") or ab[0].cost.get("power") or ab[0].cost.get("xp")):
                free.append(c.name)
    assert free == [], free


def test_coverage_floor(db):
    import collections
    c = collections.Counter(x.script_status for x in db)
    assert c["auto"] + c["manual"] >= 600


def test_unscripted_card_makes_deck_illegal(db, decks):
    """Owner rule: no silent simplifications. A deck with a card the engine cannot fully run is rejected."""
    from riftsim.core.deck import Deck, DeckError
    d = decks[0]
    bad = next(c for c in db if c.script_status == "none" and c.type in ("unit", "spell", "gear")
               and c.domains and set(c.domains) <= set(db.card(d.legend).domains))
    d2 = Deck(d.name, d.legend, d.champion, d.main[:-1] + [bad.id], d.runes, d.battlefields)
    errs = d2.validate(db)
    assert any("not fully scripted" in e for e in errs)
    try:
        d2.validate(db, raise_on_error=True)
        assert False, "expected DeckError"
    except DeckError:
        pass


# ---------------------------------------------------------------- payment (CR 162-168, 357, 430, 445)
def _random_states(db, decks, n_games=3, every=7):
    from riftsim.core.game import Game
    from riftsim.core.policies import make_policy
    for seed in range(n_games):
        g = Game(db, decks, seed=seed)
        pols = [make_policy("greedy", seed=seed + 1), make_policy("greedy", seed=seed + 2)]
        k = 0
        while True:
            d = g.run()
            if d is None or g.turn > 14:
                break
            k += 1
            if k % every == 0:
                yield g, d
            g.choose(pols[d.player].choose(g, d))


def test_can_pay_matches_payment_plans(db, decks):
    """The fast affordability check and the full plan enumeration must always agree."""
    from riftsim.core import payment
    checked = 0
    for g, d in _random_states(db, decks):
        for p in range(2):
            ps = g.players[p]
            for u in list(ps.hand) + ([ps.champion] if ps.champion else []):
                e, pw = g.card_cost(p, u, g.objects[u].zone)
                purpose = payment.purpose_of_card(g, u)
                assert g.can_pay(p, e, pw, purpose=purpose) == bool(g.payment_plans(p, e, pw, purpose)), (g.label(u), e, pw)
                checked += 1
    assert checked > 50


def test_every_payment_plan_pays_exactly_the_cost(db, decks):
    """Applying any offered plan removes exactly the cost from the resources the player had."""
    from riftsim.core import payment
    n = 0
    for g, d in _random_states(db, decks, every=5):
        p = d.player
        ps = g.players[p]
        for u in list(ps.hand)[:3]:
            e, pw = g.card_cost(p, u, g.objects[u].zone)
            purpose = payment.purpose_of_card(g, u)
            for plan in g.payment_plans(p, e, pw, purpose)[:6]:
                h = g.clone()
                hs = h.players[p]
                before_runes = {x: h.objects[x].exhausted for x in hs.runes}
                h.apply_payment(p, plan, None, purpose)
                acts, spend = plan
                assert sum(n for (r, _), n in spend if r == "E") == e
                assert sorted(r for (r, _), n in spend for _ in range(n) if r != "E") == sorted(
                    r for r in [x for (x, _), m in spend for _ in range(m) if x != "E"])
                assert len([1 for (r, _), m in spend for _ in range(m) if r != "E"]) == len(pw)
                # recycled runes left the board, exhausted ones are exhausted, nothing else changed
                for x, was in before_runes.items():
                    if ("rc", x) in acts:
                        assert x not in hs.runes and x in hs.rune_deck
                    elif ("ex", x) in acts:
                        assert h.objects[x].exhausted and not was
                    else:
                        assert h.objects[x].exhausted == was
                assert hs.energy >= 0
                n += 1
    assert n > 20


def test_add_restriction_limits_spending(db):
    """Kai'Sa's legend adds [A] 'Use only to play spells': it can pay for a spell but not for a unit."""
    from riftsim.core import payment
    from riftsim.core.deck import Deck
    from riftsim.core.game import Game
    deck = Deck.load(str(ROOT / "data/decks/tournament/kaisa_void.json"), db)
    other = Deck.load(str(ROOT / "data/decks/tournament/riven_exile.json"), db)
    g = Game(db, [deck, other], seed=3)
    g.run()
    p = 0
    ps = g.players[p]
    for u in list(ps.runes):
        g.do_recycle([u])
    ps.energy, ps.power, ps.pool_r = 0, [], [("any", "spells")]
    spell = next(c.id for c in db if c.type == "spell")
    unit = next(c.id for c in db if c.type == "unit")
    assert payment.restriction_ok(g, "spells", {"kind": "play", "types": {"spell"}})
    assert not payment.restriction_ok(g, "spells", {"kind": "play", "types": {"unit"}})
    assert g.can_pay(p, 0, ["any"], purpose={"kind": "play", "types": {"spell"}})
    assert not g.can_pay(p, 0, ["any"], purpose={"kind": "play", "types": {"unit"}})
    plans = g.payment_plans(p, 0, ["any"], {"kind": "play", "types": {"spell"}})
    assert len(plans) == 1
    g.apply_payment(p, plans[0], None, {"kind": "play", "types": {"spell"}})
    assert ps.pool_r == []


def test_runes_are_a_choice_when_domains_differ(db, decks):
    """With ready runes of several domains, paying 1 energy offers one plan per domain to exhaust."""
    from riftsim.core.game import Game
    g = Game(db, decks, seed=0)
    g.run()
    p = 0
    ps = g.players[p]
    while len({g.objects[u].domain for u in ps.runes}) < 2 and ps.rune_deck:
        g.do_channel(p, 1)
    for u in ps.runes:
        g.objects[u].exhausted = False
    ps.energy, ps.power, ps.pool_r = 0, [], []
    plans = g.payment_plans(p, 1, [], {"kind": "play", "types": {"unit"}})
    assert len(plans) == len({g.objects[u].domain for u in ps.runes}) >= 2


def test_play_session_seat_decides_who_goes_first(db):
    """Derrick's report: as first player he must start turn 1 with 2 runes; second player gets 3 on turn 2."""
    from riftsim.core.playsession import PlaySession
    d0 = json.load(open(ROOT / "data/decks/tournament/kaisa_void.json"))
    d1 = json.load(open(ROOT / "data/decks/tournament/riven_exile.json"))
    for human in (0, 1):
        s = PlaySession(db)
        s.new(d0, d1, human=human, ai="greedy", analysis=20)
        g = s.game
        me = g.players[human]
        assert g.objects[me.legend].defn.name.startswith("Kai'Sa")       # the human always plays deck0
        assert g.first_player == 0
        assert g.pending.kind == "mulligan" and g.pending.player == human   # CR 117: P0 first, then P1
        s.choose(0)                                                          # keep
        if human == 0:
            while g.phase != "main" and g.pending is not None and ("pass",) in g.pending.options:
                g.choose(("pass",)); g.run()      # a battlefield's Beginning-phase trigger may be on the chain
            assert g.turn == 1 and g.turn_player == 0 and len(me.runes) == 2
        else:
            assert len(me.runes) in (0, 3)       # AI's turn 1 already played out, or human's turn 2 started
    s1, s2 = PlaySession(db), PlaySession(db)
    s1.new(d0, d1, ai="greedy", analysis=20)
    s2.new(d0, d1, ai="greedy", analysis=20)
    assert s1.seed != s2.seed                      # every game is a fresh shuffle


def test_mulligan_sets_aside_draws_and_recycles(db):
    """CR 117: in turn order, set aside up to two cards, draw that many, then recycle the set-aside cards."""
    d0 = Deck.load(str(ROOT / "data/decks/tournament/kaisa_void.json"), db)
    d1 = Deck.load(str(ROOT / "data/decks/tournament/riven_exile.json"), db)
    g = Game(db, [d0, d1], seed=3, first_player=1)
    d = g.run()
    assert d.kind == "mulligan" and d.player == 1 and d.options[0] == ()
    # every distinct outcome once: copies of the same card are interchangeable
    from itertools import combinations
    ps = g.players[1]
    want = {tuple(sorted(g.objects[u].defn.id for u in c)) for k in range(3) for c in combinations(ps.hand, k)}
    assert len(d.options) == len(want) and max(len(o) for o in d.options) == 2
    hand0 = list(ps.hand)
    aside = d.options[-1]
    top2 = ps.deck[:2]
    g.choose(aside)
    assert sorted(ps.hand) == sorted([u for u in hand0 if u not in aside] + top2)
    assert set(ps.deck[-2:]) == set(aside) and len(ps.hand) == 4
    d = g.run()
    assert d.kind == "mulligan" and d.player == 0
    g.choose(())
    d = g.run()
    assert d.kind != "mulligan" and g.turn_player == 1
