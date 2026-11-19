"""Hand scripts for common cards the auto-scripter cannot parse (each against its printed text)."""
from __future__ import annotations

from . import script, SpellEffect
from ..abilities import Static, Triggered, PlayPermission, _by_me
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
    return [Triggered("play_self", [O.Buff(Ref("self")), O.Draw(1)],
                      filt=poro, label=defn.name, source_text=defn.text)]


@script("Portal Rescue")
def portal_rescue(defn):
    # [Action]  Banish a friendly unit, then its owner plays it to their base, ignoring its cost. (errata, Origins)
    owner = lambda g, c: g.objects[c.vars["t"]].owner
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Banish(Ref("t")),
                         O.If(lambda g, c: c.vars.get("t") in g.objects and g.objects[c.vars["t"]].zone == "banish",
                              [O.PlayCard(Ref("t"), ignore="all", loc=lambda g, c: ("base", owner(g, c)), player=owner)])],
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
    # I cost [1] less for each card in your trash. Played from the trash (Last Rites) Rhasa is on the chain when its cost
    # is set (CR 354-357), so it doesn't count itself.
    return [PlayPermission("cost", cost_mod=lambda g, u, e, p: (max(0, e - sum(1 for x in g.players[_ctrl(g, u)].trash if x != u)), p),
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
    return [Triggered("play_self", [O.Ready(Ref("self"))],
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
    return [Triggered("play_self", [O.Draw(1)], filt=lambda g, s, ev: gear3(g, s),
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
    elsewhere = Sel("unit", side="friendly", pred=lambda g, c, u: g.objects[u].location != c.vars.get("loc"), elsewhere=True)
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
        return (ev.get("uid") == s and not ev.get("combat") and not ev.get("unit_source") and ev.get("by") is not None
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
                             O.ChooseLocation(out="__tl", player=lambda g, c: g.objects[c.vars["t"]].owner,
                                              pred=lambda g, c, l: l not in {g.objects[s].place for s, _ in g.rules("cant_play_here")}),
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


# ---------------------------------------------------------------- Origins commons (batch 2026-11-06 15:50)
@script("Raging Soul")
def raging_soul(defn):
    # If you've discarded a card this turn, I have [Assault] and [Ganking].
    defn.keywords.pop("assault", None); defn.keywords.pop("ganking", None)      # conditional, not printed keywords
    cond = lambda g, s: g.turn_memo.get(("discarded", g.objects[s].controller), 0) > 0
    return [Static("self", "keyword", ("assault", True), cond=cond, source_text=defn.text),
            Static("self", "keyword", ("ganking", True), cond=cond, source_text=defn.text)]


def _pick_up_to(options, n, out, label):
    """'up to N' among many options as N single picks (each may pick nothing), collected in ctx.vars[out]."""
    def init(g, c):
        c.vars[out] = []
    def add(i):
        def f(g, c):
            v = c.vars.get(f"{out}_{i}")
            if v:
                c.vars[out].extend(v if isinstance(v, (tuple, list)) else [v])
        return f
    rest = lambda g, c: [u for u in options(g, c) if u not in c.vars.get(out, [])]
    tail = []
    for i in reversed(range(n)):          # stop asking once nothing is picked
        picked = lambda g, c, i=i: bool(c.vars.get(f"{out}_{i}"))
        tail = [O.ChooseFromList(rest, out=f"{out}_{i}", n=1, up_to=True, label=label), O.Do(add(i), label=label)] + \
            ([O.If(picked, tail)] if tail else [])
    return [O.Do(init, label=label)] + tail


@script("Forge of the Future")
def forge_of_the_future(defn):
    # When you play this, play a 1 [M] Recruit unit token at your base.  Kill this: Recycle up to 4 cards from trashes.
    from ..abilities import Activated
    trashes = lambda g, c: [u for ps in g.players for u in ps.trash]
    return [Triggered("play_self", [O.PlayToken("Recruit", loc="base")], label=defn.name, source_text=defn.text),
            Activated({"energy": 0, "power": [], "kill_self": True},
                      _pick_up_to(trashes, 4, "__rc", "recycle a card from a trash (up to 4)") +
                      [O.Recycle(lambda g, c: list(c.vars.get("__rc") or ()))],
                      timing="main", label="Kill this: recycle up to 4", source_text=defn.text)]


@script("Reinforce")
def reinforce(defn):
    # Look at the top 5 cards of your Main Deck. You may banish a unit from among them, then play it, reducing its cost
    # by [5]. Recycle the remaining cards.
    units = lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck" and g.objects[u].base_defn().is_unit]
    def cheaper(g, c):
        e, pw = g.card_cost(c.controller, c.vars["__ru"], "banish", None)
        return (max(0, e - 5), pw)
    return [SpellEffect([O.Look(5, out="looked"),
                         O.ChooseFromList(units, out="__ru", up_to=True, label="banish a unit, then play it for [5] less"),
                         O.Do(_unwrap("__ru")),
                         O.If(Ref("__ru"), [O.Banish(Ref("__ru")), O.PlayCard(Ref("__ru"), alt_cost=cheaper)]),
                         O.Recycle(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"])],
                        label=defn.name, source_text=defn.text)]


@script("Pack of Wonders")
def pack_of_wonders(defn):
    # [T]: Return another friendly gear, unit, or [Hidden] card to its owner's hand.
    from ..abilities import Activated
    def opts(g, c):
        out = []
        for u, o in g.objects.items():
            if u == c.source or not g.is_friendly(o.controller, c.controller):
                continue
            if o.zone == "board" and o.defn.type != "rune" and ("unit" in g.chars(u).types or "gear" in g.chars(u).types):
                out.append(u)
            elif o.zone == "facedown":
                out.append(u)
        return out
    return [Activated({"energy": 0, "power": [], "exhaust": True},
                      [O.ChooseFromList(opts, out="__pw", label="return to its owner's hand"), O.ToHand(Ref("__pw"))],
                      timing="main", label=defn.name, source_text=defn.text)]


@script("The Grand Plaza")
def the_grand_plaza(defn):
    # When you hold here, if you have 7+ units here, you win the game.
    def win(g, c):
        p = c.event.get("player")
        if len([u for u in g.units_at(c.event.get("loc")) if g.objects[u].controller == p]) >= 7:
            g._end_game(p, "The Grand Plaza")
    return [Triggered("you_hold_here", [O.Do(win, label="7+ units here: win the game")], controller="event",
                      label=defn.name, source_text=defn.text)]


@script("Hallowed Tomb")
def hallowed_tomb(defn):
    # When you hold here, you may return your Chosen Champion from your trash to your Champion Zone if it is empty.
    def can(g, c):
        ps = g.players[c.controller]
        u = ps.chosen_champion
        return ps.champion is None and u is not None and g.objects[u].zone == "trash"
    def back(g, c):
        ps = g.players[c.controller]
        g._to_zone(g.objects[ps.chosen_champion], "champion"); g.bump()
    return [Triggered("you_hold_here", [O.If(can, [O.May([O.Do(back, label="Chosen Champion to the Champion Zone")],
                                                         label="return your Chosen Champion from your trash")])],
                      controller="event", label=defn.name, source_text=defn.text)]


@script("Shakedown")
def shakedown(defn):
    # [Reaction]  Choose an enemy unit. Deal 6 to it unless its controller has you draw 2.
    ctl = lambda g, c: g.objects[c.vars["t"]].controller
    return [SpellEffect([O.Choose(Sel("unit", side="enemy"), out="t"),
                         O.ChooseMode([("take 6 damage", [O.Deal(6, Ref("t"))]), ("let them draw 2", [O.Draw(2)])],
                                      player=ctl)],
                        label=defn.name, source_text=defn.text)]


@script("Albus Ferros")
def albus_ferros(defn):
    # When you play me, spend any number of buffs. For each buff spent, channel 1 rune exhausted.
    buffed = lambda g, c: [u for u, o in g.objects.items() if o.zone == "board" and o.controller == c.controller and o.buffs > 0]
    def run(g, c):
        n = 0
        for u in c.vars.get("__ab") or ():
            if g.do_spend_buff(u, c):
                n += 1
        if n:
            g.do_channel(c.controller, n, exhausted=True)
        g.bump()
    return [Triggered("play_self", [O.ChooseFromList(buffed, out="__ab", n=lambda g, c: len(buffed(g, c)), up_to=True,
                                                     label="spend buffs: channel 1 rune exhausted for each"),
                                    O.Do(run, label="spend buffs, channel")], label=defn.name, source_text=defn.text)]


@script("Mistfall")
def mistfall(defn):
    # When you buff a friendly unit, you may pay [Body] and exhaust this to ready it.
    def buffed(g, s, ev):
        return ev.get("kind") == "buff" and _by_me(g, s, ev) and ev.get("player") == g.objects[s].controller
    ready_me = lambda g, c: not g.objects[c.source].exhausted
    return [Triggered(buffed, [O.If(ready_me, [O.PayResources(0, ["body"], out="__mf"),
                                               O.If(Ref("__mf"), [O.Exhaust(Ref("self")), O.Ready(lambda g, c: c.event.get("uid"))])])],
                      label=defn.name, source_text=defn.text)]


@script("Overt Operation")
def overt_operation(defn):
    # [Action]  For each friendly unit, you may spend its buff to ready it. Then buff all friendly units.
    buffed = lambda g, c: [u for u, o in g.objects.items() if o.zone == "board" and g.is_friendly(o.controller, c.controller)
                           and "unit" in g.chars(u).types and o.buffs > 0]
    friends = lambda g, c: [u for u, o in g.objects.items() if o.zone == "board" and g.is_friendly(o.controller, c.controller)
                            and "unit" in g.chars(u).types]
    def run(g, c):
        for u in c.vars.get("__oo") or ():
            if g.do_spend_buff(u, c):
                g.do_ready(u, c)
        g.bump()
    return [SpellEffect([O.ChooseFromList(buffed, out="__oo", n=lambda g, c: len(buffed(g, c)), up_to=True,
                                          label="spend buffs to ready those units"),
                         O.Do(run, label="spend buffs, ready"), O.Buff(friends)], label=defn.name, source_text=defn.text)]


# ---------------------------------------------------------------- batch 2026-11-06 16:00
class _RevealUntilUnit(O.Instr):
    """Dazzling Aurora: reveal cards from the top of your Main Deck until you reveal a unit (__du; the rest in __dr).
    A Nocturne, Horrifying banished as he is revealed is not revealed (CR 370), so the reveals go on past him."""
    label = "reveal until a unit"

    def run(self, g, c):
        c.vars["__dr"], c.vars["__du"], c.vars["__noct_done"] = [], None, []
        return self._go(g, c)

    def _go(self, g, c):
        for u in list(g.players[c.controller].deck):
            if u in c.vars["__dr"]:
                continue
            if not g.objects[u].base_defn().is_unit:
                c.vars["__dr"].append(u)
                continue
            d = O._nocturne_step(g, c, [u], viewer=c.controller)
            if d is not None:
                return d
            if g.objects[u].zone == "deck":
                c.vars["__du"] = u
                break
        shown = c.vars["__dr"] + ([c.vars["__du"]] if c.vars["__du"] is not None else [])
        if shown:
            g.emit("reveal", cards=tuple(shown), player=c.controller, ctx=c)
        return None

    def resume(self, g, c, choice):
        d = O._nocturne_apply(g, c, choice)
        if d is not None:
            return d
        return self._go(g, c)


@script("Dazzling Aurora")
def dazzling_aurora(defn):
    # At the end of your turn, reveal cards from the top of your Main Deck until you reveal a unit. Play it, ignoring its
    # cost, and recycle the rest.
    return [Triggered("end_turn", [_RevealUntilUnit(),
                                   O.If(Ref("__du"), [O.PlayCard(Ref("__du"), ignore="all")]),
                                   O.Recycle(lambda g, c: [u for u in c.vars.get("__dr", []) if g.objects[u].zone == "deck"])],
                      label=defn.name, source_text=defn.text)]


@script("Stormbringer, Volibear")
def stormbringer(defn):
    # Choose a friendly unit in your base. Deal damage equal to its Might to all enemy units at a battlefield, then move
    # your unit there.
    foes = lambda g, c: [u for u in g.units_at(c.vars["loc"]) if _enemy(g, c, u)]
    might = lambda g, c: g.chars(c.vars["t"]).might or 0
    return [SpellEffect([O.Choose(Sel("unit", side="friendly", where="own_base"), out="t"), O.ChooseLocation(out="loc"),
                         O.Deal(might, foes), O.Move(Ref("t"), Ref("loc"))], label=defn.name, source_text=defn.text)]


@script("Dragon's Rage, Lee Sin")
def dragons_rage(defn):
    # Move an enemy unit. Then choose another enemy unit at its destination. They deal damage equal to their Mights to
    # each other.
    dests = lambda g, c, l: c.vars.get("t") is not None and l != g.objects[c.vars["t"]].location and g.valid_destination(c.vars["t"], l, mover=c.controller)
    there = lambda g, c: [u for u in g.units_at(g.objects[c.vars["t"]].location) if u != c.vars["t"] and _enemy(g, c, u)] \
        if c.vars.get("t") in g.objects and g.objects[c.vars["t"]].zone == "board" else []
    return [SpellEffect([O.Choose(Sel("unit", side="enemy"), out="t"),
                         O.ChooseLocation(out="loc", pred=dests, include_bases=True, label="move it where?"),
                         O.Move(Ref("t"), Ref("loc")),
                         O.ChooseFromList(there, out="t2", label="choose another enemy unit there"),
                         O.Do(lambda g, c: _fight(g, c, c.vars.get("t"), c.vars.get("t2")) if c.vars.get("t2") else None,
                              label="they deal damage to each other")], label=defn.name, source_text=defn.text)]


@script("Zenith Blade, Leona")
def zenith_blade(defn):
    # [Action]  Stun an enemy unit at a battlefield. You may move a friendly unit to that enemy unit's battlefield.
    bf = lambda g, c: g.objects[c.vars["t"]].location
    movers = lambda g, c: [u for u, o in g.objects.items() if o.zone == "board" and g.is_friendly(o.controller, c.controller)
                           and "unit" in g.chars(u).types and o.location != bf(g, c) and g.valid_destination(u, bf(g, c), mover=c.controller)]
    return [SpellEffect([O.Choose(Sel("unit", side="enemy", where="battlefield"), out="t"), O.Stun(Ref("t")),
                         O.ChooseFromList(movers, out="__zm", up_to=True, label="you may move a friendly unit there"),
                         O.Move(lambda g, c: list(c.vars.get("__zm") or ()), bf)],
                        label=defn.name, source_text=defn.text)]


@script("Strike Down")
def strike_down(defn):
    # Choose an equipped friendly unit. It deals damage equal to its Might to an enemy unit. Then detach an Equipment
    # from it.
    equipped = Sel("unit", side="friendly", pred=lambda g, c, u: bool(g.objects[u].attachments))
    gear = lambda g, c: list(g.objects[c.vars["t"]].attachments) if c.vars.get("t") in g.objects else []
    return [SpellEffect([O.Choose(equipped, out="t"), O.Choose(Sel("unit", side="enemy"), out="t2"),
                         O.Deal(lambda g, c: g.chars(c.vars["t"]).might or 0, Ref("t2")),
                         O.ChooseFromList(gear, out="__sd", label="detach an Equipment"),
                         O.If(Ref("__sd"), [O.Detach(Ref("__sd"))])], label=defn.name, source_text=defn.text)]


@script("Smite")
def smite(defn):
    # [Action]  Deal 3 to a unit at a battlefield. If it would die this turn, banish it instead.
    applies = lambda g, ctx, ev: ev.get("uid") == ctx.vars.get("t")
    rep = lambda g, ctx, ev: dict(ev, replaced_with="banish")
    return [SpellEffect([O.Choose(Sel("unit", where="battlefield"), out="t"),
                         O.DelayedPassive("replace:die", {"applies": applies, "replace": rep}),
                         O.Deal(3, Ref("t"))], label=defn.name, source_text=defn.text)]


@script("Noxian Guillotine, Darius")
def noxian_guillotine(defn):
    # [Action]  Choose a unit. Kill it the next time it takes damage this turn.  [Legion] — Kill it now instead.
    legion = lambda g, c: g.legion_active(c.controller, c.source)
    dmg = lambda g, s, ev: ev.get("kind") == "damage"
    it = lambda g, c, ev: ev.get("uid") == c.vars.get("t")
    return [SpellEffect([O.Choose(Sel("unit"), out="t"),
                         O.If(legion, [O.Kill(Ref("t"))],
                              [O.Delayed(dmg, [O.Kill(Ref("t"))], filt=it, expires="turn", once=True, label="Noxian Guillotine")])],
                        label=defn.name, source_text=defn.text)]


@script("Card Sharp")
def card_sharp(defn):
    # When you play me, you and each opponent may play a Gold gear token exhausted. For each opponent who did, you play a
    # Gold gear token exhausted.
    def gold(p):
        return lambda g, c: g.play_token(p(g, c), "Gold", ("base", p(g, c)), exhausted_gear=True, ctx=c)
    me = lambda g, c: c.controller
    opp = lambda g, c: g.opponent(c.controller)
    return [Triggered("play_self", [O.May([O.Do(gold(me), label="play a Gold")], label="play a Gold gear token exhausted"),
                                    O.May([O.Do(gold(opp), label="play a Gold"), O.Do(gold(me), label="they did: you play a Gold")],
                                          label="play a Gold gear token exhausted", player=opp)],
                      label=defn.name, source_text=defn.text)]


@script("Riposte")
def riposte(defn):
    # [Reaction]  Choose a friendly unit and a spell. Counter that spell and give that unit +[M] equal to that spell's
    # Energy cost this turn.
    spell = Sel("card", zone="chain", pred=lambda g, c, u: any(it.uid == u and it.kind == "spell" for it in g.chain))
    def counter(g, c):
        u = c.vars.get("__sp")
        it = next((x for x in g.chain if x.uid == u and x.kind == "spell"), None)
        c.vars["__spc"] = g.objects[u].base_defn().energy or 0 if u in g.objects else 0
        if it is not None:
            g.do_counter(it.id, c)
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Choose(spell, out="__sp"),
                         O.Do(counter, label="counter it"), O.GiveMight(Ref("t"), Ref("__spc"))], label=defn.name, source_text=defn.text)]


@script("Void Rush")
def void_rush(defn):
    # Reveal the top 2 cards of your Main Deck. You may play one of them, reducing its cost by [2]. Draw any you did not
    # play this way.
    cards = lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"]
    def cheaper(g, c):
        e, pw = g.card_cost(c.controller, c.vars["__vr"], "deck", None)
        return (max(0, e - 2), pw)
    def draw_rest(g, c):
        ps = g.players[c.controller]
        for u in [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"]:
            ps.deck.remove(u); ps.deck.insert(0, u)
            g.do_draw(c.controller, 1, c)
    return [SpellEffect([O.Look(2, out="looked", reveal=True),
                         O.ChooseFromList(cards, out="__vr", up_to=True, label="play one, [2] less"), O.Do(_unwrap("__vr")),
                         O.If(Ref("__vr"), [O.PlayCard(Ref("__vr"), alt_cost=cheaper)]),
                         O.Do(draw_rest, label="draw the rest")], label=defn.name, source_text=defn.text)]


# ---------------------------------------------------------------- batch 2026-11-06 16:10
@script("Deadly Flourish")
def deadly_flourish(defn):
    # Deal 3 to an enemy unit. When it dies this turn, play a Gold gear token exhausted.
    dies = lambda g, s, ev: ev.get("kind") == "die"
    it = lambda g, c, ev: ev.get("uid") == c.vars.get("t")
    return [SpellEffect([O.Choose(Sel("unit", side="enemy"), out="t"),
                         O.Delayed(dies, [O.PlayToken("Gold", loc="base", exhausted=True)], filt=it, expires="turn", once=True,
                                   label="Deadly Flourish: Gold"),
                         O.Deal(3, Ref("t"))], label=defn.name, source_text=defn.text)]


@script("Call to Battle")
def call_to_battle(defn):
    # Move a unit you control to a battlefield you control. Then, choose an opponent. They move a unit they control to
    # the same battlefield.
    mine = lambda g, c, l: g.battlefields[l[1]].controller == c.controller
    theirs = lambda g, c: [u for u, o in g.objects.items() if c.vars.get("loc") is not None and o.zone == "board"
                           and o.controller == c.vars.get("__opp") and "unit" in g.chars(u).types and o.location != c.vars["loc"]
                           and g.valid_destination(u, c.vars["loc"], mover=c.controller)]
    return [SpellEffect([O.Choose(Sel("unit", side="friendly", pred=lambda g, c, u: g.objects[u].controller == c.controller), out="t"),
                         O.ChooseLocation(out="loc", pred=mine, label="a battlefield you control"),
                         O.Move(Ref("t"), Ref("loc")),
                         O.ChoosePlayer(out="__opp", opponent=True),
                         O.ChooseFromList(theirs, out="__ct", player=Ref("__opp"), label="move a unit you control there"),
                         O.Move(Ref("__ct"), Ref("loc"))], label=defn.name, source_text=defn.text)]


@script("Disposal Order")
def disposal_order(defn):
    # [Reaction]  Choose one — Choose up to 3 cards from opponents' trashes. Their owners recycle them. / Draw 1.
    opp_trash = lambda g, c: [u for q in g.opponents(c.controller) for u in g.players[q].trash]
    return [SpellEffect([O.ChooseMode([
        ("recycle up to 3 cards from opponents' trashes",
         _pick_up_to(opp_trash, 3, "__dor", "choose a card from an opponent's trash (up to 3)") +
         [O.Recycle(lambda g, c: list(c.vars.get("__dor") or ()))]),
        ("draw 1", [O.Draw(1)])])], label=defn.name, source_text=defn.text)]


@script("Abandon")
def abandon(defn):
    # [Reaction]  Counter a spell. Return it to its owner's hand instead of putting it in their trash.  [Predict].
    spell = Sel("card", zone="chain", pred=lambda g, c, u: any(it.uid == u and it.kind == "spell" for it in g.chain))
    def counter(g, c):
        u = c.vars.get("__sp")
        it = next((x for x in g.chain if x.uid == u and x.kind == "spell"), None)
        if it is not None and g.do_counter(it.id, c) and g.objects[u].zone == "trash":
            g._to_zone(g.objects[u], "hand"); g.bump()
    return [SpellEffect([O.Choose(spell, out="__sp"), O.Do(counter, label="counter it, to its owner's hand"), O.Predict(1)],
                        label=defn.name, source_text=defn.text)]


@script("Insightful Investigator")
def insightful_investigator(defn):
    # When you play me, choose an opponent. They reveal their hand. You may pay 2 XP to choose a card from their hand. If
    # you do, they discard that card and draw 1.
    def reveal(g, c):
        q = c.vars["__opp"]
        if g.players[q].hand:
            g.emit("reveal", cards=tuple(g.players[q].hand), player=q, ctx=c)
    can = lambda g, c: g.players[c.controller].xp >= 2 and bool(g.players[c.vars["__opp"]].hand)
    def pay_xp(g, c):
        g.players[c.controller].xp -= 2; g.bump()
    hand = lambda g, c: list(g.players[c.vars["__opp"]].hand)
    def discard(g, c):
        q, u = c.vars["__opp"], c.vars.get("__ii")
        if u is not None:
            g.do_discard(q, [u], c); g.do_draw(q, 1, c)
    return [Triggered("play_self", [O.ChoosePlayer(out="__opp", opponent=True), O.Do(reveal, label="they reveal their hand"),
                                    O.If(can, [O.May([O.Do(pay_xp, label="pay 2 XP"),
                                                      O.ChooseFromList(hand, out="__ii", label="they discard it and draw 1"),
                                                      O.Do(discard, label="discard, draw 1")], label="pay 2 XP to choose a card")])],
                      label=defn.name, source_text=defn.text)]


@script("Suave Negotiator")
def suave_negotiator(defn):
    # When you play me, choose an opponent. You and that player each draw 1.
    return [Triggered("play_self", [O.ChoosePlayer(out="__opp", opponent=True), O.Draw(1), O.Draw(1, player=Ref("__opp"))],
                      label=defn.name, source_text=defn.text)]


@script("Siren's Song")
def sirens_song(defn):
    # [Reaction]  Move an enemy unit that moved this turn.
    moved = Sel("unit", side="enemy", pred=lambda g, c, u: g.objects[u].temp.get(("moved", g.turn)))
    dests = lambda g, c, l: l != g.objects[c.vars["t"]].location and g.valid_destination(c.vars["t"], l, mover=c.controller)
    return [SpellEffect([O.Choose(moved, out="t"), O.ChooseLocation(out="loc", pred=dests, include_bases=True, label="move it where?"),
                         O.Move(Ref("t"), Ref("loc"))], label=defn.name, source_text=defn.text)]


@script("Explosimian")
def explosimian(defn):
    # When I hold, play three Bomb gear tokens to a single battlefield.
    return [Triggered("hold_self",
                      [O.ChooseLocation(out="loc"), O.PlayToken("Bomb", loc=Ref("loc"), count=3)],
                      label=defn.name, source_text=defn.text)]


@script("Elder Dragon")
def elder_dragon(defn):
    # Any amount of your damage is enough to kill enemy units.  When you play me, choose up to one enemy unit at each
    # location. Deal 1 to them.
    def pick_code():
        return [O.Do(lambda g, c: c.vars.__setitem__("__ed", []), label="choose up to one enemy unit at each location")]
    def locs(g, c):
        return sorted({g.objects[u].location for u, o in g.objects.items() if o.zone == "board" and "unit" in g.chars(u).types
                       and _enemy(g, c, u)}, key=str)
    code = pick_code()
    for i in range(8):        # at most one pick per location (bases and battlefields)
        at = lambda g, c, i=i: [u for u in g.objects if g.objects[u].zone == "board" and "unit" in g.chars(u).types and _enemy(g, c, u)
                                and g.objects[u].location == (locs(g, c)[i] if i < len(locs(g, c)) else None)]
        code += [O.ChooseFromList(at, out=f"__ed{i}", up_to=True, label="deal 1 to an enemy unit here"),
                 O.Do(lambda g, c, i=i: c.vars["__ed"].extend(c.vars.get(f"__ed{i}") or ()), label="")]
    code += [O.Deal(1, lambda g, c: list(c.vars["__ed"]))]
    return [Static("self", "rule", ("any_damage_kills_enemies",), source_text=defn.text),
            Triggered("play_self", code, label=defn.name, source_text=defn.text)]


# ---------------------------------------------------------------- batch 2026-11-06 16:20 (Radiance)
@script("One-Two Punch")
def one_two_punch(defn):
    # [Action]  [Buff] a friendly unit and [Stun] an enemy unit.
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Choose(Sel("unit", side="enemy"), out="t2"),
                         O.Buff(Ref("t")), O.Stun(Ref("t2"))], label=defn.name, source_text=defn.text)]


@script("Raucous Anthem")
def raucous_anthem(defn):
    # Ready your units and give them +3 [M] this turn.
    mine = lambda g, c: [u for u, o in g.objects.items() if o.zone == "board" and o.controller == c.controller and "unit" in g.chars(u).types]
    return [SpellEffect([O.Ready(mine), O.GiveMight(mine, 3)], label=defn.name, source_text=defn.text)]


@script("Steadfast Outrider")
def steadfast_outrider(defn):
    # [Tank]  While there are 2 or more other friendly units and/or gear at my battlefield, I have +2 [M].
    def cond(g, s):
        o = g.objects[s]
        if o.location is None or o.location[0] != "bf":
            return False
        n = sum(1 for u, x in g.objects.items() if u != s and x.zone == "board" and x.location == o.location
                and g.is_friendly(x.controller, o.controller) and x.defn.type != "rune"
                and ("unit" in x.defn.types or "gear" in x.defn.types))
        return n >= 2
    return [Static("self", "might", 2, cond=cond, label="+2 [M] with 2+ other friendly units/gear here", source_text=defn.text)]


@script("Cosmic Vista")
def cosmic_vista(defn):
    # When you hold here, if your Rune Deck is empty, you score 1 point.
    empty = lambda g, c: not g.players[c.controller].rune_deck
    return [Triggered("you_hold_here", [O.GainPoints(1)], intervening=empty, controller="event", label=defn.name, source_text=defn.text)]


@script("Ntofo Strikes")
def ntofo_strikes(defn):
    # [Action]  Give a friendly unit [Shield 2] this turn, then deal damage equal to its [Shield] to an enemy unit.
    def shield(g, c):
        g.add_mod(c.vars["t"], "keyword", ("shield", 2), duration="turn", source=c.source)
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Choose(Sel("unit", side="enemy"), out="t2"),
                         O.Do(shield, label="[Shield 2] this turn"),
                         O.Deal(lambda g, c: g.chars(c.vars["t"]).kw("shield") if c.vars.get("t") in g.objects else 0, Ref("t2"))],
                        label=defn.name, source_text=defn.text)]


@script("Armored Tusker")
def armored_tusker(defn):
    # [Shield 3]  [Tank]  When I move, you may deal damage equal to my [Shield] to a unit at a battlefield.
    return [Triggered("move_self", [O.May([O.ChooseFromList(lambda g, c: [u for u, o in g.objects.items() if o.zone == "board"
                                                                         and "unit" in g.chars(u).types and o.location and o.location[0] == "bf"],
                                                            out="__at", label="deal damage equal to my [Shield]"),
                                           O.Deal(lambda g, c: g.chars(c.source).kw("shield"), Ref("__at"))],
                                          label="deal damage equal to my [Shield] to a unit at a battlefield")],
                      label=defn.name, source_text=defn.text)]


@script("Party Crasher")
def party_crasher(defn):
    # I cost [1] less for each exhausted unit you control.  [Tank]
    def reduce(g, u, e, p):
        q = _ctrl(g, u)
        n = sum(1 for x, o in g.objects.items() if o.zone == "board" and o.controller == q and o.exhausted and "unit" in g.chars(x).types)
        return (max(0, e - n), p)
    return [PlayPermission("cost", cost_mod=reduce, label="[1] less per exhausted unit you control", source_text=defn.text)]


@script("Bloodscent Swarm")
def bloodscent_swarm(defn):
    # I cost [2] less for each battlefield you've conquered this turn.
    def reduce(g, u, e, p):
        n = len(g.turn_memo.get(("conquered_bfs", _ctrl(g, u)), ()))
        return (max(0, e - 2 * n), p)
    return [PlayPermission("cost", cost_mod=reduce, label="[2] less per battlefield you conquered this turn", source_text=defn.text)]


@script("Titanic Shrine")
def titanic_shrine(defn):
    # When you play a unit with Might greater than each other unit on the board, exhaust me to draw 1.
    def big(g, s, ev):
        if ev.get("kind") != "play" or ev.get("card_type") != "unit" or ev.get("player") != g.objects[s].controller:
            return False
        u = ev.get("uid")
        if u not in g.objects or g.objects[u].zone != "board" or g.objects[s].exhausted:
            return False
        m = g.chars(u).might or 0
        return all((g.chars(x).might or 0) < m for x, o in g.objects.items() if x != u and o.zone == "board" and "unit" in g.chars(x).types)
    # "exhaust me to draw 1": exhausting is the base cost, paid as the trigger is finalized (CR 383.3.b)
    from ..targeting import TriggerBaseCost
    ready = lambda g, c: g.objects[c.source].zone == "board" and not g.objects[c.source].exhausted
    return [Triggered(big, [O.Draw(1)], targets=[TriggerBaseCost(ready), O.Exhaust(Ref("self"))],
                      label=defn.name, source_text=defn.text)]


@script("Forbidden Technique")
def forbidden_technique(defn):
    # Ready a unit.  When you play a card with Energy cost [7] or more, you may play this from your trash for
    # [1][Fury][Fury]. Banish this.
    def big(g, s, ev):
        if ev.get("kind") != "play" or ev.get("token") or ev.get("player") != g.objects[s].owner or ev.get("uid") == s:
            return False
        o = g.objects.get(ev.get("uid"))
        return o is not None and (o.base_defn().energy or 0) >= 7
    # "Banish this." is printed in the trash paragraph: read as "if played from your trash this way, banish it as it
    # resolves" (otherwise the trash ability could only ever be used after a discard).
    from_trash = lambda g, c: getattr(c, "played_from", None) == "trash"
    return [SpellEffect([O.Choose(Sel("unit"), out="t"), O.Ready(Ref("t")), O.If(from_trash, [O.Banish(Ref("self"))])],
                        label=defn.name, source_text=defn.text),
            Triggered(big, [O.May([O.PlayCard(Ref("self"), alt_cost=(1, ["fury", "fury"]))], label="play this from your trash for [1][Fury][Fury]")],
                      zone="trash", label="play from trash", source_text=defn.text)]


@script("Remember the Fallen")
def remember_the_fallen(defn):
    # Play up to 3 units and/or gear from your trash, each with Energy cost no more than [3] and Power cost no more than
    # [A], ignoring their costs.
    def ok(g, c):
        out = []
        for u in g.players[c.controller].trash:
            d = g.objects[u].base_defn()
            if (d.is_unit or d.is_gear) and (d.energy or 0) <= 3 and (d.power or 0) <= 1:
                out.append(u)
        return out
    code = _pick_up_to(ok, 3, "__rf", "play a unit or gear from your trash (up to 3)")
    for i in range(3):
        code.append(O.If(lambda g, c, i=i: len(c.vars.get("__rf") or ()) > i,
                         [O.PlayCard(lambda g, c, i=i: c.vars["__rf"][i], ignore="all")]))
    return [SpellEffect(code, label=defn.name, source_text=defn.text)]


# ---------------------------------------------------------------- batch 2026-11-06 16:30
@script("Primordial Roar")
def primordial_roar(defn):
    # [Show Off] a unit.  If you showed off a unit, deal damage equal to that unit's Might to a unit.
    shown = lambda g, c: bool(getattr(c, "shown_off", None))
    return [SpellEffect([O.Choose(Sel("unit"), out="t"),
                         O.If(shown, [O.Deal(lambda g, c: c.shown_off["might"], Ref("t"))])], label=defn.name, source_text=defn.text)]


@script("Rousing Display")
def rousing_display(defn):
    # [Show Off] a card with Energy cost [7] or more.  Play two 1 [M] Recruit unit tokens to your base. If you showed
    # off, play four to your base instead.
    n = lambda g, c: 4 if getattr(c, "shown_off", None) else 2
    return [SpellEffect([O.PlayToken("Recruit", loc="base", count=n)], label=defn.name, source_text=defn.text)]


@script("Black Rose Sanctum")
def black_rose_sanctum(defn):
    # For each player, the first time each turn a non-token unit they control dies here, they play a 1 [M] Recruit unit
    # token to their base.
    def dies(g, s, ev):
        if ev.get("kind") != "die" or ev.get("card_type") != "unit" or ev.get("token") or ev.get("loc") != g.objects[s].place:
            return False
        key = ("black_rose", s, ev.get("player"))
        if g.turn_memo.get(key):
            return False
        g.turn_memo[key] = True
        return True
    return [Triggered(dies, [O.PlayToken("Recruit", loc="base")], controller="event", label=defn.name, source_text=defn.text)]


@script("Durand Memorial")
def durand_memorial(defn):
    # When you defend here, choose a unit you control here. Give it [Tank] this combat.
    def defend(g, s, ev):
        if ev.get("kind") != "defend" or ev.get("loc") != g.objects[s].place or ev.get("player") != g.objects[s].controller:
            return False
        key = ("durand", s, id(g.combat))
        if g.turn_memo.get(key):
            return False
        g.turn_memo[key] = True
        return True
    here = lambda g, c: [u for u in g.units_at(g.objects[c.source].place) if g.objects[u].controller == c.controller]
    return [Triggered(defend, [O.ChooseFromList(here, out="__dm", label="give it [Tank] this combat"),
                               O.Do(lambda g, c: g.add_mod(c.vars["__dm"], "keyword", ("tank", True), duration="combat", source=c.source)
                                    if c.vars.get("__dm") is not None else None, label="[Tank] this combat")],
                      label=defn.name, source_text=defn.text)]


@script("Angler Wyrm")
def angler_wyrm(defn):
    # [Deflect]  [T]: Choose an opponent. They must move a unit they control to my battlefield.
    from ..abilities import Activated
    def theirs(g, c):
        loc = g.objects[c.source].location
        return [u for u, o in g.objects.items() if o.zone == "board" and o.controller == c.vars.get("__opp") and "unit" in g.chars(u).types
                and o.location != loc and g.valid_destination(u, loc, mover=c.vars.get("__opp"))]
    at_bf = lambda g, c: g.objects[c.source].location is not None and g.objects[c.source].location[0] == "bf"
    return [Activated({"energy": 0, "power": [], "exhaust": True},
                      [O.ChoosePlayer(out="__opp", opponent=True),
                       O.If(at_bf, [O.ChooseFromList(theirs, out="__aw", player=Ref("__opp"), label="move a unit to that battlefield"),
                                    O.Move(Ref("__aw"), lambda g, c: g.objects[c.source].location)])],
                      timing="main", label=defn.name, source_text=defn.text)]


@script("Cataclysm")
def cataclysm(defn):
    # Opponents can't play spells this turn.  Move a friendly unit to an occupied enemy battlefield.
    occ = lambda g, c, l: g.battlefields[l[1]].controller is not None and not g.is_friendly(g.battlefields[l[1]].controller, c.controller) \
        and bool(g.units_at(l)) and g.valid_destination(c.vars["t"], l, mover=c.controller)
    return [SpellEffect([O.Do(lambda g, c: g.add_turn_effect(c, "cant_play_spells", {"players": tuple(g.opponents(c.controller))}),
                              label="opponents can't play spells this turn"),
                         O.Choose(Sel("unit", side="friendly"), out="t"),
                         O.ChooseLocation(out="loc", pred=occ, label="an occupied enemy battlefield"),
                         O.Move(Ref("t"), Ref("loc"))], label=defn.name, source_text=defn.text)]


@script("Mechanical Bandit")
def mechanical_bandit(defn):
    # At the start of your Beginning Phase, each player reveals the top card of their Main Deck. If you revealed a card
    # with the lowest Energy cost, draw it. Recycle the rest.
    def top_cards(g, c):
        c.vars["__mb"] = [g.players[q].deck[0] for q in range(len(g.players)) if g.players[q].deck]

    def run(g, c):
        # a Nocturne, Horrifying banished as he was revealed is not revealed (CR 370: the event was replaced)
        tops = {g.objects[u].owner: u for u in c.vars.get("__mb", []) if g.objects[u].zone == "deck"}
        if not tops:
            return
        for q, u in tops.items():
            g.emit("reveal", cards=(u,), player=q, ctx=c)
        low = min(g.objects[u].base_defn().energy or 0 for u in tops.values())
        me = c.controller
        rest = [u for q, u in tops.items() if q != me]
        if me in tops:
            if (g.objects[tops[me]].base_defn().energy or 0) == low:
                g.do_draw(me, 1, c)
            else:
                rest.append(tops[me])
        g.do_recycle(rest, c)
    return [Triggered("start_beginning", [O.Do(top_cards), O.SeeFromDeck(Ref("__mb")), O.Do(run, label="reveal top cards")],
                      label=defn.name, source_text=defn.text)]


# ---------------------------------------------------------------- batch 2026-11-06 16:40
@script("Seraphic Wyvern")
def seraphic_wyvern(defn):
    # If you would channel runes, channel that many runes plus 1 exhausted rune instead.
    return [Static("self", "rule", ("channel_plus_one",), source_text=defn.text)]


@script("The Waters' Wage")
def the_waters_wage(defn):
    # [Hidden]  Play a Gold gear token exhausted. If it's your turn and you played this from face down, play three ready
    # Gold gear tokens instead.
    big = lambda g, c: g.turn_player == c.controller and getattr(c, "played_from", None) == "facedown"
    return [SpellEffect([O.If(big, [O.PlayToken("Gold", loc="base", count=3)], [O.PlayToken("Gold", loc="base", exhausted=True)])],
                        label=defn.name, source_text=defn.text)]


@script("Piltovan Guidebot")
def piltovan_guidebot(defn):
    # When you play a card, you may have my base Might become equal to that card's Energy cost this turn.
    def setm(g, c):
        o = g.objects.get(c.event.get("uid"))
        if o is not None:
            g.add_mod(c.source, "base_might", o.base_defn().energy or 0, duration="turn", source=c.source)
    return [Triggered("you_play_card", [O.May([O.Do(setm, label="base Might = its Energy cost")],
                                              label="make my base Might equal that card's Energy cost this turn")],
                      label=defn.name, source_text=defn.text)]


@script("Demon Shade")
def demon_shade(defn):
    # [Hidden]  Choose a friendly unit, then choose one — Move it to an open battlefield. / Give it [Ganking] this turn
    # if there are no open battlefields.
    def opens(g, c):
        return [("bf", b.idx) for b in g.battlefields if b.controller is None and not g.units_at(("bf", b.idx))]
    no_open = lambda g, c: not opens(g, c)
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"),
                         O.ChooseMode([("move it to an open battlefield",
                                        [O.ChooseLocation(out="loc", pred=lambda g, c, l: l in opens(g, c) and g.valid_destination(c.vars["t"], l, mover=c.controller)),
                                         O.Move(Ref("t"), Ref("loc"))]),
                                       ("give it [Ganking] this turn if there are no open battlefields",
                                        [O.If(no_open, [O.Do(lambda g, c: g.add_mod(c.vars["t"], "keyword", ("ganking", True), duration="turn",
                                                                                    source=c.source), label="[Ganking] this turn")])])])],
                        label=defn.name, source_text=defn.text)]


