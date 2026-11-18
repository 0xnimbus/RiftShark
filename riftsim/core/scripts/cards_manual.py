"""Hand-written card scripts. Each function returns a list of abilities (replacing auto output) or a dict
{'abilities': [...], 'effect_abilities': [...], 'replace': bool}."""
from __future__ import annotations

from . import script, SpellEffect
from ..abilities import Static, Triggered, Activated, PlayPermission, Replacement
from ..selectors import Sel
from .. import ops as O
from ..vm import Ref


# ----------------------------------------------------------------------------- helpers
def _loc_of(g, s):
    return g.objects[s].place


def _play_here_first_each_turn(g, s, ev, non_token=False, kinds=("unit", "gear")):
    """Battlefield trigger: the first time a player plays a unit/gear here each turn."""
    if ev.get("kind") != "play" or ev.get("loc") != _loc_of(g, s):
        return False
    d = g.objects[ev["uid"]].base_defn()
    if d.type not in kinds or (non_token and d.is_token):
        return False
    key = ("bf_first_play", s, ev["player"])
    if g.turn_memo.get(key):
        return False
    g.turn_memo[key] = True
    return True


# ----------------------------------------------------------------------------- Riven / Kai'Sa tournament staples
@script("Bedeviling Stranger")
def bedeviling_stranger(defn):
    # When you play me, choose a battlefield. If there are 4 or more units there, you may return an enemy unit there to its owner's hand.
    # The enemy unit is a target (CR 355.10, 355.12: chosen independently of the "may"), so it is chosen with the
    # battlefield as the trigger goes on the chain (up to one: there may be none there); the count is checked and
    # the "may" decided on resolution (383.3.a.3).
    return [Triggered("play_self", [
        O.ChooseLocation(out="__bl"),
        O.Choose(Sel("unit", side="enemy", where="loc:__bl"), out="t", up_to=True),
        O.If(lambda g, c: c.vars.get("t") is not None and c.vars.get("__bl") is not None and len(g.units_at(c.vars["__bl"])) >= 4,
             [O.May([O.ToHand(Ref("t"))], label="return an enemy unit there")]),
    ], label=defn.name, source_text=defn.text)]


@script("Tideturner")
def tideturner(defn):
    # [Hidden]  When you play me, you may choose a unit you control at another location. Move me to its location and
    # it to my original location. (errata, Origins: "at another location")
    other = Sel("unit", side="friendly", pred=lambda g, c, u: g.objects[u].location != g.objects[c.source].location, elsewhere=True)
    return [Triggered("play_self", [O.May([O.Choose(other, out="t"), O.SwapLocations(Ref("self"), Ref("t"))],
                                          label="swap places with a unit you control at another location")],
                      label=defn.name, source_text=defn.text)]


@script("Zhonya's Hourglass")
def zhonyas(defn):
    # The next time a friendly unit would die, kill this instead. Recall that unit exhausted.
    def applies(g, s, ev):
        o = g.objects.get(ev.get("uid"))
        return o is not None and o.controller == g.objects[s].controller and "unit" in g.chars(ev["uid"]).types and not ev.get("replaced_with")

    def replace(g, s, ev):
        g.do_kill([s], None)
        return dict(ev, replaced_with="recall", exhaust=True)
    return [Replacement("die", applies, replace, label=defn.name, single_use=True)]


@script("Emperor's Dais")
def emperors_dais(defn):
    # When you conquer here, you may pay [1] and return a unit you control here to its owner's hand. If you do, play a 2 [M] Sand Soldier unit token here.
    return [Triggered("you_conquer_here", [
        O.May([O.PayResources(1, [], out="__paid", optional=False),
               O.If(O.has_var("__paid"), [O.Choose(Sel("unit", side="friendly", where="here"), out="t", targeted=False),
                                           O.If(O.has_var("t"), [O.ToHand(Ref("t")), O.PlayToken("Sand Soldier", loc="here")])])],
              label="pay [1] and bounce a unit for a Sand Soldier")], label=defn.name, source_text=defn.text)]


@script("Rakelstake")
def rakelstake(defn):
    # For each player, the first time they play a unit or gear here each turn, they [Predict].
    return [Triggered(lambda g, s, ev: _play_here_first_each_turn(g, s, ev), [O.Predict(1, player=Ref("__p"))],
                      store={"player": "__p"}, controller="event", label=defn.name, source_text=defn.text)]


