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


def _named_in_trash(g, u, name):
    return sum(1 for x in g.players[g.objects[u].owner].trash if g.objects[x].base_defn().name == name)


def _has_domain(g, u, dom):
    return dom in (g.chars(u).domains or ())


@script("Shadow Order Disciple")
def shadow_order_disciple(defn):
    # When I move, you may [Burn 1] to give me +1 [M] this turn.
    return [Triggered("move_self", [O.May([O.Burn(1), O.GiveMight(Ref("self"), 1)], label="burn 1 for +1 [M]")],
                      label=defn.name, source_text=defn.text)]


@script("Shadowblade Lurker")
def shadowblade_lurker(defn):
    # I cost [2] less for each card with my name in your trash.
    return [PlayPermission("cost", cost_mod=lambda g, u, e, p: (max(0, e - 2 * _named_in_trash(g, u, defn.name)), p),
                           label="[2] less per copy in your trash", source_text=defn.text)]


@script("Spiderling")
def spiderling(defn):
    # [Hidden]  I have +1 [M] for each other unit you control here with my name.
    # Your deck can have any number of cards named Spiderling.   (Deck.validate)
    def n(g, s, u):
        o = g.objects[s]
        return sum(1 for x in g.units_at(o.location, o.controller) if x != s and g.objects[x].defn.name == defn.name) \
            if o.location is not None else 0
    return [Static("self", "might", n, label="+1 [M] per other Spiderling here", source_text=defn.text)]


@script("Disciple of Shen")
def disciple_of_shen(defn):
    # [Hidden]  I have [Shield 3] while I'm at a battlefield with exactly one other unit you control.
    def one_other(g, s):
        o = g.objects[s]
        return o.location is not None and o.location[0] == "bf" and \
            len([x for x in g.units_at(o.location, o.controller) if x != s]) == 1
    defn.keywords.pop("shield", None)
    return [Static("self", "keyword", ("shield", 3), cond=one_other, label="[Shield 3] with exactly one other unit",
                   source_text=defn.text)]


@script("Keeper of Law")
def keeper_of_law(defn):
    # I cost [2][Order] less if you control a battlefield with exactly two units there.
    def ok(g, u):
        me = _ctrl(g, u)
        return any(bf.controller == me and len(g.units_at(("bf", bf.idx))) == 2 for bf in g.battlefields)

    def reduce(g, u, e, p):
        if not ok(g, u):
            return e, p
        p = list(p)
        if "order" in p:
            p.remove("order")
        return max(0, e - 2), p
    return [PlayPermission("cost", cost_mod=reduce, label="[2][Order] less", source_text=defn.text)]


@script("Consuming Curse")
def consuming_curse(defn):
    # [Action]  Deal 2 to a unit at a battlefield. This deals 1 Bonus Damage for each card with this name in your trash.
    return [SpellEffect([O.Choose(Sel("unit", where="battlefield"), out="t"),
                         O.Deal(lambda g, c: 2 + sum(1 for x in g.players[c.controller].trash
                                                     if g.objects[x].base_defn().name == defn.name), Ref("t"))],
                        label=defn.name, source_text=defn.text)]


@script("Perfect Execution")
def perfect_execution(defn):
    # Ready a unit and give it [Assault 3] this turn.  [Flow] [3][Fury]   (keyword)
    return [SpellEffect([O.Choose(Sel("unit"), out="t"), O.Ready(Ref("t")), O.GiveKeyword(Ref("t"), "assault", 3)],
                        label=defn.name, source_text=defn.text)]


@script("Shadow Assassin")
def shadow_assassin(defn):
    # I enter ready if you have a card with my name in your trash.
    return [_enter_ready_if(defn, lambda g, s: _named_in_trash(g, s, defn.name) > 0, "enter ready with a copy in your trash")]


@script("Pakaa Protector")
def pakaa_protector(defn):
    # When I move, reveal the top card of your Main Deck. If it's a unit, draw it. Otherwise, put it in your trash and
    # give me +2 [M] this turn.
    top = lambda g, c: (c.vars.get("looked") or [None])[0]
    is_unit = lambda g, c: g.objects[top(g, c)].base_defn().is_unit
    return [Triggered("move_self", [O.Look(1, out="looked", reveal=True),
                                    O.If(lambda g, c: top(g, c) is not None and g.objects[top(g, c)].zone == "deck",
                                         [O.If(is_unit, [O.ToHand(top)], [O.ToTrash(top), O.GiveMight(Ref("self"), 2)])])],
                      label=defn.name, source_text=defn.text)]