@script("Hexplosive Minefield")
def hexplosive_minefield(defn):
    # [Action]  Kill any number of friendly Bomb tokens. At end of turn, play that many Bomb tokens to a single battlefield.
    bombs = lambda g, c: [u for u, o in g.objects.items() if o.zone == "board" and g.is_friendly(o.controller, c.controller)
                          and o.defn.is_token and o.defn.name == "Bomb"]
    def kill(g, c):
        us = list(c.vars.get("__hb") or ())
        c.vars["__hbn"] = len(us)
        if us:
            g.do_kill(us, c)
    end = lambda g, s, ev: ev.get("kind") == "ending_phase"
    return [SpellEffect(_pick_up_to(bombs, 12, "__hb", "kill a friendly Bomb token (any number)") +
                        [O.Do(kill, label="kill them"),
                         O.If(lambda g, c: c.vars.get("__hbn"), [
                             O.Delayed(end, [O.ChooseLocation(out="loc"), O.PlayToken("Bomb", loc=Ref("loc"), count=Ref("__hbn"))],
                                       expires="turn", once=True, label="Hexplosive Minefield: Bombs")])],
                        label=defn.name, source_text=defn.text)]


@script("Transpositionist")
def transpositionist(defn):
    # [Chaos], [T]: Return a friendly unit to its owner's hand. You may play a unit with less Might than that unit had,
    # ignoring its cost.
    from ..abilities import Activated
    def ret(g, c):
        u = c.vars.get("t")
        if u is None:
            return
        c.vars["__tm"] = g.chars(u).might or 0
        g.put_in_hand(u, c) if hasattr(g, "put_in_hand") else g._to_zone(g.objects[u], "hand")
    smaller = lambda g, c: [u for u in g.players[c.controller].hand if g.objects[u].base_defn().is_unit
                            and (g.objects[u].base_defn().might or 0) < c.vars.get("__tm", 0)]   # the returned card too
    return [Activated({"energy": 0, "power": ["chaos"], "exhaust": True},
                      [O.Choose(Sel("unit", side="friendly"), out="t"), O.Do(ret, label="return it to its owner's hand"),
                       O.ChooseFromList(smaller, out="__tp", up_to=True, label="play a unit with less Might, ignoring its cost"),
                       O.Do(_unwrap("__tp")), O.If(Ref("__tp"), [O.PlayCard(Ref("__tp"), ignore="all")])],
                      timing="main", label=defn.name, source_text=defn.text)]


