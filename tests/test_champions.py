"""Champion unit scripts against printed text."""
import pathlib

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.scripts import script_all
from test_targeting import main_phase

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


@pytest.fixture(scope="module")
def decks(db):
    return [Deck.load(str(ROOT / "data/decks/tournament/riven_exile.json"), db),
            Deck.load(str(ROOT / "data/decks/tournament/kaisa_void.json"), db)]


def put(g, db, p, name, loc, exclude=()):
    """Put a fresh copy of card `name` on the board at loc (re-using a deck object), ready."""
    u = next(u for u in g.players[p].deck if u not in exclude and g.objects[u].zone == "deck")
    g.objects[u].defn = next(c for c in db if c.name == name)
    g._to_zone(g.objects[u], "board", location=loc, controller=p)
    g.objects[u].exhausted = False
    g.restruct()
    return u


def settle(g, yes=True, picks=()):
    picks = list(picks)
    g.dirty = True
    g.pending = None
    for _ in range(80):
        d = g.run()
        if d is None:
            return None
        if d.kind == "action" and not g.chain and g.showdown is None and g.combat is None:
            return d
        if picks and picks[0] in d.options:
            g.choose(picks.pop(0)); continue
        if d.kind == "yesno":
            g.choose(yes); continue
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    raise AssertionError("did not settle")


def test_master_yi_meditative_needs_8_runes(db, decks):
    g = main_phase(db, decks)
    u = put(g, db, 0, "Master Yi, Meditative", ("base", 0))
    base = g.objects[u].defn.might
    ps = g.players[0]
    while len(ps.runes) > 7:
        g._to_zone(g.objects[ps.runes[-1]], "rune_deck"); g.restruct()
    assert g.chars(u).might == base
    while len(ps.runes) < 8:
        g.channel(0, 1) if hasattr(g, "channel") else g._to_zone(g.objects[ps.rune_deck[0]], "board", controller=0)
        g.restruct()
    assert g.chars(u).might == base + 4


def test_sett_kingpin_and_lee_sin_centered_count_buffed_units_at_their_battlefield(db, decks):
    g = main_phase(db, decks)
    sett = put(g, db, 0, "Sett, Kingpin", ("bf", 0))
    lee = put(g, db, 0, "Lee Sin, Centered", ("bf", 0), exclude=(sett,))
    other = put(g, db, 0, "Sett, Kingpin", ("base", 0), exclude=(sett, lee))
    s0, l0 = g.chars(sett).might, g.chars(lee).might
    g.objects[lee].buffs = 1; g.restruct()
    assert g.chars(sett).might == s0 + 1            # one buffed unit there; Sett isn't buffed, so no +2 from Lee Sin
    assert g.chars(lee).might == l0 + 1             # the buff counter only; Lee Sin's static says "other"
    g.objects[other].buffs = 1; g.restruct()            # at base: doesn't count
    assert g.chars(sett).might == s0 + 1
    g.objects[sett].buffs = 1; g.restruct()             # own buff +1, two buffed units +2, Lee Sin +2
    assert g.chars(sett).might == s0 + 5


def test_kogmaw_deathknell_hits_all_units_at_his_battlefield(db, decks):
    g = main_phase(db, decks)
    kog = put(g, db, 0, "Kog'Maw, Caustic", ("bf", 0))
    foe = put(g, db, 1, "Sett, Kingpin", ("bf", 0))
    far = put(g, db, 1, "Sett, Kingpin", ("bf", 1), exclude=(foe,))
    g.do_kill([kog])
    settle(g)
    assert g.objects[foe].damage == 4 or g.objects[foe].zone == "trash"
    assert g.objects[far].damage == 0


def test_vi_doubles_her_might(db, decks):
    g = main_phase(db, decks)
    vi = put(g, db, 0, "Vi, Hotheaded", ("base", 0))
    m = g.chars(vi).might
    ab = g.abilities(vi)[0]
    assert ab.cost["energy"] == 2 and ab.cost["power"] == ["fury"]
    from riftsim.core.vm import Context
    from riftsim.core.vm import run_vm, Frame
    ctx = Context(0, vi)
    ctx.vars["self"] = vi
    g.vm_frames.append(Frame(ab.code, ctx))
    settle(g)
    assert g.chars(vi).might == 2 * m


def test_volibear_draws_once_per_opponent_move_elsewhere(db, decks):
    g = main_phase(db, decks)
    voli = put(g, db, 0, "Volibear, Imposing", ("bf", 0))
    a = put(g, db, 1, "Sett, Kingpin", ("base", 1))
    b = put(g, db, 1, "Sett, Kingpin", ("base", 1), exclude=(a,))
    hand = len(g.players[0].hand)
    g.do_move([a, b], ("bf", 1))
    settle(g)
    assert len(g.players[0].hand) == hand + 1


def test_leblanc_fragmented_draws_one_outside_beginning_phase(db, decks):
    g = main_phase(db, decks)
    lb = put(g, db, 0, "LeBlanc, Fragmented", ("base", 0))
    hand = len(g.players[0].hand)
    g.do_kill([lb])
    settle(g)
    assert len(g.players[0].hand) == hand + 1


def test_xin_zhao_enters_ready_with_two_other_units_in_base(db, decks):
    g = main_phase(db, decks)
    for u in [u for u, o in g.objects.items() if o.zone == "board" and o.location == ("base", 0) and "unit" in g.chars(u).types]:
        g._to_zone(g.objects[u], "trash")
    s1 = put(g, db, 0, "Sett, Kingpin", ("base", 0))
    u = next(u for u in g.players[0].deck if g.objects[u].zone == "deck")
    g.objects[u].defn = next(c for c in db if c.name == "Xin Zhao, Vigilant")
    g._to_zone(g.objects[u], "hand"); g.restruct()
    ev = {"kind": "enter_ready", "uid": u, "player": 0, "ready": False, "loc": ("base", 0)}
    assert g.replace_event(dict(ev))["ready"] is False      # only one other unit in base
    put(g, db, 0, "Sett, Kingpin", ("base", 0), exclude=(s1, u))
    assert g.replace_event(dict(ev))["ready"] is True


