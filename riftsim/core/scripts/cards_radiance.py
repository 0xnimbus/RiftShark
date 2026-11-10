"""Hand-written scripts for the cards of the Radiance tournament decks (Master Yi, Akali, Irelia, Vex, Azir, Viktor,
Nasus) that the auto-scripter does not cover. Printed text is quoted above each script."""
from __future__ import annotations

from . import script, SpellEffect, weaponmaster_ability
from ..abilities import Static, Triggered, Activated, PlayPermission, Replacement
from ..selectors import Sel
from .. import ops as O
from ..vm import Ref


# ----------------------------------------------------------------------------- helpers
def _ev(c):
    return c.vars.get("ev") or {}


def _ctrl(g, s):
    return g.objects[s].controller


def _alone_defender(g, u):
    o = g.objects[u]
    if o.designation != "defender":
        return False
    return [x for x in g.units_at(o.location, o.controller) if g.objects[x].designation == "defender"] == [u]


def _played_this_turn_equipment(g, p):
    return any("Equipment" in g.objects[u].base_defn().tags for u in g.players[p].played_this_turn if u in g.objects)


def _keep(defn, abilities):
    """Keep the keyword/auto abilities already attached and add these."""
    return {"abilities": abilities, "replace": False}


def _replace_auto(defn, abilities, effect_abilities=None):
    return {"abilities": abilities, "effect_abilities": effect_abilities or [], "replace": True}


# ----------------------------------------------------------------------------- battlefields
@script("Abandoned Hall")
def abandoned_hall(defn):
    # When a player plays a spell, they may give a unit they control here +1 [M] this turn.
    return [Triggered("any_plays_spell", [
        O.May([O.Choose(Sel("unit", side="friendly", where="here"), out="t"), O.GiveMight(Ref("t"), 1)],
              label="give a unit you control here +1 [M]")],
        controller="event", label=defn.name, source_text=defn.text)]


@script("Bandle Tree")
def bandle_tree(defn):
    # You may hide an additional card here.
    return [Static("self", "rule", ("extra_hide_here",), label=defn.name, source_text=defn.text)]


@script("Forbidding Waste")
def forbidding_waste(defn):
    # While a unit here is defending alone, it has -2 [M].
    return [Static(Sel("unit", where="here", pred=lambda g, c, u: _alone_defender(g, u)), "might", -2,
                   label=defn.name, source_text=defn.text)]


@script("Forgotten Monument")
def forgotten_monument(defn):
    # Players can't score here until their third turn.
    return [Static("self", "rule", ("no_score_before_turn", 3), label=defn.name, source_text=defn.text)]


@script("Ravenbloom Conservatory")
def ravenbloom_conservatory(defn):
    # When you defend here, reveal the top card of your Main Deck. If it's a spell, put it in your hand. Otherwise, recycle it.
    def top_is_spell(g, c):
        u = (c.vars.get("__top") or [None])[0]
        return u is not None and "spell" in g.objects[u].base_defn().types
    return [Triggered("you_defend", [
        O.Look(1, out="__top", reveal=True),
        O.If(top_is_spell, [O.ToHand(lambda g, c: c.vars["__top"][0])],
             [O.Recycle(lambda g, c: list(c.vars.get("__top") or []))]),
    ], filt=lambda g, s, ev: ev.get("loc") == g.objects[s].place, label=defn.name, source_text=defn.text)]


@script("Seat of Power")
def seat_of_power(defn):
    # When you conquer here, draw 1 for each other battlefield you or allies control.
    def n(g, c):
        return sum(1 for b in g.battlefields if ("bf", b.idx) != c.here and b.controller is not None
                   and g.is_friendly(b.controller, c.controller))
    return [Triggered("you_conquer_here", [O.Draw(n)], label=defn.name, source_text=defn.text)]


@script("Targon's Peak")
def targons_peak(defn):
    # When you conquer here, ready 2 runes at the end of this turn.
    return [Triggered("you_conquer_here", [
        O.Delayed("end_turn", [O.Choose(Sel("rune", side="friendly", exhausted=True), out="__r", n=2, up_to=True, targeted=False),
                               O.Ready(Ref("__r"))], label="Targon's Peak: ready 2 runes")],
        label=defn.name, source_text=defn.text)]


