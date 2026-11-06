"""Game state. Kept as plain slotted objects with a hand-written clone() so search is fast."""
from __future__ import annotations

import random


class Unit:
    __slots__ = ("uid", "card_id", "owner", "exhausted", "damage", "temp_might")

    def __init__(self, uid, card_id, owner, exhausted=True):
        self.uid, self.card_id, self.owner = uid, card_id, owner
        self.exhausted, self.damage, self.temp_might = exhausted, 0, 0

    def clone(self):
        u = Unit.__new__(Unit)
        u.uid, u.card_id, u.owner = self.uid, self.card_id, self.owner
        u.exhausted, u.damage, u.temp_might = self.exhausted, self.damage, self.temp_might
        return u

    def to_dict(self):
        return {"uid": self.uid, "card": self.card_id, "exhausted": self.exhausted,
                "damage": self.damage, "temp_might": self.temp_might}


class Rune:
    __slots__ = ("domain", "exhausted")

    def __init__(self, domain, exhausted=False):
        self.domain, self.exhausted = domain, exhausted

    def clone(self):
        return Rune(self.domain, self.exhausted)


class PlayerState:
    __slots__ = ("idx", "deck_name", "legend", "champion", "hand", "deck", "trash",
                 "rune_deck", "runes", "base", "points", "scored", "legend_used")

    def __init__(self, idx):
        self.idx = idx
        self.deck_name = ""
        self.legend = ""
        self.champion = None        # (uid, card_id) while in the champion zone, else None
        self.hand = []              # list of (uid, card_id)
        self.deck = []              # card ids, index 0 = top
        self.trash = []             # card ids
        self.rune_deck = []         # domains, index 0 = top
        self.runes = []             # Rune objects in play
        self.base = []              # Units at base
        self.points = 0
        self.scored = set()         # battlefield indices scored this turn
        self.legend_used = False    # once-per-turn legend abilities

    def clone(self):
        p = PlayerState.__new__(PlayerState)
        p.idx, p.deck_name, p.legend, p.champion = self.idx, self.deck_name, self.legend, self.champion
        p.hand, p.deck, p.trash = list(self.hand), list(self.deck), list(self.trash)
        p.rune_deck = list(self.rune_deck)
        p.runes = [r.clone() for r in self.runes]
        p.base = [u.clone() for u in self.base]
        p.points, p.scored, p.legend_used = self.points, set(self.scored), self.legend_used
        return p


class Battlefield:
    __slots__ = ("name", "owner", "controller", "units")

    def __init__(self, name, owner):
        self.name, self.owner, self.controller = name, owner, None
        self.units = ([], [])       # units per player

    def clone(self):
        b = Battlefield.__new__(Battlefield)
        b.name, b.owner, b.controller = self.name, self.owner, self.controller
        b.units = ([u.clone() for u in self.units[0]], [u.clone() for u in self.units[1]])
        return b


class GameState:
    __slots__ = ("reg", "config", "players", "battlefields", "active", "first", "turn",
                 "winner", "done", "rng", "next_uid", "log", "actions_this_turn")

    def clone(self, keep_log=False):
        s = GameState.__new__(GameState)
        s.reg, s.config = self.reg, self.config
        s.players = [p.clone() for p in self.players]
        s.battlefields = [b.clone() for b in self.battlefields]
        s.active, s.first, s.turn = self.active, self.first, self.turn
        s.winner, s.done, s.next_uid = self.winner, self.done, self.next_uid
        s.rng = random.Random()
        s.rng.setstate(self.rng.getstate())
        s.log = self.log if keep_log else None
        s.actions_this_turn = self.actions_this_turn
        return s

    # --- helpers -------------------------------------------------------
    def card(self, cid):
        return self.reg.cards[cid]

    def all_units(self):
        """Yield (unit, location) for every unit; location -1 = base, else battlefield index."""
        for p in self.players:
            for u in p.base:
                yield u, -1
        for i, bf in enumerate(self.battlefields):
            for side in bf.units:
                for u in side:
                    yield u, i

    def find_unit(self, uid):
        for u, loc in self.all_units():
            if u.uid == uid:
                return u, loc
        return None, None

    def snapshot(self):
        """JSON-friendly view of the full state, used by replays."""
        def player(p):
            return {
                "deck": p.deck_name, "legend": p.legend, "points": p.points,
                "hand": [c for _, c in p.hand], "deck_size": len(p.deck), "trash": list(p.trash),
                "champion_zone": p.champion[1] if p.champion else None,
                "runes": [{"domain": r.domain, "exhausted": r.exhausted} for r in p.runes],
                "rune_deck_size": len(p.rune_deck),
                "base": [u.to_dict() for u in p.base],
            }
        return {
            "turn": self.turn, "active": self.active, "winner": self.winner,
            "players": [player(p) for p in self.players],
            "battlefields": [{"name": b.name, "controller": b.controller,
                              "units": [[u.to_dict() for u in side] for side in b.units]}
                             for b in self.battlefields],
        }