def test_shen_leader_scores_when_holding_with_exactly_one_other_unit(db, decks):
    g = main_phase(db, decks)
    shen = put(g, db, 0, "Shen, Leader of the Kinkou Order", ("bf", 0))
    pts = g.players[0].points
    g.emit("hold", player=0, loc=("bf", 0), bf=0, units=(shen,))
    settle(g)
    assert g.players[0].points == pts                      # alone: no point
    put(g, db, 0, "Sett, Kingpin", ("bf", 0), exclude=(shen,))
    g.emit("hold", player=0, loc=("bf", 0), bf=0, units=(shen,))
    settle(g)
    assert g.players[0].points in (pts + 1,)


def test_riven_shattered_deals_2_per_equipment(db, decks):
    g = main_phase(db, decks)
    riv = put(g, db, 0, "Riven, Shattered", ("bf", 0))
    foe = put(g, db, 1, "Sett, Kingpin", ("bf", 0))
    eq = next(c for c in db if c.type == "gear" and "Equipment" in c.tags)
    for i in range(2):
        e = put(g, db, 0, eq.name, ("bf", 0), exclude=(riv, foe))
        g.objects[e].defn = eq
        g.objects[riv].attachments.append(e)
        g.objects[e].attached_to = riv if hasattr(g.objects[e], "attached_to") else None
    g.restruct()
    ab = next(a for a in g.abilities(riv) if a.label == "Riven, Shattered")
    from riftsim.core.vm import Context
    ctx = Context(0, riv, here=("bf", 0)); ctx.vars["self"] = riv; ctx.vars["t"] = foe
    from riftsim.core.vm import Frame
    g.vm_frames.append(Frame(ab.code, ctx))
    settle(g)
    assert g.objects[foe].damage == 4 or g.objects[foe].zone == "trash"


def test_swain_scores_after_unit_gear_and_spell(db, decks):
    g = main_phase(db, decks)
    sw = put(g, db, 0, "Swain, Visionary", ("bf", 0))
    pts = g.players[0].points
    unit = next(c for c in db if c.is_unit and not c.is_token)
    gear = next(c for c in db if c.type == "gear" and not c.is_token)
    spell = next(c for c in db if c.type == "spell")
    used = []
    for d in (unit, gear, spell):
        u = next(u for u in g.players[0].deck if g.objects[u].zone == "deck" and u not in used)
        g.objects[u].defn = d; used.append(u)
    g.players[0].played_this_turn.extend(used[:2])
    g.emit("conquer", player=0, loc=("bf", 0), bf=0, units=(sw,))
    settle(g)
    assert g.players[0].points == pts                      # no spell yet
    g.players[0].played_this_turn.append(used[2])
    g.emit("conquer", player=0, loc=("bf", 0), bf=0, units=(sw,))
    settle(g)
    assert g.players[0].points == pts + 1


def _card_in(g, db, p, name, zone):
    u = next(u for u in g.players[p].deck if g.objects[u].zone == "deck")
    g.objects[u].defn = next(c for c in db if c.name == name)
    g._to_zone(g.objects[u], zone)
    g.restruct()
    return u


def _fire(g, uid, label, ctx_vars=None, here=None):
    from riftsim.core.vm import Context, Frame
    ab = next(a for a in g.abilities(uid) if a.label == label)
    ctx = Context(g.objects[uid].controller, uid, here=here or g.objects[uid].place)
    ctx.vars["self"] = uid
    ctx.vars.update(ctx_vars or {})
    from riftsim.core.vm import relocate
    tc = list(ab.target_code or [])
    g.vm_frames.append(Frame(tc + relocate(ab.code, len(tc)), ctx))
    return ctx


def test_ornn_draws_a_gear_from_the_top_4(db, decks):
    g = main_phase(db, decks)
    ornn = put(g, db, 0, "Ornn, Blacksmith", ("base", 0))
    deck = g.players[0].deck
    gear = next(c for c in db if c.type == "gear" and not c.is_token)
    g.objects[deck[2]].defn = gear
    target = deck[2]
    hand = len(g.players[0].hand)
    _fire(g, ornn, "Ornn, Blacksmith")
    settle(g, picks=[(target,)])
    assert g.objects[target].zone == "hand" and len(g.players[0].hand) == hand + 1


def test_fiora_doubles_only_one_on_one(db, decks):
    g = main_phase(db, decks)
    fi = put(g, db, 0, "Fiora, Peerless", ("bf", 0))
    foe = put(g, db, 1, "Sett, Kingpin", ("bf", 0))
    g.combat = {"bf": 0, "attacker": 0, "defender": 1, "step": "showdown"}
    m = g.chars(fi).might
    _fire(g, fi, "Fiora, Peerless")
    g.dirty = True; g.pending = None
    for _ in range(10):
        d = g.run()
        if not g.vm_frames:
            break
        g.choose(d.options[0])
    assert g.chars(fi).might == 2 * m


def test_poppy_readies_and_gains_xp_when_an_opponent_is_close(db, decks):
    g = main_phase(db, decks)
    pop = put(g, db, 0, "Poppy, Paragon", ("base", 0))
    g.objects[pop].exhausted = True
    g.players[1].points = g.cfg["victory"] - 3
    xp = g.players[0].xp
    _fire(g, pop, "Poppy, Paragon")
    settle(g)
    assert not g.objects[pop].exhausted and g.players[0].xp == xp + 3


