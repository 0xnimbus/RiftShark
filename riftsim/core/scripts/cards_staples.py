"""Hand-written scripts for competitive cards the auto-scripter does not cover (Rek'Sai deck first, then legends and
other staples). Printed text, with errata applied, is quoted above each script."""
from __future__ import annotations

from . import script, SpellEffect
from ..abilities import Static, Triggered, Activated, PlayPermission
from ..selectors import Sel
from .. import ops as O
from ..vm import Ref


def _keep(abilities, effect_abilities=None):
    """Keep the keyword/auto abilities already attached and add these."""
    return {"abilities": abilities, "effect_abilities": effect_abilities or [], "replace": False}


def _ready_self(g, c):
    return c.source in g.objects and not g.objects[c.source].exhausted


# ----------------------------------------------------------------------------- Rek'Sai
@script("Void Burrower", "Rek'sai, Void Burrower", "Reksai, Void Burrower", "Rek'Sai, Void Burrower")
def void_burrower(defn):
    # Errata (Spiritforged errata): When you conquer, you may exhaust me to reveal the top 2 cards of your Main Deck.
    # You may banish one, then play it. Recycle the rest.
    def banish_pick(g, c):
        pick = c.vars.get("__pick") or ()
        u = pick[0] if pick else None
        c.vars["__bp"] = u
        if u is not None:
            g.do_banish([u], c)

    return {"abilities": [Triggered("you_conquer", [
        O.May([O.If(_ready_self, [
            O.Exhaust(Ref("self")),
            O.Look(2, out="looked", reveal=True),
            O.ChooseFromList(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"],
                             out="__pick", n=1, up_to=True, label="banish one, then play it"),
            O.Do(banish_pick, label="banish it"),
            O.If(lambda g, c: c.vars.get("__bp") is not None, [O.PlayCard(Ref("__bp"))]),
            O.Recycle(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"]),
        ])], label="exhaust me to reveal the top 2 cards of your Main Deck"),
    ], label=defn.name, source_text=defn.text)], "replace": True}


@script("Rek'Sai, Breacher")
def reksai_breacher(defn):
    # [Accelerate] [Assault] (keywords). Friendly units played from anywhere other than a player's hand have [Accelerate].
    return _keep([Static("self", "rule", ("accelerate_if_not_from_hand",), label=defn.name,
                         source_text="Friendly units played from anywhere other than a player's hand have [Accelerate].")])


@script("Undertitan")
def undertitan(defn):
    # When you play me, give your other units +2 [M] this turn.  (auto)
    # As I'm revealed from your deck, [Add] [2].   (happens immediately, no chain: CR 369.1 example)
    def add2(g, u, ctx):
        g.add_resources(g.objects[u].owner, 2, [], ctx=ctx)
        g.log("as_revealed", uid=u, add=2)
    return _keep([PlayPermission("as_revealed_from_deck", zone="deck", value=add2, label="As I'm revealed, [Add] [2]",
                                 source_text="As I'm revealed from your deck, [Add] [2].")])


@script("Drag Under")
def drag_under(defn):
    # [Action]. I cost [2] less to play from anywhere other than your hand. Kill a unit at a battlefield.
    def cheaper(g, uid, e, p):
        return (max(0, e - 2), p) if g.objects[uid].zone != "hand" else (e, p)
    return {"abilities": [
        PlayPermission("cost", zone="any", cost_mod=cheaper, label="costs [2] less from anywhere other than your hand"),
        SpellEffect([O.Choose(Sel("unit", pred=lambda g, c, u: g.objects[u].location is not None
                                  and g.objects[u].location[0] == "bf"), out="t", targeted=True),
                     O.Kill(Ref("t"))], label=defn.name, source_text=defn.text)], "replace": True}


@script("Lacerate")
def lacerate(defn):
    # Choose a unit. If it's [Empowered], disempower it. Then kill it if it has 3 [M] or less.
    return {"abilities": [SpellEffect([
        O.Choose(Sel("unit"), out="t", targeted=True),
        O.If(lambda g, c: c.vars.get("t") is not None and bool(g.objects[c.vars["t"]].empowered), [O.Disempower(Ref("t"))]),
        O.If(lambda g, c: c.vars.get("t") is not None and (g.chars(c.vars["t"]).might or 0) <= 3, [O.Kill(Ref("t"))]),
    ], label=defn.name, source_text=defn.text)], "replace": True}


@script("Hunters' Circle")
def hunters_circle(defn):
    # For each player, the first unit or gear they play here on their turn costs [1] less.
    def reduce(g, src, uid, e, pw, p, loc):
        here = g.objects[src].place
        d = g.objects[uid].base_defn()
        if loc != here or g.turn_player != p or not (d.is_unit or d.is_gear):
            return e, pw
        if (p, here) in g.turn_memo.get("played_at", []):
            return e, pw
        return max(0, e - 1), pw
    return {"abilities": [Static("self", "rule", ("cost_reduce_at", reduce), label=defn.name, source_text=defn.text)],
            "replace": True}


@script("The Candlelit Sanctum")
def candlelit_sanctum(defn):
    # When you conquer here, look at the top two cards of your Main Deck. You may recycle one or both of them.
    # Put those you don't back in any order.   (= [Predict 2])
    def conquer_here(g, src, ev):        # "you" = the player who conquers this battlefield (CR 190.6)
        return ev.get("kind") == "conquer" and ev.get("loc") == g.objects[src].place
    return {"abilities": [Triggered(conquer_here, [O.Predict(2)], controller="event", label=defn.name,
                                    source_text=defn.text)], "replace": True}
