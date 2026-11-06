"""Mutable game objects, players, battlefields and the characteristics (layers) snapshot."""
from __future__ import annotations

NUMERIC_KEYWORDS = ("assault", "shield", "deflect", "disarm", "hunt")


class Mod:
    """A modification applied to a game object by an effect.

    kind: 'might' (arithmetic) | 'base_might' (set) | 'keyword' ((kw, value)) | 'ability' (Ability) | 'tag' (str)
          | 'prevent' (int, consumed by damage) | 'control' (player)
    duration: 'turn' | 'permanent' | 'combat' | 'while_here' (until the object changes location) | 'leaves' (until it leaves the board)
    """
    __slots__ = ("kind", "value", "duration", "source", "stamp", "loc")

    def __init__(self, kind, value, duration, source, stamp, loc=None):
        self.kind, self.value, self.duration, self.source, self.stamp, self.loc = kind, value, duration, source, stamp, loc

    def __repr__(self):
        return f"Mod({self.kind}={self.value!r},{self.duration})"


class Chars:
    """Characteristics of an object after layers are applied."""
    __slots__ = ("name", "types", "supertype", "tags", "keywords", "might", "abilities", "domains", "energy", "power", "defn")

    def __init__(self, defn):
        self.defn = defn
        self.name = defn.name
        self.types = set(defn.types)
        self.supertype = defn.supertype
        self.tags = set(defn.tags)
        self.keywords = dict(defn.keywords)
        self.might = defn.might
        self.abilities = list(defn.abilities)
        self.domains = tuple(defn.domains)
        self.energy = defn.energy
        self.power = defn.power

    def add_keyword(self, kw, value):
        if kw in NUMERIC_KEYWORDS:
            v = 1 if value is True or value is None else int(value)
            cur = self.keywords.get(kw)
            cur = 0 if cur in (None, False) else (1 if cur is True else int(cur))
            self.keywords[kw] = cur + v
        elif value is False:
            self.keywords.pop(kw, None)
        else:
            self.keywords[kw] = value if value is not None else True

    def kw(self, name, default=0):
        v = self.keywords.get(name)
        if v is None or v is False:
            return default
        return 1 if v is True else v

    @property
    def mighty(self):
        return self.might is not None and self.might >= 5


class GameObject:
    __slots__ = ("uid", "defn", "owner", "controller", "zone", "location", "exhausted", "damage", "buffs",
                 "empowered", "stunned", "attached_to", "attachments", "designation", "mods", "copy_of",
                 "chars_cache", "chars_version", "entered_stamp", "facedown_turn", "hidden_at", "played_from",
                 "counters", "temp", "domain", "accel_paid", "token_source")

    def __init__(self, uid, defn, owner):
        self.uid, self.defn, self.owner, self.controller = uid, defn, owner, owner
        self.zone, self.location = "deck", None
        self.exhausted, self.damage, self.buffs, self.empowered, self.stunned = False, 0, 0, 0, False
        self.attached_to, self.attachments = None, []
        self.designation = None            # 'attacker' | 'defender' | None (combat)
        self.mods = []
        self.copy_of = None
        self.chars_cache, self.chars_version = None, -1
        self.entered_stamp = 0             # timestamp of entering current zone
        self.facedown_turn = None          # turn number the card was hidden
        self.hidden_at = None
        self.played_from = None
        self.counters = {}
        self.temp = {}                     # scratch per-object memory (e.g. once-per-turn flags)
        self.domain = defn.domains[0] if defn.domains and "rune" in defn.types else None
        self.accel_paid = False
        self.token_source = None

    def __repr__(self):
        return f"<{self.uid}:{self.defn.name} {self.zone}@{self.location}>"

    def base_defn(self):
        return self.copy_of or self.defn

    @property
    def place(self):
        """Location used for 'here': a battlefield card sits at ('bfcard', i) but its 'here' is ('bf', i)."""
        loc = self.location
        if loc is not None and loc[0] == "bfcard":
            return ("bf", loc[1])
        return loc


class PlayerState:
    __slots__ = ("idx", "name", "deck_name", "hand", "deck", "trash", "banish", "rune_deck", "runes", "legend",
                 "champion", "battlefield_cards", "points", "xp", "energy", "power", "pool_r", "played_this_turn", "burned_out",
                 "legend_name", "memo", "passed_showdown", "conceded")

    def __init__(self, idx):
        self.idx = idx
        self.name = f"P{idx}"
        self.deck_name = ""
        self.hand, self.deck, self.trash, self.banish = [], [], [], []
        self.rune_deck, self.runes = [], []
        self.legend, self.champion = None, None
        self.battlefield_cards = []
        self.points, self.xp = 0, 0
        self.energy, self.power = 0, []          # rune pool (unrestricted Energy, Power domains / 'any')
        self.pool_r = []                         # restricted pool resources: (res 'E' or domain, restriction text)
        self.played_this_turn = []               # uids finalized this turn
        self.burned_out = False
        self.legend_name = ""
        self.memo = {}                           # per-turn memory for once-per-turn effects
        self.passed_showdown = False
        self.conceded = False


class BattlefieldState:
    __slots__ = ("idx", "uid", "owner", "controller", "contested_by", "staged_showdown", "staged_combat", "facedown", "replaced")

    def __init__(self, idx, uid, owner):
        self.idx, self.uid, self.owner = idx, uid, owner
        self.controller = None
        self.contested_by = None
        self.staged_showdown = False
        self.staged_combat = False
        self.facedown = {}      # player -> uid of hidden card
        self.replaced = None    # original battlefield uid when replaced by a token battlefield


class ChainItem:
    """Spell, played permanent, activated/triggered/reflexive ability on the chain."""
    __slots__ = ("id", "kind", "controller", "uid", "ability", "ctx", "finalized", "label", "resolves_now", "countered",
                 "is_trigger", "is_add", "code", "target_code", "cost", "stamp", "removed")

    def __init__(self, id, kind, controller, uid=None, ability=None, ctx=None, label="", code=None, target_code=None, cost=None):
        self.id, self.kind, self.controller, self.uid, self.ability, self.ctx = id, kind, controller, uid, ability, ctx
        if ctx is not None and getattr(ctx, "item", None) is None:
            ctx.item = id          # effects know which chain item they belong to (spell-only bonuses, kill credit)
        self.finalized = False
        self.label = label
        self.resolves_now = kind in ("unit", "gear", "add")
        self.countered = False
        self.is_trigger = kind in ("trigger", "reflexive")
        self.is_add = kind == "add"
        self.code, self.target_code, self.cost = code, target_code, cost
        self.stamp = 0
        self.removed = False

    def __repr__(self):
        return f"ChainItem({self.id} {self.kind} P{self.controller} {self.label})"
