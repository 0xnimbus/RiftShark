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


def _ctrl(g, u):
    o = g.objects[u]
    return o.controller if o.controller is not None else o.owner


def _fight(g, c, a, b):
    """'We deal damage equal to our Mights to each other' (both amounts read before either is dealt)."""
    if a not in g.objects or b not in g.objects or g.objects[a].zone != "board" or g.objects[b].zone != "board":
        return
    ma, mb = g.chars(a).might or 0, g.chars(b).might or 0
    g.do_deal([b], ma, c, source_uid=a)
    g.do_deal([a], mb, c, source_uid=b)


@script("Carnivorous Snapvine")
def carnivorous_snapvine(defn):
    # When you play me, choose an enemy unit at a battlefield. We deal damage equal to our Mights to each other.
    return [Triggered("play_self", [O.Choose(Sel("unit", side="enemy", where="battlefield"), out="t"),
                                    O.Do(lambda g, c: _fight(g, c, c.source, c.vars.get("t")), label="fight")],
                      label=defn.name, source_text=defn.text)]


@script("Maddened Marauder")
def maddened_marauder(defn):
    # [Tank]  When you play me, move a unit from a battlefield to its base.
    return [Triggered("play_self", [O.Choose(Sel("unit", where="battlefield"), out="t"), O.Move(Ref("t"), "base")],
                      label=defn.name, source_text=defn.text)]


@script("Mindsplitter")
def mindsplitter(defn):
    # When you play me, choose an opponent. They reveal their hand. Choose a card from it, and they discard that card.
    def reveal(g, c):
        p = c.vars.get("__opp")
        if p is not None:
            g.emit("reveal", player=p, cards=list(g.players[p].hand), ctx=c)
    return [Triggered("play_self", [
        O.ChoosePlayer(out="__opp", opponent=True), O.Do(reveal, label="reveal hand"),
        O.Choose(lambda g, c: list(g.players[c.vars["__opp"]].hand) if c.vars.get("__opp") is not None else [],
                 out="__md", targeted=False),
        O.If(Ref("__md"), [O.DiscardChosen(Ref("__md"), player=lambda g, c: c.vars["__opp"])])],
        label=defn.name, source_text=defn.text)]


@script("Rhasa the Sunderer")
def rhasa(defn):
    # I cost [1] less for each card in your trash.
    return [PlayPermission("cost", cost_mod=lambda g, u, e, p: (max(0, e - len(g.players[_ctrl(g, u)].trash)), p),
                           label="[1] less per card in your trash", source_text=defn.text)]


def _play_unit_from_trash(label):
    units = lambda g, c: [u for u in g.players[c.controller].trash if g.objects[u].base_defn().is_unit]
    return [O.ChooseFromList(units, out="__ut", up_to=True, label=label), O.Do(_unwrap("__ut")),
            O.If(Ref("__ut"), [O.PlayCard(Ref("__ut"), ignore="energy")])]


@script("Soulgorger")
def soulgorger(defn):
    # When you play me, you may play a unit from your trash, ignoring its Energy cost.
    return [Triggered("play_self", _play_unit_from_trash("play a unit from your trash"), label=defn.name, source_text=defn.text)]


@script("The Harrowing")
def the_harrowing(defn):
    # Play a unit from your trash, ignoring its Energy cost.
    units = lambda g, c: [u for u in g.players[c.controller].trash if g.objects[u].base_defn().is_unit]
    return [SpellEffect([O.ChooseFromList(units, out="__ut", label="play a unit from your trash"),
                         O.If(Ref("__ut"), [O.PlayCard(Ref("__ut"), ignore="energy")])], label=defn.name, source_text=defn.text)]


@script("Invert Timelines")
def invert_timelines(defn):
    # Each player discards their hand, then draws 4.
    def run(g, c):
        for q in range(len(g.players)):
            g.do_discard(q, list(g.players[q].hand), c)
        for q in range(len(g.players)):
            g.do_draw(q, 4, c)
    return [SpellEffect([O.Do(run, label="discard hands, draw 4")], label=defn.name, source_text=defn.text)]


@script("Super Mega Death Rocket!, Jinx")
def super_mega_death_rocket(defn):
    # Deal 5 to a unit.  When you conquer, you may discard 1 to return this from your trash to your hand.
    has_hand = lambda g, c: bool(g.players[c.controller].hand)
    return [SpellEffect([O.Choose(Sel("unit"), out="t"), O.Deal(5, Ref("t"))], label=defn.name, source_text=defn.text),
            Triggered(lambda g, s, ev: ev.get("kind") == "conquer" and ev.get("player") == g.objects[s].owner, [O.If(has_hand, [O.May([O.Discard(1), O.ToHand(Ref("self"))],
                                                            label="discard 1 to return this to your hand")])],
                      zone="trash", label="return from trash", source_text=defn.text)]