# ----------------------------------------------------------------------------- legends
@script("Wuju Bladesman", "Master Yi, Wuju Bladesman")
def master_yi_legend(defn):
    # While a friendly unit defends alone, it gets +2 [M].
    return [Static(Sel("unit", side="friendly", pred=lambda g, c, u: _alone_defender(g, u)), "might", 2,
                   label=defn.name, source_text=defn.text)]


@script("Rogue Assassin", "Akali, Rogue Assassin")
def akali_legend(defn):
    # [Empower] [3][A]   (keyword)
    # [Action][>] [T]: If it's your turn, move a friendly unit in a showdown to base and if I'm [Empowered], ready it.
    def in_showdown(g, c, u):
        sd = g.showdown if g.showdown is not None else g.combat
        return sd is not None and g.objects[u].location == ("bf", sd["bf"])
    return _keep(defn, [Activated({"exhaust": True}, [
        O.If(O.is_my_turn, [O.Move(Ref("t"), "base"),
                            O.If(lambda g, c: bool(g.objects[c.source].empowered), [O.Ready(Ref("t"))])]),
    ], targets=[O.Choose(Sel("unit", side="friendly", pred=in_showdown), out="t")], timing="action",
        label="move a friendly unit in a showdown to base", source_text=defn.text)])


@script("Irelia, Blade Dancer")
def irelia_legend(defn):
    # When you choose a friendly unit, you may exhaust me and pay [A] to ready it.
    # When you conquer, you may pay [1] to ready me.
    def chose_friendly(g, s, ev):
        if ev.get("kind") != "target" or ev.get("player") != _ctrl(g, s) or g.objects[s].exhausted:
            return False
        return any(u in g.objects and g.objects[u].zone == "board" and g.objects[u].controller == _ctrl(g, s)
                   and "unit" in g.chars(u).types for u in ev.get("targets", ()))

    def friendly_targets(g, c):
        return [u for u in _ev(c).get("targets", ()) if u in g.objects and g.objects[u].zone == "board"
                and g.objects[u].controller == c.controller and "unit" in g.chars(u).types]
    return [
        Triggered(chose_friendly, [O.May([
            O.If(lambda g, c: not g.objects[c.source].exhausted, [
                O.PayResources(0, ["any"], out="__paid", optional=False),
                O.If(O.has_var("__paid"), [O.Exhaust(Ref("self")), O.Choose(friendly_targets, out="__u", targeted=False),
                                           O.Ready(Ref("__u"))])])],
            label="exhaust Irelia and pay [A] to ready the chosen unit")],
            label="Irelia: ready a chosen unit", source_text=defn.text),
        Triggered("you_conquer", [O.May([O.PayResources(1, [], out="__p1", optional=False),
                                         O.If(O.has_var("__p1"), [O.Ready(Ref("self"))])], label="pay [1] to ready Irelia")],
                  label="Irelia: ready me", source_text=defn.text),
    ]


@script("Azir, Emperor of the Sands")
def azir_legend(defn):
    # Your Sand Soldiers have [Weaponmaster].
    # [1], [T]: Play a 2 [M] Sand Soldier unit token to your base. Use only if you've played an Equipment this turn.
    return _replace_auto(defn, [
        Static(Sel("unit", side="friendly", name="Sand Soldier"), "ability", weaponmaster_ability(),
               label="Sand Soldiers have Weaponmaster", source_text=defn.text),
        Activated({"energy": 1, "exhaust": True}, [O.PlayToken("Sand Soldier", loc="base")], timing="main",
                  restriction=lambda g, s: _played_this_turn_equipment(g, _ctrl(g, s)),
                  label="play a Sand Soldier", source_text=defn.text),
    ])


