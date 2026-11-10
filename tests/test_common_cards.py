"""Hand-scripted common cards (riftsim/core/scripts/cards_common.py) against printed text."""
from test_champions import db, decks, put, settle, _card_in, _fire  # noqa: F401  (fixtures)
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
    it.finalized = True                 # only a finalized spell can be chosen (CR 355.9.a.2)
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


def test_decree_of_rage_cannot_be_countered(db, decks):
    from riftsim.core.objects import ChainItem
    g = main_phase(db, decks)
    sp = _card_in(g, db, 0, "Decree of Rage", "hand")
    g._to_zone(g.objects[sp], "chain"); g.bump()
    it = ChainItem(901, "spell", 0, uid=sp, label="Decree of Rage")
    g.chain.append(it)
    assert g.do_counter(901) is False and it in g.chain


def test_spiderlings_count_each_other_and_ignore_the_copy_limit(db, decks):
    from riftsim.core.deck import Deck
    g = main_phase(db, decks)
    a = put(g, db, 0, "Spiderling", ("bf", 0))
    b = put(g, db, 0, "Spiderling", ("bf", 0), exclude=(a,))
    c = put(g, db, 0, "Spiderling", ("bf", 1), exclude=(a, b))
    assert g.chars(a).might == 2 and g.chars(c).might == 1
    d0 = Deck.from_dict(decks[0].to_dict())
    d0.main[:5] = ["Spiderling"] * 5
    assert not any("Spiderling" in e and "copies" in e for e in (d0.validate(db) or []))


def test_cataclysmic_duel_each_player_keeps_one(db, decks):
    g = main_phase(db, decks)
    a = put(g, db, 0, "Rell, Magnetic", ("bf", 0))
    b = put(g, db, 0, "Spiderling", ("bf", 0), exclude=(a,))
    x = put(g, db, 1, "Rell, Magnetic", ("bf", 1))
    y = put(g, db, 1, "Spiderling", ("bf", 1), exclude=(x,))
    _run_spell(g, db, "Cataclysmic Duel", picks=[b, x])
    assert g.objects[b].zone == "board" and g.objects[x].zone == "board"
    assert g.objects[a].zone == "trash" and g.objects[y].zone == "trash"


def test_wind_and_ghosts_banishes_small_returns_big(db, decks):
    g = main_phase(db, decks)
    small = put(g, db, 1, "Spiderling", ("bf", 0))
    big = put(g, db, 1, "Rell, Magnetic", ("bf", 0), exclude=(small,))
    _run_spell(g, db, "Wind and Ghosts", picks=[small])
    _run_spell(g, db, "Wind and Ghosts", picks=[big])
    assert g.objects[small].zone == "banish" and g.objects[big].zone == "hand"


def test_lingering_animus_and_hold_em_turn_memory(db, decks):
    g = main_phase(db, decks)
    he = _card_in(g, db, 0, "Hold 'Em", "hand")
    e0 = g.card_cost(0, he, "hand")[0]
    g.turn_memo[("played_to_bf", 0)] = True
    assert g.card_cost(0, he, "hand")[0] == max(0, e0 - 2)
    la = put(g, db, 0, "Lingering Animus", ("base", 0))
    ev = g.replace_event({"kind": "enter_ready", "uid": la, "player": 0, "ready": False, "loc": ("base", 0)})
    assert not ev["ready"]
    gear = put(g, db, 0, "Doran's Blade", ("base", 0), exclude=(la,))
    g.do_kill([gear])
    ev = g.replace_event({"kind": "enter_ready", "uid": la, "player": 0, "ready": False, "loc": ("base", 0)})
    assert ev["ready"]


def _bf_card(g, db, name, i=0):
    """Turn battlefield i into `name` (re-using its object)."""
    bf = g.battlefields[i]
    g.objects[bf.uid].defn = next(c for c in db if c.name == name)
    g.bump()
    return bf.uid


def test_aspirants_climb_and_otterpus(db, decks):
    g = main_phase(db, decks)
    v = g.victory_score()
    _bf_card(g, db, "Aspirant's Climb")
    assert g.victory_score() == v + 1
    put(g, db, 1, "Otterpus", ("base", 1))
    g.turns_taken[0] = 1
    pts, hand = g.players[0].points, len(g.players[0].hand)
    g.gain_points(0, 1, "conquer")
    assert g.players[0].points == pts and len(g.players[0].hand) == hand + 1
    g.turns_taken[0] = 3
    g.gain_points(0, 1, "conquer")
    assert g.players[0].points == pts + 1


def test_esteemed_hierophant_and_sacred_protector(db, decks):
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    h = put(g, db, 0, "Esteemed Hierophant", ("bf", 0))
    while len(g.players[0].runes) < 7:
        g.do_channel(0, 1)
    g.do_deal([h], 2, Context(1, None))
    assert g.objects[h].damage == 0
    g.do_deal([h], 2, Context(0, None))
    assert g.objects[h].damage == 2
    sp = put(g, db, 0, "Sacred Protector", ("bf", 1), exclude=(h,))
    assert g.no_combat_damage(sp)
    put(g, db, 0, "Spiderling", ("bf", 1), exclude=(h, sp))
    assert not g.no_combat_damage(sp)


def test_tactical_retreat_saves_the_unit_once(db, decks):
    g = main_phase(db, decks)
    u = put(g, db, 0, "Rell, Magnetic", ("bf", 0))
    _run_spell(g, db, "Tactical Retreat", picks=[u])
    g.do_kill([u])
    assert g.objects[u].zone == "board" and g.objects[u].location == ("base", 0) and g.objects[u].exhausted
    g.do_kill([u])
    assert g.objects[u].zone == "trash"


# ---------------------------------------------------------------- Radiance type fixes (checked against card images)
def test_radiance_type_fixes(db):
    by = {c.id: c for c in db}
    assert by["RAD-007"].type == "spell" and by["RAD-056"].type == "spell" and by["RAD-124"].type == "spell"
    assert by["RAD-064"].type == "gear" and by["RAD-046"].type == "gear" and by["RAD-069"].type == "gear"
    for i in ("RAD-016", "RAD-072", "RAD-097", "RAD-120", "RAD-130", "RAD-131"):
        assert by[i].is_unit and by[i].might
    assert by["RAD-071"].domains == ("body",) or list(by["RAD-071"].domains) == ["body"]
    assert "Equipment" in by["RAD-071"].tags and "Yordle" in by["RAD-001"].tags