@script("Star Spring")
def star_spring(defn):
    # The first time a player plays a non-token unit here each turn, they may move another unit they control here to its base.
    return [Triggered(lambda g, s, ev: _play_here_first_each_turn(g, s, ev, non_token=True, kinds=("unit",)), [
        O.May([O.Choose(Sel("unit", side="friendly", where="here", pred=lambda g, c, u: u != c.vars.get("__u")), out="t", targeted=False),
               O.Move(Ref("t"), "base")], label="move another unit here to base")],
        store={"player": "__p", "uid": "__u"}, controller="event", label=defn.name, source_text=defn.text)]


@script("Temporal Breach")
def temporal_breach(defn):
    # Banish a unit, then its owner plays it to the same location, ignoring its cost.
    def remember(g, c):
        u = c.vars.get("t")
        if u is not None:
            c.vars["__loc"] = g.objects[u].location
            c.vars["__owner"] = g.objects[u].owner
    return [SpellEffect([O.Choose(Sel("unit"), out="t"), O.Do(remember), O.Banish(Ref("t")),
                         O.PlayCard(Ref("t"), ignore="all", loc=lambda g, c: c.vars.get("__loc"), may=False, player=Ref("__owner"))],
                        label=defn.name, source_text=defn.text)]


@script("Time Warp")
def time_warp(defn):
    # Take a turn after this one. Banish this.
    return [SpellEffect([O.Do(lambda g, c: g.turn_queue.insert(0, c.controller), label="extra turn"), O.Banish(Ref("self"))],
                        label=defn.name, source_text=defn.text)]


@script("Blade of the Exile")
def blade_of_the_exile(defn):
    # [Equip] — [A] or exhaust a friendly unit. The keyword ability pays [A]; this second Equip ability is the
    # alternative cost (exhaust a ready friendly unit, which may be the unit being equipped).
    alt = Activated({"energy": 0, "power": [], "exhaust_unit": Sel("unit", side="friendly", pred=lambda g, c, u: not g.objects[u].exhausted)},
                    [O.Attach(Ref("self"), Ref("t"))],
                    targets=[O.Choose(Sel("unit", side="friendly", pred=lambda g, c, u: g.objects[c.source].attached_to != u), targeted=True)],
                    label="Equip (exhaust a friendly unit)", is_equip=True, keyword="equip",
                    source_text="[Equip] — exhaust a friendly unit")
    return {"abilities": [alt], "replace": False}


@script("Baron Nashor")
def baron_nashor(defn):
    # "As you play me, add the Baron Pit battlefield token to the board if it's not there already. If you do, I enter
    # there." (CR 187.9, 369.3): done while finalizing; the entry location is replaced.
    def as_play(g, c):
        if any(g.objects[bf.uid].defn.name == "Baron Pit" for bf in g.battlefields):
            return
        idx = g.add_battlefield_token(c.controller, "Baron Pit", c)
        c.vars["__play_loc"] = c.vars.get("__loc")      # where he was played to (The Exile reads this)
        c.vars["__loc"] = ("bf", idx)
        c.target_bf = None
    return [PlayPermission("as_play", value=[O.Do(as_play, label="add the Baron Pit")],
                           source_text="As you play me, add the Baron Pit battlefield token to the board if it's not there already. If you do, I enter there."),
            Static("self", "keyword", ("untargetable", True), source_text="I can't be chosen by enemy spells and abilities."),
            Static(Sel("unit", side="friendly", other=True), "might", 2, source_text="Other friendly units have +2 [M].")]


# ----------------------------------------------------------------------------- 2026-11-08: auto-scripter misparses
# A scan of every selector for tags no card has (e.g. "Something", "It,Instead") found these: each auto-script chose
# from an empty set, so part of the card did nothing.
def _evd(c):
    return c.vars.get("ev") or {}


@script("Ekko, Recurrent")
def ekko_recurrent(defn):
    # [Accelerate]  [Deathknell] — Recycle me to ready your runes.
    # "Recycle me" is the base cost, paid as the trigger is finalized (CR 383.3.b, Ekko is the rule's example)
    from ..targeting import TriggerBaseCost
    return [Triggered("die_self", [O.Ready(Sel("rune", side="friendly"))], targets=[
        TriggerBaseCost(lambda g, c: g.objects[c.source].zone == "trash"),
        O.Recycle(Ref("self")),
    ], label="Deathknell", source_text=defn.text, keyword="deathknell")]