@script("Siphon Power, Viktor")
def siphon_power(defn):
    # [Reaction]  Choose a battlefield. Give friendly units there +1 [M] this turn and enemy units there -1 [M] this
    # turn, to a minimum of 1 [M].
    friends = lambda g, c: [u for u in g.units_at(c.vars["loc"]) if g.is_friendly(g.objects[u].controller, c.controller)]
    foes = lambda g, c: [u for u in g.units_at(c.vars["loc"]) if not g.is_friendly(g.objects[u].controller, c.controller)]
    return [SpellEffect([O.ChooseLocation(out="loc"), O.GiveMight(friends, 1), O.GiveMight(foes, -1, min_value=1)],
                        label=defn.name, source_text=defn.text)]


@script("Flash")
def flash(defn):
    # [Reaction]  Move up to 2 friendly units to base.
    return [SpellEffect([O.Choose(Sel("unit", side="friendly", where="battlefield"), out="t", n=2, up_to=True),
                         O.Move(Ref("t"), "base")], label=defn.name, source_text=defn.text)]


@script("Against the Odds")
def against_the_odds(defn):
    # [Reaction]  Give a friendly unit at a battlefield +2 [M] this turn for each enemy unit there.
    def amount(g, c):
        t = c.vars.get("t")
        if t not in g.objects or g.objects[t].zone != "board":
            return 0
        return 2 * sum(1 for u in g.units_at(g.objects[t].location) if not g.is_friendly(g.objects[u].controller, c.controller))
    return [SpellEffect([O.Choose(Sel("unit", side="friendly", where="battlefield"), out="t"), O.GiveMight(Ref("t"), amount)],
                        label=defn.name, source_text=defn.text)]


@script("Blood Rush")
def blood_rush(defn):
    # [Action] [Repeat] [1]  Give a unit [Assault 2].
    return [SpellEffect([O.Choose(Sel("unit"), out="t"), O.GiveKeyword(Ref("t"), "assault", 2)],
                        label=defn.name, source_text=defn.text)]


@script("Void Drone")
def void_drone(defn):
    # I cost [2] less to play from anywhere other than your hand.
    return [PlayPermission("cost", cost_mod=lambda g, u, e, p: (max(0, e - 2), p) if g.objects[u].zone != "hand" else (e, p),
                           label="[2] less from anywhere but your hand", source_text=defn.text)]


@script("Battering Ram")
def battering_ram(defn):
    # I cost [1] less for each card you've played this turn, to a minimum of [1].
    def reduce(g, u, e, p):
        n = len(g.players[_ctrl(g, u)].played_this_turn)
        return (max(min(e, 1), e - n), p)
    return [PlayPermission("cost", cost_mod=reduce, label="[1] less per card played this turn", source_text=defn.text)]


@script("Buhru Captain")
def buhru_captain(defn):
    # When you play me, you may draw 1 or buff me.
    return [Triggered("play_self", [O.ChooseMode([("draw 1", [O.Draw(1)]), ("buff me", [O.Buff(Ref("self"))]),
                                                  ("neither", [])])], label=defn.name, source_text=defn.text)]


@script("Called Shot")
def called_shot(defn):
    # [Action] [Repeat] [Chaos]  Look at the top 2 cards of your Main Deck. Draw one and recycle the other.
    return [SpellEffect([O.Look(2, out="looked"),
                         O.ChooseFromList(lambda g, c: list(c.vars.get("looked", [])), out="__cs", label="draw one"),
                         O.ToHand(Ref("__cs")),
                         O.Recycle(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"])],
                        label=defn.name, source_text=defn.text)]


@script("Overzealous Fan")
def overzealous_fan(defn):
    # When I defend, you may kill me to move an attacking unit to its base.
    attackers = Sel("unit", pred=lambda g, c, u: g.objects[u].designation == "attacker")
    return [Triggered("defend_self", [O.May([O.Kill(Ref("self")), O.Choose(attackers, out="t"), O.Move(Ref("t"), "base")],
                                            label="kill me to move an attacking unit to its base")],
                      label=defn.name, source_text=defn.text)]


@script("Bonds of Strength")
def bonds_of_strength(defn):
    # [Reaction] [Repeat] [2]  Give two friendly units each +1 [M] this turn.
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t", n=2), O.GiveMight(Ref("t"), 1)],
                        label=defn.name, source_text=defn.text)]


@script("Trusty Ramhound")
def trusty_ramhound(defn):
    # While you have another unit here, I have +1 [M].
    def other_here(g, s):
        o = g.objects[s]
        return o.location is not None and any(u != s for u in g.units_at(o.location, o.controller))
    return [Static("self", "might", 1, cond=other_here, label="+1 [M] with another unit here", source_text=defn.text)]