def test_equipment_grants_its_keywords_to_the_unit(db, decks):
    g = main_phase(db, decks)
    u = put(g, db, 0, "Shipyard Skulker", ("base", 0))
    n = put(g, db, 0, "Nazuman Ntofo", ("base", 0), exclude=(u,))
    p = put(g, db, 0, "Protector's Shield", ("base", 0), exclude=(u, n))
    assert not g.chars(u).kw("shield")
    g.do_attach(n, u); g.do_attach(p, u); g.bump()
    assert g.chars(u).kw("shield") == 2 and g.has_keyword(u, "tank")


def test_overloaded_traveler_with_a_deploy_gear_at_its_battlefield(db, decks):
    g = main_phase(db, decks)
    t = put(g, db, 0, "Overloaded Traveler", ("bf", 0))
    assert g.chars(t).might == 2
    gear = put(g, db, 0, "The Good Stuff", ("bf", 1), exclude=(t,))
    assert g.chars(t).might == 2                      # a different battlefield
    g.objects[gear].location = ("bf", 0); g.bump()
    assert g.chars(t).might == 3


def test_improvised_projectile_and_burn_away(db, decks):
    g = main_phase(db, decks)
    gear = put(g, db, 0, "Protector's Shield", ("base", 0))
    foe = put(g, db, 1, "Stalwart Goatherd", ("bf", 0))
    _run_spell(g, db, "Improvised Projectile", picks=[gear, foe])
    assert g.objects[foe].damage == 2 or g.objects[foe].zone == "trash"
    big = put(g, db, 1, "Elnuk Herd", ("bf", 1))
    small = put(g, db, 1, "Hunting Dog", ("bf", 1), exclude=(big,))
    trash = len(g.players[0].trash)
    _run_spell(g, db, "Burn Away", picks=[small])
    assert g.objects[big].zone == "board" and g.objects[small].zone == "banish"
    assert len(g.players[0].trash) == trash + 2


def test_an_offer_you_cant_refuse_gives_its_controller_a_gold(db, decks):
    g = main_phase(db, decks)
    gear = put(g, db, 1, "Protector's Shield", ("base", 1))
    _run_spell(g, db, "An Offer You Can't Refuse", picks=[gear])
    assert g.objects[gear].zone == "trash"
    gold = [u for u, o in g.objects.items() if o.zone == "board" and o.defn.name == "Gold"]
    assert len(gold) == 1 and g.objects[gold[0]].controller == 1 and g.objects[gold[0]].exhausted


def test_scrutinizing_scope_recycles_on_a_right_guess(db, decks):
    g = main_phase(db, decks)
    s = put(g, db, 0, "Scrutinizing Scope", ("base", 0))
    top = g.players[0].deck[0]
    kind = next(k for k in ("unit", "gear", "spell") if k in g.objects[top].base_defn().types)
    hand = len(g.players[0].hand)
    _fire(g, s, "Scrutinizing Scope")
    settle(g, picks=[["unit", "gear", "spell"].index(kind)])
    assert g.objects[top].zone == "deck" and g.players[0].deck[-1] == top and len(g.players[0].hand) == hand
    top = g.players[0].deck[0]
    wrong = next(i for i, k in enumerate(("unit", "gear", "spell")) if k not in g.objects[top].base_defn().types)
    _fire(g, s, "Scrutinizing Scope")
    settle(g, picks=[wrong])
    assert g.objects[top].zone == "hand"


def test_battlefield_armorer_returns_a_dead_gear(db, decks):
    g = main_phase(db, decks)
    put(g, db, 0, "Battlefield Armorer", ("base", 0))
    gear = put(g, db, 0, "The Good Stuff", ("bf", 0))
    g.do_kill([gear])
    settle(g)
    assert g.objects[gear].zone == "hand"


def test_demacian_illuminators_buff_once_per_batch(db, decks):
    g = main_phase(db, decks)
    il = put(g, db, 0, "Demacian Illuminators", ("base", 0))
    a = put(g, db, 0, "Hunting Dog", ("bf", 0), exclude=(il,))
    b = put(g, db, 0, "Hunting Dog", ("bf", 0), exclude=(il, a))
    g.do_kill([a, b])
    settle(g, picks=[il])
    assert g.objects[il].buffs == 1


def test_zero_point_inflection_overflows(db, decks):
    g = main_phase(db, decks)
    z = put(g, db, 0, "Zero Point Inflection", ("base", 0))
    while len(g.players[0].hand) < 9:
        g.do_draw(0, 1)
    pts = g.players[1].points
    g.do_draw(0, 1)
    settle(g)
    assert g.objects[z].zone == "trash" and not g.players[0].hand and g.players[1].points == pts + 1


def test_zero_point_inflection_counts_only_other_cards(db, decks):
    g = main_phase(db, decks)
    z = put(g, db, 0, "Zero Point Inflection", ("base", 0))
    while len(g.players[0].hand) > 8:
        g.do_discard(0, [g.players[0].hand[-1]])
    while len(g.players[0].hand) < 8:
        g.do_draw(0, 1)
    g.do_draw(0, 2)                                    # 8 others: no trigger
    settle(g)
    assert g.objects[z].zone == "board" and len(g.players[0].hand) == 10


def test_meticulous_restorationist_replays_from_trash(db, decks):
    g = main_phase(db, decks)
    m = _card_in(g, db, 0, "Meticulous Restorationist", "trash")
    for r in g.players[0].runes[:1]:
        g.objects[r].defn = next(c for c in db if c.name == "Order Rune")
        g.objects[r].domain = "order"
    g.bump()
    big = _card_in(g, db, 0, "Supernova", "hand")
    g.emit("play", uid=big, player=0, card_type="spell")
    settle(g)
    assert g.objects[m].zone == "board"


def test_raging_soul_after_a_discard(db, decks):
    g = main_phase(db, decks)
    r = put(g, db, 0, "Raging Soul", ("base", 0))
    assert not g.has_keyword(r, "ganking")
    g.do_discard(0, [g.players[0].hand[0]])
    assert g.has_keyword(r, "ganking") and g.has_keyword(r, "assault")


def test_forge_of_the_future_recycles_up_to_four(db, decks):
    g = main_phase(db, decks)
    f = put(g, db, 0, "Forge of the Future", ("base", 0))
    cards = [g.players[1].deck[i] for i in range(5)]
    for u in cards:
        g._to_zone(g.objects[u], "trash")
    g.bump()
    _fire(g, f, "Kill this: recycle up to 4")
    settle(g, picks=[(cards[0],), (cards[1],), ()])
    assert g.objects[cards[0]].zone == "deck" and g.objects[cards[1]].zone == "deck" and g.objects[cards[2]].zone == "trash"