@script("Miss Fortune, Captain")
def miss_fortune_captain(defn):
    # [Accelerate] [Ganking]  The first time I move each turn, you may ready something else that's exhausted.
    def exhausted_others(g, c):
        return [u for u, o in g.objects.items() if o.zone == "board" and u != c.source and o.exhausted
                and {"unit", "gear", "rune", "legend"} & set(g.chars(u).types)]
    return [Triggered("move_self", [
        O.ChooseFromList(exhausted_others, out="__r", n=1, up_to=True, label="ready something else that's exhausted"),
        O.Ready(Ref("__r")),
    ], once_per_turn=True, label=defn.name, source_text=defn.text)]


@script("Royal Entourage")
def royal_entourage(defn):
    # When you play me, ready or exhaust a legend.
    leg = Sel("legend")
    return [Triggered("play_self", [O.ChooseMode([
        ("ready a legend", [O.Choose(leg, out="__l", targeted=False), O.Ready(Ref("__l"))]),
        ("exhaust a legend", [O.Choose(leg, out="__l", targeted=False), O.Exhaust(Ref("__l"))]),
    ])], label=defn.name, source_text=defn.text)]


@script("Repulse")
def repulse(defn):
    # [Reaction]  Choose a friendly unit at a battlefield. Counter an enemy spell or ability that chooses it and no
    # other friendly unit.
    def item_ok(g, c, it, u):
        if it.controller == c.controller or it.ctx is None or it.removed or not it.finalized:
            return False
        chosen = [x for x in g._target_uids(it.ctx) if isinstance(x, int) and x in g.objects]
        if u not in chosen:
            return False
        return not any(x != u and g.objects[x].zone == "board" and g.objects[x].controller == c.controller
                       and g.is_unit(x) for x in chosen)

    def unit_ok(g, c, u):
        return any(item_ok(g, c, it, u) for it in g.chain)

    def source_ok(g, c, s):
        u = c.vars.get("__ru")
        return u is not None and any(it.uid == s and item_ok(g, c, it, u) for it in g.chain)
    second = O.Choose(Sel("any", zone="any", pred=source_ok), out="__sp", targeted=True)
    second.depends = True          # legality is checked through the unit choice
    return [SpellEffect([O.Choose(Sel("unit", side="friendly", where="battlefield", pred=unit_ok), out="__ru"), second,
                         O.CounterItem(lambda g, c: next((it.id for it in reversed(g.chain) if it.uid == c.vars.get("__sp")
                                                          and item_ok(g, c, it, c.vars.get("__ru"))), None))],
                        label=defn.name, source_text=defn.text)]


@script("Sudden Storm")
def sudden_storm(defn):
    # [Hidden] [Action]  Deal 2 to a unit at a battlefield. If it's attacking, deal 4 to it instead.
    amt = lambda g, c: 4 if c.vars.get("t") in g.objects and g.objects[c.vars["t"]].designation == "attacker" else 2
    return [SpellEffect([O.Choose(Sel("unit", where="battlefield"), out="t"), O.Deal(amt, Ref("t"))],
                        label=defn.name, source_text=defn.text)]


@script("Monster Harpoon")
def monster_harpoon(defn):
    # [Action]  Deal 2 to a unit at a battlefield. If you control a facedown card, deal 4 to it instead.
    def facedown(g, c):
        return any(o.zone == "facedown" and o.controller == c.controller for o in g.objects.values())
    return [SpellEffect([O.Choose(Sel("unit", where="battlefield"), out="t"),
                         O.Deal(lambda g, c: 4 if facedown(g, c) else 2, Ref("t"))],
                        label=defn.name, source_text=defn.text)]


@script("Blast Cone")
def blast_cone(defn):
    # When you play this, you may move an enemy unit.  When you move an enemy unit, you may exhaust this to [Stun] it.
    moved_enemy = lambda g, s, ev: ev.get("kind") == "move" and ev.get("player") != g.objects[s].controller \
        and not ev.get("standard")
    return [Triggered("play_self", [O.May([
        O.Choose(Sel("unit", side="enemy"), out="t"),
        O.ChooseLocation(out="__to", include_bases=True,
                         pred=lambda g, c, l: c.vars.get("t") in g.objects and g.valid_destination(c.vars["t"], l, mover=c.controller)),
        O.Move(Ref("t"), Ref("__to"))], label="move an enemy unit")], label=defn.name, source_text=defn.text),
        Triggered(moved_enemy, [O.If(lambda g, c: not g.objects[c.source].exhausted, [O.May([
            O.Exhaust(Ref("self")), O.Stun(lambda g, c: _evd(c).get("uid"))], label="exhaust this to stun it")])],
            label=defn.name, source_text=defn.text)]