@script("Curator of the Sands", "Nasus, Curator of the Sands")
def nasus_legend(defn):
    # When you play a unit, gear, or activated ability with Energy cost [7] or more, you may exhaust me to ready up to 2 runes.
    def big_play(g, s, ev):
        if ev.get("player") != _ctrl(g, s) or g.objects[s].exhausted:
            return False
        if ev.get("kind") == "play" and ev.get("card_type") in ("unit", "gear") and not ev.get("token"):
            return (g.objects[ev["uid"]].base_defn().energy or 0) >= 7
        if ev.get("kind") == "activate":
            return (ev.get("energy") or 0) >= 7
        return False
    return [Triggered(big_play, [O.May([
        O.If(lambda g, c: not g.objects[c.source].exhausted, [
            O.Exhaust(Ref("self")),
            O.Choose(Sel("rune", side="friendly", exhausted=True), out="__r", n=2, up_to=True, targeted=False),
            O.Ready(Ref("__r"))])], label="exhaust Nasus to ready up to 2 runes")],
        label=defn.name, source_text=defn.text)]


# ----------------------------------------------------------------------------- units
@script("Akali, Deadly Weapon")
def akali_deadly_weapon(defn):
    # [Empower] [2][Fury]  (keyword)
    # When I move, you may deal 1 to a unit at a battlefield I moved to or from. If I'm [Empowered], deal 2 instead.
    # [Empowered][>] I have +1 [M].
    def near(g, c, u):
        ev = _ev(c)
        loc = g.objects[u].location
        return loc is not None and loc[0] == "bf" and loc in (ev.get("from"), ev.get("to"))
    return _replace_auto(defn, [
        Triggered("move_self", [O.May([O.Choose(Sel("unit", pred=near), out="t"),
                                       O.Deal(lambda g, c: 2 if g.objects[c.source].empowered else 1, Ref("t"))],
                                      label="deal damage to a unit where Akali moved to or from")],
                  label="Akali: deal 1 (2 if Empowered)", source_text=defn.text),
        Static("self", "might", 1, cond=lambda g, s: bool(g.objects[s].empowered), label="Empowered: +1 [M]"),
    ])


@script("Evelynn, Entrancing")
def evelynn_entrancing(defn):
    # [Hidden] [Backline]
    # When you play me from face down on your turn, you may move an enemy unit at a different location to my battlefield.
    def mine(g, c):
        return _ev(c).get("loc")
    return [Triggered("play_self", [O.May([
        O.Choose(Sel("unit", side="enemy", pred=lambda g, c, u: g.objects[u].location != _ev(c).get("loc")), out="t"),
        O.Move(Ref("t"), mine)], label="move an enemy unit to Evelynn's battlefield")],
        filt=lambda g, s, ev: ev.get("from_zone") == "facedown" and g.turn_player == ev.get("player"),
        label=defn.name, source_text=defn.text)]


@script("Gust Monk")
def gust_monk(defn):
    # You may pay [1] as an additional cost to play me.   (auto: the additional cost)
    # When you play me, if you paid the additional cost, banish a card from any trash to give a unit [Assault 2] this turn.
    return _keep(defn, [Triggered("play_self", [
        O.Choose(Sel("card", zone="trash"), out="__b", targeted=True),
        O.Choose(Sel("unit"), out="t"),
        O.If(O.has_var("__b"), [O.Banish(Ref("__b")), O.GiveKeyword(Ref("t"), "assault", 2)]),
    ], filt=lambda g, s, ev: bool((ev.get("paid") or {}).get("add")),
        label="Gust Monk: Assault 2", source_text=defn.text)])


@script("Kha'Zix, Mutating Horror")
def khazix(defn):
    # [Ambush]
    # When I attack or defend, if an enemy unit is alone here, give me +2 [M] this turn and gain 2 XP.
    def enemy_alone(g, s, ev=None):
        o = g.objects[s]
        enemies = [u for u in g.units_at(o.location) if not g.is_friendly(g.objects[u].controller, o.controller)]
        return len(enemies) == 1
    eff = [O.If(lambda g, c: enemy_alone(g, c.source), [O.GiveMight(Ref("self"), 2), O.GainXP(2)])]
    return [Triggered("attack_self", eff, filt=enemy_alone, label=defn.name, source_text=defn.text),
            Triggered("defend_self", eff, filt=enemy_alone, label=defn.name, source_text=defn.text)]