@script("Raving Witness")
def raving_witness(defn):
    # When I move, reveal the top card of your Main Deck. If it's [Mighty], draw it. Otherwise, recycle it.
    top = lambda g, c: (c.vars.get("looked") or [None])[0]
    mighty = lambda g, c: (g.objects[top(g, c)].base_defn().might or 0) >= 5
    return [Triggered("move_self", [O.Look(1, out="looked", reveal=True),
                                    O.If(lambda g, c: top(g, c) is not None and g.objects[top(g, c)].zone == "deck",
                                         [O.If(mighty, [O.ToHand(top)], [O.Recycle(top)])])],
                      label=defn.name, source_text=defn.text)]


@script("Resonating Strike")
def resonating_strike(defn):
    # [Hidden] [Reaction]  Choose a battlefield you control and a unit you control at a different location. Move that
    # unit to that battlefield and give it +2 [M] this turn.
    mine = lambda g, c, l: g.battlefields[l[1]].controller == c.controller
    elsewhere = Sel("unit", side="friendly", pred=lambda g, c, u: g.objects[u].location != c.vars.get("loc"))
    return [SpellEffect([O.ChooseLocation(out="loc", pred=mine), O.Choose(elsewhere, out="t"),
                         O.Move(Ref("t"), Ref("loc")), O.GiveMight(Ref("t"), 2)], label=defn.name, source_text=defn.text)]


@script("Shock Blast")
def shock_blast(defn):
    # [Action]  This costs [2] less if you control something that's [Empowered].  Deal 4 to a unit at a battlefield.
    emp = lambda g, u: any(o.zone == "board" and o.controller == _ctrl(g, u) and o.empowered for o in g.objects.values())
    return [PlayPermission("cost", cost_mod=lambda g, u, e, p: (max(0, e - 2), p) if emp(g, u) else (e, p),
                           label="[2] less with something Empowered", source_text=defn.text),
            SpellEffect([O.Choose(Sel("unit", where="battlefield"), out="t"), O.Deal(4, Ref("t"))], label=defn.name,
                        source_text=defn.text)]


@script("Noxian Demolitionist")
def noxian_demolitionist(defn):
    # When I conquer, you may kill a gear with Energy cost no more than my Might.
    gear = Sel("gear", pred=lambda g, c, u: (g.objects[u].base_defn().energy or 0) <= (g.chars(c.source).might or 0)
               if c.source in g.objects else False)
    return [Triggered("conquer_self", [O.May([O.Choose(gear, out="t"), O.Kill(Ref("t"))], label="kill a gear")],
                      label=defn.name, source_text=defn.text)]


@script("Shadows of the Past")
def shadows_of_the_past(defn):
    # Return up to 2 units from trashes to their owners' hands.
    units = lambda g, c: [u for q in g.players for u in q.trash if g.objects[u].base_defn().is_unit]
    return [SpellEffect([O.ChooseFromList(units, out="__sp", n=2, up_to=True, label="return up to 2 units"),
                         O.ToHand(lambda g, c: list(c.vars.get("__sp") or ()))], label=defn.name, source_text=defn.text)]


@script("Twilight Step")
def twilight_step(defn):
    # Move a unit with 3 [M] or less.  [Flow] [4][Chaos]   (keyword)
    from .auto_grammar import parse_sentence
    code = parse_sentence("move a unit", {"tcount": 0})
    code[0].sel = Sel("unit", pred=lambda g, c, u: (g.chars(u).might or 0) <= 3)
    return [SpellEffect(code, label=defn.name, source_text=defn.text)]


@script("Wind and Ghosts")
def wind_and_ghosts(defn):
    # [Action]  Choose a unit at a battlefield. If it has 3 [M] or less, banish it. Otherwise, return it to its owner's hand.
    small = lambda g, c: c.vars.get("t") in g.objects and (g.chars(c.vars["t"]).might or 0) <= 3
    return [SpellEffect([O.Choose(Sel("unit", where="battlefield"), out="t"),
                         O.If(small, [O.Banish(Ref("t"))], [O.ToHand(Ref("t"))])], label=defn.name, source_text=defn.text)]


@script("Decree of Rage")
def decree_of_rage(defn):
    # [Action]  This can't be countered.  Deal 4 to an enemy Calm unit.
    return [PlayPermission("uncounterable", label="can't be countered", source_text=defn.text),
            SpellEffect([O.Choose(Sel("unit", side="enemy", pred=lambda g, c, u: _has_domain(g, u, "calm")), out="t"),
                         O.Deal(4, Ref("t"))], label=defn.name, source_text=defn.text)]


