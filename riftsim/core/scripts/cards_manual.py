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
    return [Triggered("play_self", [
        O.ChooseLocation(out="__bl"),
        O.If(lambda g, c: c.vars.get("__bl") is not None and len(g.units_at(c.vars["__bl"])) >= 4,
             [O.May([O.Choose(Sel("unit", side="enemy", where="loc:__bl"), out="t"), O.ToHand(Ref("t"))], label="return an enemy unit there")]),
    ], label=defn.name, source_text=defn.text)]


@script("Zhonya's Hourglass")
def zhonyas(defn):
    # The next time a friendly unit would die, kill this instead. Recall that unit exhausted.
    def applies(g, s, ev):
        o = g.objects.get(ev.get("uid"))
        return o is not None and o.controller == g.objects[s].controller and "unit" in g.chars(ev["uid"]).types and not ev.get("replaced_with")

    def replace(g, s, ev):
        g.do_kill([s], None)
        return dict(ev, replaced_with="recall", exhaust=True)
    return [Replacement("die", applies, replace, label=defn.name)]


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