@script("Lonely Poro")
def lonely_poro(defn):
    # [Deathknell][>] If I died alone, draw 1.
    return [Triggered("die_self", [O.Draw(1)], filt=lambda g, s, ev: bool(ev.get("alone")), zone="any",
                      label="Deathknell: draw 1 if I died alone", source_text=defn.text, keyword="deathknell")]


@script("Nasus, Guardian of Knowledge")
def nasus_guardian(defn):
    # Once each turn, when an enemy unit here dies, channel 1 rune exhausted.
    return [Triggered("enemy_unit_dies_here", [O.Channel(1, exhausted=True)], once_per_turn=True,
                      label=defn.name, source_text=defn.text)]


@script("Orianna, Exquisite")
def orianna_exquisite(defn):
    # [Shield]
    # I don't deal combat damage unless there's a friendly gear here.
    def no_gear(g, s):
        o = g.objects[s]
        return not any(g.objects[u].controller == o.controller and "gear" in g.chars(u).types
                       for u, x in g.objects.items() if x.zone == "board" and x.location == o.location)
    return [Static("self", "rule", ("no_combat_damage",), cond=no_gear, label=defn.name, source_text=defn.text)]


@script("Rengar, Trophy Hunter")
def rengar(defn):
    # [Ambush]
    # I can be played to a battlefield where there are enemy units.
    return [PlayPermission("to_enemy_bf", label=defn.name, source_text=defn.text)]


@script("Tomb-Raider Barbara")
def tomb_raider_barbara(defn):
    # When you play me, if you control 7 or more runes, choose an enemy gear. If it's [Empowered], disempower it. Otherwise, kill it.
    def seven(g, c_or_s, ev=None):
        p = _ctrl(g, c_or_s) if ev is not None else c_or_s.controller
        return len(g.players[p].runes) >= 7
    return [Triggered("play_self", [
        O.Choose(Sel("gear", side="enemy"), out="t"),
        O.If(lambda g, c: seven(g, c), [
            O.If(lambda g, c: c.vars.get("t") is not None and bool(g.objects[c.vars["t"]].empowered),
                 [O.Disempower(Ref("t"))], [O.Kill(Ref("t"))])]),
    ], filt=lambda g, s, ev: seven(g, s, ev), label=defn.name, source_text=defn.text)]


@script("Trifarian Captain")
def trifarian_captain(defn):
    # When you play me, look at the top 4 cards of your Main Deck. You may reveal from among them a unit or gear with
    # Energy cost no more than [3] and with Power cost no more than [A] and draw it. Recycle the rest.
    def eligible(g, c):
        out = []
        for u in c.vars.get("__look") or []:
            d = g.objects[u].base_defn()
            if (d.is_unit or d.is_gear) and (d.energy or 0) <= 3 and (d.power or 0) <= 1:
                out.append(u)
        return out

    def take(g, c):
        u = c.vars.get("__pick")
        if u is not None:
            g.emit("reveal", player=c.controller, cards=[u], ctx=c)
            g.put_in_hand(u, c)
            g.emit("draw", player=c.controller, uid=u, ctx=c)
    return [Triggered("play_self", [
        O.Look(4, out="__look"),
        O.ChooseFromList(eligible, out="__picks", n=1, up_to=True, label="reveal a unit or gear and draw it"),
        O.SetVar("__pick", lambda g, c: (c.vars.get("__picks") or (None,))[0] if isinstance(c.vars.get("__picks"), tuple)
                 else c.vars.get("__picks")),
        O.Do(take, label="draw it"),
        O.Recycle(lambda g, c: [u for u in c.vars.get("__look") or [] if u != c.vars.get("__pick")
                                and g.objects[u].zone == "deck"]),
    ], label=defn.name, source_text=defn.text)]


