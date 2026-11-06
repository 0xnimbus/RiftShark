"""Card scripts: turn card text into abilities.

Three layers, applied in order by `attach_scripts`:
1. keywords  - every keyword in the card data becomes its rules-defined ability (CR 800-832).
2. auto      - templated rules text ("When you play me, draw 1.", "[Reaction] ...: Deal 2 to a unit.") is
               parsed by `auto.parse_card` into ability trees.
3. manual    - hand written scripts in `cards_*.py` keyed by card name override/extend the above.

`CardDef.script_status` records which layer scripted the card ('none' | 'keywords' | 'auto' | 'manual').
Cards whose rules text is not fully scripted are reported by `coverage()`.
"""
from __future__ import annotations

import re

from ..abilities import Static, Triggered, Activated, PlayPermission, Replacement
from ..selectors import Sel
from .. import ops as O
from ..vm import Ref

REGISTRY = {}        # card name (lower) -> callable(defn) -> list of abilities, or dict
_SCRIPTED = {}


def script(*names):
    """Decorator registering a manual script for one or more card names."""
    def deco(fn):
        for n in names:
            REGISTRY[n.lower()] = fn
        return fn
    return deco


class SpellEffect:
    """The main effect of a spell (what happens when it resolves)."""
    kind = "spell"
    __slots__ = ("code", "target_code", "label", "source_text", "zone", "cond", "keyword")

    def __init__(self, effect=None, targets=None, label="", source_text=""):
        from ..vm import compile_effect
        if targets is None:
            from ..targeting import split_choices
            targets, effect = split_choices(effect)      # choices are made as the spell is played (CR 355)
        self.code = compile_effect(effect)
        self.target_code = compile_effect(targets)
        self.label, self.source_text, self.zone, self.cond, self.keyword = label, source_text, "chain", None, None

    def active(self, g, src):
        return True


# ----------------------------------------------------------------------------- keywords
def keyword_abilities(defn):
    kws = defn.keywords
    out = []
    if kws.get("deathknell") and defn.is_permanent:
        pass  # the effect text itself is scripted by auto/manual; the trigger is "die_self"
    if kws.get("temporary"):
        out.append(Triggered("start_beginning", [O.Kill(Ref("self"))], label="Temporary", keyword="temporary"))
    if kws.get("vision"):
        out.append(Triggered("enter_self", [O.Predict(1)], label="Vision", keyword="vision"))
    if kws.get("hunt"):
        n = kws["hunt"] if isinstance(kws["hunt"], int) else 1
        out.append(Triggered("score_self", [O.GainXP(n)], label=f"Hunt {n}", keyword="hunt"))
    if kws.get("disarm"):
        n = kws["disarm"] if isinstance(kws["disarm"], int) else 1
        out.append(Triggered("attack_self", [O.GiveMight(Ref("t"), -n)], targets=[O.Choose(Sel("unit", side="enemy", where="here"))],
                             label=f"Disarm {n}", keyword="disarm"))
    if kws.get("equip") is not None and defn.is_gear:
        cost = parse_cost(_equip_cost_text(defn))
        mx = re.search(r"\[Equip\]\s*(?:[-—–:]\s*)?Spend (\d+) XP", defn.text)
        if mx:
            cost["xp"] = int(mx.group(1))
        out.append(Activated(cost, [O.Attach(Ref("self"), Ref("t"))],
                             targets=[O.Choose(Sel("unit", side="friendly", pred=lambda g, c, u: g.objects[c.source].attached_to != u), targeted=True)],
                             timing="reaction" if kws.get("quick_draw") else "main", label="Equip", is_equip=True, keyword="equip"))
    if kws.get("quick_draw") and defn.is_gear:
        out.append(Triggered("play_self", [O.Attach(Ref("self"), Ref("t"))], targets=[O.Choose(Sel("unit", side="friendly"), targeted=True)],
                             label="Quick-Draw", keyword="quick_draw"))
    if kws.get("weaponmaster"):
        out.append(weaponmaster_ability())
    if defn.is_equipment and defn.might:
        defn.effect_abilities.append(Static("attached", "might", defn.might, label=f"+{defn.might} [M]"))
    if kws.get("deploy") and defn.is_gear:
        out.append(PlayPermission("deploy", label="Deploy"))
    if kws.get("ambush"):
        out.append(PlayPermission("ambush", label="Ambush"))
    if kws.get("flow") is not None and defn.type == "spell":
        m = re.search(r"\[Flow\]\s*((?:\[[^\]]+\]\s*)+)", defn.text)
        if m:
            c = parse_cost(m.group(1)); defn.keywords["flow_cost"] = (c["energy"], tuple(c["power"]))
    if kws.get("repeat") is not None:
        m = re.search(r"\[Repeat\]\s*((?:\[[^\]]+\]\s*)+)", defn.text)
        if m:
            c = parse_cost(m.group(1)); defn.keywords["repeat_cost"] = (c["energy"], tuple(c["power"]))
    if kws.get("empower") is not None:
        m = re.search(r"\[Empower\]\s*((?:\[[^\]]+\]\s*)+)", defn.text)
        cost = parse_cost(m.group(1)) if m else {"energy": 1}
        out.append(Activated(cost, [O.Empower(Ref("self"))], timing="main", label="Empower", is_empower=True, keyword="empower"))
    return out