def test_reinforce_plays_a_unit_for_five_less(db, decks):
    g = main_phase(db, decks)
    top = g.players[0].deck[:5]
    unit = next(u for u in top if g.objects[u].base_defn().is_unit)
    _run_spell(g, db, "Reinforce", picks=[(unit,), unit])
    assert g.objects[unit].zone == "board"
    assert all(g.objects[u].zone != "deck" or g.players[0].deck.index(u) >= len(g.players[0].deck) - 4 for u in top if u != unit)


def test_grand_plaza_and_hallowed_tomb(db, decks):
    g = main_phase(db, decks)
    _bf_card(g, db, "The Grand Plaza", 0)
    g.set_bf_controller(0, 0)
    us = []
    for _ in range(7):
        us.append(put(g, db, 0, "Hunting Dog", ("bf", 0), exclude=tuple(us)))
    g.emit("hold", player=0, loc=("bf", 0), bf=0, units=tuple(us))
    settle(g)
    assert g.over and g.winner == 0
    g = main_phase(db, decks)
    _bf_card(g, db, "Hallowed Tomb", 0)
    g.set_bf_controller(0, 0)
    ch = g.players[0].chosen_champion
    g._to_zone(g.objects[ch], "trash"); g.bump()
    g.emit("hold", player=0, loc=("bf", 0), bf=0, units=())
    settle(g)
    assert g.objects[ch].zone == "champion" and g.players[0].champion == ch


def test_shakedown_controller_chooses(db, decks):
    g = main_phase(db, decks)
    foe = put(g, db, 1, "Elnuk Herd", ("bf", 0))
    hand = len(g.players[0].hand)
    _run_spell(g, db, "Shakedown", picks=[1])
    assert len(g.players[0].hand) == hand + 2 and g.objects[foe].damage == 0
    _run_spell(g, db, "Shakedown", picks=[0])
    assert g.objects[foe].damage == 6 or g.objects[foe].zone == "trash"


def test_albus_ferros_and_overt_operation(db, decks):
    g = main_phase(db, decks)
    a = put(g, db, 0, "Hunting Dog", ("base", 0)); b = put(g, db, 0, "Hunting Dog", ("base", 0), exclude=(a,))
    g.objects[a].buffs = g.objects[b].buffs = 1
    g.objects[a].exhausted = True
    _run_spell(g, db, "Overt Operation", picks=[(a,)])
    assert not g.objects[a].exhausted and g.objects[a].buffs == 1 and g.objects[b].buffs == 1
    runes = len(g.players[0].runes)
    al = put(g, db, 0, "Albus Ferros", ("base", 0), exclude=(a, b))
    _fire(g, al, "Albus Ferros")
    settle(g, picks=[tuple(u for u in g.objects if u in (a, b))])
    assert len(g.players[0].runes) == runes + 2 and g.objects[a].buffs == 0


def test_mistfall_readies_a_buffed_unit(db, decks):
    g = main_phase(db, decks)
    m = put(g, db, 0, "Mistfall", ("base", 0))
    u = put(g, db, 0, "Hunting Dog", ("base", 0), exclude=(m,))
    r = g.players[0].runes[0]
    g.objects[r].defn = next(c for c in db if c.name == "Body Rune"); g.objects[r].domain = "body"; g.bump()
    g.objects[u].exhausted = True
    g.do_buff(u)
    settle(g)
    assert not g.objects[u].exhausted and g.objects[m].exhausted


def test_dazzling_aurora_plays_the_first_unit_revealed(db, decks):
    g = main_phase(db, decks)
    a = put(g, db, 0, "Dazzling Aurora", ("base", 0))
    deck = g.players[0].deck
    first_unit = next(u for u in deck if g.objects[u].base_defn().is_unit)
    before = [u for u in deck[:deck.index(first_unit)]]
    _fire(g, a, "Dazzling Aurora")
    settle(g)
    assert g.objects[first_unit].zone == "board"
    assert all(u in g.players[0].deck[-len(before):] for u in before) if before else True


def test_stormbringer_and_dragons_rage(db, decks):
    g = main_phase(db, decks)
    me = put(g, db, 0, "Elnuk Herd", ("base", 0))
    foe = put(g, db, 1, "Hunting Dog", ("bf", 0), exclude=(me,))
    _run_spell(g, db, "Stormbringer, Volibear", picks=[me, ("bf", 0)])
    assert g.objects[me].location == ("bf", 0) and (g.objects[foe].zone == "trash" or g.objects[foe].damage >= 3)
    g = main_phase(db, decks)
    a = put(g, db, 1, "Elnuk Herd", ("bf", 0))
    b = put(g, db, 1, "Hunting Dog", ("bf", 1), exclude=(a,))
    _run_spell(g, db, "Dragon's Rage, Lee Sin", picks=[a, ("bf", 1), b])
    assert g.objects[a].location == ("bf", 1) and g.objects[a].damage + g.objects[b].damage > 0 or g.objects[b].zone == "trash"


def test_smite_banishes_instead_of_dying(db, decks):
    g = main_phase(db, decks)
    foe = put(g, db, 1, "Hunting Dog", ("bf", 0))
    _run_spell(g, db, "Smite", picks=[foe])
    assert g.objects[foe].zone in ("banish", "board")
    g.do_kill([foe])
    assert g.objects[foe].zone == "banish"


def test_noxian_guillotine_kills_on_next_damage(db, decks):
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    foe = put(g, db, 1, "Elnuk Herd", ("bf", 0))
    _run_spell(g, db, "Noxian Guillotine, Darius", picks=[foe])
    assert g.objects[foe].zone == "board"
    g.do_deal([foe], 1, Context(0, None))
    settle(g)
    assert g.objects[foe].zone == "trash"


def test_card_sharp_gold_for_each_opponent_who_took_one(db, decks):
    g = main_phase(db, decks)
    cs = put(g, db, 0, "Card Sharp", ("base", 0))
    _fire(g, cs, "Card Sharp")
    settle(g, yes=True)
    golds = [o.controller for o in g.objects.values() if o.zone == "board" and o.defn.name == "Gold"]
    assert sorted(golds) == [0, 0, 1]


def test_riposte_counters_and_pumps(db, decks):
    from riftsim.core.objects import ChainItem
    g = main_phase(db, decks)
    u = put(g, db, 0, "Hunting Dog", ("base", 0))
    sp = _card_in(g, db, 1, "Get Excited!", "hand")
    g._to_zone(g.objects[sp], "chain"); g.bump()
    g.chain.append(ChainItem(900, "spell", 1, uid=sp, label="Get Excited!"))
    g.chain[-1].finalized = True        # only a finalized spell can be chosen (CR 355.9.a.2)
    base = g.chars(u).might
    _run_spell(g, db, "Riposte", picks=[u, sp])
    assert g.objects[sp].zone == "trash" and g.chars(u).might == base + (g.objects[sp].base_defn().energy or 0)