@script("Tornado Warrior")
def tornado_warrior(defn):
    # [Hidden]  When you play me from face down, you may empower something here. Disempower it at end of turn.
    # The auto-scripter read "something here" as a unit tag, so nothing could ever be chosen.
    # "here" = the battlefield I was played to ("When you play me" triggers before I'm on the board, so no ctx.here)
    sel = Sel("permanent", pred=lambda g, c, u: g.objects[u].location == _ev(c).get("loc"))
    return _replace_auto(defn, [Triggered("play_self", [O.May([
        O.Choose(sel, out="t"),
        O.Empower(Ref("t")),
        O.Delayed("end_turn", [O.Disempower(Ref("t"))], label="Tornado Warrior: disempower it"),
    ], label="empower something here")],
        filt=lambda g, s, ev: ev.get("from_zone") == "facedown", label=defn.name, source_text=defn.text)])


@script("Vex, Apathetic")
def vex_apathetic(defn):
    # [Deflect]
    # When an opponent plays a unit while I'm at a battlefield, [Stun] it. They can't move it this turn.
    # A token unit is played too (CR 185.2.a), so Vex stuns tokens: "opponent_plays_card" skips them.
    opp_plays = lambda g, s, ev: ev.get("kind") == "play" and ev.get("player") is not None \
        and not g.is_friendly(ev["player"], g.objects[s].controller)
    return [Triggered(opp_plays, [O.Stun(lambda g, c: _ev(c).get("uid")),
                                              O.GiveKeyword(lambda g, c: _ev(c).get("uid"), "cant_move", True)],
                      filt=lambda g, s, ev: ev.get("card_type") == "unit" and (g.objects[s].location or ("",))[0] == "bf",
                      label=defn.name, source_text=defn.text)]


# ----------------------------------------------------------------------------- gear
@script("Brutalizer")
def brutalizer(defn):
    # [Equip] [Calm]   effect: If this was attached to me this turn, I have an additional +2 [M].
    def this_turn(g, s):
        o = g.objects[s]
        return o.attached_to is not None and o.temp.get("attached_turn") == (g.turn, o.attached_to)
    return {"abilities": [], "effect_abilities": [Static("attached", "might", 2, cond=this_turn, label="+2 [M] the turn it's attached")],
            "replace": False}


@script("Guardian Angel")
def guardian_angel(defn):
    # [Equip] [Calm]   effect: If I would die, kill Guardian Angel instead. Heal me, exhaust me, and recall me.
    def applies(g, s, ev):
        return ev.get("uid") is not None and ev.get("uid") == g.objects[s].attached_to and not ev.get("replaced_with")

    def replace(g, s, ev):
        g.do_kill([s], None)
        return dict(ev, replaced_with="recall", exhaust=True)
    return {"abilities": [Replacement("die", applies, replace, label="Guardian Angel", source_text=defn.effect_text)],
            "replace": False}


@script("Hand Hammer")
def hand_hammer(defn):
    # [Equip] [Calm]   effect: I have +2 [M] while I'm at a battlefield with exactly one other unit you control.
    def cond(g, s):
        u = g.objects[s].attached_to
        if u is None:
            return False
        o = g.objects[u]
        return o.location is not None and o.location[0] == "bf" and len(g.units_at(o.location, o.controller)) == 2
    return {"abilities": [], "effect_abilities": [Static("attached", "might", 2, cond=cond, label="+2 [M] with exactly one other unit")],
            "replace": False}


@script("Edge of Night")
def edge_of_night(defn):
    # [Hidden]  When you play this from face down, attach it to a unit you control here.  [Equip] [Chaos]
    return _keep(defn, [Triggered("play_self", [
        O.Choose(Sel("unit", side="friendly", pred=lambda g, c, u: g.objects[u].location == _ev(c).get("loc")), out="t", targeted=False),
        O.Attach(Ref("self"), Ref("t"))],
        filt=lambda g, s, ev: ev.get("from_zone") == "facedown", label=defn.name, source_text=defn.text)])