@script("Decree of Insight")
def decree_of_insight(defn):
    # [Reaction]  Ignore [Deflect] while paying this spell's cost.  Give an enemy Body unit -5 [M] this turn.
    return [PlayPermission("ignore_deflect", label="ignore Deflect", source_text=defn.text),
            SpellEffect([O.Choose(Sel("unit", side="enemy", pred=lambda g, c, u: _has_domain(g, u, "body")), out="t"),
                         O.GiveMight(Ref("t"), -5)], label=defn.name, source_text=defn.text)]


@script("Decree of Strength")
def decree_of_strength(defn):
    # Choose an opponent. They reveal their hand and you choose a Mind card from it. They recycle that card.
    def reveal(g, c):
        p = c.vars.get("__opp")
        if p is not None:
            g.emit("reveal", player=p, cards=list(g.players[p].hand), ctx=c)
    mind = lambda g, c: [u for u in g.players[c.vars["__opp"]].hand if "mind" in (g.objects[u].base_defn().domains or ())]
    return [SpellEffect([O.ChoosePlayer(out="__opp", opponent=True), O.Do(reveal, label="reveal hand"),
                         O.ChooseFromList(mind, out="__dm", label="choose a Mind card"), O.Recycle(Ref("__dm"))],
                        label=defn.name, source_text=defn.text)]


@script("Decree of Focus")
def decree_of_focus(defn):
    # [Reaction]  Choose a friendly unit that's in combat with an enemy Fury unit or that's being chosen by an enemy Fury
    # spell. Give it +4 [M] this turn.
    def ok(g, c, u):
        o = g.objects[u]
        if g.combat is not None and o.location == ("bf", g.combat["bf"]) and any(
                _enemy(g, c, x) and _has_domain(g, x, "fury") for x in g.units_at(o.location)):
            return True
        for it in g.chain:
            if it.kind == "spell" and it.controller != c.controller and it.uid in g.objects \
                    and "fury" in (g.objects[it.uid].base_defn().domains or ()) and u in g._target_uids(it.ctx):
                return True
        return False
    return [SpellEffect([O.Choose(Sel("unit", side="friendly", pred=ok), out="t"), O.GiveMight(Ref("t"), 4)],
                        label=defn.name, source_text=defn.text)]


@script("Cataclysmic Duel")
def cataclysmic_duel(defn):
    # Each player chooses a unit they control. Kill the rest.
    def ask(q):
        # chosen as the spell resolves (a callable list keeps the choice out of the finalize step)
        return O.Choose(lambda g, c, q=q: [u for u, o in g.objects.items() if o.zone == "board" and o.controller == q
                                           and "unit" in g.chars(u).types], out=f"__keep{q}", targeted=False, player=q)

    def kill_rest(g, c):
        keep = {c.vars.get(f"__keep{q}") for q in range(len(g.players))}
        g.do_kill([u for u, o in g.objects.items() if o.zone == "board" and "unit" in g.chars(u).types and u not in keep], c)
    return [SpellEffect([ask(0), ask(1), O.Do(kill_rest, label="kill the rest")], label=defn.name, source_text=defn.text)]


@script("Lingering Animus")
def lingering_animus(defn):
    # I enter ready if a friendly unit or gear died this turn.
    return [_enter_ready_if(defn, lambda g, s: bool(g.turn_memo.get(("perms_died", g.objects[s].controller if
                                                                       g.objects[s].controller is not None else g.objects[s].owner))),
                            "enter ready if a friendly unit or gear died this turn")]


@script("Iridescent Avian")
def iridescent_avian(defn):
    # [T]: [Buff] a unit. If it's already buffed, give it +2 [M] this turn instead.
    from ..abilities import Activated
    buffed = lambda g, c: c.vars.get("t") in g.objects and g.objects[c.vars["t"]].buffs > 0
    return [Activated({"energy": 0, "power": [], "exhaust": True},
                      [O.If(buffed, [O.GiveMight(Ref("t"), 2)], [O.Buff(Ref("t"))])],
                      targets=[O.Choose(Sel("unit"), out="t")], label="buff a unit", source_text=defn.text)]


@script("Ki Burst")
def ki_burst(defn):
    # [Action]  As an additional cost to play this, exhaust a friendly unit.  [Stun] a unit.
    ready = Sel("unit", side="friendly", pred=lambda g, c, u: not g.objects[u].exhausted)
    return [PlayPermission("additional_cost", value=(ready, [O.Choose(ready, out="__kb", targeted=False), O.Exhaust(Ref("__kb"))], True),
                           label="exhaust a friendly unit", source_text=defn.text),
            SpellEffect([O.Choose(Sel("unit"), out="t"), O.Stun(Ref("t"))], label=defn.name, source_text=defn.text)]