def test_fizz_replays_a_cheap_spell_from_trash_and_recycles_it(db, decks):
    g = main_phase(db, decks)
    fz = put(g, db, 0, "Fizz, Trickster", ("base", 0))
    have = {g.objects[r].defn.domains[0] for r in g.players[0].runes if g.objects[r].defn.domains}
    cheap = next(c for c in db if c.type == "spell" and (c.energy or 0) <= 3 and "draw" in (c.text or "").lower()
                 and not any(w in c.text.lower() for w in ("unit", "choose", "gear", "discard", "hidden", "spell"))
                 and set(c.domains) <= have)
    u = next(u for u in g.players[0].deck if g.objects[u].zone == "deck")
    g.objects[u].defn = cheap
    g._to_zone(g.objects[u], "trash"); g.restruct()
    _fire(g, fz, "Fizz, Trickster")
    settle(g, picks=[(u,)])
    assert g.objects[u].zone == "deck" and g.players[0].deck[-1] == u


def test_jayce_man_of_progress_makes_next_gear_free(db, decks):
    g = main_phase(db, decks)
    jc = put(g, db, 0, "Jayce, Man of Progress", ("base", 0))
    old = put(g, db, 0, next(c.name for c in db if c.type == "gear" and not c.is_token), ("base", 0), exclude=(jc,))
    big = next(c for c in db if c.type == "gear" and 4 <= (c.energy or 0) <= 7 and not c.is_token)
    h = _card_in(g, db, 0, big.name, "hand")
    _fire(g, jc, "Jayce, Man of Progress")
    settle(g, yes=True, picks=[old])
    assert g.objects[old].zone == "trash"
    assert g.card_cost(0, h, "hand", ("base", 0))[0] == 0


def test_yasuo_windrider_scores_on_third_move(db, decks):
    g = main_phase(db, decks)
    y = put(g, db, 0, "Yasuo, Windrider", ("base", 0))
    fired = lambda: [e for e in g.events if e.get("kind") == "trigger" and e.get("label") == "Yasuo, Windrider"]
    for dest in [("bf", 0), ("base", 0)]:
        g.do_move([y], dest); settle(g)
    assert not fired()
    g.do_move([y], ("bf", 1)); settle(g)
    assert len(fired()) == 1


def test_kayn_takes_no_damage_after_moving_twice(db, decks):
    g = main_phase(db, decks)
    k = put(g, db, 0, "Kayn, Unleashed", ("base", 0))
    g.do_move([k], ("bf", 0)); settle(g)
    g.do_move([k], ("base", 0)); settle(g)
    assert g.replace_event({"kind": "damage", "uid": k, "amount": 3}) is None


def test_ambessa_empowered_ignores_damage_outside_combat(db, decks):
    g = main_phase(db, decks)
    a = put(g, db, 0, "Ambessa, The Wolf", ("base", 0))
    m = g.chars(a).might
    assert g.replace_event({"kind": "damage", "uid": a, "amount": 3}) is not None
    g.objects[a].empowered = 1; g.restruct()
    assert g.chars(a).might == m + 3
    assert g.replace_event({"kind": "damage", "uid": a, "amount": 3}) is None


def test_sona_readies_four_runes_at_end_of_turn_at_a_battlefield(db, decks):
    g = main_phase(db, decks)
    put(g, db, 0, "Sona, Harmonious", ("bf", 0))
    for r in g.players[0].runes:
        g.objects[r].exhausted = True
    g.restruct()
    g.pending = None
    g.run()
    g.choose(("end_turn",))
    for _ in range(60):
        d = g.run()
        if g.turn_player == 1:
            break
        if d.kind in ("choose", "choose_many", "pick_many") and all(isinstance(o, tuple) for o in d.options):
            g.choose(max(d.options, key=len))            # "up to 4" (errata): take all four
            continue
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert sum(not g.objects[r].exhausted for r in g.players[0].runes) == min(4, len(g.players[0].runes))


def test_vex_cheerless_changes_spell_costs_only_in_combat(db, decks):
    g = main_phase(db, decks)
    vx = put(g, db, 0, "Vex, Cheerless", ("bf", 0))
    spell = next(c for c in db if c.type == "spell" and (c.energy or 0) >= 3)
    mine = _card_in(g, db, 0, spell.name, "hand")
    theirs = _card_in(g, db, 1, spell.name, "hand")
    e0, p0 = g.card_cost(0, mine, "hand")
    assert g.card_cost(1, theirs, "hand") == (e0, p0)
    g.combat = {"bf": 0, "attacker": 0, "defender": 1, "step": "showdown"}
    g.restruct()
    e1, p1 = g.card_cost(0, mine, "hand")
    assert e1 == e0 - 1 and len(p1) == max(0, len(p0) - 1)
    e2, p2 = g.card_cost(1, theirs, "hand")
    assert e2 == e0 + 1 and len(p2) == len(p0) + 1


def test_draven_scores_first_combat_win_and_gives_a_point_when_he_dies_in_combat(db, decks):
    g = main_phase(db, decks)
    dr = put(g, db, 0, "Draven, Audacious", ("bf", 0))
    p1 = g.players[1].points
    ab = [a for a in g.abilities(dr) if a.label == "Draven, Audacious"]
    assert len(ab) == 2
    _fire(g, dr, "Draven, Audacious")       # first ability: win combat -> score
    settle(g)
    from riftsim.core.vm import Context, Frame
    ctx = Context(0, dr); ctx.vars["self"] = dr
    g.vm_frames.append(Frame(list(ab[1].code), ctx))
    settle(g)
    assert g.players[1].points == p1 + 1