@script("Sprite Fountain")
def sprite_fountain(defn):
    # [Temporary]  When you play this, play a ready 3 [M] Sprite unit token with [Temporary] to your base.
    # [Deathknell][>] Repeat this gear's play effect.
    play = [O.PlayToken("Sprite", loc="base", ready=True, grant={"temporary": True})]
    return _keep(defn, [Triggered("die_self", play, zone="any", label="Deathknell: play a Sprite", source_text=defn.text,
                                  keyword="deathknell")])


# ----------------------------------------------------------------------------- spells
@script("Alpha Strike")
def alpha_strike(defn):
    # [Action] Choose a friendly unit. It deals damage equal to its Might split among enemy units at battlefields.
    # Then for each unit this kills, do this: Gain 1 XP.
    def might(g, c):
        u = c.vars.get("__f")
        return (g.chars(u).might or 0) if u is not None and g.objects[u].zone == "board" else 0
    return [SpellEffect([
        O.Split(might, Ref("t"), source=Ref("__f")),
        O.Delayed(lambda g, s, ev: ev.get("kind") == "die" and ev.get("dmg_item") is not None, [O.GainXP(1)],
                  filt=lambda g, c, ev: ev.get("dmg_item") == c.item, once=False, label="Alpha Strike: gain 1 XP"),
    ], targets=[
        O.Choose(Sel("unit", side="friendly"), out="__f"),
        O.Choose(Sel("unit", side="enemy", where="battlefield"), out="t",
                 n=lambda g, c: max(1, might(g, c)), up_to=True),
    ], label=defn.name, source_text=defn.text)]


@script("Arise!")
def arise(defn):
    # Play a 2 [M] Sand Soldier unit token for each Equipment you control. Then do this: Ready up to two of them.
    return [SpellEffect([
        O.PlayToken("Sand Soldier", loc="base", count=lambda g, c: len([u for u in Sel("gear", side="friendly", tags=["Equipment"]).candidates(g, c)]),
                    out="__ss"),
        # errata (Spiritforged): "Then do this: Ready up to two of them."
        O.Choose(lambda g, c: [u for u in c.vars.get("__sss", ()) if g.objects[u].zone == "board"], out="__rd", n=2, up_to=True,
                 targeted=False),
        O.Ready(Ref("__rd")),
    ], label=defn.name, source_text=defn.text)]


@script("Guards!")
def guards(defn):
    # [Hidden]  Play a 2 [M] Sand Soldier unit token. Then do this: You may pay [C] to ready it. (errata, Unleashed)
    # "it" is the token (the auto-scripter read it as a chosen unit, so paying readied nothing).
    return [SpellEffect([
        O.PlayToken("Sand Soldier", loc="choose", out="__tok"),
        O.If(O.has_var("__tok"), [O.May([O.PayResources(0, ["order"], out="__paid", optional=False),
                                         O.If(O.has_var("__paid"), [O.Ready(Ref("__tok"))])], label="pay [Order] to ready it")]),
    ], label=defn.name, source_text=defn.text)]


@script("Back Off")
def back_off(defn):
    # [Hidden] [Action] [Stun] a unit. If you played this from your hand, draw 1.
    return [SpellEffect([O.Choose(Sel("unit"), out="t"), O.Stun(Ref("t")),
                         O.If(lambda g, c: c.played_from == "hand", [O.Draw(1)])], label=defn.name, source_text=defn.text)]


@script("Blood Money")
def blood_money(defn):
    # [Action] Kill a unit at a battlefield with 2 [M] or less. If it was an enemy unit, play a Gold gear token exhausted.
    # If it was a friendly unit, play two Gold gear tokens exhausted.
    def remember(g, c):
        u = c.vars.get("t")
        c.vars["__was_enemy"] = None if u is None else not g.is_friendly(g.objects[u].controller, c.controller)
    return [SpellEffect([
        O.Choose(Sel("unit", where="battlefield", max_might=2), out="t"),
        O.Do(remember),
        O.Kill(Ref("t")),
        O.If(lambda g, c: c.vars.get("__was_enemy") is True, [O.PlayToken("Gold", loc="base", exhausted=True)]),
        O.If(lambda g, c: c.vars.get("__was_enemy") is False, [O.PlayToken("Gold", loc="base", exhausted=True, count=2)]),
    ], label=defn.name, source_text=defn.text)]