@script("Parallel Convergence")
def parallel_convergence(defn):
    # As an additional cost to play this, return a friendly unit to its owner's hand.  Deal 5 to a unit at a battlefield.
    fr = Sel("unit", side="friendly")
    return [PlayPermission("additional_cost", value=(fr, [O.Choose(fr, out="__pc", targeted=False), O.ToHand(Ref("__pc"))], True),
                           label="return a friendly unit to hand", source_text=defn.text),
            SpellEffect([O.Choose(Sel("unit", where="battlefield"), out="t"), O.Deal(5, Ref("t"))], label=defn.name,
                        source_text=defn.text)]


@script("Fanfare")
def fanfare(defn):
    # The next three times you play a unit this turn, draw 1.
    played = lambda g, s, ev: ev.get("kind") == "play" and ev.get("card_type") == "unit"
    mine = lambda g, c, ev: ev.get("player") == c.controller
    return [SpellEffect([O.Delayed(played, [O.Draw(1)], filt=mine, expires="turn", once=True, label="Fanfare: draw 1")
                         for _ in range(3)], label=defn.name, source_text=defn.text)]


@script("Hold 'Em")
def hold_em(defn):
    # [Action]  This costs [2] less if you've played a unit or gear to a battlefield this turn.  Give a unit +3 [M].
    def to_bf(g, u):
        me = _ctrl(g, u)
        return bool(g.turn_memo.get(("played_to_bf", me)))
    return [PlayPermission("cost", cost_mod=lambda g, u, e, p: (max(0, e - 2), p) if to_bf(g, u) else (e, p),
                           label="[2] less after playing to a battlefield", source_text=defn.text),
            SpellEffect([O.Choose(Sel("unit"), out="t"), O.GiveMight(Ref("t"), 3)], label=defn.name, source_text=defn.text)]


@script("Disposal Expert")
def disposal_expert(defn):
    # I enter ready if you control no other units.  [Disarm 2]
    alone = lambda g, s: not any(u != s and o.zone == "board" and o.controller == _ctrl(g, s) and "unit" in g.chars(u).types
                                 for u, o in g.objects.items())
    return [_enter_ready_if(defn, alone, "enter ready with no other units")]


@script("Acceleration Gate")
def acceleration_gate(defn):
    # Ready up to 4 units, gear, and/or runes.
    things = lambda g, c: [u for u, o in g.objects.items() if o.zone == "board" and o.exhausted and
                           ({"unit", "gear", "rune"} & g.chars(u).types)]
    return [SpellEffect([O.ChooseFromList(things, out="__ag", n=4, up_to=True, label="ready up to 4"),
                         O.Ready(lambda g, c: list(c.vars.get("__ag") or ()))], label=defn.name, source_text=defn.text)]


@script("Up from the Deep")
def up_from_the_deep(defn):
    # Play two 1 [M] Tentacle unit tokens from Bilgewater.  [Flow] [3]
    return [SpellEffect([O.PlayToken("Tentacle", loc="choose", count=2)], label=defn.name, source_text=defn.text)]


