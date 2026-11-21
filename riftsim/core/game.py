"""Game state and game actions (CR 408-447): zones, characteristics/layers, events, triggers,
replacement effects, costs and the rune pool. Turn structure, chain and combat are in flow.py."""
from __future__ import annotations

import copy
import itertools
import os
import sys
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


CACHE_CHECK = os.environ.get("RIFTSHARK_CACHE_CHECK") == "1"
_PYPY = sys.implementation.name == "pypy"


def _make_obj_copier():
    """A function copying every GameObject field by plain attribute assignment: faster than a __dict__ update in
    CPython and ~200x faster in PyPy (whose JIT handles direct attribute stores well)."""
    src = "def copy_obj(o):\n    c = _new(GameObject)\n" + "".join(f"    c.{k} = o.{k}\n" for k in GameObject.FIELDS) \
        + "    return c\n"
    ns = {"GameObject": GameObject, "_new": object.__new__}
    exec(src, ns)
    return ns["copy_obj"]


_copy_obj_fields = _make_obj_copier()
_DEFN_TRIGGERS = {}
_KINDS = {}


def _kinds_of(ab):
    """event_kinds(ab), memoized per ability object (abilities are immutable once scripted)."""
    r = _KINDS.get(id(ab))
    if r is None or r[0] is not ab:
        from .abilities import event_kinds
        r = _KINDS[id(ab)] = (ab, event_kinds(ab))
    return r[1]


def _zone_ok(az, z):
    """The zone part of Ability.active: can an ability with zone `az` work for an object in zone `z`?"""
    if az == "any":
        return True
    if isinstance(az, (tuple, list, set)):
        return z in az
    return az == z


_MOD_LAYER = {"type": 1, "tag": 1, "keyword": 2, "ability": 2, "might": 3, "base_might": 3}


def _layer_stamp(t):
    return (t[0], t[1])


def _mod_stamp(m):
    return m.stamp


_TRIGGER_KEYWORDS = ("temporary", "vision", "hunt", "disarm")     # granting these adds abilities (_grant_keyword_trigger)


def _prints_temporary(defn):
    """Does the definition list the [Temporary] ability itself (so _compute_chars adds no second one)?"""
    return any(getattr(ab, "keyword", None) == "temporary" for ab in defn.abilities)


def _gear_may_grant(defn):
    """Could this gear's equipment effect add an ability to the unit it is attached to?"""
    return any(isinstance(ab, Static) and _may_grant_ability(ab) for ab in defn.effect_abilities)


def _may_grant_ability(st):
    """Could this Static add an ability to an object's characteristics (an ability, or [Temporary])?"""
    k = st.mod_kind
    if k in ("ability", "abilities"):
        return True
    if k == "keyword":
        v = st.value
        if callable(v):
            return True
        return (v[0] if isinstance(v, tuple) else v) in _TRIGGER_KEYWORDS
    return False