@script("Convergent Mutation")
def convergent_mutation(defn):
    # [Reaction]  Choose a friendly unit. This turn, increase its Might to the Might of another friendly unit.
    other = Sel("unit", side="friendly", pred=lambda g, c, u: u != c.vars.get("t"))
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Choose(other, out="__o"),
                         O.SetMight(Ref("t"), lambda g, c: g.chars(c.vars["__o"]).might if c.vars.get("__o") in g.objects else 0)],
                        label=defn.name, source_text=defn.text)]


@script("Yordle Explorer")
def yordle_explorer(defn):
    # When you play a card with Power cost [A][A] or more, draw 1.
    def big(g, s, ev):
        return (ev.get("kind") == "play" and ev.get("player") == g.objects[s].controller and ev.get("uid") in g.objects
                and (g.objects[ev["uid"]].base_defn().power or 0) >= 2 and not ev.get("token"))
    return [Triggered(big, [O.Draw(1)], label=defn.name, source_text=defn.text)]


def _xp(g, p):
    return g.players[p].xp


def _enter_ready_if(defn, pred, label):
    from ..abilities import Replacement
    return Replacement("enter_ready", lambda g, s, ev: ev.get("uid") == s and pred(g, s),
                       lambda g, s, ev: dict(ev, ready=True), label=label, zone="any", source_text=defn.text)


@script("Apprentice Smith")
def apprentice_smith(defn):
    # When I move, reveal the top card of your Main Deck. If it's a gear, draw it. Otherwise, recycle it.
    top = lambda g, c: (c.vars.get("looked") or [None])[0]
    is_gear = lambda g, c: top(g, c) is not None and g.objects[top(g, c)].base_defn().is_gear
    return [Triggered("move_self", [O.Look(1, out="looked", reveal=True),
                                    O.If(lambda g, c: top(g, c) is not None and g.objects[top(g, c)].zone == "deck",
                                         [O.If(is_gear, [O.ToHand(top)], [O.Recycle(top)])])],
                      label=defn.name, source_text=defn.text)]


@script("Dropboarder")
def dropboarder(defn):
    # When you play me, if you control two or more gear, ready me.
    two_gear = lambda g, s: sum(1 for u, o in g.objects.items() if o.zone == "board" and o.controller == g.objects[s].controller
                                and "gear" in g.chars(u).types) >= 2
    return [Triggered("play_self", [O.If(lambda g, c: two_gear(g, c.source), [O.Ready(Ref("self"))])],
                      filt=lambda g, s, ev: two_gear(g, s), label=defn.name, source_text=defn.text)]


@script("Production Surge")
def production_surge(defn):
    # This costs [2] less if you control a Mech.  Play a 3 [M] Mech unit token to your base.  Draw 1.
    def reduce(g, u, e, p):
        me = _ctrl(g, u)
        mech = any(o.zone == "board" and o.controller == me and "Mech" in g.chars(x).tags and "unit" in g.chars(x).types
                   for x, o in g.objects.items())
        return (max(0, e - 2), p) if mech else (e, p)
    return [PlayPermission("cost", cost_mod=reduce, label="[2] less if you control a Mech", source_text=defn.text),
            SpellEffect([O.PlayToken("Mech", loc="base"), O.Draw(1)], label=defn.name, source_text=defn.text)]


@script("Beast Below")
def beast_below(defn):
    # When you play me, return another friendly unit and an enemy unit to their owners' hands.
    return [Triggered("play_self", [O.Choose(Sel("unit", side="friendly", other=True), out="a"),
                                    O.Choose(Sel("unit", side="enemy"), out="b"),
                                    O.ToHand(lambda g, c: [u for u in (c.vars.get("a"), c.vars.get("b")) if u is not None])],
                      label=defn.name, source_text=defn.text)]


@script("Glasc Mixologist")
def glasc_mixologist(defn):
    # [Deathknell] — You may play a unit with cost no more than [3] and no more than [A] from your trash, ignoring its cost.
    def units(g, c):
        return [u for u in g.players[c.controller].trash if u != c.source and g.objects[u].base_defn().is_unit
                and (g.objects[u].base_defn().energy or 0) <= 3 and (g.objects[u].base_defn().power or 0) <= 1]
    return [Triggered("die_self", [O.ChooseFromList(units, out="__gm", up_to=True, label="play a unit from your trash"),
                                   O.Do(_unwrap("__gm")), O.If(Ref("__gm"), [O.PlayCard(Ref("__gm"), ignore="all")])],
                      label="Deathknell", source_text=defn.text, keyword="deathknell")]


@script("Rally the Troops")
def rally_the_troops(defn):
    # [Action]  When a friendly unit is played this turn, buff it.  Draw 1.
    played = lambda g, s, ev: ev.get("kind") == "play" and ev.get("card_type") == "unit"
    mine = lambda g, c, ev: ev.get("player") == c.controller
    return [SpellEffect([O.Delayed(played, [O.Buff(lambda g, c: c.event.get("uid"))], filt=mine, expires="turn", once=False,
                                   label="Rally the Troops: buff it"), O.Draw(1)], label=defn.name, source_text=defn.text)]


