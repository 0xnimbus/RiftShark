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
    g.bump()
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
        g._to_zone(g.objects[ps.runes[-1]], "rune_deck"); g.bump()
    assert g.chars(u).might == base
    while len(ps.runes) < 8:
        g.channel(0, 1) if hasattr(g, "channel") else g._to_zone(g.objects[ps.rune_deck[0]], "board", controller=0)
        g.bump()
    assert g.chars(u).might == base + 4


def test_sett_kingpin_and_lee_sin_centered_count_buffed_units_at_their_battlefield(db, decks):
    g = main_phase(db, decks)
    sett = put(g, db, 0, "Sett, Kingpin", ("bf", 0))
    lee = put(g, db, 0, "Lee Sin, Centered", ("bf", 0), exclude=(sett,))
    other = put(g, db, 0, "Sett, Kingpin", ("base", 0), exclude=(sett, lee))
    s0, l0 = g.chars(sett).might, g.chars(lee).might
    g.objects[lee].buffs = 1; g.bump()
    assert g.chars(sett).might == s0 + 1            # one buffed unit there; Sett isn't buffed, so no +2 from Lee Sin
    assert g.chars(lee).might == l0 + 1             # the buff counter only; Lee Sin's static says "other"
    g.objects[other].buffs = 1; g.bump()            # at base: doesn't count
    assert g.chars(sett).might == s0 + 1
    g.objects[sett].buffs = 1; g.bump()             # own buff +1, two buffed units +2, Lee Sin +2
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
    g._to_zone(g.objects[u], "hand"); g.bump()
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
    g.bump()
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