@script("Deathgrip")
def deathgrip(defn):
    # [Reaction] Kill a friendly unit to give +[M] equal to its Might to another friendly unit this turn. Draw 1.
    def kill_and_note(g, c):
        u = c.vars.get("__k")
        c.vars["__m"] = (g.chars(u).might or 0) if u is not None else 0
        c.vars["__killed"] = False
        if u is not None:
            g.do_kill([u], c)
            c.vars["__killed"] = g.objects[u].zone != "board"
    return [SpellEffect([
        O.Choose(Sel("unit", side="friendly"), out="__k"),
        O.Choose(Sel("unit", side="friendly", pred=lambda g, c, u: u != c.vars.get("__k")), out="t"),
        O.Do(kill_and_note, label="kill a friendly unit"),
        O.If(lambda g, c: c.vars.get("__killed"), [O.GiveMight(Ref("t"), lambda g, c: c.vars["__m"])]),
        O.Draw(1),
    ], label=defn.name, source_text=defn.text)]


@script("En Garde")
def en_garde(defn):
    # [Reaction] Give a friendly unit +1 [M] this turn, then an additional +1 [M] this turn if it is the only unit you control there.
    def only(g, c):
        u = c.vars.get("t")
        return u is not None and g.units_at(g.objects[u].location, c.controller) == [u]
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.GiveMight(Ref("t"), 1),
                         O.If(only, [O.GiveMight(Ref("t"), 1)])], label=defn.name, source_text=defn.text)]


@script("Facebreaker")
def facebreaker(defn):
    # [Hidden] [Action] Stun a friendly unit and an enemy unit at the same battlefield.
    def has_enemy_there(g, c, u):
        loc = g.objects[u].location
        return any(not g.is_friendly(g.objects[x].controller, c.controller) for x in g.units_at(loc))
    return [SpellEffect([
        O.Choose(Sel("unit", side="friendly", where="battlefield", pred=has_enemy_there), out="t"),
        O.SetVar("__tloc", O.loc_of(Ref("t"))),
        O.Choose(Sel("unit", side="enemy", where="loc:__tloc"), out="t2"),
        O.Stun(Ref("t")), O.Stun(Ref("t2")),
    ], label=defn.name, source_text=defn.text)]


@script("Find Your Center")
def find_your_center(defn):
    # [Action] If an opponent's score is within 3 points of the Victory Score, this costs [2] less.
    # Draw 1 and channel 1 rune exhausted.
    def close(g, u):
        p = g.objects[u].owner
        return any(q.points >= g.victory_score() - 3 for i, q in enumerate(g.players) if i != p)
    return [SpellEffect([O.Draw(1), O.Channel(1, exhausted=True)], label=defn.name, source_text=defn.text),
            PlayPermission("cost", cost_mod=lambda g, u, e, p: (max(0, e - 2), p) if close(g, u) else (e, p),
                           label="costs [2] less near victory")]


@script("Hunker Down")
def hunker_down(defn):
    # [Reaction] Ready a friendly unit. It can't move this turn. Draw 1.
    return [SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Ready(Ref("t")),
                         O.GiveKeyword(Ref("t"), "cant_move", True), O.Draw(1)], label=defn.name, source_text=defn.text)]


@script("Hush")
def hush(defn):
    # [Reaction] Counter a spell with Power cost [A][A] or more.
    return [SpellEffect([
        O.Choose(Sel("spell", zone="chain", pred=lambda g, c, u: any(it.uid == u and it.kind == "spell" for it in g.chain)
                     and (g.objects[u].base_defn().power or 0) >= 2), out="__sp"),
        O.CounterItem(lambda g, c: next((it.id for it in g.chain if it.uid == c.vars.get("__sp")), None)),
    ], label=defn.name, source_text=defn.text)]