def test_zed_swaps_with_a_shadow_clone(db, decks):
    g = main_phase(db, decks)
    z = put(g, db, 0, "Zed, Without a Sound", ("bf", 0))
    c = g.play_token(0, "Shadow Clone", ("base", 0))
    g.restruct()
    ab = next(a for a in g.abilities(z) if a.label == "swap with a Shadow Clone")
    from riftsim.core.vm import Context, Frame
    ctx = Context(0, z); ctx.vars["self"] = z; ctx.vars["t"] = c
    g.vm_frames.append(Frame(list(ab.code), ctx))
    settle(g)
    assert g.objects[z].location == ("base", 0) and g.objects[c].location == ("bf", 0)


def test_lee_sin_ascetic_stacks_buffs_and_spends_one(db, decks):
    g = main_phase(db, decks)
    lee = put(g, db, 0, "Lee Sin, Ascetic", ("base", 0))
    other = put(g, db, 0, "Sett, Kingpin", ("base", 0), exclude=(lee,))
    for _ in range(3):
        g.do_buff(lee); g.do_buff(other)
    assert g.objects[lee].buffs == 3 and g.objects[other].buffs == 1
    g.do_spend_buff(lee)
    assert g.objects[lee].buffs == 2


def test_master_yi_unstoppable_costs_less_by_level(db, decks):
    g = main_phase(db, decks)
    yi = _card_in(g, db, 0, "Master Yi, Unstoppable", "hand")
    base_e, base_p = g.card_cost(0, yi, "hand")
    g.players[0].xp = 6
    e, p = g.card_cost(0, yi, "hand")
    assert e == base_e - 4 and len(p) == len(base_p) - 2
    g.players[0].xp = 11
    e, p = g.card_cost(0, yi, "hand")
    assert e == base_e - 6 and len(p) == len(base_p) - 3


def test_renata_mastermind_abilities_only_at_a_battlefield(db, decks):
    g = main_phase(db, decks)
    r = put(g, db, 0, "Renata Glasc, Mastermind", ("base", 0))
    ab = g.abilities(r)[0]
    assert not g._can_activate(0, r, 0, ab)
    g.do_move([r], ("bf", 0)); settle(g)
    assert g.objects[r].location == ("bf", 0)
    assert ab.restriction(g, r)


def test_akali_silent_can_be_chosen_only_in_combat(db, decks):
    g = main_phase(db, decks)
    ak = put(g, db, 0, "Akali, Silent", ("bf", 0))
    assert g.chars(ak).keywords.get("untargetable")
    g.combat = {"bf": 0, "attacker": 1, "defender": 0, "step": "showdown"}
    g.restruct()
    assert not g.chars(ak).keywords.get("untargetable")


def test_ezreal_prodigy_reduces_optional_costs(db, decks):
    g = main_phase(db, decks)
    assert g.reduce_optional_cost(0, 1, ["fury"]) == (1, ["fury"])
    put(g, db, 0, "Ezreal, Prodigy", ("base", 0))
    assert g.reduce_optional_cost(0, 1, ["fury"]) == (1, [])
    assert g.reduce_optional_cost(0, 2, []) == (1, [])


def test_akali_brash_second_move_lets_you_play_the_banished_card(db, decks):
    g = main_phase(db, decks)
    ak = put(g, db, 0, "Akali, Brash", ("base", 0))
    cheap = next(c for c in db if c.is_unit and not c.is_champion and (c.energy or 0) <= 1 and not c.domains)
    top = g.players[0].deck[0]
    g.objects[top].defn = cheap
    g.do_move([ak], ("bf", 0)); settle(g)
    g.do_move([ak], ("base", 0)); settle(g)
    assert g.objects[top].zone == "banish"
    d = g.run()
    assert any(o[0] == "play" and o[1] == top for o in d.options)


def test_jhin_meticulous_costs_mind_after_a_4_energy_spell(db, decks):
    g = main_phase(db, decks)
    j = _card_in(g, db, 0, "Jhin, Meticulous Killer", "hand")
    assert g.card_cost(0, j, "hand") != (0, ["mind"])
    g.turn_memo[("spell_spent_4", 0)] = True
    assert g.card_cost(0, j, "hand") == (0, ["mind"])


def test_leblanc_everywhere_stops_temporary_at_her_battlefield(db, decks):
    g = main_phase(db, decks)
    s1 = g.play_token(0, "Sprite", ("bf", 0), ready=True)
    s2 = g.play_token(0, "Sprite", ("bf", 1), ready=True)
    put(g, db, 0, "LeBlanc, Everywhere at Once", ("bf", 0))
    from riftsim.core.scripts import temporary_blocked
    assert temporary_blocked(g, s1) and not temporary_blocked(g, s2)


def test_kayle_empowers_three_times(db, decks):
    g = main_phase(db, decks)
    k = put(g, db, 0, "Kayle, Justified", ("base", 0))
    m = g.chars(k).might
    emp = next(i for i, a in enumerate(g.abilities(k)) if getattr(a, "is_empower", False))
    for n in (1, 2, 3):
        assert g._can_activate(0, k, emp, g.abilities(k)[emp]) or g.players[0].runes == []
        g.do_empower(k)
        assert g.objects[k].empowered == n
    g.do_empower(k)
    assert g.objects[k].empowered == 3
    c = g.chars(k)
    assert c.might == m + 6 and c.kw("deflect") >= 3 and c.keywords.get("ganking")


def test_ziggs_gear_abilities_deal_bonus_damage(db, decks):
    g = main_phase(db, decks)
    put(g, db, 0, "Ziggs, Short-Fused", ("base", 0))
    gear = put(g, db, 0, next(c.name for c in db if c.type == "gear" and not c.is_token), ("base", 0))
    foe = put(g, db, 1, "Sett, Kingpin", ("bf", 0))
    from riftsim.core.vm import Context
    g.do_deal([foe], 1, Context(0, gear))
    assert g.objects[foe].damage == 2


