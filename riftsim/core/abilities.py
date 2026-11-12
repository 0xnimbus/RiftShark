"""Ability classes attached to card definitions (or granted by effects).

Static     - continuous effects (layers): "Friendly units here have +1 [M]", "I have Ganking while ...".
Triggered  - "When/Whenever <event>, <effect>". Keyword triggers (Deathknell, Vision, Hunt, Disarm,
             Temporary, Weaponmaster, Quick-Draw) are expressed as Triggered abilities by keywords.py.
Activated  - "[cost]: effect" with timing (main/action/reaction). Equip and Empower are activated abilities.
Replacement- "If X would happen, instead Y" / "Prevent".
Delayed    - created at runtime by effects (ops.Delayed); lives on the game, not on a card.

Trigger conditions
------------------
`event` names a condition from TRIGGERS (relative to the ability's source and controller) or is a callable
(game, src_uid, ev) -> bool. Events are dicts with at least {"kind": ...}; see game.emit for the kinds.
"""
from __future__ import annotations

from .vm import compile_effect
from .targeting import split_choices, split_trigger


def _ev_is(ev, kind):
    return ev.get("kind") == kind


def _at_source(g, src, ev):
    o = g.objects.get(src)
    return o is not None and o.location is not None and ev.get("loc") == o.place


def _friendly_unit(g, src, uid):
    o, s = g.objects.get(uid), g.objects.get(src)
    return o is not None and s is not None and g.is_friendly(o.controller, s.controller) and "unit" in g.chars(uid).types


def _enemy_unit(g, src, uid):
    o, s = g.objects.get(uid), g.objects.get(src)
    return o is not None and s is not None and not g.is_friendly(o.controller, s.controller) and "unit" in g.chars(uid).types


def _mine(g, src, ev):
    s = g.objects.get(src)
    return s is not None and ev.get("player") == s.controller


def _first_in_batch(g, src, ev, key):
    """True for the first matching event of a batch (events with the same `batch` id happened together)."""
    s = g.objects.get(src)
    if s is None or ev.get("batch") is None:
        return True
    seen = s.temp.setdefault(("batches", key), set())
    if ev["batch"] in seen:
        return False
    seen.add(ev["batch"])
    return True