@script("Unsung Hero")
def unsung_hero(defn):
    # [Deathknell] — If I was [Mighty], draw 2.
    return [Triggered("die_self", [O.Draw(2)], filt=lambda g, s, ev: (ev.get("might") or 0) >= 5,
                      label="Deathknell", source_text=defn.text, keyword="deathknell")]


@script("Tianna Crownguard")
def tianna_crownguard(defn):
    # [Deflect]  While I'm at a battlefield, opponents can't score points.
    from ..abilities import Replacement

    def blocks(g, s, ev):
        o = g.objects[s]
        return (o.location is not None and o.location[0] == "bf" and ev.get("player") is not None
                and not g.is_friendly(ev["player"], o.controller))
    return [Replacement("gain_points", blocks, lambda g, s, ev: None, label="opponents can't score", source_text=defn.text)]


@script("Downwell")
def downwell(defn):
    # Return all units and gear to their owners' hands.
    def all_perms(g, c):
        return [u for u, o in g.objects.items() if o.zone == "board" and o.location is not None
                and o.location[0] in ("bf", "base") and ({"unit", "gear"} & g.chars(u).types)]
    return [SpellEffect([O.ToHand(all_perms)], label=defn.name, source_text=defn.text)]


@script("Towering Pairofant")
def towering_pairofant(defn):
    # [Assault]  If a unit died this turn, I enter ready.
    died = lambda g, s: any(v for k, v in g.turn_memo.items() if isinstance(k, tuple) and k[0] == "units_died")
    return [_enter_ready_if(defn, died, "enter ready if a unit died this turn")]


@script("Monch")
def monch(defn):
    # If an opponent controls a stunned unit, I cost [2] less and enter ready.
    def stunned_foe(g, s):
        me = _ctrl(g, s)
        return any(o.zone == "board" and o.stunned and o.controller is not None and not g.is_friendly(o.controller, me)
                   for o in g.objects.values())
    return [PlayPermission("cost", cost_mod=lambda g, u, e, p: (max(0, e - 2), p) if stunned_foe(g, u) else (e, p),
                           label="[2] less if an opponent controls a stunned unit", source_text=defn.text),
            _enter_ready_if(defn, stunned_foe, "enter ready if an opponent controls a stunned unit")]


@script("Prepared Neophyte")
def prepared_neophyte(defn):
    # If you've spent [4] or more to play a spell this turn, I have +4 [M].
    return [Static("self", "might", 4, cond=lambda g, s: bool(g.turn_memo.get(("spell_spent_4", g.objects[s].controller))),
                   label="+4 [M] after spending [4]+ on a spell", source_text=defn.text)]


@script("Combat Experience")
def combat_experience(defn):
    # [Reaction]  Give a unit +1 [M] this turn.  [Level 6][>] Give it +3 [M] this turn instead.
    return [SpellEffect([O.Choose(Sel("unit"), out="t"),
                         O.GiveMight(Ref("t"), lambda g, c: 3 if _xp(g, c.controller) >= 6 else 1)],
                        label=defn.name, source_text=defn.text)]


@script("Skyward Strike")
def skyward_strike(defn):
    # Move an enemy unit.  [Level 6][>] [Stun] an enemy unit.
    from .auto_grammar import parse_sentence
    leveled = Sel("unit", side="enemy", pred=lambda g, c, u: _xp(g, c.controller) >= 6)     # chosen as played
    return [SpellEffect(parse_sentence("move an enemy unit", {"tcount": 0}) + [O.Choose(leveled, out="s2"), O.Stun(Ref("s2"))],
                        label=defn.name, source_text=defn.text)]


@script("Concentrate")
def concentrate(defn):
    # Draw 2.  [Level 6][>] This costs [2] less.  [Level 11][>] This costs [4] less instead.
    def reduce(g, u, e, p):
        x = _xp(g, _ctrl(g, u))
        return (max(0, e - (4 if x >= 11 else 2 if x >= 6 else 0)), p)
    return [PlayPermission("cost", cost_mod=reduce, label="Level discounts", source_text=defn.text),
            SpellEffect([O.Draw(2)], label=defn.name, source_text=defn.text)]


