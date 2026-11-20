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
    g.restruct()


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
    g.restruct()


def test_hidden_temporal_breach_on_brynhir_locks_the_opponent_on_their_turn(db):
    # Kai'Sa walks Brynhir to a battlefield, hides Temporal Breach there and flips it on the opponent's turn: Brynhir is
    # played again, so "When you play me, opponents can't play cards this turn" locks the opponent for their own turn.
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    bry = put(g, db, 0, "Brynhir Thundersong", ("bf", 0))
    g.set_bf_controller(0, 0)
    tb = give(g, 0, "Temporal Breach", db)
    assert g.do_hide(0, tb, ("bf", 0))
    g.objects[tb].facedown_turn = g.turn - 1
    g.restruct()
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
    g.restruct()
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
    g.restruct()
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
    g.restruct()
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
    g.restruct()
    assert g.card_cost(0, nh, "hand", ("base", 0)) == (4, [])
    other = give(g, 0, "Stupefy", db)
    g.players[0].played_this_turn = [other]
    g.restruct()
    assert g.card_cost(0, nh, "hand", ("base", 0)) == (2, [])


@pytest.mark.parametrize("name", ["Darius, Hand of Noxus", "Hand of Noxus", "Sun Disc"])
def test_legion_activated_abilities_need_legion(db, name):
    # "[T]: [Reaction], [Legion] — [Add] [1]." / "[T]: [Legion] — ...": usable only once you've played another card
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    u = put(g, db, 0, "Forecaster", ("base", 0))
    g.objects[u].defn = _card(db, name)
    g.restruct()
    idx = next(i for i, a in enumerate(g.abilities(u)) if type(a).__name__ == "Activated")
    ab = g.abilities(u)[idx]
    g.players[0].played_this_turn = []
    g.restruct()
    assert not g._can_activate(0, u, idx, ab)
    g.players[0].played_this_turn = [give(g, 0, "Stupefy", db)]
    g.restruct()
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
            g.restruct()
            flagged = [a for a in g.abilities(u) if "Level 3" in (a.source_text or "") + (a.label or "")]
            assert flagged, name
            assert all(a.active(g, u) == active for a in flagged), (name, xp)
        if name == "Scorchclaw":
            g.players[0].xp = 0
            g.restruct()
            base = g.chars(u).might
            g.players[0].xp = 3
            g.restruct()
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


# ----------------------------------------------------------------------------- 2026-11-07 20:20 run: play locations
def _clear_bfs(g, db=None):
    for bf in g.battlefields if db is not None else ():
        g.objects[bf.uid].defn = _card(db, "Windswept Hillock")      # no "can't play here" battlefield in the way
    for u, o in g.objects.items():
        if o.zone == "board" and o.location is not None and o.location[0] == "bf":
            o.zone, o.location = "trash", None
    for bf in g.battlefields:
        bf.controller = None
    g.pending = None
    g.restruct()


def _locs(g, p, uid):
    return [l for l in g._play_locations(p, uid, g.objects[uid].zone) if l[0] == "bf"]


def test_play_location_permissions_follow_the_printed_text(db):
    # "You may play me to an open battlefield", "I can be played to a battlefield you're attacking" and "You may play
    # me to an occupied enemy battlefield" were all read as "any battlefield".
    g = main_phase(db, [_deck(db, "reksai_void_burrower"), _deck(db, "viktor_herald")])
    _clear_bfs(g, db)
    g.battlefields[1].controller = 1                         # bf 0 open, bf 1 enemy-controlled and empty
    scout, dog, rengar = (give(g, 0, n, db) for n in ("Sai Scout", "Deadbloom Predator", "Rengar, Pouncing"))
    g.restruct()
    assert _locs(g, 0, scout) == [("bf", 0)]                 # open = unoccupied and uncontrolled (CR 170.11.c)
    assert _locs(g, 0, dog) == [] and _locs(g, 0, rengar) == []
    enemy = put(g, db, 1, "Forecaster", ("bf", 1))
    put(g, db, 1, "Forecaster", ("bf", 0))                   # bf 0 occupied, so no longer open
    g.restruct()
    assert _locs(g, 0, scout) == []
    assert _locs(g, 0, dog) == [("bf", 1)]                   # occupied enemy battlefield only
    assert _locs(g, 0, rengar) == []
    g.combat = {"bf": 1, "attacker": 0, "defender": 1, "step": "showdown"}
    g.restruct()
    assert _locs(g, 0, rengar) == [("bf", 1)]                # the battlefield you're attacking
    g.combat = {"bf": 1, "attacker": 1, "defender": 0, "step": "showdown"}
    g.restruct()
    assert _locs(g, 0, rengar) == []                         # not while defending
    assert enemy in g.units_at(("bf", 1))


def test_hunters_circle_counts_a_token_as_the_first_unit_played_there(db):
    # "For each player, the first unit or gear they play here on their turn costs [1] less." Playing a token is
    # playing a unit (CR 185.2.a), so a token played there first uses up the discount.
    g = main_phase(db, [_deck(db, "reksai_void_burrower"), _deck(db, "viktor_herald")])
    _clear_bfs(g)
    circle = next(i for i, bf in enumerate(g.battlefields) if g.objects[bf.uid].defn.name == "Hunters' Circle") \
        if any(g.objects[bf.uid].defn.name == "Hunters' Circle" for bf in g.battlefields) else None
    if circle is None:
        circle = 0
        g.objects[g.battlefields[0].uid].defn = _card(db, "Hunters' Circle")
    loc = ("bf", circle)
    g.battlefields[circle].controller = 0
    u = give(g, 0, "Hunting Dog", db)
    g.restruct()
    full = _card(db, "Hunting Dog").energy
    assert g.card_cost(0, u, "hand", loc)[0] == full - 1
    g.play_token(0, "Recruit", loc, Context(0))
    g.restruct()
    assert g.card_cost(0, u, "hand", loc)[0] == full


def test_effect_plays_offer_the_cards_own_locations_and_skip_rockfall_path(db):
    # Void Burrower "banish one, then play it": the location choice used only base + controlled battlefields, so it
    # missed "play me to an open battlefield" and offered Rockfall Path (where the play then silently failed).
    g = main_phase(db, [_deck(db, "reksai_void_burrower"), _deck(db, "viktor_herald")])
    _clear_bfs(g, db)
    g.objects[g.battlefields[1].uid].defn = _card(db, "Rockfall Path")
    g.battlefields[1].controller = 0
    rs = put(g, db, 0, "Rek'Sai, Breacher", ("base", 0))
    scout = give(g, 0, "Sai Scout", db)
    g.players[0].hand.remove(scout)
    g.objects[scout].zone = "deck"
    g.players[0].deck.remove(scout) if scout in g.players[0].deck else None
    g.players[0].deck.insert(0, scout)
    _ready_runes(g, 0)
    g.emit("conquer", player=0, loc=("bf", 1), bf=1, units=(rs,))
    g.dirty = True
    seen = []

    def pick(d):
        if d.kind == "order_triggers":
            return next(o for o, lab in zip(d.options, d.labels) if lab == "Void Burrower")
        if d.kind == "yesno":
            return True
        if d.kind == "pick_many" and (scout,) in d.options:
            return (scout,)
        if d.kind == "choose_location":
            seen.append(list(d.options))
            return ("bf", 0)
        return None
    _drive(g, pick=pick)
    assert seen == [[("base", 0), ("bf", 0)]]
    assert g.objects[scout].zone == "board" and g.objects[scout].location == ("bf", 0)


# ----------------------------------------------------------------------------- 2026-11-08 00:20 run: Riven / Vex
def test_vex_stuns_token_units_an_opponent_plays(db):
    # "When an opponent plays a unit while I'm at a battlefield, [Stun] it." Token units are played too (CR 185.2.a);
    # Vex used the "plays a card" trigger, which skips tokens.
    for vex_loc, stunned in ((("bf", 0), True), (("base", 0), False)):
        g = main_phase(db, [_deck(db, "vex_gloomist"), _deck(db, "viktor_herald")])
        put(g, db, 0, "Vex, Apathetic", vex_loc)
        tok = g.play_token(1, "Recruit", ("base", 1), Context(1))
        settle(g)
        assert bool(g.objects[tok].stunned) == stunned


def test_tornado_warrior_from_face_down_empowers_something_here_until_end_of_turn(db):
    # "When you play me from face down, you may empower something here. Disempower it at end of turn." The auto-script
    # looked for a unit with the tag "Something", so the trigger could never choose anything.
    g = main_phase(db, [_deck(db, "vex_gloomist"), _deck(db, "riven_exile")])
    paws = put(g, db, 0, "Steel Paws", ("bf", 0))
    elsewhere = put(g, db, 0, "Forecaster", ("base", 0))
    g.set_bf_controller(0, 0)
    tw = give(g, 0, "Tornado Warrior", db)
    assert g.do_hide(0, tw, ("bf", 0))
    g.objects[tw].facedown_turn = g.turn - 1
    _ready_runes(g, 0)
    d = g.run()
    flip = next(o for o in d.options if o[0] == "play" and o[1] == tw)
    g.choose(flip)
    offered = []

    def pick(d):
        if d.kind == "yesno":
            return True
        if d.kind in ("choose", "choose_many") and paws in d.options:
            offered.append(list(d.options))
            return paws
        return None
    _drive(g, pick=pick)
    assert offered and elsewhere not in offered[0] and tw in offered[0]
    assert g.objects[paws].empowered and g.chars(paws).might == 7          # [Empowered] — I have +7 [M]
    g.choose(("end_turn",))
    _drive(g, stop=lambda d: g.turn_player == 1)
    assert not g.objects[paws].empowered


@pytest.mark.parametrize("name", ["Faithful Manufactor", "Mischievous Marai", "Blitzcrank, Impassive"])
def test_when_you_play_me_here_means_the_battlefield_played_to(db, name):
    # "When you play me" triggers go on the chain while the unit is still there, so their "here" was empty: Faithful
    # Manufactor made no Recruit, Mischievous Marai dealt nothing and Blitzcrank moved nobody.
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    g.set_bf_controller(0, 0)
    put(g, db, 0, "Forecaster", ("bf", 0))
    foe_here = put(g, db, 1, "Forecaster", ("bf", 0))
    foe_base = put(g, db, 1, "Forecaster", ("base", 1))
    g.set_bf_controller(0, 0)
    u = give(g, 0, name, db)
    _ready_runes(g, 0)
    for r in list(g.players[0].rune_deck)[:4]:
        g.players[0].rune_deck.remove(r)
        g.players[0].runes.append(r)
        g.objects[r].zone, g.objects[r].exhausted = "board", False
    g.restruct()
    d = g.run()
    g.choose(("play", u, ("bf", 0)))
    _drive(g, pick=lambda d: True if d.kind == "yesno" else (foe_base if foe_base in d.options else
                                                             (foe_here if foe_here in d.options else None)))
    assert g.objects[u].location == ("bf", 0)
    if name == "Faithful Manufactor":
        assert [x for x, o in g.objects.items() if o.zone == "board" and o.defn.name == "Recruit"
                and o.location == ("bf", 0)]
    elif name == "Mischievous Marai":
        assert g.objects[foe_here].zone == "trash"                      # 2 damage kills the 1 Might Forecaster
    else:
        # "move an enemy unit to here" (it then fights there)
        assert any(isinstance(e, dict) and e.get("kind") == "move" and e.get("uid") == foe_base for e in g.events)
        assert g.objects[foe_base].location != ("base", 1)


# ----------------------------------------------------------------------------- 2026-11-08 05:20 run: misparsed cards
def _cast(g, db, p, name, pick):
    """Give `name` to player p, make it affordable, play it and drive with pick."""
    u = give(g, p, name, db)
    for r in list(g.players[p].rune_deck)[:6]:
        g.players[p].rune_deck.remove(r)
        g.players[p].runes.append(r)
        g.objects[r].zone = "board"
    _ready_runes(g, p)
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == u))
    _drive(g, pick=pick)
    return u


def _fresh(db, deck="vex_gloomist"):
    g = main_phase(db, [_deck(db, deck), _deck(db, "riven_exile")])
    _clear_bfs(g, db)
    return g


def test_no_selector_uses_a_tag_no_card_has(db):
    # The auto-scripter turned phrases like "something else", "it instead" and "an opponent" into unit tags, so the
    # choice was always empty (Tornado Warrior, Sudden Storm, Possession, Ocean Drake, ...).
    tags = {t.lower() for c in db for t in (c.tags or [])}
    bad = []
    for c in db:
        if c.script_status == "partial":
            continue
        for a in list(c.abilities) + list(getattr(c, "effect_abilities", []) or []):
            for i in (getattr(a, "target_code", None) or []) + list(getattr(a, "code", None) or []):
                sel = getattr(i, "sel", None)
                if sel is not None and any(t.lower() not in tags for t in (getattr(sel, "tags", None) or ())):
                    bad.append((c.name, str(sel)))
    assert not bad, bad


def test_scuttle_crab_reveals_the_opponents_hand_and_gains_xp(db):
    g = _fresh(db)
    sc = put(g, db, 0, "Scuttle Crab", ("base", 0))
    g.do_kill([sc], Context(0))
    settle(g)
    assert g.players[0].xp == 1 and g.peek_facedown.get(0) == g.turn
    assert g.players[1].hand and all(u in g.known.get(0, {}) for u in g.players[1].hand)