TRIGGERS = {
    # ---- self events
    "play_self": lambda g, s, ev: _ev_is(ev, "play") and ev.get("uid") == s,
    "enter_self": lambda g, s, ev: _ev_is(ev, "enter") and ev.get("uid") == s,
    "die_self": lambda g, s, ev: _ev_is(ev, "die") and ev.get("uid") == s,
    "die_self_combat": lambda g, s, ev: _ev_is(ev, "die") and ev.get("uid") == s and ev.get("in_combat"),
    "leave_self": lambda g, s, ev: _ev_is(ev, "leave") and ev.get("uid") == s,
    "attack_self": lambda g, s, ev: _ev_is(ev, "attack") and ev.get("uid") == s,
    "defend_self": lambda g, s, ev: _ev_is(ev, "defend") and ev.get("uid") == s,
    "move_self": lambda g, s, ev: _ev_is(ev, "move") and ev.get("uid") == s,
    "move_self_to_bf": lambda g, s, ev: _ev_is(ev, "move") and ev.get("uid") == s and ev.get("to", (None,))[0] == "bf",
    "conquer_self": lambda g, s, ev: _ev_is(ev, "conquer") and s in ev.get("units", ()),
    "hold_self": lambda g, s, ev: _ev_is(ev, "hold") and s in ev.get("units", ()),
    "score_self": lambda g, s, ev: _ev_is(ev, "score") and s in ev.get("units", ()),
    "win_combat_self": lambda g, s, ev: _ev_is(ev, "combat_result") and s in ev.get("winners", ()),
    "lose_combat_self": lambda g, s, ev: _ev_is(ev, "combat_result") and s in ev.get("losers", ()),
    "survive_combat_self": lambda g, s, ev: _ev_is(ev, "combat_end") and s in ev.get("survivors", ()),
    "buffed_self": lambda g, s, ev: _ev_is(ev, "buff") and ev.get("uid") == s,
    "stunned_self": lambda g, s, ev: _ev_is(ev, "stun") and ev.get("uid") == s,
    "empowered_self": lambda g, s, ev: _ev_is(ev, "empower") and ev.get("uid") == s,
    "damaged_self": lambda g, s, ev: _ev_is(ev, "damage") and ev.get("uid") == s and ev.get("amount", 0) > 0,
    "deals_damage_self": lambda g, s, ev: _ev_is(ev, "damage") and ev.get("source") == s and ev.get("amount", 0) > 0,
    "targeted_self": lambda g, s, ev: _ev_is(ev, "target") and s in ev.get("targets", ()),
    "equipped_self": lambda g, s, ev: _ev_is(ev, "attach") and ev.get("to") == s,
    "attach_self": lambda g, s, ev: _ev_is(ev, "attach") and ev.get("uid") == s,
    "exhaust_self": lambda g, s, ev: _ev_is(ev, "exhaust") and ev.get("uid") == s,
    "ready_self": lambda g, s, ev: _ev_is(ev, "ready") and ev.get("uid") == s,
    "mighty_self": lambda g, s, ev: _ev_is(ev, "becomes_mighty") and ev.get("uid") == s,
    "discard_self": lambda g, s, ev: _ev_is(ev, "discard") and ev.get("uid") == s,
    "recycle_self": lambda g, s, ev: _ev_is(ev, "recycle") and ev.get("uid") == s,
    "draw_self": lambda g, s, ev: _ev_is(ev, "draw") and ev.get("uid") == s,
    "banish_self": lambda g, s, ev: _ev_is(ev, "banish") and ev.get("uid") == s,
    "showoff_self": lambda g, s, ev: _ev_is(ev, "showoff") and ev.get("uid") == s,
    # ---- controller events
    "start_beginning": lambda g, s, ev: _ev_is(ev, "beginning_phase") and _mine(g, s, ev),
    "start_turn": lambda g, s, ev: _ev_is(ev, "beginning_phase") and _mine(g, s, ev),
    "start_main": lambda g, s, ev: _ev_is(ev, "main_phase") and _mine(g, s, ev),
    "end_turn": lambda g, s, ev: _ev_is(ev, "ending_phase") and _mine(g, s, ev),
    "end_any_turn": lambda g, s, ev: _ev_is(ev, "ending_phase"),
    "start_any_turn": lambda g, s, ev: _ev_is(ev, "beginning_phase"),
    "you_play_card": lambda g, s, ev: _ev_is(ev, "play") and _mine(g, s, ev) and ev.get("uid") != s and not ev.get("token"),
    "you_play_spell": lambda g, s, ev: _ev_is(ev, "play") and _mine(g, s, ev) and ev.get("card_type") == "spell",
    "you_play_unit": lambda g, s, ev: _ev_is(ev, "play") and _mine(g, s, ev) and ev.get("card_type") == "unit" and ev.get("uid") != s,
    "you_play_gear": lambda g, s, ev: _ev_is(ev, "play") and _mine(g, s, ev) and ev.get("card_type") == "gear" and ev.get("uid") != s,
    "you_play_unit_here": lambda g, s, ev: _ev_is(ev, "play") and _mine(g, s, ev) and ev.get("card_type") == "unit" and ev.get("uid") != s and _at_source(g, s, ev),
    "you_play_unit_or_gear": lambda g, s, ev: _ev_is(ev, "play") and _mine(g, s, ev) and ev.get("card_type") in ("unit", "gear") and ev.get("uid") != s,
    "opponent_plays_spell": lambda g, s, ev: _ev_is(ev, "play") and not _mine(g, s, ev) and ev.get("card_type") == "spell",
    "opponent_plays_card": lambda g, s, ev: _ev_is(ev, "play") and not _mine(g, s, ev) and not ev.get("token"),
    "any_plays_spell": lambda g, s, ev: _ev_is(ev, "play") and ev.get("card_type") == "spell",
    "you_conquer": lambda g, s, ev: _ev_is(ev, "conquer") and _mine(g, s, ev),
    "you_hold": lambda g, s, ev: _ev_is(ev, "hold") and _mine(g, s, ev),
    "you_score": lambda g, s, ev: _ev_is(ev, "score") and _mine(g, s, ev),
    "you_conquer_here": lambda g, s, ev: _ev_is(ev, "conquer") and _mine(g, s, ev) and _at_source(g, s, ev),
    "you_hold_here": lambda g, s, ev: _ev_is(ev, "hold") and _mine(g, s, ev) and _at_source(g, s, ev),
    "you_score_here": lambda g, s, ev: _ev_is(ev, "score") and _mine(g, s, ev) and _at_source(g, s, ev),
    "you_draw": lambda g, s, ev: _ev_is(ev, "draw") and _mine(g, s, ev),
    # "one or more": once per group of events that happened together (same batch id)
    "you_draw_batch": lambda g, s, ev: _ev_is(ev, "draw") and _mine(g, s, ev) and _first_in_batch(g, s, ev, "draw"),
    "you_discard_batch": lambda g, s, ev: _ev_is(ev, "discard") and _mine(g, s, ev) and _first_in_batch(g, s, ev, "discard"),
    "you_recycle_batch": lambda g, s, ev: _ev_is(ev, "recycle") and _mine(g, s, ev) and _first_in_batch(g, s, ev, "recycle"),
    "enemy_units_die_batch": lambda g, s, ev: _ev_is(ev, "die") and not _mine(g, s, ev) and ev.get("card_type") == "unit"
        and _first_in_batch(g, s, ev, "enemy_die"),
    "friendly_units_die_batch": lambda g, s, ev: _ev_is(ev, "die") and _mine(g, s, ev) and ev.get("card_type") == "unit"
        and _first_in_batch(g, s, ev, "friendly_die"),
    "you_discard": lambda g, s, ev: _ev_is(ev, "discard") and _mine(g, s, ev),
    "you_recycle": lambda g, s, ev: _ev_is(ev, "recycle") and _mine(g, s, ev),
    "you_channel": lambda g, s, ev: _ev_is(ev, "channel") and _mine(g, s, ev),
    "you_buff": lambda g, s, ev: _ev_is(ev, "buff") and _mine(g, s, ev),
    "you_stun": lambda g, s, ev: _ev_is(ev, "stun") and _mine(g, s, ev),
    "you_gain_xp": lambda g, s, ev: _ev_is(ev, "xp") and _mine(g, s, ev),
    "you_hide": lambda g, s, ev: _ev_is(ev, "hide") and _mine(g, s, ev),
    "you_empower": lambda g, s, ev: _ev_is(ev, "empower") and _mine(g, s, ev),
    "you_showoff": lambda g, s, ev: _ev_is(ev, "showoff") and _mine(g, s, ev),
    "you_win_combat": lambda g, s, ev: _ev_is(ev, "combat_result") and ev.get("winner") is not None and _mine(g, s, {"player": ev.get("winner")}),
    "you_lose_combat": lambda g, s, ev: _ev_is(ev, "combat_result") and ev.get("loser") is not None and _mine(g, s, {"player": ev.get("loser")}),
    "you_attack": lambda g, s, ev: _ev_is(ev, "combat_start") and _mine(g, s, {"player": ev.get("attacker")}),
    "you_defend": lambda g, s, ev: _ev_is(ev, "combat_start") and _mine(g, s, {"player": ev.get("defender")}),
    "combat_start": lambda g, s, ev: _ev_is(ev, "combat_start"),
    "combat_start_here": lambda g, s, ev: _ev_is(ev, "combat_start") and _at_source(g, s, ev),
    "showdown_start": lambda g, s, ev: _ev_is(ev, "showdown_start"),
    "showdown_start_here": lambda g, s, ev: _ev_is(ev, "showdown_start") and _at_source(g, s, ev),
    "combat_end": lambda g, s, ev: _ev_is(ev, "combat_end"),
    "combat_end_here": lambda g, s, ev: _ev_is(ev, "combat_end") and _at_source(g, s, ev),
    "anyone_conquers_here": lambda g, s, ev: _ev_is(ev, "conquer") and _at_source(g, s, ev),
    "anyone_scores_here": lambda g, s, ev: _ev_is(ev, "score") and _at_source(g, s, ev),
    "opponent_conquers_here": lambda g, s, ev: _ev_is(ev, "conquer") and _at_source(g, s, ev) and not _mine(g, s, ev),
    # ---- unit events (any unit) ; use `filt` to narrow
    "friendly_unit_dies": lambda g, s, ev: _ev_is(ev, "die") and ev.get("uid") != s and _mine(g, s, ev) and ev.get("card_type") == "unit",
    "another_friendly_unit_dies": lambda g, s, ev: _ev_is(ev, "die") and ev.get("uid") != s and _mine(g, s, ev) and ev.get("card_type") == "unit",
    "enemy_unit_dies": lambda g, s, ev: _ev_is(ev, "die") and not _mine(g, s, ev) and ev.get("card_type") == "unit",
    "any_unit_dies": lambda g, s, ev: _ev_is(ev, "die") and ev.get("card_type") == "unit",
    "unit_dies_here": lambda g, s, ev: _ev_is(ev, "die") and ev.get("card_type") == "unit" and _at_source(g, s, ev),
    "friendly_unit_dies_here": lambda g, s, ev: _ev_is(ev, "die") and _mine(g, s, ev) and ev.get("card_type") == "unit" and _at_source(g, s, ev) and ev.get("uid") != s,
    "enemy_unit_dies_here": lambda g, s, ev: _ev_is(ev, "die") and not _mine(g, s, ev) and ev.get("card_type") == "unit" and _at_source(g, s, ev),
    "friendly_unit_enters_here": lambda g, s, ev: _ev_is(ev, "arrive") and _mine(g, s, ev) and _at_source(g, s, ev) and ev.get("uid") != s,
    "enemy_unit_enters_here": lambda g, s, ev: _ev_is(ev, "arrive") and not _mine(g, s, ev) and _at_source(g, s, ev),
    "unit_enters_here": lambda g, s, ev: _ev_is(ev, "arrive") and _at_source(g, s, ev) and ev.get("uid") != s,
    "friendly_unit_moves": lambda g, s, ev: _ev_is(ev, "move") and _mine(g, s, ev) and ev.get("uid") != s,
    "friendly_unit_attacks": lambda g, s, ev: _ev_is(ev, "attack") and _mine(g, s, ev) and ev.get("uid") != s,
    "friendly_unit_buffed": lambda g, s, ev: _ev_is(ev, "buff") and _mine(g, s, ev),
    "friendly_unit_stunned": lambda g, s, ev: _ev_is(ev, "stun") and _mine(g, s, ev),
    "enemy_unit_stunned": lambda g, s, ev: _ev_is(ev, "stun") and not _mine(g, s, ev),
    "friendly_unit_damaged": lambda g, s, ev: _ev_is(ev, "damage") and _mine(g, s, ev) and ev.get("amount", 0) > 0,
    "enemy_unit_damaged": lambda g, s, ev: _ev_is(ev, "damage") and not _mine(g, s, ev) and ev.get("amount", 0) > 0,
    "unit_becomes_mighty": lambda g, s, ev: _ev_is(ev, "becomes_mighty") and _mine(g, s, ev),
    "friendly_unit_leaves_here": lambda g, s, ev: _ev_is(ev, "leave_loc") and _mine(g, s, ev) and ev.get("from") == g.objects[s].location and ev.get("uid") != s,
    "friendly_unit_killed_by_spell": lambda g, s, ev: _ev_is(ev, "die") and _mine(g, s, ev) and ev.get("by") == "spell",
    "friendly_gear_enters": lambda g, s, ev: _ev_is(ev, "enter") and _mine(g, s, ev) and ev.get("card_type") == "gear" and ev.get("uid") != s,
    "friendly_unit_enters": lambda g, s, ev: _ev_is(ev, "enter") and _mine(g, s, ev) and ev.get("card_type") == "unit" and ev.get("uid") != s,
    "friendly_token_enters": lambda g, s, ev: _ev_is(ev, "enter") and _mine(g, s, ev) and ev.get("token") and ev.get("uid") != s,
    "equipped_unit_attacks": lambda g, s, ev: _ev_is(ev, "attack") and ev.get("uid") == g.objects[s].attached_to,
    "equipped_unit_dies": lambda g, s, ev: _ev_is(ev, "die") and ev.get("uid") == g.objects[s].attached_to,
    "equipped_unit_conquers": lambda g, s, ev: _ev_is(ev, "conquer") and g.objects[s].attached_to in ev.get("units", ()),
    "equipped_unit_holds": lambda g, s, ev: _ev_is(ev, "hold") and g.objects[s].attached_to in ev.get("units", ()),
    "equipped_unit_scores": lambda g, s, ev: _ev_is(ev, "score") and g.objects[s].attached_to in ev.get("units", ()),
    "equipped_unit_moves": lambda g, s, ev: _ev_is(ev, "move") and ev.get("uid") == g.objects[s].attached_to,
    "equipped_unit_defends": lambda g, s, ev: _ev_is(ev, "defend") and ev.get("uid") == g.objects[s].attached_to,
    "equipped_unit_wins_combat": lambda g, s, ev: _ev_is(ev, "combat_result") and g.objects[s].attached_to in ev.get("winners", ()),
    "equipped_unit_damaged": lambda g, s, ev: _ev_is(ev, "damage") and ev.get("uid") == g.objects[s].attached_to and ev.get("amount", 0) > 0,
    "equipped_unit_deals_damage": lambda g, s, ev: _ev_is(ev, "damage") and ev.get("source") == g.objects[s].attached_to and ev.get("amount", 0) > 0,
    "equipped_unit_plays": lambda g, s, ev: _ev_is(ev, "play") and ev.get("uid") == g.objects[s].attached_to,
    "equipped_unit_buffed": lambda g, s, ev: _ev_is(ev, "buff") and ev.get("uid") == g.objects[s].attached_to,
    "equipped_unit_killed": lambda g, s, ev: _ev_is(ev, "die") and ev.get("uid") == g.objects[s].attached_to,
    "equipped_unit_mighty": lambda g, s, ev: _ev_is(ev, "becomes_mighty") and ev.get("uid") == g.objects[s].attached_to,
    "chain_item_countered": lambda g, s, ev: _ev_is(ev, "counter") and _mine(g, s, ev),
    "any_reveal": lambda g, s, ev: _ev_is(ev, "reveal"),
    "you_reveal": lambda g, s, ev: _ev_is(ev, "reveal") and _mine(g, s, ev),
    "any_spell_resolves": lambda g, s, ev: _ev_is(ev, "resolve") and ev.get("card_type") == "spell",
    "you_resolve_spell": lambda g, s, ev: _ev_is(ev, "resolve") and ev.get("card_type") == "spell" and _mine(g, s, ev),
    "you_pay_energy": lambda g, s, ev: _ev_is(ev, "pay") and _mine(g, s, ev),
    "you_add": lambda g, s, ev: _ev_is(ev, "add") and _mine(g, s, ev),
    "legend_exhausted": lambda g, s, ev: _ev_is(ev, "exhaust") and ev.get("uid") == g.players[g.objects[s].controller].legend,
    "you_lose_points": lambda g, s, ev: _ev_is(ev, "lose_points") and _mine(g, s, ev),
    "you_gain_points": lambda g, s, ev: _ev_is(ev, "gain_points") and _mine(g, s, ev),
    "opponent_gains_points": lambda g, s, ev: _ev_is(ev, "gain_points") and not _mine(g, s, ev),
    "you_kill_enemy": lambda g, s, ev: _ev_is(ev, "die") and not _mine(g, s, ev) and ev.get("killer") is not None and g.is_friendly(ev.get("killer"), g.objects[s].controller),
    "chosen_self": lambda g, s, ev: _ev_is(ev, "target") and s in ev.get("targets", ()),
    "you_burn": lambda g, s, ev: _ev_is(ev, "burn") and _mine(g, s, ev),
    "deflect_paid_self": lambda g, s, ev: _ev_is(ev, "deflect") and ev.get("uid") == s,
}