@script("Lightning Rush")
def lightning_rush(defn):
    # Look at the top 3 cards of your Main Deck. You may choose a card from among them and draw it. Put the rest into
    # your trash.  [Flow] [2][A]
    return [SpellEffect([O.Look(3, out="looked"),
                         O.ChooseFromList(lambda g, c: list(c.vars.get("looked", [])), out="__lr", up_to=True, label="draw one"),
                         O.Do(_unwrap("__lr")), O.If(Ref("__lr"), [O.ToHand(Ref("__lr"))]),
                         O.ToTrash(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"])],
                        label=defn.name, source_text=defn.text)]


@script("Minah Swiftfoot")
def minah_swiftfoot(defn):
    # When I move to a battlefield, choose one — Each player discards 1. / Each player draws 1.
    to_bf = lambda g, s, ev: ev.get("kind") == "move" and ev.get("uid") == s and (ev.get("to") or ("",))[0] == "bf"
    each = lambda f: O.Do(lambda g, c: [f(g, c, q) for q in range(len(g.players))])
    return [Triggered(to_bf, [O.ChooseMode([
        ("each player discards 1", [O.Discard(1, player=0), O.Discard(1, player=1)]),
        ("each player draws 1", [each(lambda g, c, q: g.do_draw(q, 1, c))])])], label=defn.name, source_text=defn.text)]


@script("Dominus")
def dominus(defn):
    # [Action]  This turn, double a unit's Might and give it "[A][A]: Ready me."
    from ..abilities import Activated
    ready_me = Activated({"energy": 0, "power": ["any", "any"]}, [O.Ready(Ref("self"))], label="[A][A]: Ready me.",
                         source_text="[A][A]: Ready me.")
    return [SpellEffect([O.Choose(Sel("unit"), out="t"), O.DoubleMight(Ref("t")), O.GiveAbility(Ref("t"), ready_me)],
                        label=defn.name, source_text=defn.text)]


def _at_a_bf(g, s):
    o = g.objects[s]
    return o.zone == "board" and o.location is not None and o.location[0] == "bf"


def _bf_controller(g, s):
    o = g.objects[s]
    i = o.location[1] if o.location is not None else None
    return g.battlefields[i].controller if i is not None else None


@script("Aspirant's Climb")
def aspirants_climb(defn):
    # Increase the points needed to win the game by 1.
    return [Static("self", "rule", ("victory_plus", 1), label="+1 point needed to win", source_text=defn.text)]


@script("Sandstone Chimera")
def sandstone_chimera(defn):
    # While I'm at a battlefield, players only channel 1 rune at the start of their Channel Phase.
    return [Static("self", "rule", ("channel_only_one",), label="players channel only 1 rune", source_text=defn.text)]


@script("Sacred Protector")
def sacred_protector(defn):
    # I don't deal combat damage unless I'm at a battlefield with exactly one other unit you control.
    def not_paired(g, s):
        o = g.objects[s]
        return not (_at_a_bf(g, s) and len([x for x in g.units_at(o.location, o.controller) if x != s]) == 1)
    return [Static("self", "rule", ("no_combat_damage",), cond=not_paired, label="no combat damage unless paired",
                   source_text=defn.text)]


@script("Otterpus")
def otterpus(defn):
    # If a player would score 1 point from conquering or holding during their first or second turn, they draw 1 instead.
    from ..abilities import Replacement

    def early(g, s, ev):
        p = ev.get("player")
        return ev.get("reason") in ("conquer", "hold") and p == g.turn_player and g.turns_taken.get(p, 0) <= 2

    def draw_instead(g, s, ev):
        g.do_draw(ev["player"], 1)
        return None
    return [Replacement("gain_points", early, draw_instead, label="draw 1 instead of an early point", source_text=defn.text)]


@script("Threshold of the Gray")
def threshold_of_the_gray(defn):
    # When combat starts here, the attacker and defender each [Add] [1].
    def add(g, c):
        ev = c.event or {}
        for q in (ev.get("attacker"), ev.get("defender")):
            if q is not None:
                g.players[q].energy += 1
                g.emit("add", player=q, energy=1, power=[], ctx=c)
        g.bump()
    return [Triggered("combat_start_here", [O.Do(add, label="attacker and defender add [1]")], label=defn.name,
                      source_text=defn.text)]


@script("Valley of Idols")
def valley_of_idols(defn):
    # When a player plays a unit here, they may pay [1] to [Buff] it.
    here = lambda g, s, ev: ev.get("kind") == "play" and ev.get("card_type") == "unit" and ev.get("loc") == g.objects[s].place
    return [Triggered(here, [O.PayResources(1, out="__vi"), O.If(Ref("__vi"), [O.Buff(lambda g, c: c.event.get("uid"))])],
                      controller="event", label=defn.name, source_text=defn.text)]


@script("Gardens of Becoming")
def gardens_of_becoming(defn):
    # Units here have "[T]: Gain 1 XP."
    from ..abilities import Activated
    xp = Activated({"energy": 0, "power": [], "exhaust": True}, [O.GainXP(1)], label="[T]: Gain 1 XP.",
                   source_text="[T]: Gain 1 XP.")
    here = Sel("unit", pred=lambda g, c, u: g.objects[u].location == g.objects[c.source].place)
    return [Static(here, "ability", xp, label="units here: [T]: Gain 1 XP", source_text=defn.text)]


@script("Forgotten Library")
def forgotten_library(defn):
    # While you control this battlefield, when you play a spell, if you spent [4] or more, [Predict].
    def big_spell(g, s, ev):
        ctrl = _bf_controller(g, s) if g.objects[s].location and g.objects[s].location[0] == "bfcard" else None
        return (ev.get("kind") == "play" and ev.get("card_type") == "spell" and ctrl is not None
                and ev.get("player") == ctrl and (ev.get("energy") or 0) >= 4)
    return [Triggered(big_spell, [O.Predict(1)], controller="event", label=defn.name, source_text=defn.text)]


@script("Esteemed Hierophant")
def esteemed_hierophant(defn):
    # While you control 7 or more runes, prevent all damage that enemy spells and abilities would deal to me.
    from ..abilities import Replacement

    def applies(g, s, ev):
        o = g.objects[s]
        return (ev.get("uid") == s and not ev.get("combat") and ev.get("by") is not None
                and not g.is_friendly(ev["by"], o.controller) and len(g.players[o.controller].runes) >= 7)
    return [Replacement("damage", applies, lambda g, s, ev: None, label="prevent enemy spell damage", source_text=defn.text)]


def _fewer_runes_at_beginning(defn, gain, keyword=None):
    def fewer(g, s, ev):
        me = g.objects[s].controller
        return any(len(g.players[me].runes) < len(q.runes) for i, q in enumerate(g.players) if not g.is_friendly(i, me))
    eff = [O.GiveMight(Ref("self"), gain)] + ([O.GiveKeyword(Ref("self"), keyword)] if keyword else [])
    return [Triggered("start_beginning", eff, filt=fewer, label=defn.name, source_text=defn.text)]


@script("Forsaken Baccai")
def forsaken_baccai(defn):
    # If you control fewer runes than an opponent at the start of your Beginning Phase, give me +1 [M] this turn.
    return _fewer_runes_at_beginning(defn, 1)


@script("Oasis Raider")
def oasis_raider(defn):
    # If you control fewer runes than an opponent at the start of your Beginning Phase, give me +2 [M] and [Ganking].
    return _fewer_runes_at_beginning(defn, 2, "ganking")


@script("Shadow")
def shadow_unit(defn):
    # If you play me to a battlefield, I enter ready.  [Action][>] [1][A], [T]: [Stun] an enemy unit attacking here.
    from ..abilities import Activated
    att_here = Sel("unit", side="enemy", pred=lambda g, c, u: g.objects[u].designation == "attacker"
                   and g.objects[u].location == g.objects[c.source].location)
    from ..abilities import Replacement
    return [Replacement("enter_ready", lambda g, s, ev: ev.get("uid") == s and (ev.get("loc") or ("",))[0] == "bf",
                        lambda g, s, ev: dict(ev, ready=True), label="enter ready at a battlefield", zone="any", source_text=defn.text),
            Activated({"energy": 1, "power": ["any"], "exhaust": True}, [O.Stun(Ref("t"))], targets=[O.Choose(att_here, out="t")],
                      timing="action", label="stun an enemy attacking here", source_text=defn.text)]


@script("Tactical Retreat")
def tactical_retreat(defn):
    # [Reaction]  Choose a friendly unit. The next time it would die this turn, heal it, exhaust it, and recall it instead.
    def applies(g, ctx, ev):
        return ev.get("uid") == ctx.vars.get("t")
    rep = lambda g, ctx, ev: dict(ev, replaced_with="recall", exhaust=True)
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"),
                         O.DelayedPassive("replace:die", {"applies": applies, "replace": rep}, uses=1)],
                        label=defn.name, source_text=defn.text)]