def test_sudden_storm_and_monster_harpoon_deal_4_instead(db):
    for name, setup, want in (("Sudden Storm", "attacker", 4), ("Sudden Storm", None, 2),
                              ("Monster Harpoon", "facedown", 4), ("Monster Harpoon", None, 2)):
        g = _fresh(db, "akali_rogue")                             # Fury runes
        g.set_bf_controller(0, 1)
        foe = put(g, db, 1, "Thousand-Tailed Watcher", ("bf", 0))   # 7 Might: the damage stays on it
        if setup == "attacker":
            g.objects[foe].designation = "attacker"
        if setup == "facedown":
            hid = give(g, 0, "Tornado Warrior", db)
            g.set_bf_controller(1, 0)
            assert g.do_hide(0, hid, ("bf", 1))
        g.restruct()
        _cast(g, db, 0, name, lambda d: foe if d.kind in ("choose", "choose_many") and foe in d.options else None)
        assert g.objects[foe].damage == want, (name, setup)


def test_possession_takes_control_and_recalls(db):
    g = _fresh(db)
    g.set_bf_controller(0, 1)
    foe = put(g, db, 1, "Forecaster", ("bf", 0))
    _cast(g, db, 0, "Possession", lambda d: foe if d.kind in ("choose", "choose_many") and foe in d.options else None)
    assert g.objects[foe].controller == 0 and g.objects[foe].location == ("base", 0)


def test_ekko_recurrent_recycles_itself_to_ready_your_runes(db):
    g = _fresh(db)
    ek = put(g, db, 0, "Ekko, Recurrent", ("base", 0))
    for r in g.players[0].runes:
        g.objects[r].exhausted = True
    g.do_kill([ek], Context(0))
    settle(g)
    assert g.objects[ek].zone == "deck" and g.players[0].runes
    assert not any(g.objects[r].exhausted for r in g.players[0].runes)


def test_ocean_drake_can_return_any_non_dragon_unit(db):
    g = _fresh(db)
    foe = put(g, db, 1, "Forecaster", ("base", 1))
    offered = []

    def pick(d):
        if d.kind == "yesno":
            return True
        if d.kind in ("choose", "choose_many") and foe in d.options:
            offered.append(d.options)
            return foe
        return None
    _cast(g, db, 0, "Ocean Drake", pick)
    assert g.objects[foe].zone == "hand"


def test_ravenbloom_prefect_banishes_itself_to_banish_an_opponents_gear(db):
    g = _fresh(db)
    pf = put(g, db, 0, "Ravenbloom Prefect", ("base", 0))
    gold = g.play_token(1, "Gold", ("base", 1), Context(1))
    _drive(g, pick=lambda d: True if d.kind == "yesno" else None)
    assert g.objects[pf].zone == "banish" and g.objects[gold].zone != "board"


def test_royal_entourage_exhausts_a_legend(db):
    g = _fresh(db)
    leg = next(u for u, o in g.objects.items() if o.zone == "board" and o.location == ("legend", 1))
    g.objects[leg].exhausted = False

    def pick(d):
        if any(lab.startswith("exhaust a legend") for lab in d.labels):
            return next(o for o, lab in zip(d.options, d.labels) if lab.startswith("exhaust a legend"))
        if d.kind in ("choose", "choose_many") and leg in d.options:
            return leg
        return None
    _cast(g, db, 0, "Royal Entourage", pick)
    assert g.objects[leg].exhausted


def test_first_move_triggers_miss_fortune_and_blade_twirler(db):
    g = _fresh(db)
    mf = put(g, db, 0, "Miss Fortune, Captain", ("base", 0))
    bt = put(g, db, 0, "Blade Twirler", ("base", 0))
    rune = g.players[0].runes[0]
    g.objects[rune].exhausted = True
    trash0 = len([o for o in g.objects.values() if o.zone == "trash" and o.owner == 1])
    g.do_move([mf, bt], ("bf", 0), Context(0))
    players = []

    def pick(d):
        if d.kind == "pick_many" and (rune,) in d.options:
            return (rune,)
        if d.kind == "choose_player":
            players.append(list(d.options))
            return 1
        return None
    settle(g, picks=()) if False else _drive(g, pick=pick)
    assert not g.objects[rune].exhausted
    assert players == [[0, 1]]                                       # "choose a player": either one


# ----------------------------------------------------------------------------- 2026-11-08 10:20 run: unset variables
def test_that_player_is_the_player_whose_beginning_phase_it_is(db):
    # "At the start of each player's first Beginning Phase, that player gains 1 point / channels 1 rune." "That player"
    # was never stored, so the battlefield's controller got it (P0, if they took it on turn 1, scored on P1's turn).
    for name in ("The Arena's Greatest", "Obelisk of Power"):
        g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
        g.objects[g.battlefields[0].uid].defn = _card(db, name)
        g.set_bf_controller(0, 0)
        g.restruct()
        pts, runes = [p.points for p in g.players], [len(p.runes) for p in g.players]
        g.run()
        g.choose(("end_turn",))
        _drive(g, stop=lambda d: g.turn_player == 1 and g.phase == "main" and d.kind == "action" and not g.chain)
        if name == "The Arena's Greatest":
            assert g.players[0].points == pts[0] and g.players[1].points >= pts[1] + 1
        else:
            assert len(g.players[0].runes) == runes[0]
            assert len(g.players[1].runes) >= runes[1] + 3            # 2 channelled + 1 from Obelisk (3 on their 1st turn: +1)


def test_lillia_plays_the_sprite_where_she_moved_from(db):
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    li = put(g, db, 0, "Lillia, Fae Fawn", ("bf", 0))
    g.do_move([li], ("base", 0), Context(0))
    settle(g)
    sprites = [o.location for o in g.objects.values() if o.zone == "board" and o.defn.name == "Sprite"]
    assert sprites == [("bf", 0)]


def test_attack_triggers_fire_once_per_combat(db):
    """CR 383.4.e.2.a: a unit that loses and regains the Attacker designation in one combat doesn't attack again;
    a unit that joins the combat late attacks once (CR 466.2.c.3.a)."""
    g = _fresh(db)
    a = put(g, db, 0, "Thousand-Tailed Watcher", ("bf", 0))
    d = put(g, db, 1, "Thousand-Tailed Watcher", ("bf", 0))
    seen = []
    real = g.emit
    g.emit = lambda kind, **kw: (seen.append((kind, kw.get("uid"))), real(kind, **kw))[1]
    g.battlefields[0].contested_by = 0
    g._begin_showdown(0)
    assert g.combat is not None and g.objects[a].designation == "attacker"
    assert seen.count(("attack", a)) == 1 and seen.count(("defend", d)) == 1
    g.objects[a].location = "base"          # leaves the combat ...
    g._cleanup_once()
    assert g.objects[a].designation is None
    g.objects[a].location = ("bf", 0)       # ... and comes back: no new attack trigger
    g._cleanup_once()
    assert g.objects[a].designation == "attacker"
    assert seen.count(("attack", a)) == 1
    late = put(g, db, 0, "Thousand-Tailed Watcher", ("bf", 0))
    g._cleanup_once()
    assert g.objects[late].designation == "attacker" and seen.count(("attack", late)) == 1


def test_choose_a_friendly_unit_triggers_once_per_friendly_unit(db):
    """'When you choose a friendly unit' triggers for each friendly unit a spell chooses, and never for a spell that
    chooses only enemies (Blade Dancer's auto-script fired on any target)."""
    g = main_phase(db, [_deck(db, "irelia_blade_dancer"), _deck(db, "riven_exile")])
    _clear_bfs(g, db)
    a, b = put(g, db, 0, "Forecaster", "base"), put(g, db, 0, "Forecaster", "base")
    dancer = put(g, db, 0, "Blade Dancer", "base")
    foe = put(g, db, 1, "Forecaster", ("bf", 0))
    asks = []

    def pick(d):
        if d.kind == "yesno":
            asks.append(d.labels[0])
            return False
        return None
    _cast(g, db, 0, "Charm", lambda d: foe if d.kind == "choose" and foe in d.options else pick(d))
    assert asks == []                                   # Charm chose only an enemy unit
    first = []
    _cast(g, db, 0, "Defiant Dance", lambda d: (first.append(1) or a) if d.kind == "choose" and a in d.options and not first
          else (b if d.kind == "choose" and b in d.options else pick(d)))
    irelia = [x for x in asks if "Irelia" in x]
    assert len(irelia) == 2                             # one Irelia trigger per chosen friendly unit
    assert len(asks) == 4                               # and one Blade Dancer trigger per chosen friendly unit


def test_countered_flow_spell_is_banished(db):
    """CR 829.1.b.1: a spell played for its Flow cost is banished if it leaves the chain any way other than its own
    execution, so a countered Lightning Rush must not go back to the trash to be played again."""
    g = main_phase(db, [_deck(db, "kennen_tempest"), _deck(db, "riven_exile")])
    _clear_bfs(g, db)
    u = give(g, 0, "Lightning Rush", db)
    g._to_zone(g.objects[u], "trash")
    for r in list(g.players[0].rune_deck)[:6]:
        g.players[0].rune_deck.remove(r)
        g.players[0].runes.append(r)
        g.objects[r].zone = "board"
    _ready_runes(g, 0)
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == u))
    _drive(g, stop=lambda d: any(it.uid == u and it.finalized for it in g.chain))
    item = next(it for it in g.chain if it.uid == u)
    assert item.ctx.played_from == "trash"
    assert g.do_counter(item.id)
    assert g.objects[u].zone == "banish"


def test_hard_bargain_repeat_on_one_spell_and_never_itself(db):
    """Hard Bargain ([Repeat] [2], "Counter a spell unless its controller pays [2]"): it can't choose itself while it is
    being played (only finalized spells on the chain, CR 355.9.a.2), and once its first execution counters the spell,
    the repeat has nothing to counter, so nobody is asked to pay again (CR 820.1.d.2)."""
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "kennen_tempest")])
    _clear_bfs(g, db)
    put(g, db, 0, "Forecaster", "base")
    s, hb = give(g, 0, "Discipline", db), give(g, 1, "Hard Bargain", db)
    for p in (0, 1):
        for r in list(g.players[p].rune_deck)[:8]:
            g.players[p].rune_deck.remove(r)
            g.players[p].runes.append(r)
            g.objects[r].zone = "board"
        _ready_runes(g, p)
    g.run()
    g.choose(("play", s))
    chooses, asked = [], []
    for _ in range(80):
        d = g.run()
        if d is None or (d.kind == "action" and not g.chain):
            break
        if d.player == 1 and d.kind == "action" and ("play", hb) in d.options:
            g.choose(("play", hb))
        elif d.player == 1 and d.kind == "additional_cost":
            g.choose(True)                                   # pay Repeat
        elif d.player == 1 and d.kind == "choose":
            chooses.append(list(d.options))
            g.choose(s)
        elif d.player == 0 and d.kind == "pay" and "decline" in d.options:
            asked.append(1)
            g.choose("decline")
        else:
            g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert all(hb not in opts for opts in chooses)
    assert g.objects[s].zone == "trash"                      # countered by the first execution
    assert len(asked) == 1                                   # the repeat found no spell and asked nothing


def test_not_so_fast_counters_the_ability_that_chooses_my_unit(db):
    """Not So Fast ("Counter an enemy spell or ability that chooses a friendly unit or gear"): when one enemy source has
    two abilities on the chain, it counters the one that chose my unit, not just the first one from that source."""
    from riftsim.core.objects import ChainItem
    from riftsim.core.vm import Context
    g = _fresh(db, "irelia_blade_dancer")
    mine = put(g, db, 0, "Forecaster", "base")
    theirs = put(g, db, 1, "Forecaster", ("base", 1))
    src = put(g, db, 1, "Forecaster", ("base", 1), exclude=(theirs,))
    items = []
    for i, tgt in enumerate((theirs, mine)):            # older item chooses their own unit, newer one chooses mine
        it = ChainItem(900 + i, "ability", 1, uid=src, label=f"ability {i}")
        it.cost, it.finalized, it.ctx, it.code = {"energy": 0, "power": []}, True, Context(1, src), []
        it.ctx.vars["t"] = tgt
        it.ctx.vars["__targets"] = [("t", None)]
        g.chain.append(it)
        items.append(it)
    g.priority = 0
    _cast(g, db, 0, "Not So Fast", lambda d: src if d.kind == "choose" and src in d.options else None)
    assert items[1].countered and not items[0].countered


def test_repeat_pays_deflect_again_for_its_second_choice(db):
    """Deflect is paid "for each time they choose [me]" (CR 809.1.c): Blood Rush with [Repeat] choosing an enemy
    Tianna Crownguard ([Deflect]) for both executions pays [A] twice, not once."""
    g = _fresh(db, "akali_rogue")
    tianna = put(g, db, 1, "Tianna Crownguard", ("base", 1))
    n = len(g.events)

    def pick(d):
        if d.kind == "choose" and tianna in d.options:
            return tianna
        if d.kind == "additional_cost":
            return True
        if d.kind == "pay":
            return d.options[0]
        return None
    _cast(g, db, 0, "Blood Rush", pick)
    power = sum(len(e["power"]) for e in g.events[n:] if e["kind"] == "pay" and e["player"] == 0)
    assert power == 2                                  # Blood Rush has no Power cost: both are Deflect


