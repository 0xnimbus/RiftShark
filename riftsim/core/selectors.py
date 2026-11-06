"""Selectors describe sets of game objects / players / locations for effects and triggers."""
from __future__ import annotations

from .vm import val


class Sel:
    """Selects game objects on the board (or in a zone). All criteria are ANDed.

    kind: 'unit' | 'gear' | 'permanent' | 'rune' | 'legend' | 'battlefield' | 'card' (any main deck object)
    side: 'friendly' | 'enemy' | None (relative to ctx.controller)
    where: 'here' | 'battlefield' | 'base' | 'own_base' | 'loc:<ref>' | None (anywhere on board)
    zone: 'board' (default) | 'trash' | 'hand' | 'chain' | 'facedown' | 'champion' | 'banish'
    """

    def __init__(self, kind="unit", side=None, where=None, zone="board", tags=None, not_tags=None, keyword=None,
                 min_might=None, max_might=None, exhausted=None, ready=None, buffed=None, empowered=None, stunned=None,
                 name=None, not_self=False, other=False, pred=None, owner=None, supertype=None, types=None, attached=None,
                 damaged=None, mighty=None, token=None, label=None):
        self.kind, self.side, self.where, self.zone = kind, side, where, zone
        self.tags = tuple(tags) if isinstance(tags, (list, tuple)) else ((tags,) if tags else ())
        self.not_tags = tuple(not_tags or ())
        self.keyword, self.min_might, self.max_might = keyword, min_might, max_might
        self.exhausted, self.ready, self.buffed, self.empowered, self.stunned = exhausted, ready, buffed, empowered, stunned
        self.name, self.not_self, self.other, self.pred, self.owner = name, not_self or other, other, pred, owner
        self.supertype, self.types, self.attached, self.damaged, self.mighty, self.token = supertype, types, attached, damaged, mighty, token
        self.label = label

    def __repr__(self):
        parts = [self.kind]
        if self.side: parts.append(self.side)
        if self.where: parts.append(self.where)
        if self.zone != "board": parts.append("in " + self.zone)
        if self.tags: parts.append("tags=" + ",".join(self.tags))
        if self.min_might is not None: parts.append(f"might>={self.min_might}")
        if self.max_might is not None: parts.append(f"might<={self.max_might}")
        return "Sel(" + " ".join(parts) + ")"

    def matches(self, g, ctx, uid):
        o = g.objects[uid]
        ch = g.chars(uid)
        if self.zone == "board":
            if o.zone != "board":
                return False
        elif self.zone != "any" and o.zone != self.zone:
            return False
        k = self.kind
        if k == "unit" and "unit" not in ch.types: return False
        if k == "gear" and "gear" not in ch.types: return False
        if k == "permanent" and not ("unit" in ch.types or "gear" in ch.types): return False
        if k == "rune" and "rune" not in ch.types: return False
        if k == "legend" and "legend" not in ch.types: return False
        if k == "battlefield" and "battlefield" not in ch.types: return False
        if k == "spell" and "spell" not in ch.types: return False
        if k == "equipment" and "Equipment" not in ch.tags: return False
        if k == "card" and o.defn.is_token: return False
        if self.types and not any(t in ch.types for t in self.types): return False
        if self.supertype and ch.supertype != self.supertype: return False
        if self.side == "friendly" and not g.is_friendly(o.controller, ctx.controller): return False
        if self.side == "enemy" and g.is_friendly(o.controller, ctx.controller): return False
        if self.owner is not None and o.owner != val(g, ctx, self.owner): return False
        if self.where:
            w = self.where
            if w == "here":
                if ctx.here is None or o.location != ctx.here: return False
            elif w == "battlefield":
                if not o.location or o.location[0] != "bf": return False
            elif w == "base":
                if not o.location or o.location[0] != "base": return False
            elif w == "own_base":
                if o.location != ("base", o.controller): return False
            elif w.startswith("loc:"):
                if o.location != val(g, ctx, ctx.vars.get(w[4:])): return False
            elif w == "in_combat":
                if o.designation is None: return False
        if self.tags and not any(t in ch.tags for t in self.tags): return False
        if self.not_tags and any(t in ch.tags for t in self.not_tags): return False
        if self.keyword and not ch.keywords.get(self.keyword): return False
        if self.min_might is not None and (ch.might is None or ch.might < val(g, ctx, self.min_might)): return False
        if self.max_might is not None and (ch.might is None or ch.might > val(g, ctx, self.max_might)): return False
        if self.exhausted is not None and o.exhausted != self.exhausted: return False
        if self.ready is not None and o.exhausted == self.ready: return False
        if self.buffed is not None and bool(o.buffs) != self.buffed: return False
        if self.empowered is not None and bool(o.empowered) != self.empowered: return False
        if self.stunned is not None and o.stunned != self.stunned: return False
        if self.damaged is not None and bool(o.damage) != self.damaged: return False
        if self.mighty is not None and (ch.might is not None and ch.might >= 5) != self.mighty: return False
        if self.token is not None and o.defn.is_token != self.token: return False
        if self.attached is not None and bool(o.attached_to) != self.attached: return False
        if self.name and ch.name != self.name: return False
        if self.not_self and ctx.source is not None and uid == ctx.source: return False
        if self.pred and not self.pred(g, ctx, uid): return False
        return True

    def candidates(self, g, ctx):
        if self.zone == "board":
            pool = g.board_uids()
        elif self.zone == "any":
            pool = list(g.objects)
        else:
            pool = [u for u, o in g.objects.items() if o.zone == self.zone]
        return [u for u in pool if self.matches(g, ctx, u)]


UNIT = Sel("unit")
FRIENDLY_UNIT = Sel("unit", side="friendly")
ENEMY_UNIT = Sel("unit", side="enemy")
UNIT_AT_BF = Sel("unit", where="battlefield")
ENEMY_UNIT_HERE = Sel("unit", side="enemy", where="here")
FRIENDLY_UNIT_HERE = Sel("unit", side="friendly", where="here")
GEAR = Sel("gear")