def test_strike_down_and_void_rush(db, decks):
    g = main_phase(db, decks)
    u = put(g, db, 0, "Elnuk Herd", ("base", 0))
    eq = put(g, db, 0, "Protector's Shield", ("base", 0), exclude=(u,))
    g.do_attach(eq, u); g.bump()
    foe = put(g, db, 1, "Elnuk Herd", ("bf", 0), exclude=(u, eq))
    _run_spell(g, db, "Strike Down", picks=[u, foe])
    assert g.objects[eq].attached_to is None and (g.objects[foe].damage > 0 or g.objects[foe].zone == "trash")
    top2 = g.players[0].deck[:2]
    hand = len(g.players[0].hand)
    _run_spell(g, db, "Void Rush", picks=[()])
    assert all(g.objects[x].zone == "hand" for x in top2) and len(g.players[0].hand) == hand + 2


def test_zenith_blade_stuns_and_may_move(db, decks):
    g = main_phase(db, decks)
    foe = put(g, db, 1, "Elnuk Herd", ("bf", 0))
    me = put(g, db, 0, "Hunting Dog", ("base", 0), exclude=(foe,))
    _run_spell(g, db, "Zenith Blade, Leona", picks=[(me,)])
    assert any(e["kind"] == "move" and e.get("uid") == me and e.get("to") == ("bf", 0) for e in g.events)   # then a showdown there


def test_deadly_flourish_gold_when_it_dies(db, decks):
    g = main_phase(db, decks)
    foe = put(g, db, 1, "Hunting Dog", ("bf", 0))
    _run_spell(g, db, "Deadly Flourish", picks=[foe])
    settle(g)
    golds = [o for o in g.objects.values() if o.zone == "board" and o.defn.name == "Gold" and o.controller == 0]
    assert g.objects[foe].zone == "trash" and len(golds) == 1


def test_abandon_returns_the_spell_to_hand(db, decks):
    from riftsim.core.objects import ChainItem
    g = main_phase(db, decks)
    sp = _card_in(g, db, 1, "Get Excited!", "hand")
    g._to_zone(g.objects[sp], "chain"); g.bump()
    g.chain.append(ChainItem(900, "spell", 1, uid=sp, label="Get Excited!"))
    g.chain[-1].finalized = True        # only a finalized spell can be chosen (CR 355.9.a.2)
    _run_spell(g, db, "Abandon", picks=[sp])
    assert g.objects[sp].zone == "hand" and sp in g.players[1].hand


def test_suave_negotiator_and_disposal_order(db, decks):
    g = main_phase(db, decks)
    h0, h1 = len(g.players[0].hand), len(g.players[1].hand)
    s = put(g, db, 0, "Suave Negotiator", ("base", 0))
    _fire(g, s, "Suave Negotiator"); settle(g)
    assert len(g.players[0].hand) == h0 + 1 and len(g.players[1].hand) == h1 + 1
    t = [g.players[1].deck[i] for i in range(4)]
    for u in t:
        g._to_zone(g.objects[u], "trash")
    g.bump()
    _run_spell(g, db, "Disposal Order", picks=[0, (t[0],), (t[1],), (t[2],)])
    assert [g.objects[u].zone for u in t] == ["deck", "deck", "deck", "trash"]


def test_sirens_song_moves_a_unit_that_moved(db, decks):
    g = main_phase(db, decks)
    a = put(g, db, 1, "Hunting Dog", ("bf", 0))
    b = put(g, db, 1, "Hunting Dog", ("bf", 0), exclude=(a,))
    g.do_move([a], ("bf", 1), None) if hasattr(g, "do_move") else None
    assert g.objects[a].location == ("bf", 1)
    _run_spell(g, db, "Siren's Song", picks=[("base", 1)])
    assert g.objects[a].location == ("base", 1) and g.objects[b].location == ("bf", 0)


def test_elder_dragon_any_damage_kills(db, decks):
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    put(g, db, 0, "Elder Dragon", ("base", 0))
    foe = put(g, db, 1, "Elnuk Herd", ("bf", 0))
    mine = put(g, db, 0, "Elnuk Herd", ("bf", 1), exclude=(foe,))
    g.do_deal([foe], 1, Context(0, None)); g.do_deal([mine], 1, Context(0, None))
    settle(g)
    assert g.objects[foe].zone == "trash" and g.objects[mine].zone == "board"


def test_insightful_investigator_pays_xp(db, decks):
    g = main_phase(db, decks)
    g.players[0].xp = 2
    target = g.players[1].hand[0]
    ii = put(g, db, 0, "Insightful Investigator", ("base", 0))
    h1 = len(g.players[1].hand)
    _fire(g, ii, "Insightful Investigator"); settle(g, picks=[target])
    assert g.players[0].xp == 0 and g.objects[target].zone == "trash" and len(g.players[1].hand) == h1


def test_radiance_batch_simple_spells(db, decks):
    g = main_phase(db, decks)
    me = put(g, db, 0, "Hunting Dog", ("base", 0))
    foe = put(g, db, 1, "Elnuk Herd", ("bf", 0), exclude=(me,))
    _run_spell(g, db, "One-Two Punch", picks=[me, foe])
    assert g.objects[me].buffs == 1 and g.objects[foe].stunned
    g.objects[me].exhausted = True
    base = g.chars(me).might
    _run_spell(g, db, "Raucous Anthem")
    assert not g.objects[me].exhausted and g.chars(me).might == base + 3


def test_steadfast_outrider_and_party_crasher(db, decks):
    g = main_phase(db, decks)
    so = put(g, db, 0, "Steadfast Outrider", ("bf", 0))
    m = g.chars(so).might
    a = put(g, db, 0, "Hunting Dog", ("bf", 0), exclude=(so,))
    assert g.chars(so).might == m
    put(g, db, 0, "The Good Stuff", ("bf", 0), exclude=(so, a))
    assert g.chars(so).might == m + 2
    pc = _card_in(g, db, 0, "Party Crasher", "hand")
    e0 = g.card_cost(0, pc, "hand")[0]
    g.objects[a].exhausted = True; g.objects[so].exhausted = True; g.bump()
    assert g.card_cost(0, pc, "hand")[0] == max(0, e0 - 2)