def test_repeat_choices_count_as_chosen(db):
    """Both executions' choices are made while playing a Repeat spell (CR 820.2), so "When you choose a friendly unit"
    (Irelia, Blade Dancer) triggers for the repeat's unit too, not only for the first execution's."""
    g = main_phase(db, [_deck(db, "irelia_blade_dancer"), _deck(db, "riven_exile")])
    _clear_bfs(g, db)
    a, b = put(g, db, 0, "Forecaster", "base"), put(g, db, 0, "Forecaster", "base")
    order, asks = [a, b], []

    def pick(d):
        if d.kind == "choose" and order and order[0] in d.options:
            return order.pop(0)
        if d.kind == "additional_cost":
            return True
        if d.kind == "yesno":
            asks.append(d.labels[0])
            return False
        return None
    _cast(g, db, 0, "Feral Strength", pick)
    assert sum("Irelia" in x for x in asks) == 2


def test_hidden_guards_plays_its_sand_soldier_at_that_battlefield(db):
    """CR 811.1.d.5: a hidden spell that plays a unit plays it at the battlefield it was hidden at. Guards! ("Play a
    2 [M] Sand Soldier unit token") played from facedown used to offer base or any battlefield you control."""
    g = _fresh(db, "azir_emperor")
    g.battlefields[0].controller = g.battlefields[1].controller = 0
    put(g, db, 0, "Forecaster", ("bf", 0))
    put(g, db, 0, "Forecaster", ("bf", 1))
    u = give(g, 0, "Guards!", db)
    assert g.do_hide(0, u, ("bf", 1))
    g.objects[u].facedown_turn = g.turn - 1              # hidden last turn: it may be played now
    _ready_runes(g, 0)
    g.restruct()
    d = g.run()
    opt = next(o for o in d.options if o[0] == "play" and o[1] == u)
    g.choose(opt)
    _drive(g, pick=lambda d: False if d.kind == "yesno" else None)
    toks = [o for o in g.objects.values() if o.zone == "board" and o.defn.name == "Sand Soldier"]
    assert [o.location for o in toks] == [("bf", 1)]


def _set_runes(g, db, p, spec):
    """Give player p exactly these runes: [(domain, exhausted)]."""
    rdefs = {c.domains[0]: c for c in db if c.type == "rune" and len(c.domains) == 1}
    ps = g.players[p]
    while len(ps.runes) < len(spec):
        r = ps.rune_deck.pop(0)
        ps.runes.append(r)
        g.objects[r].zone = "board"
    for r in ps.runes[len(spec):]:
        ps.runes.remove(r)
        ps.rune_deck.append(r)
        g.objects[r].zone = "rune_deck"
    for r, (dom, ex) in zip(ps.runes, spec):
        o = g.objects[r]
        o.defn, o.domain, o.exhausted = rdefs[dom], dom, ex
    g.pending = None
    g.restruct()


def _play_from_hand(g, p, u, pick):
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == u and (len(o) < 3 or o[2][0] == "base")))
    seen = []

    def wrap(d):
        seen.append(d)
        return pick(d)
    _drive(g, pick=wrap)
    return seen


def test_ezreal_reduces_an_optional_cost_by_1_or_a_power_the_players_pick(db):
    """Ezreal, Prodigy: "Optional additional costs you pay cost [1] or [A] less." The player picks, so Blast Corps
    Cadet's [1][Fury] can cost [Fury] or [1]. It always took the power off, so with only an exhausted rune left to
    recycle (power but no energy) the [1] was demanded and the additional cost was never offered."""
    g = _fresh(db, "kennen_tempest")
    put(g, db, 0, "Ezreal, Prodigy", "base")
    assert g.optional_cost_variants(0, 1, ["fury"]) == [(1, []), (0, ["fury"])]
    enemy = put(g, db, 1, "Forecaster", ("bf", 0))
    cadet = give(g, 0, "Blast Corps Cadet", db)
    _set_runes(g, db, 0, [("fury", False), ("fury", False), ("fury", True)])
    n = len(g.events)
    seen = _play_from_hand(g, 0, cadet, lambda d: True if d.kind == "additional_cost" else
                           (enemy if d.kind == "choose" and enemy in d.options else None))
    assert any(d.kind == "additional_cost" for d in seen)
    pays = [e for e in g.events[n:] if e["kind"] == "pay" and e["player"] == 0]
    assert sum(e["energy"] for e in pays) == 2 and sum(len(e["power"]) for e in pays) == 1   # [2] + [Fury]
    assert g.objects[enemy].damage == 2 or g.objects[enemy].zone != "board"

    # three ready runes: both ways are offered ([1] less: exhaust 3; [Fury] less: exhaust 2, recycle 1)
    g = _fresh(db, "kennen_tempest")
    put(g, db, 0, "Ezreal, Prodigy", "base")
    cadet = give(g, 0, "Blast Corps Cadet", db)
    _set_runes(g, db, 0, [("fury", False)] * 3)
    pays = []
    _play_from_hand(g, 0, cadet, lambda d: True if d.kind == "additional_cost" else
                    (pays.append(d) or d.options[0] if d.kind == "pay" else None))
    plans = pays[0].options
    assert any(not any(a[0] == "rc" for a in pl[0]) for pl in plans if pl != "decline")
    assert any(any(a[0] == "rc" for a in pl[0]) for pl in plans if pl != "decline")


def test_pay_x_as_an_additional_cost_is_paid_with_the_cost(db):
    """CR 357: additional costs are added to the total cost and paid together. Sea Monkey's "you may pay [1] as an
    additional cost" was paid on its own first, so with exactly [2] the player could pay the [1] and then not afford
    the card (it left the chain). It is only offered when [3] can be paid, and paying it still buffs Sea Monkey."""
    g = _fresh(db, "kennen_tempest")
    sm = give(g, 0, "Sea Monkey", db)
    _set_runes(g, db, 0, [("body", False)] * 2)
    seen = _play_from_hand(g, 0, sm, lambda d: True if d.kind in ("additional_cost", "yesno") else None)
    assert not any(d.kind in ("additional_cost", "yesno") for d in seen)
    assert g.objects[sm].zone == "board" and not g.objects[sm].buffs

    g = _fresh(db, "kennen_tempest")
    sm = give(g, 0, "Sea Monkey", db)
    _set_runes(g, db, 0, [("body", False)] * 3)
    seen = _play_from_hand(g, 0, sm, lambda d: True if d.kind == "additional_cost" else None)
    assert any(d.kind == "additional_cost" for d in seen)
    assert g.objects[sm].zone == "board" and g.objects[sm].buffs
    assert all(g.objects[r].exhausted for r in g.players[0].runes)


def test_vex_apathetic_only_stops_its_controller_moving_the_unit(db):
    """Vex, Apathetic: "When an opponent plays a unit while I'm at a battlefield, [Stun] it. They can't move it this
    turn." Only that opponent is locked: Vex's controller may still move it with Charm ("Move an enemy unit")."""
    g = _fresh(db, "master_yi_wuju")             # calm runes for Charm
    put(g, db, 0, "Vex, Apathetic", ("bf", 0))
    tok = g.play_token(1, "Recruit", ("base", 1), Context(1))
    settle(g)
    assert g.objects[tok].stunned
    assert not g.valid_destination(tok, ("bf", 1), standard=True)          # its controller can't move it
    assert not g.valid_destination(tok, ("bf", 1), mover=1)
    assert g.valid_destination(tok, ("bf", 1), mover=0)
    _cast(g, db, 0, "Charm", lambda d: tok if d.kind == "choose" and tok in d.options else
          (("bf", 1) if d.kind == "choose_location" else None))
    assert g.objects[tok].location == ("bf", 1)


def test_rhasa_played_from_the_trash_does_not_count_itself(db):
    """Rhasa the Sunderer ("I cost [1] less for each card in your trash"): played from the trash with Last Rites, it
    moves to the chain before its cost is set (CR 354.1, 357), so it is not one of the cards in your trash."""
    g = _fresh(db, "kennen_tempest")
    rh = give(g, 0, "Rhasa the Sunderer", db)
    base = g.objects[rh].base_defn().energy
    others = [give(g, 0, "Gust", db) for _ in range(2)]
    for u in others:
        g._to_zone(g.objects[u], "trash")
    assert g.card_cost(0, rh, "hand")[0] == max(0, base - 2)
    g._to_zone(g.objects[rh], "trash")
    assert g.card_cost(0, rh, "trash")[0] == max(0, base - 2)


def test_cull_the_weak_each_player_picks_as_it_resolves(db):
    """Cull the Weak ("Each player kills one of their units") doesn't target (CR 355.10.e): each player, the caster
    too, picks as it resolves. It was chosen while playing, so it couldn't be played without a unit of your own, and
    the picks were locked before the opponent could respond."""
    g = _fresh(db, "viktor_herald")
    a, b = put(g, db, 1, "Forecaster", ("base", 1)), put(g, db, 1, "Forecaster", ("base", 1))
    picks = []

    def pick(d):
        if d.kind == "choose" and b in d.options:
            picks.append(d.player)
            return b
        return None
    _cast(g, db, 0, "Cull the Weak", pick)                # P0 has no units: still playable
    assert picks == [1]
    assert g.objects[b].zone == "trash" and g.objects[a].zone == "board"

    g = _fresh(db, "viktor_herald")
    mine = put(g, db, 0, "Forecaster", ("base", 0))
    theirs = put(g, db, 1, "Forecaster", ("base", 1))
    item = []

    def watch(d):
        if d.kind == "action" and g.chain and not item:
            item.append(dict(g.chain[-1].ctx.vars))          # nothing picked while it is on the chain
        return None
    _cast(g, db, 0, "Cull the Weak", watch)
    assert item and "__k1" not in item[0] and "__k2" not in item[0]
    assert g.objects[mine].zone == "trash" and g.objects[theirs].zone == "trash"


def _cast_with(g, db, p, name, runes, pick):
    u = give(g, p, name, db)
    _set_runes(g, db, p, runes)
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == u))
    _drive(g, pick=pick)
    return u


def test_next_spell_bonus_damage_goes_to_that_spells_every_deal(db):
    """Ravenborn Tome: "The next spell you play this turn deals 1 Bonus Damage." It belongs to the next spell played
    (CR 2955 example): each of Falling Star's two Deal actions gets it, and a spell that deals nothing still uses it up.
    It was spent by the first Deal of any source (an ability's Deal wasted it) and given to one Deal only."""
    from riftsim.core import ops as O
    tome = _card(db, "Ravenborn Tome")
    assert any(isinstance(i, O.DelayedPassive) and i.kind == "bonus_damage" for a in tome.abilities for i in a.code)
    g = _fresh(db, "akali_rogue")
    a, b = put(g, db, 1, "Rhasa the Sunderer", ("base", 1)), put(g, db, 1, "Rhasa the Sunderer", ("base", 1))
    g.add_turn_effect(Context(0, None), "bonus_damage", {"amount": 1, "spell_only": True}, uses=1)   # what the Tome does
    order = [a, b]
    _cast_with(g, db, 0, "Falling Star", [("fury", False)] * 4,
               lambda d: order.pop(0) if d.kind == "choose" and order and order[0] in d.options else None)
    assert (g.objects[a].damage, g.objects[b].damage) == (4, 4)

    g = _fresh(db, "akali_rogue")
    a = put(g, db, 1, "Rhasa the Sunderer", ("base", 1))
    g.add_turn_effect(Context(0, None), "bonus_damage", {"amount": 1, "spell_only": True}, uses=1)
    _cast_with(g, db, 0, "Discipline", [("calm", False)] * 4, lambda d: None)      # deals nothing, still the next spell
    _cast_with(g, db, 0, "Falling Star", [("fury", False)] * 4, lambda d: a if d.kind == "choose" and a in d.options else None)
    assert g.objects[a].damage == 6


def test_that_battlefield_in_a_trigger_is_the_events_battlefield(db):
    """Irresistible Faefolk ("When I move to a battlefield, you may move an enemy unit to that battlefield"), Vex,
    Mocking and Exemplar of Demacia read "that battlefield" from a variable nothing set, so the move went nowhere."""
    for name in ("Irresistible Faefolk", "Vex, Mocking", "Exemplar of Demacia"):
        assert any(getattr(a, "store", {}).get("loc") == "__bl" for a in _card(db, name).abilities), name
    g = _fresh(db, "sett_the_boss")
    f = put(g, db, 0, "Irresistible Faefolk", ("base", 0))
    e = put(g, db, 1, "Forecaster", ("base", 1))
    moved = []
    g.pending = None
    g.restruct()
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "move" and f in o[1] and o[-1] == ("bf", 0)))
    for _ in range(40):
        d = g.run()
        if any(ev["kind"] == "move" and ev.get("uid") == e for ev in g.events):
            moved.append(True)
            break
        if d is None or (d.kind == "action" and not g.chain):
            break
        g.choose(True if d.kind == "yesno" else (e if d.kind == "choose" and e in d.options else
                 (("pass",) if ("pass",) in d.options else d.options[0])))
    assert moved


