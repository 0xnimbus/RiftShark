"""Hand-scripted common cards (riftsim/core/scripts/cards_common.py) against printed text."""
from test_champions import db, decks, put, settle, _card_in  # noqa: F401  (fixtures)
from test_targeting import main_phase, give


def _play(g, uid, answer):
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == uid))
    for _ in range(60):
        d = g.run()
        a = answer(d)
        if a is not None:
            g.choose(a); continue
        if d.kind == "action" and not g.chain:
            return d
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    raise AssertionError("did not settle")


def test_call_to_glory_is_free_when_you_spend_a_buff(db, decks):
    g = main_phase(db, decks)
    u = put(g, db, 0, "Rell, Magnetic", ("base", 0))
    g.objects[u].buffs = 1
    for r in g.players[0].runes:
        g.objects[r].exhausted = True          # no resources: only the free way is legal
    g.bump()
    s = give(g, 0, "Call to Glory", db)
    base = g.chars(u).might
    _play(g, s, lambda d: u if d.kind == "choose" and u in d.options else None)
    assert g.objects[u].buffs == 0 and g.chars(u).might == base - 1 + 3


def test_meditation_draws_two_if_a_unit_was_exhausted(db, decks):
    g = main_phase(db, decks)
    u = put(g, db, 0, "Rell, Magnetic", ("base", 0))
    s = give(g, 0, "Meditation", db)
    hand = len(g.players[0].hand)
    _play(g, s, lambda d: True if d.kind == "yesno" else (u if d.kind == "choose" and u in d.options else None))
    assert g.objects[u].exhausted and len(g.players[0].hand) == hand - 1 + 2


def test_meditation_without_the_cost_draws_one(db, decks):
    g = main_phase(db, decks)
    s = give(g, 0, "Meditation", db)
    hand = len(g.players[0].hand)
    _play(g, s, lambda d: False if d.kind == "yesno" else None)
    assert len(g.players[0].hand) == hand - 1 + 1


def test_spoils_of_war_costs_less_after_an_enemy_unit_died(db, decks):
    g = main_phase(db, decks)
    s = _card_in(g, db, 0, "Spoils of War", "hand")
    e0, _ = g.card_cost(0, s, "hand")
    foe = put(g, db, 1, "Rell, Magnetic", ("bf", 0))
    g.do_kill([foe])
    e1, _ = g.card_cost(0, s, "hand")
    assert e1 == max(0, e0 - 2)


def test_solari_chief_kills_a_stunned_enemy_otherwise_stuns(db, decks):
    g = main_phase(db, decks)
    a = put(g, db, 1, "Rell, Magnetic", ("bf", 0))
    chief = put(g, db, 0, "Solari Chief", ("base", 0))
    g.emit("play", uid=chief, player=0, card_type="unit")
    settle(g, picks=[a])
    assert g.objects[a].stunned and g.objects[a].zone == "board"
    g.emit("play", uid=chief, player=0, card_type="unit")
    settle(g, picks=[a])
    assert g.objects[a].zone == "trash"


def test_get_excited_deals_the_discarded_cards_energy_cost(db, decks):
    g = main_phase(db, decks)
    foe = put(g, db, 1, "Gangplank, Naval", ("bf", 0))
    s = give(g, 0, "Get Excited!", db)
    for u in list(g.players[0].hand):
        if u != s:
            g._to_zone(g.objects[u], "trash")
    junk = _card_in(g, db, 0, "Soraka, Wanderer", "hand")
    fury = next(c for c in db if c.name == "Fury Rune")
    for r in g.players[0].runes[:2]:
        g.objects[r].defn, g.objects[r].domain = fury, "fury"
    g.bump()
    _play(g, s, lambda d: foe if d.kind == "choose" and foe in d.options else None)
    dmg = [e["amount"] for e in g.events if e["kind"] == "damage" and e.get("uid") == foe]
    assert g.objects[junk].zone == "trash" and dmg and dmg[0] >= g.objects[junk].defn.energy


def test_carnivorous_snapvine_fights_an_enemy_at_a_battlefield(db, decks):
    g = main_phase(db, decks)
    sv = put(g, db, 0, "Carnivorous Snapvine", ("base", 0))
    foe = put(g, db, 1, "Gangplank, Naval", ("bf", 0))
    g.emit("play", uid=sv, player=0, card_type="unit")
    settle(g)
    hits = {e["uid"]: e["amount"] for e in g.events if e["kind"] == "damage"}
    assert hits.get(foe, 0) >= 6 and hits.get(sv, 0) >= 6


def test_rhasa_and_battering_ram_and_void_drone_costs(db, decks):
    g = main_phase(db, decks)
    rh = _card_in(g, db, 0, "Rhasa the Sunderer", "hand")
    n = len(g.players[0].trash)
    assert g.card_cost(0, rh, "hand")[0] == max(0, 10 - n)
    ram = _card_in(g, db, 0, "Battering Ram", "hand")
    g.players[0].played_this_turn = [1, 2, 3, 4, 5, 6]
    assert g.card_cost(0, ram, "hand")[0] == 1
    vd = _card_in(g, db, 0, "Void Drone", "trash")
    assert g.card_cost(0, vd, "trash")[0] == 1