class Ability:
    kind = "ability"
    __slots__ = ("label", "zone", "cond", "source_text", "keyword")

    def __init__(self, label="", zone="board", cond=None, source_text="", keyword=None):
        self.label, self.zone, self.cond, self.source_text, self.keyword = label, zone, cond, source_text, keyword

    def active(self, g, src):
        """Is this ability active for source `src` (zone and condition)?"""
        o = g.objects.get(src)
        if o is None:
            return False
        z = self.zone
        if z == "board":
            if o.zone != "board":
                return False
        elif z == "any":
            pass
        elif isinstance(z, (tuple, list, set)):
            if o.zone not in z:
                return False
        elif o.zone != z:
            return False
        if self.cond is not None and not self.cond(g, src):
            return False
        return True

    def __repr__(self):
        return f"{self.__class__.__name__}({self.label or self.source_text[:30]!r})"


class Static(Ability):
    """Continuous effect. `sel` picks affected objects (evaluated with ctx of the source);
    'self' applies to the source only. kind: 'might'|'keyword'|'tag'|'ability'|'rule'|'type'.

    Rules (kind='rule') are named flags checked by the engine, e.g. 'can_move_anywhere',
    'units_here_cant_be_moved', 'opponents_cant_play_reactions', with `value` as parameters.
    """
    kind = "static"
    __slots__ = ("sel", "mod_kind", "value", "layer")

    def __init__(self, sel="self", mod_kind="might", value=1, cond=None, zone="board", label="", source_text=""):
        super().__init__(label, zone, cond, source_text)
        self.sel, self.mod_kind, self.value = sel, mod_kind, value
        self.layer = {"type": 1, "tag": 1, "keyword": 2, "ability": 2, "abilities": 2, "rule": 2, "might": 3, "base_might": 3}.get(mod_kind, 3)

    def applies_to(self, g, src, uid):
        if self.sel == "self":
            return uid == src
        if self.sel == "attached":
            return g.objects[src].attached_to == uid
        from .vm import Context
        o = g.objects[src]
        ctx = Context(o.controller, src, here=o.place)
        return self.sel.matches(g, ctx, uid)


