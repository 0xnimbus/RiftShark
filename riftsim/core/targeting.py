"""Choices are made when a chain item is finalized, not when it resolves (CR 355.3-355.5, 355.12, 355.14.b),
and targets that became illegal are unaffected when it resolves (CR 359.3.e).

Card scripts describe an effect as one instruction list in printed order ("Deal 2 to a unit, then move a friendly
unit"). `split_choices` moves the choices out of that list into the item's finalize code:
- top-level Choose over public zones (board, chain, trash) and ChooseLocation (move destinations, "choose a
  battlefield"), in printed order;
- the same inside a top-level May body ("You may move an enemy unit": the unit is chosen now, the may is decided
  on resolution, CR 355.12);
- SetVar("__tloc", ...) right after a hoisted choice is copied (both phases), so "there" / "at its location" work.
Choices inside conditionals (If, ForEach, modes) and choices among hidden cards (hand, deck) stay at resolution.

Each hoisted Choose is followed by `_Stamp`, which records the chosen objects' zone-entry stamps and, for targeted
choices, registers the variable in ctx.vars["__targets"] (Deflect costs, "when chosen" triggers). The resolution code
starts with `_Recheck`, which drops chosen objects that changed zones or no longer match the selector."""
from __future__ import annotations

from .vm import Instr, Ref
from . import ops as O
from .selectors import Sel

PUBLIC_ZONES = ("board", "chain", "trash", "any")


def _items(tree):
    if tree is None:
        return []
    if isinstance(tree, Instr):
        return [tree]
    return list(tree)


def _hoistable_choose(ins, outs):
    if not isinstance(ins, O.Choose) or not isinstance(ins.sel, Sel):
        return False
    if getattr(ins, "at_resolution", False):
        return False            # chosen as the spell resolves (CR 355.10.e-g)
    if ins.sel.zone not in PUBLIC_ZONES:
        return False
    w = ins.sel.where or ""
    if w.startswith("loc:") and w[4:] not in outs:
        return False
    if isinstance(ins.n, Ref) or (callable(ins.n) and not isinstance(ins.n, int)):
        return False            # "for each ..." counts depend on the state at resolution
    return True


def split_choices(tree):
    """Return (finalize_code, resolution_code) as instruction lists."""
    items = _items(tree)
    hoisted, rest, outs, checks = [], [], set(), []
    prev_hoisted = False
    for ins in items:
        if _hoistable_choose(ins, outs):
            hoisted += [ins, _Stamp(ins.out, ins.sel, ins.targeted)]
            outs.add(ins.out)
            checks.append(ins.out)
            prev_hoisted = True
            continue
        if isinstance(ins, O.ChooseLocation):
            hoisted.append(ins)
            outs.add(ins.out)
            prev_hoisted = True
            continue
        if isinstance(ins, O.SetVar) and ins.name == "__tloc" and prev_hoisted:
            hoisted.append(ins)
            outs.add(ins.name)
            rest.append(ins)
            continue
        if isinstance(ins, O.May):
            body_h, body_r = [], []
            for b in ins.body:
                if _hoistable_choose(b, outs):
                    body_h += [b, _Stamp(b.out, b.sel, b.targeted)]
                    outs.add(b.out)
                    checks.append(b.out)
                elif isinstance(b, O.ChooseLocation) and not body_r:
                    body_h.append(b)
                    outs.add(b.out)
                else:
                    body_r.append(b)
            if body_h:
                hoisted += body_h
                rest.append(O.May(body_r, label=ins.label, player=ins.player, out=ins.out))
                prev_hoisted = True
                continue
        rest.append(ins)
        prev_hoisted = False
    if not hoisted:
        return [], items
    groups = [_GroupRecheck(h.out) for h in hoisted if isinstance(h, O.Choose) and getattr(h, "same_loc", False)]
    return hoisted, ([_Recheck(checks)] if checks else []) + groups + rest


class _Stamp(Instr):
    def __init__(self, out, sel, targeted):
        self.out, self.sel, self.targeted = out, sel, targeted

    def run(self, game, ctx):
        v = ctx.vars.get(self.out)
        uids = v if isinstance(v, tuple) else (() if v is None else (v,))
        st = ctx.vars.setdefault("__chosen", {})
        st[self.out] = {"sel": self.sel, "targeted": self.targeted,
                        "stamps": {u: game.objects[u].entered_stamp for u in uids if u in game.objects},
                        "at_bf": {u: game.objects[u].location == ctx.target_bf for u in uids if u in game.objects}
                        if ctx.target_bf is not None else {}}
        if self.targeted:
            tl = ctx.vars.setdefault("__targets", [])
            if all(n != self.out for n, _ in tl):
                tl.append((self.out, self.sel))
        return None


class _Recheck(Instr):
    """CR 359.3.e: a chosen object that changed zones, or no longer meets the choice's requirements, is unaffected."""

    def __init__(self, outs):
        self.outs = outs

    def run(self, game, ctx):
        info = ctx.vars.get("__chosen", {})
        for name in self.outs:
            rec = info.get(name)
            v = ctx.vars.get(name)
            if rec is None or v is None:
                continue
            many = isinstance(v, tuple)
            keep = []
            for u in (v if many else (v,)):
                o = game.objects.get(u)
                if o is None or o.entered_stamp != rec["stamps"].get(u):
                    continue
                if not rec["sel"].matches(game, ctx, u):
                    continue
                if rec["at_bf"].get(u) and o.location != ctx.target_bf:
                    continue       # Hidden: chosen at the battlefield it was played from (CR 359.3.e.2.a)
                if rec["targeted"] and o.zone == "board" and not game.is_friendly(o.controller, ctx.controller) \
                        and game.chars(u).keywords.get("untargetable"):
                    continue
                keep.append(u)
            ctx.vars[name] = tuple(keep) if many else (keep[0] if keep else None)
        return None


class _GroupRecheck(Instr):
    """CR 355.11.b: if a same-location group of targets no longer shares a location, the controller chooses a legal
    subset with the most targets possible."""

    def __init__(self, out):
        self.out = out

    def run(self, game, ctx):
        v = ctx.vars.get(self.out)
        if not isinstance(v, tuple) or len({game.objects[u].location for u in v}) <= 1:
            return None
        groups = {}
        for u in v:
            groups.setdefault(game.objects[u].location, []).append(u)
        opts = [tuple(g) for g in groups.values()]      # each group is a maximal legal subset (Bellows Breath example)
        if len(opts) == 1:
            ctx.vars[self.out] = opts[0]
            return None
        from .vm import Decision
        return Decision(ctx.controller, "choose_many", opts, out=self.out,
                        labels=[", ".join(game.label(u) for u in o) for o in opts],
                        info={"label": "targets that still share a location"})