def test_sivir_mercenary_after_spending_two_power(db, decks):
    g = main_phase(db, decks)
    s = put(g, db, 0, "Sivir, Mercenary", ("base", 0))
    m = g.chars(s).might
    g.turn_memo[("spent", 0)] = [3, 1]; g.restruct()
    assert g.chars(s).might == m
    g.turn_memo[("spent", 0)] = [3, 2]; g.restruct()
    assert g.chars(s).might == m + 2 and g.chars(s).keywords.get("ganking")


def test_irelia_graceful_spell_choosing_her_costs_less(db, decks):
    g = main_phase(db, decks)
    ir = put(g, db, 0, "Irelia, Graceful", ("base", 0))
    have = {g.objects[r].defn.domains[0] for r in g.players[0].runes if g.objects[r].defn.domains}
    buff = next(c for c in db if c.type == "spell" and "Give a unit +" in (c.text or "") and "Choose" not in c.text
                and set(c.domains) <= have and (c.energy or 0) >= 1)
    sp = _card_in(g, db, 0, buff.name, "hand")
    e, pw = g.card_cost(0, sp, "hand")
    it = g._play(0, sp, None)
    g.pending = None
    for _ in range(30):
        d = g.run()
        if d.kind == "choose" and ir in d.options:
            g.choose(ir); continue
        if it.cost.get("paid") is not None or d.kind == "action":
            break
        g.choose(d.options[0])
    paid = it.cost.get("paid")
    assert paid is not None
    assert (paid[0], len(paid[1])) == ((e, len(pw) - 1) if pw else (e - 1, 0))


def test_seraphine_draws_when_three_units_exhaust_together(db, decks):
    g = main_phase(db, decks)
    put(g, db, 0, "Seraphine, Inspiring", ("base", 0))
    us = []
    for _ in range(3):
        us.append(put(g, db, 0, "Sett, Kingpin", ("base", 0), exclude=tuple(us)))
    hand = len(g.players[0].hand)
    g.do_exhaust(us[0]); g.do_exhaust(us[1]); settle(g)
    assert len(g.players[0].hand) == hand
    for u in us:
        g.objects[u].exhausted = False
    b = g.tick()
    for u in us:
        g.do_exhaust(u, batch=b)
    settle(g)
    assert len(g.players[0].hand) == hand + 1


def test_orianna_first_gear_each_turn_costs_1_any_less(db, decks):
    g = main_phase(db, decks)
    ori = put(g, db, 0, "Orianna, Mechanical Marvel", ("base", 0))
    gear = next(c for c in db if c.type == "gear" and not c.is_token and (c.energy or 0) >= 2)
    a = _card_in(g, db, 0, gear.name, "hand")
    e0, p0 = g.card_cost(0, a, "hand", ("base", 0))
    g.do_move([ori], ("bf", 0)); settle(g)
    e1, p1 = g.card_cost(0, a, "hand", ("base", 0))
    assert e1 == e0 - 1 and len(p1) == max(0, len(p0) - 1)
    g._use_play_effects(0, a)
    assert g.card_cost(0, a, "hand", ("base", 0)) == (e0, p0)


def test_ivern_friend_gains_the_chosen_tag_as_played(db, decks):
    g = main_phase(db, decks)
    iv = _card_in(g, db, 0, "Ivern, Friend to All", "hand")
    it = g._play(0, iv, ("base", 0))
    it.cost = {"energy": 0, "power": []}
    g.pending = None
    for _ in range(30):
        d = g.run()
        if d.kind == "mode":
            g.choose(next(o for o, l in zip(d.options, d.labels) if l == "Cat")); continue
        if d.kind == "action" and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert g.objects[iv].zone == "board" and "Cat" in g.chars(iv).tags


def test_aphelios_modes_once_each_per_turn(db, decks):
    g = main_phase(db, decks)
    ap = put(g, db, 0, "Aphelios, Exalted", ("base", 0))
    eq = next(c for c in db if c.type == "gear" and c.is_equipment and not c.is_token)
    labels = []
    for i in range(2):
        e = put(g, db, 0, eq.name, ("base", 0), exclude=(ap,))
        g.emit("attach", uid=e, to=ap, player=0)
        g.dirty = True; g.pending = None
        for _ in range(30):
            d = g.run()
            if d.kind == "mode":
                labels.append(tuple(d.labels)); g.choose(d.options[0]); continue
            if d.kind == "action" and not g.chain:
                break
            g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert len(labels) == 2 and len(labels[1]) == len(labels[0]) - 1


def test_teemo_strategist_deals_1_per_hidden_card_revealed(db, decks):
    g = main_phase(db, decks)
    t = put(g, db, 0, "Teemo, Strategist", ("bf", 0))
    foe = put(g, db, 1, "Sett, Kingpin", ("bf", 0))
    hidden = next(c for c in db if c.keywords.get("hidden") and c.type == "spell")
    plain = next(c for c in db if c.type == "spell" and not c.keywords.get("hidden"))
    deck = g.players[0].deck
    for i, d in enumerate([hidden, plain, hidden, plain, plain]):
        g.objects[deck[i]].defn = d
    top5 = deck[:5]
    _fire(g, t, "Teemo, Strategist")
    settle(g)
    assert g.objects[foe].damage == 2 or g.objects[foe].zone == "trash"
    assert all(u in g.players[0].deck[-5:] for u in top5)


