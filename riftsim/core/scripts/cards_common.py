"""Hand scripts for common cards the auto-scripter cannot parse (each against its printed text)."""
from __future__ import annotations

from . import script, SpellEffect
from ..abilities import Static, Triggered, PlayPermission
from ..selectors import Sel
from .. import ops as O
from ..vm import Ref
from .cards_staples import _unwrap


def _spend_buff_cost():
    """'spend a buff' as an optional additional cost: choose a friendly buffed unit and spend its buff."""
    buffed = Sel("unit", side="friendly", pred=lambda g, c, u: g.objects[u].buffs > 0)
    return [O.SetVar("__addok", False),
            O.Choose(buffed, out="__sb", targeted=False),
            O.If(Ref("__sb"), [O.Do(lambda g, c: g.do_spend_buff(c.vars["__sb"], c)), O.SetVar("__addok", True)])]


def _has_buffed_unit(g, p, uid):
    return any(o.zone == "board" and o.controller == p and o.buffs > 0 for o in g.objects.values())


def _free_by_spending_a_buff(defn):
    return PlayPermission("free_with_cost", value=(_has_buffed_unit, _spend_buff_cost()),
                          label="spend a buff to ignore this spell's cost", source_text=defn.text)


@script("Call to Glory")
def call_to_glory(defn):
    # [Reaction]  As you play this, you may spend a buff as an additional cost. If you do, ignore this spell's cost.
    # Give a unit +3 [M] this turn.
    return [_free_by_spending_a_buff(defn),
            SpellEffect([O.Choose(Sel("unit"), out="t"), O.GiveMight(Ref("t"), 3)], label=defn.name, source_text=defn.text)]


@script("Wallop")
def wallop(defn):
    # [Action]  As you play this, you may spend a buff as an additional cost. If you do, ignore this spell's cost.
    # Ready a unit.
    return [_free_by_spending_a_buff(defn),
            SpellEffect([O.Choose(Sel("unit"), out="t"), O.Ready(Ref("t"))], label=defn.name, source_text=defn.text)]


@script("Get Excited!")
def get_excited(defn):
    # [Action]  Discard 1. Deal its Energy cost as damage to a unit at a battlefield. (Ignore its Power cost.)
    def cost(g, c):
        d = c.vars.get("discarded") or ()
        return sum(g.objects[u].base_defn().energy or 0 for u in d)
    return [SpellEffect([O.Discard(1, out="discarded"),
                         O.Choose(Sel("unit", where="battlefield"), out="t"),
                         O.Deal(cost, Ref("t"))], label=defn.name, source_text=defn.text)]


@script("Sky Splitter")
def sky_splitter(defn):
    # [Action]  This spell's Energy cost is reduced by the highest Might among units you control.
    # Deal 5 to a unit at a battlefield.
    def reduce(g, u, e, p):
        me = g.objects[u].controller if g.objects[u].controller is not None else g.objects[u].owner
        best = max([g.chars(x).might or 0 for x, o in g.objects.items() if o.zone == "board" and o.controller == me
                    and "unit" in g.chars(x).types] or [0])
        return max(0, e - best), p
    return [PlayPermission("cost", cost_mod=reduce, label="costs less by your highest Might", source_text=defn.text),
            SpellEffect([O.Choose(Sel("unit", where="battlefield"), out="t"), O.Deal(5, Ref("t"))],
                        label=defn.name, source_text=defn.text)]


@script("Meditation")
def meditation(defn):
    # [Reaction]  As an additional cost to play this, you may exhaust a friendly unit. If you do, draw 2.
    # Otherwise, draw 1.
    ready = Sel("unit", side="friendly", pred=lambda g, c, u: not g.objects[u].exhausted)
    ins = [O.SetVar("__addok", False), O.Choose(ready, out="__mx", targeted=False),
           O.If(Ref("__mx"), [O.Exhaust(Ref("__mx")), O.SetVar("__addok", True)])]
    return [PlayPermission("additional_cost", value=(None, ins, False), label="exhaust a friendly unit", source_text=defn.text),
            SpellEffect([O.If(O.played_cost_additional("add"), [O.Draw(2)], [O.Draw(1)])], label=defn.name,
                        source_text=defn.text)]


@script("Wielder of Water")
def wielder_of_water(defn):
    # While I'm attacking or defending alone, I have +2 [M].
    def alone(g, s):
        o = g.objects[s]
        if o.designation not in ("attacker", "defender"):
            return False
        return [u for u in g.units_at(o.location, o.controller)] == [s]
    return [Static("self", "might", 2, cond=alone, label="+2 [M] attacking or defending alone", source_text=defn.text)]


@script("Mobilize")
def mobilize(defn):
    # Channel 1 rune exhausted. If you can't, draw 1.
    return [SpellEffect([O.Channel(1, exhausted=True, out="__ch"),
                         O.If(lambda g, c: not c.vars.get("__ch"), [O.Draw(1)])], label=defn.name, source_text=defn.text)]