def _look_reveal_draw_recycle(n, pred, label):
    cands = lambda g, c: [u for u in c.vars.get("looked", []) if pred(g.objects[u].base_defn())]
    return [O.Look(n, out="looked"),
            O.ChooseFromList(cands, out="__lr", up_to=True, label=label), O.Do(_unwrap("__lr")),
            O.If(Ref("__lr"), [O.Do(lambda g, c: g.emit("reveal", player=c.controller, cards=[c.vars["__lr"]], ctx=c)),
                               O.ToHand(Ref("__lr"))]),
            O.Recycle(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"])]


@script("Fate Weaver")
def fate_weaver(defn):
    # When you play me, look at the top 4 cards of your Main Deck. You may reveal a spell with Energy cost [4] or more
    # from among them and draw it. Recycle the rest.
    return [Triggered("play_self", _look_reveal_draw_recycle(4, lambda d: d.type == "spell" and (d.energy or 0) >= 4,
                                                             "reveal a spell costing [4]+ and draw it"),
                      label=defn.name, source_text=defn.text)]


@script("Double Trouble")
def double_trouble(defn):
    # [Repeat] [2]  Look at the top 3 cards of your Main Deck. You may reveal a unit from among them and draw it.
    # Recycle the rest.
    return [SpellEffect(_look_reveal_draw_recycle(3, lambda d: d.is_unit, "reveal a unit and draw it"),
                        label=defn.name, source_text=defn.text)]


def _enemy(g, c, u):
    o = g.objects[u]
    return o.controller is not None and not g.is_friendly(o.controller, c.controller)


@script("Kinkou Initiate")
def kinkou_initiate(defn):
    # When you play me, draw 1 if your other units have total Might 5 or more.
    def total(g, c):
        return sum(g.chars(u).might or 0 for u, o in g.objects.items() if u != c.source and o.zone == "board"
                   and o.controller == c.controller and "unit" in g.chars(u).types)
    return [Triggered("play_self", [O.If(lambda g, c: total(g, c) >= 5, [O.Draw(1)])], label=defn.name, source_text=defn.text)]


@script("Bewitching Spirit")
def bewitching_spirit(defn):
    # When you play me, choose a player. They discard 1.
    return [Triggered("play_self", [O.ChoosePlayer(out="__pl", opponent=False),
                                    O.Discard(1, player=lambda g, c: c.vars["__pl"])], label=defn.name, source_text=defn.text)]


@script("Isolate")
def isolate(defn):
    # Move an enemy unit from a battlefield to its base. Then, if there's an enemy unit alone at that battlefield, draw 1.
    def remember(g, c):
        t = c.vars.get("t")
        c.vars["__from"] = g.objects[t].location if t in g.objects else None

    def alone(g, c):
        loc = c.vars.get("__from")
        if loc is None:
            return False
        foes = {}
        for u in g.units_at(loc):
            if _enemy(g, c, u):
                foes.setdefault(g.objects[u].controller, []).append(u)
        return any(len(v) == 1 for v in foes.values())
    return [SpellEffect([O.Choose(Sel("unit", side="enemy", where="battlefield"), out="t"), O.Do(remember),
                         O.Move(Ref("t"), "base"), O.If(alone, [O.Draw(1)])], label=defn.name, source_text=defn.text)]


@script("Walking Roost")
def walking_roost(defn):
    # [Deflect]  When you play me, choose an opponent. They play a 1 [M] Bird unit token with [Deflect].
    def bird(g, c):
        p = c.vars.get("__opp")
        if p is not None:
            g.play_token(p, "Bird", ("base", p), ctx=c)
    return [Triggered("play_self", [O.ChoosePlayer(out="__opp", opponent=True), O.Do(bird, label="they play a Bird")],
                      label=defn.name, source_text=defn.text)]


@script("Crimson Pigeons")
def crimson_pigeons(defn):
    # I have +2 [M] while I'm attacking with another unit.
    def with_another(g, s):
        o = g.objects[s]
        return o.designation == "attacker" and any(u != s and g.objects[u].designation == "attacker"
                                                    for u in g.units_at(o.location, o.controller))
    return [Static("self", "might", 2, cond=with_another, label="+2 [M] attacking with another unit", source_text=defn.text)]


@script("Heroic Charge")
def heroic_charge(defn):
    # [Action]  Give a friendly unit +1 [M] this turn and [Stun] an enemy unit at its location.
    there = Sel("unit", side="enemy", pred=lambda g, c, u: c.vars.get("t") in g.objects
                and g.objects[u].location == g.objects[c.vars["t"]].location)
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Choose(there, out="s"),
                         O.GiveMight(Ref("t"), 1), O.Stun(Ref("s"))], label=defn.name, source_text=defn.text)]


@script("Loyal Poro")
def loyal_poro(defn):
    # [Deathknell][>] If I didn't die alone, draw 1.
    return [Triggered("die_self", [O.Draw(1)], filt=lambda g, s, ev: not ev.get("alone"),
                      label="Deathknell", source_text=defn.text, keyword="deathknell")]


@script("Scrutinizing Sergeant")
def scrutinizing_sergeant(defn):
    # When you play me, gain 1 XP for each friendly unit.
    n = lambda g, c: sum(1 for u, o in g.objects.items() if o.zone == "board" and o.controller == c.controller
                         and "unit" in g.chars(u).types)
    return [Triggered("play_self", [O.GainXP(n)], label=defn.name, source_text=defn.text)]


