"""Legend scripts against printed text (legends swapped onto a running game's legend object)."""
import pathlib

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.scripts import script_all
from test_targeting import main_phase, give, unit_at

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


@pytest.fixture(scope="module")
def decks(db):
    return [Deck.load(str(ROOT / "data/decks/tournament/riven_exile.json"), db),
            Deck.load(str(ROOT / "data/decks/tournament/kaisa_void.json"), db)]


def legend(g, db, cid):
    u = g.players[0].legend
    g.objects[u].defn = next(c for c in db if c.id == cid)
    g.objects[u].exhausted = False
    g.bump()
    return u


def activate(g, uid, answers):
    d = g.run()
    acts = [o for o in d.options if o[0] == "activate" and o[1] == uid]
    assert acts, "ability not offered"
    g.choose(acts[0])
    answers = list(answers)
    while True:
        d = g.run()
        if d is None:
            return
        if d.kind == "action":
            if g.chain and ("pass",) in d.options:
                g.choose(("pass",)); continue
            return d
        pick = answers.pop(0) if answers and answers[0] in d.options else d.options[0]
        g.choose(pick)


def test_yasuo_moves_a_unit_from_base_to_a_battlefield_and_back(db, decks):
    g = main_phase(db, decks)
    lg = legend(g, db, "OGN-259")
    u = unit_at(g, 0, ("base", 0))
    activate(g, lg, [u, ("bf", 0)])
    assert g.objects[u].location == ("bf", 0)
    for _ in range(200):                                    # the move opened a showdown there: let it finish
        d = g.run()
        if g.showdown is None and g.combat is None and not g.chain and d.player == 0 and d.kind == "action":
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    if g.objects[u].location != ("bf", 0) or g.turn_player != 0:
        pytest.skip("the unit left the battlefield in the showdown")
    g.objects[lg].exhausted = False
    for r in g.players[0].runes:
        g.objects[r].exhausted = False
    g.pending = None
    g.bump()
    activate(g, lg, [u])
    assert g.objects[u].location == ("base", 0)


def test_lucian_equipment_each_give_assault(db, decks):
    g = main_phase(db, decks)
    legend(g, db, "SFD-183")
    u = unit_at(g, 0, ("base", 0))
    blade = give(g, 0, "Blade of the Exile", db)
    g._to_zone(g.objects[blade], "board", location=("base", 0), controller=0)
    g.do_attach(blade, u, None)
    g.bump()
    assert g.chars(u).kw("assault") >= 1


def test_jax_attaches_a_detached_equipment(db, decks):
    g = main_phase(db, decks)
    lg = legend(g, db, "SFD-193")
    u = unit_at(g, 0, ("base", 0))
    blade = give(g, 0, "Blade of the Exile", db)
    g._to_zone(g.objects[blade], "board", location=("base", 0), controller=0)
    g.bump()
    activate(g, lg, [blade, u])
    assert g.objects[blade].attached_to == u


def test_ezreal_needs_two_enemy_choices_this_turn(db, decks):
    g = main_phase(db, decks)
    lg = legend(g, db, "SFD-199")
    d = g.run()
    assert not any(o[0] == "activate" and o[1] == lg for o in d.options)
    g.turn_memo[("chose_enemy", 0)] = 2
    g.pending = None
    g.bump()
    d = g.run()
    assert any(o[0] == "activate" and o[1] == lg for o in d.options)


def test_enemy_choices_are_counted_from_spells(db, decks):
    g = main_phase(db, decks)
    foe = unit_at(g, 1, ("bf", 0))
    s = give(g, 0, "Stupefy", db)
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == s))
    while g.pending is None or g.pending.kind != "action":
        d = g.run()
        if d.kind == "action":
            break
        g.choose(foe if foe in d.options else d.options[0])
    assert g.turn_memo.get(("chose_enemy", 0)) == 1


def test_sivir_readies_once_when_several_enemy_units_die_together(db, decks):
    g = main_phase(db, decks)
    lg = legend(g, db, "OPP-203")
    g.objects[lg].exhausted = True
    a = unit_at(g, 1, ("bf", 0))
    b = unit_at(g, 1, ("bf", 0), exclude=(a,))
    g.do_kill([a, b], None)
    sivir_items = [it for it in g.chain if it.uid == lg]
    assert len(sivir_items) == 1                            # "one or more enemy units die": one trigger


