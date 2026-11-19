"""Choices are made when a chain item is finalized, not when it resolves (CR 355.3-355.5, 355.12, 355.14.b),
and targets that became illegal are unaffected when it resolves (CR 359.3.e).

Card scripts describe an effect as one instruction list in printed order ("Deal 2 to a unit, then move a friendly
unit"). `split_choices` moves the choices out of that list into the item's finalize code:
- top-level Choose over public zones (board, chain, trash) and ChooseLocation (move destinations, "choose a
  battlefield"), in printed order;
- the same inside a top-level May body ("You may move an enemy unit": the unit is chosen now, the may is decided
  on resolution, CR 355.12);
- SetVar("__tloc", ...) right after a hoisted choice is copied (both phases), so "there" / "at its location" work.
- a top-level ChooseMode: the mode is picked now (CR 355.3), with that mode's own leading choices; the bodies run
  at resolution through ModeDispatch.
Choices inside conditionals (If, ForEach) and choices among hidden cards (hand, deck) stay at resolution.

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
    if isinstance(ins.n, Ref) or (callable(ins.n) and not isinstance(ins.n, int) and not getattr(ins.n, "at_finalize", False)):
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
        if isinstance(ins, O.ChooseMode):
            # CR 355.3: the mode is chosen as the item is finalized, then that mode's choices (355.5)
            var = ins.out or f"__mode{len(hoisted)}_{id(ins)}"
            parts = [split_choices(list(body) if isinstance(body, list) else [body]) for _, body in ins.modes]
            hoisted.append(O.ChooseMode([(label, h) for (label, _), (h, _) in zip(ins.modes, parts)], out=var,
                                        player=ins.player, exclude_used=ins.exclude_used, legal_only=True))
            outs.add(var)
            rest.append(O.ModeDispatch(var, [r for _, r in parts]))
            prev_hoisted = True
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
                        if ctx.target_bf is not None else {},
                        "src_stamp": game.objects[ctx.source].entered_stamp
                        if ctx.target_bf is not None and ctx.source in game.objects else None}
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
                if rec["at_bf"].get(u) and game.hidden_source_gone(ctx, rec.get("src_stamp")):
                    continue       # its permanent left the board: it can't tell where it was played from (811.1.d.3.a)
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


def _remove_trigger(game, ctx):
    """CR 383.3.a.2 / 383.3.e.2.b: a declined (or unpaid) optional trigger leaves the chain as if it never triggered."""
    it = next((x for x in game.chain if x.id == ctx.item), None)
    if it is None:
        return
    game.chain.remove(it)
    ab = it.ability
    o = game.objects.get(it.uid)
    if ab is not None and getattr(ab, "once_per_turn", False) and o is not None:
        o.temp.pop(("opt", id(ab)), None)
    game.log("trigger_declined", item=it.id, label=it.label, controller=it.controller)
    game.bump()
    game.dirty = True


_END = 10 ** 9          # jump past the end of the finalize program


class TriggerBaseCost(Instr):
    """CR 383.3.b / 204.1.c: a cost within instructions at the start of a triggered ability's effect ("Recycle me to
    ready your runes", "exhaust me to draw 1", "banish a card from any trash to ...") is its base cost, paid as the
    trigger is finalized. Put this in the finalize code before the cost instructions; `ok(game, ctx)` says whether
    the cost can be paid. If it can't, the trigger leaves the chain (383.3.b.1)."""

    def __init__(self, ok):
        self.ok = ok

    def run(self, game, ctx):
        if not self.ok(game, ctx):
            _remove_trigger(game, ctx)
            return _END
        return None