def _defn_triggers(defn, zone):
    """[(Triggered, event kinds)] among a card definition's printed abilities that can work while the card is in `zone`,
    in order (memoized per definition and zone). On the chain, board abilities are kept for "When you play me"."""
    key = (id(defn), zone)
    r = _DEFN_TRIGGERS.get(key)
    if r is None or r[0] is not defn:
        r = _DEFN_TRIGGERS[key] = (defn, [(ab, _kinds_of(ab)) for ab in defn.abilities if isinstance(ab, Triggered)
                                          and (_zone_ok(ab.zone, zone) or (zone == "chain" and ab.zone == "board"))])
    return r[1]


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
        self.struct = 0                # bumped on structural changes only (restruct)
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
        self._partial = {}             # uid -> chars so far, while its layers are re-applied (CR 478.3)
        self._recursed = set()
        self._grant_cache = None
        self._board_cache = None
        self._pao_cache = None
        self._canpay_memo = None
        self._setup(decks)

    # ------------------------------------------------------------------ setup
    def _new_obj(self, defn, owner):
        o = GameObject(self.next_uid, defn, owner)
        self.objects[o.uid] = o
        self.next_uid += 1
        self.restruct()
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

    def restruct(self):
        """Bump after a structural change: objects created, zones, mods, attachments or copies. Caches that only
        depend on those (board statics, the trigger and rule indexes when no layer adds abilities) key on `struct`."""
        self.struct += 1
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

    def board_items(self):
        """[(uid, obj)] of the objects on the board, in board (creation) order. Zones only change with restruct, so
        this is cached per structure; don't mutate the list."""
        cache = self._board_cache
        if cache is not None and cache[0] == self.struct:
            if CACHE_CHECK:
                self._check_cache("board", cache[1], [(u, o) for u, o in self.objects.items() if o.zone == "board"])
            return cache[1]
        out = [(u, o) for u, o in self.objects.items() if o.zone == "board"]
        self._board_cache = (self.struct, out)
        return out

    def board_uids(self):
        return [u for u, o in self.board_items()]

    def units_at(self, loc, player=None):
        return [u for u, o in self.board_items() if o.location == loc and self.is_unit(u)
                and (player is None or o.controller == player)]

    def permanents_at(self, loc, player=None):
        return [u for u, o in self.board_items() if o.location == loc and self.defn_of(u).is_permanent
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
            # an effect on this object reads this object (Fiora, Victorious: "While I'm [Mighty], I have ... [Shield]"):
            # answer with what is known so far, then re-apply the layers until nothing changes (CR 478.3)
            self._recursed.add(uid)
            p = self._partial.get(uid)
            return p if p is not None else self._local_chars(o)
        self._computing.add(uid)
        try:
            c = self._compute_chars(o)
            for _ in range(4):
                if uid not in self._recursed:
                    break
                self._recursed.discard(uid)
                self._partial[uid] = c
                c2 = self._compute_chars(o)
                same = (c2.might == c.might and c2.keywords == c.keywords and c2.tags == c.tags and c2.types == c.types
                        and len(c2.abilities) == len(c.abilities))
                c = c2
                if same:
                    break
        finally:
            self._computing.discard(uid)
            self._partial.pop(uid, None)
            self._recursed.discard(uid)
        o.chars_cache, o.chars_version = c, self.version
        return c

    def _local_chars(self, o):
        c = Chars(o.base_defn())
        if o.copy_of is not None:
            c.abilities = list(o.copy_of.abilities)
        for m in o.mods:
            self._apply_mod(c, m)
        if o.zone == "board" and c.might is not None:
            c.might += o.buffs + self._buff_bonus(o)
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
            _grant_keyword_trigger(c, m.value)
        elif k == "ability":
            c.abilities.append(m.value)
        elif k == "tag":
            c.tags.add(m.value)
        elif k == "type":
            c.types.add(m.value)

    def _board_statics(self):
        """(src, obj, Static) for every printed/copied/mod-granted static ability of objects on the board, in board
        order. Depends only on the game state, so it is cached per state version (like chars)."""
        cache = getattr(self, "_statics_cache", None)
        if cache is not None and cache[0] == self.struct:      # only zones, printed abilities and mods (restruct)
            if CACHE_CHECK:
                self._check_cache("statics", cache[1], self._build_statics())
            return cache[1]
        out = self._build_statics()
        self._statics_cache = (self.struct, out)
        return out

    def _build_statics(self):
        out = []
        for src, so in self.board_items():
            for ab in self._abilities_of(src, so):
                if isinstance(ab, Static):
                    out.append((src, so, ab))
        return out

    def _compute_chars(self, o):
        c = Chars(o.base_defn())
        if o.copy_of is not None:
            c.abilities = list(o.copy_of.abilities)
        if o.zone == "board" and o.attached_to is not None:
            c.abilities = _active_printed(o, c.abilities)     # CR 135.4: printed rules text inactive while attached
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
        for src, so, ab in self._board_statics():
            if ab.active(self, src) and ab.applies_to(self, src, uid):
                statics.append((ab.layer, so.entered_stamp, ab, src))
        # equipment effect abilities apply to the unit they are attached to
        for a in o.attachments:
            ao = self.objects.get(a)
            if ao is None or ao.zone != "board":
                continue
            for ab in ao.defn.effect_abilities:
                if isinstance(ab, Static) and (ab.cond is None or ab.cond(self, a)) and ab.sel in ("attached", "self"):
                    statics.append((ab.layer, ao.entered_stamp, ab, a))
        if statics or o.mods:
            statics.sort(key=_layer_stamp)
            mods = sorted(o.mods, key=_mod_stamp)
            for layer in (1, 2, 3):
                for m in mods:
                    if _MOD_LAYER.get(m.kind, 3) == layer:
                        self._apply_mod(c, m)
                for lay, _, ab, src in statics:
                    if lay != layer:
                        continue
                    self._apply_static(c, ab, src, uid)
        if c.keywords.get("temporary") and not any(getattr(a, "keyword", None) == "temporary" for a in c.abilities) \
                and (o.attached_to is None or any(m.kind == "keyword" and m.value[0] == "temporary" for m in o.mods)):
            c.abilities.append(_temporary_ability())     # granted [Temporary] (CR: kill me at the start of my Beginning Phase)
        if c.might is not None:
            c.might += o.buffs + self._buff_bonus(o)
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
        for uid, o in self.board_items():
            if o.zone != "board" or "unit" not in self.chars(uid).types:
                continue
            neg = {}
            for src, so in self.board_items():
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
            _grant_keyword_trigger(c, v)
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
        if o.zone == "board" and o.attached_to is not None:
            res = _active_printed(o, res)                      # CR 135.4: printed rules text inactive while attached
        for m in o.mods:
            if m.kind == "ability":
                res.append(m.value)
        return res

    def abilities(self, uid):
        """All abilities including those granted by statics (uses computed chars)."""
        o = self.objects[uid]
        if o.zone == "board":
            if self._printed_abilities_only(o):
                return o.base_defn().abilities
            return self.chars(uid).abilities
        return self._abilities_of(uid, o)

    def is_unit(self, uid):
        """'unit' in chars(uid).types, without computing characteristics when nothing can change the object's types
        (types are only added by 'type' mods, 'type' statics and attached gear; see _compute_chars)."""
        o = self.objects[uid]
        cc = o.chars_cache
        if cc is not None and o.chars_version == self.version:
            return "unit" in cc.types
        if o.zone == "board" and (o.attachments or self._board_flags()[1] or any(m.kind == "type" for m in o.mods)):
            return "unit" in self.chars(uid).types
        if o.zone != "board" and any(m.kind == "type" and m.duration == "permanent" for m in o.mods):
            return "unit" in self.chars(uid).types
        return "unit" in o.base_defn().types

    def _board_flags(self):
        """Per state version: (some board static may grant abilities, some board static changes types)."""
        cache = self._grant_cache
        if cache is None or cache[0] != self.struct:
            st = self._board_statics()
            cache = self._grant_cache = (self.struct, (any(_may_grant_ability(ab) for _, _, ab in st),
                                                        any(ab.mod_kind == "type" for _, _, ab in st)))
        return cache[1]

    def _build_rules_index(self):
        idx = {}
        layered = False
        for src, so in self.board_items():
            if not self._printed_abilities_only(so):
                layered = True
            for ab in self.abilities(src):
                if isinstance(ab, Static) and ab.mod_kind == "rule":
                    idx.setdefault(ab.value[0], []).append((src, so, ab))
        return idx, layered

    def _check_cache(self, what, cached, fresh):
        """RIFTSHARK_CACHE_CHECK=1: a structure-keyed cache must equal a rebuild."""
        def norm(x):
            if isinstance(x, dict):
                return {k: norm(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)):
                return [norm(v) for v in x]
            if isinstance(x, GameObject) or hasattr(x, "__call__") or type(x).__name__ in ("Static", "Triggered"):
                return id(x)
            return x
        if norm(cached) != norm(fresh):
            raise AssertionError(f"stale {what} cache at turn {self.turn} (struct {self.struct}, version {self.version})")

    def _printed_abilities_only(self, o):
        """True when layers can't add abilities to this board object, so its abilities are exactly the printed (or
        copied) ones and its characteristics need not be computed to list them. Abilities are only added by
        'ability' mods, statics granting abilities, attached gear, granted trigger keywords ([Temporary], [Vision],
        [Hunt], [Disarm]); an attached card's printed text is inactive (see _compute_chars).
        All of these are structural, so the answer is cached per structure."""
        cache = self._pao_cache
        if cache is None or cache[0] != self.struct:
            cache = self._pao_cache = (self.struct, {})
        r = cache[1].get(o.uid)
        if r is None:
            r = cache[1][o.uid] = self._printed_abilities_only_raw(o)
        return r

    def _printed_abilities_only_raw(self, o):
        if self._board_flags()[0] or o.attached_to is not None:      # attached: printed text inactive (CR 135.4)
            return False
        bd = o.copy_of or o.defn
        if bd.keywords.get("temporary") and not _prints_temporary(bd):
            return False
        for m in o.mods:
            k = m.kind
            if k == "ability" or (k == "keyword" and (m.value[0] if isinstance(m.value, tuple) else m.value) in _TRIGGER_KEYWORDS):
                return False
        for a in o.attachments:
            ao = self.objects.get(a)
            if ao is not None and ao.zone == "board" and _gear_may_grant(ao.defn):
                return False
        return True

    def has_keyword(self, uid, kw):
        return bool(self.chars(uid).keywords.get(kw))

    def keyword_value(self, uid, kw):
        return self.chars(uid).kw(kw)

    def rules(self, name, player=None, loc=None):
        """Collect active rule statics named `name` (kind='rule'). Returns list of (src, value)."""
        out = []
        cache = getattr(self, "_rules_cache", None)
        if cache is not None and (cache[0] == self.version or (cache[1] is not None and cache[1] == self.struct)):
            if CACHE_CHECK and cache[0] != self.version:
                self._check_cache("rules", cache[2], self._build_rules_index()[0])
        else:
            idx, layered = self._build_rules_index()
            cache = self._rules_cache = (self.version, None if layered else self.struct, idx)
        for src, so, ab in cache[2].get(name, ()):
            if ab.active(self, src):
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
        self.restruct()
        self._check_mighty(uid, before)

    def _check_mighty(self, uid, before):
        o = self.objects.get(uid)
        if o is None or o.zone != "board":
            return
        c = self.chars(uid)
        if before is not None and before < 5 and c.might is not None and c.might >= 5:
            o.temp["__mighty"] = True
            self.emit("becomes_mighty", uid=uid, player=o.controller, loc=o.location)

    def _check_becomes_mighty(self):
        """CR 709: a unit becomes Mighty whenever its Might goes from under 5 to 5 or more, whatever the cause: a
        static (Sett, Kingpin; Shield or Assault as a designation is set), a -[M] effect expiring, ... Mods and buffs
        announce it at once (_check_mighty); this catches the rest, comparing with the last state seen. Only run while
        something could trigger on it."""
        _, by_kind = self._trigger_index()
        if not by_kind.get("becomes_mighty") and not by_kind.get("*"):
            return
        for uid, o in self.board_items():
            if o.zone != "board" or not self.is_unit(uid):
                continue
            m = self.chars(uid).might
            now = m is not None and m >= 5
            prev = o.temp.get("__mighty")
            o.temp["__mighty"] = now
            if prev is False and now:
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
            self.restruct()

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
        self.restruct()

    def _sync_attachments(self, o):
        """CR 719.3.a: when the top-most card changes locations, all attached cards change locations with it."""
        for a in o.attachments:
            ao = self.objects.get(a)
            if ao is not None and ao.zone == "board":
                ao.location = o.location

    def _on_change_location(self, o):
        self._sync_attachments(o)
        if any(m.duration == "while_here" for m in o.mods):
            o.mods = [m for m in o.mods if m.duration != "while_here"]
            self.restruct()
        else:
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
        self.restruct()

    def _to_zone(self, o, zone, location=None, top=False, controller=None):
        """Low level zone change. Tokens leaving the board cease to exist (CR 187)."""
        if o.zone == "board" and zone != "board":
            o.temp["__lk_controller"] = o.controller     # last known controller ("Its controller draws 2")
        # who will know the card once it is in a hand: a face-up card moving there in public view (a unit returned
        # to hand, a card taken from the trash) is known to every player; a revealed card stays known to those who
        # saw it (CR 124 makes a new object, but the move itself was public information)
        seen_by = self._public_viewers(o) if zone == "hand" else ()
        self._remove_from_zone(o)
        if o.defn.is_token and zone not in ("board", "chain"):
            o.zone = "gone"
            o.location = None
            self.restruct()
            return
        p = self.players[o.owner]
        o.zone = zone
        o.location = location
        o.entered_stamp = self.tick()
        o.controller = o.owner if controller is None else controller
        if zone == "hand":
            p.hand.append(o.uid)
            for q in seen_by:
                self.known.setdefault(q, {})[o.uid] = o.entered_stamp
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
        self.restruct()

    def _public_viewers(self, o):
        """Players who see a card as it moves from its current zone to a hand: everyone for a face-up public zone
        (board, trash, banishment, chain, champion zone), those it was revealed to for a card in a deck."""
        if o.zone in ("board", "trash", "banish", "chain", "champion"):
            return tuple(range(len(self.players)))
        if o.zone == "deck":
            return tuple(q for q, m in self.known.items() if m.get(o.uid) == o.entered_stamp)
        return ()

    def _draw_raw(self, p):
        ps = self.players[p]
        if not ps.deck:
            return None
        u = ps.deck.pop(0)
        o = self.objects[u]
        seen_by = self._public_viewers(o)          # a card revealed on top of the deck, then drawn
        o.zone = "hand"
        ps.hand.append(u)
        o.entered_stamp = self.tick()
        for q in seen_by:
            self.known.setdefault(q, {})[u] = o.entered_stamp
        self.restruct()                 # zone change: the trigger index lists abilities by zone
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
        if self.log_enabled:
            self.log("event:" + kind, **{k: v for k, v in data.items() if k != "ctx"})
        self._collect_triggers(ev)
        return ev

    def _trigger_index(self):
        """Per state version: every triggered ability an object has, in board order, as
        (uid, obj, ability, event kinds or None, is_equipment_effect), grouped by event kind."""
        cache = getattr(self, "_trig_cache", None)
        if cache is not None and (cache[0] == self.version or (cache[1] is not None and cache[1] == self.struct)):
            if CACHE_CHECK and cache[0] != self.version:
                self._check_cache("triggers", cache[2], self._build_trigger_index()[0])
            return cache[2]
        index, layered = self._build_trigger_index()
        # without layered objects the index only depends on structure; otherwise on the full state version
        self._trig_cache = (self.version, None if layered else self.struct, index)
        return index

    def _build_trigger_index(self):
        layered = False
        entries = []
        add = entries.append
        dtr = _DEFN_TRIGGERS
        for uid, o in list(self.objects.items()):
            z = o.zone
            if z == "board":
                bd = o.copy_of or o.defn
                if not self._printed_abilities_only(o):
                    # layers may add abilities (see _printed_abilities_only): use the computed characteristics
                    layered = True
                    for ab in self.chars(uid).abilities:
                        if isinstance(ab, Triggered):
                            add((uid, o, ab, _kinds_of(ab), False))
                else:
                    r = dtr.get((id(bd), z))
                    for ab, kinds in (r[1] if r is not None and r[0] is bd else _defn_triggers(bd, z)):
                        add((uid, o, ab, kinds, False))
                if o.attached_to is not None:
                    for ab in o.defn.effect_abilities:
                        if isinstance(ab, Triggered):
                            add((uid, o, ab, None, True))
                continue
            if z is None or z == "gone":
                continue
            # off the board: printed (or copied) + mod-granted abilities, no layers (as _abilities_of). Abilities that
            # can't work in the object's zone are left out: Ability.active would reject them (every zone change bumps
            # the version), except "When you play me" while the card is on the chain (see _collect_triggers).
            bd = o.copy_of or o.defn
            r = dtr.get((id(bd), z))
            for ab, kinds in (r[1] if r is not None and r[0] is bd else _defn_triggers(bd, z)):
                add((uid, o, ab, kinds, False))
            if o.mods:
                for m in o.mods:
                    if m.kind == "ability" and isinstance(m.value, Triggered):
                        add((uid, o, m.value, _kinds_of(m.value), False))
        by_kind = {}
        for k, e in enumerate(entries):
            for kind in (e[3] if e[3] is not None else ("*",)):
                by_kind.setdefault(kind, []).append(k)
        return (entries, by_kind), layered

    def _collect_triggers(self, ev):
        pend = []
        entries, by_kind = self._trigger_index()
        kind = ev.get("kind")
        picks = sorted(by_kind.get(kind, []) + by_kind.get("*", []))
        leaving = getattr(self, "_leaving", None)
        for k in picks:
            uid, o, ab, _, equip = entries[k]
            if leaving and (uid in leaving or (equip and o.attached_to in leaving)) \
                    and ev.get("uid") not in (uid, o.attached_to if equip else uid):
                continue                                    # CR 383.2.c.2: leaving at the same time
            if equip:
                # an Equipment's effect is an ability of the unit it is attached to: "When I conquer" means that unit
                # conquers and "me" is that unit; the gear stays the source (Blighted Battleaxe unattaches itself)
                unit = o.attached_to
                if unit in self.objects and self.objects[unit].zone == "board":
                    try:
                        ok = ab.matches(self, unit, ev)
                    except (KeyError, AttributeError, TypeError):
                        ok = False
                    if ok:
                        pend.append((uid, ab, unit))
                continue
            if not ab.active(self, uid):
                # "When you play me" abilities work while the card is still on the chain (CR 340: the
                # play event happens before the object enters the board).
                if not (kind == "play" and ev.get("uid") == uid and o.zone == "chain" and ab.zone == "board"):
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
        for d in list(self.delayed):
            if d.fired and d.once:
                continue
            dst = d.ctx.vars.get("__dl_stamps")
            if dst and ev.get("uid") in dst and ev["uid"] in self.objects \
                    and self.objects[ev["uid"]].entered_stamp != dst[ev["uid"]]:
                continue           # the event is about a new object, not the one the delayed ability refers to
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
        for uid, ab, me in pend:
            item = self._add_trigger(uid, ab, ev, me=me)
            if item is not None:
                groups.setdefault(item.controller, []).append(item)
        # CR 383: each player puts their own simultaneous triggers on the chain in the order they choose
        # (the turn player's go on first, so they resolve last). Identical abilities need no choice.
        for ctrl, items in groups.items():
            if len(items) > 1 and len({id(it.ability) if it.ability is not None else it.label for it in items}) > 1:
                self.reorder_requests.append({"player": ctrl, "items": [it.id for it in items], "order": []})

    def _add_trigger(self, uid, ab, ev, me=None):
        o = self.objects.get(uid)
        if isinstance(ab, DelayedAbility):
            ctx = ab.ctx.clone()
            ctx.event = ev
            ctx.vars["ev"] = ev
            # "it" in a delayed trigger refers back to what the creating effect chose; it is not chosen again, so the
            # creator's targets are not re-checked against this trigger's event (that dropped them, e.g. Tornado Warrior)
            ctx.vars.pop("__targets", None)
            self._stamp_trigger_objects(ctx, ev)
            if ctx.vars.get("__dl_stamps"):
                ctx.vars["__ev_stamps"] = {**ctx.vars.get("__ev_stamps", {}), **ctx.vars["__dl_stamps"]}
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
        if me is not None:                      # Equipment effect: "me" is the unit it is attached to
            ctx.vars["self"] = me
            ctx.here = self.objects[me].place
        if ev.get("kind") == "play" and ev.get("uid") == uid:
            ctx.shown_off = self.shown_off.get(uid)      # "When you play me, if you showed off" (CR 832.1.c.1)
            ctx.paid = dict(ev.get("paid") or {})          # "When you play me, if you paid the additional cost"
            if ctx.here is None and ev.get("loc") is not None:
                ctx.here = ev["loc"]                        # still on the chain: "here" is where I'm played to
            if ev.get("from_zone") == "facedown" and ev.get("loc") is not None and ev["loc"][0] == "bf":
                ctx.target_bf = ev["loc"]                   # CR 811.1.d.3: play effects target at the battlefield played to
        for k, v in ab.store.items():
            ctx.vars[v] = ev.get(k)
        if ev.get("kind") == "die":
            ctx.origin_loc = ev.get("loc")
            ctx.here = ev.get("loc")
        if ab.once_per_turn:
            o.temp[("opt", id(ab))] = self.turn
        self._stamp_trigger_objects(ctx, ev)
        item = ChainItem(self.next_item_id, "trigger", ctrl, uid, ab, ctx, label=ab.label or ab.source_text[:40] or ab.event,
                         code=ab.code, target_code=ab.target_code)
        self.next_item_id += 1
        item.stamp = self.tick()
        self.chain.append(item)
        self.log("trigger", item=item.id, source=uid, label=item.label, controller=ctrl)
        self.dirty = True
        return item

    def _stamp_trigger_objects(self, ctx, ev):
        """CR 124: an object that leaves the board and comes back is a new object. A trigger's "it"/"me" (the event's
        object, its source) means the object as it was when the trigger happened, so remember the board objects'
        entry stamps; `ops._uids` drops one that has since been replaced by a new object (Imperial Decree's "kill it"
        on a unit returned to hand and played again)."""
        st = {}
        for u in (ev.get("uid"), ctx.vars.get("self"), *(ev.get("uids") or ())):
            o = self.objects.get(u) if isinstance(u, int) else None
            if o is not None and o.zone == "board":
                st[u] = o.entered_stamp
        if st:
            ctx.vars["__ev_stamps"] = st

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
        # CR 124: "it" in a delayed ability is the object chosen when it was created ("Kill it the next time it takes
        # damage", "When it dies this turn", "Disempower it at end of turn"); once that object leaves the board and
        # comes back it is a new object the delayed ability doesn't see. Remember the board objects' entry stamps.
        st = {}
        for name, rec in (ctx.vars.get("__chosen") or {}).items():
            for u, stamp in (rec.get("stamps") or {}).items():
                o = self.objects.get(u)
                if o is not None and o.zone == "board" and o.entered_stamp == stamp:
                    st[u] = stamp
        so = self.objects.get(ctx.source) if ctx.source is not None else None
        if so is not None and so.zone == "board":
            st[ctx.source] = so.entered_stamp
        if st:
            d.ctx.vars["__dl_stamps"] = st
        self.delayed.append(d)

    def _buff_bonus(self, o):
        """Stand United: "Buffs give an additional +1 [M] to friendly units this turn." """
        if not o.buffs or not self.turn_effects:
            return 0
        return o.buffs * sum(1 for t in self.turn_effects if t["kind"] == "buff_bonus" and self.is_friendly(t["player"], o.controller))

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

    def replace_event(self, ev, dry=False, skip=(), first=None):
        """Apply replacement effects to an event (CR 367-375). Returns the (possibly modified) event or
        None if it was prevented entirely. An optional replacement that applies stops the pass and returns the event
        with "deferred": (source uid, ability id) and "applied" (keys already used) for its controller to decide
        (do_kill asks; see abilities.Replacement). dry=True previews the result without using up once-per-turn or
        limited-use replacements, and without optional ones. `skip`: replacement keys already applied or declined."""
        applied = set(skip)
        if first is not None and first[0] == "te" and isinstance(first[1], int) and first[1] < len(self.turn_effects):
            first = ("te", id(self.turn_effects[first[1]]))         # chosen turn effect, by its index in turn_effects
        changed = True
        guard = 0
        while changed and ev is not None and guard < 10:
            if ev["kind"] == "die" and ev.get("replaced_with"):
                break           # the death was replaced (recall, banish): there is no death left to replace (CR 370)
            changed = False
            guard += 1
            te_first = first is not None and first[0] == "te" and first not in applied
            order = [] if te_first else list(self.objects.items())
            if first is not None and first[0] in self.objects and first not in applied:
                order.insert(0, (first[0], self.objects[first[0]]))      # the replacement chosen for this event
            for uid, o in order:
                if o.zone in (None, "gone"):
                    continue
                abl = self.abilities(uid) if o.zone == "board" else self._abilities_of(uid, o)
                if first is not None and uid == first[0]:
                    abl = sorted(abl, key=lambda a: id(a) != first[1])
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
                        if ab.optional and (dry or not ab.options(self, uid, ev)):
                            continue
                    except (KeyError, AttributeError, TypeError):
                        continue
                    if ab.optional:
                        return dict(ev, deferred=key, applied=tuple(applied))
                    applied.add(key)
                    if not dry:
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
            if changed:
                continue
            tes = list(self.turn_effects)
            if te_first:
                tes.sort(key=lambda t: id(t) != first[1])
            for t in tes:
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
                if t["uses"] is not None and not dry:
                    t["uses"] -= 1
                    if t["uses"] <= 0:
                        self.turn_effects.remove(t)
                changed = True
                if ev is None:
                    return None
                break
            if te_first and not changed:
                first, changed = None, True           # the chosen turn effect no longer applies: try the others
        return ev

    def die_replacements(self, ev):
        """The replacement effects that could apply to death event `ev` now, as (key, label): object ones as
        (uid, id(ability)), turn effects as ("te", index in turn_effects). Used to let the dying object's controller
        pick which one applies first (CR 372)."""
        out = []
        for uid, o in list(self.objects.items()):
            if o.zone in (None, "gone"):
                continue
            abl = self.abilities(uid) if o.zone == "board" else self._abilities_of(uid, o)
            for ab in abl:
                if not isinstance(ab, Replacement) or ab.event != "die" or not ab.active(self, uid):
                    continue
                if ab.once_per_turn and o.temp.get(("rpt", id(ab))) == self.turn:
                    continue
                try:
                    if not ab.applies(self, uid, ev) or (ab.optional and not ab.options(self, uid, ev)):
                        continue
                except (KeyError, AttributeError, TypeError):
                    continue
                out.append(((uid, id(ab)), ab.label or self.label(uid)))
        for i, t in enumerate(self.turn_effects):
            if t["kind"] != "replace:die":
                continue
            f = t["data"].get("applies")
            try:
                if f is not None and not f(self, t["ctx"], ev):
                    continue
            except (KeyError, AttributeError, TypeError):
                continue
            src = t["ctx"].source
            out.append((("te", i), self.label(src) if src in self.objects else "an effect"))
        return out

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
        for gu, go in list(self.objects.items()):        # its Equipment's effects are its abilities too
            if go.attached_to != uid or go.zone != "board":
                continue
            for ab in go.defn.effect_abilities:
                if isinstance(ab, Triggered):
                    try:
                        if ab.matches(self, uid, fake):
                            self._add_trigger(gu, ab, fake, me=uid)
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
            if not self._burn_out_until_cards(p):
                return
            u = self._draw_raw(p)
            self.turn_memo[("draws", p)] = self.turn_memo.get(("draws", p), 0) + 1
            self.log("draw", player=p, uid=u)
            self.emit("draw", player=p, uid=u, ctx=ctx, batch=batch)

    def _burn_out_until_cards(self, p):
        """CR 432.1-432.3: moving a card out of an empty Main Deck burns out first; if the deck is still empty
        the attempt burns out again, until an opponent has won. True when there is a card to move."""
        ps = self.players[p]
        v = self.victory_score()
        while not ps.deck:
            self.do_burn_out(p)
            if not ps.deck and any(q.points >= v and all(q.points > r.points for r in self.players if r is not q)
                                   for q in self.players):
                return False         # the cleanup that follows ends the game (CR 432.3.a)
        return True

    def do_burn_out(self, p):
        """CR 432.2: recycle the trash into the Main Deck (randomized), then an opponent gains 1 point."""
        ps = self.players[p]
        if ps.deck:
            return
        self.log("burn_out", player=p)
        ps.burned_out = True
        cards = [u for u in ps.trash if not self.objects[u].defn.is_token]
        for u in cards:
            self._to_zone(self.objects[u], "deck")
        self.rng.shuffle(ps.deck)
        for q in self.opponents(p)[:1]:          # 432.2.c: "chooses an opponent" (1v1: the only one)
            self.gain_points(q, 1, "burn_out", None)
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
        if any(src == uid for src, _ in self.rules("cant_ready")):
            return False
        if ctx is not None and (o.defn.is_unit or o.defn.is_gear) and any(
                self.objects[src].controller != o.controller and (self.objects[src].location or ("",))[0] == "bf"
                for src, _ in self.rules("no_ready_enemies")):
            return False        # Mageseeker Warden: "spells and abilities can't ready enemy units and gear"
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

    def do_stun(self, uid, ctx=None, batch=None):
        o = self.objects.get(uid)
        if o is None or o.zone != "board" or o.stunned:
            return            # CR 424.1.a.1: a stunned unit can't be stunned again (no "stun" event)
        if self._chosen_harm_redirect(uid, ctx):
            return
        ev = self.replace_event({"kind": "stun", "uid": uid, "player": o.controller, "loc": o.location})
        if ev is None:
            return
        o.stunned = True      # CR 424.1.b: it only stops its combat damage; stunning doesn't exhaust it
        self.bump()
        self.emit("stun", uid=uid, player=o.controller, loc=o.location, by=ctx.controller if ctx else None, ctx=ctx,
                  batch=batch if batch is not None else self.tick())       # one Stun action: "one or more" triggers once
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
        self.emit("buff", uid=uid, player=o.controller, loc=o.location, by=ctx.controller if ctx else None, ctx=ctx)
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

    def deal_bonus(self, ctx, combat=False):
        """Bonus Damage granted to a Deal action of ctx (CR 712-715): (bonus for every target, {location: extra
        bonus for targets there}) - Annie, Fiery / Ziggs / Ravenborn Tome, and Void Gate ("units here")."""
        bonus, here_bonus = 0, {}
        if ctx is None or combat:
            return bonus, here_bonus
        for src_r, v in self.rules("bonus_damage", player=ctx.controller):
            bonus += v
        so = self.objects.get(ctx.source)
        if so is not None and so.zone == "board" and "gear" in self.chars(ctx.source).types:
            for src_r, v in self.rules("bonus_damage_gear_abilities", player=ctx.controller):    # Ziggs, Short-Fused
                bonus += v
        bonus += ctx.vars.get("__spell_bonus", 0)       # the next spell you play deals N Bonus Damage (flow)
        for src_r, v in self.rules("bonus_damage_here"):
            here_bonus[self.objects[src_r].place] = here_bonus.get(self.objects[src_r].place, 0) + v
        return bonus, here_bonus

    def split_bonus(self, ctx, uids=None):
        """Bonus Damage added to the amount a Split divides (CR 715.3): the ctx bonus, plus a location's bonus
        (Void Gate) when the split affects a unit there. uids=None: the most any target set could get."""
        bonus, here = self.deal_bonus(ctx)
        if uids is None:
            return bonus + max(here.values(), default=0)
        locs = {self.objects[u].location for u in uids if u in self.objects}
        return bonus + max((v for l, v in here.items() if l in locs), default=0)

    def _damage_mod_orders(self, o, amt):
        """CR 372 / 433.1.b: the damage replacement effects on a unit (Lotus Trap's doubling, Counter Strike's
        prevent-next, Ki Barrier-style shields) apply in the order its controller picks. -> list of (order, final
        amount, label) with one entry per distinct outcome, in the default order first. An order is a tuple of
        indexes into o.mods."""
        effs = [i for i, m in enumerate(o.mods) if m.kind == "double_damage"]
        pn = next((i for i, m in enumerate(o.mods) if m.kind == "prevent_next"), None)
        effs += [pn] if pn is not None else []
        effs += [i for i, m in enumerate(o.mods) if m.kind == "prevent" and m.value > 0]
        out, seen = [], set()
        perms = [tuple(effs)] + ([q for q in itertools.permutations(effs) if q != tuple(effs)] if len(effs) <= 5 else [])
        for order in perms:
            a, left = amt, {}
            for i in order:
                m = o.mods[i]
                if a <= 0:
                    break
                if m.kind == "double_damage":
                    a *= 2
                elif m.kind == "prevent_next":
                    left[i], a = 0, 0
                else:
                    used = min(m.value, a)
                    left[i], a = m.value - used, a - used
            key = (a, tuple(sorted(left.items())))
            if key in seen:
                continue
            seen.add(key)
            names = " then ".join(self.label(o.mods[i].source) if o.mods[i].source in self.objects else o.mods[i].kind
                                  for i in order)
            out.append((order, a, f"{names}: {a} damage"))
        return out

    def do_deal(self, uids, amount, ctx, source_uid=None, combat=False, bonus=True, _orders=None, _amts=None):
        """Deal `amount` damage to each target. A single Deal action (CR 418). bonus=False: the amount already
        includes its Bonus Damage (a Split, CR 715.3). `_orders` {uid: mod order} / `_amts` {uid: amount}: set when
        a target's controller has picked the order of its damage replacements (_DamageOrderStep)."""
        _orders, _amts = dict(_orders or {}), dict(_amts or {})
        src = source_uid if source_uid is not None else (ctx.source if ctx else None)
        by = ctx.controller if ctx else None
        # CR 418.6.b.3: when a spell or ability names a unit as the source ("They deal damage equal to their Mights to
        # each other", Alpha Strike), the damage is dealt by that unit, not by the spell or ability: it isn't spell or
        # ability damage (Unyielding Spirit), gets no spell/ability Bonus Damage, and the unit's controller is
        # responsible for it (418.6.b.4)
        so = self.objects.get(source_uid) if source_uid is not None and not combat else None
        unit_source = so is not None and "unit" in (self.chars(source_uid).types if so.zone == "board" else so.defn.types)
        if unit_source:
            by = so.controller if so.zone == "board" else so.temp.get("__lk_controller", so.owner)
            bonus = False
        if amount is None or amount <= 0:
            return                                       # no damage dealt: Bonus Damage doesn't apply (CR 715.4)
        bonus, here_bonus = self.deal_bonus(ctx, combat) if bonus else (0, {})
        uids = list(uids)
        for k, u in enumerate(uids):
            o = self.objects.get(u)
            if o is None or o.zone != "board":
                continue
            amt = _amts[u] if u in _amts else amount + bonus + here_bonus.get(o.location, 0)
            base = {"kind": "damage", "uid": u, "amount": amt, "source": src, "player": o.controller,
                    "loc": o.location, "by": by, "combat": combat, "unit_source": unit_source}
            if u not in _orders:
                # CR 372: several replacement effects on this damage apply in the order its controller picks
                dry = self.replace_event(dict(base), dry=True)
                if dry is not None and dry.get("amount", 0) > 0 and len(self._damage_mod_orders(o, dry["amount"])) > 1:
                    rest = [x for x in uids[k:] if x in self.objects and self.objects[x].zone == "board"]
                    amts = dict(_amts)
                    for x in rest:
                        amts.setdefault(x, amount + bonus + here_bonus.get(self.objects[x].location, 0))
                    c = Context(o.controller, u, here=o.location)
                    c.vars["__dord"] = {"uid": u, "uids": tuple(rest), "amts": amts, "orders": _orders,
                                        "ctx_controller": ctx.controller if ctx is not None else None,
                                        "ctx_source": ctx.source if ctx is not None else None,
                                        "ctx_item": ctx.item if ctx is not None else None,
                                        "source_uid": source_uid, "combat": combat}
                    self.vm_frames.append(Frame([_DamageOrderStep()], c))
                    return
            ev = self.replace_event(base)
            if ev is None or ev.get("amount", 0) <= 0:
                continue
            amt = ev["amount"]
            # Lotus Trap: "Double all damage that would be dealt to it this turn." (one doubling per effect);
            # Counter Strike: "The next time that unit would be dealt damage this turn, prevent it."; prevention
            # shields (mods of kind 'prevent'), in the order picked (default: doublings, prevent-next, shields)
            opts = self._damage_mod_orders(o, amt)
            order = _orders.get(u)
            order = next((q for q, _, _ in opts if q == order), opts[0][0] if opts else ())
            drop = None
            for i in order:
                m = o.mods[i]
                if amt <= 0:
                    break
                if m.kind == "double_damage":
                    amt *= 2
                elif m.kind == "prevent_next":
                    drop, amt = i, 0
                    self.log("prevent", uid=u, amount=amt)
                else:
                    used = min(m.value, amt)
                    # Mods are never changed in place (clones share them): replace the shield with a smaller one
                    o.mods[i] = Mod(m.kind, m.value - used, m.duration, m.source, m.stamp, m.loc)
                    amt -= used
            if drop is not None:
                del o.mods[drop]
                self.restruct()
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
            self.emit("damage", uid=u, amount=amt, source=src, player=o.controller, loc=o.location, by=by, combat=combat,
                      unit_source=unit_source, ctx=ctx)
            self.dirty = True

    def preview_damage(self, u, amount, by, combat=True):
        """How much damage unit u would actually take from `amount` damage dealt by player `by` (replacement
        effects, Lotus Trap doubling, Counter Strike and prevention), without changing anything."""
        o = self.objects.get(u)
        if o is None or o.zone != "board":
            return 0
        ev = self.replace_event({"kind": "damage", "uid": u, "amount": amount, "source": None, "player": o.controller,
                                 "loc": o.location, "by": by, "combat": combat}, dry=True)
        if ev is None or ev.get("amount", 0) <= 0:
            return 0
        amt = ev["amount"]
        for m in o.mods:
            if m.kind == "double_damage":
                amt *= 2
        if any(m.kind == "prevent_next" for m in o.mods):
            return 0
        for m in o.mods:
            if m.kind == "prevent" and m.value > 0 and amt > 0:
                amt -= min(m.value, amt)
        return max(0, amt)

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
        if o.damage <= 0:
            return False
        c = self.chars(uid)
        if c.might is None:
            return False
        if o.damage >= c.might:
            return True
        # Elder Dragon: "Any amount of your damage is enough to kill enemy units."
        return any(o.temp.get(("damaged_by", self.objects[src].controller)) and not self.is_friendly(self.objects[src].controller, o.controller)
                   for src, _ in self.rules("any_damage_kills_enemies"))

    def do_kill(self, uids, ctx=None, by=None, in_combat=False, _first=None):
        """Kill permanents (CR 429): they are sent to their owner's trash; deathknell triggers first.
        `_first`: {uid: replacement key} picked by _ReplacementOrderStep (those deaths are replaced first, by that key)."""
        _first = dict(_first or {})
        alone = {}
        batch = self.tick()            # one id for everything killed at the same time ("one or more units die")
        for u in list(uids):
            o = self.objects.get(u)
            if o is not None and o.zone == "board" and o.location is not None:
                alone[u] = len([x for x in self.units_at(o.location, o.controller)]) == 1
        killer = ctx.controller if ctx is not None else None

        def base_ev(u):
            o = self.objects[u]
            return {"kind": "die", "uid": u, "player": o.controller, "loc": o.location, "killer": killer,
                    "in_combat": in_combat or self.combat is not None and o.location == ("bf", self.combat["bf"]),
                    "card_type": "unit" if "unit" in self.chars(u).types else "gear", "by": by,
                    "token": o.defn.is_token, "might": self.chars(u).might, "stunned": o.stunned, "buffed": o.buffs > 0, "empowered": bool(o.empowered),
                    "alone": alone.get(u, False), "dmg_item": o.temp.get("dmg_item") if by == "damage" else None,
                    "batch": batch}
        dying = [u for u in dict.fromkeys(uids) if u in self.objects and self.objects[u].zone == "board"
                 and self.defn_of(u).is_permanent]
        # CR 373: a replacement that can be applied to only one event (Zhonya's Hourglass) and could replace several of
        # these simultaneous deaths is applied where its controller chooses.
        contest = self._contested_single_use(dying, base_ev, _first)
        if contest is not None:
            key, cands = contest
            c = Context(self.objects[key[0]].controller, key[0], here=self.objects[key[0]].place)
            c.vars["__rord"] = {"uids": tuple(dying), "key": key, "cands": tuple(cands), "first": _first, "by": by,
                                "in_combat": in_combat, "ctx_controller": killer,
                                "ctx_source": ctx.source if ctx is not None else None}
            self.vm_frames.append(Frame([_ReplacementOrderStep()], c))
            return
        # CR 372: when several replacement effects could replace one death, the dying object's controller picks the
        # one that applies (a replaced death is no longer a death, so the others then don't apply).
        for u in dying:
            if u in _first:
                continue
            opts = self.die_replacements(base_ev(u))
            if len(opts) >= 2:
                c = Context(self.objects[u].controller, u, here=self.objects[u].place)
                c.vars["__rord"] = {"uids": tuple(dying), "unit": u, "opts": tuple(k for k, _ in opts),
                                    "labels": tuple(l for _, l in opts), "first": _first, "by": by,
                                    "in_combat": in_combat, "ctx_controller": killer,
                                    "ctx_source": ctx.source if ctx is not None else None}
                self.vm_frames.append(Frame([_ReplacementChoiceStep()], c))
                return
        dying.sort(key=lambda u: (list(_first).index(u) if u in _first else len(_first)))
        events = []
        for u in dying:
            ev = self.replace_event(base_ev(u), first=_first.get(u))
            if ev is not None:
                events.append((u, ev))
        # CR 383.2.c.2: an object leaving the board at the same time as another one doesn't see that one leave
        # (Viktor, Leader dying together with another unit makes no Recruit); its own death/leave triggers still
        # work (383.2.c.3). Recalled units stay on the board, and deferred ones wait for their controller.
        prev = getattr(self, "_leaving", frozenset())
        self._leaving = prev | {u for u, ev in events
                                if not ev.get("deferred") and ev.get("replaced_with") != "recall"}
        try:
            for u, ev in events:
                if ev.get("deferred"):                      # "you may ... instead": its controller decides first
                    self._ask_optional_replacement(u, ev, ctx)
                    continue
                self._finish_death(u, ev, ctx)
        finally:
            self._leaving = prev

    def _contested_single_use(self, dying, base_ev, first):
        """A single-use 'die' replacement (not yet assigned in `first`) that applies to 2+ of `dying`, as
        (key, candidate uids), or None."""
        if len(dying) < 2:
            return None
        done = set(first.values())
        for src, o in list(self.objects.items()):
            if o.zone in (None, "gone"):
                continue
            abl = self.abilities(src) if o.zone == "board" else self._abilities_of(src, o)
            for ab in abl:
                if not isinstance(ab, Replacement) or ab.event != "die" or not getattr(ab, "single_use", False):
                    continue
                key = (src, id(ab))
                if key in done or not ab.active(self, src):
                    continue
                cands = []
                for u in dying:
                    if u in first:
                        continue
                    try:
                        if ab.applies(self, src, base_ev(u)):
                            cands.append(u)
                    except (KeyError, AttributeError, TypeError):
                        pass
                if len(cands) >= 2:
                    return key, cands
        return None

    def _ask_optional_replacement(self, u, ev, ctx):
        """Keep u on the board and push a frame that asks the replacement's controller (runs before anything else)."""
        src = ev["deferred"][0]
        c = Context(self.objects[src].controller, src, here=self.objects[src].place)
        c.vars["__orep"] = {"uid": u, "ev": ev, "ctx_controller": ctx.controller if ctx is not None else None,
                            "ctx_source": ctx.source if ctx is not None else None}
        self.vm_frames.append(Frame([_OptionalReplacementStep()], c))

    def _optional_replacement_ability(self, key):
        src, aid = key
        o = self.objects.get(src)
        if o is None or o.zone in (None, "gone"):
            return None
        abl = self.abilities(src) if o.zone == "board" else self._abilities_of(src, o)
        return next((ab for ab in abl if id(ab) == aid), None)

    def _finish_death(self, u, ev, ctx):
        o = self.objects.get(u)
        if o is None or o.zone != "board":
            return
        if ev.get("replaced_with") == "banish":         # "if it would die this turn, banish it instead" (Smite)
            self.do_banish([u], ctx)
            return
        if ev.get("replaced_with") == "recall":
            self.do_recall(u, ctx, heal=True, exhaust=ev.get("exhaust", False))
            return
        ev = {k: v for k, v in ev.items() if k not in ("deferred", "applied")}
        # CR 808.1.d.2: death triggers are added before the card moves (they see the board state)
        self.log("die", uid=u, name=o.defn.name, loc=o.location)
        if ev["card_type"] == "unit":
            key = ("units_died", ev["player"])           # "if an enemy unit has died this turn"
            self.turn_memo.setdefault(("first_unit_die_batch", ev["player"]), ev.get("batch"))  # "the first time"
            self.turn_memo[key] = self.turn_memo.get(key, 0) + 1
        if ev["card_type"] == "unit" and getattr(self, "phase", None) == "beginning":
            self.turn_memo[("died_in_beginning", ev["player"])] = True      # Shadow Watcher
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

    def do_recycle(self, uids, ctx=None, rune_order=None):
        """Recycle (CR 417): cards go to the bottom of their owner's deck; runes to the bottom of the rune deck.
        Several cards recycled at once go to the bottom in a random order (CR 417.5); `rune_order`: runes recycled
        with them, in the order their owner chose (417.5.a), top-most first."""
        uids = list(uids)
        if len(uids) > 1:
            self.rng.shuffle(uids)
        uids += list(rune_order or ())
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
            self.emit("recycle", uid=u, player=o.owner, from_zone=was, loc=loc, ctx=ctx, batch=batch, to=o.zone)
            if was == "board":
                self.emit("leave", uid=u, player=o.owner, loc=loc, ctx=ctx)
                self.dirty = True

    def do_burn(self, p, n, ctx=None):
        """Burn (CR 441): put the top n cards of the deck into the trash."""
        ps = self.players[p]
        for _ in range(n):
            if not self._burn_out_until_cards(p):      # CR 432.1.b: moving cards out of an empty deck burns out
                return
            u = ps.deck[0]
            self._to_zone(self.objects[u], "trash")
            self.emit("burn", uid=u, player=p, ctx=ctx)

    def do_channel(self, p, n, exhausted=False, ctx=None):
        ps = self.players[p]
        made = []
        extra = len(self.rules("channel_plus_one", player=p)) if n > 0 else 0     # Seraphic Wyvern: "+1 exhausted rune"
        plan = [bool(exhausted)] * n + [True] * extra
        if extra:
            self.log("channel_extra", player=p, n=extra)
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
        self.emit("empower", uid=uid, player=o.controller, loc=o.location, by=ctx.controller if ctx else None, ctx=ctx)
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

    def valid_destination(self, uid, dest, standard=False, mover=None):
        """`mover`: the player whose move or effect moves the unit (default its controller)."""
        o = self.objects[uid]
        if dest == o.location:
            return False
        if self.cant_move(uid):
            return False
        by = self.keyword_value(uid, "cant_move_by")
        if by and (o.controller if mover is None else mover) in by:
            return False          # Vex, Apathetic: "They can't move it this turn" (other players still may)
        if dest[0] == "base":
            if any(v == "all" or self.objects[src].place == o.location for src, v in self.rules("cant_move_to_base")):
                return False          # "Units can't move from here to base" / "Units can't move to base."
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
            mover = ctx.controller if (ctx is not None and not standard and ctx.controller is not None) else o.controller
            if not self.valid_destination(u, dest, mover=mover):
                continue
            if ctx is not None and not standard and ctx.controller is not None \
                    and not self.is_friendly(ctx.controller, o.controller) and self.has_keyword(u, "unmovable_by_enemies"):
                continue          # Jagged Cutlass: "I can't be moved by enemy spells and abilities."
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
        if o.location == base:             # "heal it, exhaust it, and recall it" still heals and exhausts a unit in base
            if heal:
                o.damage = 0
                o.temp = {k: v for k, v in o.temp.items() if not (isinstance(k, tuple) and k[0] == "damaged_by")}
            if exhaust:
                self.do_exhaust(uid, ctx)      # the Exhaust action: "When I become exhausted" triggers (CR 415)
            self.dirty = True
            return
        frm = o.location
        if heal:
            o.damage = 0
            o.temp = {k: v for k, v in o.temp.items() if not (isinstance(k, tuple) and k[0] == "damaged_by")}
        if exhaust:
            self.do_exhaust(uid, ctx)          # "heal it, exhaust it, and recall it", in that order
        o.location = base
        self._on_change_location(o)
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
        if defn.is_unit and loc is not None and loc[0] == "bf" \
                and loc in {self.objects[src].place for src, v in self.rules("cant_play_here")}:
            self.log("token_blocked", name=name, loc=loc, player=p)    # Rockfall Path: token units are played too (CR 185.2.a)
            return None
        o = self._new_obj(defn, p)
        if defn.type == "battlefield":
            return self._create_battlefield_token(o, loc, ctx)
        o.zone = "board"
        o.location = loc if loc is not None else ("base", p)
        o.controller = p
        self.restruct()
        if defn.is_unit:
            if self.consume_turn_effects("enter_ready", player=p):     # "friendly units enter ready this turn"
                ready = True
            ev = self.replace_event({"kind": "enter_ready", "uid": o.uid, "player": p, "ready": ready, "loc": o.location})
            if ev is not None:
                ready = bool(ev.get("ready"))
        o.exhausted = (not ready) if defn.is_unit else bool(exhausted_gear)
        o.entered_stamp = self.tick()
        o.token_source = ctx.source if ctx else None
        self.bump()
        self.log("token", uid=o.uid, name=name, loc=o.location, player=p)
        ctype = "unit" if defn.is_unit else "gear"
        self.turn_memo.setdefault("played_at", []).append((p, o.location))   # a token is played too (Hunters' Circle)
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
        self.restruct()
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
        self.restruct()
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
                        self.restruct()
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
                        # a spell played from the trash for its Flow cost is banished whenever it leaves the chain
                        # other than by its own execution, so countering it banishes it too (CR 829.1.b.1)
                        flow = it.kind == "spell" and it.ctx is not None and it.ctx.vars.get("__flow")
                        self._to_zone(o, "banish" if flow else "trash")
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
        self.restruct()
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
        self.restruct()

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
            self.emit("to_hand", uid=uid, player=o.owner, from_zone=was, loc=loc, ctx=ctx)     # Ripper's Bay
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
            self._sync_attachments(o)
        if duration != "permanent":
            o.mods.append(Mod("control", o.owner, duration, ctx.source if ctx else None, self.tick()))
        self.restruct()
        self.dirty = True

    def _end_bound_legends(self):
        """A legend added by Neeko, Blending In exists only while that Neeko is on the board."""
        for _, o in self.board_items():
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
                self.restruct()
                if o.zone == "board" and o.controller != m.value:
                    o.controller = m.value
                    if o.location is not None and o.location[0] == "base":
                        o.location = ("base", o.controller)
                        self._sync_attachments(o)
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
        memo = self._canpay_memo
        if memo is not None:               # inside legal_actions: the state can't change between calls
            key = (p, energy, tuple(power), tuple(extra_exhaust),
                   None if purpose is None else tuple(sorted((k, frozenset(v) if isinstance(v, set) else v)
                                                              for k, v in purpose.items())))
            r = memo.get(key)
            if r is None:
                r = memo[key] = payment.can_pay(self, p, energy, list(power), purpose, extra_exhaust)
            return r
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
    @staticmethod
    def _could_target_at_bf(sel):
        """CR 811.1.d.2-3: a hidden card's targets must be at its battlefield "unless it explicitly restricts
        targeting in such a way that makes this impossible". True when the selector itself could match something
        at a battlefield (so an empty choice there means no valid target, not a free choice)."""
        if not hasattr(sel, "kind") or getattr(sel, "zone", "board") != "board":
            return False
        if sel.kind in ("legend", "rune", "battlefield"):
            return False
        if sel.where in ("base", "own_base") or (isinstance(sel.where, str) and sel.where.startswith("loc:")):
            return False
        # a pred restricting to another location ("at another location": Tideturner, Evelynn, Resonating Strike) can never
        # be met there, so the choice stays free; any other condition (Facebreaker, Switcheroo) must be met there
        return not getattr(sel, "elsewhere", False)

    def _unpaid_base_cost(self, ctx):
        """(energy, power[, purpose]) the item being finalized still has to pay, for the Deflect check; None when it
        is already paid or a cost reduction chosen later could lower it (then only the tax is checked)."""
        if "__base_cost" in ctx.vars:
            return ctx.vars["__base_cost"]
        if ctx.item is None:
            return None
        it = next((x for x in self.chain if x.id == ctx.item), None)
        if it is None or it.finalized or not it.cost or it.cost.get("paid") is not None:
            return None
        if self._exhaust_reducers(it.controller) or (it.uid in self.objects and self._variable_reduce_perm(it.uid)):
            return None
        return (it.cost.get("energy", 0), list(it.cost.get("power", ())))

    def hidden_source_gone(self, ctx, stamp=None):
        """CR 811.1.d.3.a: a play effect of a permanent played from facedown reads where it was played from its source;
        once the source is off the board (or a new object), its battlefield-restricted choices have no legal target."""
        o = self.objects.get(ctx.source) if ctx.source is not None else None
        if o is None or ctx.target_bf is None or o.base_defn().type not in ("unit", "gear"):
            return False
        return o.zone != "board" or (stamp is not None and o.entered_stamp != stamp)

    def choice_candidates(self, ctx, sel, targeted=True):
        if isinstance(sel, (list, tuple)):
            return [u for u in sel if u in self.objects]
        cands = sel.candidates(self, ctx)
        if targeted:
            # Hidden (CR 811.1.d): targets of a card played from facedown must be at that battlefield when possible
            if ctx.target_bf is not None:
                here = [u for u in cands if self.objects[u].location == ctx.target_bf]
                if self.hidden_source_gone(ctx):
                    here = []     # CR 811.1.d.3.a: its source left the board, so it can't choose at that battlefield
                if here or self._could_target_at_bf(sel):
                    cands = here          # no valid target at that battlefield -> no target (CR 811.1.d)
            # Deflect (CR 809): opponents' targeting costs [A] per deflect value; drop unaffordable targets
            # CR 355.16: no choice that makes the play's costs unpayable, so the tax is checked together with the
            # cost still to pay (spell or ability cost, plus the Deflect of targets already chosen)
            out = []
            base = self._unpaid_base_cost(ctx)
            purpose = base[2] if base is not None and len(base) > 2 else self.ctx_purpose(ctx)
            chosen = [x for x in self._target_uids(ctx) if x in self.objects]
            for u in cands:
                o = self.objects[u]
                if o.zone == "board" and not self.is_friendly(o.controller, ctx.controller):
                    if self.chars(u).keywords.get("untargetable"):
                        continue
                    d = self.keyword_value(u, "deflect")
                    if d:
                        prior = sum(self.keyword_value(x, "deflect") for x in chosen if x != u
                                    and self.objects[x].zone == "board" and not self.is_friendly(self.objects[x].controller, ctx.controller))
                        e0, p0 = (base[0], list(base[1])) if base is not None else (0, [])
                        if not self.can_pay(ctx.controller, e0, p0 + ["any"] * (d + prior), purpose=purpose):
                            continue
                out.append(u)
            cands = out
        return cands

    # ------------------------------------------------------------------ cloning / snapshots
    def clone(self, copy_rng=True):
        """An independent copy of the game. copy_rng=False leaves `rng` unset for a caller that replaces it at once
        (determinize): copying the generator's state is costly, above all in PyPy."""
        if _PYPY:
            g = Game.__new__(Game)
            g.__dict__ = self.__dict__.copy()          # copy.copy and __dict__.update are ~40x slower in PyPy
        else:
            g = copy.copy(self)
        g._statics_cache = g._trig_cache = g._rules_cache = g._grant_cache = g._board_cache = g._pao_cache = None
        g._addsrc_cache = None                         # caches hold this game's objects
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
        if copy_rng:
            g.rng = random.Random.__new__(random.Random)     # no seeding from the OS: the state is set right away
            g.rng.setstate(self.rng.getstate())
        else:
            g.rng = None
        g.pending = self._clone_decision(self.pending) if self.pending else None
        g._computing = set()
        g._partial, g._recursed = {}, set()
        g._canpay_memo = None
        g.combat_result_memo = {}
        self.__dict__.pop("_ctx_map", None)
        g.__dict__.pop("_ctx_map", None)
        return g

    def _clone_obj(self, o):
        c = _copy_obj_fields(o)
        c.mods = list(o.mods) if o.mods else []        # Mod objects are immutable once made
        c.attachments = list(o.attachments) if o.attachments else []
        c.counters = _copy_containers(o.counters) if o.counters else {}
        c.temp = _copy_containers(o.temp) if o.temp else {}
        c.chars_cache = None
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


def _active_printed(o, abilities):
    """CR 135.4 / 721.2: an attached card's printed rules text is inactive (its abilities don't trigger, apply or
    activate; its keywords can still be seen, 135.4.a). Abilities scripted from its effect text (source_text is the
    effect text, e.g. Guardian Angel's replacement) belong to the unit it's attached to and stay."""
    eff = o.defn.effect_text
    return [a for a in abilities if eff and getattr(a, "source_text", None) == eff]


_TEMPORARY = []


def _grant_keyword_trigger(c, v):
    """A granted triggered-ability keyword is its trigger too. [Vision]: one instance per grant (CR 817.1.b, 817.2:
    Forecaster's "Your Mechs have [Vision]", Gemcraft Seer). [Hunt]/[Disarm]: one trigger using the summed value
    (CR 823.2, 831.1.d.1: Clanging Sentry's "Your Mechs have [Disarm]")."""
    kw, val_ = (v[0], v[1]) if isinstance(v, tuple) else (v, True)
    if val_ is False or val_ is None:
        return
    if kw == "vision":
        c.abilities.append(_granted_vision())
    elif kw in ("hunt", "disarm"):
        if not any(getattr(a, "keyword", None) == kw for a in c.abilities):
            from .scripts import hunt_ability, disarm_ability
            c.abilities.append(hunt_ability() if kw == "hunt" else disarm_ability())


_VISION = []


def _granted_vision():
    if not _VISION:
        from .abilities import Triggered
        from . import ops as O
        _VISION.append(Triggered("enter_self", [O.Predict(1)], label="Vision", keyword="vision"))
    return _VISION[0]


def _temporary_ability():
    if not _TEMPORARY:
        from .abilities import Triggered
        from . import ops as O
        from .vm import Ref
        from .scripts import temporary_ability
        _TEMPORARY.append(temporary_ability())
    return _TEMPORARY[0]


class _OptionalReplacementStep:
    """VM step for an optional death replacement ("you may kill a friendly unit to ... instead", Mordekaiser):
    the source's controller declines or picks an option; then the death finishes (CR 370, 372)."""

    def run(self, game, ctx):
        info = ctx.vars["__orep"]
        u, ev = info["uid"], info["ev"]
        ab = game._optional_replacement_ability(ev["deferred"])
        o = game.objects.get(u)
        if o is None or o.zone != "board":
            return None
        opts = []
        if ab is not None and ab.active(game, ev["deferred"][0]):
            try:
                opts = list(ab.options(game, ev["deferred"][0], ev))
            except (KeyError, AttributeError, TypeError):
                opts = []
        if not opts:
            return self.resume(game, ctx, "decline")
        if ab.option_label is not None:
            labels = [f"don't ({game.label(u)} dies)"] + [ab.option_label(game, ev["deferred"][0], x) for x in opts]
        else:
            labels = [f"don't ({game.label(u)} dies)"] + [f"kill {game.label(x)}" if x in game.objects else str(x) for x in opts]
        return Decision(ctx.controller, "optional_replacement", ["decline"] + opts, out="__orep_choice", labels=labels,
                        info={"uid": u, "source": ev["deferred"][0], "label": ab.label or "optional replacement"})

    def resume(self, game, ctx, choice):
        info = ctx.vars["__orep"]
        u, ev = info["uid"], dict(info["ev"])
        key, applied = ev.pop("deferred"), set(ev.pop("applied", ()))
        dctx = Context(info["ctx_controller"], info["ctx_source"]) if info["ctx_controller"] is not None else None
        if choice in (None, "decline"):           # declined: the other replacements may still apply
            ev = game.replace_event(ev, skip=applied | {key})
            if ev is None:
                return None
            if ev.get("deferred"):
                game._ask_optional_replacement(u, ev, dctx)
                return None
            game._finish_death(u, ev, dctx)
            return None
        src = key[0]
        ab = game._optional_replacement_ability(key)
        so = game.objects.get(src)
        if ab is not None and ab.once_per_turn and so is not None:
            so.temp[("rpt", id(ab))] = game.turn
        game.log("replace", source=src, event="die", label=ab.label if ab is not None else "")
        ev = ab.replace(game, src, ev, choice) if ab is not None else ev
        ev = game.replace_event(ev, skip=applied | {key})
        if ev is None:
            return None
        if ev.get("deferred"):
            game._ask_optional_replacement(u, ev, dctx)
            return None
        game._finish_death(u, ev, dctx)
        return None


class _DamageOrderStep:
    """VM step: a unit about to be dealt damage has several damage replacement effects whose order changes the
    outcome (Lotus Trap + Ki Barrier, Counter Strike + a shield): its controller picks the order (CR 372, 433.1.b
    example at 467.2.c.5); then the Deal goes on for it and the targets after it."""

    def _opts(self, game, ctx):
        info = ctx.vars["__dord"]
        u = info["uid"]
        o = game.objects.get(u)
        if o is None or o.zone != "board":
            return []
        return game._damage_mod_orders(o, info["amts"][u])

    def run(self, game, ctx):
        opts = self._opts(game, ctx)
        if len(opts) < 2:
            return self.resume(game, ctx, None)
        u = ctx.vars["__dord"]["uid"]
        return Decision(ctx.controller, "order_replacement", list(range(len(opts))), out="__dord_choice",
                        labels=[l for _, _, l in opts], info={"uid": u, "label": game.label(u)})

    def resume(self, game, ctx, choice):
        info = ctx.vars["__dord"]
        opts = self._opts(game, ctx)
        orders = dict(info["orders"])
        orders[info["uid"]] = opts[choice][0] if choice is not None and choice < len(opts) else (opts[0][0] if opts else ())
        dctx = None
        if info["ctx_controller"] is not None:
            dctx = Context(info["ctx_controller"], info["ctx_source"])
            dctx.item = info["ctx_item"]
        game.do_deal(list(info["uids"]), 0 if not info["uids"] else 1, dctx, source_uid=info["source_uid"],
                     combat=info["combat"], bonus=False, _orders=orders, _amts=info["amts"])
        return None


class _ReplacementOrderStep:
    """VM step: the controller of a single-use death replacement picks which of several simultaneous deaths it
    replaces (CR 373, e.g. Zhonya's Hourglass when two friendly units die together); then the deaths go on."""

    def run(self, game, ctx):
        info = ctx.vars["__rord"]
        cands = [u for u in info["cands"] if u in game.objects and game.objects[u].zone == "board"]
        if len(cands) < 2:
            return self.resume(game, ctx, None)
        src = info["key"][0]
        name = game.label(src)
        return Decision(ctx.controller, "order_replacement", cands, out="__rord_choice",
                        labels=[f"{name} saves {game.label(u)}" for u in cands],
                        info={"source": src, "label": name})

    def resume(self, game, ctx, choice):
        info = ctx.vars["__rord"]
        first = dict(info["first"])
        if choice is not None:
            first[choice] = info["key"]
        dctx = Context(info["ctx_controller"], info["ctx_source"]) if info["ctx_controller"] is not None else None
        game.do_kill(info["uids"], dctx, by=info["by"], in_combat=info["in_combat"], _first=first)
        return None


class _ReplacementChoiceStep:
    """VM step: several replacement effects could replace one death (Zhonya's Hourglass and Smite, Guardian Angel and
    Zhonya's ...): the dying object's controller picks the one that applies (CR 372); then the deaths go on."""

    def run(self, game, ctx):
        info = ctx.vars["__rord"]
        u = info["unit"]
        if u not in game.objects or game.objects[u].zone != "board":
            return self.resume(game, ctx, None)
        return Decision(ctx.controller, "order_replacement", list(range(len(info["opts"]))), out="__rord_choice",
                        labels=[f"{l} replaces {game.label(u)}'s death" for l in info["labels"]],
                        info={"uid": u, "label": game.label(u)})

    def resume(self, game, ctx, choice):
        info = ctx.vars["__rord"]
        first = dict(info["first"])
        if choice is not None:
            first[info["unit"]] = info["opts"][choice]      # options are indexes (ability ids differ between runs)
        dctx = Context(info["ctx_controller"], info["ctx_source"]) if info["ctx_controller"] is not None else None
        game.do_kill(info["uids"], dctx, by=info["by"], in_combat=info["in_combat"], _first=first)
        return None
