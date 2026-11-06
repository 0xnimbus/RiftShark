"""Deep rules audit 2026-11-06 20:19: niche interactions from the Kai'Sa and Riven lists (Brynhir Thundersong with a
hidden Temporal Breach, Baron Nashor with The Exile, Astral Heron after it dies, Thrill of the Hunt dodging a spell)
and plays made by effects (CR 420.3.b: every normal step of playing applies, including "can't play" locks)."""
import pathlib

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.scripts import script_all
from riftsim.core.vm import Context
from test_champions import put, settle
from test_targeting import give, main_phase

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


def _deck(db, name):
    return Deck.load(str(ROOT / f"data/decks/tournament/{name}.json"), db)


def _ready_runes(g, p):
    for u in g.players[p].runes:
        g.objects[u].exhausted = False
    g.pending = None
    g.bump()


def _drive(g, pick=None, stop=None, limit=60):
    """Run decisions: pick(d) may return a choice; stop(d) ends the loop. Defaults pass / first option."""
    for _ in range(limit):
        d = g.run()
        if d is None:
            return None
        if stop is not None and stop(d):
            return d
        c = pick(d) if pick is not None else None
        if c == "rerun":                 # pick changed the game: ask for a fresh decision
            continue
        if c is not None:
            g.choose(c)
            continue
        if d.kind == "action" and not g.chain and g.showdown is None and g.combat is None:
            return d
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    raise AssertionError("did not settle")


def _rockfall(g, db, idx):
    g.objects[g.battlefields[idx].uid].defn = next(c for c in db if c.name == "Rockfall Path")
    g.bump()


def test_hidden_temporal_breach_on_brynhir_locks_the_opponent_on_their_turn(db):
    # Kai'Sa walks Brynhir to a battlefield, hides Temporal Breach there and flips it on the opponent's turn: Brynhir is
    # played again, so "When you play me, opponents can't play cards this turn" locks the opponent for their own turn.
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    bry = put(g, db, 0, "Brynhir Thundersong", ("bf", 0))
    g.set_bf_controller(0, 0)
    tb = give(g, 0, "Temporal Breach", db)
    assert g.do_hide(0, tb, ("bf", 0))
    g.objects[tb].facedown_turn = g.turn - 1
    g.bump()
    settle(g)
    g.choose(("end_turn",))
    _drive(g, stop=lambda d: g.turn_player == 1 and g.phase == "main" and d.kind == "action" and not g.chain)
    _ready_runes(g, 1)
    herder = put(g, db, 1, "Stellacorn Herder", ("base", 1))
    sp = give(g, 1, "Discipline", db)
    assert any(o[0] == "play" for o in g.legal_actions(1))
    g.run()
    g.choose(("play", sp))
    flipped = []

    def pick(d):
        if d.kind in ("choose", "choose_many"):
            return bry if bry in d.options else (herder if herder in d.options else None)
        if d.kind == "action" and d.player == 0 and not flipped and ("play", tb) in d.options:
            flipped.append(1)
            return ("play", tb)
        return None
    _drive(g, pick=pick)
    assert flipped and g.objects[tb].zone == "trash"
    assert g.objects[bry].zone == "board" and g.objects[bry].location == ("bf", 0)
    assert any(t["kind"] == "cant_play" and 1 in t["data"]["players"] for t in g.turn_effects)
    assert not [o for o in g.legal_actions(1) if o[0] == "play"]


def test_temporal_breach_on_a_locked_opponents_unit_leaves_it_banished(db):
    # CR 420.3.b: "its owner plays it" is a normal play, so Brynhir's lock stops it; the unit stays banished (420.3.c)
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    foe = put(g, db, 1, "Stellacorn Herder", ("bf", 1))
    g.add_turn_effect(Context(0, None), "cant_play", {"players": [1]})
    tb = give(g, 0, "Temporal Breach", db)
    _ready_runes(g, 0)
    g.run()
    g.choose(("play", tb))
    _drive(g, pick=lambda d: foe if d.kind in ("choose", "choose_many") and foe in d.options else None)
    assert g.objects[foe].zone == "banish"


def test_baron_nashor_played_to_a_controlled_battlefield_enters_the_pit_ready_with_the_exile(db):
    # The Exile: "Units you play to battlefields you control enter ready." Baron's "I enter there" moves the entry to the
    # new Baron Pit; his controller orders the two replacements (CR 372.1), so he arrives at the Pit ready.
    for where, ready in ((("bf", 0), True), (("base", 0), False)):
        g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "kaisa_void")])
        g.do_channel(0, 4)
        _ready_runes(g, 0)
        put(g, db, 0, "Stellacorn Herder", ("bf", 0))
        g.set_bf_controller(0, 0)
        baron = give(g, 0, "Baron Nashor", db)
        g.pending = None
        g.run()
        g.choose(("play", baron, where))
        _drive(g)
        pit = g.battlefields[-1]
        assert g.objects[pit.uid].defn.name == "Baron Pit"
        assert g.objects[baron].location == ("bf", pit.idx)
        assert g.objects[baron].exhausted == (not ready), where