@script("Bottled Constellation")
def bottled_constellation(defn):
    # At the start of your Main Phase, you may kill 3 other friendly units and/or gear to score 1 point.
    others = lambda g, c: [u for u, o in g.objects.items() if u != c.source and o.zone == "board" and o.controller == c.controller
                           and o.defn.type != "rune" and ("unit" in g.chars(u).types or "gear" in g.chars(u).types)]
    def pay(g, c):
        us = list(c.vars.get("__bc") or ())
        if len(us) == 3:
            g.do_kill(us, c)
            g.gain_points(c.controller, 1, "effect", c)
    return [Triggered("start_main", [O.If(lambda g, c: len(others(g, c)) >= 3, [
        O.May(_pick_up_to(others, 3, "__bc", "kill 3 other friendly units and/or gear") + [O.Do(pay, label="kill 3, score 1")],
              label="kill 3 other friendly units and/or gear to score 1 point")])], label=defn.name, source_text=defn.text)]


@script("Forgotten Relic")
def forgotten_relic(defn):
    # When you play this or at the start of your Beginning Phase, [Burn 1]. When you burn a unit this way, do this: Give a
    # friendly unit +[M] equal to the burned card's Might this turn.
    def burn(g, c):
        ps = g.players[c.controller]
        top = ps.deck[0] if ps.deck else None
        g.do_burn(c.controller, 1, c)
        c.vars["__fr"] = (g.objects[top].base_defn().might or 0) if top is not None and g.objects[top].base_defn().is_unit \
            and g.objects[top].zone == "trash" else None
    pump = [O.Choose(Sel("unit", side="friendly"), out="t"), O.GiveMight(Ref("t"), Ref("__fr"))]
    body = [O.Do(burn, label="[Burn 1]"), O.If(lambda g, c: c.vars.get("__fr") is not None, [O.Reflexive(pump, label="burned a unit")])]
    return [Triggered("play_self", body, label=defn.name, source_text=defn.text),
            Triggered("start_beginning", list(body), label=defn.name + " (Beginning Phase)", source_text=defn.text)]


