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


# ----------------------------------------------------------------------------- 2026-11-07 00:20 run: errata wording
def _resolve(g, pick=None):
    return _drive(g, pick=lambda d: (True if d.kind == "yesno" else None) if pick is None else pick(d))


def test_guards_pays_order_to_ready_the_sand_soldier_it_made(db):
    # Guards! (errata): "Play a 2 [M] Sand Soldier unit token. Then do this: You may pay [C] to ready it." The
    # auto-scripter read "it" as a chosen unit, so paying readied nothing.
    g = main_phase(db, [_deck(db, "azir_emperor"), _deck(db, "kaisa_void")])
    gu = give(g, 0, "Guards!", db)
    g.pending = None
    g.run()
    g.choose(("play", gu))
    _resolve(g, pick=lambda d: True if d.kind == "yesno" else (d.options[0] if d.kind == "pay" else None))
    soldiers = [u for u, o in g.objects.items() if o.defn.name == "Sand Soldier" and o.zone == "board"]
    assert len(soldiers) == 1 and not g.objects[soldiers[0]].exhausted


def test_tideturner_only_swaps_with_a_unit_at_another_location(db):
    # Tideturner (errata): "you may choose a unit you control at another location"
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "kaisa_void")])
    here = put(g, db, 0, "Stellacorn Herder", ("bf", 0))
    home = put(g, db, 0, "Stellacorn Herder", ("base", 0), exclude=(here,))
    g.set_bf_controller(0, 0)
    tt = give(g, 0, "Tideturner", db)
    ab = next(a for a in g.abilities(tt) if type(a).__name__ == "Triggered")
    ch = next(i for i in (ab.target_code or []) + ab.code if type(i).__name__ == "Choose")
    g.objects[tt].location = ("bf", 0)            # as if it had entered at the battlefield
    assert g.choice_candidates(Context(0, tt), ch.sel, targeted=True) == [home]
    g.objects[tt].location = None
    g.pending = None
    g.run()
    g.choose(("play", tt, ("bf", 0)))
    _resolve(g)
    assert g.objects[tt].location == ("base", 0) and g.objects[home].location == ("bf", 0)


def test_arise_readies_up_to_two_soldiers(db):
    # Arise! (errata): "Then do this: Ready up to two of them." -> readying fewer is a legal choice
    ar = next(c for c in db if c.name == "Arise!")
    ch = next(i for i in ar.abilities[0].code if type(i).__name__ == "Choose")
    assert ch.n == 2 and ch.up_to


# ----------------------------------------------------------------------------- 2026-11-07 05:20 run: errata, other cards
def _card(db, name):
    return next(c for c in db if c.name == name)


def _choose_of(ab):
    return next(i for i in (ab.target_code or []) + list(ab.code) if type(i).__name__ in ("Choose", "ChooseFromList"))


def test_up_to_errata_dark_child_sona_janna(db):
    # Origins/Spiritforged errata: "ready up to 2 runes", "ready up to 4 friendly runes", "move up to one enemy unit"
    for name, n in (("Dark Child, Starter", 2), ("Sona, Harmonious", 4), ("Janna, Savior", 1)):
        ch = _choose_of(_card(db, name).abilities[-1])
        assert ch.n == n and ch.up_to, name
    sel = _choose_of(_card(db, "Dark Child, Starter").abilities[-1]).sel
    assert sel.side == "friendly"                      # it used to offer the opponent's runes too


def test_yone_conquer_trigger_exists_once(db):
    yone = _card(db, "Yone, Blademaster")
    assert sum(1 for a in yone.abilities if getattr(a, "event", None) == "conquer_self") == 1


def test_karma_buffs_on_cards_recycled_to_the_main_deck_not_runes(db):
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    k = put(g, db, 0, "Karma, Channeler", ("base", 0))
    g.pending = None
    settle(g)
    n = len(g.events)
    g.do_recycle([g.players[0].runes[0]], Context(0, None))           # rune -> rune deck: no trigger
    assert not [e for e in g.events[n:] if e["kind"] == "trigger" and e["source"] == k]
    card = g.players[0].hand[0]
    g.do_recycle([card], Context(0, None))                            # card -> Main Deck: buff
    assert [e for e in g.events[n:] if e["kind"] == "trigger" and e["source"] == k]