def test_reksai_swarm_queen_plays_a_revealed_unit_here(db, decks):
    g = main_phase(db, decks)
    rq = put(g, db, 0, "Rek'Sai, Swarm Queen", ("bf", 0))
    have = {g.objects[r].defn.domains[0] for r in g.players[0].runes if g.objects[r].defn.domains}
    unit = next(c for c in db if c.is_unit and not c.is_champion and (c.energy or 0) <= 2 and set(c.domains) <= have and not c.text)
    top = g.players[0].deck[0]
    g.objects[top].defn = unit
    _fire(g, rq, "Rek'Sai, Swarm Queen", here=("bf", 0))
    settle(g, yes=True, picks=[(top,), ("bf", 0)])
    assert g.objects[top].zone == "board" and g.objects[top].location == ("bf", 0)


def test_karthus_makes_deathknell_trigger_twice(db, decks):
    g = main_phase(db, decks)
    put(g, db, 0, "Karthus, Eternal", ("base", 0))
    lb = put(g, db, 0, "LeBlanc, Fragmented", ("base", 0))
    hand = len(g.players[0].hand)
    g.do_kill([lb])
    settle(g)
    assert len(g.players[0].hand) == hand + 2


def _spell_ctx(g, p, picked):
    from riftsim.core.vm import Context
    ctx = Context(p, None)
    ctx.vars["__picked"] = tuple(picked)
    return ctx


def test_gangplank_naval_empowered_turns_chosen_stun_minus_might_and_bounce_into_plus_3(db, decks):
    g = main_phase(db, decks)
    gp = put(g, db, 1, "Gangplank, Naval", ("bf", 0))
    base = g.chars(gp).might
    ctx = _spell_ctx(g, 0, [gp])
    g.do_stun(gp, ctx)                       # not Empowered: stunned as usual
    assert g.objects[gp].stunned
    g.objects[gp].stunned = False
    g.objects[gp].empowered = 1
    g.restruct()
    g.do_stun(gp, ctx)
    assert not g.objects[gp].stunned and g.chars(gp).might == base + 3
    g.give_might(gp, -2, "turn", ctx)
    assert g.chars(gp).might == base + 6
    g.put_in_hand(gp, ctx)
    assert g.objects[gp].zone == "board" and g.chars(gp).might == base + 9
    # an effect that doesn't choose him (e.g. "all units") is not replaced
    g.give_might(gp, -2, "turn", _spell_ctx(g, 0, []))
    assert g.chars(gp).might == base + 7


def test_mel_empowered_extra_minus_might_and_uncounterable(db, decks):
    g = main_phase(db, decks)
    mel = put(g, db, 0, "Mel, Newly Awakened", ("base", 0))
    foe = put(g, db, 1, "Gangplank, Naval", ("bf", 0))
    base = g.chars(foe).might
    g.give_might(foe, -1, "turn", _spell_ctx(g, 0, [foe]))
    assert g.chars(foe).might == base - 1
    g.objects[mel].empowered = 1
    g.restruct()
    g.give_might(foe, -1, "turn", _spell_ctx(g, 0, [foe]))
    assert g.chars(foe).might == base - 3
    g.give_might(foe, -1, "turn", _spell_ctx(g, 1, [foe]))     # the opponent's effects get no bonus
    assert g.chars(foe).might == base - 4
    from riftsim.core.objects import ChainItem
    it = ChainItem(999, "spell", 0, label="test spell")
    g.chain.append(it)
    assert g.do_counter(999) is False and it in g.chain
    g.chain.remove(it)


def test_ahri_confident_grows_when_you_reduce_an_enemy_here(db, decks):
    g = main_phase(db, decks)
    bf = ("bf", 0)
    ahri = put(g, db, 0, "Ahri, Confident", bf)
    foe = put(g, db, 1, "Gangplank, Naval", bf)
    far = put(g, db, 1, "Mel, Newly Awakened", ("bf", 1), exclude=(foe,))
    base = g.chars(ahri).might
    g.give_might(far, -1, "turn", _spell_ctx(g, 0, [far]))     # not here
    settle(g)
    assert g.chars(ahri).might == base
    g.give_might(foe, -1, "turn", _spell_ctx(g, 0, [foe]))
    settle(g)
    assert g.chars(ahri).might == base + 1
    g.give_might(foe, -1, "turn", _spell_ctx(g, 1, [foe]))     # the opponent reduced it
    settle(g)
    assert g.chars(ahri).might == base + 1


def test_ahri_counts_a_static_minus_might_that_starts_applying(db, decks):
    # ruling: a stunned enemy at the battlefield of your Leona, Zealot receives -[M] from her passive
    g = main_phase(db, decks)
    bf = ("bf", 0)
    ahri = put(g, db, 0, "Ahri, Confident", bf)
    leona = put(g, db, 0, "Leona, Zealot", bf, exclude=(ahri,))
    foe = put(g, db, 1, "Gangplank, Naval", bf)
    settle(g)
    base = g.chars(ahri).might
    g.do_stun(foe, None)
    settle(g)
    assert g.chars(ahri).might == base + 1


def test_rell_magnetic_plays_a_cheap_equipment_free_and_attaches_it(db, decks):
    g = main_phase(db, decks)
    rell = put(g, db, 0, "Rell, Magnetic", ("base", 0))
    eq = _card_in(g, db, 0, "Doran's Blade", "hand")
    big = _card_in(g, db, 0, "Rell, Magnetic", "hand")       # not an Equipment: not offered
    runes_ready = sum(1 for u in g.players[0].runes if not g.objects[u].exhausted)
    g.emit("attack", uid=rell, player=0, loc=("bf", 0))
    seen = []
    for _ in range(40):
        d = g.run()
        if d.kind in ("pick", "pick_many") or (d.kind == "choose" and eq in d.options):
            seen.append(list(d.options))
            g.choose(next(o for o in d.options if o == eq or o == (eq,))); continue
        if d.kind == "yesno":
            g.choose(True); continue
        if d.kind == "action" and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert g.objects[eq].zone == "board" and g.objects[eq].attached_to == rell
    assert sum(1 for u in g.players[0].runes if not g.objects[u].exhausted) == runes_ready
    assert all(big not in o and (big,) not in o for o in seen)