@script("Right of Conquest")
def right_of_conquest(defn):
    # Draw 1, then draw 1 for each battlefield you or allies control.
    n = lambda g, c: sum(1 for bf in g.battlefields if bf.controller is not None and g.is_friendly(bf.controller, c.controller))
    return [SpellEffect([O.Draw(1), O.Draw(n)], label=defn.name, source_text=defn.text)]


@script("Crescent Strike")
def crescent_strike(defn):
    # [Action]  Choose a battlefield and an enemy unit there. Deal 4 to that unit and 1 to each other enemy unit there.
    there = Sel("unit", side="enemy", pred=lambda g, c, u: g.objects[u].location == c.vars.get("loc"))
    others = lambda g, c: [u for u in g.units_at(c.vars["loc"]) if _enemy(g, c, u) and u != c.vars.get("t")]
    def deal(g, c):
        t = c.vars.get("t")
        rest = others(g, c)
        if t is not None:
            g.do_deal([t], 4, c)
        if rest:
            g.do_deal(rest, 1, c)
    return [SpellEffect([O.ChooseLocation(out="loc"), O.Choose(there, out="t"), O.Do(deal, label="deal 4 and 1")],
                        label=defn.name, source_text=defn.text)]


@script("Petal Pixie")
def petal_pixie(defn):
    # I have +1 [M] for each of your units with [Temporary] at my battlefield.
    def own_temp(g, x):
        o = g.objects[x]
        return bool(o.base_defn().keywords.get("temporary")) or any(
            m.kind == "keyword" and isinstance(m.value, tuple) and m.value[0] == "temporary" for m in o.mods)

    def n(g, s, u):
        o = g.objects[s]
        if o.location is None or o.location[0] != "bf":
            return 0
        return sum(1 for x in g.units_at(o.location, o.controller)
                   if (own_temp(g, x) if x == s else g.chars(x).keywords.get("temporary")))
    return [Static("self", "might", n, label="+1 [M] per Temporary unit here", source_text=defn.text)]


@script("Angler Beast")
def angler_beast(defn):
    # When you play me, return all units with 2 [M] or less to their owners' hands.
    small = lambda g, c: [u for u, o in g.objects.items() if o.zone == "board" and "unit" in g.chars(u).types
                          and (g.chars(u).might or 0) <= 2]
    return [Triggered("play_self", [O.ToHand(small)], label=defn.name, source_text=defn.text)]


@script("Existential Dread")
def existential_dread(defn):
    # [Action] [Repeat] [2]  [Stun] an attacking enemy unit. If it's already stunned, return it to its owner's hand instead.
    attacking = Sel("unit", side="enemy", pred=lambda g, c, u: g.objects[u].designation == "attacker")
    stunned = lambda g, c: c.vars.get("t") in g.objects and g.objects[c.vars["t"]].stunned
    return [SpellEffect([O.Choose(attacking, out="t"), O.If(stunned, [O.ToHand(Ref("t"))], [O.Stun(Ref("t"))])],
                        label=defn.name, source_text=defn.text)]


@script("Starhound")
def starhound(defn):
    # When you play me, return a Bird, Cat, Dog, or Poro from your trash to your hand.
    pets = lambda g, c: [u for u in g.players[c.controller].trash if {"Bird", "Cat", "Dog", "Poro"} & set(g.objects[u].base_defn().tags)]
    return [Triggered("play_self", [O.ChooseFromList(pets, out="__pet", label="return a Bird, Cat, Dog or Poro"),
                                    O.ToHand(Ref("__pet"))], label=defn.name, source_text=defn.text)]


@script("Wily Newtfish")
def wily_newtfish(defn):
    # If you've gained XP this turn, I have +1 [M] and [Ganking].
    gained = lambda g, s: bool(g.turn_memo.get(("xp_gained", g.objects[s].controller)))
    defn.keywords.pop("ganking", None)      # the printed [Ganking] is conditional, not a standing keyword
    return [Static("self", "might", 1, cond=gained, label="+1 [M] after gaining XP", source_text=defn.text),
            Static("self", "keyword", ("ganking", True), cond=gained, label="[Ganking] after gaining XP", source_text=defn.text)]


@script("Friendship")
def friendship(defn):
    # [Reaction]  Choose a unit. Give it +1 [M] this turn for each of the following tags among your units — Bird, Cat,
    # Dog, and Poro.
    def n(g, c):
        tags = set()
        for u, o in g.objects.items():
            if o.zone == "board" and o.controller == c.controller and "unit" in g.chars(u).types:
                tags |= {"Bird", "Cat", "Dog", "Poro"} & set(g.chars(u).tags)
        return len(tags)
    return [SpellEffect([O.Choose(Sel("unit"), out="t"), O.GiveMight(Ref("t"), n)], label=defn.name, source_text=defn.text)]