def test_elnuk_herd_may_pump_itself_and_recycles_only_itself_from_face_down(db):
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    other = put(g, db, 0, "Stellacorn Herder", ("bf", 0))
    g.set_bf_controller(0, 0)
    el = give(g, 0, "Elnuk Herd", db)
    assert g.do_hide(0, el, ("bf", 0))
    g.objects[el].facedown_turn = g.turn - 1
    g.pending = None
    g.bump()
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == el))
    seen = []

    def pick(d):
        if d.kind in ("choose", "choose_many"):
            seen.append(set(d.options))
            return el if el in d.options else None
        return None
    _drive(g, pick=pick)
    assert seen and el in seen[0] and other in seen[0]          # errata: "a friendly unit" (itself included)
    assert g.objects[el].zone == "deck" and g.objects[other].zone == "board"


def test_portal_rescue_returns_a_borrowed_unit_to_its_owners_base(db):
    # errata: "Banish a friendly unit, then its owner plays it to their base"
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    stolen = put(g, db, 1, "Stellacorn Herder", ("bf", 0))
    g.objects[stolen].controller = 0
    g.bump()
    pr = give(g, 0, "Portal Rescue", db)
    _ready_runes(g, 0)
    g.run()
    g.choose(("play", pr))
    _drive(g, pick=lambda d: stolen if d.kind in ("choose", "choose_many") and stolen in d.options else None)
    assert g.objects[stolen].zone == "board" and g.objects[stolen].location == ("base", 1)
    assert g.objects[stolen].controller == 1


# ----------------------------------------------------------------------------- 2026-11-07 10:20 run: Legion
def test_noxus_hopeful_costs_2_less_only_with_legion(db):
    # "[Legion] — I cost [2] less." The auto-scripter dropped the Legion condition, so Kai'Sa's three Hopefuls always
    # cost [2] instead of [4].
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    nh = give(g, 0, "Noxus Hopeful", db)
    g.players[0].played_this_turn = []
    g.bump()
    assert g.card_cost(0, nh, "hand", ("base", 0)) == (4, [])
    other = give(g, 0, "Stupefy", db)
    g.players[0].played_this_turn = [other]
    g.bump()
    assert g.card_cost(0, nh, "hand", ("base", 0)) == (2, [])


@pytest.mark.parametrize("name", ["Darius, Hand of Noxus", "Hand of Noxus", "Sun Disc"])
def test_legion_activated_abilities_need_legion(db, name):
    # "[T]: [Reaction], [Legion] — [Add] [1]." / "[T]: [Legion] — ...": usable only once you've played another card
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    u = put(g, db, 0, "Forecaster", ("base", 0))
    g.objects[u].defn = _card(db, name)
    g.bump()
    idx = next(i for i, a in enumerate(g.abilities(u)) if type(a).__name__ == "Activated")
    ab = g.abilities(u)[idx]
    g.players[0].played_this_turn = []
    g.bump()
    assert not g._can_activate(0, u, idx, ab)
    g.players[0].played_this_turn = [give(g, 0, "Stupefy", db)]
    g.bump()
    assert g._can_activate(0, u, idx, ab)


# ----------------------------------------------------------------------------- 2026-11-07 15:20 run: [Level N]
def test_level_3_enter_ready_needs_level_3(db):
    # Bandle Soldier "[Level 3][>] I enter ready." and Scorchclaw "[Level 3][>] I have +1 [M] and enter ready."
    # The auto-scripter dropped the Level condition, so both always entered ready (and Scorchclaw always had +1).
    for name in ("Bandle Soldier", "Scorchclaw"):
        defn = _card(db, name)
        for xp, active in ((0, False), (2, False), (3, True)):
            g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
            g.players[0].xp = xp
            u = put(g, db, 0, "Forecaster", ("base", 0))
            g.objects[u].defn = defn
            g.bump()
            flagged = [a for a in g.abilities(u) if "Level 3" in (a.source_text or "") + (a.label or "")]
            assert flagged, name
            assert all(a.active(g, u) == active for a in flagged), (name, xp)
        if name == "Scorchclaw":
            g.players[0].xp = 0
            g.bump()
            base = g.chars(u).might
            g.players[0].xp = 3
            g.bump()
            assert g.chars(u).might == base + 1


def test_every_flagged_line_carries_its_condition(db):
    # Every ability parsed from a [Legion] / [Empowered] / [Level N] line must be conditional.
    from riftsim.core.scripts.auto_grammar import script_line, split_lead_keywords
    missing = []
    for c in db:
        for line in (c.text or "").split("\n"):
            flags, body = split_lead_keywords(line)
            if not body or not any(f.split(" ")[0] in ("legion", "empowered", "level") for f in flags):
                continue
            try:
                abs_ = script_line(c, line)
            except Exception:
                continue
            missing += [(c.name, line) for a in abs_ if hasattr(a, "cond") and a.cond is None]
    assert not missing, missing[:10]