def test_ashe_focused_banishes_a_card_until_they_hold(db, decks):
    g = main_phase(db, decks)
    ashe = put(g, db, 0, "Ashe, Focused", ("base", 0))
    hand1 = list(g.players[1].hand)
    target = hand1[0]
    g.emit("play", uid=ashe, player=0, card_type="unit")
    for _ in range(40):
        d = g.run()
        if d.kind == "choose" and target in d.options:
            g.choose(target); continue
        if d.kind == "action" and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert g.objects[target].zone == "banish"
    g._to_zone(g.objects[ashe], "trash"); g.restruct()            # even if Ashe left the board
    g.emit("hold", player=0, loc=("bf", 0), bf=0, units=())    # my hold: nothing
    settle(g)
    assert g.objects[target].zone == "banish"
    g.emit("hold", player=1, loc=("bf", 1), bf=1, units=())
    settle(g)
    assert g.objects[target].zone == "hand"


def test_soraka_saves_smaller_friendly_units_here_and_takes_damage_last(db, decks):
    g = main_phase(db, decks)
    bf = ("bf", 0)
    sor = put(g, db, 0, "Soraka, Wanderer", bf)
    small = put(g, db, 0, "Ahri, Confident", bf, exclude=(sor,))
    g.add_mod(small, "might", -2, "turn"); g.objects[small].damage = 1
    big = put(g, db, 0, "Sivir, Ambitious", bf, exclude=(sor, small))
    g.do_kill([small])
    assert g.objects[small].zone == "board" and g.objects[small].location == ("base", 0)
    assert g.objects[small].exhausted and g.objects[small].damage == 0
    g.do_kill([big])                                   # 7 [M] is not less than Soraka's 4
    assert g.objects[big].zone == "trash"
    other = put(g, db, 0, "Gangplank, Naval", bf, exclude=(sor, small, big))
    plans = g._damage_plans([sor, other], 3)
    assert all(p[0] == 0 for p in plans)               # Gangplank (6 [M]) must take lethal before Soraka gets any


def test_sivir_ambitious_deals_the_excess_after_conquering(db, decks):
    g = main_phase(db, decks)
    bf = ("bf", 0)
    sv = put(g, db, 0, "Sivir, Ambitious", bf)
    foe = put(g, db, 1, "Gangplank, Naval", ("bf", 1))
    hp = g.chars(foe).might
    g.combat = {"attacker": 0, "defender": 1, "bf": 0}
    g.turn_memo[("combat_excess", 0)] = 4
    g.emit("conquer", player=0, loc=bf, bf=0, units=(sv,))
    g.combat = None
    settle(g)
    assert g.objects[foe].damage == 0                  # 4 excess: no trigger
    g.combat = {"attacker": 0, "defender": 1, "bf": 0}
    g.turn_memo[("combat_excess", 0)] = 5
    g.emit("conquer", player=0, loc=bf, bf=0, units=(sv,))
    g.combat = None
    settle(g)
    bonus = sum(v for _, v in g.rules("bonus_damage", player=0)) + \
        sum(v for src, v in g.rules("bonus_damage_here") if g.objects[src].place == ("bf", 1))   # battlefield bonus
    assert [e["amount"] for e in g.events if e["kind"] == "damage" and e.get("uid") == foe] == [5 + bonus]


def test_azir_ascendant_swaps_with_a_unit_and_takes_its_equipment(db, decks):
    g = main_phase(db, decks)
    az = put(g, db, 0, "Azir, Ascendant", ("base", 0))
    friend = put(g, db, 0, "Rell, Magnetic", ("bf", 0), exclude=(az,))
    eq = put(g, db, 0, "Doran's Blade", ("bf", 0), exclude=(az, friend))
    g.do_attach(eq, friend)
    d = g.run()
    act = next(o for o in d.options if o[0] == "activate" and o[1] == az)
    g.choose(act)
    for _ in range(40):
        d = g.run()
        if d.kind in ("pick", "pick_many") and any(eq == o or (eq,) == o for o in d.options):
            g.choose(next(o for o in d.options if o == eq or o == (eq,))); continue
        if d.kind == "choose" and friend in d.options:
            g.choose(friend); continue
        if d.kind == "action" and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert g.objects[az].location == ("bf", 0) and g.objects[friend].location == ("base", 0)
    assert g.objects[eq].attached_to == az
    assert not any(o[0] == "activate" and o[1] == az for o in g.run().options)    # once per turn


def test_rumble_recycles_a_unit_to_replay_a_mech_cheaper(db, decks):
    g = main_phase(db, decks)
    bf = ("bf", 0)
    rum = put(g, db, 0, "Rumble, Hotheaded", bf)
    friend = put(g, db, 0, "Ahri, Confident", bf, exclude=(rum,))
    mech = _card_in(g, db, 0, "Adaptatron", "trash")
    g.add_mod(friend, "might", -2, "turn")
    fm = g.chars(friend).might
    assert 0 < g.objects[mech].defn.energy - fm
    n = len(g.events)
    g.emit("conquer", player=0, loc=bf, bf=0, units=(rum,))
    for _ in range(40):
        d = g.run()
        if d.kind == "choose" and friend in d.options:
            g.choose(friend); continue
        if d.kind in ("pick", "pick_many") and any(mech == o or (mech,) == o for o in d.options):
            g.choose(next(o for o in d.options if o == mech or o == (mech,))); continue
        if d.kind == "yesno":
            g.choose(True); continue
        if d.kind == "action" and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert g.objects[friend].zone == "deck"
    assert g.objects[mech].zone == "board"
    pays = [e for e in g.events[n:] if e["kind"] == "pay" and e.get("energy")]
    assert pays and pays[-1]["energy"] == max(0, g.objects[mech].defn.energy - fm)


