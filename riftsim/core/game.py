"""Game state and game actions (CR 408-447): zones, characteristics/layers, events, triggers,
replacement effects, costs and the rune pool. Turn structure, chain and combat are in flow.py."""
from __future__ import annotations

import copy
import random

from .abilities import Static, Triggered, Activated, Replacement, PlayPermission, DelayedAbility, TRIGGERS
from .cards import CardDB, DOMAINS
from .objects import Mod, Chars, GameObject, PlayerState, BattlefieldState, ChainItem
from .selectors import Sel
from . import payment
from .vm import Context, Decision, Frame, compile_effect, _copy_containers
from . import flow

MODES = {
    "1v1": dict(players=2, victory=8, battlefields_per_player=1, hand=4, start_runes=0),
}


class RulesError(Exception):
    pass


class Game(flow.FlowMixin):
    def __init__(self, db: CardDB, decks, seed=0, mode="1v1", log=True, strict=True, first_player=None):
        self.db = db
        self._first_choice = first_player   # None: random (CR: players determine who goes first randomly)
        self.strict = strict  # False: allow decks with unscripted cards (dev smoke tests only)
        self.mode = mode
        self.cfg = MODES[mode]
        self.rng = random.Random(seed)
        self.seed = seed
        self.objects: dict[int, GameObject] = {}
        self.next_uid = 1
        self.players = [PlayerState(i) for i in range(self.cfg["players"])]
        self.battlefields: list[BattlefieldState] = []
        self.stamp = 0                 # timestamp counter for layer ordering
        self.version = 0               # bumped whenever characteristics may change
        self.turn = 0
        self.turn_player = 0
        self.turn_queue = []
        self.phase = "setup"
        self.chain: list[ChainItem] = []
        self.next_item_id = 1
        self.priority = None
        self.focus = None
        self.passes = 0
        self.showdown = None           # dict(bf, combat(bool), opened_by, chain_opened_by_trigger)
        self.combat = None             # dict(bf, attacker, defender, step)
        self.tasks = []                # outstanding tasks (stack; last = next)
        self.vm_frames = []
        self.pending = None
        self.delayed: list[DelayedAbility] = []
        self.turn_effects = []         # dicts: kind, data, expires, uses, ctx
        self.scored = set()            # (player, bf idx) scored this turn
        self.conquered_from = None     # previous controller of the battlefield last conquered
        self.turn_memo = {}            # per-turn memory (cleared at end of turn)
        self.turns_taken = {}          # player -> number of turns they have started (Forgotten Monument)
        self.known = {}                # viewer -> {uid: entered_stamp} of hidden cards revealed to them (hand reveals)
        self.peek_facedown = {}        # viewer -> turn in which they can look at opponents' facedown cards (Scuttle Crab)
        self.shown_off = {}            # played card uid -> locked-in info of what it showed off (CR 832), or None
        self.reorder_requests = []     # simultaneous triggers a player still has to order (CR 383)
        self.events = []               # structured log of everything that happened
        self.log_enabled = log
        self.winner = None
        self.over = False
        self.reason = ""
        self.dirty = False             # a cleanup is needed
        self.combat_result_memo = {}
        self.extra_legends = {}
        self.decision_count = 0
        self.history = []              # (decision kind, choice label) for replay
        self.action_count = 0
        self.max_turns = 60
        self.deck_names = []
        self._computing = set()
        self._setup(decks)

    # ------------------------------------------------------------------ setup
    def _new_obj(self, defn, owner):
        o = GameObject(self.next_uid, defn, owner)
        self.objects[o.uid] = o
        self.next_uid += 1
        return o

    def _setup(self, decks):
        from .deck import Deck
        for i, d in enumerate(decks):
            if not isinstance(d, Deck):
                d = Deck.from_dict(d, self.db)
            d.validate(self.db, raise_on_error=True, strict=self.strict)
            p = self.players[i]
            p.deck_name = d.name
            self.deck_names.append(d.name)
            leg = self._new_obj(self.db.card(d.legend), i)
            leg.zone, leg.location = "board", ("legend", i)
            p.legend = leg.uid
            p.legend_name = leg.defn.name
            self.extra_legends[i] = tuple(d.extra_legends)      # Neeko, Blending In (read-only after setup)
            ch = self._new_obj(self.db.card(d.champion), i)
            ch.zone = "champion"
            p.champion = ch.uid
            p.chosen_champion = ch.uid
            for cid in d.main:
                o = self._new_obj(self.db.card(cid), i)
                o.zone = "deck"
                p.deck.append(o.uid)
            for dom in d.runes:
                o = self._new_obj(self.db.card(f"{dom.capitalize()} Rune"), i)
                o.zone, o.domain = "rune_deck", dom
                p.rune_deck.append(o.uid)
            for b in d.battlefields:
                o = self._new_obj(self.db.card(b), i)
                o.zone = "bf_deck"
                p.battlefield_cards.append(o.uid)
            self.rng.shuffle(p.deck)
            self.rng.shuffle(p.rune_deck)
        # battlefields: each player contributes cfg['battlefields_per_player'] chosen at random (CR 1v1)
        n = self.cfg["battlefields_per_player"]
        for i, p in enumerate(self.players):
            picks = self.rng.sample(p.battlefield_cards, n)
            for u in picks:
                bf = BattlefieldState(len(self.battlefields), u, i)
                self.objects[u].zone, self.objects[u].location = "board", ("bfcard", len(self.battlefields))
                self.objects[u].controller = None      # battlefields start uncontrolled (CR 190.6.d)
                self.battlefields.append(bf)
        # who goes first: random; second player channels an extra rune in 1v1? (CR 486: second player draws? )
        first = self.rng.randrange(len(self.players))
        if self._first_choice is not None:
            first = int(self._first_choice)
        self.turn_queue = [(first + k) % len(self.players) for k in range(len(self.players))]
        for i, p in enumerate(self.players):
            for _ in range(self.cfg["hand"]):
                self._draw_raw(i)
        # CR 117: in turn order, each player may set aside up to two cards, draw that many, then recycle them.
        self.mulligan_queue = list(self.turn_queue)
        self.phase = "mulligan"
        self.first_player = first
        for i, p in enumerate(self.players):
            p.conceded = False
        self.bump()

    def set_bf_controller(self, i, p):
        """A battlefield's controller is also the controller of its card, so 'you' in its abilities means that
        player (CR 190.6.d); with no controller, 'you' refers to no one."""
        bf = self.battlefields[i]
        bf.controller = p
        self.objects[bf.uid].controller = p
        self.bump()

    # ------------------------------------------------------------------ basics
    def bump(self):
        self.version += 1

    def tick(self):
        self.stamp += 1
        return self.stamp

    def opponent(self, p):
        return (p + 1) % len(self.players)

    def opponents(self, p):
        return [q for q in range(len(self.players)) if q != p]

    def is_friendly(self, a, b):
        return a == b

    def victory_score(self):
        """Points needed to win: the configured Victory Score plus 'Increase the points needed to win' (Aspirant's Climb)."""
        return self.cfg["victory"] + sum(v for _, v in self.rules("victory_plus"))

    def cant_move(self, uid):
        """'I can't move' statics on the unit, or a 'can't move this turn' effect on it."""
        if self.has_keyword(uid, "cant_move"):
            return True
        return any(src == uid for src, _ in self.rules("cant_move"))

    def no_combat_damage(self, uid):
        """'I don't deal combat damage' (possibly conditional, e.g. Orianna, Exquisite)."""
        return self.has_keyword(uid, "no_combat_damage") or any(src == uid for src, _ in self.rules("no_combat_damage"))

    def board_uids(self):
        return [u for u, o in self.objects.items() if o.zone == "board"]

    def units_at(self, loc, player=None):
        return [u for u, o in self.objects.items() if o.zone == "board" and o.location == loc and "unit" in self.chars(u).types
                and (player is None or o.controller == player)]

    def permanents_at(self, loc, player=None):
        return [u for u, o in self.objects.items() if o.zone == "board" and o.location == loc and self.defn_of(u).is_permanent
                and (player is None or o.controller == player)]

    def defn_of(self, uid):
        return self.objects[uid].base_defn()

    def label(self, uid):
        if uid is None:
            return "none"
        if isinstance(uid, tuple):
            return self.loc_name(uid)
        o = self.objects.get(uid)
        if o is None:
            return str(uid)
        return f"{o.defn.name}#{uid}"

    def loc_name(self, loc):
        if loc is None:
            return "nowhere"
        if loc[0] == "base":
            return f"base P{loc[1]}"
        if loc[0] == "bf":
            return f"BF{loc[1]} {self.objects[self.battlefields[loc[1]].uid].defn.name}"
        return str(loc)

    def log(self, kind, **data):
        if self.log_enabled:
            data["kind"] = kind
            data["turn"] = self.turn
            self.events.append(data)

    def player_of(self, uid):
        return self.objects[uid].controller

    # ------------------------------------------------------------------ characteristics (CR 475-482 layers)
    def chars(self, uid) -> Chars:
        o = self.objects[uid]
        if o.chars_cache is not None and o.chars_version == self.version:
            return o.chars_cache
        if uid in self._computing:
            return self._local_chars(o)
        self._computing.add(uid)
        try:
            c = self._compute_chars(o)
        finally:
            self._computing.discard(uid)
        o.chars_cache, o.chars_version = c, self.version
        return c

    def _local_chars(self, o):
        c = Chars(o.base_defn())
        if o.copy_of is not None:
            c.abilities = list(o.copy_of.abilities)
        for m in o.mods:
            self._apply_mod(c, m)
        if o.zone == "board" and c.might is not None:
            c.might += o.buffs
        return c

    def _apply_mod(self, c, m):
        k = m.kind
        if k == "might":
            if c.might is not None:
                c.might += m.value
        elif k == "base_might":
            c.might = m.value
        elif k == "keyword":
            c.add_keyword(*m.value)
        elif k == "ability":
            c.abilities.append(m.value)
        elif k == "tag":
            c.tags.add(m.value)
        elif k == "type":
            c.types.add(m.value)

    def _compute_chars(self, o):
        c = Chars(o.base_defn())
        if o.copy_of is not None:
            c.abilities = list(o.copy_of.abilities)
        uid = o.uid
        if o.zone != "board":
            # CR 711: objects off the board use printed characteristics (+ granted mods that persist in zones)
            for m in o.mods:
                if m.duration == "permanent":
                    self._apply_mod(c, m)
            if c.might is not None and c.might < 0:
                c.might = 0
            return c
        # layer 1 (traits) and 2 (abilities/keywords) from own mods and static abilities, then 3 (arithmetic)
        statics = []
        for src, so in self.objects.items():
            if so.zone != "board":
                continue
            for ab in self._abilities_of(src, so, c if src == uid else None):
                if isinstance(ab, Static) and ab.active(self, src) and ab.applies_to(self, src, uid):
                    statics.append((ab.layer, so.entered_stamp, ab, src))
        # equipment effect abilities apply to the unit they are attached to
        for a in o.attachments:
            ao = self.objects.get(a)
            if ao is None or ao.zone != "board":
                continue
            for ab in ao.defn.effect_abilities:
                if isinstance(ab, Static) and (ab.cond is None or ab.cond(self, a)) and ab.sel in ("attached", "self"):
                    statics.append((ab.layer, ao.entered_stamp, ab, a))
        statics.sort(key=lambda t: (t[0], t[1]))
        mods = sorted(o.mods, key=lambda m: m.stamp)
        for layer in (1, 2, 3):
            for m in mods:
                if {"type": 1, "tag": 1, "keyword": 2, "ability": 2, "might": 3, "base_might": 3}.get(m.kind, 3) == layer:
                    self._apply_mod(c, m)
            for lay, _, ab, src in statics:
                if lay != layer:
                    continue
                self._apply_static(c, ab, src, uid)
        if c.keywords.get("temporary") and not any(getattr(a, "keyword", None) == "temporary" for a in c.abilities):
            c.abilities.append(_temporary_ability())     # granted [Temporary] (CR: kill me at the start of my Beginning Phase)
        if c.might is not None:
            c.might += o.buffs
            # keywords that modify might by designation
            if o.designation == "attacker":
                c.might += c.kw("assault")
                if c.keywords.get("assault_equals_shield"):      # Pride of Nazumah: "[Assault] equal to my [Shield]"
                    c.might += c.kw("shield")
            elif o.designation == "defender":
                c.might += c.kw("shield")
            if c.might < 0:
                c.might = 0
        return c

    def _check_static_might_reductions(self):
        """Ahri, Confident counts a static -[M] that starts applying (ruling, Radiance patch notes): compare each
        unit's negative static might per source controller with the last check and emit 'might_reduced'."""
        if not self.rules("watch_might_reductions"):
            return
        for uid, o in self.objects.items():
            if o.zone != "board" or "unit" not in self.chars(uid).types:
                continue
            neg = {}
            for src, so in self.objects.items():
                if so.zone != "board":
                    continue
                for ab in self.abilities(src):
                    if isinstance(ab, Static) and ab.mod_kind == "might" and ab.active(self, src) and ab.applies_to(self, src, uid):
                        v = ab.value(self, src, uid) if callable(ab.value) else ab.value
                        if v and v < 0:
                            neg[so.controller] = neg.get(so.controller, 0) - v
            prev = o.temp.get("neg_static", {})
            if neg != prev:
                o.temp["neg_static"] = neg
                for p, n in neg.items():
                    if n > prev.get(p, 0):
                        self.emit("might_reduced", uid=uid, player=o.controller, by=p, loc=o.location,
                                  amount=n - prev.get(p, 0), ctx=None)

    def _apply_static(self, c, ab, src, uid):
        v = ab.value
        if callable(v):
            v = v(self, src, uid)
        k = ab.mod_kind
        if k == "might":
            if c.might is not None and v:
                c.might += v
        elif k == "base_might":
            c.might = v
        elif k == "keyword":
            c.add_keyword(*v) if isinstance(v, tuple) else c.add_keyword(v, True)
        elif k == "ability":
            c.abilities.append(v)
        elif k == "abilities":
            c.abilities.extend(v or ())
        elif k == "tag":
            c.tags.add(v)
        elif k == "type":
            c.types.add(v)

    def _abilities_of(self, uid, o, partial=None):
        """Abilities an object currently has: printed (or copied) + granted via mods (+ equipment)."""
        res = list(o.base_defn().abilities)
        for m in o.mods:
            if m.kind == "ability":
                res.append(m.value)
        return res

    def abilities(self, uid):
        """All abilities including those granted by statics (uses computed chars)."""
        o = self.objects[uid]
        if o.zone == "board":
            return self.chars(uid).abilities
        return self._abilities_of(uid, o)

    def has_keyword(self, uid, kw):
        return bool(self.chars(uid).keywords.get(kw))

    def keyword_value(self, uid, kw):
        return self.chars(uid).kw(kw)

    def rules(self, name, player=None, loc=None):
        """Collect active rule statics named `name` (kind='rule'). Returns list of (src, value)."""
        out = []
        for src, so in self.objects.items():
            if so.zone != "board":
                continue
            for ab in self.abilities(src):
                if isinstance(ab, Static) and ab.mod_kind == "rule" and ab.value[0] == name and ab.active(self, src):
                    if player is not None and ab.sel == "self" and so.controller != player:
                        continue
                    out.append((src, ab.value[1] if len(ab.value) > 1 else True))
        return out

    # ------------------------------------------------------------------ mods / durations
    def add_mod(self, uid, kind, value, duration="turn", source=None):
        o = self.objects.get(uid)
        if o is None:
            return
        if kind == "might" and self.chars(uid).might is None and o.zone == "board":
            return
        before = self.chars(uid).might if o.zone == "board" else None
        o.mods.append(Mod(kind, value, duration, source, self.tick(), loc=o.location))
        self.bump()
        self._check_mighty(uid, before)

    def _check_mighty(self, uid, before):
        o = self.objects.get(uid)
        if o is None or o.zone != "board":
            return
        c = self.chars(uid)
        if before is not None and before < 5 and c.might is not None and c.might >= 5:
            self.emit("becomes_mighty", uid=uid, player=o.controller, loc=o.location)

    def expire_mods(self, duration):
        changed = False
        for o in self.objects.values():
            n = len(o.mods)
            o.mods = [m for m in o.mods if m.duration != duration]
            changed |= len(o.mods) != n
        self.delayed = [d for d in self.delayed if d.expires != duration]
        self.turn_effects = [t for t in self.turn_effects if t["expires"] != duration]
        if changed:
            self.bump()

    def _on_leave_board(self, o):
        """Statuses and 'while on board' mods clear when an object leaves the board (CR 460/… snapshots)."""
        o.mods = [m for m in o.mods if m.duration == "permanent" and m.kind in ("keyword", "ability", "tag")] if o.defn.is_token else \
                 [m for m in o.mods if False]
        o.exhausted, o.damage, o.buffs, o.empowered, o.stunned = False, 0, 0, 0, False
        o.designation = None
        o.copy_of = None
        o.location = None
        o.played_from = None
        o.accel_paid = False
        for a in list(o.attachments):
            self._detach_raw(a)
        if o.attached_to is not None:
            self._detach_raw(o.uid)
        self.bump()

    def _on_change_location(self, o):
        o.mods = [m for m in o.mods if m.duration != "while_here"]
        self.bump()

    # ------------------------------------------------------------------ zones
    def _remove_from_zone(self, o):
        p = self.players[o.owner]
        z = o.zone
        if z == "hand":
            p.hand.remove(o.uid)
        elif z == "deck":
            p.deck.remove(o.uid)
        elif z == "trash":
            p.trash.remove(o.uid)
        elif z == "banish":
            p.banish.remove(o.uid)
        elif z == "rune_deck":
            p.rune_deck.remove(o.uid)
        elif z == "champion":
            p.champion = None
        elif z == "facedown":
            if o.hidden_at is not None:
                bf = self.battlefields[o.hidden_at[1]]
                for k, v in list(bf.facedown.items()):
                    if v == o.uid:
                        del bf.facedown[k]
            o.hidden_at = None
        elif z == "board":
            if o.defn.is_unit or o.defn.is_gear or o.defn.type == "rune" or o.copy_of is not None:
                if o.location is not None and o.location[0] == "runes":
                    self.players[o.controller].runes.remove(o.uid)
                self._on_leave_board(o)
        elif z == "chain":
            pass
        o.zone = None

    def _to_zone(self, o, zone, location=None, top=False, controller=None):
        """Low level zone change. Tokens leaving the board cease to exist (CR 187)."""
        self._remove_from_zone(o)
        if o.defn.is_token and zone not in ("board", "chain"):
            o.zone = "gone"
            o.location = None
            self.bump()
            return
        p = self.players[o.owner]
        o.zone = zone
        o.location = location
        o.entered_stamp = self.tick()
        o.controller = o.owner if controller is None else controller
        if zone == "hand":
            p.hand.append(o.uid)
        elif zone == "deck":
            (p.deck.insert(0, o.uid) if top else p.deck.append(o.uid))
        elif zone == "trash":
            p.trash.append(o.uid)
        elif zone == "banish":
            p.banish.append(o.uid)
        elif zone == "rune_deck":
            (p.rune_deck.insert(0, o.uid) if top else p.rune_deck.append(o.uid))
        elif zone == "champion":
            p.champion = o.uid
        elif zone == "board":
            o.temp = {}
            if o.defn.type == "rune" and location is None:
                o.location = ("runes", o.controller)
                p.runes.append(o.uid)
            o.counters = {}
        self.bump()

    def _draw_raw(self, p):
        ps = self.players[p]
        if not ps.deck:
            return None
        u = ps.deck.pop(0)
        o = self.objects[u]
        o.zone = "hand"
        ps.hand.append(u)
        o.entered_stamp = self.tick()
        return u

    # ------------------------------------------------------------------ events, triggers, replacements
    def emit(self, kind, ctx=None, **data):
        """Announce an event. Triggered abilities that match become pending chain items; delayed
        abilities fire. Returns the event dict."""
        ev = dict(data)
        ev["kind"] = kind
        if kind == "reveal":            # a revealed card is known to everyone until it changes zones
            for u in data.get("cards") or ():
                if u in self.objects:
                    for q in range(len(self.players)):
                        self.known.setdefault(q, {})[u] = self.objects[u].entered_stamp
                    if self.objects[u].zone == "deck":          # "As I'm revealed from your deck, ..." (Undertitan)
                        for ab in self._abilities_of(u, self.objects[u]):
                            if isinstance(ab, PlayPermission) and ab.perm == "as_revealed_from_deck":
                                ab.value(self, u, ctx)
        self.log("event:" + kind, **{k: v for k, v in data.items() if k != "ctx"})
        self._collect_triggers(ev)
        return ev

    def _collect_triggers(self, ev):
        pend = []
        for uid, o in list(self.objects.items()):
            if o.zone in (None, "gone"):
                continue
            abl = self.abilities(uid) if o.zone == "board" else self._abilities_of(uid, o)
            for ab in abl:
                if not isinstance(ab, Triggered):
                    continue
                if not ab.active(self, uid):
                    # "When you play me" abilities work while the card is still on the chain (CR 340: the
                    # play event happens before the object enters the board).
                    if not (ev.get("kind") == "play" and ev.get("uid") == uid and o.zone == "chain" and ab.zone == "board"):
                        continue
                if ab.once_per_turn and o.temp.get(("opt", id(ab))) == self.turn:
                    continue
                try:
                    ok = ab.matches(self, uid, ev)
                except (KeyError, AttributeError, TypeError):
                    ok = False
                if ok:
                    pend.append((uid, ab, None))
                    if getattr(ab, "keyword", None) == "deathknell":
                        who = o.controller if o.controller is not None else o.owner
                        for _ in self.rules("deathknell_twice", player=who):      # Karthus, Eternal
                            pend.append((uid, ab, None))
            # equipment effect triggers (active while attached)
            if o.zone == "board" and o.attached_to is not None:
                for ab in o.defn.effect_abilities:
                    if isinstance(ab, Triggered) and ab.matches(self, uid, ev):
                        pend.append((uid, ab, None))
        for d in list(self.delayed):
            if d.fired and d.once:
                continue
            if d.matches(self, ev):
                pend.append((d.ctx.source, d, None))
                d.fired = True
                if d.once:
                    self.delayed.remove(d)
        if not pend:
            return
        # APNAP-ish: turn player's triggers first (CR 383: controller of each adds in turn order).
        def order(t):
            uid, ab, _ = t
            o = self.objects.get(uid)
            ctrl = o.controller if (o is not None and o.controller is not None) else self.turn_player
            return ((ctrl - self.turn_player) % len(self.players), getattr(ab, "priority", 0))
        pend.sort(key=order)
        groups = {}
        for uid, ab, _ in pend:
            item = self._add_trigger(uid, ab, ev)
            if item is not None:
                groups.setdefault(item.controller, []).append(item)
        # CR 383: each player puts their own simultaneous triggers on the chain in the order they choose
        # (the turn player's go on first, so they resolve last). Identical abilities need no choice.
        for ctrl, items in groups.items():
            if len(items) > 1 and len({id(it.ability) if it.ability is not None else it.label for it in items}) > 1:
                self.reorder_requests.append({"player": ctrl, "items": [it.id for it in items], "order": []})

    def _add_trigger(self, uid, ab, ev):
        o = self.objects.get(uid)
        if isinstance(ab, DelayedAbility):
            ctx = ab.ctx.clone()
            ctx.event = ev
            ctx.vars["ev"] = ev
            item = ChainItem(self.next_item_id, "trigger", ctx.controller, uid, None, ctx, label=ab.label or "delayed", code=ab.code)
            self.next_item_id += 1
            self.chain.append(item)
            item.stamp = self.tick()
            self.log("trigger", item=item.id, source=uid, label=item.label)
            self.dirty = True
            return item
        if ab.controller == "self":
            ctrl = o.controller
            if ctrl is None:
                ctrl = self.turn_player      # CR 190.6.b: an uncontrolled battlefield's ability is the turn player's
        elif ab.controller == "owner":
            ctrl = o.owner
        elif ab.controller == "event" and ev.get("player") is not None:
            ctrl = ev["player"]          # "they": the player the event is about (battlefield abilities)
        else:
            ctrl = self.turn_player
        ctx = Context(ctrl, uid, here=o.place)
        ctx.event = ev
        ctx.vars["ev"] = ev
        ctx.vars["self"] = uid
        if ev.get("kind") == "play" and ev.get("uid") == uid:
            ctx.shown_off = self.shown_off.get(uid)      # "When you play me, if you showed off" (CR 832.1.c.1)
            ctx.paid = dict(ev.get("paid") or {})          # "When you play me, if you paid the additional cost"
        for k, v in ab.store.items():
            ctx.vars[v] = ev.get(k)
        if ev.get("kind") == "die":
            ctx.origin_loc = ev.get("loc")
            ctx.here = ev.get("loc")
        if ab.once_per_turn:
            o.temp[("opt", id(ab))] = self.turn
        item = ChainItem(self.next_item_id, "trigger", ctrl, uid, ab, ctx, label=ab.label or ab.source_text[:40] or ab.event,
                         code=ab.code, target_code=ab.target_code)
        self.next_item_id += 1
        item.stamp = self.tick()
        self.chain.append(item)
        self.log("trigger", item=item.id, source=uid, label=item.label, controller=ctrl)
        self.dirty = True
        return item

    def add_reflexive(self, ctx, effect, label="do this"):
        c = ctx.clone()
        item = ChainItem(self.next_item_id, "reflexive", ctx.controller, ctx.source, None, c, label=label, code=compile_effect(effect))
        self.next_item_id += 1
        item.stamp = self.tick()
        self.chain.append(item)
        self.dirty = True

    def add_delayed(self, ctx, event, effect, filt, expires, once, label):
        d = DelayedAbility(self.next_item_id, event, compile_effect(effect), filt, expires, once, ctx.clone(), label, self.turn)
        self.next_item_id += 1
        self.delayed.append(d)

    def add_turn_effect(self, ctx, kind, data, expires="turn", uses=None):
        self.turn_effects.append({"kind": kind, "data": data, "expires": expires, "uses": uses, "ctx": ctx.clone(), "player": ctx.controller})

    def consume_turn_effects(self, kind, player=None, **match):
        """Find active turn effects of `kind` (for `player`), decrement uses, return their data list."""
        out = []
        for t in list(self.turn_effects):
            if t["kind"] != kind or (player is not None and t["player"] != player):
                continue
            if any(t["data"].get(k) != v for k, v in match.items()):
                continue
            out.append(t["data"])
            if t["uses"] is not None:
                t["uses"] -= 1
                if t["uses"] <= 0:
                    self.turn_effects.remove(t)
        return out

    def replace_event(self, ev):
        """Apply replacement effects to an event (CR 367-375). Returns the (possibly modified) event or
        None if it was prevented entirely. Optional replacements cannot be created (see abilities.Replacement)."""
        applied = set()
        changed = True
        guard = 0
        while changed and ev is not None and guard < 10:
            changed = False
            guard += 1
            for uid, o in list(self.objects.items()):
                if o.zone in (None, "gone"):
                    continue
                abl = self.abilities(uid) if o.zone == "board" else self._abilities_of(uid, o)
                for ab in abl:
                    if not isinstance(ab, Replacement) or ab.event != ev["kind"]:
                        continue
                    key = (uid, id(ab))
                    if key in applied or not ab.active(self, uid):
                        continue
                    if ab.once_per_turn and o.temp.get(("rpt", id(ab))) == self.turn:
                        continue
                    try:
                        if not ab.applies(self, uid, ev):
                            continue
                    except (KeyError, AttributeError, TypeError):
                        continue
                    applied.add(key)
                    if ab.once_per_turn:
                        o.temp[("rpt", id(ab))] = self.turn
                    self.log("replace", source=uid, event=ev["kind"], label=ab.label)
                    ev = ab.replace(self, uid, ev)
                    changed = True
                    if ev is None:
                        return None
                    break
                if changed:
                    break
            # turn effects acting as replacements
            for t in list(self.turn_effects):
                if t["kind"] != "replace:" + ev["kind"]:
                    continue
                key = ("te", id(t))
                if key in applied:
                    continue
                f = t["data"].get("applies")
                if f is not None and not f(self, t["ctx"], ev):
                    continue
                applied.add(key)
                ev = t["data"]["replace"](self, t["ctx"], ev)
                if t["uses"] is not None:
                    t["uses"] -= 1
                    if t["uses"] <= 0:
                        self.turn_effects.remove(t)
                changed = True
                if ev is None:
                    return None
                break
        return ev

    def activate_named_triggers(self, uid, event, ctx):
        """'Activate the conquer effects of units here': add matching triggers as if event happened."""
        o = self.objects.get(uid)
        if o is None:
            return
        fake = {"kind": event, "units": (uid,), "player": o.controller, "loc": o.location, "uid": uid}
        for ab in self.abilities(uid):
            if isinstance(ab, Triggered) and ab.active(self, uid):
                try:
                    if ab.matches(self, uid, fake):
                        self._add_trigger(uid, ab, fake)
                except (KeyError, AttributeError, TypeError):
                    pass

    # ------------------------------------------------------------------ game actions
    def do_draw(self, p, n, ctx=None):
        ps = self.players[p]
        batch = self.tick()            # cards drawn by one instruction share it ("when you draw 1 or more cards")
        for _ in range(n):
            ev = self.replace_event({"kind": "draw", "player": p})
            if ev is None:
                continue
            if ev.get("player") != p:
                p2 = ev["player"]
                self.do_draw(p2, 1, ctx)
                continue
            if not ps.deck:
                self.do_burn_out(p)
                if not ps.deck:
                    continue
            u = self._draw_raw(p)
            self.turn_memo[("draws", p)] = self.turn_memo.get(("draws", p), 0) + 1
            self.log("draw", player=p, uid=u)
            self.emit("draw", player=p, uid=u, ctx=ctx, batch=batch)

    def do_burn_out(self, p):
        """CR 432: deck empty -> opponent(s) gain a point? No: the player recycles trash into deck and each
        opponent gains 1 point (burn out)."""
        ps = self.players[p]
        if ps.deck:
            return
        self.log("burn_out", player=p)
        ps.burned_out = True
        for q in self.opponents(p):
            self.gain_points(q, 1, "burn_out", None)
        cards = [u for u in ps.trash if not self.objects[u].defn.is_token]
        for u in cards:
            self._to_zone(self.objects[u], "deck")
        self.rng.shuffle(ps.deck)
        self.emit("burn_out", player=p)

    def do_exhaust(self, uid, ctx=None, batch=None):
        """`batch`: objects exhausted at the same time share it (Seraphine, Inspiring)."""
        o = self.objects.get(uid)
        if o is None or o.zone != "board" or o.exhausted:
            return False
        o.exhausted = True
        self.bump()
        b = batch if batch is not None else self.tick()
        n = 0
        if "unit" in self.chars(uid).types:
            key = ("exhaust_batch", b, o.controller)
            n = self.turn_memo[key] = self.turn_memo.get(key, 0) + 1
        self.emit("exhaust", uid=uid, player=o.controller, loc=o.location, batch=b, units_in_batch=n, ctx=ctx)
        self.dirty = True
        return True

    def do_ready(self, uid, ctx=None):
        o = self.objects.get(uid)
        if o is None or o.zone != "board" or not o.exhausted:
            return False
        if o.stunned:
            return False
        if any(src == uid for src, _ in self.rules("cant_ready")):
            return False
        o.exhausted = False
        self.bump()
        self.emit("ready", uid=uid, player=o.controller, loc=o.location, ctx=ctx)
        self.dirty = True
        return True

    def chose(self, ctx, uid):
        """True if the spell/ability running with `ctx` chose `uid` (targeted or not)."""
        if ctx is None or uid is None:
            return False
        if uid in (ctx.vars.get("__picked") or ()):
            return True
        return uid in self._target_uids(ctx)

    def _chosen_harm_redirect(self, uid, ctx):
        """Gangplank, Naval (errata 2026-10-27): if a spell or ability that chooses me would stun me, give me -[M],
        or return me to hand, give me +3 [M] this turn instead."""
        if ctx is None or not self.chose(ctx, uid):
            return False
        hits = [v for src, v in self.rules("chosen_harm_to_might") if src == uid]
        if not hits:
            return False
        self.log("replace", source=uid, event="chosen_harm", label="+%d [M] this turn instead" % hits[0])
        self.add_mod(uid, "might", hits[0], duration="turn", source=uid)
        return True

    def give_might(self, uid, amt, duration="turn", ctx=None):
        """Give +/-N [M]. -[M] from a spell/ability goes through Gangplank's and Mel's replacements and emits
        'might_reduced' (Ahri, Confident: an ability of an object you control gives a unit non-zero -[M])."""
        o = self.objects.get(uid)
        if o is None:
            return
        if amt < 0 and ctx is not None and o.zone == "board":
            if self._chosen_harm_redirect(uid, ctx):
                return
            if self.chose(ctx, uid):
                amt -= sum(v for _, v in self.rules("chosen_minus_might_extra", player=ctx.controller))   # Mel
        self.add_mod(uid, "might", amt, duration=duration, source=ctx.source if ctx else None)
        if amt < 0 and o.zone == "board":
            self.emit("might_reduced", uid=uid, player=o.controller, by=ctx.controller if ctx else None,
                      loc=o.location, amount=-amt, ctx=ctx)

    def do_stun(self, uid, ctx=None):
        o = self.objects.get(uid)
        if o is None or o.zone != "board":
            return
        if self._chosen_harm_redirect(uid, ctx):
            return
        ev = self.replace_event({"kind": "stun", "uid": uid, "player": o.controller, "loc": o.location})
        if ev is None:
            return
        o.stunned = True
        o.exhausted = True
        self.bump()
        self.emit("stun", uid=uid, player=o.controller, loc=o.location, by=ctx.controller if ctx else None, ctx=ctx)
        self.dirty = True

    def do_buff(self, uid, ctx=None):
        o = self.objects.get(uid)
        if o is None or o.zone != "board" or "unit" not in self.chars(uid).types:
            return
        ev = self.replace_event({"kind": "buff", "uid": uid, "player": o.controller, "loc": o.location})
        if ev is None:
            return
        many = any(src == uid for src, _ in self.rules("many_buffs"))     # Lee Sin, Ascetic
        if o.buffs >= 1 and not many:
            return
        before = self.chars(uid).might
        o.buffs = o.buffs + 1 if many else 1
        self.bump()
        self.emit("buff", uid=uid, player=o.controller, loc=o.location, ctx=ctx)
        self._check_mighty(uid, before)
        self.dirty = True

    def do_spend_buff(self, uid, ctx=None):
        o = self.objects.get(uid)
        if o is None or o.buffs < 1:
            return False
        o.buffs -= 1          # one buff counter (several only with "any number of buffs")
        self.bump()
        self.emit("spend_buff", uid=uid, player=o.controller, ctx=ctx)
        return True

    def do_heal(self, uid, ctx=None):
        o = self.objects.get(uid)
        if o is None or o.damage == 0:
            return
        o.damage = 0
        o.temp = {k: v for k, v in o.temp.items() if not (isinstance(k, tuple) and k[0] == "damaged_by")}
        self.bump()

    def do_deal(self, uids, amount, ctx, source_uid=None, combat=False):
        """Deal `amount` damage to each target. A single Deal action (CR 418)."""
        src = source_uid if source_uid is not None else (ctx.source if ctx else None)
        by = ctx.controller if ctx else None
        bonus = 0
        if ctx is not None and not combat:
            for src_r, v in self.rules("bonus_damage", player=ctx.controller):
                bonus += v
            so = self.objects.get(ctx.source)
            if so is not None and so.zone == "board" and "gear" in self.chars(ctx.source).types:
                for src_r, v in self.rules("bonus_damage_gear_abilities", player=ctx.controller):    # Ziggs, Short-Fused
                    bonus += v
            for t in self.consume_turn_effects("bonus_damage", player=ctx.controller):
                if t.get("spell_only") and not (ctx.item is not None and self._item_is_spell(ctx.item)):
                    continue
                bonus += t.get("amount", 0)
        here_bonus = {}
        if ctx is not None and not combat:
            for src_r, v in self.rules("bonus_damage_here"):
                here_bonus[self.objects[src_r].place] = here_bonus.get(self.objects[src_r].place, 0) + v
        for u in list(uids):
            o = self.objects.get(u)
            if o is None or o.zone != "board":
                continue
            bonus_u = bonus + here_bonus.get(o.location, 0)
            amt = amount + bonus_u
            ev = self.replace_event({"kind": "damage", "uid": u, "amount": amt, "source": src, "player": o.controller,
                                     "loc": o.location, "by": by, "combat": combat})
            if ev is None or ev.get("amount", 0) <= 0:
                continue
            amt = ev["amount"]
            # prevention shields (mods of kind 'prevent')
            for m in o.mods:
                if m.kind == "prevent" and m.value > 0 and amt > 0:
                    used = min(m.value, amt)
                    m.value -= used
                    amt -= used
            if amt <= 0:
                continue
            if "unit" not in self.chars(u).types:
                continue
            o.damage += amt
            o.temp["dmg_item"] = ctx.item if ctx is not None else None
            o.temp[("dealt_damage", self.turn)] = True          # "if I haven't been dealt damage this turn"
            if by is not None:
                o.temp[("damaged_by", by)] = True                # Elder Dragon: "any amount of your damage"
            self.bump()
            self.log("damage", uid=u, amount=amt, source=src, combat=combat)
            self.emit("damage", uid=u, amount=amt, source=src, player=o.controller, loc=o.location, by=by, combat=combat, ctx=ctx)
            self.dirty = True

    def do_deal_split(self, uids, amount, ctx):
        """Split damage among targets: greedy lethal-first then dump the rest on the biggest (AI default)."""
        us = [u for u in uids if u in self.objects and self.objects[u].zone == "board"]
        if not us:
            return
        remaining = amount
        plan = {u: 0 for u in us}
        for u in sorted(us, key=lambda x: self.chars(x).might or 0):
            need = max(0, (self.chars(u).might or 0) - self.objects[u].damage)
            take = min(need, remaining)
            plan[u] += take
            remaining -= take
        if remaining > 0:
            plan[us[-1]] += remaining
        for u, a in plan.items():
            if a > 0:
                self.do_deal([u], a, ctx)

    def lethal_damage(self, uid):
        o = self.objects[uid]
        c = self.chars(uid)
        if c.might is None or o.damage <= 0:
            return False
        if o.damage >= c.might:
            return True
        # Elder Dragon: "Any amount of your damage is enough to kill enemy units."
        return any(o.temp.get(("damaged_by", self.objects[src].controller)) and not self.is_friendly(self.objects[src].controller, o.controller)
                   for src, _ in self.rules("any_damage_kills_enemies"))

    def do_kill(self, uids, ctx=None, by=None, in_combat=False):
        """Kill permanents (CR 429): they are sent to their owner's trash; deathknell triggers first."""
        alone = {}
        batch = self.tick()            # one id for everything killed at the same time ("one or more units die")
        for u in list(uids):
            o = self.objects.get(u)
            if o is not None and o.zone == "board" and o.location is not None:
                alone[u] = len([x for x in self.units_at(o.location, o.controller)]) == 1
        for u in list(uids):
            o = self.objects.get(u)
            if o is None or o.zone != "board" or not self.defn_of(u).is_permanent:
                continue
            killer = ctx.controller if ctx is not None else None
            ev = self.replace_event({"kind": "die", "uid": u, "player": o.controller, "loc": o.location, "killer": killer,
                                     "in_combat": in_combat or self.combat is not None and o.location == ("bf", self.combat["bf"]),
                                     "card_type": "unit" if "unit" in self.chars(u).types else "gear", "by": by,
                                     "token": o.defn.is_token, "might": self.chars(u).might, "stunned": o.stunned, "buffed": o.buffs > 0,
                                     "alone": alone.get(u, False), "dmg_item": o.temp.get("dmg_item") if by == "damage" else None,
                                     "batch": batch})
            if ev is None:
                continue
            if ev.get("replaced_with") == "banish":         # "if it would die this turn, banish it instead" (Smite)
                self.do_banish([u], ctx)
                continue
            if ev.get("replaced_with") == "recall":
                self.do_recall(u, ctx, heal=True, exhaust=ev.get("exhaust", False))
                continue
            # CR 808.1.d.2: death triggers are added before the card moves (they see the board state)
            self.log("die", uid=u, name=o.defn.name, loc=o.location)
            if ev["card_type"] == "unit":
                key = ("units_died", ev["player"])           # "if an enemy unit has died this turn"
                self.turn_memo[key] = self.turn_memo.get(key, 0) + 1
            key = ("perms_died", ev["player"])               # "if a friendly unit or gear died this turn"
            self.turn_memo[key] = self.turn_memo.get(key, 0) + 1
            self.emit("die", ctx=ctx, **{k: v for k, v in ev.items() if k != "kind"})
            self._to_zone(o, "trash")
            self.emit("leave", uid=u, player=ev["player"], loc=ev["loc"], card_type=ev["card_type"], ctx=ctx)
            self.dirty = True

    def do_banish(self, uids, ctx=None):
        for u in list(uids):
            o = self.objects.get(u)
            if o is None or o.zone in (None, "gone"):
                continue
            was = o.zone
            loc = o.location
            self._to_zone(o, "banish")
            self.emit("banish", uid=u, player=o.owner, from_zone=was, loc=loc, ctx=ctx)
            if was == "board":
                self.emit("leave", uid=u, player=o.owner, loc=loc, ctx=ctx)
            self.dirty = True

    def do_discard(self, p, uids, ctx=None):
        batch = self.tick()            # "when you discard one or more cards" fires once per batch
        for u in list(uids):
            o = self.objects.get(u)
            if o is None or o.zone != "hand":
                continue
            self._to_zone(o, "trash")
            self.log("discard", player=p, uid=u)
            self.turn_memo[("discarded", o.owner)] = self.turn_memo.get(("discarded", o.owner), 0) + 1
            self.emit("discard", uid=u, player=o.owner, ctx=ctx, batch=batch)

    def do_recycle(self, uids, ctx=None):
        """Recycle (CR 417): cards go to the bottom of their owner's deck; runes to the bottom of the rune deck.
        Several cards recycled at once go to the bottom in a random order (CR 417.5)."""
        uids = list(uids)
        if len(uids) > 1:
            self.rng.shuffle(uids)
        batch = self.tick()
        for u in uids:
            o = self.objects.get(u)
            if o is None or o.zone in (None, "gone"):
                continue
            was, loc = o.zone, o.location
            if o.defn.type == "rune":
                self._to_zone(o, "rune_deck")
            elif o.defn.is_token:
                self._to_zone(o, "gone")
            else:
                self._to_zone(o, "deck")
            self.emit("recycle", uid=u, player=o.owner, from_zone=was, loc=loc, ctx=ctx, batch=batch)
            if was == "board":
                self.emit("leave", uid=u, player=o.owner, loc=loc, ctx=ctx)
                self.dirty = True

    def do_burn(self, p, n, ctx=None):
        """Burn (CR 441): put the top n cards of the deck into the trash."""
        ps = self.players[p]
        for _ in range(n):
            if not ps.deck:
                break
            u = ps.deck[0]
            self._to_zone(self.objects[u], "trash")
            self.emit("burn", uid=u, player=p, ctx=ctx)

    def do_channel(self, p, n, exhausted=False, ctx=None):
        ps = self.players[p]
        made = []
        extra = len(self.rules("channel_plus_one", player=p)) if n > 0 else 0     # Seraphic Wyvern: "+1 exhausted rune"
        plan = [bool(exhausted)] * n + [True] * extra
        for k, exh in enumerate(plan):
            if not ps.rune_deck:
                self.log("channel_short", player=p, missing=len(plan) - k)     # rune deck empty: nothing to channel
                break
            u = ps.rune_deck[0]
            o = self.objects[u]
            self._to_zone(o, "board")
            o.exhausted = exh
            made.append(u)
            self.emit("channel", uid=u, player=p, ctx=ctx)
        return made

    def empower_cap(self, uid):
        """How many times an object can be Empowered (CR 442.1.c.1): 1, or more with a 'max_empower' rule on itself."""
        caps = [v for src, v in self.rules("max_empower") if src == uid]
        return max(caps) if caps else 1

    def do_empower(self, uid, ctx=None):
        o = self.objects.get(uid)
        if o is None or o.zone != "board":
            return False
        cap = self.empower_cap(uid)
        if o.empowered >= cap:          # CR 442.1.c: already (fully) empowered -> nothing happens
            return False
        o.empowered += 1
        self.bump()
        self.emit("empower", uid=uid, player=o.controller, loc=o.location, ctx=ctx)
        self.dirty = True
        return True

    def do_disempower(self, uid, ctx=None):
        o = self.objects.get(uid)
        if o is None or not o.empowered:
            return
        o.empowered = 0
        self.bump()
        self.emit("disempower", uid=uid, player=o.controller, ctx=ctx)
        self.dirty = True

    def valid_destination(self, uid, dest, standard=False):
        o = self.objects[uid]
        if dest == o.location:
            return False
        if self.cant_move(uid):
            return False
        if dest[0] == "base":
            if any(self.objects[src].place == o.location for src, _ in self.rules("cant_move_to_base")):
                return False          # "Units can't move from here to base"
            if any(src == uid for src, _ in self.rules("i_cant_move_to_base")):
                return False          # Determined Sentry
            return dest[1] == o.controller
        if dest[0] != "bf":
            return False
        bf = self.battlefields[dest[1]]
        # CR 464.1: can't move into a battlefield where two other players fight (n/a in 1v1)
        players_there = {self.objects[u].controller for u in self.units_at(dest)}
        if o.controller not in players_there and len(players_there) >= 2:
            return False
        if standard:
            if o.location is None:
                return False
            if o.location[0] == "bf" and not self.has_keyword(uid, "ganking") \
                    and not any(self.objects[src].place == dest for src, _ in self.rules("move_here_from_anywhere")):
                return False
            for src, v in self.rules("cant_move_here"):
                if self.objects[src].location == dest and v is True:
                    return False
        return True

    def do_move(self, uids, dest, ctx=None, standard=False):
        """Move units (CR 447-455). Applies Contested when moving to a battlefield not controlled by the mover."""
        moved = []
        origin = {}
        for u in list(uids):
            o = self.objects.get(u)
            if o is None or o.zone != "board" or "unit" not in self.chars(u).types:
                continue
            origin[u] = o.location
            if not self.valid_destination(u, dest):
                continue
            ev = self.replace_event({"kind": "move", "uid": u, "player": o.controller, "from": o.location, "to": dest, "standard": standard})
            if ev is None:
                continue
            dest_u = ev["to"]
            frm = o.location
            o.location = dest_u
            self._on_change_location(o)
            moved.append(u)
            o.temp[("moves", self.turn)] = o.temp.get(("moves", self.turn), 0) + 1    # "the third time I move in a turn"
            self.log("move", uid=u, name=o.defn.name, frm=frm, to=dest_u, standard=standard)
            self.emit("leave_loc", uid=u, player=o.controller, **{"from": frm}, to=dest_u, ctx=ctx)
        if not moved:
            return []
        batch = self.tick()          # units moved together by one action/effect share a batch ("when an opponent moves")
        for i, u in enumerate(moved):
            o = self.objects[u]
            o.temp[("moved", self.turn)] = True                 # "a unit that moved this turn" (Siren's Song)
            self.emit("move", uid=u, player=o.controller, **{"from": origin.get(u)}, to=o.location, loc=o.location, standard=standard,
                      batch=batch, batch_index=i, ctx=ctx)
            self.emit("arrive", uid=u, player=o.controller, loc=o.location, ctx=ctx)
        self._apply_contested(dest, self.objects[moved[0]].controller)
        self.dirty = True
        return moved

    def _apply_contested(self, dest, player):
        if dest[0] != "bf":
            return
        bf = self.battlefields[dest[1]]
        if bf.controller != player and bf.contested_by is None:
            bf.contested_by = player
            self.log("contest", bf=dest[1], player=player)

    def do_recall(self, uid, ctx=None, heal=False, exhaust=False):
        o = self.objects.get(uid)
        if o is None or o.zone != "board":
            return
        base = ("base", o.controller)
        if o.location == base:
            return
        frm = o.location
        o.location = base
        self._on_change_location(o)
        if heal:
            o.damage = 0
            o.temp = {k: v for k, v in o.temp.items() if not (isinstance(k, tuple) and k[0] == "damaged_by")}
        if exhaust:
            o.exhausted = True
        o.designation = None
        self.log("recall", uid=uid, name=o.defn.name, frm=frm)
        self.emit("recall", uid=uid, player=o.controller, **{"from": frm}, ctx=ctx)
        self.emit("leave_loc", uid=uid, player=o.controller, **{"from": frm}, to=base, ctx=ctx)
        self.dirty = True

    def gain_points(self, p, n, reason="effect", ctx=None):
        ps = self.players[p]
        for _ in range(n):
            ev = self.replace_event({"kind": "gain_points", "player": p, "amount": 1, "reason": reason})
            if ev is None:
                continue
            ps.points += 1
            self.log("points", player=p, points=ps.points, reason=reason)
            self.emit("gain_points", player=p, reason=reason, ctx=ctx)
        self.dirty = True

    def lose_points(self, p, n, ctx=None):
        ps = self.players[p]
        lost = min(n, ps.points)
        ps.points -= lost
        if lost:
            self.log("points", player=p, points=ps.points, reason="lose")
            self.emit("lose_points", player=p, amount=lost, ctx=ctx)

    def gain_xp(self, p, n, ctx=None):
        self.players[p].xp += n
        if n > 0:
            self.turn_memo[("xp_gained", p)] = self.turn_memo.get(("xp_gained", p), 0) + n
        self.bump()
        self.log("xp", player=p, xp=self.players[p].xp)
        self.emit("xp", player=p, amount=n, ctx=ctx)

    def play_token(self, p, name, loc, ready=False, exhausted_gear=False, ctx=None):
        """Create a token (CR 440) on the board at loc under player p's control."""
        defn = self.db.tokens[name]
        from .scripts import attach_scripts
        attach_scripts(self.db, defn)
        o = self._new_obj(defn, p)
        if defn.type == "battlefield":
            return self._create_battlefield_token(o, loc, ctx)
        o.zone = "board"
        o.location = loc if loc is not None else ("base", p)
        o.controller = p
        o.exhausted = (not ready) if defn.is_unit else bool(exhausted_gear)
        o.entered_stamp = self.tick()
        o.token_source = ctx.source if ctx else None
        self.bump()
        self.log("token", uid=o.uid, name=name, loc=o.location, player=p)
        ctype = "unit" if defn.is_unit else "gear"
        self.emit("play", uid=o.uid, player=p, card_type=ctype, loc=o.location, from_zone=None, token=True, ctx=ctx)
        self.emit("enter", uid=o.uid, player=p, loc=o.location, card_type=ctype, token=True, ctx=ctx)
        if defn.is_unit:
            self.emit("arrive", uid=o.uid, player=p, loc=o.location, ctx=ctx)
            if o.location[0] == "bf":
                self._apply_contested(o.location, p)
        self.dirty = True
        return o.uid

    def knows(self, viewer, uid):
        """Can `viewer` see this card? Own cards, public zones, cards revealed to them since they last changed
        zones, and opponents' facedown cards during a turn they may look at them."""
        o = self.objects[uid]
        if o.controller == viewer and o.zone in ("hand", "facedown"):
            return True
        if o.zone == "facedown":
            return self.peek_facedown.get(viewer) == self.turn
        if o.zone in ("hand", "deck", "rune_deck"):
            return self.known.get(viewer, {}).get(uid) == o.entered_stamp and o.zone == "hand"
        return True

    def add_battlefield_token(self, p, name, ctx=None):
        """'Add the X battlefield token to the board' (Baron Pit): a new, uncontrolled battlefield. Returns its index."""
        defn = self.db.tokens[name]
        from .scripts import attach_scripts
        attach_scripts(self.db, defn)
        o = self._new_obj(defn, p)
        idx = len(self.battlefields)
        o.zone, o.location, o.controller = "board", ("bfcard", idx), None
        o.entered_stamp = self.tick()
        self.battlefields.append(BattlefieldState(idx, o.uid, p))
        self.log("battlefield_token", uid=o.uid, name=name, idx=idx, player=p)
        self.bump()
        return idx

    def _create_battlefield_token(self, o, loc, ctx):
        if loc is None or loc[0] != "bf":
            return None
        bf = self.battlefields[loc[1]]
        old = bf.uid
        self.objects[old].zone = "replaced_bf"
        o.zone, o.location = "board", ("bfcard", loc[1])
        bf.replaced = old
        bf.uid = o.uid
        self.bump()
        return o.uid

    def replace_with_token(self, uid, token, ctx=None):
        o = self.objects.get(uid)
        if o is None:
            return None
        if "battlefield" in o.defn.types:
            for bf in self.battlefields:
                if bf.uid == uid:
                    if token is None and bf.replaced is not None:
                        self.objects[bf.replaced].zone = "board"
                        o.zone = "gone"
                        bf.uid, bf.replaced = bf.replaced, None
                        self.bump()
                        return bf.uid
                    return self.play_token(ctx.controller if ctx else o.owner, token, ("bf", bf.idx), ctx=ctx)
            return None
        loc, p = o.location, o.controller
        self.do_kill([uid], ctx)
        return self.play_token(p, token, loc, ctx=ctx)

    def do_counter(self, item_id, ctx=None):
        for it in self.chain:
            if it.id == item_id and not it.removed:
                if it.uid is not None and it.kind == "spell" and any(isinstance(ab, PlayPermission) and ab.perm == "uncounterable"
                                                                    for ab in self._abilities_of(it.uid, self.objects[it.uid])):
                    self.log("counter_refused", item=item_id, label=it.label)     # "This can't be countered."
                    return False
                if it.kind not in ("unit", "gear") and self.rules("my_spells_abilities_uncounterable", player=it.controller):
                    self.log("counter_refused", item=item_id, label=it.label)     # Mel, Newly Awakened
                    return False
                it.countered = True
                it.removed = True
                self.chain.remove(it)
                if it.uid is not None and it.kind in ("spell", "unit", "gear"):
                    o = self.objects[it.uid]
                    if o.zone == "chain":
                        self._to_zone(o, "trash")
                self.log("counter", item=item_id, label=it.label)
                self.emit("counter", item=item_id, player=it.controller, ctx=ctx)
                self.dirty = True
                return True
        return False

    def do_attach(self, gear, unit, ctx=None):
        g, u = self.objects.get(gear), self.objects.get(unit)
        if g is None or u is None or g.zone != "board" or u.zone != "board":
            return False
        if g.attached_to is not None:
            self._detach_raw(gear)
        g.attached_to = unit
        g.temp["attached_turn"] = (self.turn, unit)
        u.attachments.append(gear)
        g.location = u.location
        self.bump()
        self.log("attach", gear=gear, unit=unit)
        self.emit("attach", uid=gear, to=unit, player=g.controller, loc=u.location, ctx=ctx)
        self.dirty = True
        return True

    def _detach_raw(self, gear):
        g = self.objects.get(gear)
        if g is None or g.attached_to is None:
            return
        u = self.objects.get(g.attached_to)
        if u is not None and gear in u.attachments:
            u.attachments.remove(gear)
        g.attached_to = None
        self.bump()

    def do_detach(self, gear, ctx=None):
        g = self.objects.get(gear)
        if g is None or g.attached_to is None:
            return
        self._detach_raw(gear)
        self.emit("detach", uid=gear, player=g.controller, ctx=ctx)
        self.dirty = True

    def put_in_hand(self, uid, ctx=None):
        o = self.objects.get(uid)
        if o is None or o.zone in (None, "gone"):
            return
        was, loc = o.zone, o.location
        if was == "board" and self._chosen_harm_redirect(uid, ctx):
            return
        self._to_zone(o, "hand")
        if was == "board":
            self.emit("leave", uid=uid, player=o.owner, loc=loc, ctx=ctx)
            self.dirty = True

    def put_in_trash(self, uid, ctx=None):
        o = self.objects.get(uid)
        if o is None or o.zone in (None, "gone"):
            return
        was, loc = o.zone, o.location
        self._to_zone(o, "trash")
        if was == "board":
            self.emit("leave", uid=uid, player=o.owner, loc=loc, ctx=ctx)
            self.dirty = True

    def put_on_top(self, uid):
        o = self.objects.get(uid)
        if o is None:
            return
        self._to_zone(o, "deck", top=True)

    def take_control(self, uid, p, ctx=None, duration="permanent"):
        o = self.objects.get(uid)
        if o is None or o.zone != "board" or o.controller == p:
            return
        o.controller = p
        if o.location is not None and o.location[0] == "base":
            o.location = ("base", p)
        if duration != "permanent":
            o.mods.append(Mod("control", o.owner, duration, ctx.source if ctx else None, self.tick()))
        self.bump()
        self.dirty = True

    def _end_bound_legends(self):
        """A legend added by Neeko, Blending In exists only while that Neeko is on the board."""
        for o in self.objects.values():
            b = o.temp.get("bound_to") if o.zone == "board" else None
            if b is None:
                continue
            so = self.objects.get(b[0])
            if so is None or so.zone != "board" or so.entered_stamp != b[1]:
                self.log("cease", uid=o.uid, name=o.defn.name)
                self._to_zone(o, "gone")
                self.dirty = True

    def _end_control_durations(self):
        """'You control it until I leave the board' (Akshan, Mischievous): duration ("until_leaves", src, stamp)."""
        for o in self.objects.values():
            if not o.mods:
                continue
            for m in list(o.mods):
                if m.kind != "control" or not isinstance(m.duration, tuple) or m.duration[0] != "until_leaves":
                    continue
                so = self.objects.get(m.duration[1])
                if so is not None and so.zone == "board" and so.entered_stamp == m.duration[2]:
                    continue
                o.mods.remove(m)
                if o.zone == "board" and o.controller != m.value:
                    o.controller = m.value
                    if o.location is not None and o.location[0] == "base":
                        o.location = ("base", o.controller)
                    self.log("control_ends", uid=o.uid, player=o.controller)
                    self.bump()
                    self.dirty = True

    def facedown_cards(self, bf_idx, p):
        """Player p's facedown cards at a battlefield (one, or more with 'hide an additional card here')."""
        return [u for k, u in self.battlefields[bf_idx].facedown.items() if (k if isinstance(k, int) else k[0]) == p]

    def can_hide_at(self, p, bf_idx):
        bf = self.battlefields[bf_idx]
        here = ("bf", bf_idx)
        extra = sum(1 for src, _ in self.rules("extra_hide_here") if self.objects[src].place == here)
        return len(self.facedown_cards(bf_idx, p)) < 1 + extra

    def do_hide(self, p, uid, loc, ctx=None):
        o = self.objects.get(uid)
        if o is None or loc[0] != "bf":
            return False
        bf = self.battlefields[loc[1]]
        if bf.controller != p or not self.can_hide_at(p, bf.idx):
            return False
        self._to_zone(o, "facedown")
        o.controller = p
        o.hidden_at = loc
        o.facedown_turn = self.turn
        k = 0
        while (p if k == 0 else (p, k)) in bf.facedown:
            k += 1
        bf.facedown[p if k == 0 else (p, k)] = uid
        self.log("hide", uid=uid, bf=loc[1], player=p)
        self.emit("hide", uid=uid, player=p, loc=loc, ctx=ctx)
        return True

    # ------------------------------------------------------------------ resources (CR 162-168)
    def available_energy(self, p):
        ps = self.players[p]
        return ps.energy + sum(1 for u in ps.runes if not self.objects[u].exhausted)

    def available_power(self, p):
        ps = self.players[p]
        return len(ps.power) + len(ps.runes)

    def add_resources(self, p, energy=0, power=(), restriction=None, ctx=None):
        """CR 430: put resources into p's Rune Pool. Restricted resources ('Use only to play spells') stay tagged."""
        ps = self.players[p]
        if restriction:
            ps.pool_r.extend([("E", restriction)] * energy)
            ps.pool_r.extend((d, restriction) for d in power)
        else:
            ps.energy += energy
            ps.power.extend(power)
        self.bump()
        self.emit("add", player=p, energy=energy, power=list(power), ctx=ctx)

    def empty_pools(self):
        """CR 167: every Rune Pool empties at the start of each Main Phase and the end of each turn."""
        for ps in self.players:
            ps.energy, ps.power, ps.pool_r = 0, [], []

    def can_pay(self, p, energy=0, power=(), extra_exhaust=(), purpose=None):
        return payment.can_pay(self, p, energy, list(power), purpose, extra_exhaust)

    def payment_plans(self, p, energy=0, power=(), purpose=None):
        return payment.plans(self, p, energy, list(power), purpose)

    def apply_payment(self, p, plan, ctx=None, purpose=None):
        payment.apply_plan(self, p, plan, ctx, purpose)

    def item_purpose(self, it):
        """What a chain item's cost pays for (Add restrictions check this)."""
        if it is None:
            return None
        if it.kind in ("spell", "unit", "gear"):
            return payment.purpose_of_card(self, it.uid, "play")
        o = self.objects.get(it.uid)
        types = set(self.chars(it.uid).types) if (o is not None and o.zone == "board") else (set(o.base_defn().types) if o else set())
        return {"kind": "ability", "types": types, "uid": it.uid}

    def ctx_purpose(self, ctx):
        if ctx is None or ctx.item is None:
            return None
        for it in self.chain:
            if it.id == ctx.item:
                return self.item_purpose(it)
        return None

    # ------------------------------------------------------------------ choices
    def choice_candidates(self, ctx, sel, targeted=True):
        if isinstance(sel, (list, tuple)):
            return [u for u in sel if u in self.objects]
        cands = sel.candidates(self, ctx)
        if targeted:
            # Hidden (CR 811.1.d): targets of a card played from facedown must be at that battlefield when possible
            if ctx.target_bf is not None:
                here = [u for u in cands if self.objects[u].location == ctx.target_bf]
                if here:
                    cands = here
            # Deflect (CR 809): opponents' targeting costs [A] per deflect value; drop unaffordable targets
            out = []
            paid = ctx.vars.get("__deflect_cost", 0)
            for u in cands:
                o = self.objects[u]
                if o.zone == "board" and not self.is_friendly(o.controller, ctx.controller):
                    if self.chars(u).keywords.get("untargetable"):
                        continue
                    d = self.keyword_value(u, "deflect")
                    if d and not self.can_pay(ctx.controller, 0, ["any"] * (d + paid), purpose=self.ctx_purpose(ctx)):
                        continue
                out.append(u)
            cands = out
        return cands

    # ------------------------------------------------------------------ cloning / snapshots
    def clone(self):
        g = copy.copy(self)
        self._ctx_map = {}           # keep contexts shared between a chain item and its frames shared in the clone
        g.objects = {u: self._clone_obj(o) for u, o in self.objects.items()}
        g.players = [self._clone_player(p) for p in self.players]
        g.battlefields = [self._clone_bf(b) for b in self.battlefields]
        g.chain = [self._clone_item(it) for it in self.chain]
        g.tasks = [tuple(t) for t in self.tasks]
        g.vm_frames = [self._clone_frame(f) for f in self.vm_frames]
        g.delayed = [self._clone_delayed(d) for d in self.delayed]
        g.turn_effects = [dict(t, ctx=t["ctx"].clone()) for t in self.turn_effects]
        g.scored = set(self.scored)
        g.turn_memo = _copy_containers(self.turn_memo)
        g.turns_taken = dict(self.turns_taken)
        g.shown_off = dict(self.shown_off)
        g.known = {k: dict(v) for k, v in self.known.items()}
        g.peek_facedown = dict(self.peek_facedown)
        g.mulligan_queue = list(getattr(self, "mulligan_queue", []))
        g.reorder_requests = [dict(r, items=list(r["items"]), order=list(r["order"])) for r in self.reorder_requests]
        g.turn_queue = list(self.turn_queue)
        g.events = []
        g.log_enabled = False
        g.history = []
        g.showdown = _copy_containers(self.showdown) if self.showdown else None
        g.combat = _copy_containers(self.combat) if self.combat else None
        g.rng = random.Random()
        g.rng.setstate(self.rng.getstate())
        g.pending = self._clone_decision(self.pending) if self.pending else None
        g._computing = set()
        g.combat_result_memo = {}
        self.__dict__.pop("_ctx_map", None)
        g.__dict__.pop("_ctx_map", None)
        return g

    def _clone_obj(self, o):
        c = GameObject.__new__(GameObject)
        for k in GameObject.__slots__:
            v = getattr(o, k)
            if k == "mods":
                v = [Mod(m.kind, m.value, m.duration, m.source, m.stamp, m.loc) for m in v]
            elif k in ("attachments",):
                v = list(v)
            elif k in ("counters", "temp"):
                v = _copy_containers(v)
            elif k == "chars_cache":
                v = None
            setattr(c, k, v)
        return c

    def _clone_player(self, p):
        c = PlayerState.__new__(PlayerState)
        for k in PlayerState.__slots__:
            v = getattr(p, k)
            if isinstance(v, (list, dict, set)):
                v = _copy_containers(v)
            setattr(c, k, v)
        return c

    def _clone_bf(self, b):
        c = BattlefieldState.__new__(BattlefieldState)
        for k in BattlefieldState.__slots__:
            v = getattr(b, k)
            if isinstance(v, dict):
                v = dict(v)
            setattr(c, k, v)
        return c

    def _clone_item(self, it):
        c = ChainItem.__new__(ChainItem)
        for k in ChainItem.__slots__:
            v = getattr(it, k)
            if k == "ctx" and v is not None:
                v = self._clone_ctx(v)
            elif k == "cost" and isinstance(v, dict):
                v = dict(v)
            setattr(c, k, v)
        return c

    def _clone_ctx(self, ctx):
        m = getattr(self, "_ctx_map", None)
        if m is None:
            return ctx.clone()
        c = m.get(id(ctx))
        if c is None:
            c = m[id(ctx)] = ctx.clone()
        return c

    def _clone_frame(self, f):
        nf = Frame(f.code, self._clone_ctx(f.ctx), f.tag)
        nf.pc = f.pc
        return nf

    def _clone_delayed(self, d):
        return DelayedAbility(d.id, d.event, d.code, d.filt, d.expires, d.once, d.ctx.clone(), d.label, d.created_turn)

    def _clone_decision(self, d):
        nd = Decision(d.player, d.kind, d.options, d.out, d.labels, dict(d.info))
        return nd

    def snapshot(self):
        """JSON-friendly view of the public state (for replays / frontend)."""
        def obj(u):
            o = self.objects[u]
            c = self.chars(u) if o.zone == "board" else None
            return {"uid": u, "card": o.defn.id, "name": o.defn.name, "controller": o.controller, "owner": o.owner,
                    "zone": o.zone, "loc": o.location, "exhausted": o.exhausted, "damage": o.damage, "buffs": o.buffs,
                    "might": c.might if c else o.defn.might, "stunned": o.stunned, "empowered": bool(o.empowered),
                    "attached_to": o.attached_to, "designation": o.designation,
                    "keywords": dict(c.keywords) if c else dict(o.defn.keywords), "image": o.defn.image, "token": o.defn.is_token}
        players = []
        for p in self.players:
            players.append({"idx": p.idx, "deck": p.deck_name, "legend": self.objects[p.legend].defn.name, "points": p.points,
                            "xp": p.xp, "hand": [obj(u) for u in p.hand], "hand_size": len(p.hand), "deck_size": len(p.deck),
                            "trash": [obj(u) for u in p.trash], "rune_deck": len(p.rune_deck),
                            "runes": [obj(u) for u in p.runes], "champion": obj(p.champion) if p.champion else None,
                            "energy": p.energy, "power": list(p.power), "pool_restricted": [list(x) for x in p.pool_r], "legend_obj": obj(p.legend),
                            "base": [obj(u) for u in self.permanents_at(("base", p.idx))]})
        bfs = []
        for b in self.battlefields:
            bfs.append({"idx": b.idx, "card": self.objects[b.uid].defn.id, "name": self.objects[b.uid].defn.name,
                        "image": self.objects[b.uid].defn.image, "owner": b.owner,
                        "controller": b.controller, "contested_by": b.contested_by,
                        "units": [obj(u) for u in self.permanents_at(("bf", b.idx))],
                        "facedown": {str(k): v for k, v in b.facedown.items()}})
        return {"turn": self.turn, "turn_player": self.turn_player, "phase": self.phase, "players": players,
                "battlefields": bfs, "chain": [{"id": it.id, "label": it.label, "controller": it.controller, "kind": it.kind,
                                                "finalized": it.finalized, "card": self.objects[it.uid].defn.id if it.uid else None} for it in self.chain],
                "showdown": self.showdown, "combat": self.combat, "winner": self.winner, "over": self.over,
                "priority": self.priority, "focus": self.focus}


_TEMPORARY = []


def _temporary_ability():
    if not _TEMPORARY:
        from .abilities import Triggered
        from . import ops as O
        from .vm import Ref
        from .scripts import temporary_ability
        _TEMPORARY.append(temporary_ability())
    return _TEMPORARY[0]