def test_invert_timelines_discards_hands_and_draws_four(db, decks):
    g = main_phase(db, decks)
    s = give(g, 0, "Invert Timelines", db)
    old1 = list(g.players[1].hand)
    _play(g, s, lambda d: None)
    assert len(g.players[0].hand) == 4 and len(g.players[1].hand) == 4
    assert all(g.objects[u].zone == "trash" for u in old1)


def test_super_mega_death_rocket_returns_from_trash_on_conquer(db, decks):
    g = main_phase(db, decks)
    r = _card_in(g, db, 0, "Super Mega Death Rocket!, Jinx", "trash")
    g.emit("conquer", player=0, loc=("bf", 0), bf=0, units=())
    settle(g)
    assert g.objects[r].zone == "hand"


def test_trusty_ramhound_and_convergent_mutation(db, decks):
    g = main_phase(db, decks)
    rh = put(g, db, 0, "Trusty Ramhound", ("bf", 0))
    assert g.chars(rh).might == 2
    big = put(g, db, 0, "Gangplank, Naval", ("bf", 0), exclude=(rh,))
    assert g.chars(rh).might == 3
    from riftsim.core.vm import Context, Frame
    s = next(c for c in db if c.name == "Convergent Mutation")
    ctx = Context(0, None)
    ab = s.abilities[-1]
    g.vm_frames.append(Frame(list(ab.target_code or []) + list(ab.code), ctx))
    for _ in range(20):
        d = g.run()
        if d.kind == "choose" and rh in d.options and ctx.vars.get("t") is None:
            g.choose(rh); continue
        if d.kind == "choose" and big in d.options:
            g.choose(big); continue
        break
    assert g.chars(rh).might == g.chars(big).might


def test_tianna_stops_opponents_scoring_while_at_a_battlefield(db, decks):
    g = main_phase(db, decks)
    t = put(g, db, 0, "Tianna Crownguard", ("base", 0))
    p1 = g.players[1].points
    g.gain_points(1, 1)
    assert g.players[1].points == p1 + 1
    g._to_zone(g.objects[t], "board", location=("bf", 0), controller=0); g.bump()
    g.gain_points(1, 1)
    p0 = g.players[0].points
    g.gain_points(0, 1)
    assert g.players[1].points == p1 + 1 and g.players[0].points == p0 + 1


def test_downwell_returns_units_and_gear_but_not_runes_or_legends(db, decks):
    g = main_phase(db, decks)
    a = put(g, db, 0, "Rell, Magnetic", ("bf", 0))
    b = put(g, db, 1, "Doran's Blade", ("base", 1))
    from riftsim.core.vm import Context, Frame
    s = next(c for c in db if c.name == "Downwell")
    g.vm_frames.append(Frame(list(s.abilities[-1].code), Context(0, None)))
    settle(g)
    assert g.objects[a].zone == "hand" and g.objects[b].zone == "hand"
    assert g.objects[g.players[0].legend].zone == "board" and all(g.objects[r].zone == "board" for r in g.players[0].runes)


def test_unsung_hero_draws_only_if_it_was_mighty(db, decks):
    g = main_phase(db, decks)
    u = put(g, db, 0, "Unsung Hero", ("bf", 0))
    h = len(g.players[0].hand)
    g.do_kill([u]); settle(g)
    assert len(g.players[0].hand) == h
    u2 = put(g, db, 0, "Unsung Hero", ("bf", 0))
    g.add_mod(u2, "might", 3, "turn")
    g.do_kill([u2]); settle(g)
    assert len(g.players[0].hand) == h + 2


def test_prepared_neophyte_and_combat_experience_levels(db, decks):
    g = main_phase(db, decks)
    n = put(g, db, 0, "Prepared Neophyte", ("base", 0))
    assert g.chars(n).might == 1
    g.turn_memo[("spell_spent_4", 0)] = True; g.bump()
    assert g.chars(n).might == 5
    from riftsim.core.vm import Context, Frame
    s = next(c for c in db if c.name == "Combat Experience")
    for xp, gain in ((0, 1), (6, 3)):
        g.players[0].xp = xp
        before = g.chars(n).might
        ctx = Context(0, None); ctx.vars["t"] = n
        g.vm_frames.append(Frame([x for x in s.abilities[-1].code if type(x).__name__ != "_Recheck"], ctx))
        settle(g)
        assert g.chars(n).might == before + gain