@script("Imperial Decree")
def imperial_decree(defn):
    # [Action] When any unit takes damage this turn, kill it.
    return [SpellEffect([O.Delayed(lambda g, s, ev: ev.get("kind") == "damage" and ev.get("amount", 0) > 0,
                                   [O.Kill(lambda g, c: _ev(c).get("uid"))], once=False, expires="turn",
                                   label="Imperial Decree: kill the damaged unit")],
                        label=defn.name, source_text=defn.text)]


@script("Life from Stone")
def life_from_stone(defn):
    # [Reaction] As an additional cost to play this, exhaust a friendly unit. Draw 1 and channel 1 rune exhausted.
    sel = Sel("unit", side="friendly", exhausted=False)
    return [PlayPermission("additional_cost", value=(sel, [O.Choose(sel, out="__ex", targeted=False), O.Exhaust(Ref("__ex"))], True),
                           label="exhaust a friendly unit"),
            SpellEffect([O.Draw(1), O.Channel(1, exhausted=True)], label=defn.name, source_text=defn.text)]


@script("Rampage")
def rampage(defn):
    # As you play this, you may pay [Body] as an additional cost.
    # Choose a friendly unit and an enemy unit. If you paid the additional cost, give the friendly unit +2 [M] this turn.
    # They deal damage equal to their Mights to each other.
    def fight(g, c):
        a, b = c.vars.get("t"), c.vars.get("t2")
        if a is None or b is None:
            return
        ma, mb = g.chars(a).might or 0, g.chars(b).might or 0
        g.do_deal([b], ma, c, source_uid=a)
        g.do_deal([a], mb, c, source_uid=b)
    return [PlayPermission("additional_cost", value=(None, [O.PayResources(0, ["body"], out="__addp", optional=False)], False),
                           label="pay [Body]"),
            SpellEffect([O.Choose(Sel("unit", side="friendly"), out="t"), O.Choose(Sel("unit", side="enemy"), out="t2"),
                         O.If(O.played_cost_additional(), [O.GiveMight(Ref("t"), 2)]),
                         O.Do(fight, label="they deal damage to each other")], label=defn.name, source_text=defn.text)]


@script("Sabotage")
def sabotage(defn):
    # Choose an opponent. They reveal their hand. Choose a non-unit card from it, and recycle that card.
    def reveal(g, c):
        p = c.vars.get("__opp")
        if p is not None:
            g.emit("reveal", player=p, cards=list(g.players[p].hand), ctx=c)
    return [SpellEffect([
        O.ChoosePlayer(out="__opp", opponent=True),
        O.Do(reveal, label="reveal hand"),
        O.Choose(lambda g, c: [u for u in g.players[c.vars["__opp"]].hand if not g.objects[u].base_defn().is_unit]
                 if c.vars.get("__opp") is not None else [], out="t", targeted=False),
        O.Recycle(Ref("t")),
    ], label=defn.name, source_text=defn.text)]


@script("Mordekaiser, Twice Slain")
def mordekaiser_twice_slain(defn):
    # [Accelerate] [Assault 3]  (keywords)
    # Once each turn, if I would die, you may kill a friendly unit to heal me, exhaust me, and recall me instead.
    # An optional replacement (CR 369-372): his controller chooses whether, and which friendly unit to kill. Killing
    # him as a cost (Whirling Twirligig, Cruel Patron) still pays the cost when this replaces his death (CR 203.2).
    def applies(g, s, ev):
        return ev.get("uid") == s and not ev.get("replaced_with")

    def options(g, s, ev):
        me = g.objects[s]
        return [u for u, o in g.objects.items() if u != s and o.zone == "board" and o.controller == me.controller
                and "unit" in g.chars(u).types]

    def replace(g, s, ev, choice):
        g.do_kill([choice], None)
        return dict(ev, replaced_with="recall", exhaust=True)
    return [Replacement("die", applies, replace, once_per_turn=True, optional=True, options=options,
                        label="Mordekaiser: kill a friendly unit to heal, exhaust and recall me instead",
                        source_text=defn.text)]