def test_ntofo_strikes_and_cosmic_vista(db, decks):
    g = main_phase(db, decks)
    me = put(g, db, 0, "Hunting Dog", ("base", 0))
    foe = put(g, db, 1, "Elnuk Herd", ("bf", 0), exclude=(me,))
    _run_spell(g, db, "Ntofo Strikes", picks=[me, foe])
    assert g.chars(me).kw("shield") == 2 and (g.objects[foe].damage == 2 or g.objects[foe].zone == "trash")
    _bf_card(g, db, "Cosmic Vista", 1); g.set_bf_controller(1, 0)
    pts = g.players[0].points
    g.emit("hold", player=0, loc=("bf", 1), bf=1, units=()); settle(g)
    assert g.players[0].points == pts
    g.players[0].rune_deck.clear()
    g.set_bf_controller(1, 0)                          # (no units there, so control lapsed after the first hold)
    g.emit("hold", player=0, loc=("bf", 1), bf=1, units=()); settle(g)
    assert g.players[0].points == pts + 1


def test_remember_the_fallen_plays_cheap_cards_from_trash(db, decks):
    g = main_phase(db, decks)
    a = _card_in(g, db, 0, "Hunting Dog", "trash")
    b = _card_in(g, db, 0, "Elnuk Herd", "trash")      # costs 6: not allowed
    _run_spell(g, db, "Remember the Fallen", picks=[(a,), ()])
    assert g.objects[a].zone == "board" and g.objects[b].zone == "trash"


def test_rousing_display_and_cataclysm(db, decks):
    g = main_phase(db, decks)
    _run_spell(g, db, "Rousing Display")
    assert sum(1 for o in g.objects.values() if o.zone == "board" and o.defn.name == "Recruit" and o.controller == 0) == 2
    me = put(g, db, 0, "Hunting Dog", ("base", 0))
    put(g, db, 1, "Elnuk Herd", ("bf", 1), exclude=(me,)); g.set_bf_controller(1, 1)
    _run_spell(g, db, "Cataclysm", picks=[me])
    assert any(e["kind"] == "move" and e.get("uid") == me and e.get("to") == ("bf", 1) for e in g.events)


def test_black_rose_sanctum_once_per_player_per_turn(db, decks):
    g = main_phase(db, decks)
    _bf_card(g, db, "Black Rose Sanctum", 0)
    a = put(g, db, 1, "Hunting Dog", ("bf", 0)); b = put(g, db, 1, "Hunting Dog", ("bf", 0), exclude=(a,))
    g.do_kill([a]); settle(g); g.do_kill([b]); settle(g)
    assert sum(1 for o in g.objects.values() if o.zone == "board" and o.defn.name == "Recruit" and o.controller == 1) == 1


def test_mechanical_bandit_draws_the_lowest(db, decks):
    g = main_phase(db, decks)
    mb = put(g, db, 0, "Mechanical Bandit", ("base", 0))
    t0, t1 = g.players[0].deck[0], g.players[1].deck[0]
    g.objects[t0].defn = next(c for c in db if c.name == "Hunting Dog")
    g.objects[t1].defn = next(c for c in db if c.name == "Elnuk Herd")
    _fire(g, mb, "Mechanical Bandit"); settle(g)
    assert g.objects[t0].zone == "hand" and g.objects[t1].zone == "deck" and g.players[1].deck[-1] == t1


def test_seraphic_wyvern_channels_one_more_exhausted(db, decks):
    g = main_phase(db, decks)
    put(g, db, 0, "Seraphic Wyvern", ("base", 0))
    n = len(g.players[0].runes)
    made = g.do_channel(0, 1)
    assert len(made) == 2 and not g.objects[made[0]].exhausted and g.objects[made[1]].exhausted
    assert len(g.players[0].runes) == n + 2


def test_waters_wage_and_piltovan_guidebot(db, decks):
    g = main_phase(db, decks)
    _run_spell(g, db, "The Waters' Wage")
    golds = [o for o in g.objects.values() if o.zone == "board" and o.defn.name == "Gold"]
    assert len(golds) == 1 and golds[0].exhausted
    gb = put(g, db, 0, "Piltovan Guidebot", ("base", 0))
    big = _card_in(g, db, 0, "Supernova", "hand")
    g.emit("play", uid=big, player=0, card_type="spell"); settle(g)
    assert g.chars(gb).might == 9


def test_transpositionist_and_bottled_constellation(db, decks):
    g = main_phase(db, decks)
    t = put(g, db, 0, "Transpositionist", ("base", 0))
    r = g.players[0].runes[0]
    g.objects[r].defn = next(c for c in db if c.name == "Chaos Rune"); g.objects[r].domain = "chaos"; g.bump()
    big = put(g, db, 0, "Elnuk Herd", ("bf", 0), exclude=(t,))
    small = _card_in(g, db, 0, "Hunting Dog", "hand")
    _fire(g, t, "Transpositionist", ctx_vars={})
    settle(g, picks=[big, (small,)])
    assert g.objects[big].zone == "hand" and g.objects[small].zone == "board"
    g = main_phase(db, decks)
    bc = put(g, db, 0, "Bottled Constellation", ("base", 0))
    us = []
    for _ in range(3):
        us.append(put(g, db, 0, "Hunting Dog", ("base", 0), exclude=tuple(us) + (bc,)))
    pts = g.players[0].points
    _fire(g, bc, "Bottled Constellation")
    order = [u for u in g.objects if u in us]
    settle(g, picks=[(order[0],), (order[1],), (order[2],)])
    assert all(g.objects[u].zone == "trash" for u in us) and g.players[0].points == pts + 1


def test_bushwhack_units_enter_ready(db, decks):
    g = main_phase(db, decks)
    _run_spell(g, db, "Bushwhack")
    u = g.play_token(0, "Recruit", ("base", 0))
    assert not g.objects[u].exhausted


def test_flame_chompers_from_discard(db, decks):
    g = main_phase(db, decks)
    fc = _card_in(g, db, 0, "Flame Chompers", "hand")
    r = g.players[0].runes[0]
    g.objects[r].defn = next(c for c in db if c.name == "Fury Rune"); g.objects[r].domain = "fury"; g.bump()
    g.do_discard(0, [fc]); settle(g)
    assert g.objects[fc].zone == "board"


def test_party_favors_and_kings_edict(db, decks):
    g = main_phase(db, decks)
    h0, h1 = len(g.players[0].hand), len(g.players[1].hand)
    _run_spell(g, db, "Party Favors", picks=[0])
    assert len(g.players[0].hand) == h0 + 1 and len(g.players[1].hand) == h1 + 1
    a = put(g, db, 1, "Hunting Dog", ("bf", 0)); b = put(g, db, 1, "Elnuk Herd", ("bf", 0), exclude=(a,))
    _run_spell(g, db, "King's Edict", picks=[a])
    assert g.objects[a].zone == "trash" and g.objects[b].zone == "board"