def test_akshan_steals_an_enemy_gear_until_he_leaves(db, decks):
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    ak = put(g, db, 0, "Akshan, Mischievous", ("base", 0))
    blade = put(g, db, 1, "Doran's Blade", ("base", 1))
    ctx = Context(0, ak)
    g.emit("play", uid=ak, player=0, card_type="unit", paid={}, ctx=ctx)       # additional cost not paid
    settle(g)
    assert g.objects[blade].controller == 1
    g.emit("play", uid=ak, player=0, card_type="unit", paid={"add": True}, ctx=ctx)
    settle(g, picks=[blade])
    assert g.objects[blade].controller == 0 and g.objects[blade].attached_to == ak
    g.do_kill([ak])
    settle(g)
    assert g.objects[blade].controller == 1 and g.objects[blade].location == ("base", 1)


def test_temporary_control_returns_at_end_of_turn(db, decks):
    g = main_phase(db, decks)
    foe = put(g, db, 1, "Rell, Magnetic", ("base", 1))
    from riftsim.core.vm import Context
    g.take_control(foe, 0, Context(0, None), duration="turn")
    assert g.objects[foe].controller == 0
    g._expiration()
    assert g.objects[foe].controller == 1 and g.objects[foe].location == ("base", 1)


def test_nami_headstrong_paid_additional_cost_triggers_the_stun(db, decks):
    # end to end: the play event carries the paid additional costs to "if you paid the additional cost" triggers
    from test_targeting import give
    g = main_phase(db, decks)
    foe = put(g, db, 1, "Rell, Magnetic", ("bf", 0))
    nami = give(g, 0, "Nami, Headstrong", db)
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == nami and (len(o) < 3 or o[2] == ("base", 0))))
    for _ in range(60):
        d = g.run()
        if d.kind == "additional_cost":
            g.choose(True); continue
        if d.kind == "choose" and foe in d.options:
            g.choose(foe); continue
        if d.kind == "action" and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert g.objects[nami].zone == "board"
    assert g.objects[foe].stunned


def test_heimerdinger_inventor_has_friendly_tap_abilities(db, decks):
    g = main_phase(db, decks)
    hm = put(g, db, 0, "Heimerdinger, Inventor", ("base", 0))
    ball = put(g, db, 0, "Iron Ballista", ("base", 0), exclude=(hm,))
    g.objects[ball].exhausted = True
    foe = put(g, db, 1, "Rell, Magnetic", ("bf", 0))
    labels = [a.source_text for a in g.abilities(hm)]
    assert any("Deal 2" in t for t in labels)
    d = g.run()
    act = next(o for o in d.options if o[0] == "activate" and o[1] == hm)
    g.choose(act)
    for _ in range(40):
        d = g.run()
        if d.kind == "choose" and foe in d.options:
            g.choose(foe); continue
        if d.kind == "action" and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert g.objects[hm].exhausted and g.objects[ball].exhausted
    assert any(e["kind"] == "damage" and e.get("uid") == foe and e.get("source") == hm for e in g.events)


def test_nocturne_can_be_banished_and_played_for_any_power_when_looked_at(db, decks):
    from riftsim.core.vm import Context, Frame, compile_effect
    from riftsim.core import ops as O
    g = main_phase(db, decks)
    deck = g.players[0].deck
    noc = deck[1]
    g.objects[noc].defn = next(c for c in db if c.name == "Nocturne, Horrifying")
    g.restruct()
    other = deck[0]
    ctx = Context(0, None)
    g.vm_frames.append(Frame(compile_effect([O.Look(3, out="looked")]), ctx))
    asked = []
    for _ in range(40):
        d = g.run()
        if d.kind == "seen_from_deck":
            asked.append(d.info["uid"]); g.choose("banish_play"); continue
        if d.kind == "action" and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert asked == [noc]
    assert g.objects[noc].zone == "board"
    assert noc not in ctx.vars["looked"] and other in ctx.vars["looked"]
    pays = [e for e in g.events if e["kind"] == "pay" and e.get("power")]
    assert pays and pays[-1]["energy"] == 0 and len(pays[-1]["power"]) == 1


def test_neeko_adds_a_chosen_legend_while_on_board(db, decks):
    from riftsim.core.deck import Deck
    legs = [c.name for c in db if c.type == "legend" and c.script_status in ("auto", "manual", "vanilla")]
    d0 = Deck.from_dict(decks[0].to_dict())
    d0.main[0] = "Neeko, Blending In"
    d0.extra_legends = [n for n in legs if n != db.card(d0.legend).name][:3]
    errs = d0.validate(db)
    assert not [e for e in (errs or []) if "extra legend" in e or "different names" in e]
    bad = Deck.from_dict(d0.to_dict()); bad.extra_legends = [d0.extra_legends[0]] * 2
    assert any("different names" in e for e in (bad.validate(db) or []))
    g = main_phase(db, [d0, decks[1]])
    g.extra_legends[0] = tuple(d0.extra_legends)
    nk = put(g, db, 0, "Neeko, Blending In", ("base", 0))
    pick = d0.extra_legends[1]
    g.emit("play", uid=nk, player=0, card_type="unit")
    settle(g, picks=[pick])
    added = [u for u, o in g.objects.items() if o.zone == "board" and o.defn.name == pick and o.location == ("legend", 0)]
    assert len(added) == 1 and not g.objects[added[0]].exhausted
    g.do_kill([nk])
    settle(g)
    assert g.objects[added[0]].zone == "gone"