class Triggered(Ability):
    """`event`: name in TRIGGERS or callable(g, src, ev). `filt`: extra callable(g, src, ev) -> bool.
    `targets`: instruction tree run at finalize (choices), `effect`: tree run on resolution.
    `optional`: 'may' triggers (controller chooses whether to do it at resolution).
    `zone`: where the source must be for the trigger to fire ('board', 'hand', 'trash', 'any' ...).
    `controller`: 'self' (source controller) | 'owner' | 'turn' ."""
    kind = "triggered"
    __slots__ = ("event", "filt", "targets", "effect", "optional", "once_per_turn", "code", "target_code",
                 "store", "controller", "uses_chain", "priority")

    def __init__(self, event, effect=None, targets=None, filt=None, optional=False, once_per_turn=False, zone="board",
                 cond=None, label="", source_text="", store=None, controller="self", keyword=None):
        super().__init__(label, zone, cond, source_text, keyword)
        self.event, self.filt, self.targets, self.effect = event, filt, targets, effect
        self.optional, self.once_per_turn = optional, once_per_turn
        if targets is None:
            targets, effect = split_trigger(effect)      # choices are made as the trigger is finalized (CR 355, 383.3)
            self.targets, self.effect = targets or None, effect
        self.code = compile_effect(effect)
        self.target_code = compile_effect(targets)
        self.store = store or {}       # event field -> ctx var name to copy when triggering
        self.controller = controller
        self.uses_chain = True
        self.priority = 0

    def matches(self, g, src, ev):
        f = TRIGGERS[self.event] if isinstance(self.event, str) else self.event
        if not f(g, src, ev):
            return False
        if self.filt is not None and not self.filt(g, src, ev):
            return False
        return True