@script("Fresh Beans")
def fresh_beans(defn):
    # When you play a unit during a showdown, you may exhaust this to draw 1.
    def unit_in_showdown(g, s, ev):
        return (ev.get("kind") == "play" and ev.get("card_type") == "unit" and ev.get("player") == g.objects[s].controller
                and g.showdown is not None)
    ready = lambda g, c: c.source in g.objects and not g.objects[c.source].exhausted
    return [Triggered(unit_in_showdown, [O.If(ready, [O.May([O.Exhaust(Ref("self")), O.Draw(1)], label="exhaust this to draw 1")])],
                      label=defn.name, source_text=defn.text)]


@script("Stare Down")
def stare_down(defn):
    # Choose a friendly unit and a battlefield. Move all enemy units at that battlefield with less Might than the chosen
    # unit to their base. Gain 1 XP.
    def smaller(g, c):
        t = c.vars.get("t")
        if t not in g.objects or c.vars.get("loc") is None:
            return []
        m = g.chars(t).might or 0
        return [u for u in g.units_at(c.vars["loc"]) if _enemy(g, c, u) and (g.chars(u).might or 0) < m]
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.ChooseLocation(out="loc"),
                         O.Move(smaller, "base"), O.GainXP(1)], label=defn.name, source_text=defn.text)]


@script("Undying Legion")
def undying_legion(defn):
    # [Legion][>] You may play me from your trash for [3][Fury].
    return [PlayPermission("from_trash", zone="trash", alt_cost=(3, ["fury"]),
                           cond=lambda g, u: g.legion_active(g.objects[u].owner, u),
                           label="Legion: play me from your trash for [3][Fury]", source_text=defn.text)]


@script("Grim Resolve")
def grim_resolve(defn):
    # [Action]  Give a friendly unit +3 [M] this turn. When it wins a combat this turn, gain 2 XP.
    def wins(g, s, ev):
        return ev.get("kind") == "combat_result" and ev.get("winner") is not None
    won = lambda g, c, ev: c.vars.get("t") in (ev.get("winners") or ())
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.GiveMight(Ref("t"), 3),
                         O.Delayed(wins, [O.GainXP(2)], filt=won, expires="turn", once=True, label="Grim Resolve: 2 XP")],
                        label=defn.name, source_text=defn.text)]


def _kill_cost(sel, out="__k", remember=None):
    """Mandatory 'As an additional cost to play this, kill a friendly ...' (remember: fn(g, c, uid) before the kill)."""
    ins = [O.Choose(sel, out=out, targeted=False)]
    if remember is not None:
        ins.append(O.Do(lambda g, c: remember(g, c, c.vars.get(out))))
    return ins + [O.Kill(Ref(out))]


@script("Determined Sentry")
def determined_sentry(defn):
    # I can't move to base.
    return [Static("self", "rule", ("i_cant_move_to_base",), label="can't move to base", source_text=defn.text)]


@script("Sacrifice")
def sacrifice(defn):
    # [Reaction]  As an additional cost to play this, kill a friendly [Mighty] unit.  Draw 2 and channel 1 rune exhausted.
    mighty = Sel("unit", side="friendly", pred=lambda g, c, u: (g.chars(u).might or 0) >= 5)
    return [PlayPermission("additional_cost", value=(mighty, _kill_cost(mighty), True), label="kill a friendly Mighty unit",
                           source_text=defn.text),
            SpellEffect([O.Draw(2), O.Channel(1, exhausted=True)], label=defn.name, source_text=defn.text)]


@script("Heedless Resurrection")
def heedless_resurrection(defn):
    # [Reaction]  As an additional cost to play this, kill a friendly unit.  Play a unit from your trash that costs no
    # more Energy and no more Power than the killed unit, ignoring its cost.
    friendly = Sel("unit", side="friendly")

    def remember(g, c, u):
        if u in g.objects:
            d = g.objects[u].base_defn()
            c.vars["__ke"], c.vars["__kp"] = d.energy or 0, d.power or 0

    def units(g, c):
        return [u for u in g.players[c.controller].trash if g.objects[u].base_defn().is_unit
                and u != c.vars.get("__k")
                and (g.objects[u].base_defn().energy or 0) <= c.vars.get("__ke", -1)
                and (g.objects[u].base_defn().power or 0) <= c.vars.get("__kp", -1)]
    return [PlayPermission("additional_cost", value=(friendly, _kill_cost(friendly, remember=remember), True),
                           label="kill a friendly unit", source_text=defn.text),
            SpellEffect([O.ChooseFromList(units, out="__hr", label="play a unit from your trash"),
                         O.If(Ref("__hr"), [O.PlayCard(Ref("__hr"), ignore="all")])], label=defn.name, source_text=defn.text)]


