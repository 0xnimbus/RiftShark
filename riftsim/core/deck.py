"""Deck definitions and construction rules (CR 110-130, 1v1)."""
from __future__ import annotations

import json
from pathlib import Path

from .cards import DOMAINS


class DeckError(Exception):
    pass


class Deck:
    def __init__(self, name, legend, champion, main, runes, battlefields, extra_legends=()):
        self.name, self.legend, self.champion = name, legend, champion
        self.main = list(main)
        self.runes = list(runes)
        self.battlefields = list(battlefields)
        self.extra_legends = list(extra_legends)    # additional deckbuilding choice (Neeko, Blending In)

    @classmethod
    def from_dict(cls, d, db=None):
        main = []
        for e in d["main"]:
            if isinstance(e, str):
                main.append(e)
            else:
                main += [e["id"] if "id" in e else e["name"]] * e.get("count", 1)
        runes = []
        r = d.get("runes", {})
        if isinstance(r, dict):
            for dom, n in r.items():
                runes += [dom.lower()] * n
        else:
            runes = [x.lower() for x in r]
        return cls(d["name"], d["legend"], d["champion"], main, runes, d["battlefields"], d.get("extra_legends", ()))

    @classmethod
    def load(cls, path, db=None):
        return cls.from_dict(json.loads(Path(path).read_text()), db)

    def to_dict(self):
        counts = {}
        for c in self.main:
            counts[c] = counts.get(c, 0) + 1
        rc = {}
        for r in self.runes:
            rc[r] = rc.get(r, 0) + 1
        return {"name": self.name, "legend": self.legend, "champion": self.champion,
                "main": [{"id": k, "count": v} for k, v in counts.items()], "runes": rc, "battlefields": self.battlefields,
                **({"extra_legends": self.extra_legends} if self.extra_legends else {})}

    def validate(self, db, raise_on_error=False, strict=True):
        errs = []
        try:
            leg = db.card(self.legend)
            if leg.type != "legend":
                errs.append(f"{self.legend} is not a legend")
        except KeyError:
            errs.append(f"unknown legend {self.legend}")
            leg = None
        try:
            ch = db.card(self.champion)
            if not ch.is_champion or not ch.is_unit:
                errs.append(f"{self.champion} is not a champion unit")
            elif leg is not None and ch.tags and leg.tags and not (set(ch.tags) & set(leg.tags)):
                errs.append(f"champion {ch.name} does not match legend {leg.name} tags")
        except KeyError:
            errs.append(f"unknown champion {self.champion}")
            ch = None
        # CR 103.3: the 40-card Main Deck includes the Chosen Champion, which starts in the Champion Zone,
        # so `main` lists the other 39 cards.
        if len(self.main) < 39:
            errs.append(f"main deck has {len(self.main) + 1} cards including the champion, needs at least 40")
        counts = {}
        for c in self.main:
            try:
                cd = db.card(c)
            except KeyError:
                errs.append(f"unknown card {c}")
                continue
            if cd.type not in ("unit", "spell", "gear"):
                errs.append(f"{cd.name} cannot be in the main deck")
            counts[cd.name] = counts.get(cd.name, 0) + 1
            if leg is not None and cd.domains and not set(cd.domains) <= set(leg.domains):
                errs.append(f"{cd.name} is outside the legend's domains {leg.domains}")
        if ch is not None:
            counts[ch.name] = counts.get(ch.name, 0) + 1     # the Chosen Champion counts toward its name's limit
        for n, k in counts.items():
            cd = db.card(n)
            limit = 1 if cd.keywords.get("unique") else 3
            if "your deck can have any number of cards named" in (cd.text or "").lower():
                limit = 10 ** 6                          # Spiderling
            if k > limit:
                errs.append(f"{n}: {k} copies (max {limit})")
        # Neeko, Blending In (errata): choose up to 3 different legends in addition to your starting legend
        if self.extra_legends:
            names = []
            for x in self.extra_legends:
                try:
                    lx = db.card(x)
                except KeyError:
                    errs.append(f"unknown extra legend {x}")
                    continue
                if lx.type != "legend":
                    errs.append(f"extra legend {x} is not a legend")
                names.append(lx.name)
            if len(names) > 3:
                errs.append("more than 3 extra legends")
            if len(set(names)) != len(names) or (leg is not None and leg.name in names):
                errs.append("extra legends must have different names from each other and the starting legend")
            if "Neeko, Blending In" not in counts:
                errs.append("extra legends are only chosen when Neeko, Blending In is in the deck")
        if len(self.runes) != 12:
            errs.append(f"rune deck has {len(self.runes)} runes, expected 12")
        for r in self.runes:
            if r not in DOMAINS:
                errs.append(f"bad rune domain {r}")
            elif leg is not None and r not in leg.domains:
                errs.append(f"{r} rune is outside the legend's domains")
        if len(self.battlefields) != 3:
            errs.append(f"{len(self.battlefields)} battlefields, expected 3")
        for b in self.battlefields:
            try:
                if db.card(b).type != "battlefield":
                    errs.append(f"{b} is not a battlefield")
            except KeyError:
                errs.append(f"unknown battlefield {b}")
        # No silent simplifications: once card scripts are attached, every card in the deck must be fully scripted
        # ('auto', 'manual' or 'vanilla'); a card the engine would only partly run makes the deck illegal here.
        if getattr(db, "scripted", False):
            for c in [self.legend, self.champion] + list(self.main) + list(self.battlefields):
                try:
                    cd = db.card(c)
                except KeyError:
                    continue
                st = getattr(cd, "script_status", "none")
                if st not in ("auto", "manual", "vanilla"):
                    errs.append(f"{cd.name} is not fully scripted ({st}); the engine would simplify it")
        if errs and raise_on_error and strict:
            raise DeckError("; ".join(errs))
        return errs
