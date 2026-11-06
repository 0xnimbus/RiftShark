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