def _trigger_kinds():
    """Event kinds each TRIGGERS entry can match. Every entry starts with `_ev_is(ev, "kind") [or ...] and`
    (checked here from the source; an entry that does not is left out, meaning "any kind")."""
    import re
    try:
        with open(__file__, encoding="utf-8") as fh:
            src = fh.read()
        i = src.index("TRIGGERS = {")
        j = src.index("\n}\n", i)
    except (OSError, ValueError):
        return {}
    out = {}
    for e in re.split(r'\n    (?="[a-z_0-9]+":)', src[i:j])[1:]:
        m = re.match(r'"([a-z_0-9]+)":\s*lambda g, s, ev:\s*(\(?\s*_ev_is\(ev, "[a-z_]+"\)(?:\s*or\s*_ev_is\(ev, "[a-z_]+"\))*\s*\)?)\s*(?:and\b|,|$)',
                     e.strip())
        if m:
            out[m.group(1)] = frozenset(re.findall(r'_ev_is\(ev, "([a-z_]+)"\)', m.group(2)))
    return out


TRIGGER_KINDS = _trigger_kinds()


def event_kinds(ab):
    """Event kinds a Triggered/Delayed ability can fire on, or None when unknown (custom matcher)."""
    ev = getattr(ab, "event", None)
    return TRIGGER_KINDS.get(ev) if isinstance(ev, str) else None


