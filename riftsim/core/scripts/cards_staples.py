"""Hand-written scripts for competitive cards the auto-scripter does not cover (Rek'Sai deck first, then legends and
other staples). Printed text, with errata applied, is quoted above each script."""
from __future__ import annotations

from . import script, SpellEffect
from ..abilities import Static, Triggered, Activated, PlayPermission, Replacement
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


# ----------------------------------------------------------------------------- legends
def _unit_loc(g, c, name="t"):
    u = c.vars.get(name)
    return g.objects[u].location if u is not None and u in g.objects else None


@script("Unforgiven", "Yasuo, Unforgiven")
def yasuo_legend(defn):
    # [2], [T]: Move a friendly unit to or from its base.
    def dest_ok(g, c, loc):
        cur = _unit_loc(g, c)
        if cur is None:
            return False
        u = c.vars["t"]
        if cur[0] == "base":
            return loc[0] == "bf" and g.valid_destination(u, loc, mover=c.controller)            # from its base
        return loc == ("base", g.objects[u].controller)                      # to its base
    return {"abilities": [Activated({"energy": 2, "exhaust": True}, [
        O.If(lambda g, c: c.vars.get("t") is not None and c.vars.get("dest") is not None, [O.Move(Ref("t"), Ref("dest"))]),
    ], targets=[O.Choose(Sel("unit", side="friendly"), out="t", targeted=True),
                O.ChooseLocation(out="dest", pred=dest_ok, include_bases=True, label="Move it to or from its base")],
        timing="main", label="move a friendly unit to or from its base", source_text=defn.text)], "replace": True}


@script("Wuju Bladesman, Starter")
def wuju_starter(defn):
    from .cards_radiance import master_yi_legend
    return master_yi_legend(defn)


@script("Emperor of the Sands")
def emperor_of_the_sands(defn):
    # SFD-197: "Your Sand Soldiers have [Weaponmaster]."   SFD-247: "Sand Soldiers you play have [Weaponmaster]."
    # [1], [T]: Play a 2 [M] Sand Soldier unit token to your base. Use only if you've played an Equipment this turn.
    from . import weaponmaster_ability
    from .cards_radiance import _played_this_turn_equipment, _ctrl
    you_play = "you play" in defn.text
    sel = Sel("unit", side="friendly", name="Sand Soldier") if not you_play else \
        Sel("unit", name="Sand Soldier", pred=lambda g, c, u: g.objects[u].owner == c.controller)
    return {"abilities": [
        Static(sel, "ability", weaponmaster_ability(), label=defn.name, source_text=defn.text),
        Activated({"energy": 1, "exhaust": True}, [O.PlayToken("Sand Soldier", loc="base")], timing="main",
                  restriction=lambda g, s: _played_this_turn_equipment(g, _ctrl(g, s)),
                  label="play a Sand Soldier", source_text=defn.text)], "replace": True}


@script("Purifier", "Lucian, Purifier")
def lucian_legend(defn):
    # Your Equipment each give [Assault].
    def n_equipment(g, src, uid):
        me = g.objects[src].controller
        n = sum(1 for a in g.objects[uid].attachments if a in g.objects and g.objects[a].controller == me
                and "Equipment" in g.chars(a).tags)
        return ("assault", n) if n else ("assault", 0)
    return {"abilities": [Static(Sel("unit", pred=lambda g, c, u: any(
        a in g.objects and g.objects[a].controller == c.controller for a in g.objects[u].attachments)),
        "keyword", n_equipment, label=defn.name, source_text=defn.text)], "replace": True}


@script("Grandmaster at Arms", "Jax, Grandmaster At Arms", "Jax, Grandmaster at Arms")
def jax_legend(defn):
    # [1], [T]: Attach a detached Equipment you control to a unit you control.
    # [T]: Attach an attached Equipment you control to a unit you control.
    def equipment(attached):
        return Sel("gear", side="friendly", pred=lambda g, c, u: "Equipment" in g.chars(u).tags
                   and ((g.objects[u].attached_to is not None) == attached))
    def unit_for(gear_var):
        return Sel("unit", side="friendly", pred=lambda g, c, u: g.objects[c.vars[gear_var]].attached_to != u
                   if c.vars.get(gear_var) is not None else True)
    return {"abilities": [
        Activated({"energy": 1, "exhaust": True}, [O.Attach(Ref("eq"), Ref("t"))],
                  targets=[O.Choose(equipment(False), out="eq", targeted=True),
                           O.Choose(unit_for("eq"), out="t", targeted=True)],
                  timing="main", label="attach a detached Equipment", source_text=defn.text),
        Activated({"exhaust": True}, [O.Attach(Ref("eq"), Ref("t"))],
                  targets=[O.Choose(equipment(True), out="eq", targeted=True),
                           O.Choose(unit_for("eq"), out="t", targeted=True)],
                  timing="main", label="move an attached Equipment", source_text=defn.text)], "replace": True}


@script("Prodigal Explorer", "Ezreal, Prodigal Explorer")
def ezreal_legend(defn):
    # [T]: [Reaction] — Draw 1. Use only if you've chosen enemy units and/or gear twice this turn with spells or unit
    # abilities.   (counted by the engine from the target events of spells and units' abilities: turn_memo["chose_enemy"])
    return {"abilities": [Activated({"exhaust": True}, [O.Draw(1)], timing="reaction",
                                    restriction=lambda g, s: g.turn_memo.get(("chose_enemy", g.objects[s].controller), 0) >= 2,
                                    label="draw 1", source_text=defn.text)], "replace": True}


def _may_exhaust_me(body, label):
    return O.May([O.If(_ready_self, [O.Exhaust(Ref("self"))] + body)], label=label)


@script("Battle Mistress", "Sivir, Battle Mistress")
def sivir_legend(defn):
    # When you recycle a rune, you may exhaust me to play a Gold gear token exhausted.
    # When one or more enemy units die, ready me.
    def you_recycle_rune(g, s, ev):
        o = g.objects.get(ev.get("uid"))
        return ev.get("kind") == "recycle" and o is not None and o.defn.type == "rune" and ev.get("player") == g.objects[s].controller

    def enemy_units_die(g, s, ev):
        if ev.get("kind") != "die" or ev.get("card_type") != "unit" or ev.get("player") is None:
            return False
        if g.is_friendly(ev["player"], g.objects[s].controller):
            return False
        seen = g.objects[s].temp.setdefault("sivir_batches", set())      # once per group of units dying together
        if ev.get("batch") in seen:
            return False
        seen.add(ev.get("batch"))
        return True
    return {"abilities": [
        Triggered(you_recycle_rune, [_may_exhaust_me([O.PlayToken("Gold", loc="base", exhausted=True)],
                                                     "exhaust me to play a Gold gear token exhausted")],
                  label="When you recycle a rune", source_text=defn.text),
        Triggered(enemy_units_die, [O.Ready(Ref("self"))], label="When one or more enemy units die, ready me",
                  source_text=defn.text)], "replace": True}


@script("Chem-Baroness", "Renata Glasc, Chem-Baroness")
def renata_legend(defn):
    # When you or an ally hold, you may exhaust me to play a Gold gear token exhausted.   (1v1: no allies)
    # While your score is within 3 points of the Victory Score, your Gold [Add] an additional [1].
    def close_to_win(g, s):
        p = g.objects[s].controller
        return g.players[p].points >= g.victory_score() - 3
    return {"abilities": [
        Triggered("you_hold", [_may_exhaust_me([O.PlayToken("Gold", loc="base", exhausted=True)],
                                               "exhaust me to play a Gold gear token exhausted")],
                  label="When you hold", source_text=defn.text),
        Static("self", "rule", ("gold_adds_extra", 1), cond=close_to_win, label="your Gold [Add] an additional [1]",
               source_text=defn.text)], "replace": True}


@script("Bashful Bloom")
def bashful_bloom(defn):
    # [4], [T]: Play a ready 3 [M] Sprite unit token with [Temporary]. This ability costs [1] less for each friendly
    # unit with [Temporary].
    def n_temporary(g, uid):
        p = g.objects[uid].controller
        return sum(1 for u in g.board_uids() if g.objects[u].controller == p and "unit" in g.chars(u).types
                   and g.chars(u).keywords.get("temporary"))
    return {"abilities": [Activated({"energy": 4, "exhaust": True, "energy_reduction": n_temporary},
                                    [O.PlayToken("Sprite", loc="choose", ready=True)], timing="main",
                                    label="play a ready Sprite", source_text=defn.text)], "replace": True}


@script("Green Father", "Ivern, Green Father")
def green_father(defn):
    # When you conquer or hold, you may exhaust me to replace that battlefield with a Brush battlefield token.
    def bf_uid(g, c):
        loc = (c.vars.get("ev") or {}).get("loc")
        return g.battlefields[loc[1]].uid if loc and loc[0] == "bf" else None
    body = [_may_exhaust_me([O.ReplaceWithToken(bf_uid, "Brush")], "exhaust me to replace that battlefield with a Brush")]
    return {"abilities": [Triggered("you_conquer", body, label="When you conquer", source_text=defn.text),
                          Triggered("you_hold", list(body), label="When you hold", source_text=defn.text)], "replace": True}


@script("Voidreaver")
def voidreaver(defn):
    # When you win a combat, gain 1 XP. / Spend 1 XP, [T]: [Buff] a unit.   (auto)
    # Spend 2 XP, [T]: Move an exhausted friendly unit from a battlefield to its base.
    return _keep([Activated({"xp": 2, "exhaust": True}, [O.Move(Ref("t"), "base")],
                            targets=[O.Choose(Sel("unit", side="friendly", pred=lambda g, c, u: g.objects[u].exhausted
                                                  and g.objects[u].location is not None and g.objects[u].location[0] == "bf"),
                                              out="t", targeted=True)],
                            timing="main", label="move an exhausted friendly unit to its base",
                            source_text="Spend 2 XP, [T]: Move an exhausted friendly unit from a battlefield to its base.")])


@script("Pride of Nazumah")
def pride_of_nazumah(defn):
    # [1], [T]: Give a friendly unit "I have [Assault] equal to my [Shield]" this turn.
    return {"abilities": [Activated({"energy": 1, "exhaust": True},
                                    [O.GiveKeyword(Ref("t"), "assault_equals_shield", True, duration="turn")],
                                    targets=[O.Choose(Sel("unit", side="friendly"), out="t", targeted=True)], timing="main",
                                    label="give a unit Assault equal to its Shield", source_text=defn.text)], "replace": True}


@script("Agony's Embrace")
def agonys_embrace(defn):
    # Once each turn, when you play a card from face down, draw 1. Then, if it's not your turn, discard 1.
    def facedown_play(g, s, ev):
        return ev.get("kind") == "play" and ev.get("from_zone") == "facedown" and ev.get("player") == g.objects[s].controller
    return {"abilities": [Triggered(facedown_play, [O.Draw(1), O.If(O.not_(O.is_my_turn), [O.Discard(1)])],
                                    once_per_turn=True, label=defn.name, source_text=defn.text)], "replace": True}