@script("Catalyst of Aeons")
def catalyst_of_aeons(defn):
    # Channel 2 runes exhausted. If you couldn't channel 2 runes this way, draw 1.
    def short(g, c):
        v = c.vars.get("__ch")
        n = len(v) if isinstance(v, (list, tuple)) else (v or 0)
        return n < 2
    return [SpellEffect([O.Channel(2, exhausted=True, out="__ch"), O.If(short, [O.Draw(1)])],
                        label=defn.name, source_text=defn.text)]


@script("Fight or Flight")
def fight_or_flight(defn):
    # [Hidden] [Action]  Move a unit from a battlefield to its base.
    return [SpellEffect([O.Choose(Sel("unit", where="battlefield"), out="t"), O.Move(Ref("t"), "base")],
                        label=defn.name, source_text=defn.text)]


@script("Back to Back")
def back_to_back(defn):
    # [Reaction]  Give two friendly units each +2 [M] this turn.
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t", n=2), O.GiveMight(Ref("t"), 2)],
                        label=defn.name, source_text=defn.text)]


@script("Poro Herder")
def poro_herder(defn):
    # When you play me, if you control a Poro, buff me and draw 1.
    def poro(g, s, ev=None):
        me = g.objects[s].controller if g.objects[s].controller is not None else g.objects[s].owner
        return any(o.zone == "board" and o.controller == me and u != s and "Poro" in g.chars(u).tags
                   for u, o in g.objects.items())
    return [Triggered("play_self", [O.If(lambda g, c: poro(g, c.source), [O.Buff(Ref("self")), O.Draw(1)])],
                      filt=poro, label=defn.name, source_text=defn.text)]


@script("Portal Rescue")
def portal_rescue(defn):
    # [Action]  Banish a friendly unit, then play it to base, ignoring its cost.
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Banish(Ref("t")),
                         O.If(lambda g, c: c.vars.get("t") in g.objects and g.objects[c.vars["t"]].zone == "banish",
                              [O.PlayCard(Ref("t"), ignore="all", loc=lambda g, c: ("base", c.controller))])],
                        label=defn.name, source_text=defn.text)]


@script("Spoils of War")
def spoils_of_war(defn):
    # [Reaction]  If an enemy unit has died this turn, this costs [2] less.  Draw 2.
    def reduce(g, u, e, p):
        me = g.objects[u].controller if g.objects[u].controller is not None else g.objects[u].owner
        died = any(n for (k, q), n in ((k, v) for k, v in g.turn_memo.items() if isinstance(k, tuple) and len(k) == 2)
                   if k == "units_died" and not g.is_friendly(q, me))
        return (max(0, e - 2), p) if died else (e, p)
    return [PlayPermission("cost", cost_mod=reduce, label="[2] less if an enemy unit died this turn", source_text=defn.text),
            SpellEffect([O.Draw(2)], label=defn.name, source_text=defn.text)]


@script("Peak Guardian")
def peak_guardian(defn):
    # When you play me, buff me. Then, if I am at a battlefield, buff all other friendly units there.
    def others_there(g, c):
        me = g.objects.get(c.source)
        if me is None or me.zone != "board" or me.location is None or me.location[0] != "bf":
            return []
        return [u for u in g.units_at(me.location, me.controller) if u != c.source]
    return [Triggered("play_self", [O.Buff(Ref("self")), O.Buff(others_there)], label=defn.name, source_text=defn.text)]


@script("Solari Chief")
def solari_chief(defn):
    # When you play me, choose an enemy unit. If it is stunned, kill it. Otherwise, stun it.
    stunned = lambda g, c: c.vars.get("t") in g.objects and g.objects[c.vars["t"]].stunned
    return [Triggered("play_self", [O.Choose(Sel("unit", side="enemy"), out="t"),
                                    O.If(stunned, [O.Kill(Ref("t"))], [O.Stun(Ref("t"))])],
                      label=defn.name, source_text=defn.text)]


@script("Scrapheap")
def scrapheap(defn):
    # When this is played, discarded, or killed, draw 1.
    played = lambda g, s, ev: ev.get("kind") == "play" and ev.get("uid") == s
    discarded = lambda g, s, ev: ev.get("kind") == "discard" and ev.get("uid") == s
    killed = lambda g, s, ev: ev.get("kind") == "die" and ev.get("uid") == s
    return [Triggered(played, [O.Draw(1)], label="played: draw 1", source_text=defn.text),
            Triggered(discarded, [O.Draw(1)], zone="trash", label="discarded: draw 1", source_text=defn.text),
            Triggered(killed, [O.Draw(1)], label="killed: draw 1", source_text=defn.text)]


@script("Solari Shrine")
def solari_shrine(defn):
    # When you kill a stunned enemy unit, you may exhaust this to draw 1.
    def kill_stunned(g, s, ev):
        me = g.objects[s].controller
        return (ev.get("kind") == "die" and ev.get("killer") == me and ev.get("stunned")
                and ev.get("player") is not None and not g.is_friendly(ev["player"], me))
    ready = lambda g, c: c.source in g.objects and not g.objects[c.source].exhausted
    return [Triggered(kill_stunned, [O.If(ready, [O.May([O.Exhaust(Ref("self")), O.Draw(1)], label="exhaust this to draw 1")])],
                      label=defn.name, source_text=defn.text)]