class Activated(Ability):
    """cost: dict with any of energy:int, power:list[domain], exhaust:bool (exhaust source), discard:int,
    kill_self:bool, banish_self:bool, recycle:int, sacrifice:Sel, spend_buff:bool, xp:int, custom:instr-tree.
    timing: 'main' (your turn, neutral open state) | 'action' | 'reaction'.
    is_add: resource-adding ability (resolves immediately, does not pass focus)."""
    kind = "activated"
    __slots__ = ("cost", "timing", "targets", "effect", "once_per_turn", "is_add", "code", "target_code", "is_equip",
                 "is_empower", "cost_code", "restriction")

    def __init__(self, cost=None, effect=None, targets=None, timing="main", once_per_turn=False, is_add=False,
                 zone="board", cond=None, label="", source_text="", is_equip=False, is_empower=False, restriction=None, keyword=None):
        super().__init__(label, zone, cond, source_text, keyword)
        self.cost = dict(cost or {})
        self.timing, self.targets, self.effect = timing, targets, effect
        self.once_per_turn, self.is_add = once_per_turn, is_add
        if targets is None and not is_add:
            targets, effect = split_choices(effect)      # choices are made as the ability is activated (CR 355)
            self.targets, self.effect = targets or None, effect
        self.code = compile_effect(effect)
        self.target_code = compile_effect(targets)
        self.is_equip, self.is_empower = is_equip, is_empower
        self.cost_code = compile_effect(self.cost.get("custom"))
        self.restriction = restriction      # callable(g, src) -> bool ("Play only if ...")