def weaponmaster_ability():
    """[Weaponmaster]: when you play me, you may attach an Equipment you control to me, paying its Equip cost."""
    return Triggered("play_self", [O.If(lambda g, c: c.vars.get("t") is not None,
                                        [O.PayEquip(Ref("t"), out="__eq"), O.If(Ref("__eq"), [O.Attach(Ref("t"), Ref("self"))])])],
                     targets=[O.Choose(Sel("gear", side="friendly", tags=["Equipment"]), up_to=True, targeted=False)],
                     label="Weaponmaster", optional=True, keyword="weaponmaster")


def _equip_cost_text(defn):
    m = re.search(r"\[Equip\]\s*(?:[-—–:]\s*)?((?:\[[^\]]+\]\s*)+)", defn.text)
    return m.group(1) if m else ""


COST_TOKEN = re.compile(r"\[(\d+|A|C|T|Fury|Calm|Mind|Body|Chaos|Order)\]")


def parse_cost(text):
    """'[2][Fury]' -> {'energy': 2, 'power': ['fury']}; [T] -> exhaust; [A] any power; [C] card's domain."""
    cost = {"energy": 0, "power": []}
    for tok in COST_TOKEN.findall(text or ""):
        if tok.isdigit():
            cost["energy"] += int(tok)
        elif tok == "T":
            cost["exhaust"] = True
        elif tok == "A":
            cost["power"].append("any")
        elif tok == "C":
            cost["power"].append("C")
        else:
            cost["power"].append(tok.lower())
    return cost


# ----------------------------------------------------------------------------- attach
def attach_scripts(db, defn):
    if _SCRIPTED.get(id(defn)) is defn:     # identity check: ids of freed CardDefs get reused
        return defn
    _SCRIPTED[id(defn)] = defn
    defn.abilities = []
    defn.effect_abilities = []
    status = "none"
    kw = keyword_abilities(defn)
    defn.abilities.extend(kw)
    kw_eff = list(defn.effect_abilities)
    if kw:
        status = "keywords"
    from . import auto
    try:
        res = auto.script_card(defn)
    except Exception as e:  # never let one card break loading
        res = None
        defn.keywords["_auto_error"] = repr(e)
    if res is not None:
        abilities, effect_abilities, complete = res
        defn.abilities.extend(abilities)
        defn.effect_abilities.extend(effect_abilities)
        if complete:
            status = "auto"
        elif abilities or effect_abilities:
            status = "partial"
    fn = REGISTRY.get(defn.name.lower())
    if fn is not None:
        r = fn(defn)
        if isinstance(r, dict):
            if r.get("replace", True):
                defn.abilities = list(kw) + list(r.get("abilities", []))
                defn.effect_abilities = kw_eff + list(r.get("effect_abilities", []))
            else:
                defn.abilities.extend(r.get("abilities", []))
                defn.effect_abilities.extend(r.get("effect_abilities", []))
        elif r:
            defn.abilities = list(kw) + list(r)
        status = "manual"
    if not defn.text.strip() and not defn.effect_text.strip():
        status = "manual" if status == "manual" else "vanilla"
    defn.script_status = status
    return defn


def script_all(db):
    from . import cards_manual, cards_radiance  # noqa: F401  (registers manual scripts)
    for c in db:
        attach_scripts(db, c)
    db.scripted = True
    return db


def coverage(db, cards=None):
    """Return dict status -> count and the list of unscripted cards."""
    counts = {}
    missing = []
    for c in (cards or list(db)):
        counts[c.script_status] = counts.get(c.script_status, 0) + 1
        if c.script_status in ("none", "keywords", "partial") and (c.text.strip() or c.effect_text.strip()):
            missing.append(c)
    return counts, missing