def test_you_may_pay_to_affect_a_unit_chooses_it_as_the_trigger_goes_on_the_chain(db):
    """Kennen, Keeper of Balance: "When you play me or I attack, you may pay [2] to [Stun] a unit." The unit is a
    target, chosen as the trigger goes on the chain and independently of the decision to pay (CR 355.5, 355.12,
    403.2); it was picked at resolution after paying, so nobody could respond to it. Same for Icevale Archer,
    Sinister Poro, Mask Mother, Portable Portal and Exemplar of Demacia."""
    for name in ("Kennen, Keeper of Balance", "Icevale Archer", "Sinister Poro", "Mask Mother", "Portable Portal",
                 "Exemplar of Demacia"):
        trig = next(a for a in _card(db, name).abilities if getattr(a, "targets", None) is not None and a.targets)
        assert any(type(i).__name__ == "Choose" for i in trig.targets), name
    g = _fresh(db, "viktor_herald")
    enemy = put(g, db, 1, "Forecaster", ("base", 1))
    kennen = give(g, 0, "Kennen, Keeper of Balance", db)
    _set_runes(g, db, 0, [("chaos", False)] * 7)
    order = []

    def pick(d):
        if d.kind == "choose" and enemy in d.options:
            order.append(("choose", bool(g.chain)))
            return enemy
        if d.kind == "yesno":
            order.append(("yesno", bool(g.chain)))
            return True
        return None
    _play_from_hand(g, 0, kennen, pick)
    assert [k for k, _ in order] == ["yesno", "choose"]       # the may, then the target, both as it goes on the chain
    assert g.objects[enemy].stunned


def test_modes_and_their_targets_are_chosen_as_the_ability_goes_on_the_chain(db):
    """CR 355.3 / 403.2: the mode of a "choose one" ability is chosen as it is put on the chain, then that mode's
    targets (355.5). Udyr, Wildman's "Spend my buff: Choose one ..." asked for the mode and the unit only when it
    resolved, after both players had passed, so the opponent could never see what it would do."""
    g = _fresh(db, "sett_the_boss")
    udyr = put(g, db, 0, "Udyr, Wildman", ("base", 0))
    g.objects[udyr].buffs = 1
    enemy = put(g, db, 1, "Forecaster", ("bf", 0))
    put(g, db, 1, "Forecaster", ("bf", 0), exclude=(enemy,))
    g.pending = None
    g.restruct()
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "activate" and o[1] == udyr))
    order = []

    def pick(d):
        if d.kind == "mode":
            order.append("mode")
            return next(o for o, lab in zip(d.options, d.labels) if lab.startswith("Stun"))
        if d.kind == "choose" and enemy in d.options:
            order.append("choose")
            return enemy
        if d.kind == "action" and ("pass",) in d.options and g.chain:
            order.append("pass")
        return None
    _drive(g, pick=pick)
    assert order[:2] == ["mode", "choose"] and "pass" in order[2:]
    assert g.objects[enemy].stunned
    # with no unit at a battlefield, the Deal and Stun modes can't choose a target, so they aren't offered (CR 355.8)
    g = _fresh(db, "sett_the_boss")
    udyr = put(g, db, 0, "Udyr, Wildman", ("base", 0))
    g.objects[udyr].buffs = 1
    g.pending = None
    g.restruct()
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "activate" and o[1] == udyr))
    d = g.run()
    assert d.kind == "mode" and d.labels == ["Ready me", "Give me [Ganking] this turn"]


def test_a_leading_you_may_is_decided_and_its_cost_paid_as_the_trigger_goes_on_the_chain(db):
    """CR 383.3.a: "When ..., you may ..." is decided as the trigger is finalized; declining removes it from the chain
    (it never triggered). CR 383.3.b: a cost right after that "you may" (Kennen, Keeper of Balance: "you may pay [2]
    to [Stun] a unit") is the trigger's base cost, paid then. Both used to happen at resolution."""
    for accept in (False, True):
        g = _fresh(db, "viktor_herald")
        enemy = put(g, db, 1, "Forecaster", ("base", 1))
        kennen = give(g, 0, "Kennen, Keeper of Balance", db)
        _set_runes(g, db, 0, [("chaos", False)] * 7)
        n = len(g.events)
        _play_from_hand(g, 0, kennen, lambda d: accept if d.kind == "yesno" else
                        (enemy if d.kind == "choose" and enemy in d.options else None))
        evs = g.events[n:]
        trig = [e for e in evs if e["kind"] == "trigger" and e.get("source") == kennen]
        assert len(trig) == 1
        tid = trig[0]["item"]
        kinds = [(e["kind"], e.get("item"), e.get("energy")) for e in evs]
        if accept:
            fin = kinds.index(("finalized", tid, None))
            res = next(i for i, k in enumerate(kinds) if k[0] == "resolve" and k[1] == tid)
            pay = next(i for i, k in enumerate(kinds) if k[0] == "pay" and k[2] == 2)
            assert pay < fin < res and g.objects[enemy].stunned
        else:
            assert not any(k[1] == tid and k[0] in ("finalized", "resolve") for k in kinds)
            assert ("trigger_declined", tid, None) in kinds and not g.objects[enemy].stunned


def test_you_may_exhaust_me_is_paid_as_the_trigger_goes_on_the_chain(db):
    """CR 383.3.b: "you may exhaust me [and pay [A]] to ..." makes exhausting the source the trigger's base cost, paid as
    it is finalized (Irelia, Blade Dancer; also Rek'Sai, Void Burrower, Vex, Gloomist, Nasus' Curator of the Sands, Sivir,
    Renata, Exemplar of Demacia). It used to be paid at resolution, so the legend stayed ready on the chain."""
    for name in ("Rek'sai, Void Burrower", "Gloomist", "Curator of the Sands", "Irelia, Blade Dancer", "Exemplar of Demacia"):
        trig = next(a for a in _card(db, name).abilities if type(a).__name__ == "Triggered" and a.targets)
        assert any(type(i).__name__ == "Exhaust" for i in trig.targets), name
    g = _fresh(db, "irelia_blade_dancer")
    legend = next(u for u, o in g.objects.items() if o.zone == "board" and o.location == ("legend", 0))
    unit = put(g, db, 0, "Forecaster", ("base", 0))
    g.objects[unit].exhausted = True
    n = len(g.events)
    _cast_with(g, db, 0, "Discipline", [("calm", False)] * 4,
               lambda d: True if d.kind == "yesno" else (unit if d.kind == "choose" and unit in d.options else None))
    evs = g.events[n:]
    tid = next(e["item"] for e in evs if e["kind"] == "trigger" and e.get("source") == legend)
    kinds = [(e["kind"], e.get("uid"), e.get("item")) for e in evs]
    ex = kinds.index(("event:exhaust", legend, None))
    fin = kinds.index(("finalized", None, tid))
    assert ex < fin and not g.objects[unit].exhausted and g.objects[legend].exhausted


def test_an_if_right_after_the_trigger_condition_is_not_checked_again_on_resolution(db):
    """CR 383.2.a.1: "When you play me, if you control 7 or more runes, ..." (Tomb-Raider Barbara): the "if" is part
    of the trigger condition. Once the trigger is on the chain it resolves even if the runes drop below 7 (Sona's
    example in the rules). Several hand scripts checked the condition again on resolution (Barbara, Kha'Zix, Shen,
    Swain, Poppy, Jarvan IV, Cosmic Vista, Poro Herder, Patched Porobot, Dropboarder)."""
    g = _fresh(db, "nasus_curator")
    gear = put(g, db, 1, "Long Sword", ("base", 1))
    barbara = give(g, 0, "Tomb-Raider Barbara", db)
    _set_runes(g, db, 0, [("calm", False)] * 4 + [("calm", True)] * 4)
    done = []

    def pick(d):
        if g.chain and any(it.kind == "trigger" and it.uid == barbara for it in g.chain) and not done:
            ps = g.players[0]
            while len(ps.runes) > 6:              # "in response": two runes leave
                r = ps.runes.pop()
                ps.rune_deck.append(r)
                g.objects[r].zone = "rune_deck"
            g.restruct()
            done.append(True)
        return gear if d.kind == "choose" and gear in d.options else None
    _play_from_hand(g, 0, barbara, pick)
    assert done and len(g.players[0].runes) == 6
    assert g.objects[gear].zone == "trash"
    for name in ("Shen, Scourge of Shadows", "Shen, Leader of the Kinkou Order", "Swain, Visionary", "Poppy, Paragon",
                 "Jarvan IV, Martial Paragon", "Cosmic Vista", "Poro Herder", "Patched Porobot", "Dropboarder",
                 "Kha'Zix, Mutating Horror"):
        trig = [a for a in _card(db, name).abilities if type(a).__name__ == "Triggered"][-1]
        assert trig.filt is not None and not any(type(i).__name__ == "If" for i in trig.effect), name


def test_a_unit_dying_with_another_does_not_see_its_death(db):
    """CR 383.2.c.2: "When another friendly unit dies, ..." (Viktor, Leader) doesn't trigger when Viktor dies at the
    same time (the rules' own example). It did when the other unit happened to be killed first in the batch."""
    def recruits(g):
        return sum(1 for o in g.objects.values() if o.zone == "board" and o.defn.name == "Recruit")
    for order in (0, 1):
        g = _fresh(db, "viktor_herald")
        a = put(g, db, 0, "Forecaster", ("base", 0))
        v = put(g, db, 0, "Viktor, Leader", ("base", 0))
        g.do_kill([a, v] if order == 0 else [v, a], None, by="damage")
        _drive(g)
        assert recruits(g) == 0, order
        assert getattr(g, "_leaving", frozenset()) == frozenset()
    g = _fresh(db, "viktor_herald")
    a = put(g, db, 0, "Forecaster", ("base", 0))
    put(g, db, 0, "Viktor, Leader", ("base", 0))
    g.do_kill([a], None, by="damage")
    _drive(g)
    assert recruits(g) == 1


def test_the_first_time_a_friendly_unit_dies_counts_deaths_before_the_source_arrived(db):
    """CR 383.1/383.1.b: Wraith of Echoes ("The first time a friendly unit dies each turn, draw 1") only triggers on
    the turn's first friendly death; one that happened before Wraith was on the board still counts. Two units dying
    at the same time are one instance (it draws 1)."""
    def wraith_triggers(g, n):
        return sum(1 for e in g.events[n:] if e["kind"] == "trigger" and g.objects.get(e.get("source")) is not None
                   and g.objects[e["source"]].defn.name == "Wraith of Echoes")
    g = _fresh(db, "viktor_herald")
    a = put(g, db, 0, "Forecaster", ("base", 0))
    g.do_kill([a], None, by="damage")
    _drive(g)
    put(g, db, 0, "Wraith of Echoes", ("base", 0))
    b = put(g, db, 0, "Forecaster", ("base", 0))
    n = len(g.events)
    g.do_kill([b], None, by="damage")
    _drive(g)
    assert wraith_triggers(g, n) == 0
    g = _fresh(db, "viktor_herald")
    put(g, db, 0, "Wraith of Echoes", ("base", 0))
    a = put(g, db, 0, "Forecaster", ("base", 0))
    b = put(g, db, 0, "Forecaster", ("base", 0))
    n = len(g.events)
    g.do_kill([a, b], None, by="damage")
    _drive(g)
    assert wraith_triggers(g, n) == 1


def test_its_controller_is_the_controller_it_had_when_it_left_the_board(db):
    """Hidden Blade: "Kill a unit at a battlefield. Its controller draws 2." The unit is in the trash when the draw
    happens; its controller is the one it had on the board (last known information), not its owner. A unit you had
    taken control of made its owner draw. "Its owner channels" (Retreat) still uses the owner."""
    g = _fresh(db, "akali_rogue")
    u = put(g, db, 1, "Rhasa the Sunderer", ("bf", 0))
    g.objects[u].controller = 0                     # taken control of (Possession and the like)
    g.restruct()
    hands = [len(g.players[0].hand), len(g.players[1].hand)]
    _cast_with(g, db, 0, "Hidden Blade", [("order", False)] * 3, lambda d: u if d.kind == "choose" and u in d.options else None)
    assert g.objects[u].zone == "trash"
    assert [len(g.players[0].hand), len(g.players[1].hand)] == [hands[0] + 2, hands[1]]
    from riftsim.core.scripts.auto_grammar import parse_sentence
    instrs = parse_sentence("its owner channels 1 rune exhausted", {"tcount": 1})
    g.objects[u].temp["__lk_controller"] = 0
    c = Context(0, None)
    c.vars["t"] = u
    assert instrs[0].player(g, c) == 1


def test_the_awaken_phase_readying_triggers_when_i_become_ready(db):
    """CR 315.1.b / 416.3.a: the Awaken Phase readies with the Ready action, so "When I become ready" (Fretful Feline,
    Jayce, Hammer in Hand) and "When you choose or ready me" (Irelia, Fervent) trigger then. They never did."""
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    cat = put(g, db, 1, "Fretful Feline", ("base", 1))
    ire = put(g, db, 1, "Irelia, Fervent", ("base", 1))
    for u in (cat, ire):
        g.objects[u].exhausted = True
    g.restruct()
    base = g.chars(cat).might, g.chars(ire).might
    g.run()
    g.choose(("end_turn",))
    _drive(g, stop=lambda d: g.turn_player == 1 and g.phase == "main" and d.kind == "action" and not g.chain)
    assert not g.objects[cat].exhausted and not g.objects[ire].exhausted
    assert (g.chars(cat).might, g.chars(ire).might) == (base[0] + 2, base[1] + 1)
    # "When you ready a friendly unit" (Pirate's Haven) is about units: readying runes doesn't trigger it
    haven = [a for a in _card(db, "Pirate's Haven").abilities if type(a).__name__ == "Triggered"][0]
    g.set_bf_controller(0, 1)
    g.restruct()
    r = g.players[1].runes[0]
    assert haven.matches(g, g.battlefields[0].uid, {"kind": "ready", "uid": cat, "player": 1})
    assert not haven.matches(g, g.battlefields[0].uid, {"kind": "ready", "uid": r, "player": 1})