@script("Thrill of the Hunt")
def thrill_of_the_hunt(defn):
    # [Reaction]  Banish a friendly unit, then its owner plays it to any battlefield, ignoring its cost.
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Banish(Ref("t")),
                         O.If(lambda g, c: c.vars.get("t") in g.objects and g.objects[c.vars["t"]].zone == "banish", [
                             O.ChooseLocation(out="__tl", player=lambda g, c: g.objects[c.vars["t"]].owner),
                             O.PlayCard(Ref("t"), ignore="all", loc=Ref("__tl"), player=lambda g, c: g.objects[c.vars["t"]].owner)])],
                        label=defn.name, source_text=defn.text)]


@script("Moonfall")
def moonfall(defn):
    # [Action]  Choose a battlefield where you have units. You may move up to one enemy unit to that battlefield. Then
    # give enemy units there -2 [M] this turn.
    where = lambda g, c, l: bool(g.units_at(l, c.controller))
    foes_there = lambda g, c: [u for u in g.units_at(c.vars["loc"]) if _enemy(g, c, u)]
    elsewhere = Sel("unit", side="enemy", pred=lambda g, c, u: g.objects[u].location != c.vars.get("loc"))
    return [SpellEffect([O.ChooseLocation(out="loc", pred=where),
                         O.Choose(elsewhere, out="__mv", n=1, up_to=True),
                         O.Move(lambda g, c: list(c.vars.get("__mv") or ()), Ref("loc")),
                         O.GiveMight(foes_there, -2)], label=defn.name, source_text=defn.text)]


