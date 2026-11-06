"""Card definitions (static, shared) and the card database."""
from __future__ import annotations

import json
from pathlib import Path

DOMAINS = ("fury", "calm", "mind", "body", "chaos", "order")
DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "cards" / "riftbound.json"


class CardDef:
    """Printed characteristics of a card or token. Immutable after scripts are attached."""
    __slots__ = ("id", "name", "type", "types", "supertype", "domains", "energy", "power", "might", "might_bonus",
                 "tags", "keywords", "text", "effect_text", "set", "image", "printings", "is_token", "abilities",
                 "effect_abilities", "script_status", "data_incomplete", "rarity")

    def __init__(self, **kw):
        self.id = kw["id"]
        self.name = kw["name"]
        self.type = kw["type"]
        self.types = tuple(kw.get("types") or [kw["type"]])
        self.supertype = kw.get("supertype")
        self.domains = tuple(kw.get("domains") or ())
        self.energy = kw.get("energy") or 0
        self.power = kw.get("power") or 0
        self.might = kw.get("might")
        self.might_bonus = kw.get("might_bonus")
        self.tags = tuple(kw.get("tags") or ())
        self.keywords = dict(kw.get("keywords") or {})
        self.text = kw.get("text") or ""
        self.effect_text = kw.get("effect_text") or ""
        self.set = kw.get("set", "")
        self.image = kw.get("image", "")
        self.printings = tuple(kw.get("printings") or ())
        self.rarity = kw.get("rarity", "")
        self.is_token = kw.get("is_token", False)
        self.data_incomplete = kw.get("data_incomplete", False)
        self.abilities = []          # rules-text abilities (filled by scripts)
        self.effect_abilities = []   # effect-text abilities, active while attached (equipment)
        self.script_status = "none"  # none | keywords | auto | manual

    @property
    def is_unit(self):
        return "unit" in self.types

    @property
    def is_gear(self):
        return "gear" in self.types

    @property
    def is_permanent(self):
        return self.is_unit or self.is_gear

    @property
    def is_champion(self):
        return self.supertype == "champion"

    @property
    def is_equipment(self):
        return "Equipment" in self.tags

    def __repr__(self):
        return f"<{self.id} {self.name}>"


# Tokens defined by CR 187.
TOKEN_DEFS = {
    "Recruit": dict(id="TOKEN-RECRUIT", name="Recruit", type="unit", might=1, tags=["Recruit"]),
    "Sprite": dict(id="TOKEN-SPRITE", name="Sprite", type="unit", might=3, tags=["Fae"], keywords={"temporary": True}),
    "Sand Soldier": dict(id="TOKEN-SAND", name="Sand Soldier", type="unit", might=2, tags=["Shurima"]),
    "Mech": dict(id="TOKEN-MECH", name="Mech", type="unit", might=3, tags=["Mech"]),
    "Gold": dict(id="TOKEN-GOLD", name="Gold", type="gear", text="[Reaction] Kill this, [T]: [Add] [A]."),
    "Reflection": dict(id="TOKEN-REFLECTION", name="Reflection", type="unit", might=0),
    "Bird": dict(id="TOKEN-BIRD", name="Bird", type="unit", might=1, tags=["Bird"], keywords={"deflect": True}),
    "Brush": dict(id="TOKEN-BRUSH", name="Brush", type="battlefield",
                  text="Bird, Cat, Dog, Poro, and Ivern units here have +1 [M]. When you score here, you may replace this with the battlefield it replaced."),
    "Baron Pit": dict(id="TOKEN-BARONPIT", name="Baron Pit", type="battlefield", text="Units can move here from anywhere."),
    "Tentacle": dict(id="TOKEN-TENTACLE", name="Tentacle", type="unit", might=1, tags=["Bilgewater"]),
    "Shadow Clone": dict(id="TOKEN-SHADOWCLONE", name="Shadow Clone", type="unit", might=0,
                         text="When I attack, you may banish a unit from your trash. If you do, give me [Assault 4] this turn."),
    "Bomb": dict(id="TOKEN-BOMB", name="Bomb", type="gear", tags=["Bomb"], keywords={"deploy": True, "deathknell": True},
                 text="[Deploy] [Deathknell] Deal 2 to an enemy unit here and kill all other Bombs you control here."),
}


class CardDB:
    def __init__(self):
        self.by_id: dict[str, CardDef] = {}
        self.by_name: dict[str, CardDef] = {}
        self.tokens: dict[str, CardDef] = {}

    @classmethod
    def load(cls, path=DEFAULT_DB) -> "CardDB":
        db = cls()
        data = json.loads(Path(path).read_text())
        set_rank = {"OGN": 0, "OGS": 1, "SFD": 2, "UNL": 3, "VEN": 4, "RAD": 5}
        for raw in sorted(data["cards"], key=lambda c: set_rank.get(c["set"], -1)):
            c = CardDef(**{k: v for k, v in raw.items() if k in CardDef.__slots__ or k in ("types",)})
            db.by_id[c.id] = c
            for p in c.printings:
                db.by_id.setdefault(p.upper(), c)
            # Same name = same card (CR 132); the latest printing carries the current errata'd text.
            db.by_name[c.name.lower()] = c
        for name, t in TOKEN_DEFS.items():
            tok = CardDef(**{**t, "is_token": True})
            db.tokens[name] = tok
            db.by_id[tok.id] = tok
        return db

    def card(self, key: str) -> CardDef:
        k = key.strip()
        if k.upper() in self.by_id:
            return self.by_id[k.upper()]
        if k.lower() in self.by_name:
            return self.by_name[k.lower()]
        if k in self.tokens:
            return self.tokens[k]
        raise KeyError(f"unknown card {key!r}")

    def __iter__(self):
        seen = set()
        for c in self.by_id.values():
            if id(c) not in seen:
                seen.add(id(c))
                yield c
