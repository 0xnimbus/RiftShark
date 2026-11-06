"""Card, legend and deck definitions, loaded from JSON data files."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DOMAINS = ("fury", "calm", "mind", "body", "chaos", "order")


@dataclass(frozen=True)
class CardDef:
    id: str
    name: str
    type: str                      # "unit" | "spell" | "champion"
    domains: tuple = ()
    energy: int = 0                # paid by exhausting any ready runes
    power: tuple = ()              # one domain per point, paid by recycling a rune of that domain
    might: int = 0
    keywords: dict = field(default_factory=dict)   # e.g. {"assault": 1, "shield": 1, "tank": true}
    effect: dict | None = None     # see engine.resolve_effect for supported shapes
    text: str = ""

    @property
    def is_unit(self) -> bool:
        return self.type in ("unit", "champion")


@dataclass(frozen=True)
class LegendDef:
    id: str
    name: str
    domains: tuple
    ability: dict | None = None
    text: str = ""


@dataclass(frozen=True)
class Deck:
    name: str
    legend: str
    champion: str
    main: tuple                    # 40 card ids
    runes: tuple                   # 12 domain names
    battlefields: tuple            # battlefield names (one is picked at random each game)


class Registry:
    def __init__(self):
        self.cards: dict[str, CardDef] = {}
        self.legends: dict[str, LegendDef] = {}

    def load_set(self, path: str | Path) -> "Registry":
        data = json.loads(Path(path).read_text())
        for c in data.get("cards", []):
            card = CardDef(
                id=c["id"], name=c["name"], type=c["type"],
                domains=tuple(c.get("domains", [])), energy=c.get("energy", 0),
                power=tuple(c.get("power", [])), might=c.get("might", 0),
                keywords=c.get("keywords", {}), effect=c.get("effect"), text=c.get("text", ""),
            )
            self.cards[card.id] = card
        for l in data.get("legends", []):
            self.legends[l["id"]] = LegendDef(l["id"], l["name"], tuple(l["domains"]), l.get("ability"), l.get("text", ""))
        return self

    def load_deck(self, path: str | Path) -> Deck:
        d = json.loads(Path(path).read_text())
        main = []
        for entry in d["main"]:
            main += [entry["id"]] * entry["count"]
        runes = []
        for dom, n in d["runes"].items():
            runes += [dom] * n
        deck = Deck(d["name"], d["legend"], d["champion"], tuple(main), tuple(runes), tuple(d["battlefields"]))
        self.validate_deck(deck)
        return deck

    def validate_deck(self, deck: Deck) -> None:
        errs = []
        legend = self.legends.get(deck.legend)
        if legend is None:
            errs.append(f"unknown legend {deck.legend}")
        for cid in set(deck.main) | {deck.champion}:
            if cid not in self.cards:
                errs.append(f"unknown card {cid}")
        if len(deck.main) != 40:
            errs.append(f"main deck has {len(deck.main)} cards, expected 40")
        if len(deck.runes) != 12:
            errs.append(f"rune deck has {len(deck.runes)} runes, expected 12")
        for cid in set(deck.main):
            if deck.main.count(cid) > 3:
                errs.append(f"{cid}: more than 3 copies")
        if legend and not errs:
            for cid in set(deck.main) | {deck.champion}:
                if not set(self.cards[cid].domains) <= set(legend.domains):
                    errs.append(f"{cid} is outside the legend's domains {legend.domains}")
            for r in deck.runes:
                if r not in legend.domains:
                    errs.append(f"rune {r} is outside the legend's domains")
        if errs:
            raise ValueError(f"Deck '{deck.name}' is illegal: " + "; ".join(errs))