@script("Rally for War")
def rally_for_war(defn):
    # Choose an occupied enemy battlefield. Play three 1 [M] Recruit unit tokens there.
    occ = lambda g, c, l: g.battlefields[l[1]].controller is not None and not g.is_friendly(g.battlefields[l[1]].controller, c.controller) \
        and bool(g.units_at(l))
    return [SpellEffect([O.ChooseLocation(out="loc", pred=occ), O.PlayToken("Recruit", loc=Ref("loc"), count=3)],
                        label=defn.name, source_text=defn.text)]


@script("Siphoning Strike")
def siphoning_strike(defn):
    # Deal 4 to a unit at a battlefield. If you control 7 or more runes, deal 7 to it instead. When it dies this turn,
    # channel 1 rune exhausted.
    dies = lambda g, s, ev: ev.get("kind") == "die"
    it_died = lambda g, c, ev: ev.get("uid") == c.vars.get("t")
    return [SpellEffect([O.Choose(Sel("unit", where="battlefield"), out="t"),
                         O.Delayed(dies, [O.Channel(1, exhausted=True)], filt=it_died, expires="turn", once=True,
                                   label="Siphoning Strike: channel 1"),
                         O.Deal(lambda g, c: 7 if len(g.players[c.controller].runes) >= 7 else 4, Ref("t"))],
                        label=defn.name, source_text=defn.text)]


@script("Corrupted Dragon")
def corrupted_dragon(defn):
    # If your score is not within 3 points of the Victory Score, I enter ready.  When I attack, you may move any number
    # of enemy units here each with 5 [M] or less to their base.
    far = lambda g, s: g.players[_ctrl(g, s)].points < g.victory_score() - 3
    small_here = lambda g, c: [u for u in g.units_at(g.objects[c.source].location) if _enemy(g, c, u)
                               and (g.chars(u).might or 0) <= 5]
    return [_enter_ready_if(defn, far, "enter ready when not close to winning"),
            Triggered("attack_self", [O.ChooseFromList(small_here, out="__cd", n=99, up_to=True, label="move enemy units to base"),
                                      O.Move(lambda g, c: list(c.vars.get("__cd") or ()), "base")],
                      label=defn.name, source_text=defn.text)]


@script("Affectionate Poro")
def affectionate_poro(defn):
    # When a combat that I was in ends, if I haven't been dealt damage this turn, draw 1.
    unhurt = lambda g, s, ev: not g.objects[s].temp.get(("dealt_damage", g.turn))
    return [Triggered("survive_combat_self", [O.Draw(1)], filt=unhurt, label=defn.name, source_text=defn.text)]


# ---------------------------------------------------------------- Radiance cards whose gallery type was wrong
def _gear_with_deploy_at(g, p, loc):
    return any(o.zone == "board" and o.location == loc and g.is_friendly(o.controller, p) and o.defn.is_gear
               and g.has_keyword(u, "deploy") for u, o in g.objects.items())


@script("Overloaded Traveler")
def overloaded_traveler(defn):
    # While there's a friendly gear with [Deploy] at my battlefield, I have +1 [M].
    def cond(g, s):
        o = g.objects[s]
        return o.location is not None and o.location[0] == "bf" and _gear_with_deploy_at(g, o.controller, o.location)
    return [Static("self", "might", 1, cond=cond, label="+1 [M] with a friendly [Deploy] gear here", source_text=defn.text)]


@script("Meticulous Restorationist")
def meticulous_restorationist(defn):
    # When you play a card with Energy cost [7] or more, you may play me from your trash for [Order].
    def big(g, s, ev):
        if ev.get("kind") != "play" or ev.get("token") or ev.get("player") != g.objects[s].owner or ev.get("uid") == s:
            return False
        o = g.objects.get(ev.get("uid"))
        return o is not None and (o.base_defn().energy or 0) >= 7
    return [Triggered(big, [O.May([O.PlayCard(Ref("self"), alt_cost=(0, ["order"]))], label="play me from your trash for [Order]")],
                      zone="trash", label=defn.name, source_text=defn.text)]


@script("Improvised Projectile")
def improvised_projectile(defn):
    # [Action]  Choose a friendly gear. Deal damage equal to its Energy cost to a unit at a battlefield.
    cost = lambda g, c: g.objects[c.vars["gr"]].base_defn().energy or 0 if c.vars.get("gr") is not None else 0
    return [SpellEffect([O.Choose(Sel("gear", side="friendly"), out="gr"), O.Choose(Sel("unit", where="battlefield"), out="t"),
                         O.Deal(cost, Ref("t"))], label=defn.name, source_text=defn.text)]