@script("Swift Scout", "Teemo, Swift Scout")
def teemo_legend(defn):
    # You may pay [1] to hide a card with [Hidden] instead of [A].
    # [1], [T]: Put a Teemo unit you own into your hand from your Champion Zone or the board.
    def teemo_unit(g, c, u):
        o = g.objects[u]
        d = o.base_defn()
        return o.owner == c.controller and d.is_unit and o.zone in ("champion", "board") and \
            ("Teemo" in d.tags or d.name.split(",")[0].strip() == "Teemo")
    return {"abilities": [
        Static("self", "rule", ("hide_for_1_energy",), label="hide for [1] instead of [A]", source_text=defn.text),
        Activated({"energy": 1, "exhaust": True}, [O.ToHand(Ref("t"))],
                  targets=[O.Choose(Sel("card", zone="any", pred=teemo_unit), out="t", targeted=False)], timing="main",
                  label="put a Teemo unit you own into your hand", source_text=defn.text)], "replace": True}


@script("Boy Who Shattered Time", "Ekko, Boy Who Shattered Time")
def boy_who_shattered_time(defn):
    # [Empower] — [1], [T]   (keyword)
    # Disempower me, [T]: Reduce the cost of the next unit you play this turn by [2][A] and give it
    # "Kill me at end of turn."
    kill_eot = Triggered("end_turn", [O.Kill(Ref("self"))], label="Kill me at end of turn", source_text="Kill me at end of turn.")

    def grant(g, uid, ctx):
        g.add_mod(uid, "ability", kill_eot, duration="permanent", source=ctx.source)

    reduce = O.DelayedPassive("cost_reduce", {"energy": 2, "power": 1, "on_play": grant,
                                              "filter": lambda g, u: g.objects[u].base_defn().is_unit}, uses=1)
    return {"abilities": [Activated({"energy": 0, "power": [], "exhaust": True, "disempower_self": True,
                                     "custom": [O.Disempower(Ref("self"))]}, [reduce], timing="main",
                                    label="next unit costs [2][A] less and dies at end of turn", source_text=defn.text)],
            "replace": True}


@script("Starry-Eyed Songstress")
def starry_eyed_songstress(defn):
    # As an additional cost to play a spell, you may exhaust me and three friendly units to reduce the cost of
    # that spell by [2].   (flow._exhaust_reducer_code offers it while the spell is finalized)
    return {"abilities": [Static("self", "rule", ("spell_reduce_exhaust_units", (3, 2)), label=defn.name, source_text=defn.text)],
            "replace": True}


