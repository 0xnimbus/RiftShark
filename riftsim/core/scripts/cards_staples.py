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
            return loc[0] == "bf" and g.valid_destination(u, loc)            # from its base
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
        return g.players[p].points >= g.cfg["victory"] - 3
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
        lady.temp["clockwork"] = new
        g.add_mod(new, "type", "unit", duration="permanent", source=c.source)
        g.add_mod(new, "base_might", g.objects[new].base_defn().energy or 0, duration="permanent", source=c.source)
        g.bump()

    return {"abilities": [Triggered("start_main", [
        O.If(lambda g, c: bool(g.choice_candidates(c, gear, targeted=True)), [
            O.PayResources(1, out="__lady"),
            O.If(Ref("__lady"), [O.Choose(gear, out="t", targeted=True), O.Do(animate)])])],
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

    other_here = Sel("unit", pred=lambda g, c, u: u != c.vars.get("token") and g.objects[u].location == c.event.get("loc"))
    body = [O.Choose(Sel("card", zone="hand", pred=lambda g, c, u: g.objects[u].owner == c.controller), out="__dd", targeted=False),
            O.Do(lambda g, c: g.do_discard(c.controller, [c.vars["__dd"]], c)),
            O.Do(lambda g, c: g.do_exhaust(c.source, c)),
            O.PlayToken("Reflection", loc=there, ready=True),
            O.Choose(other_here, out="__model", targeted=False),
            O.CopyAs(Ref("token"), Ref("__model")),
            O.GiveKeyword(Ref("token"), "temporary", True, duration="permanent")]
    return {"abilities": [Triggered(conquer_or_hold, [O.If(can, [O.May(body, label="discard 1 and exhaust Deceiver to play a Reflection copy there")])],
                                    label=defn.name, source_text=defn.text)], "replace": True}