# ---------------------------------------------------------------- batch 2026-11-06 16:50 (Origins / Spiritforged)
@script("Bushwhack")
def bushwhack(defn):
    # [Hidden]  Friendly units enter ready this turn. Play a Gold gear token exhausted.
    return [SpellEffect([O.DelayedPassive("enter_ready", {}), O.PlayToken("Gold", loc="base", exhausted=True)],
                        label=defn.name, source_text=defn.text)]


@script("Flame Chompers")
def flame_chompers(defn):
    # When you discard me, you may pay [Fury] to play me.
    return [Triggered("discard_self", [O.May([O.PlayCard(Ref("self"), alt_cost=(0, ["fury"]))], label="pay [Fury] to play me")],
                      zone="trash", label=defn.name, source_text=defn.text)]


def _units_on_board(g):
    return [u for u, o in g.objects.items() if o.zone == "board" and "unit" in g.chars(u).types]


@script("Whirlwind")
def whirlwind(defn):
    # Starting with the next player, each player may return a unit to its owner's hand.
    def one(who):
        return [O.ChooseFromList(lambda g, c: _units_on_board(g), out=f"__ww{who}", up_to=True, player=lambda g, c: (c.controller + who) % len(g.players),
                                 label="you may return a unit to its owner's hand"),
                O.Do(_unwrap(f"__ww{who}")),
                O.If(Ref(f"__ww{who}"), [O.Do(lambda g, c, who=who: g.put_in_hand(c.vars[f"__ww{who}"], c), label="return it")])]
    return [SpellEffect(one(1) + one(0), label=defn.name, source_text=defn.text)]


