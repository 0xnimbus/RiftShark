"""Rek'Sai, Void Burrower deck (18th Convergence IV): per-card tests against printed text (errata applied)."""
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
    return [Deck.load(str(ROOT / "data/decks/preban/reksai_void_burrower.json"), db),
            Deck.load(str(ROOT / "data/decks/preban/kaisa_void.json"), db)]


def _drain(g, answer=lambda d: d.options[0]):
    while True:
        d = g.run()
        if d is None:
            return None
        if d.kind == "action":
            if g.chain and ("pass",) in d.options:
                g.choose(("pass",))
                continue
            return d
        g.choose(answer(d))


def test_deck_is_legal_and_fully_scripted(db, decks):
    d = decks[0]
    assert d.validate(db, raise_on_error=True)  is not False
    bad = [db.card(c).name for c in d.main + [d.legend, d.champion] + list(d.battlefields)
           if db.card(c).script_status not in ("auto", "manual", "vanilla")]
    assert bad == []


def test_void_burrower_reveals_banishes_and_plays(db, decks):
    g = main_phase(db, decks)
    ps = g.players[0]
    legend = ps.legend
    top = ps.deck[:2]
    cheap = next(c for c in db if c.name == "Noxus Hopeful")
    g.objects[top[0]].defn = cheap
    g.restruct()
    hand = len(ps.hand)
    g.emit("conquer", player=0, units=(), loc=("bf", 0))
    picked = []

    def answer(d):
        if d.kind == "yesno":
            return True
        if d.kind == "pick_many":
            o = next(o for o in d.options if o == (top[0],))
            picked.append(o)
            return o
        return d.options[0]
    _drain(g, answer)
    assert picked and g.objects[legend].exhausted
    assert g.objects[top[0]].zone == "board"                       # banished, then played
    assert g.objects[top[1]].zone == "deck" and ps.deck[-1] == top[1]   # the rest recycled to the bottom
    assert len(ps.hand) == hand


def test_undertitan_adds_2_as_revealed_from_deck(db, decks):
    g = main_phase(db, decks)
    ps = g.players[0]
    g.objects[ps.deck[0]].defn = next(c for c in db if c.name == "Undertitan")
    g.restruct()
    e = ps.energy
    from riftsim.core.ops import Look
    from riftsim.core.vm import Context
    Look(2, reveal=True).run(g, Context(0, ps.legend))
    assert ps.energy == e + 2


def test_reksai_breacher_grants_accelerate_off_hand_plays(db, decks):
    g = main_phase(db, decks)
    rk = give(g, 0, "Rek'Sai, Breacher", db)
    g._to_zone(g.objects[rk], "board", location=("base", 0), controller=0)
    g.restruct()
    u = g.players[0].deck[0]
    g.objects[u].defn = next(c for c in db if c.name == "Noxus Hopeful")
    assert not g.objects[u].defn.keywords.get("accelerate")
    g._to_zone(g.objects[u], "banish")
    from riftsim.core.vm import Context
    assert g.limited_play(0, u, Context(0, g.players[0].legend))
    it = g.chain[-1]
    assert any(n == "accelerate" for n, _ in g._optional_costs(it, it.ctx))
    h = give(g, 0, "Noxus Hopeful", db)
    g.chain.clear(); g.pending = None; g.restruct()
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == h))
    it = next(x for x in g.chain if x.uid == h)
    assert not any(n == "accelerate" for n, _ in g._optional_costs(it, it.ctx))   # played from hand: no


def test_drag_under_costs_2_less_outside_hand(db, decks):
    g = main_phase(db, decks)
    s = give(g, 0, "Drag Under", db)
    assert g.card_cost(0, s, "hand")[0] == 5
    g._to_zone(g.objects[s], "banish")
    assert g.card_cost(0, s, "banish")[0] == 3


def test_lacerate_kills_3_might_or_less_and_spares_bigger(db, decks):
    g = main_phase(db, decks)
    small = unit_at(g, 1, ("bf", 0))
    g.objects[small].defn = next(c for c in db if c.is_unit and not c.is_token and (c.might or 0) == 2 and "[M]" not in c.text)
    g.restruct()
    assert g.chars(small).might <= 3
    s = give(g, 0, "Lacerate", db)
    d = g.run()
    g.choose(next(o for o in d.options if o[0] == "play" and o[1] == s))
    _drain(g, lambda d: small if small in d.options else d.options[0])
    assert g.objects[small].zone != "board"


def test_hunters_circle_first_unit_here_costs_1_less(db, decks):
    g = main_phase(db, decks)
    hc = next(c for c in db if c.name == "Hunters' Circle")
    bf = g.battlefields[0]
    g.objects[bf.uid].defn = hc
    bf.controller = 0
    g.restruct()
    u = give(g, 0, "Noxus Hopeful", db)
    base = g.card_cost(0, u, "hand", ("base", 0))[0]
    assert g.card_cost(0, u, "hand", ("bf", 0))[0] == max(0, base - 1)
    g.turn_memo.setdefault("played_at", []).append((0, ("bf", 0)))
    assert g.card_cost(0, u, "hand", ("bf", 0))[0] == base                    # only the first one


def test_candlelit_sanctum_predicts_2_on_conquer_here(db, decks):
    g = main_phase(db, decks)
    bf = g.battlefields[0]
    g.objects[bf.uid].defn = next(c for c in db if c.name == "The Candlelit Sanctum")
    g.restruct()
    g.emit("conquer", player=0, units=(), loc=("bf", 0))
    kinds = []

    def answer(d):
        kinds.append(d.kind)
        return d.options[0]
    _drain(g, answer)
    assert "predict" in kinds
