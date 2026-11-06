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