@script("Party Favors")
def party_favors(defn):
    # Each other player chooses Cards or Runes. For each player that chooses Cards, you and that player each draw 1. For
    # each player that chooses Runes, you and that player each channel 1 rune exhausted.
    opp = lambda g, c: g.opponent(c.controller)
    return [SpellEffect([O.ChooseMode([("Cards", [O.Draw(1), O.Draw(1, player=opp)]),
                                       ("Runes", [O.Channel(1, exhausted=True), O.Channel(1, exhausted=True, player=opp)])],
                                      player=opp)], label=defn.name, source_text=defn.text)]


@script("King's Edict")
def kings_edict(defn):
    # Starting with the next player, each other player chooses a unit you don't control that hasn't been chosen for this
    # spell. Kill those units.
    pool = lambda g, c: [u for u in _units_on_board(g) if g.objects[u].controller != c.controller]
    return [SpellEffect([O.ChooseFromList(pool, out="__ke", player=lambda g, c: g.opponent(c.controller),
                                          label="choose a unit the caster doesn't control"),
                         O.Kill(Ref("__ke"))], label=defn.name, source_text=defn.text)]


@script("Blind Fury")
def blind_fury(defn):
    # [Action]  Each opponent reveals the top card of their Main Deck. Choose one and banish it, then play it, ignoring
    # its cost. Then recycle the rest.
    def tops(g, c):
        c.vars["__bf"] = [g.players[q].deck[0] for q in g.opponents(c.controller) if g.players[q].deck]

    def reveal(g, c):
        c.vars["__bf"] = [u for u in c.vars["__bf"] if g.objects[u].zone == "deck"]     # minus a banished Nocturne
        for u in c.vars["__bf"]:
            g.emit("reveal", cards=(u,), player=g.objects[u].owner, ctx=c)
    rest = lambda g, c: [u for u in c.vars.get("__bf", []) if u != c.vars.get("__bfp") and g.objects[u].zone == "deck"]
    return [SpellEffect([O.Do(tops), O.SeeFromDeck(Ref("__bf")), O.Do(reveal, label="opponents reveal their top card"),
                         O.ChooseFromList(lambda g, c: c.vars.get("__bf", []), out="__bfp", label="banish it, then play it"),
                         O.If(Ref("__bfp"), [O.Banish(Ref("__bfp")), O.PlayCard(Ref("__bfp"), ignore="all")]),
                         O.Recycle(rest)], label=defn.name, source_text=defn.text)]