def test_fox_fire_total_might_four(db, decks):
    g = main_phase(db, decks)
    a = put(g, db, 1, "Hunting Dog", ("bf", 0)); b = put(g, db, 1, "Hunting Dog", ("bf", 0), exclude=(a,))
    c = put(g, db, 1, "Elnuk Herd", ("bf", 0), exclude=(a, b))
    ma, mb = g.chars(a).might, g.chars(b).might
    _run_spell(g, db, "Fox-Fire, Ahri", picks=[("bf", 0), (a,), (b,), ()])
    killed = [u for u in (a, b, c) if g.objects[u].zone == "trash"]
    assert sum(g.chars(u).might or 0 for u in killed) <= 4 + 0 and c not in killed and a in killed
    assert (b in killed) == (ma + mb <= 4)


def test_blind_fury_plays_the_opponents_top_card(db, decks):
    g = main_phase(db, decks)
    top = g.players[1].deck[0]
    g.objects[top].defn = next(c for c in db if c.name == "Hunting Dog"); g.bump()
    _run_spell(g, db, "Blind Fury")
    assert g.objects[top].zone == "board" and g.objects[top].controller == 0


def test_stand_united_and_spirits_refuge(db, decks):
    g = main_phase(db, decks)
    u = put(g, db, 0, "Hunting Dog", ("base", 0))
    v = put(g, db, 0, "Hunting Dog", ("base", 0), exclude=(u,))
    g.objects[v].buffs = 1; g.bump()
    base_u, base_v = g.chars(u).might, g.chars(v).might
    _run_spell(g, db, "Stand United", picks=[u])
    assert g.chars(u).might == base_u + 2 and g.chars(v).might == base_v + 1
    sr = put(g, db, 0, "Spirit's Refuge", ("base", 0), exclude=(u, v))
    assert g.has_keyword(v, "deflect")


def test_symbol_of_the_solari_recalls_everyone_on_a_tie(db, decks):
    g = main_phase(db, decks)
    put(g, db, 0, "Symbol of the Solari", ("base", 0))
    a = put(g, db, 0, "Elnuk Herd", ("bf", 0)); d = put(g, db, 1, "Elnuk Herd", ("bf", 0), exclude=(a,))
    g.combat = {"bf": 0, "attacker": 0, "defender": 1, "step": "damage"}
    g._task_combat_cleanup()
    assert g.objects[a].location == ("base", 0) and g.objects[d].location == ("base", 1)
    g.combat = None


def test_counter_strike_lotus_trap_hostile_takeover(db, decks):
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    u = put(g, db, 1, "Elnuk Herd", ("bf", 0))
    _run_spell(g, db, "Counter Strike", picks=[u])
    g.do_deal([u], 2, Context(0, None))
    assert g.objects[u].damage == 0
    g.do_deal([u], 1, Context(0, None))
    assert g.objects[u].damage == 1
    _run_spell(g, db, "Lotus Trap", picks=[u])
    g.do_deal([u], 1, Context(0, None))
    assert g.objects[u].damage == 3
    g = main_phase(db, decks)
    foe = put(g, db, 1, "Hunting Dog", ("bf", 0))
    g.objects[foe].exhausted = True
    _run_spell(g, db, "Hostile Takeover", picks=[foe])
    assert g.objects[foe].controller == 0 and not g.objects[foe].exhausted


def test_flurry_of_feathers_birds_and_rippers_bay(db, decks):
    g = main_phase(db, decks)
    _run_spell(g, db, "Flurry of Feathers", picks=[1])
    birds = [o for o in g.objects.values() if o.zone == "board" and o.defn.name == "Bird" and o.controller == 0]
    assert len(birds) == 4
    _bf_card(g, db, "Ripper's Bay", 0)
    u = put(g, db, 0, "Hunting Dog", ("bf", 0))
    n = len(g.players[0].runes)
    g.put_in_hand(u); settle(g, yes=True)
    assert len(g.players[0].runes) == n + 1


def test_jagged_cutlass_unit_cant_be_moved_by_enemies(db, decks):
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    u = put(g, db, 0, "Shipyard Skulker", ("bf", 0))
    gear = put(g, db, 0, "Jagged Cutlass", ("base", 0), exclude=(u,))
    g.do_attach(gear, u); g.bump()
    assert not g.do_move([u], ("base", 0), Context(1, None))      # an enemy effect
    assert g.objects[u].location == ("bf", 0)
    assert g.do_move([u], ("base", 0), Context(0, None))          # its controller's own effect still moves it


def test_blighted_battleaxe_hurts_a_unit_that_did_not_conquer(db, decks):
    g = main_phase(db, decks)
    u = put(g, db, 0, "Mega-Mech", ("base", 0))
    gear = put(g, db, 0, "Blighted Battleaxe", ("base", 0), exclude=(u,))
    g.do_attach(gear, u); g.bump()
    g.emit("ending_phase", player=0)
    settle(g)
    assert g.objects[gear].attached_to is None and g.objects[u].damage == 4


def test_perched_grimwyrm_only_to_a_battlefield_conquered_this_turn(db, decks):
    g = main_phase(db, decks)
    from test_targeting import give
    u = give(g, 0, "Perched Grimwyrm", db)
    g.set_bf_controller(0, 0)
    put(g, db, 0, "Shipyard Skulker", ("bf", 0), exclude=(u,))
    assert g._play_locations(0, u, "hand") == []
    g.turn_memo[("conquered_bfs", 0)] = {0}
    assert g._play_locations(0, u, "hand") == [("bf", 0)]


def test_dune_surfer_ignores_tank_here(db, decks):
    g = main_phase(db, decks)
    bf = ("bf", 0)
    tank = put(g, db, 1, "Mutated Mouser", bf)               # [Shield 2] [Tank]
    other = put(g, db, 1, "Shipyard Skulker", bf, exclude=(tank,))
    assert all(p[0] > 0 for p in g._damage_plans([tank, other], 2, 0))
    put(g, db, 0, "Dune Surfer", bf, exclude=(tank, other))
    assert any(p[0] == 0 for p in g._damage_plans([tank, other], 2, 0))