def test_a_combat_i_was_in_ends_even_after_a_tie_recalled_me(db):
    """Mournful Witness: "When a combat that I was in ends, empower me." After a tie the attackers are recalled before
    the combat ends; Witness was still in that combat (CR 740.2.c: it had a combat designation), so it triggers. Only
    units still at the battlefield counted."""
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    w = put(g, db, 0, "Mournful Witness", ("base", 0))
    big = put(g, db, 1, "Elnuk Herd", ("bf", 0))
    g.set_bf_controller(0, 1)
    g.objects[big].stunned = True               # deals no damage; Witness's 2 doesn't kill it: a tie
    g.bump()
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "move" and o[1] == (w,) and o[2] == ("bf", 0)))
    _drive(g)
    assert g.objects[big].zone == "board" and g.objects[w].location == ("base", 0)
    assert g.objects[w].empowered


def test_units_cant_move_to_base_is_every_unit_and_from_here_only_that_battlefield(db):
    """Minotaur Reckoner: "Units can't move to base." stops every unit (it only stopped units at Reckoner's own
    location). Vilemaw's Lair: "Units can't move from here to base." stops only units at that battlefield.
    Recalls are not moves (CR 458.3)."""
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    put(g, db, 1, "Minotaur Reckoner", ("base", 1))
    a = put(g, db, 0, "Forecaster", ("bf", 0))
    b = put(g, db, 1, "Forecaster", ("bf", 1))
    assert not g.valid_destination(a, ("base", 0)) and not g.valid_destination(b, ("base", 1))
    g.do_recall(a)
    assert g.objects[a].location == ("base", 0)
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    g.objects[g.battlefields[0].uid].defn = _card(db, "Vilemaw's Lair")
    g.bump()
    a = put(g, db, 0, "Forecaster", ("bf", 0))
    b = put(g, db, 0, "Forecaster", ("bf", 1))
    assert not g.valid_destination(a, ("base", 0)) and g.valid_destination(b, ("base", 0))


def test_zhonyas_hourglass_saves_the_unit_its_controller_picks_when_two_die_together(db):
    """Zhonya's Hourglass: "The next time a friendly unit would die, kill this instead. Recall that unit exhausted."
    When two friendly units die at the same time its controller decides which death it replaces (CR 373); it always
    saved the first one in the engine's list. Facedown (Hidden) it has no text and saves nobody."""
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    z = put(g, db, 0, "Zhonya's Hourglass", ("base", 0))
    small = put(g, db, 0, "Forecaster", ("bf", 0))
    baron = put(g, db, 0, "Baron Nashor", ("bf", 0))
    g.do_kill([small, baron])
    d = g.run()
    assert d.kind == "order_replacement" and d.player == 0 and set(d.options) == {small, baron}
    g.choose(baron)
    g.run()
    assert g.objects[small].zone == "trash" and g.objects[z].zone == "trash"
    assert g.objects[baron].location == ("base", 0) and g.objects[baron].exhausted
    # one friendly death: no question, it is saved
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    z = put(g, db, 0, "Zhonya's Hourglass", ("base", 0))
    small = put(g, db, 0, "Forecaster", ("bf", 0))
    enemy = put(g, db, 1, "Forecaster", ("bf", 1))
    g.do_kill([small, enemy])
    assert g.objects[small].location == ("base", 0) and g.objects[enemy].zone == "trash"
    assert g.objects[z].zone == "trash"
    # hidden facedown it does nothing
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    g.set_bf_controller(0, 0)
    z = give(g, 0, "Zhonya's Hourglass", db)
    assert g.do_hide(0, z, ("bf", 0))
    small = put(g, db, 0, "Forecaster", ("bf", 0))
    g.do_kill([small])
    assert g.objects[small].zone == "trash" and g.objects[z].zone == "facedown"


def _smite_on(g, db, caster, unit):
    sm = give(g, caster, "Smite", db)
    c = Context(caster, sm)
    c.vars["t"] = unit
    next(i for i in _card(db, "Smite").abilities[0].code if type(i).__name__ == "DelayedPassive").run(g, c)
    return c


def test_the_dying_units_controller_picks_which_replacement_saves_it(db):
    """Smite ("If it would die this turn, banish it instead") on a unit whose controller has Zhonya's Hourglass: both
    replace the same death, its controller picks one (CR 372), and a replaced death is no longer a death, so the other
    doesn't apply. The engine applied Zhonya's (killing it) and then Smite's banish anyway."""
    for pick_zhonya in (True, False):
        g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
        _clear_bfs(g, db)
        z = put(g, db, 1, "Zhonya's Hourglass", ("base", 1))
        a = put(g, db, 1, "Forecaster", ("bf", 0))
        c = _smite_on(g, db, 0, a)
        g.do_deal([a], 5, c)
        d = g.run()
        assert d.kind == "order_replacement" and d.player == 1 and len(d.options) == 2
        want = "Zhonya" if pick_zhonya else "Smite"
        g.choose(next(o for o, l in zip(d.options, d.labels) if want in l))
        g.run()
        if pick_zhonya:
            assert g.objects[a].location == ("base", 1) and g.objects[z].zone == "trash"
        else:
            assert g.objects[a].zone == "banish" and g.objects[z].zone == "board"
    # Guardian Angel on the unit and Zhonya's: only the picked one is spent
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    z = put(g, db, 0, "Zhonya's Hourglass", ("base", 0))
    a = put(g, db, 0, "Forecaster", ("bf", 0))
    ga = put(g, db, 0, "Guardian Angel", ("bf", 0))
    g.do_attach(ga, a)
    g.bump()
    g.do_kill([a])
    d = g.run()
    assert d.kind == "order_replacement"
    g.choose(next(o for o, l in zip(d.options, d.labels) if "Guardian" in l))
    g.run()
    assert g.objects[a].location == ("base", 0) and g.objects[ga].zone == "trash" and g.objects[z].zone == "board"


def test_stun_does_not_exhaust_and_a_stunned_unit_cant_be_stunned_again(db):
    """CR 424.1.b: a stunned unit only deals no combat damage; stunning doesn't exhaust it (Vex, Apathetic adds "They
    can't move it this turn" for that reason). The engine exhausted it, so a ready unit stunned in the main phase
    could no longer move or pay exhaust costs. CR 424.1.a.1: stunning an already stunned unit does nothing, so "When
    you stun" triggers don't fire again."""
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    u = put(g, db, 0, "Forecaster", ("base", 0))
    stuns = []
    g.do_stun(u, Context(1, None))
    assert g.objects[u].stunned and not g.objects[u].exhausted
    d = g.run()
    assert any(o[0] == "move" and o[1] == (u,) for o in d.options)      # a stunned unit may still move
    orig = g.emit

    def spy(kind, **kw):
        if kind == "stun":
            stuns.append(kw.get("uid"))
        return orig(kind, **kw)
    g.emit = spy
    g.do_stun(u, Context(1, None))
    assert stuns == []
    # nothing stops readying a stunned unit either (it stayed exhausted when an effect readied it)
    g.objects[u].exhausted = True
    assert g.do_ready(u, Context(0, None)) and not g.objects[u].exhausted and g.objects[u].stunned


def test_heal_exhaust_and_recall_is_an_exhaust_action(db):
    """Zhonya's Hourglass / Guardian Angel / Soraka: "heal it, exhaust it, and recall it". Exhausting is the Exhaust
    action (CR 415), so "When I become exhausted" (Reckless Innovator, Riven, Broken Blade) triggers; the engine set
    the flag without the event."""
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    put(g, db, 0, "Zhonya's Hourglass", ("base", 0))
    r = put(g, db, 0, "Reckless Innovator", ("bf", 0))
    seen = []
    orig = g.emit

    def spy(kind, **kw):
        seen.append((kind, kw.get("uid")))
        return orig(kind, **kw)
    g.emit = spy
    g.do_kill([r])
    assert g.objects[r].location == ("base", 0) and g.objects[r].exhausted
    assert ("exhaust", r) in seen
    d = g.run()
    assert g.chain or (d is not None and d.kind != "action")      # its trigger is waiting (mode pick or on the chain)


def test_granted_vision_triggers_once_per_instance(db):
    """Forecaster: "Your Mechs have [Vision]" (it is a Mech itself); Gemcraft Seer: "[Vision] Other friendly units have
    [Vision]". Vision is a triggered ability ("When this is played, [Predict]", CR 817.1.b), so a granted Vision
    triggers too, once per instance (817.2). Only printed Vision triggered: Kai'Sa's Forecasters never predicted."""
    from riftsim.core.game import _granted_vision
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    f = put(g, db, 0, "Forecaster", ("base", 0))
    assert sum(1 for a in g.abilities(f) if a is _granted_vision()) == 1
    put(g, db, 0, "Gemcraft Seer", ("base", 0))
    assert sum(1 for a in g.abilities(f) if a is _granted_vision()) == 2       # Mech + "other friendly units"
    _, ab = next((u, a) for u in [f] for a in g.abilities(f) if a is _granted_vision())
    assert ab.matches(g, f, {"kind": "enter", "uid": f, "player": 0})
    # playing Forecaster from hand: Vision's Predict is offered
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    fh = give(g, 0, "Forecaster", db)
    _ready_runes(g, 0)
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == fh))
    kinds = []
    _drive(g, pick=lambda d: kinds.append(d.kind) and None)
    assert "predict" in kinds


def test_granted_disarm_triggers_with_the_summed_value(db):
    """Clanging Sentry: "Your Mechs have [Disarm]." Disarm is an attack trigger (CR 831.1.d); a granted Disarm
    triggers too, once, with the summed value (831.1.d.1, 831.2: two Sentries give Disarm 2). Granted keywords were
    keyword flags only and never triggered."""
    from riftsim.core.scripts import disarm_ability, hunt_ability
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    s1 = put(g, db, 0, "Clanging Sentry", ("base", 0))
    s2 = put(g, db, 0, "Clanging Sentry", ("base", 0))
    assert g.keyword_value(s1, "disarm") == 2
    assert [a for a in g.abilities(s1) if getattr(a, "keyword", None) == "disarm"] == [disarm_ability()]
    enemy = put(g, db, 1, "Elnuk Herd", ("bf", 0))
    g.set_bf_controller(0, 1)
    g.bump()
    before = g.chars(enemy).might
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "move" and o[1] == (s1,) and o[2] == ("bf", 0)))
    _drive(g, pick=lambda d: enemy if d.kind == "choose" and enemy in d.options else None,
           stop=lambda d: g.combat is not None and g.combat.get("step") == "damage")
    assert g.chars(enemy).might == before - 2
    # printed Hunt adds up with a granted one into one trigger (CR 823.2)
    gromp = put(g, db, 0, "Voracious Gromp", ("base", 0))
    assert [a for a in g.abilities(gromp) if getattr(a, "keyword", None) == "hunt"] == [hunt_ability()]
    assert g.keyword_value(gromp, "hunt") == 3


def test_predict_puts_the_kept_cards_back_in_the_order_the_player_picks(db):
    """CR 437.1.a: "the Predicting player looks at that many cards and Recycles any number of them before putting the
    rest back on top of their Main Deck in any order." The kept cards always went back in their old order (The
    Empyrean's "[Predict] equal to its Power cost", any Predict 2+)."""
    from riftsim.core import ops as O
    from riftsim.core.vm import Frame
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "vex_gloomist")])
    deck = g.players[0].deck
    a, b, c = deck[0], deck[1], deck[2]
    g.vm_frames.append(Frame([O.Predict(3)], Context(0, None)))
    d = g.run()
    assert d.kind == "predict"
    g.choose((b,))                                   # recycle the middle one
    d = g.run()
    assert d.kind == "predict_order" and set(d.options) == {(a, c), (c, a)}
    g.choose((c, a))
    g.run()
    assert deck[:2] == [c, a] and b not in deck[:2]


def test_an_attached_cards_printed_rules_text_is_inactive(db):
    # CR 135.4 / 722 example: Spinning Axe's [Temporary] doesn't trigger while it is attached, and its [Equip] can't be
    # activated again to move it; the keyword can still be seen (135.4.a). Effect-text abilities stay (Guardian Angel).
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    u = put(g, db, 0, "Stellacorn Herder", ("base", 0))
    put(g, db, 0, "Stellacorn Herder", ("base", 0))
    axe = put(g, db, 0, "Spinning Axe", ("base", 0))
    loose = put(g, db, 0, "Long Sword", ("base", 0))
    ga = put(g, db, 0, "Guardian Angel", ("base", 0))
    g.do_attach(axe, u)
    g.do_attach(ga, u)
    _ready_runes(g, 0)
    d = g.run()
    assert any(o[0] == "activate" and o[1] == loose for o in d.options)
    assert not any(o[0] == "activate" and o[1] in (axe, ga) for o in d.options)
    assert g.has_keyword(axe, "temporary") and not g.abilities(axe)
    assert any(getattr(a, "label", "") == "Guardian Angel" for a in g.abilities(ga))
    g.choose(("end_turn",))
    _drive(g, stop=lambda d: g.turn_player == 0 and g.phase == "main" and d.kind == "action" and not g.chain,
           pick=lambda d: ("end_turn",) if ("end_turn",) in d.options and not g.chain else None)
    assert g.objects[axe].zone == "board" and g.objects[axe].attached_to == u
    g.do_detach(axe) if hasattr(g, "do_detach") else g._detach_raw(axe)
    assert any(getattr(a, "keyword", None) == "temporary" for a in g.abilities(axe))