@script("Fox-Fire, Ahri")
def fox_fire(defn):
    # [Hidden]  [Action]  Kill any number of units at a battlefield with total Might 4 or less.
    def opts(g, c):
        loc = c.vars.get("loc")
        used = sum(g.chars(u).might or 0 for u in c.vars.get("__ff", []))
        return [u for u in g.units_at(loc) if (g.chars(u).might or 0) + used <= 4] if loc else []
    return [SpellEffect([O.ChooseLocation(out="loc")] + _pick_up_to(opts, 8, "__ff", "kill a unit there (total Might 4 or less)") +
                        [O.Kill(lambda g, c: list(c.vars.get("__ff") or ()))], label=defn.name, source_text=defn.text)]


@script("Stand United")
def stand_united(defn):
    # [Hidden]  [Action]  Buff a friendly unit. Buffs give an additional +1 [M] to friendly units this turn.
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Buff(Ref("t")),
                         O.Do(lambda g, c: (g.add_turn_effect(c, "buff_bonus", {}), g.bump()), label="buffs give +1 more this turn")],
                        label=defn.name, source_text=defn.text)]


@script("Spirit's Refuge")
def spirits_refuge(defn):
    # When you play this, buff a friendly unit.  Friendly buffed units have [Deflect] if they didn't already.
    return [Triggered("play_self", [O.Choose(Sel("unit", side="friendly"), out="t"), O.Buff(Ref("t"))], label=defn.name, source_text=defn.text),
            Static(Sel("unit", side="friendly", buffed=True), "keyword", ("deflect", True), label="buffed units have [Deflect]",
                   source_text=defn.text)]


@script("Symbol of the Solari")
def symbol_of_the_solari(defn):
    # If a combat where you are the attacker ends in a tie, recall ALL units instead.
    return [Static("self", "rule", ("attacker_tie_recall_all",), source_text=defn.text)]


# ---------------------------------------------------------------- batch 2026-11-06 17:00
@script("Counter Strike")
def counter_strike(defn):
    # [Reaction]  Choose a unit. The next time that unit would be dealt damage this turn, prevent it. Draw 1.
    return [SpellEffect([O.Choose(Sel("unit"), out="t"),
                         O.Do(lambda g, c: g.add_mod(c.vars["t"], "prevent_next", True, duration="turn", source=c.source)
                              if c.vars.get("t") is not None else None, label="prevent the next damage this turn"),
                         O.Draw(1)], label=defn.name, source_text=defn.text)]


@script("Lotus Trap")
def lotus_trap(defn):
    # [Hidden]  [Reaction]  Choose a unit. Double all damage that would be dealt to it this turn.
    return [SpellEffect([O.Choose(Sel("unit"), out="t"),
                         O.Do(lambda g, c: g.add_mod(c.vars["t"], "double_damage", True, duration="turn", source=c.source)
                              if c.vars.get("t") is not None else None, label="double damage to it this turn")],
                        label=defn.name, source_text=defn.text)]