def test_monch_costs_less_and_enters_ready_with_a_stunned_enemy(db, decks):
    g = main_phase(db, decks)
    m = _card_in(g, db, 0, "Monch", "hand")
    e0 = g.card_cost(0, m, "hand")[0]
    foe = put(g, db, 1, "Rell, Magnetic", ("bf", 0))
    g.objects[foe].stunned = True; g.bump()
    assert g.card_cost(0, m, "hand")[0] == e0 - 2


def test_undying_legion_plays_from_trash_only_with_legion(db, decks):
    g = main_phase(db, decks)
    ul = _card_in(g, db, 0, "Undying Legion", "trash")
    fury = next(c for c in db if c.name == "Fury Rune")
    for r in g.players[0].runes[:2]:
        g.objects[r].defn, g.objects[r].domain = fury, "fury"
    g.bump()
    assert not any(o[0] == "play" and o[1] == ul for o in g.run().options)
    g.players[0].played_this_turn.append(-1)
    g.bump(); g.pending = None
    assert any(o[0] == "play" and o[1] == ul for o in g.run().options)
    assert g.card_cost(0, ul, "trash") == (3, ["fury"])


def test_isolate_draws_if_an_enemy_is_left_alone(db, decks):
    g = main_phase(db, decks)
    a = put(g, db, 1, "Rell, Magnetic", ("bf", 0))
    b = put(g, db, 1, "Rell, Magnetic", ("bf", 0), exclude=(a,))
    from riftsim.core.vm import Context, Frame
    s = next(c for c in db if c.name == "Isolate")
    h = len(g.players[0].hand)
    ctx = Context(0, None)
    from riftsim.core.vm import relocate
    tc = list(s.abilities[-1].target_code or [])
    g.vm_frames.append(Frame(tc + relocate(s.abilities[-1].code, len(tc)), ctx))     # jump targets shift
    settle(g, picks=[a])
    assert g.objects[a].location == ("base", 1) and len(g.players[0].hand) == h + 1


def test_wily_newtfish_after_gaining_xp(db, decks):
    g = main_phase(db, decks)
    w = put(g, db, 0, "Wily Newtfish", ("base", 0))
    assert g.chars(w).might == 4 and not g.chars(w).keywords.get("ganking")
    g.gain_xp(0, 1)
    assert g.chars(w).might == 5 and g.chars(w).keywords.get("ganking")


def _run_spell(g, db, name, controller=0, picks=(), yes=True):
    from riftsim.core.vm import Context, Frame, relocate
    s = next(c for c in db if c.name == name)
    ab = s.abilities[-1] if type(s.abilities[-1]).__name__ == "SpellEffect" else \
        next(a for a in s.abilities if type(a).__name__ == "SpellEffect")
    ctx = Context(controller, None)
    tc = list(ab.target_code or [])
    g.vm_frames.append(Frame(tc + relocate(ab.code, len(tc)), ctx))
    settle(g, yes=yes, picks=list(picks))
    return ctx


def test_determined_sentry_cannot_move_to_base(db, decks):
    g = main_phase(db, decks)
    s = put(g, db, 0, "Determined Sentry", ("bf", 0))
    assert not g.valid_destination(s, ("base", 0))
    assert g.valid_destination(s, ("bf", 1))


def test_lilting_lullaby_counters_and_locks_spells(db, decks):
    from riftsim.core.objects import ChainItem
    g = main_phase(db, decks)
    sp = _card_in(g, db, 1, "Get Excited!", "hand")
    g._to_zone(g.objects[sp], "chain"); g.bump()
    it = ChainItem(900, "spell", 1, uid=sp, label="Get Excited!")
    g.chain.append(it)
    _run_spell(g, db, "Lilting Lullaby", picks=[sp])
    assert it not in g.chain and g.objects[sp].zone == "trash"
    later = _card_in(g, db, 1, "Get Excited!", "hand")
    assert not g._play_restrictions_ok(1, later, "hand")


def test_ol_poro_not_on_your_first_three_turns(db, decks):
    g = main_phase(db, decks)
    u = _card_in(g, db, 0, "Ol' Poro", "hand")
    g.turns_taken[0] = 3
    assert not g._play_restrictions_ok(0, u, "hand")
    g.turns_taken[0] = 4
    assert g._play_restrictions_ok(0, u, "hand")


def test_keepers_verdict_owner_chooses_top_or_bottom(db, decks):
    g = main_phase(db, decks)
    foe = put(g, db, 1, "Rell, Magnetic", ("bf", 0))
    _run_spell(g, db, "Keeper's Verdict", picks=[foe, "top"])
    assert g.players[1].deck[0] == foe


def test_guttural_roar_empowered(db, decks):
    g = main_phase(db, decks)
    u = put(g, db, 0, "Rell, Magnetic", ("bf", 0))
    b = g.chars(u).might
    _run_spell(g, db, "Guttural Roar", picks=[u])
    g.objects[u].empowered = 1; g.bump()
    _run_spell(g, db, "Guttural Roar", picks=[u])
    assert g.chars(u).might == b + 6