def test_renata_gold_adds_an_extra_energy_near_victory(db, decks):
    from riftsim.core.ops import Add
    from riftsim.core.vm import Context
    g = main_phase(db, decks)
    legend(g, db, "SFD-201")
    gold = g.play_token(0, "Gold", ("base", 0))
    ps = g.players[0]
    e = ps.energy
    Add(energy=0, power=["any"]).run(g, Context(0, gold))
    assert ps.energy == e                                   # far from victory: no bonus
    ps.points = g.cfg["victory"] - 3
    g.bump()
    Add(energy=0, power=["any"]).run(g, Context(0, gold))
    assert ps.energy == e + 1


def test_bashful_bloom_costs_less_per_temporary_unit(db, decks):
    g = main_phase(db, decks)
    lg = legend(g, db, "UNL-189")
    ab = next(a for a in g.abilities(lg) if getattr(a, "cost", {}).get("energy") == 4)
    assert g.ability_energy(ab, lg) == 4
    g.play_token(0, "Sprite", ("base", 0), ready=True)
    g.bump()
    assert g.ability_energy(ab, lg) == 3


def test_teemo_lets_you_hide_for_1_energy_instead_of_any_power(db, decks):
    g = main_phase(db, decks)
    legend(g, db, "OGN-263")
    costs = g._hide_costs(0)
    assert (1, []) in costs and (0, ["any"]) in costs


def _hand_unit(g, db, p=0, min_cost=3):
    ps = g.players[p]
    u = next(u for u in ps.deck if g.objects[u].defn.is_unit and not g.objects[u].defn.is_champion
             and (g.objects[u].defn.energy or 0) >= min_cost and g.objects[u].zone == "deck")
    g._to_zone(g.objects[u], "hand")
    g.bump()
    return u


def test_boy_who_shattered_time_empower_costs_1_and_exhausts(db, decks):
    g = main_phase(db, decks)
    lg = legend(g, db, "RAD-139")
    emp = [a for a in g.abilities(lg) if getattr(a, "is_empower", False)]
    assert len(emp) == 1 and emp[0].cost["energy"] == 1 and emp[0].cost.get("exhaust")
    # the disempower ability needs the legend to be empowered first
    d = g.run()
    acts = [o for o in d.options if o[0] == "activate" and o[1] == lg]
    assert len(acts) == 1                       # only Empower is offered


def test_boy_who_shattered_time_next_unit_costs_less_and_dies_at_end_of_turn(db, decks):
    g = main_phase(db, decks)
    lg = legend(g, db, "RAD-139")
    g.objects[lg].empowered = 1
    g.bump()
    u = _hand_unit(g, db)
    u2 = _hand_unit(g, db)
    e0, p0 = g.card_cost(0, u, "hand", ("base", 0))
    d = g.run()
    acts = [o for o in d.options if o[0] == "activate" and o[1] == lg]
    dis = [o for o in acts if not g.abilities(lg)[o[2]].is_empower]
    assert dis, "disempower ability not offered"
    g.choose(dis[0])
    for _ in range(50):
        d = g.run()
        if d.kind == "action" and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert not g.objects[lg].empowered and g.objects[lg].exhausted
    e1, p1 = g.card_cost(0, u, "hand", ("base", 0))
    assert e1 == max(0, e0 - 2) and len(p1) == max(0, len(p0) - 1)
    it = g._play(0, u, ("base", 0))
    it.cost = {"energy": 0, "power": []}                # payment is tested elsewhere
    g.pending = None
    for _ in range(50):
        d = g.run()
        if d.kind == "action" and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert g.objects[u].zone == "board"
    assert g.card_cost(0, u2, "hand", ("base", 0)) == g.card_cost(0, u2, "hand", None)  # used up
    g.choose(("end_turn",))
    for _ in range(100):
        if g.objects[u].zone != "board":
            break
        d = g.run()
        if g.turn_player == 1 and not g.chain:
            break
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    assert g.objects[u].zone == "trash"