def test_weaponmaster_can_take_an_equipment_already_attached_to_another_unit(db):
    # CR 821.1.c: Weaponmaster reads the chosen Equipment's Equip cost even though its printed text is inactive while
    # attached (135.4), and moves it to the Weaponmaster unit.
    g = main_phase(db, [_deck(db, "kaisa_void"), _deck(db, "riven_exile")])
    other = put(g, db, 0, "Stellacorn Herder", ("base", 0))
    sword = put(g, db, 0, "Long Sword", ("base", 0))
    g.do_attach(sword, other)
    adept = give(g, 0, "Sentinel Adept", db)
    _ready_runes(g, 0)
    g.restruct()
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == adept))
    _drive(g, pick=lambda d: sword if sword in d.options else (True if True in d.options else None))
    assert g.objects[sword].attached_to == adept


def _set_rune_domains(g, p, doms):
    """Make p's runes exactly the given domains, all ready."""
    runes = g.players[p].runes
    assert len(runes) >= len(doms)
    for u in runes[len(doms):]:
        g.objects[u].exhausted = True
        g.objects[u].domain = "mind"          # no test card uses Mind; exhausted runes can still be recycled
    for u, d in zip(runes, doms):
        g.objects[u].domain = d
        g.objects[u].exhausted = False
    g.pending = None
    g.restruct()


def test_multi_domain_power_pips_take_any_of_the_cards_domains(db):
    # CR 135.2.e.6.c: Defiant Dance (Calm/Chaos, [1][C]) can be paid with Chaos power; Tibbers (Fury/Chaos, two split
    # pips) with two Fury, never Fury + Body.
    from riftsim.core import payment
    g = main_phase(db, [_deck(db, "irelia_blade_dancer"), _deck(db, "riven_exile")])
    dd = give(g, 0, "Defiant Dance", db)
    e, pw = g.card_cost(0, dd, "hand")
    assert (e, pw) == (1, ["calm|chaos"])
    _set_rune_domains(g, 0, ["chaos", "chaos"])
    assert g.can_pay(0, e, pw) and payment.plans(g, 0, e, pw)
    _set_rune_domains(g, 0, ["body", "body"])
    assert not g.can_pay(0, e, pw) and not payment.plans(g, 0, e, pw)
    tib = give(g, 0, "Tibbers, Annie", db)
    e, pw = g.card_cost(0, tib, "hand")
    assert pw == ["fury|chaos", "fury|chaos"]
    assert g.can_pay(0, 0, pw) is False
    _set_rune_domains(g, 0, ["fury", "fury"])
    assert g.can_pay(0, 0, pw) and payment.plans(g, 0, 0, pw)
    _set_rune_domains(g, 0, ["fury", "body"])
    assert not g.can_pay(0, 0, pw)
    assert payment.own_power(["fury", "chaos"]) == "fury|chaos" and payment.own_power([]) == "any"


def _enemy_items(g, src, target_sets):
    from riftsim.core.objects import ChainItem
    from riftsim.core.vm import Context
    items = []
    for i, tgts in enumerate(target_sets):
        it = ChainItem(900 + i, "ability", 1, uid=src, label=f"ability {i}")
        it.cost, it.finalized, it.ctx, it.code = {"energy": 0, "power": []}, True, Context(1, src), []
        for k, t in enumerate(tgts):
            it.ctx.vars[f"t{k}"] = t
        it.ctx.vars["__targets"] = [(f"t{k}", None) for k in range(len(tgts))]
        g.chain.append(it)
        items.append(it)
    g.priority = 0
    return items


def test_repulse_counters_an_enemy_item_choosing_only_that_friendly_unit(db):
    """Repulse (Master Yi and Sett sideboards): "Choose a friendly unit at a battlefield. Counter an enemy spell or ability that
    chooses it and no other friendly unit." It was unscripted. An item choosing two of my units can't be countered."""
    def setup():
        g = _fresh(db, "master_yi_wuju")
        mine = put(g, db, 0, "Forecaster", ("bf", 0))
        other = put(g, db, 0, "Forecaster", ("bf", 0), exclude=(mine,))
        src = put(g, db, 1, "Forecaster", ("base", 1))
        return g, mine, other, src
    g, mine, other, src = setup()
    items = _enemy_items(g, src, ((mine, other), (mine,)))   # older item chooses two of my units, newer one only `mine`
    _cast(g, db, 0, "Repulse", lambda d: mine if d.kind == "choose" and mine in d.options
          else (src if d.kind == "choose" and src in d.options else None))
    assert items[1].countered and not items[0].countered
    # with only the item that chooses both of my units on the chain, Repulse can't be played
    g, mine, other, src = setup()
    _enemy_items(g, src, ((mine, other),))
    rp = give(g, 0, "Repulse", db)
    _ready_runes(g, 0)
    d = g.run()
    assert d.player == 0 and not any(o[0] == "play" and o[1] == rp for o in d.options)


def test_a_cost_at_the_start_of_a_trigger_is_paid_as_it_is_finalized(db):
    """CR 383.3.b: "Recycle me to ready your runes" (Ekko, Recurrent, the rule's own example), "banish a card from any
    trash to ..." (Gust Monk) and "exhaust me to draw 1" (Titanic Shrine) are base costs paid as the trigger is
    finalized, before anyone can respond. They were paid on resolution, so a response could stop the cost."""
    g = _fresh(db)
    ek = put(g, db, 0, "Ekko, Recurrent", ("base", 0))
    g.do_kill([ek], Context(0))
    for _ in range(10):                       # run until the Deathknell is a finalized chain item
        d = g.run()
        if g.chain and all(it.finalized for it in g.chain):
            break
        g.choose(d.options[0])
    assert g.chain and g.objects[ek].zone == "deck"          # recycled before the Deathknell resolves
    # Gust Monk with every trash empty: its trigger can't be finalized (no card to banish)
    g = _fresh(db, "irelia_blade_dancer")
    for p in g.players:
        for u in list(p.trash):
            g.objects[u].zone = "banish"
            p.trash.remove(u)
            p.banish.append(u) if hasattr(p, "banish") else None
    g.restruct()
    put(g, db, 0, "Forecaster", ("base", 0))
    gm = give(g, 0, "Gust Monk", db)
    _ready_runes(g, 0)
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == gm))
    _drive(g, pick=lambda d: True if d.kind == "additional_cost" else None)
    assert not any("Assault" in str(m.value) or m.kind == "keyword" and m.value[0] == "assault"
                   for o in g.objects.values() for m in o.mods)
    assert any(e["kind"] == "trigger_declined" for e in g.events)


def _nocturne_on_top(g, db, p, at=0):
    u = g.players[p].deck[at]
    g.objects[u].defn = next(c for c in db if c.name == "Nocturne, Horrifying")
    g.restruct()
    return u


def test_nocturne_seen_by_a_look_is_played_where_his_owner_chooses(db):
    # Errata: "As you look at or reveal me from the top of your deck, you may banish me. If you do, you may play me
    # for [A]." He is played like any unit (CR 355.2.a): to base or a battlefield his owner controls, not always base.
    from riftsim.core.vm import Frame, compile_effect
    from riftsim.core import ops as O
    g = main_phase(db, [_deck(db, "kennen_tempest"), _deck(db, "riven_exile")])
    _ready_runes(g, 0)
    g.set_bf_controller(0, 0)
    noc = _nocturne_on_top(g, db, 0, at=1)
    g.vm_frames.append(Frame(compile_effect([O.Look(3, out="looked")]), Context(0, None)))
    seen = []

    def pick(d):
        if d.kind == "seen_from_deck":
            seen.append(d.player); return "banish_play"
        if d.kind == "choose_location":
            assert ("bf", 0) in d.options and ("base", 0) in d.options
            return ("bf", 0)
    _drive(g, pick)
    assert seen == [0]
    assert g.objects[noc].zone == "board" and g.objects[noc].place == ("bf", 0)


def test_nocturne_revealed_from_the_top_is_offered_to_his_owner(db):
    # "or reveal": Blind Fury makes the opponent reveal their top card; Nocturne's owner may banish and play him, and
    # Blind Fury then has nothing of theirs to banish and play.
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "kennen_tempest")])
    _set_runes(g, db, 1, [("chaos", False)] * 2)
    noc = _nocturne_on_top(g, db, 1)
    seen = []

    def pick(d):
        if d.kind == "seen_from_deck":
            seen.append(d.player); return "banish_play"
    _cast_with(g, db, 0, "Blind Fury", [("fury", False)] * 6, pick)
    assert seen == [1]
    assert g.objects[noc].zone == "board" and g.objects[noc].controller == 1


def test_dazzling_aurora_reveals_past_a_banished_nocturne(db):
    # Reveal until a unit: a Nocturne banished as he is revealed was not revealed, so Aurora goes on to the next unit.
    g = main_phase(db, [_deck(db, "kennen_tempest"), _deck(db, "riven_exile")])
    _ready_runes(g, 0)
    put(g, db, 0, "Dazzling Aurora", ("base", 0))
    deck = g.players[0].deck
    noc = _nocturne_on_top(g, db, 0, at=0)
    nxt = next(u for u in deck[1:] if g.objects[u].base_defn().is_unit)
    settle(g)
    seen = []

    def pick(d):
        if d.kind == "seen_from_deck":
            seen.append(d.info["uid"]); return "banish"
    g.choose(("end_turn",))
    _drive(g, pick, stop=lambda d: g.turn_player == 1)
    assert seen == [noc] and g.objects[noc].zone == "banish"
    assert g.objects[nxt].zone == "board"


def test_riven_spend_my_buff_to_stun_picks_the_unit_as_the_mode_is_chosen(db):
    """Riven, Broken Blade: "When I become exhausted, choose one ... — Spend my buff to [Stun] an enemy unit."
    "[do X] to [do Y]": X is a cost, the enemy unit in Y is a target (CR 355.10.c.1), chosen with the mode as the
    trigger goes on the chain (355.5), so the opponent can answer it (Not So Fast counters abilities that choose a
    friendly unit). It was chosen at resolution, after the buff was spent."""
    g = main_phase(db, [_deck(db, "riven_exile"), _deck(db, "vex_gloomist")])
    _clear_bfs(g, db)
    rv = put(g, db, 0, "Riven, Broken Blade", ("base", 0))
    g.objects[rv].buffs = 1
    foe = put(g, db, 1, "Stellacorn Herder", ("base", 1))
    put(g, db, 1, "Stellacorn Herder", ("base", 1))         # two enemy units: the pick is a real decision
    g.restruct()
    g.do_exhaust(rv, Context(0, None))
    seen = {}

    def pick(d):
        if d.kind == "mode":
            return next(o for o, lab in zip(d.options, d.labels) if "Stun" in lab)
        if d.kind == "choose" and foe in d.options:
            seen["at"] = "finalize" if not any(it.finalized for it in g.chain if it.uid == rv) else "resolution"
            seen["buffs"] = g.objects[rv].buffs
            return foe
    _drive(g, pick)
    assert seen == {"at": "finalize", "buffs": 1}
    assert g.objects[foe].stunned and g.objects[rv].buffs == 0


def test_bedeviling_stranger_chooses_the_enemy_unit_as_the_trigger_goes_on_the_chain(db):
    """Bedeviling Stranger: "When you play me, choose a battlefield. If there are 4 or more units there, you may return
    an enemy unit there to its owner's hand." The enemy unit is a target (CR 355.10, 355.12): chosen with the
    battlefield as the trigger is finalized, not on resolution."""
    g = main_phase(db, [_deck(db, "kennen_tempest"), _deck(db, "riven_exile")])
    _clear_bfs(g, db)
    put(g, db, 0, "Traveling Merchant", ("bf", 0)); put(g, db, 0, "Traveling Merchant", ("bf", 0))
    a = put(g, db, 1, "Stellacorn Herder", ("bf", 0)); b = put(g, db, 1, "Stellacorn Herder", ("bf", 0))
    seen = {}

    def pick(d):
        if d.kind == "choose_location":
            return ("bf", 0) if ("bf", 0) in d.options else None
        if d.kind == "choose_many" and (a,) in d.options:        # up to one enemy unit there
            seen["finalized"] = any(it.finalized for it in g.chain if it.kind == "trigger")
            return (a,)
        if d.kind in ("yesno", "may"):
            return True if True in d.options else d.options[0]
    _cast(g, db, 0, "Bedeviling Stranger", pick)
    assert seen == {"finalized": False}
    assert g.objects[a].zone == "hand" and g.objects[b].zone == "board"