@script("Arcane Shift")
def arcane_shift(defn):
    # [Action]  Banish a friendly unit, then its owner plays it, ignoring its cost. Deal 3 to an enemy unit at a
    # battlefield. Banish this.
    owner = lambda g, c: g.objects[c.vars["t"]].owner
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Choose(Sel("unit", side="enemy", where="battlefield"), out="t2"),
                         O.Banish(Ref("t")),
                         O.If(lambda g, c: c.vars.get("t") in g.objects and g.objects[c.vars["t"]].zone == "banish",
                              [O.PlayCard(Ref("t"), ignore="all", player=owner)]),
                         O.Deal(3, Ref("t2")),
                         O.Do(lambda g, c: c.vars.__setitem__("__banish_after", True), label="banish this")],
                        label=defn.name, source_text=defn.text)]


@script("Hostile Takeover")
def hostile_takeover(defn):
    # [Hidden]  Take control of an enemy unit at a battlefield. Ready it.  Lose control of that unit and recall it at end
    # of turn.
    end = lambda g, s, ev: ev.get("kind") == "ending_phase"
    return [SpellEffect([O.Choose(Sel("unit", side="enemy", where="battlefield"), out="t"), O.TakeControl(Ref("t"), duration="turn"),
                         O.Ready(Ref("t")),
                         O.Delayed(end, [O.Do(lambda g, c: g.do_recall(c.vars["t"], c) if g.objects[c.vars["t"]].zone == "board" else None,
                                              label="recall it")], expires="turn", once=True, label="Hostile Takeover: recall")],
                        label=defn.name, source_text=defn.text)]


@script("Flurry of Feathers")
def flurry_of_feathers(defn):
    # [Reaction]  Choose one — Counter a spell. / Play four 1 [M] Bird unit tokens with [Deflect].
    spell = lambda g, c: [it.uid for it in g.chain if it.kind == "spell" and it.uid != c.source]
    def counter(g, c):
        it = next((x for x in g.chain if x.uid == c.vars.get("__ff") and x.kind == "spell"), None)
        if it is not None:
            g.do_counter(it.id, c)
    return [SpellEffect([O.ChooseMode([("counter a spell", [O.ChooseFromList(spell, out="__ff", label="counter a spell"),
                                                            O.Do(counter, label="counter it")]),
                                       ("play four Bird tokens", [O.PlayToken("Bird", loc="base", count=4)])])],
                        label=defn.name, source_text=defn.text)]


@script("Ripper's Bay")
def rippers_bay(defn):
    # When a unit here is returned to a player's hand, that player may pay [1] to channel 1 rune exhausted.
    def returned(g, s, ev):
        return ev.get("kind") == "to_hand" and ev.get("from_zone") == "board" and ev.get("loc") == g.objects[s].place
    return [Triggered(returned, [O.PayResources(1, out="__rb"), O.If(Ref("__rb"), [O.Channel(1, exhausted=True)])],
                      controller="event", label=defn.name, source_text=defn.text)]


@script("Altar of Memories")
def altar_of_memories(defn):
    # When a friendly unit dies, you may exhaust me to draw 1, then put a card from your hand on the top or bottom of
    # your Main Deck.
    hand = lambda g, c: list(g.players[c.controller].hand)
    def put_back(g, c):
        u = c.vars.get("__am")
        if u is None:
            return
        ps = g.players[c.controller]
        g._to_zone(g.objects[u], "deck", top=c.vars.get("__amw") == 0); g.bump()
    return [Triggered("friendly_unit_dies", [O.If(lambda g, c: not g.objects[c.source].exhausted, [
        O.May([O.Exhaust(Ref("self")), O.Draw(1),
               O.ChooseFromList(hand, out="__am", label="put a card from your hand on top or bottom of your deck"),
               O.ChooseMode([("top", []), ("bottom", [])], out="__amw"),
               O.Do(put_back, label="put it back")], label="exhaust me to draw 1")])], label=defn.name, source_text=defn.text)]


@script("Shadow Watcher")
def shadow_watcher(defn):
    # If a friendly unit died during your Beginning Phase this turn, I enter ready.
    return [_enter_ready_if(defn, lambda g, u: bool(g.turn_memo.get(("died_in_beginning", _ctrl(g, u)))) and g.turn_player == _ctrl(g, u),
                            "a friendly unit died during your Beginning Phase")]


@script("Marching Orders")
def marching_orders(defn):
    # [Action]  [Repeat] [3]  Choose a friendly unit anywhere and an enemy unit at a battlefield. They deal damage equal
    # to their Mights to each other.
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Choose(Sel("unit", side="enemy", where="battlefield"), out="t2"),
                         O.Do(lambda g, c: _fight(g, c, c.vars.get("t"), c.vars.get("t2")) if c.vars.get("t") and c.vars.get("t2") else None,
                              label="they deal damage to each other")], label=defn.name, source_text=defn.text)]


@script("Temptation")
def temptation(defn):
    # [Repeat] [2]  Move an enemy unit to a location where there's a unit with the same controller.
    def dests(g, c, l):
        u = c.vars.get("t")
        o = g.objects[u]
        return l != o.location and any(g.objects[x].controller == o.controller for x in g.units_at(l)) and g.valid_destination(u, l, mover=c.controller)
    return [SpellEffect([O.Choose(Sel("unit", side="enemy"), out="t"),
                         O.ChooseLocation(out="loc", pred=dests, include_bases=True, label="where one of its controller's units is"),
                         O.Move(Ref("t"), Ref("loc"))], label=defn.name, source_text=defn.text)]


@script("Fae Porter")
def fae_porter(defn):
    # When I move to a battlefield, you may pay [Chaos] to move a unit you control to the same battlefield.
    to_bf = lambda g, s, ev: ev.get("kind") == "move" and ev.get("uid") == s and ev.get("to") and ev["to"][0] == "bf"
    others = lambda g, c: [u for u, o in g.objects.items() if o.zone == "board" and o.controller == c.controller and u != c.source
                           and "unit" in g.chars(u).types and o.location != g.objects[c.source].location
                           and g.valid_destination(u, g.objects[c.source].location, mover=c.controller)]
    return [Triggered(to_bf, [O.PayResources(0, ["chaos"], out="__fp"),
                              O.If(Ref("__fp"), [O.ChooseFromList(others, out="__fpu", label="move a unit you control here"),
                                                 O.Move(Ref("__fpu"), lambda g, c: g.objects[c.source].location)])],
                      label=defn.name, source_text=defn.text)]


# ---------------------------------------------------------------- batch 2026-11-06 17:30 (equipment effect text)
@script("Jagged Cutlass")
def jagged_cutlass(defn):
    # [Equip] [Body]   effect: I can't be moved by enemy spells and abilities.   (+2 [M] from the card's Might bonus)
    return {"abilities": [], "effect_abilities": [Static("attached", "keyword", ("unmovable_by_enemies", True),
                                                         label="can't be moved by enemy spells and abilities")],
            "replace": False}


@script("Blighted Battleaxe")
def blighted_battleaxe(defn):
    # [Equip] [1][Fury]   effect: At the end of your turn, if I didn't conquer this turn, unattach this and deal 4 to me.
    def run(g, c):
        gear = c.source
        u = g.objects[gear].attached_to
        if u is None or g.objects[u].zone != "board" or g.objects[u].temp.get(("conquered", g.turn)):
            return
        g.do_detach(gear, c)
        g.do_deal([u], 4, c, source_uid=gear)
    return {"abilities": [], "effect_abilities": [Triggered("end_turn", [O.Do(run, label="unattach and deal 4 unless it conquered")],
                                                            label=defn.name, source_text=defn.effect_text)],
            "replace": False}


@script("Perched Grimwyrm")
def perched_grimwyrm(defn):
    # Play me only to a battlefield you conquered this turn.
    ok = lambda g, p, loc: loc[0] == "bf" and loc[1] in g.turn_memo.get(("conquered_bfs", p), set())
    return [PlayPermission("only_to", value=ok, label="only to a battlefield you conquered this turn", source_text=defn.text)]


@script("Dune Surfer")
def dune_surfer(defn):
    # You ignore [Tank] while assigning combat damage here.
    return [Static("self", "rule", ("ignore_tank_here",), label="you ignore Tank here", source_text=defn.text)]


@script("Hard Bargain")
def hard_bargain(defn):
    # [Reaction] [Repeat] [2]  Counter a spell unless its controller pays [2].
    item = lambda g, c: next((it for it in g.chain if it.uid == c.vars.get("__sp")), None)
    ctl = lambda g, c: item(g, c).controller if item(g, c) is not None else g.opponent(c.controller)
    return [SpellEffect([O.Choose(Sel("spell", zone="chain", pred=lambda g, c, u: any(it.uid == u and it.kind == "spell" for it in g.chain)),
                                  out="__sp", targeted=True),
                         O.If(lambda g, c: item(g, c) is not None, [      # no spell left to counter: nobody is asked to pay
                             O.PayResources(2, out="__hb", player=ctl),
                             O.If(lambda g, c: not c.vars.get("__hb"),
                                  [O.CounterItem(lambda g, c: item(g, c).id if item(g, c) is not None else None)])])],
                        label=defn.name, source_text=defn.text)]