def _enemy_spell_on_chain(g, db, name="Get Excited!"):
    from riftsim.core.objects import ChainItem
    sp = _card_in(g, db, 1, name, "hand")
    g._to_zone(g.objects[sp], "chain"); g.bump()
    it = ChainItem(900, "spell", 1, uid=sp, label=name)
    from riftsim.core.vm import Context
    it.cost, it.finalized, it.ctx, it.code = {"energy": 0, "power": []}, True, Context(1, sp), []
    g.chain.append(it)
    return sp, it


def test_hard_bargain_counters_unless_its_controller_pays_two(db, decks):
    g = main_phase(db, decks)
    sp, it = _enemy_spell_on_chain(g, db)
    _run_spell(g, db, "Hard Bargain", picks=[sp, "decline"])
    assert it.countered and g.objects[sp].zone == "trash"
    g = main_phase(db, decks)
    sp, it = _enemy_spell_on_chain(g, db)
    g.do_channel(1, 2)
    ready = sum(not g.objects[r].exhausted for r in g.players[1].runes)
    assert ready >= 2
    _run_spell(g, db, "Hard Bargain", picks=[sp])      # the opponent's first pay option is a payment plan
    assert not getattr(it, "countered", False)
    assert sum(not g.objects[r].exhausted for r in g.players[1].runes) == ready - 2


def test_hard_bargain_counters_when_controller_cannot_pay(db, decks):
    g = main_phase(db, decks)
    sp, it = _enemy_spell_on_chain(g, db)
    for r in g.players[1].runes:
        g.objects[r].exhausted = True
    g.bump()
    _run_spell(g, db, "Hard Bargain", picks=[sp])
    assert it.countered


def test_marai_spire_repeat_costs_one_less(db, decks):
    from riftsim.core.objects import ChainItem
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    s = _card_in(g, db, 0, "Hard Bargain", "hand")
    it = ChainItem(901, "spell", 0, uid=s, label="Hard Bargain")
    rep = dict(g._optional_costs(it, Context(0, None)))["repeat"]
    assert rep[0] == 2
    _bf_card(g, db, "Marai Spire", 0)
    g.set_bf_controller(0, 0); g.bump()
    rep = dict(g._optional_costs(it, Context(0, None)))["repeat"]
    assert rep[0] == 1


def test_ornns_forge_first_gear_each_turn_costs_one_less(db, decks):
    g = main_phase(db, decks)
    gear = next(c.name for c in db if c.is_gear and not c.is_token and (c.energy or 0) >= 2)
    a = _card_in(g, db, 0, gear, "hand")
    base = g.card_cost(0, a, "hand")[0]
    _bf_card(g, db, "Ornn's Forge", 0)
    g.set_bf_controller(0, 0); g.bump()
    assert g.card_cost(0, a, "hand")[0] == base - 1
    assert g.card_cost(1, _card_in(g, db, 1, gear, "hand"), "hand")[0] == base     # only friendly gear
    g.turn_memo[("gear_played", 0)] = 1
    assert g.card_cost(0, a, "hand")[0] == base


def test_spirit_wheel_pays_one_and_exhausts_to_draw(db, decks):
    g = main_phase(db, decks)
    w = put(g, db, 0, "Spirit Wheel", ("base", 0))
    u = put(g, db, 0, "Rell, Magnetic", ("base", 0))
    hand = len(g.players[0].hand)
    g.emit("target", targets=(u,), player=0, item=None); settle(g, yes=True)
    assert g.objects[w].exhausted and len(g.players[0].hand) == hand + 1
    g = main_phase(db, decks)
    w = put(g, db, 0, "Spirit Wheel", ("base", 0))
    foe = put(g, db, 1, "Rell, Magnetic", ("bf", 0))
    hand = len(g.players[0].hand)
    g.emit("target", targets=(foe,), player=0, item=None); settle(g, yes=True)     # an enemy unit: no trigger
    assert not g.objects[w].exhausted and len(g.players[0].hand) == hand


def test_gearhead_doubles_equipment_base_might(db, decks):
    g = main_phase(db, decks)
    u = put(g, db, 0, "Gearhead", ("base", 0))
    eq = next(c.name for c in db if c.is_equipment and (c.might or 0) >= 1 and "Equip" in (c.text or ""))
    e = put(g, db, 0, eq, ("base", 0))
    base = g.chars(u).might
    g.do_attach(e, u); g.bump()
    assert g.chars(u).might == base + 2 * g.objects[e].defn.might


def test_needlessly_large_yordle_cheaper_per_hold_point(db, decks):
    g = main_phase(db, decks)
    y = _card_in(g, db, 0, "Needlessly Large Yordle", "hand")
    e, pw = g.card_cost(0, y, "hand")
    g.scored.discard((0, 0))
    g._score(0, 0, "hold")
    e2, pw2 = g.card_cost(0, y, "hand")
    assert e2 == max(0, e - 2) and pw2.count("calm") == max(0, pw.count("calm") - 1)


def test_mageseeker_warden_locks_play_locations_and_readying(db, decks):
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    g.set_bf_controller(1, 1); g.bump()
    u = _card_in(g, db, 1, "Rell, Magnetic", "hand")
    assert ("bf", 1) in g._play_locations(1, u, "hand")
    w = put(g, db, 0, "Mageseeker Warden", ("base", 0))
    assert ("bf", 1) in g._play_locations(1, u, "hand")          # only while it's at a battlefield
    g.objects[w].location = ("bf", 0); g.bump()
    assert g._play_locations(1, u, "hand") == [("base", 1)]
    foe = put(g, db, 1, "Hunting Dog", ("base", 1)); g.objects[foe].exhausted = True
    mine = put(g, db, 0, "Hunting Dog", ("base", 0), exclude=(foe,)); g.objects[mine].exhausted = True
    g.bump()
    assert not g.do_ready(foe, Context(1, None))
    assert g.do_ready(mine, Context(0, None))


def _rune_setup(g, db, p, domains):
    """Leave player p with ready runes of exactly these domains."""
    rdefs = {c.domains[0]: c for c in db if c.type == "rune" and len(c.domains) == 1}
    for i, r in enumerate(g.players[p].runes):
        o = g.objects[r]
        if i < len(domains):
            o.defn, o.domain, o.exhausted = rdefs[domains[i]], domains[i], False
        else:
            o.exhausted = True
    g.bump()