def test_empower_dash_costs_parse(db):
    by = {c.id: c for c in db}
    def emp(cid):
        return [a.cost for a in by[cid].abilities if getattr(a, "is_empower", False)]
    assert [(c["energy"], c["power"]) for c in emp("VEN-074")] == [(1, []), (0, ["body"])]   # [1] or [Body]
    assert emp("VEN-007")[0].get("discard") == 1                                              # Discard 1
    assert emp("VEN-110")[0].get("discard_type") == "spell"                                   # Discard a spell
    assert emp("VEN-124")[0].get("sacrifice") is not None                                     # Kill a friendly unit
    assert emp("VEN-054")[0].get("exhaust") and emp("VEN-054")[0]["energy"] == 0             # [T]
    assert emp("VEN-001")[0]["energy"] == 5                                                   # [5]. This ability...
    assert emp("VEN-163") == []                                                               # Risen Altar: not the keyword


def test_songstress_exhausts_herself_and_three_units_to_reduce_a_spell_by_2(db, decks):
    g = main_phase(db, decks)
    lg = legend(g, db, "RAD-151")
    units = [unit_at(g, 0, ("base", 0))]
    units.append(unit_at(g, 0, ("base", 0), exclude=units))
    units.append(unit_at(g, 0, ("base", 0), exclude=units))
    assert g._exhaust_reducers(0)
    sp = next(u for u in g.players[0].deck if g.objects[u].defn.type == "spell" and g.objects[u].defn.energy >= 2
              and not g.objects[u].defn.text.lower().startswith("choose"))
    g._to_zone(g.objects[sp], "hand"); g.bump()
    it = g._play(0, sp, None)
    g.pending = None
    asked = False
    for _ in range(30):
        d = g.run()
        if d.kind == "yesno" and "Songstress" in d.labels[0]:
            asked = True
            g.choose(True); continue
        if d.kind == "choose_many" and asked:
            g.choose(next(o for o in d.options if set(o) == set(units))); continue
        if d.kind == "action":
            break
        g.choose(d.options[0])
    assert asked
    assert g.objects[lg].exhausted and all(g.objects[u].exhausted for u in units)
    assert it.cost["paid"][0] == max(0, g.objects[sp].defn.energy - 2)


def _resolve_spell(g, sp, energy):
    """Play spell `sp` from P0's hand and let it resolve; treat it as if `energy` was spent on it."""
    g._energy_spent = lambda it: energy
    if g.objects[sp].zone != "hand":
        g._to_zone(g.objects[sp], "hand")
    it = g._play(0, sp, None)
    it.cost = {"energy": 0, "power": []}
    g.pending = None
    for _ in range(60):
        d = g.run()
        if d.kind == "yesno" and "Virtuoso" in d.labels[0]:
            g.choose(True); continue
        if d.kind == "action" and not g.chain:
            return it
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    raise AssertionError("chain did not settle")


def test_virtuoso_banishes_4_energy_spells_and_pays_off_at_four(db, decks):
    g = main_phase(db, decks)
    legend(g, db, "UNL-181")
    cheap = next(c for c in db if c.name == "Progress Day")                      # "Draw 4."
    spells = []
    for i in range(5):
        u = g.players[0].deck[-1 - i]
        g.objects[u].defn = cheap
        spells.append(u)
    _resolve_spell(g, spells[0], 3)
    assert g.objects[spells[0]].zone == "trash"            # spent only [3]: no trigger
    for u in spells[1:4]:
        _resolve_spell(g, u, 4)
        assert g.objects[u].zone == "banish"
    runes0, hand0, deck0 = len(g.players[0].runes), len(g.players[0].hand), len(g.players[0].rune_deck)
    _resolve_spell(g, spells[4], 5)
    assert all(g.objects[u].zone == "trash" for u in spells[1:])     # put each in its trash
    assert len(g.players[0].runes) == runes0 + min(4, deck0)                  # channel 4 runes
    assert len(g.players[0].hand) == hand0 + 4 + 1                     # the spell draws 4, Virtuoso draws 1