@script("Ravenbloom Prefect")
def ravenbloom_prefect(defn):
    # When an opponent plays a gear, you may banish me to banish it.
    opp_gear = lambda g, s, ev: ev.get("kind") == "play" and ev.get("player") is not None \
        and not g.is_friendly(ev["player"], g.objects[s].controller) and ev.get("card_type") == "gear"
    return [Triggered(opp_gear, [O.If(lambda g, c: g.objects[c.source].zone == "board", [O.May([
        O.Banish(Ref("self")), O.Banish(lambda g, c: _evd(c).get("uid"))], label="banish me to banish it")])],
        label=defn.name, source_text=defn.text)]


@script("Ocean Drake")
def ocean_drake(defn):
    # You may play me to an open battlefield.  When you play me, you may return a non-Dragon unit to its owner's hand.
    non_dragon = Sel("unit", pred=lambda g, c, u: "Dragon" not in g.chars(u).tags)
    return [PlayPermission("open_bf", label="You may play me to an open battlefield."),
            Triggered("play_self", [O.May([O.Choose(non_dragon, out="t"), O.ToHand(Ref("t"))],
                                          label="return a non-Dragon unit to its owner's hand")],
                      label=defn.name, source_text=defn.text)]


@script("Possession")
def possession(defn):
    # [Action]  Choose an enemy unit at a battlefield. Take control of it and recall it.
    return [SpellEffect([O.Choose(Sel("unit", side="enemy", where="battlefield"), out="t"),
                         O.TakeControl(Ref("t")), O.Recall(Ref("t"))], label=defn.name, source_text=defn.text)]


@script("Blade Twirler")
def blade_twirler(defn):
    # The first time I move each turn, choose a player. They [Burn 1].
    return [Triggered("move_self", [O.ChoosePlayer(out="__p", opponent=False), O.Burn(1, player=Ref("__p"))],
                      once_per_turn=True, label=defn.name, source_text=defn.text)]


@script("Scuttle Crab")
def scuttle_crab(defn):
    # When you play me, draw 1.  [Deathknell] — Choose an opponent. They reveal their hand. You can look at their
    # facedown cards this turn. Gain 1 XP.   (the auto-script chose "a unit with the tag Opponent")
    return [Triggered("play_self", [O.Draw(1)], label="When you play me, draw 1.", source_text="When you play me, draw 1."),
            Triggered("die_self", [
                O.ChoosePlayer(out="__opp", opponent=True),
                O.Emit("reveal", player=Ref("__opp"),
                       cards=lambda g, c: list(g.players[c.vars["__opp"]].hand)),
                O.Do(lambda g, c: g.peek_facedown.__setitem__(c.controller, g.turn), label="look at their facedown cards"),
                O.GainXP(1),
            ], label="Deathknell", source_text=defn.text, keyword="deathknell")]


# ----------------------------------------------------------------------------- Kennen deck (Europe RC, 2026-11-08)
def _your_trash(kind):
    return Sel(kind, zone="trash", pred=lambda g, c, u: g.objects[u].owner == c.controller)


@script("Last Rites")
def last_rites(defn):
    # [Equip] — [Chaos], Recycle 2 cards from your trash (the cost comes from keyword_abilities)
    # effect: When I conquer or hold, you may play a unit from your trash. (You still pay its costs.)
    def play_from_trash():
        return [O.Choose(_your_trash("unit"), out="__lr", targeted=False, allow_none=True,
                         label="play a unit from your trash (you pay its costs)"),
                O.If(Ref("__lr"), [O.PlayCard(Ref("__lr"))])]
    return {"effect_abilities": [Triggered(ev, play_from_trash(), label=f"Last Rites ({ev.split('_')[0]})",
                                           source_text=defn.effect_text)
                                 for ev in ("conquer_self", "hold_self")],
            "replace": False}


@script("Veiled Temple")
def veiled_temple(defn):
    # When you conquer here, you may ready a friendly gear. If it's an Equipment, you may detach it.
    def is_equipment(g, c):
        u = c.vars.get("__vt")
        return u is not None and u in g.objects and g.objects[u].attached_to is not None
    return [Triggered("you_conquer_here",
                      [O.Choose(Sel("gear", side="friendly"), out="__vt", targeted=False, allow_none=True,
                                label="ready a friendly gear"),
                       O.If(Ref("__vt"), [O.Ready(Ref("__vt")),
                                          O.If(is_equipment, [O.May([O.Detach(Ref("__vt"))], label="detach it")])])],
                      label="Veiled Temple", source_text=defn.text)]
