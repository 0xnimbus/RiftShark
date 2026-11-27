"""Cards scripted for the 2026-11-27 post-ban deck refresh: Forge of the Fluft (Azir), Kharox (Vex)."""
import pathlib

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.scripts import script_all
from test_champions import put
from test_targeting import main_phase

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


@pytest.fixture(scope="module")
def decks(db):
    return [Deck.load(str(ROOT / "data/decks/tournament/azir_emperor.json"), db),
            Deck.load(str(ROOT / "data/decks/tournament/vex_gloomist.json"), db)]


def _settle(g, pick=None, limit=60):
    for _ in range(limit):
        d = g.run()
        if d is None:
            return None
        if pick is not None:
            c = pick(d)
            if c is not None:
                g.choose(c)
                continue
        if d.kind == "action" and not g.chain and g.showdown is None and g.combat is None:
            return d
        g.choose(("pass",) if ("pass",) in d.options else d.options[0])
    raise AssertionError("did not settle")


def _forge_bf(g):
    return next(i for i, bf in enumerate(g.battlefields) if g.objects[bf.uid].defn.name == "Forge of the Fluft")


def test_scripted(db):
    for n in ("Forge of the Fluft", "Kharox"):
        assert db.card(n).script_status == "manual"


def test_forge_gives_legend_attach_only_while_controlled(db, decks):
    g = main_phase(db, decks)
    if not any(g.objects[bf.uid].defn.name == "Forge of the Fluft" for bf in g.battlefields):
        g.objects[g.battlefields[0].uid].defn = db.card("Forge of the Fluft")
        g.restruct()
    i = _forge_bf(g)
    legend = g.players[0].legend
    label = "[T]: Attach an Equipment you control to a unit you control."
    has = lambda: any(getattr(ab, "label", "") == label for ab in g.abilities(legend))
    g.set_bf_controller(i, None)
    assert not has()
    g.set_bf_controller(i, 0)
    assert has()
    unit = put(g, db, 0, "Vi, Peacekeeper", ("base", 0))
    sword = put(g, db, 0, "B.F. Sword", ("base", 0), exclude=(unit,))
    g.objects[legend].exhausted = False
    g.bump()
    d = g.run()
    act = next(o for o in d.options if o[0] == "activate" and o[1] == legend)
    g.choose(act)
    _settle(g, pick=lambda d: sword if sword in d.options else (unit if unit in d.options else None))
    assert g.objects[sword].attached_to == unit
    assert g.objects[legend].exhausted


def test_kharox_empower_burns_3_and_plays_their_unit(db, decks):
    g = main_phase(db, decks)
    kx = put(g, db, 0, "Kharox", ("base", 0))
    opp = g.players[1]
    victim = next(u for u in opp.deck if g.objects[u].base_defn().is_unit)
    g._to_zone(g.objects[victim], "trash")
    deck_before = len(opp.deck)
    g.bump()
    g.do_empower(kx)
    _settle(g, pick=lambda d: (victim if victim in d.options else
                               (True if d.kind in ("yesno", "may") and True in d.options else None)))
    assert len(opp.deck) <= deck_before - 3 + 0 or g.players[1].burned_out
    o = g.objects[victim]
    assert o.zone == "board" and o.controller == 0


def test_banned_cards_helper(db):
    riven = Deck.load(str(ROOT / "data/decks/tournament/riven_exile.json"), db)
    assert "Riven, Broken Blade" in riven.banned_cards(db)
    assert riven.banned_cards(db, on_date="2026-11-22") == []
    azir = Deck.load(str(ROOT / "data/decks/tournament/azir_emperor.json"), db)
    assert azir.banned_cards(db, on_date="2026-11-23") == []