@script("Lilting Lullaby")
def lilting_lullaby(defn):
    # [Reaction]  Counter a spell. Its controller can't play spells this turn.
    spell = Sel("card", zone="chain", pred=lambda g, c, u: any(it.uid == u and it.kind == "spell" for it in g.chain))

    def counter(g, c):
        u = c.vars.get("__sp")
        it = next((x for x in g.chain if x.uid == u and x.kind == "spell"), None)
        if it is None:
            return
        who = it.controller
        g.do_counter(it.id, c)
        g.add_turn_effect(c, "cant_play_spells", {"players": (who,)})
    return [SpellEffect([O.Choose(spell, out="__sp"), O.Do(counter, label="counter it")], label=defn.name, source_text=defn.text)]


@script("Keeper's Verdict")
def keepers_verdict(defn):
    # [Action]  Choose an enemy unit at a battlefield. Its owner places it on the top or bottom of their Main Deck.
    def place(g, c):
        t = c.vars.get("t")
        if t in g.objects and g.objects[t].zone == "board":
            if c.vars.get("__top"):
                g.put_on_top(t)
            else:
                g.do_recycle([t], c)
    return [SpellEffect([O.Choose(Sel("unit", side="enemy", where="battlefield"), out="t"),
                         O.If(Ref("t"), [O.ChooseFromList(lambda g, c: ["top", "bottom"], out="__tb", label="top or bottom",
                                                          player=lambda g, c: g.objects[c.vars["t"]].owner),
                                         O.Do(lambda g, c: c.vars.__setitem__("__top", c.vars.get("__tb") == "top")),
                                         O.Do(place, label="place it")])], label=defn.name, source_text=defn.text)]


@script("Ruthless Strike")
def ruthless_strike(defn):
    # [Action]  As an additional cost to play this, you may discard 1.  Deal 3 to a unit at a battlefield. If you paid
    # the additional cost, deal 5 to it instead.
    ins = [O.SetVar("__addok", False), O.If(lambda g, c: bool(g.players[c.controller].hand),
                                             [O.Discard(1), O.SetVar("__addok", True)])]
    return [PlayPermission("additional_cost", value=(None, ins, False), label="discard 1", source_text=defn.text),
            SpellEffect([O.Choose(Sel("unit", where="battlefield"), out="t"),
                         O.Deal(lambda g, c: 5 if c.paid.get("add") else 3, Ref("t"))], label=defn.name, source_text=defn.text)]


@script("Guttural Roar")
def guttural_roar(defn):
    # [Action]  Give a unit +2 [M] this turn. If it's [Empowered], give it +4 [M] this turn instead.
    amt = lambda g, c: 4 if c.vars.get("t") in g.objects and g.objects[c.vars["t"]].empowered else 2
    return [SpellEffect([O.Choose(Sel("unit"), out="t"), O.GiveMight(Ref("t"), amt)], label=defn.name, source_text=defn.text)]


@script("Ol' Poro")
def ol_poro(defn):
    # I can't be played on your first, second, or third turns.
    def ok(g, u):
        p = _ctrl(g, u)
        return not (g.turn_player == p and g.turns_taken.get(p, 0) <= 3)
    return [PlayPermission("restriction", cond=ok, label="not on your first three turns", source_text=defn.text)]


@script("Patched Porobot")
def patched_porobot(defn):
    # (I enter exhausted.)  When you play me, if you control 3 or more other gear, draw 1.
    gear3 = lambda g, s: sum(1 for u, o in g.objects.items() if u != s and o.zone == "board"
                             and o.controller == g.objects[s].controller and "gear" in g.chars(u).types) >= 3
    return [Triggered("play_self", [O.If(lambda g, c: gear3(g, c.source), [O.Draw(1)])], filt=lambda g, s, ev: gear3(g, s),
                      label=defn.name, source_text=defn.text)]


@script("Death from Below")
def death_from_below(defn):
    # Kill a unit at a battlefield. Then, if it had 3 [M] or less, you may play this from your trash for [A].
    def remember(g, c):
        t = c.vars.get("t")
        c.vars["__m"] = g.chars(t).might if t in g.objects else None

    return [SpellEffect([O.Choose(Sel("unit", where="battlefield"), out="t"), O.Do(remember), O.Kill(Ref("t")),
                         O.If(lambda g, c: c.vars.get("__m") is not None and c.vars["__m"] <= 3,
                              [O.SetVar("__may_replay", True)])], label=defn.name, source_text=defn.text),
            Triggered(lambda g, s, ev: ev.get("kind") == "resolve" and ev.get("uid") == s and ev.get("card_type") == "spell",
                      [O.If(lambda g, c: g.objects[c.source].zone == "trash" and c.event.get("may_replay"),
                            [O.May([O.PlayCard(Ref("self"), alt_cost=(0, ["any"]))], label="play this from your trash for [A]")])],
                      zone="trash", label="replay from trash", source_text=defn.text)]