class Replacement(Ability):
    """`event`: event kind this applies to ('damage','die','draw','move','recall','play','buff','discard'...).
    `applies`: callable(g, src, ev) -> bool. `replace`: callable(g, src, ev) -> new ev dict, or None to prevent.
    The engine executes replacements once per event per source.
    `optional=True` ("you may ... instead"): the controller of the source decides. Supported for 'die' events only:
    `options(g, src, ev)` lists the choices (e.g. units to kill; empty = can't apply), and
    `replace(g, src, ev, choice)` returns the new event. `game.do_kill` keeps the unit on the board and pushes a
    decision frame (game._OptionalReplacementStep); declining lets the death go on through the other replacements."""
    kind = "replacement"
    __slots__ = ("event", "applies", "replace", "once_per_turn", "optional", "options", "option_label")

    def __init__(self, event, applies, replace, once_per_turn=False, zone="board", cond=None, label="", source_text="", optional=False,
                 options=None, option_label=None):
        super().__init__(label, zone, cond, source_text)
        if optional and (event != "die" or options is None):
            raise NotImplementedError("optional replacement effects are only supported for 'die' events with options: " + label)
        self.event, self.applies, self.replace, self.once_per_turn, self.optional = event, applies, replace, once_per_turn, optional
        self.options = options
        self.option_label = option_label    # callable(g, src, choice) -> str, for the decision's option labels


class PlayPermission(Ability):
    """Alters where/when/how the source may be played (e.g. Ambush, Deploy, Hidden, 'play me from trash').
    perm: 'ambush' | 'deploy' | 'any_battlefield' | 'from_trash' | 'reaction' | 'action' | 'any_location'
    cost_mod: callable(g, src, cost) -> cost  (cost reductions on the card itself)."""
    kind = "permission"
    __slots__ = ("perm", "cost_mod", "alt_cost", "value")

    def __init__(self, perm, cond=None, zone="any", cost_mod=None, alt_cost=None, value=None, label="", source_text=""):
        super().__init__(label, zone, cond, source_text)
        self.perm, self.cost_mod, self.alt_cost, self.value = perm, cost_mod, alt_cost, value


class DelayedAbility:
    """Runtime delayed trigger (from ops.Delayed) or turn effect."""
    __slots__ = ("id", "event", "code", "filt", "expires", "once", "ctx", "label", "fired", "created_turn")

    def __init__(self, id, event, code, filt, expires, once, ctx, label, created_turn):
        self.id, self.event, self.code, self.filt, self.expires, self.once = id, event, code, filt, expires, once
        self.ctx, self.label, self.fired, self.created_turn = ctx, label, False, created_turn

    def matches(self, g, ev):
        src = self.ctx.source
        f = TRIGGERS[self.event] if isinstance(self.event, str) else self.event
        try:
            if not f(g, src, ev):
                return False
        except (KeyError, AttributeError):
            return False
        if self.filt is not None and not self.filt(g, self.ctx, ev):
            return False
        return True