def test_fiora_victorious_layers_are_reapplied_until_nothing_changes(db):
    """Fiora, Victorious (4 [M]): "While I'm [Mighty], I have [Deflect], [Ganking], and [Shield]." Layers are applied
    again until nothing changes (CR 478.3): a defender with Hunting Blind's [Shield 2] is 6 [M], so Mighty, so she
    gains Deflect and Shield too (7 [M]). Her own condition only saw her printed Might and buffs. Without Shield
    from elsewhere she stays 4 [M] with none of them (CR 478.4 example)."""
    g = main_phase(db, [_deck(db, "sett_the_boss"), _deck(db, "riven_exile")])
    _clear_bfs(g, db)
    f = put(g, db, 0, "Fiora, Victorious", ("base", 0))

    def state():
        g.restruct()
        ch = g.chars(f)
        return ch.might, ch.kw("deflect"), ch.kw("shield"), bool(ch.keywords.get("ganking"))
    g.objects[f].designation = "defender"
    assert state() == (4, 0, 0, False)
    g.objects[f].buffs = 1
    assert state() == (6, 1, 1, True)              # the CR 478.4 example: 5 [M], then Shield while defending
    g.objects[f].buffs = 0
    put(g, db, 0, "Hunting Blind", ("base", 0))
    assert state() == (7, 1, 3, True)
    g.objects[f].designation = None
    assert state() == (4, 0, 2, False)             # Hunting Blind's Shield only adds Might while defending


def test_a_unit_becomes_mighty_whatever_raises_its_might(db):
    """CR 709: a unit becomes Mighty when its Might goes from under 5 to 5 or more, whatever the cause. Only mods and
    buffs announced it, so [Assault] as a unit attacks, a static (Hunting Blind's Shield while defending) or a -[M]
    effect expiring never triggered Fiora, Worthy ("When a unit you control becomes [Mighty], you may pay [Order] to
    ready it")."""
    g = main_phase(db, [_deck(db, "sett_the_boss"), _deck(db, "riven_exile")])
    _clear_bfs(g, db)
    put(g, db, 0, "Fiora, Worthy", ("base", 0))
    u = put(g, db, 0, "Fiora, Worthy", ("bf", 0))             # 3 [M]
    g.add_mod(u, "keyword", ("assault", 2), duration="turn")
    seen = []
    orig = g.emit

    def spy(kind, **kw):
        if kind == "becomes_mighty":
            seen.append(kw.get("uid"))
        return orig(kind, **kw)
    g.emit = spy
    g._cleanup_once()
    assert seen == []                                          # 3 [M] at rest
    g.objects[u].designation = "attacker"
    g.bump()
    g._cleanup_once()
    assert seen == [u]                                         # 5 [M] while attacking: becomes Mighty
    g._cleanup_once()
    assert seen == [u]                                         # already Mighty: no second event
    g.objects[u].designation = None
    g.bump()
    g._cleanup_once()
    g.objects[u].designation = "attacker"
    g.bump()
    g._cleanup_once()
    assert seen == [u, u]


def test_a_deflect_target_needs_the_tax_on_top_of_the_cost(db):
    """CR 809.1.c / 355.16: Deflect adds [A] to the cost of a spell choosing that unit, and no choice may make the
    costs unpayable. The check only asked whether the tax alone was payable: with one Fury rune, Hextech Ray ([1] and
    Fury) could choose Vex, Apathetic ([Deflect]), then failed to pay and went to the trash with no effect."""
    g = main_phase(db, [_deck(db, "sett_the_boss"), _deck(db, "kennen_tempest")])
    _clear_bfs(g, db)
    _set_runes(g, db, 0, [("fury", False)])
    vx = put(g, db, 1, "Vex, Apathetic", ("bf", 0))
    hr = give(g, 0, "Hextech Ray", db)
    d = g.run()
    assert ("play", hr) not in d.options                   # Vex is the only target and the tax can't be paid too
    other = put(g, db, 1, "Stellacorn Herder", ("bf", 1))
    g.pending = None
    d = g.run()
    assert ("play", hr) in d.options
    offered = []

    def pick(d):
        if d.kind == "choose":
            offered.extend(d.options)
    g.choose(("play", hr))
    _drive(g, pick)
    assert vx not in offered and g.objects[vx].damage == 0
    assert g.objects[hr].zone == "trash" and (g.objects[other].zone != "board" or g.objects[other].damage == 3)
    _set_runes(g, db, 0, [("fury", False), ("fury", False)])  # cost and tax both payable: Vex can be chosen
    hr2 = give(g, 0, "Hextech Ray", db)
    g.pending = None
    d = g.run()
    g.choose(("play", hr2))
    _drive(g, lambda d: vx if d.kind == "choose" and vx in d.options else None)
    assert g.objects[vx].damage == 3


# ----------------------------------------------------------------------------- 2026-11-18 00:20 run: Bonus Damage
def test_bonus_damage_is_added_once_to_the_amount_a_split_divides(db):
    # CR 715.3: with Annie, Fiery ("Your spells and abilities deal 1 Bonus Damage"), Scorched Earth's 5 damage split
    # becomes 6 damage to split, and it can now choose 6 units (355.14.c). Each part of the split used to get the bonus
    # again (5 split three ways dealt 8).
    g = _fresh(db)
    put(g, db, 0, "Annie, Fiery", ("base", 0))
    bf = ("bf", g.battlefields[0].idx)
    foes = []
    for _ in range(3):
        foes.append(put(g, db, 1, "Mountain Drake", bf, exclude=foes))
    seen = {}

    def pick(d):
        if d.kind == "choose_location":
            return bf if bf in d.options else None
        if d.kind == "choose_many":
            seen["cap"] = max(len(o) for o in d.options)
            return next(o for o in d.options if set(o) == set(foes))
        if d.kind == "split_damage":
            seen["plans"] = d.options
            return next(o for o in d.options if tuple(o) == (2, 2, 2))
        return None
    _cast_with(g, db, 0, "Scorched Earth", [("fury", False)] * 5, pick)
    assert all(sum(p) == 6 for p in seen["plans"])
    from riftsim.core import ops as O
    assert O.split_cap(5)(g, Context(0, g.players[0].deck[0])) == 6       # up to 6 targets with Annie
    assert sorted(g.objects[u].damage for u in foes) == [2, 2, 2]


def test_no_bonus_damage_when_no_damage_is_dealt(db):
    # CR 715.4: a Deal of 0 (a 0-Might unit fighting, "deal 1 for each ..." with none) deals nothing, so Annie, Fiery
    # and Void Gate add nothing to it.
    g = _fresh(db)
    put(g, db, 0, "Annie, Fiery", ("base", 0))
    foe = put(g, db, 1, "Mountain Drake", ("bf", g.battlefields[0].idx))
    g.do_deal([foe], 0, Context(0, g.players[0].deck[0]))
    assert g.objects[foe].damage == 0
    g.do_deal([foe], 1, Context(0, g.players[0].deck[0]))
    assert g.objects[foe].damage == 2


# ----------------------------------------------------------------------------- 2026-11-18 05:20 run
def _fiora_attack(db, foes, change):
    """Fiora, Peerless (4 [M]) attacks bf 0 into `foes` enemy units; `change(g, enemies)` runs while her trigger waits
    on the chain. Returns her highest Might seen during the combat."""
    g = _fresh(db)
    fi = put(g, db, 0, "Fiora, Peerless", ("base", 0))
    bf = ("bf", g.battlefields[0].idx)
    enemies = []
    for _ in range(foes):
        enemies.append(put(g, db, 1, "Mountain Drake", bf, exclude=enemies))
    base = g.chars(fi).might
    seen = {"max": base, "changed": False}
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "move" and o[1] == (fi,) and o[2] == bf))

    def pick(d):
        if g.combat is not None and g.objects[fi].zone == "board":
            seen["max"] = max(seen["max"], g.chars(fi).might)
        if not seen["changed"] and any(it.uid == fi or getattr(it, "source", None) == fi for it in g.chain):
            seen["changed"] = True
            change(g, enemies)
            return "rerun"
        return None
    _drive(g, pick=pick)
    return base, seen


def test_fiora_peerless_checks_one_on_one_as_she_attacks(db):
    # "When I attack or defend one on one, double my Might this combat." One on one is the trigger condition (CR 383.2.a,
    # 740.2.b), checked as she attacks; the hand script re-checked it on resolution. A unit joining the fight before the
    # trigger resolves doesn't stop the doubling, and killing one of two defenders in response doesn't start it.
    def add_enemy(g, enemies):
        put(g, db, 1, "Mountain Drake", g.objects[enemies[0]].location, exclude=enemies)
    base, seen = _fiora_attack(db, 1, add_enemy)
    assert seen["changed"] and seen["max"] == 2 * base

    def kill_one(g, enemies):
        g.do_kill([enemies[1]], Context(1))
    base, seen = _fiora_attack(db, 2, kill_one)
    assert not seen["changed"] and seen["max"] == base


# ----------------------------------------------------------------------------- 2026-11-18 10:20 run
def test_hidden_facebreaker_needs_its_targets_at_its_battlefield(db):
    # CR 811.1.d.2: a spell played from facedown chooses its targets at that battlefield "unless it explicitly restricts
    # targeting in such a way that makes this impossible"; with no legal target there it can't be played (811.1.d).
    # Facebreaker ("Stun a friendly unit and an enemy unit at the same battlefield") was free to pick at any battlefield
    # when its own battlefield had no friendly unit facing an enemy, because any selector condition counted as such a
    # restriction. Only "at another location" conditions (Tideturner, Evelynn, Resonating Strike) do.
    for enemy_here in (False, True):
        g = _fresh(db)
        g.set_bf_controller(0, 0)
        mine = put(g, db, 0, "Mountain Drake", ("bf", 0))
        put(g, db, 0, "Mountain Drake", ("bf", 1), exclude=[mine])
        foe_there = put(g, db, 1, "Mountain Drake", ("bf", 1))
        foe_here = put(g, db, 1, "Mountain Drake", ("bf", 0), exclude=[foe_there]) if enemy_here else None
        fb = give(g, 0, "Facebreaker", db)
        assert g.do_hide(0, fb, ("bf", 0))
        g.objects[fb].facedown_turn = g.turn - 1
        _ready_runes(g, 0)
        g.restruct()
        offered = ("play", fb) in g.legal_actions(0)
        assert offered == enemy_here
        if enemy_here:
            g.pending = None
            g.run()
            g.choose(("play", fb))
            _drive(g)
            assert g.objects[mine].stunned and g.objects[foe_here].stunned and not g.objects[foe_there].stunned


def test_hidden_tideturner_still_swaps_with_a_unit_elsewhere(db):
    # 811.1.d.3 example: Tideturner's "a unit you control at another location" can never be met at its battlefield,
    # so it chooses freely when played from facedown.
    g = _fresh(db)
    g.set_bf_controller(0, 0)
    tt = give(g, 0, "Tideturner", db)
    other = put(g, db, 0, "Mountain Drake", ("base", 0))
    assert g.do_hide(0, tt, ("bf", 0))
    g.objects[tt].facedown_turn = g.turn - 1
    _ready_runes(g, 0)
    g.restruct()
    g.pending = None
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == tt))
    _drive(g, pick=lambda d: other if d.kind == "choose" and other in d.options
           else (True if d.kind == "yesno" else None))
    assert g.objects[tt].location == ("base", 0) and g.objects[other].location == ("bf", 0)


# ----------------------------------------------------------------------------- 2026-11-18 15:20 run
def test_when_you_choose_me_needs_its_controller_to_choose(db):
    # Irelia, Fervent ("When you choose or ready me, give me +1 [M] this turn"; Master Yi and Irelia decks) and Jae Medarda
    # ("When you choose me with a spell, draw 1") triggered when an opponent chose them: an enemy Discipline gave
    # Irelia +3. "You" is the unit's controller (and Jae's needs a spell).
    for owner in (0, 1):
        g = _fresh(db)
        ire = put(g, db, owner, "Irelia, Fervent", ("base", owner))
        jae = put(g, db, owner, "Jae Medarda", ("base", owner), exclude=[ire])
        base_m = g.chars(ire).might
        hand = len(g.players[owner].hand)
        for t in (ire, jae):
            _cast_with(g, db, 0, "Discipline", [("calm", False)] * 4,
                       lambda d, t=t: t if d.kind == "choose" and t in d.options else None)
        mine = owner == 0
        assert g.chars(ire).might == base_m + 2 + (1 if mine else 0), owner
        # P0 draws 1 per Discipline; Jae's owner draws 1 more only when it's P0's own Jae
        assert len(g.players[owner].hand) - hand == (2 + 1 if mine else 0), owner


# ----------------------------------------------------------------------------- 2026-11-18 20:20 run
def test_when_you_stun_an_enemy_unit_reads_who_stunned(db):
    # Eclipse Herald ("When you stun an enemy unit, ready me and give me +1 [M] this turn") and Leona, Radiant Dawn read
    # the stunned unit's controller as "you": stunning an enemy never triggered them, an enemy stunning your unit did.
    from riftsim.core import ops as O
    for stunner, victim_side, want in ((0, 1, True), (1, 0, False), (0, 0, False)):
        g = _fresh(db)
        eh = put(g, db, 0, "Eclipse Herald", ("base", 0))
        g.objects[eh].exhausted = True
        victim = put(g, db, victim_side, "Mountain Drake", ("base", victim_side), exclude=[eh])
        m = g.chars(eh).might
        O.Stun(lambda g, c: [victim]).run(g, Context(stunner, None))
        settle(g)
        assert g.objects[victim].stunned
        assert (g.chars(eh).might == m + 1 and not g.objects[eh].exhausted) == want, (stunner, victim_side)