@script("Marai Spire")
def marai_spire(defn):
    return [Static("self", "rule", ("repeat_cost_reduce", 1), label="friendly [Repeat] costs cost [1] less", source_text=defn.text)]


@script("Ornn's Forge")
def ornns_forge(defn):
    # While you control this battlefield, the first friendly non-token gear played each turn costs [1] less.
    def reduce(g, src, uid, e, pw):
        d = g.objects[uid].base_defn()
        p = g.objects[src].controller
        if not d.is_gear or d.is_token or g.turn_memo.get(("gear_played", p), 0):
            return e, pw
        return max(0, e - 1), pw
    return [Static("self", "rule", ("cost_reduce", reduce), label="first gear each turn costs [1] less", source_text=defn.text)]


@script("Spirit Wheel")
def spirit_wheel(defn):
    # When you choose a friendly unit, you may pay [1] and exhaust this to draw 1.
    def chose_friendly(g, s, ev):
        me = g.objects[s]
        if ev.get("kind") != "target" or ev.get("player") != me.controller or me.exhausted:
            return False
        return any(u in g.objects and g.objects[u].zone == "board" and g.objects[u].controller == me.controller
                   and "unit" in g.chars(u).types for u in ev.get("targets", ()))
    return [Triggered(chose_friendly, [O.May([
        O.If(lambda g, c: not g.objects[c.source].exhausted, [
            O.PayResources(1, [], out="__sw", optional=False),
            O.If(O.has_var("__sw"), [O.Exhaust(Ref("self")), O.Draw(1)])])],
        label="pay [1] and exhaust Spirit Wheel to draw 1")], label="Spirit Wheel: draw", source_text=defn.text)]


@script("Gearhead")
def gearhead(defn):
    # Each Equipment attached to me gives double its base Might bonus: add each one's printed bonus once more.
    def extra(g, src, uid):
        return sum((g.objects[a].base_defn().might or 0) for a in g.objects[src].attachments
                   if a in g.objects and g.objects[a].base_defn().is_equipment)
    return [Static("self", "might", extra, label="Equipment give double their base Might bonus", source_text=defn.text)]


@script("Needlessly Large Yordle")
def needlessly_large_yordle(defn):
    # I cost [2][Calm] less for each point you scored from holding this turn.
    def mod(g, u, e, pw):
        o = g.objects[u]
        n = g.turn_memo.get(("hold_points", o.controller if o.controller is not None else o.owner), 0)
        pw = list(pw)
        for _ in range(n):
            if "calm" in pw:
                pw.remove("calm")
        return max(0, e - 2 * n), pw
    return [PlayPermission("cost", cost_mod=mod, label="costs [2][Calm] less per point scored from holding this turn",
                           source_text=defn.text)]


@script("Mageseeker Warden")
def mageseeker_warden(defn):
    # While I'm at a battlefield, opponents can only play units to their base.
    # While I'm at a battlefield, spells and abilities can't ready enemy units and gear.
    return [Static("self", "rule", ("opp_units_base_only",), label="opponents play units only to their base", source_text=defn.text),
            Static("self", "rule", ("no_ready_enemies",), label="spells and abilities can't ready enemy units and gear",
                   source_text=defn.text)]


@script("Kraken Hunter")
def kraken_hunter(defn):
    # As you play me, you may spend any number of buffs as an additional cost. Reduce my cost by [Body] for each buff you spend.
    cands = lambda g, p, uid: [u for u, o in g.objects.items() if o.zone == "board" and o.controller == p and o.buffs > 0]
    return [PlayPermission("variable_reduce", value=(cands, "body", lambda g, c, u: g.do_spend_buff(u, c)),
                           label="spend buffs: [Body] less each", source_text=defn.text)]


@script("Commander Ledros")
def commander_ledros(defn):
    # As you play me, you may kill any number of friendly units as an additional cost. Reduce my cost by [Order] for each.
    cands = lambda g, p, uid: [u for u, o in g.objects.items() if o.zone == "board" and o.controller == p
                               and "unit" in g.chars(u).types and u != uid]
    return [PlayPermission("variable_reduce", value=(cands, "order", lambda g, c, u: g.do_kill([u], c, by="cost")),
                           label="kill friendly units: [Order] less each", source_text=defn.text)]


@script("Crescent Guardian")
def crescent_guardian(defn):
    # If you've played a spell this turn, you may pay [Chaos] as an additional cost to play me. If you do, I enter ready.
    from ..abilities import Replacement

    def spell_this_turn(g, uid):
        p = g.objects[uid].controller if g.objects[uid].controller is not None else g.objects[uid].owner
        return any(u in g.objects and "spell" in g.objects[u].base_defn().types for u in g.players[p].played_this_turn)
    return [PlayPermission("additional_cost", value=(None, [O.PayResources(0, ["chaos"], out="__cg", optional=False)], False),
                           cond=spell_this_turn, label="pay [Chaos]", source_text=defn.text),
            Replacement("enter_ready", lambda g, s, ev: ev.get("uid") == s and ev.get("add_paid"),
                        lambda g, s, ev: dict(ev, ready=True), label="enter ready if [Chaos] was paid", zone="any",
                        source_text=defn.text)]


@script("Here to Help")
def here_to_help(defn):
    # [Hidden] [Action]  You may play a unit from hand to a battlefield you control, reducing its cost by [3].
    from .. import payment

    def cost_at(g, p, u, loc):
        e, pw = g.card_cost(p, u, "hand", loc)
        return max(0, e - 3), pw

    def bfs(g, p, u):
        return [("bf", b.idx) for b in g.battlefields if b.controller == p
                and g.can_pay(p, *cost_at(g, p, u, ("bf", b.idx)), purpose=payment.purpose_of_card(g, u))]

    units = lambda g, c: [u for u in g.players[c.controller].hand if u in g.objects
                          and "unit" in g.objects[u].base_defn().types and bfs(g, c.controller, u)]
    pick = lambda g, c: (c.vars.get("__ht") or (None,))[0]
    locs = lambda g, c: bfs(g, c.controller, pick(g, c)) if pick(g, c) is not None else []
    return [SpellEffect([O.ChooseFromList(units, out="__ht", n=1, up_to=True, label="play a unit for [3] less"),
                         O.If(lambda g, c: pick(g, c) is not None, [
                             O.ChooseFromList(locs, out="__htl", label="to which battlefield?"),
                             O.PlayCard(pick, loc=Ref("__htl"),
                                        alt_cost=lambda g, c: cost_at(g, c.controller, pick(g, c), c.vars.get("__htl")))])],
                        label=defn.name, source_text=defn.text)]


@script("Temporal Portal")
def temporal_portal(defn):
    # [A], [T]: Give the next spell you play this turn [Repeat] equal to its cost.
    from ..abilities import Activated
    return [Activated({"energy": 0, "power": ["any"], "exhaust": True},
                      [O.Do(lambda g, c: g.add_turn_effect(c, "grant_repeat", {}, uses=1),
                            label="your next spell this turn gets [Repeat] equal to its cost")],
                      label="next spell gets [Repeat]", source_text=defn.text)]


@script("The Academy")
def the_academy(defn):
    # When you hold here, give your next spell this turn [Repeat] equal to its base cost.
    return [Triggered("you_hold_here", [O.Do(lambda g, c: g.add_turn_effect(c, "grant_repeat", {"base": True}, uses=1),
                                             label="your next spell this turn gets [Repeat] equal to its base cost")],
                      controller="event", label=defn.name, source_text=defn.text)]


@script("Firelights' Hideout")
def firelights_hideout(defn):
    # When you conquer here, the next unit you play this turn has [Accelerate].
    return [Triggered("you_conquer_here", [O.Do(lambda g, c: g.add_turn_effect(c, "grant_accelerate", {}, uses=1),
                                                label="your next unit this turn has [Accelerate]")],
                      controller="event", label=defn.name, source_text=defn.text)]


@script("Entrenched Boar")
def entrenched_boar(defn):
    # You may have me enter ready. If you do, I can't move this turn.
    # (A unit resolves as soon as it is played, so the choice is made as it is played.)
    from ..abilities import Replacement

    def ready(g, s, ev):
        g.add_mod(s, "keyword", ("cant_move", True), duration="turn", source=s)
        return dict(ev, ready=True)
    return [PlayPermission("as_play", value=[O.AskYesNo(out="__opt_ready", label="enter ready (then I can't move this turn)")]),
            Replacement("enter_ready", lambda g, s, ev: ev.get("uid") == s and ev.get("opt_ready"), ready,
                        label="enter ready; can't move this turn", zone="any", source_text=defn.text)]


@script("Noxian Emissary")
def noxian_emissary(defn):
    # [Empower] [1][Order]  /  [Empowered] [Deathknell] Play two 1 [M] Recruit unit tokens to your base.
    # (The [Empower] keyword ability comes from the keyword layer.)
    return [Triggered("die_self", [O.PlayToken("Recruit", loc="base", count=2)], filt=lambda g, s, ev: bool(ev.get("empowered")),
                      label="Deathknell (Empowered): two Recruits", source_text=defn.text, keyword="deathknell")]