def test_astral_heron_discount_stays_when_heron_dies_with_its_trigger_on_the_chain(db):
    # CR 383.2.a example: "if I'm at a battlefield" is part of the condition; removed in reaction, the ability still resolves
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "kaisa_void")])
    h = put(g, db, 0, "Astral Heron", ("bf", 0))
    s = give(g, 0, "Discipline", db)
    a = put(g, db, 0, "Stellacorn Herder", ("base", 0), exclude=(h,))
    g.players[0].played_this_turn = []
    g.pending = None
    g.run()
    g.choose(("play", s))
    killed = []

    def pick(d):
        if not killed and any(it.kind == "trigger" and it.uid == h for it in g.chain):
            g.do_kill([h], None)
            killed.append(1)
            g.pending, g.dirty = None, True
            return "rerun"
        if d.kind in ("choose", "choose_many") and a in d.options:
            return a
        return None
    _drive(g, pick=pick)
    assert killed and g.objects[h].zone == "trash"
    blitz = give(g, 0, "Blitzcrank, Impassive", db)          # 5 [C]: next card costs [2][A][A] less -> 3, no power
    assert g.card_cost(0, blitz, "hand", ("base", 0)) == (3, [])


def test_thrill_of_the_hunt_dodges_a_spell_and_skips_rockfall_path(db):
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "kaisa_void")])
    g.do_channel(1, 4)
    _ready_runes(g, 1)
    _rockfall(g, db, 0)
    if len(g.battlefields) < 3:
        g.add_battlefield_token(1, "Baron Pit", None)
    r = put(g, db, 1, "Rengar, Pouncing", ("bf", 1))
    g.set_bf_controller(1, 1)
    ray = give(g, 0, "Hextech Ray", db)
    th = give(g, 1, "Thrill of the Hunt", db)
    g.pending = None
    g.run()
    g.choose(("play", ray))
    seen = {}

    def pick(d):
        if d.kind == "choose_location" and d.player == 1:
            seen["locs"] = list(d.options)
            return d.options[-1]
        if d.kind in ("choose", "choose_many") and r in d.options:
            return r
        if d.kind == "action" and d.player == 1 and "th" not in seen and ("play", th) in d.options:
            seen["th"] = 1
            return ("play", th)
        return None
    _drive(g, pick=pick)
    assert "th" in seen and g.objects[r].zone == "board" and g.objects[r].damage == 0
    assert ("bf", 0) not in seen.get("locs", [g.objects[r].location])       # Rockfall Path: units can't be played here
    assert g.objects[r].location != ("bf", 0)


def test_rockfall_path_stops_unit_tokens_and_hidden_units(db):
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    _rockfall(g, db, 0)
    assert g.play_token(0, "Recruit", ("bf", 0), ctx=Context(0, None)) is None     # tokens are played too (CR 185.2.a)
    assert g.play_token(0, "Recruit", ("bf", 1), ctx=Context(0, None)) is not None
    fae = give(g, 0, "Mischievous Marai", db)
    g.set_bf_controller(0, 0)
    assert g.do_hide(0, fae, ("bf", 0))
    g.objects[fae].facedown_turn = g.turn - 1
    g.bump()
    assert g._play_locations(0, fae, "facedown") == []


def test_big_combat_damage_is_assigned_one_unit_at_a_time_and_every_option_completes(db):
    # Self-play hung for 15+ minutes listing every split of a big excess over many units. The same legal set is now
    # offered one unit at a time once there are more than ASSIGN_FLAT_LIMIT assignments.
    from riftsim.core.flow import DamageAssignments
    big = DamageAssignments([(2, 1)] * 10, 60)
    assert big.count() > 10 ** 9 and big.amounts(()) == list(range(2, 43))
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    foes = [put(g, db, 1, "Stellacorn Herder", ("bf", 0), exclude=()) for _ in range(1)]
    for _ in range(4):
        foes.append(put(g, db, 1, "Stellacorn Herder", ("bf", 0), exclude=tuple(foes)))
    g.combat = {"bf": 0, "attacker": 0, "defender": 1, "step": "damage", "assign": {}}
    g._task_assign(0, tuple(foes), 40)
    dp = g._assign_dp(foes, 40, 0)
    assert dp.count() > g.ASSIGN_FLAT_LIMIT
    rnd = __import__("random").Random(3)
    steps = 0
    while 0 not in g.combat["assign"]:
        if g.tasks and g.tasks[-1][0] == "assign_step":
            g._task(*g.tasks.pop())
            continue
        d = g.pending
        assert d is not None and d.kind == "assign_damage_step"
        assert all(dp.count(d.info["prefix"] + (a,)) for a in d.options)
        g.choose(rnd.choice(d.options))
        steps += 1
    plan = g.combat["assign"][0]
    assert steps >= 1 and sum(plan) == 40 and plan in set(dp.plans())