def test_kraken_hunter_spends_buffs_to_reduce_body(db, decks):
    g = main_phase(db, decks)
    a = put(g, db, 0, "Rell, Magnetic", ("base", 0)); g.objects[a].buffs = 1
    b = put(g, db, 0, "Hunting Dog", ("base", 0)); g.objects[b].buffs = 1
    k = _card_in(g, db, 0, "Kraken Hunter", "hand")
    _rune_setup(g, db, 0, ["body", "chaos", "chaos", "chaos"])
    assert not g.can_pay(0, *g.card_cost(0, k, "hand"))
    assert ("play", k, ("base", 0)) in g.legal_actions(0)       # playable only by spending at least one buff
    it = g._play(0, k, ("base", 0))
    g.pending = None
    seen = None
    for _ in range(40):
        d = g.run()
        if d.kind == "pick_many":
            seen = [set(o) for o in d.options]
            g.choose(next(o for o in d.options if set(o) == {a, b})); continue
        if it.cost.get("paid") is not None or (d.kind == "action" and not g.chain):
            break
        g.choose(d.options[0])
    assert seen is not None and set() not in seen and {a, b} in seen       # spending none is not legal here
    assert g.objects[a].buffs == 0 and g.objects[b].buffs == 0
    assert it.cost.get("paid") is not None and "body" not in it.cost["power"]


def test_commander_ledros_kills_friendly_units_to_reduce_order(db, decks):
    g = main_phase(db, decks)
    a = put(g, db, 0, "Hunting Dog", ("base", 0))
    led = _card_in(g, db, 0, "Commander Ledros", "hand")
    _rune_setup(g, db, 0, ["order"] * 3 + ["chaos"] * 5)
    ab = g._variable_reduce_perm(led)
    assert ab is not None and ab.value[0](g, 0, led) == [a] or a in ab.value[0](g, 0, led)
    e, pw = g.card_cost(0, led, "hand")
    from riftsim.core import payment
    need = g._variable_reduce_min(0, led, e, pw, payment.purpose_of_card(g, led))
    assert need == 1


def test_crescent_guardian_pays_chaos_after_a_spell_to_enter_ready(db, decks):
    g = main_phase(db, decks)
    cg = _card_in(g, db, 0, "Crescent Guardian", "hand")
    _rune_setup(g, db, 0, ["chaos"] * 6)
    ab = next(a for a in g.objects[cg].defn.abilities if getattr(a, "perm", "") == "additional_cost")
    assert not ab.cond(g, cg)
    sp = _card_in(g, db, 0, "Get Excited!", "trash")
    g.players[0].played_this_turn.append(sp)
    assert ab.cond(g, cg)
    it = g._play(0, cg, ("base", 0))
    g.pending = None
    asked = False
    for _ in range(40):
        d = g.run()
        if d.kind in ("yesno", "additional_cost"):
            asked = True; g.choose(True); continue
        if d.kind == "action" and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert asked and g.objects[cg].zone == "board" and not g.objects[cg].exhausted


def test_here_to_help_plays_a_unit_to_your_battlefield_for_three_less(db, decks):
    g = main_phase(db, decks)
    g.set_bf_controller(0, 0); g.bump()
    u = _card_in(g, db, 0, "Rell, Magnetic", "hand")
    e, pw = g.card_cost(0, u, "hand")
    _rune_setup(g, db, 0, [g.objects[u].base_defn().domains[0]] * max(len(pw), max(0, e - 3)))
    _run_spell(g, db, "Here to Help", picks=[(u,)])
    assert g.objects[u].zone == "board" and g.objects[u].location == ("bf", 0)


def test_temporal_portal_gives_next_spell_repeat_equal_to_its_cost(db, decks):
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    sp = _card_in(g, db, 0, "Get Excited!", "hand")
    e, pw = g.card_cost(0, sp, "hand")
    g.add_turn_effect(Context(0, None), "grant_repeat", {}, uses=1)
    it = g._play(0, sp, None)
    opts = dict(g._optional_costs(it, it.ctx))
    assert opts["repeat_granted"][:2] == (e, list(pw)) and g._optional_costs_include_repeat(it)
    sp2 = _card_in(g, db, 0, "Get Excited!", "hand")
    it2 = g._play(0, sp2, None)                       # only the next spell
    assert "repeat_granted" not in dict(g._optional_costs(it2, it2.ctx))


def test_the_academy_grants_repeat_equal_to_base_cost(db, decks):
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    sp = _card_in(g, db, 0, "Get Excited!", "hand")
    d = g.objects[sp].base_defn()
    _bf_card(g, db, "The Academy", 0)
    g.set_bf_controller(0, 0); g.bump()
    g.emit("hold", player=0, loc=("bf", 0), bf=0, units=()); settle(g)
    it = g._play(0, sp, None)
    rep = dict(g._optional_costs(it, it.ctx))["repeat_granted"]
    assert rep[0] == (d.energy or 0) and len(rep[1]) == (d.power or 0)


def test_firelights_hideout_next_unit_has_accelerate(db, decks):
    g = main_phase(db, decks)
    _bf_card(g, db, "Firelights' Hideout", 0)
    g.set_bf_controller(0, 0); g.bump()
    g.emit("conquer", player=0, loc=("bf", 0), bf=0, units=()); settle(g)
    u = next(c.name for c in db if c.is_unit and not c.keywords.get("accelerate") and c.domains)
    a = _card_in(g, db, 0, u, "hand")
    it = g._play(0, a, ("base", 0))
    assert "accelerate" in dict(g._optional_costs(it, it.ctx))


def _play_and_settle(g, p, uid, loc, yes):
    g._play(p, uid, loc)
    g.pending = None
    for _ in range(40):
        d = g.run()
        if d.kind == "yesno":
            g.choose(yes); continue
        if d.kind == "action" and not g.chain:
            return
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])


def test_entrenched_boar_may_enter_ready_but_then_cannot_move(db, decks):
    for yes in (True, False):
        g = main_phase(db, decks)
        b = _card_in(g, db, 0, "Entrenched Boar", "hand")
        _play_and_settle(g, 0, b, ("base", 0), yes)
        assert g.objects[b].zone == "board"
        assert g.objects[b].exhausted is (not yes) and g.cant_move(b) is yes


def test_noxian_emissary_empowered_deathknell_plays_two_recruits(db, decks):
    from riftsim.core.vm import Context
    for emp in (False, True):
        g = main_phase(db, decks)
        u = put(g, db, 0, "Noxian Emissary", ("base", 0))
        assert any(getattr(a, "is_empower", False) for a in g.abilities(u))
        g.objects[u].empowered = 1 if emp else 0; g.bump()
        n = sum(o.defn.name == "Recruit" and o.zone == "board" for o in g.objects.values())
        g.do_kill([u], Context(1, None)); settle(g)
        m = sum(o.defn.name == "Recruit" and o.zone == "board" for o in g.objects.values())
        assert m - n == (2 if emp else 0)