@script("Virtuoso", "Jhin, Virtuoso")
def virtuoso(defn):
    # When you play a spell, if you spent [4] or more, you may banish it. Then, if there are four spells banished
    # with me, put each in its trash, channel 4 runes, and draw 1.
    # Rulings (RiftJudge 8769, 9779): the trigger happens once the spell has finished resolving (Time Warp has
    # already banished itself); a countered spell was never played (CR 426.1.b), so it does not trigger.
    def spent4(g, s, ev):
        return ev.get("kind") == "resolve" and ev.get("card_type") == "spell" and \
            ev.get("player") == g.objects[s].controller and (ev.get("energy") or 0) >= 4

    def banish_it(g, c):
        u = c.event.get("uid")
        o = g.objects.get(u)
        if o is not None and o.zone == "trash":
            g.do_banish([u], c)
            g.objects[c.source].temp.setdefault("banished_with", []).append(u)

    def payoff(g, c):
        src = g.objects[c.source]
        mine = [u for u in src.temp.get("banished_with", []) if g.objects[u].zone == "banish"]
        src.temp["banished_with"] = mine
        if len(mine) < 4:
            return
        for u in mine:
            g._to_zone(g.objects[u], "trash")
        src.temp["banished_with"] = []
        g.bump()
        c.vars["__virt"] = True

    return {"abilities": [Triggered(spent4, [O.May([O.Do(banish_it)], label="banish the spell with Virtuoso"),
                                             O.Do(payoff),
                                             O.If(lambda g, c: c.vars.get("__virt"), [O.Channel(4), O.Draw(1)])],
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Lady of Clockwork")
def lady_of_clockwork(defn):
    # At the start of your Main Phase, you may pay [1] to choose a friendly gear. It becomes a unit gear with Might
    # equal to its Energy cost until you choose another gear with me.
    gear = Sel("gear", side="friendly")

    def animate(g, c):
        lady = g.objects[c.source]
        new = c.vars.get("t")
        if new is None or new not in g.objects:
            return
        old = lady.temp.get("clockwork")
        if old is not None and old in g.objects:            # "until you choose another gear with me"
            o = g.objects[old]
            o.mods = [m for m in o.mods if not (m.source == c.source and m.kind in ("type", "base_might"))]
            g.restruct()
        lady.temp["clockwork"] = new
        g.add_mod(new, "type", "unit", duration="permanent", source=c.source)
        g.add_mod(new, "base_might", g.objects[new].base_defn().energy or 0, duration="permanent", source=c.source)
        g.bump()

    # "you may pay [1] to" is the base cost paid as the trigger is finalized (CR 383.3.b); the gear is a target chosen
    # then (355.10.c.1).
    return {"abilities": [Triggered("start_main", [O.May([
        O.Choose(gear, out="t", targeted=True),
        O.PayResources(1, out="__lady", optional=False),
        O.Do(animate)], label="pay [1] to choose a friendly gear")],
        label=defn.name, source_text=defn.text)], "replace": True}


@script("Deceiver", "LeBlanc, Deceiver")
def deceiver(defn):
    # When you conquer or hold, you may discard 1 and exhaust me to play a ready Reflection unit token there.
    # It becomes a copy of another unit there. Give it [Temporary].
    def conquer_or_hold(g, s, ev):
        return ev.get("kind") in ("conquer", "hold") and ev.get("player") == g.objects[s].controller

    def can(g, c):
        me = g.objects[c.source]
        return not me.exhausted and any(g.objects[h].owner == c.controller for h in g.players[c.controller].hand)

    def there(g, c):
        return c.event.get("loc")

    # "you may discard 1 and exhaust me to ..." is the trigger's base cost (CR 383.3.b): decided and paid as it is
    # finalized; the unit to copy is picked once the Reflection exists
    from ..targeting import _TriggerMay
    other_here = Sel("unit", pred=lambda g, c, u: u != c.vars.get("token") and g.objects[u].location == c.event.get("loc"))
    may = O.May([], label="discard 1 and exhaust Deceiver to play a Reflection copy there", out="__may")
    costs = [_TriggerMay(may, pre=[can]),
             O.Choose(Sel("card", zone="hand", pred=lambda g, c, u: g.objects[u].owner == c.controller), out="__dd", targeted=False),
             O.Do(lambda g, c: g.do_discard(c.controller, [c.vars["__dd"]], c)),
             O.Do(lambda g, c: g.do_exhaust(c.source, c))]
    body = [O.PlayToken("Reflection", loc=there, ready=True),
            O.Choose(other_here, out="__model", targeted=False),
            O.CopyAs(Ref("token"), Ref("__model")),
            O.GiveKeyword(Ref("token"), "temporary", True, duration="permanent")]
    return {"abilities": [Triggered(conquer_or_hold, body, targets=costs, label=defn.name, source_text=defn.text)],
            "replace": True}


# ----------------------------------------------------------------------------------------- champion units
def _at_bf(g, u):
    o = g.objects.get(u)
    return o is not None and o.zone == "board" and o.location is not None and o.location[0] == "bf"


def _buffed_friendly_at_my_bf(g, s, other=False):
    me = g.objects[s]
    if not _at_bf(g, s):
        return []
    return [u for u, o in g.objects.items() if o.zone == "board" and o.location == me.location and o.controller == me.controller
            and o.buffs > 0 and "unit" in g.chars(u).types and not (other and u == s)]


@script("Master Yi, Meditative")
def master_yi_meditative(defn):
    # While you have 8+ runes, I have +4 [M].
    return {"abilities": [Static("self", "might", 4, cond=lambda g, s: len(g.players[g.objects[s].controller].runes) >= 8,
                                 label="8+ runes: +4 [M]", source_text=defn.text)], "replace": True}


@script("Sett, Kingpin")
def sett_kingpin(defn):
    # [Tank]   (keyword)
    # I get +1 [M] for each buffed friendly unit at my battlefield.
    return {"abilities": [Static("self", "might", lambda g, s, u: len(_buffed_friendly_at_my_bf(g, s)),
                                 label="+1 [M] per buffed friendly unit at my battlefield", source_text=defn.text)], "replace": True}


@script("Lee Sin, Centered")
def lee_sin_centered(defn):
    # [Accelerate]   (keyword)
    # Other buffed friendly units at my battlefield have +2 [M].
    sel = Sel("unit", pred=lambda g, c, u: u in _buffed_friendly_at_my_bf(g, c.source, other=True))
    return {"abilities": [Static(sel, "might", 2, label="other buffed friendly units at my battlefield +2 [M]",
                                 source_text=defn.text)], "replace": True}


@script("Xin Zhao, Vigilant")
def xin_zhao_vigilant(defn):
    # [Tank]   (keyword)
    # I enter ready if you have two or more other units in your base.
    from ..abilities import Replacement

    def cond(g, s, ev):
        if ev.get("uid") != s:
            return False
        p = g.objects[s].controller
        return len([u for u, o in g.objects.items() if u != s and o.zone == "board" and o.location == ("base", p)
                    and "unit" in g.chars(u).types]) >= 2
    return {"abilities": [Replacement("enter_ready", cond, lambda g, s, ev: dict(ev, ready=True), label=defn.name, zone="any")],
            "replace": True}


@script("Kog'Maw, Caustic")
def kogmaw_caustic(defn):
    # [Deathknell] — Deal 4 to all units at my battlefield.
    here = Sel("unit", pred=lambda g, c, u: c.event.get("loc") is not None and c.event["loc"][0] == "bf"
               and g.objects[u].location == c.event["loc"])
    return {"abilities": [Triggered("die_self", [O.Deal(4, here)], label="Deathknell", source_text=defn.text,
                                    keyword="deathknell")], "replace": True}


@script("Vi, Hotheaded")
def vi_hotheaded(defn):
    # [Deflect]   (keyword)
    # [2][Fury]: Double my Might this turn.
    return {"abilities": [Activated({"energy": 2, "power": ["fury"]},
                                    [O.DoubleMight(Ref("self"), duration="turn")],
                                    timing="main", label="double my Might this turn", source_text=defn.text)], "replace": True}


@script("Lucian, Gunslinger")
def lucian_gunslinger(defn):
    # [Assault]   (keyword)
    # When I attack, deal damage equal to my [Assault] to an enemy unit here.
    return {"abilities": [Triggered("attack_self", [O.Deal(lambda g, c: g.chars(c.source).kw("assault"), Ref("t"))],
                                    targets=[O.Choose(Sel("unit", side="enemy", where="here"), out="t")],
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Yuumi, Magical Cat")
def yuumi(defn):
    # When I attack or defend, give one of your other units here +3 [M] and [Tank] this turn.
    sel = Sel("unit", side="friendly", where="here", other=True)
    eff = [O.GiveMight(Ref("t"), 3, duration="turn"), O.GiveKeyword(Ref("t"), "tank", True, duration="turn")]
    return {"abilities": [Triggered(ev, eff, targets=[O.Choose(sel, out="t")], label=defn.name, source_text=defn.text)
                          for ev in ("attack_self", "defend_self")], "replace": True}


@script("Volibear, Imposing")
def volibear_imposing(defn):
    # [Shield 3] [Tank]   (keywords)
    # When an opponent moves to a battlefield other than mine, draw 1.
    def opp_moves_elsewhere(g, s, ev):
        if ev.get("kind") != "move":
            return False
        me = g.objects[s]
        to = ev.get("to")
        return ev.get("player") not in (None, me.controller) and not g.is_friendly(ev["player"], me.controller) and \
            to is not None and to[0] == "bf" and to != me.location and ev.get("batch_index", 0) == 0   # one move = one trigger
    return {"abilities": [Triggered(opp_moves_elsewhere, [O.Draw(1)], label=defn.name, source_text=defn.text)], "replace": True}


@script("LeBlanc, Fragmented")
def leblanc_fragmented(defn):
    # [Assault]   (keyword)
    # [Deathknell][>] Draw 1. If it's your Beginning Phase, draw 2 instead.
    n = lambda g, c: 2 if (g.turn_player == c.controller and g.phase == "beginning") else 1
    return {"abilities": [Triggered("die_self", [O.Draw(n)], label="Deathknell", source_text=defn.text, keyword="deathknell")],
            "replace": True}


def _others_here(g, s):
    me = g.objects[s]
    return [u for u, o in g.objects.items() if u != s and o.zone == "board" and o.location == me.location
            and o.controller == me.controller and "unit" in g.chars(u).types]


@script("Shen, Scourge of Shadows")
def shen_scourge(defn):
    # When I hold, if there is exactly one other unit you control here, draw 1.
    return {"abilities": [Triggered("hold_self", [O.Draw(1)], intervening=lambda g, c: len(_others_here(g, c.source)) == 1,
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Shen, Leader of the Kinkou Order")
def shen_leader(defn):
    # [Shield]   (keyword)
    # When I hold, if there is exactly one other unit you control here, you score 1 point.
    return {"abilities": [Triggered("hold_self", [O.GainPoints(1)], intervening=lambda g, c: len(_others_here(g, c.source)) == 1,
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Riven, Shattered")
def riven_shattered(defn):
    # [Weaponmaster]   (keyword)
    # When I attack, choose an enemy unit here. Deal 2 to it for each Equipment attached to me.
    def n(g, c):
        return 2 * len([a for a in g.objects[c.source].attachments if a in g.objects and "Equipment" in g.chars(a).tags])
    return {"abilities": [Triggered("attack_self", [O.Deal(n, Ref("t"))],
                                    targets=[O.Choose(Sel("unit", side="enemy", where="here"), out="t")],
                                    label=defn.name, source_text=defn.text)], "replace": False}


@script("Swain, Visionary")
def swain_visionary(defn):
    # [Vision]   (keyword)
    # When I conquer, if you've played a non-token unit, a non-token gear, and a spell this turn, you score 1 point.
    def did_all(g, c):
        played = [g.objects[u].base_defn() for u in g.players[c.controller].played_this_turn if u in g.objects]
        return any(d.is_unit and not d.is_token for d in played) and any(d.type == "gear" and not d.is_token for d in played) \
            and any(d.type == "spell" for d in played)
    return {"abilities": [Triggered("conquer_self", [O.GainPoints(1)], intervening=did_all, label=defn.name, source_text=defn.text)],
            "replace": True}


@script("Jayce, Hammer in Hand")
def jayce_hammer(defn):
    # When I become ready, choose one to give me this turn — [Assault 2] / [Deflect 2] / [Ganking]
    modes = [("[Assault 2]", [O.GiveKeyword(Ref("self"), "assault", 2, duration="turn")]),
             ("[Deflect 2]", [O.GiveKeyword(Ref("self"), "deflect", 2, duration="turn")]),
             ("[Ganking]", [O.GiveKeyword(Ref("self"), "ganking", True, duration="turn")])]
    return {"abilities": [Triggered("ready_self", [O.ChooseMode(modes)], label=defn.name, source_text=defn.text)], "replace": True}


@script("Kha'Zix, Evolving Hunter")
def khazix_evolving(defn):
    # [Hunt]   (keyword)
    # When I attack, you may spend 3 XP to deal damage equal to my Might to an enemy unit here.
    # "spend 3 XP to" is the trigger's base cost, paid as it is finalized (CR 383.3.b), and the enemy unit is chosen
    # then too (355.10.c.1: the unit is a target, the XP is not).
    return {"abilities": [Triggered("attack_self", [O.May([
        O.Choose(Sel("unit", side="enemy", where="here"), out="t"),
        O.If(lambda g, c: g.players[c.controller].xp >= 3, [
            O.SpendXP(3, out="__xp", optional=False),
            O.Deal(lambda g, c: g.chars(c.source).might or 0, Ref("t"))])], label="spend 3 XP to deal damage")],
        label=defn.name, source_text=defn.text)], "replace": True}


@script("Morgana, Vindictive")
def morgana_vindictive(defn):
    # [Ambush]   (keyword)
    # When you play me, deal damage to a unit equal to the damage marked on it.
    return {"abilities": [Triggered("play_self", [O.Deal(lambda g, c: g.objects[c.vars["t"]].damage if c.vars.get("t") in g.objects else 0,
                                                         Ref("t"))],
                                    targets=[O.Choose(Sel("unit"), out="t")], label=defn.name, source_text=defn.text)],
            "replace": True}


@script("K'Sante, Dauntless")
def ksante(defn):
    # [Shield]   (keyword)
    # When I attack or defend, double the [Shield] of a unit you control here this turn.
    eff = [O.GiveKeyword(Ref("t"), "shield", lambda g, c: g.chars(c.vars["t"]).kw("shield") if c.vars.get("t") in g.objects else 0,
                         duration="turn")]
    tg = [O.Choose(Sel("unit", side="friendly", where="here"), out="t")]
    return {"abilities": [Triggered(ev, eff, targets=list(tg), label=defn.name, source_text=defn.text)
                          for ev in ("attack_self", "defend_self")], "replace": True}


@script("Mordekaiser, Dominating")
def mordekaiser_dominating(defn):
    # When you play me or when I attack, you may discard 1 to kill a unit or gear.
    # "discard 1 to ..." is the trigger's base cost (CR 383.3.b): yes/no, the target and the discard are all settled
    # as the trigger is finalized; the kill happens on resolution.
    from ..targeting import _TriggerMay
    sel = Sel("permanent", pred=lambda g, c, u: bool({"unit", "gear"} & set(g.chars(u).types)))
    may = O.May([], label="discard 1 to kill a unit or gear", out="__may")
    pre = [lambda g, c: bool(g.players[c.controller].hand), lambda g, c: bool(sel.candidates(g, c))]
    return {"abilities": [Triggered(ev, [O.Kill(Ref("t"))],
                                    targets=[_TriggerMay(may, pre=list(pre)), O.Choose(sel, out="t"), O.Discard(1)],
                                    label=defn.name, source_text=defn.text)
                          for ev in ("play_self", "attack_self")], "replace": True}


def _unwrap(var):
    """ChooseFromList(up_to=True) stores a tuple; turn a 0/1-element pick into a uid or None."""
    def f(g, c):
        v = c.vars.get(var)
        if isinstance(v, tuple):
            c.vars[var] = v[0] if v else None
    return f


def _look_reveal_draw(n, kind):
    """Look at the top n cards of your Main Deck. You may reveal a <kind> from among them and draw it. Recycle the rest."""
    def pick_ok(g, c, u):
        d = g.objects[u].base_defn()
        return kind in d.types or (kind == "gear" and d.type == "gear") or (kind == "unit" and d.is_unit)
    return [O.Look(n, out="looked"),
            O.ChooseFromList(lambda g, c: [u for u in c.vars.get("looked", []) if pick_ok(g, c, u)], out="__pick", up_to=True,
                             label=f"reveal a {kind} and draw it"),
            O.Do(_unwrap("__pick")),
            O.Do(lambda g, c: g.emit("reveal", player=c.controller, cards=[c.vars["__pick"]], ctx=c) if c.vars.get("__pick") else None),
            O.DrawCard(Ref("__pick")),
            O.Recycle(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"])]


@script("Ornn, Blacksmith")
def ornn_blacksmith(defn):
    # When you play me or when I hold, look at the top 4 cards of your Main Deck. You may reveal a gear from among
    # them and draw it. Then recycle the rest.
    return {"abilities": [Triggered(ev, _look_reveal_draw(4, "gear"), label=defn.name, source_text=defn.text)
                          for ev in ("play_self", "hold_self")], "replace": True}


@script("Fiora, Peerless")
def fiora_peerless(defn):
    # When I attack or defend one on one, double my Might this combat.
    # "one on one" is part of the trigger condition (CR 383.2.a), checked as I attack or defend: I and the one enemy
    # unit here are both alone (CR 740.2.a-b). Nothing re-checks it on resolution.
    def one_on_one(g, s, ev):
        me = g.objects[s]
        if me.zone != "board" or ev.get("uid") != s:
            return False
        here = g.units_at(me.location)
        mine = [u for u in here if g.is_friendly(g.objects[u].controller, me.controller)]
        return len(mine) == 1 and len(here) == 2
    return {"abilities": [Triggered(ev, [O.DoubleMight(Ref("self"), duration="combat")], filt=one_on_one,
                                    label=defn.name, source_text=defn.text) for ev in ("attack_self", "defend_self")],
            "replace": True}


@script("Janna, Savior")
def janna_savior(defn):
    # [Reaction]   (keyword)
    # When you play me, heal your units here, then move up to one enemy unit from here to its base. (errata, Spiritforged)
    return {"abilities": [Triggered("play_self", [
        O.Heal(Sel("unit", side="friendly", where="here")),
        O.Move(Ref("t"), "base")], targets=[O.Choose(Sel("unit", side="enemy", where="here"), out="t", n=1, up_to=True)],
        label=defn.name, source_text=defn.text)], "replace": True}


def _opponent_near_victory(g, c):
    v = g.victory_score()
    return any(ps.points >= v - 3 for ps in g.players if not g.is_friendly(ps.idx, c.controller))


@script("Poppy, Paragon")
def poppy_paragon(defn):
    # [Deflect]   (keyword)
    # When you play me, if an opponent's score is within 3 points of the Victory Score, ready me and gain 3 XP.
    return {"abilities": [Triggered("play_self", [O.Ready(Ref("self")), O.GainXP(3)], intervening=_opponent_near_victory,
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Pyke, Returned")
def pyke_returned(defn):
    # [Hidden] [Backline]   (keywords)
    # Once each turn, when an enemy unit dies while I'm at a battlefield, play a Gold gear token exhausted.
    def enemy_dies(g, s, ev):
        me = g.objects[s]
        return ev.get("kind") == "die" and ev.get("card_type") == "unit" and ev.get("player") is not None and \
            not g.is_friendly(ev["player"], me.controller) and _at_bf(g, s)
    return {"abilities": [Triggered(enemy_dies, [O.PlayToken("Gold", loc="base", exhausted=True)], once_per_turn=True,
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Ivern, Nurturer")
def ivern_nurturer(defn):
    # When you play me or when I hold, look at the top 3 cards of your Main Deck. You may reveal a unit from among them
    # and draw it. Recycle the rest. Then if you revealed a Bird, Cat, Dog, or Poro, do this: [Buff] a friendly unit.
    pets = {"Bird", "Cat", "Dog", "Poro"}
    eff = _look_reveal_draw(3, "unit") + [
        O.If(lambda g, c: c.vars.get("__pick") in g.objects and bool(pets & set(g.objects[c.vars["__pick"]].base_defn().tags)),
             [O.Reflexive([O.Choose(Sel("unit", side="friendly"), out="t"), O.Buff(Ref("t"))], label="buff a friendly unit")])]
    return {"abilities": [Triggered(ev, list(eff), label=defn.name, source_text=defn.text) for ev in ("play_self", "hold_self")],
            "replace": True}


@script("Diana, Lunari")
def diana_lunari(defn):
    # When a showdown begins here, you may pay [1]. If you do, [Predict], then reveal the top card of your Main Deck.
    # If it's a spell, draw it.
    def top(g, c):
        deck = g.players[c.controller].deck
        c.vars["__top"] = deck[0] if deck else None

    def reveal_top(g, c):
        u = c.vars.get("__top")
        if u is None or g.objects[u].zone != "deck":      # Nocturne, Horrifying banished as he was revealed
            c.vars["__top"] = None
            return
        g.emit("reveal", player=c.controller, cards=[u], ctx=c)
    return {"abilities": [Triggered("showdown_start_here", [
        O.PayResources(1, out="__dp"),
        O.If(Ref("__dp"), [O.Predict(1), O.Do(top), O.SeeFromDeck(lambda g, c: [c.vars.get("__top")]), O.Do(reveal_top),
                           O.If(lambda g, c: c.vars.get("__top") in g.objects and g.objects[c.vars["__top"]].base_defn().type == "spell",
                                [O.DrawCard(Ref("__top"))])])], label=defn.name, source_text=defn.text)], "replace": True}


@script("Lulu, Whimsical")
def lulu_whimsical(defn):
    # When I move, you may have another unit's base Might become 4 this turn.
    return {"abilities": [Triggered("move_self", [O.May([O.Choose(Sel("unit", other=True), out="t"),
                                                         O.SetMight(Ref("t"), 4, duration="turn", base=True)],
                                                        label="have another unit's base Might become 4 this turn")],
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Fizz, Trickster")
def fizz_trickster(defn):
    # When you play me, you may play a spell from your trash with Energy cost no more than [3], ignoring its Energy
    # cost. Recycle that spell after you play it.
    def options(g, c):
        return [u for u in g.players[c.controller].trash if g.objects[u].base_defn().type == "spell"
                and (g.objects[u].base_defn().energy or 0) <= 3]

    def mark(g, c):
        u = c.vars.get("played")
        for it in g.chain:
            if it.uid == u and it.kind == "spell":
                it.ctx.vars["__recycle_after"] = True
    return {"abilities": [Triggered("play_self", [
        O.ChooseFromList(options, out="__fz", up_to=True, label="play a spell from your trash"),
        O.Do(_unwrap("__fz")),
        O.If(Ref("__fz"), [O.PlayCard(Ref("__fz"), ignore="energy"), O.Do(mark)])], label=defn.name, source_text=defn.text)],
        "replace": True}


@script("Jayce, Man of Progress")
def jayce_progress(defn):
    # When you play me, you may kill a friendly gear. If you do, you may play a gear with Energy cost no more than [7]
    # from hand this turn, ignoring its Energy cost.
    def gear7(g, u):
        d = g.objects[u].base_defn()
        return d.type == "gear" and (d.energy or 0) <= 7 and g.objects[u].zone == "hand"
    return {"abilities": [Triggered("play_self", [
        O.If(lambda g, c: bool(Sel("gear", side="friendly").candidates(g, c)), [
            O.May([O.Choose(Sel("gear", side="friendly"), out="t", targeted=False), O.Kill(Ref("t")),
                   O.DelayedPassive("cost_reduce", {"energy": 99, "filter": gear7}, uses=1)],
                  label="kill a friendly gear")])], label=defn.name, source_text=defn.text)], "replace": True}


def _moves_this_turn(g, u):
    return g.objects[u].temp.get(("moves", g.turn), 0)


def _in_combat(g, u):
    o = g.objects[u]
    return g.combat is not None and o.zone == "board" and o.location == ("bf", g.combat["bf"])


@script("Sona, Harmonious")
def sona_harmonious(defn):
    # At the end of your turn, if I'm at a battlefield, ready up to 4 friendly runes. (errata, Origins)
    exhausted_runes = lambda g, c: [r for r in g.players[c.controller].runes if g.objects[r].exhausted]
    return {"abilities": [Triggered("end_turn", [O.ChooseFromList(exhausted_runes, out="__rr", n=4, up_to=True, label="ready up to 4 runes"),
                                                 O.Ready(Ref("__rr"))],
                                    cond=lambda g, s: _at_bf(g, s), label=defn.name, source_text=defn.text)], "replace": True}


@script("Volibear, Furious")
def volibear_furious(defn):
    # [Deflect 2]   (keyword)
    # When I attack, deal 5 damage split among any number of enemy units here.
    return {"abilities": [Triggered("attack_self", [O.Split(5, Ref("t"))],
                                    targets=[O.Choose(Sel("unit", side="enemy", where="here"), out="t", n=O.split_cap(5), up_to=True)],
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Yasuo, Windrider")
def yasuo_windrider(defn):
    # [Ganking]   (keyword)
    # The third time I move in a turn, you score 1 point.
    return {"abilities": [Triggered("move_self", [O.GainPoints(1)], filt=lambda g, s, ev: _moves_this_turn(g, s) == 3,
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Kayn, Unleashed")
def kayn_unleashed(defn):
    # [Ganking]   (keyword)
    # If I have moved twice this turn, I don't take damage.
    from ..abilities import Replacement
    return {"abilities": [Replacement("damage", lambda g, s, ev: ev.get("uid") == s and _moves_this_turn(g, s) >= 2,
                                      lambda g, s, ev: None, label=defn.name, source_text=defn.text)], "replace": True}


@script("Ambessa, The Wolf")
def ambessa_wolf(defn):
    # [Empower] [3][Body]   (keyword)
    # [Empowered][>] I have +3 [M] and can't be dealt damage unless I'm in combat.
    from ..abilities import Replacement
    emp = lambda g, s: bool(g.objects[s].empowered)
    return {"abilities": [Static("self", "might", 3, cond=emp, label="Empowered: +3 [M]", source_text=defn.text),
                          Replacement("damage", lambda g, s, ev: ev.get("uid") == s and emp(g, s) and not _in_combat(g, s),
                                      lambda g, s, ev: None, label="Empowered: no damage outside combat", source_text=defn.text)],
            "replace": True}


@script("Kai'Sa, Evolutionary")
def kaisa_evolutionary(defn):
    # [Ganking]   (keyword)
    # When I conquer, you may play a spell from your trash with Energy cost less than your points without paying its
    # Energy cost. Then recycle it.
    def options(g, c):
        pts = g.players[c.controller].points
        return [u for u in g.players[c.controller].trash if g.objects[u].base_defn().type == "spell"
                and (g.objects[u].base_defn().energy or 0) < pts]

    def mark(g, c):
        for it in g.chain:
            if it.uid == c.vars.get("played") and it.kind == "spell":
                it.ctx.vars["__recycle_after"] = True
    return {"abilities": [Triggered("conquer_self", [
        O.ChooseFromList(options, out="__ks", up_to=True, label="play a spell from your trash"),
        O.Do(_unwrap("__ks")),
        O.If(Ref("__ks"), [O.PlayCard(Ref("__ks"), ignore="energy"), O.Do(mark)])], label=defn.name, source_text=defn.text)],
        "replace": True}


@script("Udyr, Wildman")
def udyr_wildman(defn):
    # Spend my buff: Choose one you've not chosen this turn — Deal 2 to a unit at a battlefield. / Stun a unit at a
    # battlefield. / Ready me. / Give me [Ganking] this turn.
    at_bf = Sel("unit", where="battlefield")
    modes = [("Deal 2 to a unit at a battlefield", [O.Choose(at_bf, out="t"), O.Deal(2, Ref("t"))]),
             ("Stun a unit at a battlefield", [O.Choose(at_bf, out="t"), O.Stun(Ref("t"))]),
             ("Ready me", [O.Ready(Ref("self"))]),
             ("Give me [Ganking] this turn", [O.GiveKeyword(Ref("self"), "ganking", True, duration="turn")])]
    return {"abilities": [Activated({"energy": 0, "power": [], "spend_buff": True}, [O.ChooseMode(modes, exclude_used=True)],
                                    timing="main", label="spend my buff: choose one", source_text=defn.text)], "replace": True}


@script("Sett, Brawler")
def sett_brawler(defn):
    # When I'm played and when I conquer, buff me.
    # Spend my buff: Give me +4 [M] this turn.
    return {"abilities": [Triggered("play_self", [O.Buff(Ref("self"))], label=defn.name, source_text=defn.text),
                          Triggered("conquer_self", [O.Buff(Ref("self"))], label=defn.name, source_text=defn.text),
                          Activated({"energy": 0, "power": [], "spend_buff": True}, [O.GiveMight(Ref("self"), 4, duration="turn")],
                                    timing="main", label="spend my buff: +4 [M] this turn", source_text=defn.text)], "replace": True}


@script("Leona, Zealot")
def leona_zealot(defn):
    # If an opponent's score is within 3 points of the Victory Score, I enter ready.
    # Stunned enemy units here have -8 [M], to a minimum of 1 [M].
    from ..abilities import Replacement

    def near(g, s, ev):
        if ev.get("uid") != s:
            return False
        v = g.victory_score()
        me = g.objects[s].controller if g.objects[s].controller is not None else g.objects[s].owner
        return any(ps.points >= v - 3 for ps in g.players if not g.is_friendly(ps.idx, me))
    # the -8 [M] static line is parsed by the auto-scripter (kept: replace=False)
    return {"abilities": [Replacement("enter_ready", near, lambda g, s, ev: dict(ev, ready=True), label=defn.name, zone="any")],
            "replace": False}


@script("Twisted Fate, Gambler")
def twisted_fate_gambler(defn):
    # When I attack, reveal the top rune of your rune deck, then recycle it. Do one of the following based on its
    # domain: [Fury] — Deal 2 to an enemy unit here and 1 to all other enemy units here. [Mind] — Draw 1.
    # [Order] — Stun an enemy unit.
    def reveal(g, c):
        rd = g.players[c.controller].rune_deck
        r = rd[0] if rd else None
        c.vars["__dom"] = (g.objects[r].defn.domains or [None])[0] if r is not None else None
        if r is not None:
            g.emit("reveal", player=c.controller, cards=[r], ctx=c)
            g.do_recycle([r], c)
    dom = lambda d: (lambda g, c: c.vars.get("__dom") == d)
    enemy_here = Sel("unit", side="enemy", where="here")
    others = Sel("unit", side="enemy", where="here", pred=lambda g, c, u: u != c.vars.get("t"))
    return {"abilities": [Triggered("attack_self", [
        O.Do(reveal),
        O.If(dom("fury"), [O.Choose(enemy_here, out="t"), O.Deal(2, Ref("t")), O.Deal(1, others)]),
        O.If(dom("mind"), [O.Draw(1)]),
        O.If(dom("order"), [O.Choose(Sel("unit", side="enemy"), out="t"), O.Stun(Ref("t"))])],
        label=defn.name, source_text=defn.text)], "replace": True}


@script("Hwei, Brooding Painter")
def hwei(defn):
    # When I move, draw 1, then discard 1. Then, do the following based on the discarded card's type:
    # Spell — Draw 1. Gear — Ready up to 2 runes. Unit — Give me +3 [M] this turn.
    def typ(t):
        def f(g, c):
            d = c.vars.get("discarded") or ()
            return bool(d) and (t in g.objects[d[0]].base_defn().types)
        return f
    exhausted_runes = lambda g, c: [r for r in g.players[c.controller].runes if g.objects[r].exhausted]
    return {"abilities": [Triggered("move_self", [
        O.Draw(1), O.Discard(1),
        O.If(typ("spell"), [O.Draw(1)]),
        O.If(typ("gear"), [O.ChooseFromList(exhausted_runes, out="__hr", n=2, up_to=True, label="ready up to 2 runes"),
                           O.Ready(Ref("__hr"))]),
        O.If(typ("unit"), [O.GiveMight(Ref("self"), 3, duration="turn")])], label=defn.name, source_text=defn.text)],
        "replace": True}


@script("Vex, Cheerless")
def vex_cheerless(defn):
    # While I'm in combat, friendly spells cost [1][A] less to a minimum of [1], and enemy spells cost [1][A] more.
    def mod(g, src, uid, e, p, player):
        if not _in_combat(g, src) or g.objects[uid].base_defn().type != "spell":
            return e, p
        if g.is_friendly(player, g.objects[src].controller):
            total = e + len(p)
            if total <= 1:
                return e, p
            # reduce [1] then [A], never below a total of 1
            if e >= 1:
                e -= 1
                total -= 1
            if total > 1 and p:
                p = p[1:]
            return e, p
        return e + 1, list(p) + ["any"]
    return {"abilities": [Static("self", "rule", ("cost_mod_all", mod), label=defn.name, source_text=defn.text)], "replace": True}


@script("Jayce, Brilliant Inventor")
def jayce_brilliant(defn):
    # When you play me or the first time you play a non-token gear each turn, you may ready something besides me
    # that's exhausted.
    def first_gear(g, s, ev):
        if ev.get("kind") != "play" or ev.get("card_type") != "gear" or ev.get("player") != g.objects[s].controller:
            return False
        d = g.objects[ev["uid"]].base_defn()
        if d.is_token:
            return False
        gears = [u for u in g.players[ev["player"]].played_this_turn if u in g.objects and
                 g.objects[u].base_defn().type == "gear" and not g.objects[u].base_defn().is_token]
        return gears[:1] == [ev["uid"]]
    sel = Sel("permanent", pred=lambda g, c, u: u != c.source and g.objects[u].exhausted and g.objects[u].controller == c.controller)
    sel_any = Sel("card", pred=lambda g, c, u: g.objects[u].zone == "board" and u != c.source and g.objects[u].exhausted
                  and g.objects[u].controller == c.controller)
    eff = [O.If(lambda g, c: bool(sel_any.candidates(g, c)),
                [O.May([O.Choose(sel_any, out="t", targeted=False), O.Ready(Ref("t"))], label="ready something exhausted")])]
    return {"abilities": [Triggered("play_self", list(eff), label=defn.name, source_text=defn.text),
                          Triggered(first_gear, list(eff), label=defn.name, source_text=defn.text)], "replace": True}


@script("Draven, Audacious")
def draven_audacious(defn):
    # [Deflect]   (keyword)
    # The first time I win a combat each turn, you score 1 point.
    # When I die in combat, choose an opponent. They score 1 point.
    return {"abilities": [Triggered("win_combat_self", [O.GainPoints(1)], once_per_turn=True, label=defn.name, source_text=defn.text),
                          Triggered("die_self_combat", [O.ChoosePlayer(out="__opp", opponent=True),
                                                        O.GainPoints(1, player=Ref("__opp"))],
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Illaoi, Prophet of the Great Kraken")
def illaoi(defn):
    # When you play me or when I score, play a [1] [M] Tentacle unit token from Bilgewater.
    # I have +1 [M] for each token unit you control.
    tok = [O.PlayToken("Tentacle", loc="choose")]
    n = lambda g, s, u: _token_units(g, g.objects[s].controller)
    return {"abilities": [Triggered("play_self", list(tok), label=defn.name, source_text=defn.text),
                          Triggered("score_self", list(tok), label=defn.name, source_text=defn.text),
                          Static("self", "might", n, label="+1 [M] per token unit", source_text=defn.text)], "replace": True}


def _token_units(g, p):
    n = 0
    for x, o in g.objects.items():
        if o.zone == "board" and o.controller == p and o.defn.is_token and o.defn.type == "unit":
            n += 1
    return n


@script("Yone, Blademaster")
def yone(defn):
    # [Weaponmaster]   (keyword)
    # When I conquer an open battlefield / a battlefield that was uncontrolled, deal damage equal to my Might to an
    # enemy unit in a base.
    return {"abilities": [Triggered("conquer_self", [O.Deal(lambda g, c: g.chars(c.source).might or 0, Ref("t"))],
                                    targets=[O.Choose(Sel("unit", side="enemy", where="base"), out="t")],
                                    filt=lambda g, s, ev: g.conquered_from is None, label=defn.name, source_text=defn.text)],
            "replace": True}       # the auto-scripter's unconditional copy of this trigger made it fire twice


@script("Zed, Without a Sound")
def zed(defn):
    # When I conquer, play a 0 [M] Shadow Clone unit token to your base.
    # [Action][>] [1][Chaos]: Move me and a Shadow Clone you control to each other's locations.
    clone = Sel("unit", side="friendly", pred=lambda g, c, u: g.objects[u].defn.name == "Shadow Clone")
    return {"abilities": [Triggered("conquer_self", [O.PlayToken("Shadow Clone", loc="base")], label=defn.name, source_text=defn.text),
                          Activated({"energy": 1, "power": ["chaos"]}, [O.SwapLocations(Ref("self"), Ref("t"))],
                                    targets=[O.Choose(clone, out="t")], timing="action",
                                    label="swap with a Shadow Clone", source_text=defn.text)], "replace": True}


@script("Riven, Deserter")
def riven_deserter(defn):
    # When another friendly unit becomes exhausted, give me +1 [M] this turn.
    # Exhaust a friendly unit: Ready a unit. Use this ability only once each turn.
    def other_exhausted(g, s, ev):
        return ev.get("kind") == "exhaust" and ev.get("uid") != s and ev.get("uid") in g.objects and \
            g.objects[ev["uid"]].controller == g.objects[s].controller and "unit" in g.chars(ev["uid"]).types
    ready_friendly = Sel("unit", side="friendly", ready=True)
    return {"abilities": [Triggered(other_exhausted, [O.GiveMight(Ref("self"), 1, duration="turn")], label=defn.name, source_text=defn.text),
                          Activated({"energy": 0, "power": [], "exhaust_unit": ready_friendly}, [O.Ready(Ref("t"))],
                                    targets=[O.Choose(Sel("unit"), out="t")], timing="main", once_per_turn=True,
                                    label="exhaust a friendly unit: ready a unit", source_text=defn.text)], "replace": True}


@script("Master Yi, Unstoppable")
def master_yi_unstoppable(defn):
    # [Level 3][>] I cost [2][Calm] less. [Level 6][>] I cost [4][Calm][Calm] less instead.
    # [Level 11][>] I cost [6][Calm][Calm][Calm] less instead. [Level 16][>] I can't be chosen by enemy spells and abilities.
    def xp(g, u):
        o = g.objects[u]
        p = o.controller if o.controller is not None else o.owner
        return g.players[p].xp

    def mod(g, u, e, p):
        x = xp(g, u)
        n, k = (6, 3) if x >= 11 else (4, 2) if x >= 6 else (2, 1) if x >= 3 else (0, 0)
        p = list(p)
        for _ in range(k):
            if "calm" in p:
                p.remove("calm")
        return max(0, e - n), p
    return {"abilities": [PlayPermission("cost", cost_mod=mod, label="Level cost reduction", zone="any"),
                          Static("self", "keyword", ("untargetable", True), cond=lambda g, s: xp(g, s) >= 16,
                                 label="Level 16: can't be chosen by enemy spells and abilities", source_text=defn.text)],
            "replace": True}


@script("Renata Glasc, Mastermind")
def renata_mastermind(defn):
    # [1][Mind]: Draw 1. / [4][Mind][Mind][Mind][Mind], [T]: Score 1 point. / Use my abilities only while I'm at a battlefield.
    at_bf = lambda g, u: _at_bf(g, u)
    return {"abilities": [Activated({"energy": 1, "power": ["mind"]}, [O.Draw(1)], timing="main", restriction=at_bf,
                                    label="draw 1", source_text=defn.text),
                          Activated({"energy": 4, "power": ["mind"] * 4, "exhaust": True}, [O.GainPoints(1)], timing="main",
                                    restriction=at_bf, label="score 1 point", source_text=defn.text)], "replace": True}


@script("Nami, Headstrong")
def nami_headstrong(defn):
    # (lines 1-2 auto-scripted) When I hold, the next time you play a unit this turn, ready it and [Buff] it.
    def next_unit(g, c, ev):
        return ev.get("kind") == "play" and ev.get("card_type") == "unit" and ev.get("player") == c.controller
    eff = [O.Ready(lambda g, c: c.event.get("uid")), O.Buff(lambda g, c: c.event.get("uid"))]
    return {"abilities": [Triggered("hold_self", [O.Delayed(lambda g, s, ev: ev.get("kind") == "play", eff, filt=next_unit, expires="turn", once=True,
                                                            label="Nami: ready and buff the next unit")],
                                    label=defn.name, source_text=defn.text)], "replace": False}


@script("Ezreal, Prodigy")
def ezreal_prodigy(defn):
    # (line 1 auto-scripted) Optional additional costs you pay cost [1] or [A] less.
    return {"abilities": [Static("self", "rule", ("optional_cost_reduce",), label=defn.name, source_text=defn.text)], "replace": False}


def _grant_may_play(g, c, uid, zone, until_your_next_ending=False):
    """Let the controller play `uid` from `zone` (paying its costs) this turn, or until their next Ending Phase."""
    if uid is None or uid not in g.objects:
        return
    p = c.controller
    until = g.turn
    if until_your_next_ending and g.turn_player != p:
        until = g.turn + 1
    g.add_turn_effect(c, "may_play", {"uid": uid, "zone": zone, "until_turn": until}, expires=None)


def _banish_top_may_play(g, c):
    """Banish the top card of your Main Deck. Until your next Ending Phase, you may play that card."""
    deck = g.players[c.controller].deck
    if not deck:
        return
    u = deck[0]
    g.do_banish([u], c)
    _grant_may_play(g, c, u, "banish", until_your_next_ending=True)


@script("Akali, Brash")
def akali_brash(defn):
    # The first time I move each turn, [Add] [1][A].
    # The second time I move each turn, banish the top card of your Main Deck. Until your next Ending Phase, you may
    # play that card. (You still pay its costs.)
    return {"abilities": [Triggered("move_self", [O.Add(1, ["any"])], filt=lambda g, s, ev: _moves_this_turn(g, s) == 1,
                                    label=defn.name, source_text=defn.text),
                          Triggered("move_self", [O.Do(_banish_top_may_play)], filt=lambda g, s, ev: _moves_this_turn(g, s) == 2,
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Runeblade Anvil")
def runeblade_anvil(defn):
    # When you play this or when this leaves the board, banish the top card of your Main Deck. Until your next
    # Ending Phase, you may play that card. (You still pay its costs.)
    # [2][Chaos], [T]: Kill this.  (activated line auto-scripted)
    return {"abilities": [Triggered("play_self", [O.Do(_banish_top_may_play)], label=defn.name, source_text=defn.text),
                          Triggered("leave_self", [O.Do(_banish_top_may_play)], label=defn.name,
                                    source_text=defn.text)], "replace": False}


@script("Clocktower Guardian")
def clocktower_guardian(defn):
    # (line 1 auto-scripted) When you play me or when I hold, [Predict 3].
    # [Deathknell][>] Banish the top card of your Main Deck. You may play it, ignoring its Energy cost.
    def banish_top(g, c):
        deck = g.players[c.controller].deck
        c.vars["__ctg"] = deck[0] if deck else None
        if deck:
            g.do_banish([deck[0]], c)
    return {"abilities": [Triggered("die_self", [O.Do(banish_top), O.If(O.has_var("__ctg"), [O.May([O.PlayCard(Ref("__ctg"), ignore="energy")],
                                                                                    label="play the banished card")])], zone="any",
                                    label="Deathknell: banish the top card, you may play it", source_text=defn.text,
                                    keyword="deathknell")], "replace": False}


@script("Heartening Soul")
def heartening_soul(defn):
    # (line 1 auto-scripted) When you play me, ready a friendly legend.
    # Friendly legends have "[T]: Give a unit +3 [M] this turn."
    pump = Activated({"energy": 0, "power": [], "exhaust": True}, [O.GiveMight(Ref("t"), 3)],
                     targets=[O.Choose(Sel("unit"), out="t", targeted=True)],
                     label="[T]: Give a unit +3 [M] this turn.", source_text="[T]: Give a unit +3 [M] this turn.")
    return {"abilities": [Static(Sel("legend", side="friendly"), "ability", pump, label=defn.name, source_text=defn.text)],
            "replace": False}


@script("Kennen, Storm of Shuriken")
def kennen_storm(defn):
    # (line 1 auto-scripted) When I conquer, give a spell in your trash [Flow] equal to its cost this turn.
    spells = lambda g, c: [u for u in g.players[c.controller].trash if g.objects[u].base_defn().type == "spell"]
    return {"abilities": [Triggered("conquer_self", [
        O.ChooseFromList(spells, out="__kn", label="give a spell in your trash [Flow]"),
        O.Do(lambda g, c: _grant_may_play(g, c, c.vars.get("__kn"), "trash"))], label=defn.name, source_text=defn.text)],
        "replace": False}


@script("Jhin, Meticulous Killer")
def jhin_meticulous(defn):
    # [Vision]   (keyword)
    # If you've spent [4] or more to play a spell this turn, you may play me for [Mind].
    def mod(g, u, e, p):
        o = g.objects[u]
        q = o.controller if o.controller is not None else o.owner
        if g.turn_memo.get(("spell_spent_4", q)):
            return 0, ["mind"]
        return e, p
    return {"abilities": [PlayPermission("cost", cost_mod=mod, label="play me for [Mind]", zone="any")], "replace": True}


@script("LeBlanc, Everywhere at Once")
def leblanc_everywhere(defn):
    # [Backline]   (keyword)
    # Your [Temporary] effects at my battlefield don't trigger.
    return {"abilities": [Static("self", "rule", ("no_temporary_here",), label=defn.name, source_text=defn.text)], "replace": True}


@script("Kayle, Justified")
def kayle_justified(defn):
    # [Empower] [3]   (keyword)
    # I can be [Empowered] up to three times. I have +2 [M] for each time I'm [Empowered].
    # While I'm [Empowered] three times, I have [Deflect 3] and [Ganking].
    three = lambda g, s: g.objects[s].empowered >= 3
    return {"abilities": [Static("self", "rule", ("max_empower", 3), label="can be Empowered up to three times", source_text=defn.text),
                          Static("self", "might", lambda g, s, u: 2 * g.objects[s].empowered, label="+2 [M] per Empowered",
                                 source_text=defn.text),
                          Static("self", "keyword", ("deflect", 3), cond=three, label="[Deflect 3] at three", source_text=defn.text),
                          Static("self", "keyword", ("ganking", True), cond=three, label="[Ganking] at three", source_text=defn.text)],
            "replace": True}


@script("Jax, Unmatched")
def jax_unmatched(defn):
    # [Deflect]   (keyword)
    # Errata (Spiritforged): Your Equipment everywhere have [Quick-Draw]. (CR 819.1.d: [Reaction] and "When you play
    # this, attach it to a unit you control.") Not only from hand: an Equipment played from the trash, from face down
    # or by an effect has it too.
    def granted_quick_draw_play(g, s, ev):
        if ev.get("kind") != "play" or ev.get("player") != g.objects[s].controller or ev.get("token"):
            return False
        d = g.objects[ev["uid"]].base_defn()
        return d.is_equipment and not d.keywords.get("quick_draw")
    return {"abilities": [Static("self", "rule", ("hand_equipment_quick_draw",), label=defn.name, source_text=defn.text),
                          Triggered(granted_quick_draw_play, [O.Attach(lambda g, c: c.event.get("uid"), Ref("t"))],
                                    targets=[O.Choose(Sel("unit", side="friendly"), out="t", targeted=True)],
                                    label="Quick-Draw (Jax)", source_text=defn.text)], "replace": True}


@script("Ziggs, Short-Fused")
def ziggs(defn):
    # (line 1 auto-scripted) Abilities of friendly gear deal 1 Bonus Damage.
    return {"abilities": [Static("self", "rule", ("bonus_damage_gear_abilities", 1), label=defn.name, source_text=defn.text)],
            "replace": False}


@script("Jarvan IV, Martial Paragon")
def jarvan_paragon(defn):
    # Your gear with [Deploy] have [Action].
    # When I conquer, if there is a friendly gear with [Deploy] here, channel 1 rune exhausted.
    def deploy_gear_here(g, c):
        me = g.objects[c.source]
        return any(o.zone == "board" and o.location == me.location and o.controller == c.controller and
                   "gear" in g.chars(u).types and o.base_defn().keywords.get("deploy") for u, o in g.objects.items())
    return {"abilities": [Static("self", "rule", ("deploy_gear_action",), label="your [Deploy] gear have [Action]", source_text=defn.text),
                          Triggered("conquer_self", [O.Channel(1, exhausted=True)], intervening=deploy_gear_here,
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Sivir, Mercenary")
def sivir_mercenary(defn):
    # [Accelerate]   (keyword)
    # If you've spent at least [A][A] this turn, I have +2 [M] and [Ganking].
    spent2 = lambda g, s: g.turn_memo.get(("spent", g.objects[s].controller), [0, 0])[1] >= 2
    return {"abilities": [Static("self", "might", 2, cond=spent2, label="spent [A][A]: +2 [M]", source_text=defn.text),
                          Static("self", "keyword", ("ganking", True), cond=spent2, label="spent [A][A]: [Ganking]",
                                 source_text=defn.text)], "replace": True}


@script("Irelia, Graceful")
def irelia_graceful(defn):
    # Your spells that choose me cost [1] or [A] less.   (applied once the spell's choices are made, flow._FinalizeCosts)
    return {"abilities": [Static("self", "rule", ("spells_choosing_me_cost_less", 1), label=defn.name, source_text=defn.text)],
            "replace": True}


@script("Seraphine, Inspiring")
def seraphine_inspiring(defn):
    # [Disarm 2]   (keyword)
    # Once each turn, when you exhaust three or more friendly units at the same time, you may draw 1.
    def three_at_once(g, s, ev):
        return ev.get("kind") == "exhaust" and ev.get("player") == g.objects[s].controller and ev.get("units_in_batch") == 3
    return {"abilities": [Triggered(three_at_once, [O.May([O.Draw(1)], label="draw 1")], once_per_turn=True,
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Orianna, Mechanical Marvel")
def orianna_marvel(defn):
    # Once each turn, while I'm at a battlefield, you may pay [1][A] less to play a gear.
    # (Applied to the first gear you play while she is at a battlefield: the saving is the same for every gear.)
    def applies(g, src, uid, p):
        return _at_bf(g, src) and g.objects[uid].base_defn().type == "gear"
    return {"abilities": [Static("self", "rule", ("cost_reduce_once", applies), label=defn.name, source_text=defn.text)],
            "replace": True}


@script("Aphelios, Exalted")
def aphelios_exalted(defn):
    # When you attach an Equipment to me, choose one that hasn't been chosen this turn — Ready 2 runes. / Channel 1 rune
    # exhausted. / [Buff] a friendly unit.
    exhausted_runes = lambda g, c: [r for r in g.players[c.controller].runes if g.objects[r].exhausted]

    def equipment_attached(g, s, ev):
        return ev.get("kind") == "attach" and ev.get("to") == s and ev.get("uid") in g.objects and \
            g.objects[ev["uid"]].base_defn().is_equipment
    modes = [("Ready 2 runes", [O.ChooseFromList(exhausted_runes, out="__ar", n=2, label="ready 2 runes"), O.Ready(Ref("__ar"))]),
             ("Channel 1 rune exhausted", [O.Channel(1, exhausted=True)]),
             ("Buff a friendly unit", [O.Choose(Sel("unit", side="friendly"), out="t"), O.Buff(Ref("t"))])]
    return {"abilities": [Triggered(equipment_attached, [O.ChooseMode(modes, exclude_used=True)], label=defn.name,
                                    source_text=defn.text)], "replace": True}


@script("Ivern, Friend to All")
def ivern_friend(defn):
    # As you play me, choose Bird, Cat, Dog, or Poro. I gain that tag.
    # When I conquer or hold, score 1 point if your units have all of the following tags among them — Bird, Cat, Dog, and Poro.
    pets = ("Bird", "Cat", "Dog", "Poro")
    choose_tag = [O.ChooseMode([(t, [O.GiveTag(Ref("self"), t, duration="permanent")]) for t in pets])]

    def all_pets(g, c):
        tags = set()
        for u, o in g.objects.items():
            if o.zone == "board" and o.controller == c.controller and "unit" in g.chars(u).types:
                tags |= set(g.chars(u).tags)
        return all(t in tags for t in pets)
    score = [O.If(all_pets, [O.GainPoints(1)])]
    return {"abilities": [PlayPermission("as_play", value=choose_tag, label="choose Bird, Cat, Dog, or Poro"),
                          Triggered("conquer_self", list(score), label=defn.name, source_text=defn.text),
                          Triggered("hold_self", list(score), label=defn.name, source_text=defn.text)], "replace": True}


@script("Teemo, Strategist")
def teemo_strategist(defn):
    # Errata (Origins): "[Hidden] When I defend, choose an enemy unit here and reveal the top 5 cards of your Main Deck.
    # Deal 1 to that unit for each card with [Hidden] revealed this way, then recycle the revealed cards."
    # The unit is chosen as the trigger goes on the chain (CR 355.5); one Deal of N (418.8), none for 0 (715.4).
    hidden_n = lambda g, c: sum(1 for u in c.vars.get("looked", []) if g.objects[u].base_defn().keywords.get("hidden"))
    eff = [O.Choose(Sel("unit", side="enemy", where="here"), out="t"),
           O.Look(5, out="looked", reveal=True),
           O.If(lambda g, c: hidden_n(g, c) > 0, [O.Deal(hidden_n, Ref("t"))]),
           O.Recycle(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"])]
    return {"abilities": [Triggered("defend_self", eff, label=defn.name, source_text=defn.text)], "replace": True}


@script("Rek'Sai, Swarm Queen")
def reksai_swarm_queen(defn):
    # Errata (Spiritforged): When I attack, you may reveal the top 2 cards of your Main Deck. You may banish one, then
    # play it. If it is a unit, you may play it here. Recycle the rest.
    # The card is banished first and played from there (paying its cost, CR 420.3.b); one that can't be played stays
    # banished (CR 420.3.c).
    def pick(g, c):
        return list(c.vars.get("looked", []))

    def is_unit(g, c):
        u = c.vars.get("__rq")
        return u in g.objects and g.objects[u].base_defn().is_unit
    here_or_usual = lambda g, c, l: l == c.here or l in O._unit_play_locations(g, c.controller)
    body = [O.Look(2, out="looked", reveal=True),
            O.ChooseFromList(pick, out="__rq", up_to=True, label="banish one of the revealed cards, then play it"),
            O.Do(_unwrap("__rq")),
            O.If(Ref("__rq"), [
                O.Banish(Ref("__rq")),
                O.If(is_unit, [O.ChooseLocation(out="__rql", include_bases=True, pred=here_or_usual, label="Play it where?"),
                               O.PlayCard(Ref("__rq"), loc=Ref("__rql"))],
                     [O.PlayCard(Ref("__rq"))])]),
            O.Recycle(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"])]
    return {"abilities": [Triggered("attack_self", [O.May(body, label="reveal the top 2 cards")], label=defn.name,
                                    source_text=defn.text)], "replace": True}


@script("Karthus, Eternal")
def karthus_eternal(defn):
    # Your [Deathknell] effects trigger an additional time.
    return {"abilities": [Static("self", "rule", ("deathknell_twice",), label=defn.name, source_text=defn.text)], "replace": True}


@script("Gangplank, Naval")
def gangplank_naval(defn):
    # [Empower] [Body][Body]   (keyword)
    # [Empowered][>] If a spell or ability that chooses me would stun me, give me -[M], or return me to hand,
    # give me +3 [M] this turn instead.   (errata 2026-10-27; engine: Game._chosen_harm_redirect)
    emp = lambda g, s: bool(g.objects[s].empowered)
    return {"abilities": [Static("self", "rule", ("chosen_harm_to_might", 3), cond=emp,
                                 label="Empowered: +3 [M] instead of stun / -[M] / return to hand", source_text=defn.text)],
            "replace": True}


@script("Mel, Newly Awakened")
def mel_newly_awakened(defn):
    # When you play me, draw 1.   [Empower] [3]   (auto-scripted, kept: replace=False)
    # [Empowered][>] Your spells and abilities can't be countered. If a spell or ability you control would give -[M]
    # to a unit it chooses, it gives an additional -1 [M].
    emp = lambda g, s: bool(g.objects[s].empowered)
    return {"abilities": [Static("self", "rule", ("my_spells_abilities_uncounterable",), cond=emp,
                                 label="Empowered: your spells and abilities can't be countered", source_text=defn.text),
                          Static("self", "rule", ("chosen_minus_might_extra", 1), cond=emp,
                                 label="Empowered: -[M] to a chosen unit is 1 more", source_text=defn.text)],
            "replace": False}


@script("Ahri, Confident")
def ahri_confident(defn):
    # [Disarm]   (keyword)
    # When you reduce the Might of an enemy unit here by 1 or more, give me +1 [M] this turn.
    # Ruling (Radiance patch notes): any non-zero -[M] applied by an object you control counts, including a static
    # -[M] that starts applying (Game._check_static_might_reductions).
    def reduced_here(g, s, ev):
        me = g.objects[s]
        return (ev.get("kind") == "might_reduced" and ev.get("by") == me.controller and ev.get("amount", 0) >= 1
                and ev.get("player") is not None and not g.is_friendly(ev["player"], me.controller)
                and ev.get("loc") == me.location)
    return {"abilities": [Static("self", "rule", ("watch_might_reductions",), label="watches -[M]"),
                          Triggered(reduced_here, [O.GiveMight(Ref("self"), 1)], label=defn.name, source_text=defn.text)],
            "replace": True}


def _mark_played(var, key, value):
    """After PlayCard stored the played uid in ctx.vars[var], set key on its chain item's ctx."""
    def run(g, c):
        for it in g.chain:
            if it.uid == c.vars.get(var) and it.uid is not None:
                it.ctx.vars[key] = value(g, c) if callable(value) else value
    return run


@script("Rell, Magnetic")
def rell_magnetic(defn):
    # [Tank]   (keyword)
    # When I attack, you may play an Equipment with Energy cost no more than [2], ignoring its cost, and attach it to me.
    def options(g, c):
        return [u for u in g.players[c.controller].hand if g.objects[u].base_defn().is_equipment
                and (g.objects[u].base_defn().energy or 0) <= 2]
    body = [O.ChooseFromList(options, out="__eq", up_to=True, label="play an Equipment costing [2] or less"),
            O.Do(_unwrap("__eq")),
            O.If(Ref("__eq"), [O.PlayCard(Ref("__eq"), ignore="all", out="__eqp"),
                               O.Do(_mark_played("__eqp", "__attach_to", lambda g, c: c.source))])]
    return {"abilities": [Triggered("attack_self", [O.If(lambda g, c: bool(options(g, c)), body)],
                                    label=defn.name, source_text=defn.text)], "replace": True}


@script("Ashe, Focused")
def ashe_focused(defn):
    # When you play me, choose an opponent. They reveal their hand. Choose a card revealed this way and banish it.
    # When they hold, return it to their hand (even if I'm no longer on the board).
    def reveal(g, c):
        p = c.vars.get("__opp")
        if p is not None:
            g.emit("reveal", player=p, cards=list(g.players[p].hand), ctx=c)

    def their_hold(g, s, ev):
        return ev.get("kind") == "hold"

    back = [O.ToHand(lambda g, c: [c.vars["__ab"]] if c.vars.get("__ab") in g.objects
                     and g.objects[c.vars["__ab"]].zone == "banish" else [])]
    return {"abilities": [Triggered("play_self", [
        O.ChoosePlayer(out="__opp", opponent=True),
        O.Do(reveal, label="reveal hand"),
        O.Choose(lambda g, c: list(g.players[c.vars["__opp"]].hand) if c.vars.get("__opp") is not None else [],
                 out="__ab", targeted=False),
        O.If(Ref("__ab"), [O.Banish(Ref("__ab")),
                           O.Delayed(their_hold, back, filt=lambda g, c, ev: ev.get("player") == c.vars.get("__opp"),
                                     expires=None, once=True, label="Ashe: return the banished card")])],
        label=defn.name, source_text=defn.text)], "replace": True}


@script("Sivir, Ambitious")
def sivir_ambitious(defn):
    # [Deflect 2]   (keyword)
    # When I conquer after an attack, if you assigned 5 or more excess damage to enemy units, you may deal that much
    # to an enemy unit.   (excess of this combat: flow turn_memo ("combat_excess", player))
    def conquer_after_attack(g, s, ev):
        me = g.objects[s]
        return (ev.get("kind") == "conquer" and s in ev.get("units", ()) and g.combat is not None
                and g.combat["attacker"] == me.controller and g.turn_memo.get(("combat_excess", me.controller), 0) >= 5)
    amount = lambda g, c: c.vars.get("__sx", 0)
    store = O.Do(lambda g, c: c.vars.__setitem__("__sx", g.turn_memo.get(("combat_excess", c.controller), 0)))
    # the "you may" and the enemy unit are settled as the trigger is finalized (CR 383.3.a, 355)
    return {"abilities": [Triggered(conquer_after_attack, [
        O.May([O.Choose(Sel("unit", side="enemy"), out="t"), store, O.Deal(amount, Ref("t"))], label="deal the excess to an enemy unit")],
        label=defn.name, source_text=defn.text)], "replace": True}


@script("Soraka, Wanderer")
def soraka_wanderer(defn):
    # I must be assigned combat damage last.
    # If another unit you control here would die, if it has less Might than me, instead heal it, exhaust it, and
    # recall it.
    from ..abilities import Replacement

    def saves(g, s, ev):
        me = g.objects[s]
        u = ev.get("uid")
        if u == s or u not in g.objects or ev.get("card_type") != "unit":
            return False
        o = g.objects[u]
        return (o.controller == me.controller and o.location == me.location
                and (g.chars(u).might or 0) < (g.chars(s).might or 0))
    return {"abilities": [Static("self", "rule", ("assigned_damage_last",), label="assigned combat damage last",
                                 source_text=defn.text),
                          Replacement("die", saves, lambda g, s, ev: dict(ev, replaced_with="recall", exhaust=True),
                                      label=defn.name, source_text=defn.text)], "replace": True}


@script("Azir, Ascendant")
def azir_ascendant(defn):
    # [Calm]: [Action] — Choose a unit you control. Move me to its location and it to my original location. If it's
    # equipped, you may attach one of its Equipment to me. Use only once per turn.
    def its_equipment(g, c):
        t = c.vars.get("t")
        return [a for a in (g.objects[t].attachments if t in g.objects else ())
                if g.objects[a].base_defn().is_equipment] if t is not None else []
    eff = [O.SwapLocations(Ref("self"), Ref("t")),
           O.If(lambda g, c: bool(its_equipment(g, c)), [
               O.ChooseFromList(its_equipment, out="__eq", up_to=True, label="attach one of its Equipment to me"),
               O.Do(_unwrap("__eq")),
               O.If(Ref("__eq"), [O.Attach(Ref("__eq"), Ref("self"))])])]
    return {"abilities": [Activated({"energy": 0, "power": ["calm"]}, eff,
                                    targets=[O.Choose(Sel("unit", side="friendly", other=True), out="t")],
                                    timing="action", once_per_turn=True, label="swap places with a unit you control",
                                    source_text=defn.text)], "replace": True}


@script("Rumble, Hotheaded")
def rumble_hotheaded(defn):
    # Your Mechs each have [Assault].   (auto-scripted static, kept: replace=False)
    # When I conquer, you may recycle another friendly unit to play a Mech from your trash. Reduce its Energy cost by
    # the Might of the unit you recycled.
    def mechs(g, c):
        return [u for u in g.players[c.controller].trash if g.objects[u].base_defn().is_unit
                and "Mech" in g.objects[u].base_defn().tags]

    def others(g, c):
        return [u for u, o in g.objects.items() if u != c.source and o.zone == "board" and o.controller == c.controller
                and "unit" in g.chars(u).types]

    def remember(g, c):
        c.vars["__rm"] = g.chars(c.vars["__rr"]).might or 0

    def cost(g, c):
        u = c.vars.get("__mech")
        e, pw = g.card_cost(c.controller, u, "trash", None)
        return (max(0, e - c.vars.get("__rm", 0)), pw)
    # "recycle another friendly unit to ..." is the trigger's base cost (CR 383.3.b): decided and paid as the trigger
    # is finalized (the unit is not a target); the Mech is picked and played on resolution.
    from ..targeting import _TriggerMay
    may = O.May([], label="recycle another friendly unit", out="__may")
    body = [O.ChooseFromList(mechs, out="__mech", label="play a Mech from your trash"),
            O.Do(_unwrap("__mech")),
            O.If(Ref("__mech"), [O.PlayCard(Ref("__mech"), alt_cost=cost)])]
    return {"abilities": [Triggered("conquer_self", body,
        targets=[_TriggerMay(may, pre=[lambda g, c: bool(mechs(g, c)) and bool(others(g, c))]),
                 O.Choose(others, out="__rr", targeted=False, label="recycle"), O.Do(remember), O.Recycle(Ref("__rr"))],
        label=defn.name, source_text=defn.text)], "replace": False}


@script("Akshan, Mischievous")
def akshan_mischievous(defn):
    # [Weaponmaster]   You may pay [Body][Body] as an additional cost to play me.   (auto, kept: replace=False)
    # When you play me, if you paid the additional cost, move an enemy gear to your base. You control it until I leave
    # the board. If it's an Equipment, attach it to me.
    def steal(g, c):
        t = c.vars.get("t")
        o = g.objects.get(t)
        me = g.objects.get(c.source)
        if o is None or o.zone != "board" or me is None:
            return
        if o.attached_to is not None:
            g.do_detach(t, c)
        o.location = ("base", c.controller)
        g.log("move", uid=t, to=o.location)
        # CR 359.3 example: if Akshan already left the board, "You control it until I leave the board" is never
        # generated: the gear is still moved, and the cleanup recalls it to its controller's base (CR 323.6)
        if o.controller != c.controller and me.zone == "board":
            prev = o.controller
            o.controller = c.controller
            from ..objects import Mod
            o.mods.append(Mod("control", prev, ("until_leaves", c.source, me.entered_stamp), c.source, g.tick()))
        g.restruct()
        g.dirty = True
        if o.base_defn().is_equipment and me.zone == "board":
            g.do_attach(t, c.source, c)
    return {"abilities": [Triggered("play_self", [O.Choose(Sel("gear", side="enemy"), out="t"), O.Do(steal, label="take the gear")],
                                    filt=lambda g, s, ev: bool((ev.get("paid") or {}).get("add")),
                                    label=defn.name, source_text=defn.text)], "replace": False}


@script("Heimerdinger, Inventor")
def heimerdinger_inventor(defn):
    # I have all [T] abilities of all friendly legends, units, and gear.
    # (printed/scripted abilities of the other objects: reading their granted abilities would recurse through layers)
    def tap_abilities(g, s, u):
        me = g.objects[s]
        out = []
        for x, o in g.objects.items():
            if x == s or o.zone != "board" or o.controller != me.controller:
                continue
            d = o.base_defn()
            if not (d.type in ("legend", "unit", "gear") or d.is_unit or d.is_gear):
                continue
            if d.name == defn.name:
                continue
            for ab in d.abilities:
                if isinstance(ab, Activated) and ab.cost.get("exhaust") and ab not in out:
                    out.append(ab)
        return out
    return {"abilities": [Static("self", "abilities", tap_abilities, label="all friendly [T] abilities",
                                 source_text=defn.text)], "replace": True}


@script("Nocturne, Horrifying")
def nocturne_horrifying(defn):
    # [Ganking]   (keyword)
    # Errata: As you look at or reveal me from the top of your deck, you may banish me. If you do, you may play me
    # for [A].   (ops._nocturne_step, asked from Look/Predict as the cards are seen)
    return {"abilities": [PlayPermission("as_seen_from_deck", zone="deck", label="banish me and play me for [A]",
                                         source_text=defn.text)], "replace": True}


@script("Neeko, Blending In")
def neeko_blending_in(defn):
    # Errata: If Neeko is in your deck, choose up to 3 different legends in addition to your starting legend.
    #   (Deck.extra_legends, chosen at deckbuilding)
    # When you play me, choose one of those Legends and add it to your Legend Zone while I'm on the board.
    # Ruling: the legends enter ready; at most one of each on the board; they cease to exist when Neeko leaves.
    def options(g, c):
        names = g.extra_legends.get(c.controller, ())
        on_board = {o.defn.name for o in g.objects.values() if o.zone == "board" and o.controller == c.controller}
        out = []
        for n in names:
            d = g.db.card(n)
            if d.name not in on_board:
                out.append(d.name)
        return out

    def add(g, c):
        n = c.vars.get("__nl")
        me = g.objects.get(c.source)
        if n is None or me is None or me.zone != "board":
            return
        o = g._new_obj(g.db.card(n), c.controller)
        o.zone, o.location, o.controller = "board", ("legend", c.controller), c.controller
        o.exhausted = False
        o.entered_stamp = g.tick()
        o.temp["bound_to"] = (c.source, me.entered_stamp)
        g.restruct()
        g.log("legend_added", uid=o.uid, name=n, player=c.controller)
        g.dirty = True
    return {"abilities": [Triggered("play_self", [
        O.ChooseFromList(options, out="__nl", label="add a legend to your Legend Zone"),
        O.Do(_unwrap("__nl")), O.Do(add, label="add the legend")], label=defn.name, source_text=defn.text)],
        "replace": True}


@script("Elnuk Herd")
def elnuk_herd(defn):
    # [Hidden]  When you play me, give a friendly unit +3 [M] this turn, then recycle me if I was played from face down.
    # (errata, Radiance: "a friendly unit", so it may be me.) The auto-scripter read "me if I was played from face
    # down" as a unit to choose and recycled that unit.
    return {"abilities": [Triggered("play_self", [
        O.GiveMight(Ref("t"), 3),
        O.If(lambda g, c: (c.vars.get("ev") or {}).get("from_zone") == "facedown", [O.Recycle(Ref("self"))])],
        targets=[O.Choose(Sel("unit", side="friendly"), out="t")], label=defn.name, source_text=defn.text)], "replace": True}


@script("Dark Child, Starter")
def dark_child_starter(defn):
    # At the end of your turn, ready up to 2 runes. (errata, Origins; your own runes: you can only ready what you control)
    return {"abilities": [Triggered("end_turn", [
        O.Choose(Sel("rune", side="friendly", exhausted=True), out="__r", n=2, up_to=True, targeted=False),
        O.Ready(Ref("__r"))], label=defn.name, source_text=defn.text)], "replace": True}


@script("Karma, Channeler")
def karma_channeler(defn):
    # [Vision]  When you recycle one or more cards to your Main Deck, buff a friendly unit. (errata, Origins: runes
    # recycled to the rune deck, e.g. to pay for power, don't count)
    def to_main(g, s, ev):
        if ev.get("kind") != "recycle" or ev.get("to") != "deck" or ev.get("player") != g.objects[s].controller:
            return False
        seen = g.objects[s].temp.setdefault(("batches", "karma"), set())
        if ev.get("batch") in seen:
            return False
        seen.add(ev.get("batch"))
        return True
    return {"abilities": [Triggered(to_main, [O.Buff(Ref("t"))], targets=[O.Choose(Sel("unit", side="friendly"), out="t")],
                                    label=defn.name, source_text=defn.text)], "replace": True}


# ----------------------------------------------------------------------------- Sett
@script("The Boss", "Sett, The Boss")
def the_boss(defn):
    # Errata (Origins errata): If a buffed unit you control would die, you may pay [C], exhaust me, and spend its buff
    # to heal it, exhaust it, and recall it instead. (Send it to base. This isn't a move.) When you conquer, ready me.
    # [C] on a Body/Order card is one Body or Order power (CR 135.2.e.6.c). An optional replacement (CR 369-372): each
    # option is one distinct way to pay; the cost is paid as the replacement is applied.
    from .. import payment

    def doms(g, s):
        d = list(g.objects[s].base_defn().domains or ())
        return d or ["any"]

    def purpose(g, s):
        return {"kind": "ability", "types": {"legend"}, "uid": s}

    def applies(g, s, ev):
        me, u = g.objects[s], ev.get("uid")
        o = g.objects.get(u)
        return (not ev.get("replaced_with") and o is not None and o.zone == "board" and o.controller == me.controller
                and "unit" in g.chars(u).types and o.buffs > 0)

    def options(g, s, ev):
        me = g.objects[s]
        if me.exhausted:
            return []
        seen, out = set(), []
        for d in doms(g, s):
            for pl in g.payment_plans(me.controller, 0, [d], purpose=purpose(g, s)):
                if pl not in seen:
                    seen.add(pl)
                    out.append(pl)
        return out

    def option_label(g, s, plan):
        return "pay [C], exhaust Sett and spend its buff to recall it (" + payment.plan_label(g, plan) + ")"

    def replace(g, s, ev, plan):
        me = g.objects[s]
        g.apply_payment(me.controller, plan, None, purpose=purpose(g, s))
        g.do_exhaust(s)
        g.do_spend_buff(ev["uid"])
        return dict(ev, replaced_with="recall", exhaust=True)

    def conquer(g, s, ev):
        return ev.get("kind") == "conquer" and ev.get("player") == g.objects[s].controller

    return {"abilities": [
        Replacement("die", applies, replace, optional=True, options=options, option_label=option_label,
                    label="Sett: pay [C], exhaust me and spend its buff to heal, exhaust and recall it instead",
                    source_text=defn.text),
        Triggered(conquer, [O.Do(lambda g, c: g.do_ready(c.source, c))],
                  label="Sett: when you conquer, ready me", source_text=defn.text)], "replace": True}


# ----------------------------------------------------------------------------- post-ban deck refresh (2026-11-27)
@script("Forge of the Fluft")
def forge_of_the_fluft(defn):
    # While you control this battlefield, friendly legends have "[T]: Attach an Equipment you control to a unit you
    # control." (A battlefield's controller is its card's controller, CR 190.6.d: with no controller no legend has it.)
    equipment = Sel("gear", side="friendly", pred=lambda g, c, u: "Equipment" in g.chars(u).tags)
    attach = Activated({"energy": 0, "power": [], "exhaust": True},
                       [O.Choose(equipment, out="__eq", targeted=False),
                        O.Choose(Sel("unit", side="friendly"), out="__eu", targeted=False),
                        O.Attach(Ref("__eq"), Ref("__eu"))],
                       label="[T]: Attach an Equipment you control to a unit you control.",
                       source_text="[T]: Attach an Equipment you control to a unit you control.")
    return {"abilities": [Static(Sel("legend", side="friendly"), "ability", attach, label=defn.name, source_text=defn.text)],
            "replace": False}


@script("Kharox")
def kharox(defn):
    # [Empower] [6][Chaos][Chaos]  (keyword, kept)
    # When I become [Empowered], choose an opponent. They [Burn 3]. Then you may do this: Choose a unit in their trash
    # and play it, ignoring its cost.
    def their_units(g, c):
        p = c.vars.get("__opp")
        if p is None:
            return []
        return [u for u in g.players[p].trash if g.objects[u].base_defn().is_unit]
    return _keep([Triggered("empowered_self", [
        O.ChoosePlayer(out="__opp", opponent=True),
        O.Burn(3, player=Ref("__opp")),
        O.May([O.Choose(their_units, out="__kx", targeted=False),
               O.PlayCard(Ref("__kx"), ignore="all")],
              label="choose a unit in their trash and play it, ignoring its cost")],
        label=defn.name, source_text=defn.text)])


@script("Tail-Cloaked Matriarch")
def tail_cloaked_matriarch(defn):
    # [Empower] [2][Chaos]  (keyword, kept)
    # When I become [Empowered], you may choose a unit in your trash with Energy cost no more than [3] and Power cost
    # no more than [A]. Play it to your base, ignoring its cost.
    def small_units(g, c):
        out = []
        for u in g.players[c.controller].trash:
            d = g.objects[u].base_defn()
            if d.is_unit and (d.energy or 0) <= 3 and (d.power or 0) <= 1:
                out.append(u)
        return out
    return _keep([Triggered("empowered_self", [
        O.May([O.Choose(small_units, out="__tm", targeted=False),
               O.PlayCard(Ref("__tm"), ignore="all", loc=lambda g, c: ("base", c.controller))],
              label="choose a unit in your trash and play it to your base, ignoring its cost")],
        label=defn.name, source_text=defn.text)])


@script("Arachnoid Horror")
def arachnoid_horror(defn):
    # [Hunt 2]  (keyword, kept)
    # I can be played to an occupied battlefield if an enemy unit is alone there.
    # Friendly units can be played to an occupied battlefield if an enemy unit is alone there.
    return _keep([PlayPermission("lone_enemy_bf", label="play me where an enemy unit is alone", source_text=defn.text),
                  Static("self", "rule", ("play_lone_enemy_bf",), label="friendly units: play where an enemy unit is alone",
                         source_text=defn.text)])