def test_one_or_more_stuns_trigger_once_per_stun(db):
    # Leona, Radiant Dawn: "When you stun one or more enemy units, buff a friendly unit." Two units stunned by one
    # instruction trigger it once; each stun was its own trigger.
    from riftsim.core import ops as O
    leona = next(c for c in db if c.name == "Leona, Radiant Dawn")
    ab = next(a for a in leona.abilities if type(a).__name__ == "Triggered")
    g = _fresh(db)
    me = put(g, db, 0, "Mountain Drake", ("base", 0))
    g.objects[me].defn = leona
    foes = [put(g, db, 1, "Mountain Drake", ("base", 1))]
    foes.append(put(g, db, 1, "Mountain Drake", ("base", 1), exclude=foes))
    seen = []
    orig = g.emit

    def spy(kind, **kw):
        if kind == "stun":
            seen.append(ab.matches(g, me, dict(kw, kind=kind)))
        return orig(kind, **kw)
    g.emit = spy
    O.Stun(lambda g, c: list(foes)).run(g, Context(0, None))
    assert seen == [True, False]


# ----------------------------------------------------------------------------- 2026-11-19 00:20 run
def test_akshan_gone_before_his_trigger_resolves_takes_no_control(db):
    # CR 359.3 example: "If Akshan leaves the board in reaction to his play effect, the delayed passive ability 'You
    # control it until I leave the board' will not be generated. You will not gain control of the targeted gear even
    # for a moment." The script still handed the gear over, for good (no duration to end it).
    g = _fresh(db)
    ak = put(g, db, 0, "Akshan, Mischievous", ("base", 0))
    blade = put(g, db, 1, "Doran's Blade", ("base", 1))
    g.emit("play", uid=ak, player=0, card_type="unit", paid={"add": True}, ctx=Context(0, ak))
    g.dirty = True
    g.pending = None
    killed = []

    def pick(d):
        if d.kind == "choose" and blade in d.options:
            return blade
        if not killed and g.chain and any(it.uid == ak for it in g.chain if it.finalized):
            killed.append(1)
            g.do_kill([ak], Context(1))
            return "rerun"
        return None
    _drive(g, pick=pick)
    assert killed and g.objects[ak].zone == "trash"
    assert g.objects[blade].controller == 1 and g.objects[blade].location == ("base", 1)
    assert g.objects[blade].attached_to is None


def test_imperial_decree_does_not_kill_a_unit_that_left_and_came_back(db):
    # CR 124: a unit returned to hand and played again is a new object. Imperial Decree's "When any unit takes damage
    # this turn, kill it" means the damaged object; if it was bounced and replayed with the trigger on the chain, the
    # new unit lives. A unit that stayed on the board is still killed.
    for replay in (True, False):
        g = main_phase(db, [_deck(db, "viktor_herald"), _deck(db, "riven_exile")])
        foe = put(g, db, 1, "Mountain Drake", ("bf", 1))
        sp = give(g, 0, "Imperial Decree", db)
        _ready_runes(g, 0)
        g.run()
        g.choose(("play", sp))
        _drive(g)
        g.do_deal([foe], 1, Context(0, None))
        g.dirty, g.pending = True, None
        done = []

        def pick(d):
            if g.chain and not done:
                done.append(1)
                assert g.chain[-1].label.startswith("Imperial Decree")
                if replay:
                    o = g.objects[foe]
                    g._to_zone(o, "hand")
                    g._to_zone(o, "board", location=("bf", 1), controller=1)
                    g.restruct()
                return "rerun"
        _drive(g, pick=pick)
        assert done
        assert g.objects[foe].zone == ("board" if replay else "trash")


# ----------------------------------------------------------------------------- 2026-11-19 10:20 run
def test_hidden_play_effect_mistargets_when_its_unit_left_the_board(db):
    # CR 811.1.d.3.a: a play effect of a permanent played from facedown reads where it was played from its source. If
    # the unit is no longer on the board when the effect resolves, it mistargets. Kennen, Keeper of Balance (Azir and
    # Viktor decks) played from facedown, pays [2] to stun an enemy there; killed in response, the stun does nothing.
    for kill in (False, True):
        g = _fresh(db)
        g.set_bf_controller(0, 0)
        k = give(g, 0, "Kennen, Keeper of Balance", db)
        put(g, db, 0, "Mountain Drake", ("bf", 0))
        foe = put(g, db, 1, "Mountain Drake", ("bf", 0))
        assert g.do_hide(0, k, ("bf", 0))
        g.objects[k].facedown_turn = g.turn - 1
        for _ in range(4):
            g.do_channel(0, 1)
        _ready_runes(g, 0)
        g.restruct()
        g.pending = None
        d = g.run()
        g.choose(next(o for o in d.options if o[0] == "play" and o[1] == k))
        done = []

        def pick(d):
            if d.kind == "choose" and foe in d.options:
                return foe
            if d.kind == "yesno":
                return True
            if kill and not done and any(it.uid == k and it.kind == "trigger" for it in g.chain):
                done.append(1)
                g.do_kill([k], Context(1, None))
                return "rerun"
        _drive(g, pick=pick)
        assert done or not kill
        assert g.objects[foe].stunned is (not kill)


# ----------------------------------------------------------------------------- 2026-11-19 15:20 run
def test_attached_gear_moves_with_its_unit(db):
    # CR 719.3.a: when the top-most card changes locations, its attached cards go with it. An equipped unit moved to a
    # battlefield left its Equipment in base, so Orianna, Exquisite ("I don't deal combat damage unless there's a
    # friendly gear here", Irelia deck) dealt none beside an equipped unit. Recalls and deaths follow the unit too.
    g = _fresh(db)
    ori = put(g, db, 0, "Orianna, Exquisite", ("bf", 0))
    u = put(g, db, 0, "Mountain Drake", ("base", 0), exclude=[ori])
    sword = put(g, db, 0, "Long Sword", ("base", 0), exclude=[ori, u])
    g.do_attach(sword, u, Context(0, None))
    assert g.no_combat_damage(ori)
    g.do_move([u], ("bf", 0), Context(0, None))
    assert g.objects[sword].location == ("bf", 0)
    assert not g.no_combat_damage(ori)
    g.do_recall(u, Context(0, None))
    assert g.objects[sword].location == ("base", 0) and g.no_combat_damage(ori)
    g.do_move([u], ("bf", 0), Context(0, None))
    g.do_kill([u], Context(1, None))
    # CR 436.4.b: it detaches where the unit last was; the cleanup recalls gear at a battlefield (436.4.a)
    assert g.objects[sword].attached_to is None and g.objects[sword].location == ("bf", 0)


# ----------------------------------------------------------------------------- 2026-11-19 20:20 run
def test_units_named_as_the_source_deal_unit_damage_not_spell_damage(db):
    # CR 418.6.b.3: "They deal damage equal to their Mights to each other" (Challenge; Rampage in the Sett and Master Yi
    # decks) is dealt by the chosen units, not by the spell. Unyielding Spirit ("Prevent all spell and ability damage
    # this turn", Master Yi deck) prevented it, and Annie's "Your spells and abilities deal 1 Bonus Damage" added to it.
    # A spell's own Deal is still prevented.
    for spirit in (False, True):
        g = _fresh(db)
        mine = put(g, db, 0, "Mountain Drake", ("bf", 0))
        foe = put(g, db, 1, "Stellacorn Herder", ("bf", 0))
        put(g, db, 0, "Annie, Fiery", ("base", 0), exclude=[mine])
        small = g.chars(foe).might
        if spirit:
            _cast_with(g, db, 0, "Unyielding Spirit", [("body", False)] * 2, None)
        order = [mine, foe]
        _cast_with(g, db, 0, "Challenge", [("body", False)] * 3,
                   lambda d: order.pop(0) if d.kind == "choose" and order and order[0] in d.options else None)
        assert g.objects[mine].damage == small and g.objects[foe].zone == "trash", spirit   # no prevention, no bonus
        if spirit:
            g.do_deal([mine], 2, Context(1, None))     # a spell or ability's own damage: prevented
            assert g.objects[mine].damage == small


# ----------------------------------------------------------------------------- 2026-11-20 00:20 run
def test_delayed_it_does_not_follow_a_unit_that_left_and_came_back(db):
    # CR 124: Noxian Guillotine ("Choose a unit. Kill it the next time it takes damage this turn") refers to the chosen
    # object. Returned to hand and played again, it is a new object: damage no longer kills it. The same unit, still on
    # the board, is killed.
    for replay in (False, True):
        g = _fresh(db)
        foe = put(g, db, 1, "Mountain Drake", ("bf", 0))
        _cast_with(g, db, 0, "Noxian Guillotine, Darius", [("fury", False)] * 4,
                   lambda d: foe if d.kind == "choose" and foe in d.options else None)
        assert g.objects[foe].zone == "board" and g.delayed
        if replay:
            o = g.objects[foe]
            g._to_zone(o, "hand")
            g._to_zone(o, "board", location=("bf", 0), controller=1)
            g.restruct()
        g.do_deal([foe], 1, Context(0, None))
        g.dirty, g.pending = True, None
        _drive(g)
        assert g.objects[foe].zone == ("board" if replay else "trash"), replay


# ----------------------------------------------------------------------------- 2026-11-20 05:20 run
def test_not_so_fast_ignores_a_target_that_left_the_board_and_came_back(db):
    # CR 359.3.e.9.a: a finalized item still "chooses" a mistargeted unit that is on the board, but not one that changed
    # to or from a non-board zone. Not So Fast (Riven, Irelia, Akali, Master Yi decks: "Counter an enemy spell or ability
    # that chooses a friendly unit or gear") could answer Hextech Ray after its target was returned and played again.
    from riftsim.core.selectors import Sel
    nsf_defn = _card(db, "Not So Fast")
    choose = next(i for a in nsf_defn.abilities for i in (a.target_code or []) if isinstance(getattr(i, "sel", None), Sel))
    for how in ("stay", "moved", "replayed"):
        g = _fresh(db)
        foe = put(g, db, 1, "Mountain Drake", ("bf", 0))
        nsf = give(g, 1, "Not So Fast", db)
        give(g, 0, "Hextech Ray", db)
        _set_runes(g, db, 0, [("fury", False)] * 3)
        g.pending = None
        d = g.run()
        ray = next(o for o in d.options if o[0] == "play" and g.objects[o[1]].defn.name == "Hextech Ray")[1]
        g.choose(("play", ray))
        _drive(g, pick=lambda d: foe if d.kind == "choose" and foe in d.options else None,
               stop=lambda d: any(it.uid == ray and it.finalized for it in g.chain))
        o = g.objects[foe]
        if how == "moved":
            g.do_move([foe], ("base", 1), Context(1, None))      # mistargeted, still on the board: still chosen
        elif how == "replayed":
            g._to_zone(o, "hand")
            g._to_zone(o, "board", location=("bf", 0), controller=1)
            g.restruct()
        offered = ray in choose.sel.candidates(g, Context(1, nsf))
        assert offered is (how != "replayed"), how


def test_a_unit_with_tank_and_backline_is_assigned_first_or_last_at_the_assigners_pick(db):
    """CR 467.2.c.8 example: Caitlyn, Patrolling (Backline) given Tank, with two units without abilities. The
    assigner fulfils one of her requirements: damage to her first (Tank) or last (Backline), never in between.
    Tank always won, so the Backline option was never offered. 467.2.c.9: two such units are picked separately."""
    g = main_phase(db, [_deck(db, "vex_gloomist"), _deck(db, "riven_exile")])
    bf = ("bf", 0)
    cait = put(g, db, 1, "Caitlyn, Patrolling", bf)
    a = put(g, db, 1, "Stellacorn Herder", bf, exclude=(cait,))
    b = put(g, db, 1, "Stellacorn Herder", bf, exclude=(cait, a))
    g.add_mod(cait, "keyword", ("tank", True), duration="turn")
    g.restruct()
    assert g.chars(cait).keywords.get("tank") and g.chars(cait).keywords.get("backline")
    nc, na = g._lethal_need(cait, 20, 0), g._lethal_need(a, 20, 0)
    plans = set(g._damage_plans([cait, a, b], 2, 0))
    assert (2, 0, 0) in plans                       # Tank: Caitlyn first
    assert (0, 2, 0) in plans and (0, 0, 2) in plans   # Backline: the others first
    total = nc + na + 1                             # Caitlyn lethal, then one unit short: Tank order
    plans = set(g._damage_plans([cait, a, b], total, 0))
    assert (nc, na, 1) in plans
    total = na + 1                                  # in between (one other unit lethal, then Caitlyn) is never legal
    plans = set(g._damage_plans([cait, a, b], total, 0))
    assert (1, na, 0) not in plans and (0, na, 1) in plans
    # two Caitlyns with Tank and one plain unit: both may be dealt first (467.2.c.9 example)
    c2 = put(g, db, 1, "Caitlyn, Patrolling", bf, exclude=(cait, a, b))
    g.add_mod(c2, "keyword", ("tank", True), duration="turn")
    g.restruct()
    plans = set(g._damage_plans([cait, c2, a], nc + nc, 0))
    assert {(nc, nc, 0), (nc, 0, na), (0, nc, na)} <= plans          # each Caitlyn picks Tank or Backline
    plans = set(g._damage_plans([cait, c2, a], na, 0))
    assert {(nc, 0, 0), (0, nc, 0), (0, 0, na)} <= plans