@script("An Offer You Can't Refuse")
def an_offer_you_cant_refuse(defn):
    # [Action]  Kill a gear. Its controller plays a Gold gear token exhausted.
    def gold(g, c):
        p = c.vars.get("__ctl")
        if p is not None:
            g.play_token(p, "Gold", ("base", p), exhausted_gear=True, ctx=c)
    def remember(g, c):
        t = c.vars.get("t")
        c.vars["__ctl"] = g.objects[t].controller if t is not None else None
    return [SpellEffect([O.Choose(Sel("gear"), out="t"), O.Do(remember, label="its controller"), O.Kill(Ref("t")),
                         O.Do(gold, label="its controller plays a Gold gear token exhausted")], label=defn.name, source_text=defn.text)]


@script("Burn Away")
def burn_away(defn):
    # Banish a unit with 3 [M] or less or a gear. [Burn 2].
    ok = lambda g, c, u: "gear" in g.chars(u).types or (g.chars(u).might or 0) <= 3
    return [SpellEffect([O.Choose(Sel("permanent", pred=ok), out="t"), O.Banish(Ref("t")), O.Burn(2)],
                        label=defn.name, source_text=defn.text)]


@script("Scrutinizing Scope")
def scrutinizing_scope(defn):
    # [1], [T]: Choose an opponent. They guess a card type. Reveal the top card of your Main Deck. If it has that type,
    # recycle it. Otherwise, draw it. (Unit, gear, and spell are types.)
    from ..abilities import Activated
    kinds = ["unit", "gear", "spell"]
    top = lambda g, c: (c.vars.get("looked") or [None])[0]
    guessed = lambda g, c: top(g, c) is not None and kinds[c.vars.get("__guess", 0)] in g.objects[top(g, c)].base_defn().types
    return [Activated({"energy": 1, "power": [], "exhaust": True},
                      [O.ChoosePlayer(out="__opp", opponent=True),
                       O.ChooseMode([(f"guess {k}", []) for k in kinds], out="__guess", player=Ref("__opp")),
                       O.Look(1, out="looked", reveal=True),
                       O.If(lambda g, c: top(g, c) is not None and g.objects[top(g, c)].zone == "deck",
                            [O.If(guessed, [O.Recycle(top)], [O.Draw(1)])])],
                      timing="main", label=defn.name, source_text=defn.text)]


@script("Battlefield Armorer")
def battlefield_armorer(defn):
    # When a friendly gear at a battlefield dies, you may pay [1] to return it to its owner's hand.
    def dies(g, s, ev):
        return ev.get("kind") == "die" and ev.get("card_type") == "gear" and ev.get("loc") is not None and ev["loc"][0] == "bf" \
            and g.is_friendly(ev.get("player"), g.objects[s].controller)
    back = lambda g, c: c.event.get("uid") if g.objects[c.event.get("uid")].zone == "trash" else None
    return [Triggered(dies, [O.PayResources(1, out="__ba"), O.If(Ref("__ba"), [O.ToHand(back)])],
                      label=defn.name, source_text=defn.text)]


@script("Demacian Illuminators")
def demacian_illuminators(defn):
    # When one or more friendly units die, [Buff] a friendly unit.
    return [Triggered("friendly_units_die_batch", [O.Choose(Sel("unit", side="friendly"), out="t"), O.Buff(Ref("t"))],
                      label=defn.name, source_text=defn.text)]


@script("Zero Point Inflection")
def zero_point_inflection(defn):
    # When you play a card, draw 2.
    # When you draw 1 or more cards with 9 or more other cards in your hand, discard your hand, kill this, and choose an
    # opponent. They score 1 point.
    def full(g, s, ev):
        if ev.get("kind") != "draw" or ev.get("player") != g.objects[s].controller:
            return False
        memo = g.objects[s].temp.setdefault("zpi_batches", {})     # batch -> [cards drawn so far, already triggered]
        st = memo.setdefault(ev.get("batch"), [0, False])
        st[0] += 1
        if st[1] or len(g.players[ev["player"]].hand) - st[0] < 9:
            return False
        st[1] = True
        return True
    def discard_all(g, c):
        g.do_discard(c.controller, list(g.players[c.controller].hand), c)
    return [Triggered("you_play_card", [O.Draw(2)], label="When you play a card, draw 2", source_text=defn.text),
            Triggered(full, [O.Do(discard_all, label="discard your hand"), O.Kill(Ref("self")),
                             O.ChoosePlayer(out="__opp", opponent=True), O.GainPoints(1, player=Ref("__opp"))],
                      label="hand overflow", source_text=defn.text)]