class _TriggerMay(Instr):
    """"When ..., you may ...": whether to perform the triggered ability is decided as it is finalized (CR 383.3.a)."""

    def __init__(self, may, pre=(), costs=()):
        self.may = may
        self.out = may.out or "__may"
        self.pre, self.costs = list(pre), list(costs)

    def _offered(self, game, ctx):
        if any(not c(game, ctx) for c in self.pre):
            return False
        if any(isinstance(c, O.Exhaust) for c in self.costs):
            o = game.objects.get(ctx.source)
            if o is None or o.zone != "board" or o.exhausted:
                return False          # "exhaust me" can't be paid
        pays = [c for c in self.costs if isinstance(c, O.PayResources)]
        first = pays[0] if pays else next((b for b in self.may.body if not isinstance(b, O.Choose)), None)
        if isinstance(first, O.PayResources):
            from .vm import val
            e = val(game, ctx, first.energy)
            pw = [val(game, ctx, p) for p in first.power]
            vs = game.optional_cost_variants(ctx.controller, e, pw) if ctx.vars.get("__optional_cost") else [(e, pw)]
            return any(game.can_pay(ctx.controller, ve, vp, purpose={"kind": "effect", "uid": ctx.source}) for ve, vp in vs)
        if isinstance(first, O.Discard):
            from .vm import val
            return len(game.players[ctx.controller].hand) >= max(1, val(game, ctx, first.n) or 0)
        return True

    def run(self, game, ctx):
        from .vm import Decision
        if not self._offered(game, ctx):
            ctx.vars[self.out] = False
            _remove_trigger(game, ctx)
            return _END
        return Decision(ctx.controller, "yesno", [True, False], out=self.out,
                        labels=["yes: " + self.may.label, "no"])

    def resume(self, game, ctx, choice):
        if not choice:
            _remove_trigger(game, ctx)
            return _END
        return None


def _is_self(ref):
    return isinstance(ref, Ref) and ref.name == "self"


def _peel_costs(body):
    """Split a "you may" body into (leading choices, preconditions, costs, effect). Costs are what CR 383.3.b makes the
    trigger's base cost: "exhaust me", "pay [N]" (and "If you paid, ..." around the rest), behind the script's
    "if I'm ready" check (a precondition for saying yes)."""
    body = list(body)
    lead = []
    while body and isinstance(body[0], O.Choose):
        lead.append(body.pop(0))
    pre, costs = [], []
    while body:
        b = body[0]
        tail_ok = all(isinstance(x, O.SetVar) for x in body[1:])      # "... SetVar(__did)" after the If
        if isinstance(b, O.If) and not b.els and tail_ok and b.then and (
                (isinstance(b.then[0], O.Exhaust) and _is_self(b.then[0].targets)) or isinstance(b.then[0], O.PayResources)):
            if not ("has_var" in getattr(b.cond, "__qualname__", "") and costs):
                pre.append(b.cond)        # (an "if you paid, ..." around the rest needs nothing: payment is checked)
            body = list(b.then) + body[1:]
            continue
        if isinstance(b, O.Exhaust) and _is_self(b.targets):
            costs.append(body.pop(0))
            continue
        if isinstance(b, O.PayResources) and not b.optional and b.out:
            costs.append(body.pop(0))
            continue
        if isinstance(b, O.If) and not b.els and costs and "has_var" in getattr(b.cond, "__qualname__", "") and tail_ok:
            body = list(b.then) + body[1:]
            continue
        break
    return lead, pre, costs, body


class _TriggerCostsOk(Instr):
    """After paying: an unpaid "pay [N]" removes the trigger (CR 383.3.b.1)."""

    def __init__(self, outs):
        self.outs = outs

    def run(self, game, ctx):
        if any(ctx.vars.get(o) is None for o in self.outs):
            _remove_trigger(game, ctx)
            return _END
        return None


def split_trigger(tree):
    """split_choices for triggered abilities: a leading "you may" is decided as the trigger is finalized (CR 383.3.a),
    and a cost right after it ("you may pay [1] / exhaust me to ...") is paid then (383.3.b). Other effects:
    split_choices."""
    items = _items(tree)
    if not items or not isinstance(items[0], O.May) or items[0].player is not None:
        return split_choices(items)
    may = items[0]
    lead, pre, costs, eff = _peel_costs(may.body)
    hoisted, rest = split_choices(lead + eff + items[1:])
    fin_costs = []
    if costs:
        fin_costs = list(costs) + [_TriggerCostsOk([c.out for c in costs if isinstance(c, O.PayResources)])]
    return [_TriggerMay(may, pre, costs)] + hoisted + fin_costs, [O.SetVar(may.out or "__may", True)] + rest
