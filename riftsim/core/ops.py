"""Instruction set for card effects. Nested instructions (If, ForEach, May ...) compile to flat code.

Conventions
- `amount` / `n` values may be ints, Ref("var") or callables (game, ctx) -> int.
- `targets` may be a Ref to a chosen uid / list of uids, a Sel (all matching objects), or a list.
- Most instructions that affect objects accept both a single uid and a list.
"""
from __future__ import annotations

import itertools

from .selectors import Sel
from .vm import Decision, Instr, Jump, JumpIf, Label, Ref, compile_effect, new_label, val


def _uids(game, ctx, t):
    v = val(game, ctx, t)
    if isinstance(v, Sel):
        return v.candidates(game, ctx)
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return [u for u in v if u is not None and u in game.objects]
    return [v] if v in game.objects else []


def _player(game, ctx, p):
    v = val(game, ctx, p)
    if v is None:
        return ctx.controller
    if v == "opponent":
        return game.opponent(ctx.controller)
    return v


# ------------------------------------------------------------------ control flow
class If(Instr):
    def __init__(self, cond, then, els=None):
        self.cond, self.then, self.els = cond, then if isinstance(then, list) else [then], (els if isinstance(els, list) else [els]) if els else []

    def compile(self, out, counter):
        l_else, l_end = new_label(counter, "else"), new_label(counter, "endif")
        out.append(JumpIf(self.cond, l_else, negate=True))
        for i in self.then:
            i.compile(out, counter)
        out.append(Jump(l_end))
        out.append(Label(l_else))
        for i in self.els:
            i.compile(out, counter)
        out.append(Label(l_end))


class Block(Instr):
    def __init__(self, body):
        self.body = body

    def compile(self, out, counter):
        for i in self.body:
            i.compile(out, counter)


class _LoopInit(Instr):
    def __init__(self, var, items):
        self.var, self.items = var, items

    def run(self, game, ctx):
        ctx.vars["__loop_" + self.var] = list(_uids(game, ctx, self.items)) if not isinstance(val(game, ctx, self.items), int) else list(range(val(game, ctx, self.items)))
        ctx.vars["__i_" + self.var] = 0
        return None


class _LoopNext(Instr):
    """Jump to end when exhausted, else set var and continue."""

    def __init__(self, var, l_end):
        self.var, self.target = var, l_end

    def run(self, game, ctx):
        items, i = ctx.vars["__loop_" + self.var], ctx.vars["__i_" + self.var]
        if i >= len(items):
            return self.target
        ctx.vars[self.var] = items[i]
        ctx.vars["__i_" + self.var] = i + 1
        return None


class ForEach(Instr):
    """ForEach('u', Sel(...) or Ref or int, body). The uid list is fixed when the loop starts."""

    def __init__(self, var, items, body):
        self.var, self.items, self.body = var, items, body if isinstance(body, list) else [body]

    def compile(self, out, counter):
        l_top, l_end = new_label(counter, "loop"), new_label(counter, "endloop")
        out.append(_LoopInit(self.var, self.items))
        out.append(Label(l_top))
        out.append(_LoopNext(self.var, l_end))
        for i in self.body:
            i.compile(out, counter)
        out.append(Jump(l_top))
        out.append(Label(l_end))


class Times(Instr):
    """Repeat body N times (N evaluated once)."""

    def __init__(self, n, body):
        self.n, self.body = n, body if isinstance(body, list) else [body]

    def compile(self, out, counter):
        var = new_label(counter, "__times")
        ForEach(var, self.n, self.body).compile(out, counter)


class RepeatBody(Instr):
    """Execute body once plus once per Repeat cost paid (ctx.repeat)."""

    def __init__(self, body):
        self.body = body if isinstance(body, list) else [body]

    def compile(self, out, counter):
        Times(lambda g, c: 1 + c.repeat, self.body).compile(out, counter)


class SetVar(Instr):
    def __init__(self, name, value):
        self.name, self.value = name, value

    def run(self, game, ctx):
        ctx.vars[self.name] = val(game, ctx, self.value)
        return None


class Do(Instr):
    """Run an arbitrary python function f(game, ctx). Escape hatch for odd cards (must be deterministic
    and must not need decisions)."""

    def __init__(self, fn, label=""):
        self.fn, self.label = fn, label

    def run(self, game, ctx):
        self.fn(game, ctx)
        return None


# ------------------------------------------------------------------ decisions
class AskYesNo(Instr):
    """'You may ...' decided on resolution. Stores bool in ctx.vars[out]."""

    def __init__(self, out="may", label="You may", player=None):
        self.out, self.label, self.player = out, label, player

    def run(self, game, ctx):
        return Decision(_player(game, ctx, self.player), "yesno", [True, False], out=self.out, labels=["yes: " + self.label, "no"])


class May(Instr):
    """May(body, label): ask yes/no, run body if yes."""

    def __init__(self, body, label="you may", player=None, out=None):
        self.body, self.label, self.player = body if isinstance(body, list) else [body], label, player
        self.out = out

    def compile(self, out, counter):
        var = self.out or new_label(counter, "__may")
        out.append(AskYesNo(var, self.label, self.player))
        If(Ref(var), self.body).compile(out, counter)


class Choose(Instr):
    """Choose n objects matching `sel` (or from an explicit list). Result stored in ctx.vars[out]:
    a single uid when n == 1, else a tuple. `up_to` allows fewer (including 0).
    When a chosen object is required but none exists, stores None (instruction using it is ignored).
    `targeted` marks the choice as targeting (Deflect costs, 'when you choose me' triggers, hidden restrictions)."""

    def __init__(self, sel, out="t", n=1, up_to=False, player=None, targeted=True, label=None, distinct=True, allow_none=False):
        self.sel, self.out, self.n, self.up_to, self.player = sel, out, n, up_to, player
        self.targeted, self.label, self.distinct, self.allow_none = targeted, label, distinct, allow_none

    def run(self, game, ctx):
        p = _player(game, ctx, self.player)
        cands = game.choice_candidates(ctx, self.sel, targeted=self.targeted)
        n = val(game, ctx, self.n)
        if n == 1 and not self.up_to:
            if not cands:
                ctx.vars[self.out] = None
                return None
            if len(cands) == 1 and not self.allow_none:
                ctx.vars[self.out] = cands[0]
                return None
            opts = list(cands) + ([None] if self.allow_none else [])
            return Decision(p, "choose", opts, out=self.out,
                            labels=[game.label(u) for u in cands] + (["none"] if self.allow_none else []),
                            info={"sel": repr(self.sel), "label": self.label or ""})
        # multi choice
        maxn = min(n, len(cands))
        opts = []
        lo = 0 if self.up_to else maxn
        for k in range(lo, maxn + 1):
            opts += [tuple(c) for c in itertools.combinations(cands, k)]
        if len(opts) == 1:
            ctx.vars[self.out] = opts[0]
            return None
        return Decision(p, "choose_many", opts, out=self.out,
                        labels=[", ".join(game.label(u) for u in o) or "none" for o in opts],
                        info={"sel": repr(self.sel), "label": self.label or ""})


class ChooseLocation(Instr):
    """Choose a battlefield (or base). Stores location tuple in ctx.vars[out]."""

    def __init__(self, out="loc", kinds=("bf",), pred=None, player=None, label="Choose a battlefield", include_bases=False):
        self.out, self.kinds, self.pred, self.player, self.label, self.include_bases = out, kinds, pred, player, label, include_bases

    def run(self, game, ctx):
        p = _player(game, ctx, self.player)
        locs = [("bf", i) for i in range(len(game.battlefields))]
        if self.include_bases:
            locs += [("base", q) for q in range(len(game.players))]
        if self.pred:
            locs = [l for l in locs if self.pred(game, ctx, l)]
        if not locs:
            ctx.vars[self.out] = None
            return None
        if len(locs) == 1:
            ctx.vars[self.out] = locs[0]
            return None
        return Decision(p, "choose_location", locs, out=self.out, labels=[game.loc_name(l) for l in locs], info={"label": self.label})


class ChooseMode(Instr):
    """Choose one of several labelled bodies. Modes: list of (label, body)."""

    def __init__(self, modes, out=None, player=None, exclude_used=False):
        self.modes, self.out, self.player, self.exclude_used = modes, out, player, exclude_used

    def compile(self, out, counter):
        var = self.out or new_label(counter, "__mode")
        out.append(_ModeAsk(self.modes, var, self.player, self.exclude_used))
        l_end = new_label(counter, "endmode")
        for idx, (label, body) in enumerate(self.modes):
            l_next = new_label(counter, "mode")
            out.append(JumpIf(lambda g, c, idx=idx, var=var: c.vars.get(var) == idx, l_next, negate=True))
            for i in (body if isinstance(body, list) else [body]):
                i.compile(out, counter)
            out.append(Jump(l_end))
            out.append(Label(l_next))
        out.append(Label(l_end))


class _ModeAsk(Instr):
    def __init__(self, modes, out, player, exclude_used):
        self.modes, self.out, self.player, self.exclude_used = modes, out, player, exclude_used

    def run(self, game, ctx):
        p = _player(game, ctx, self.player)
        idxs = list(range(len(self.modes)))
        if self.exclude_used:
            used = game.turn_memo.setdefault(("modes", ctx.source), set())
            idxs = [i for i in idxs if i not in used]
            if not idxs:
                ctx.vars[self.out] = -1
                return None
        return Decision(p, "mode", idxs, out=self.out, labels=[self.modes[i][0] for i in idxs])

    def resume(self, game, ctx, choice):
        if self.exclude_used:
            game.turn_memo.setdefault(("modes", ctx.source), set()).add(choice)
        return None


class ChoosePlayer(Instr):
    def __init__(self, out="p", opponent=True):
        self.out, self.opponent = out, opponent

    def run(self, game, ctx):
        ps = [q for q in range(len(game.players)) if not (self.opponent and q == ctx.controller)]
        if len(ps) == 1:
            ctx.vars[self.out] = ps[0]
            return None
        return Decision(ctx.controller, "choose_player", ps, out=self.out, labels=[f"P{q}" for q in ps])


class ChooseFromList(Instr):
    """Generic choice among explicit options (e.g. cards looked at). `options` -> list."""

    def __init__(self, options, out, n=1, up_to=False, player=None, labels=None, label=""):
        self.options, self.out, self.n, self.up_to, self.player, self.labels, self.label = options, out, n, up_to, player, labels, label

    def run(self, game, ctx):
        p = _player(game, ctx, self.player)
        opts = list(val(game, ctx, self.options) or [])
        n = val(game, ctx, self.n)
        if n == 1 and not self.up_to:
            if not opts:
                ctx.vars[self.out] = None; return None
            if len(opts) == 1:
                ctx.vars[self.out] = opts[0]; return None
            return Decision(p, "pick", opts, out=self.out, labels=[game.label(o) for o in opts], info={"label": self.label})
        maxn = min(n, len(opts))
        combos = []
        for k in range(0 if self.up_to else maxn, maxn + 1):
            combos += [tuple(c) for c in itertools.combinations(opts, k)]
        if len(combos) <= 1:
            ctx.vars[self.out] = combos[0] if combos else ()
            return None
        return Decision(p, "pick_many", combos, out=self.out, labels=[", ".join(game.label(u) for u in o) or "none" for o in combos], info={"label": self.label})


# ------------------------------------------------------------------ game actions
class Draw(Instr):
    def __init__(self, n=1, player=None):
        self.n, self.player = n, player

    def run(self, game, ctx):
        game.do_draw(_player(game, ctx, self.player), val(game, ctx, self.n), ctx)
        return None


class Deal(Instr):
    """Deal `amount` damage to each target (a single Deal action per target set)."""

    def __init__(self, amount, targets, source=None, each=True):
        self.amount, self.targets, self.source, self.each = amount, targets, source, each

    def run(self, game, ctx):
        us = _uids(game, ctx, self.targets)
        amt = val(game, ctx, self.amount)
        if not us or amt is None:
            return None
        src = val(game, ctx, self.source) if self.source is not None else None
        game.do_deal(us, amt, ctx, source_uid=src)
        return None


class Split(Instr):
    """Deal `amount` damage split among chosen targets (targets chosen earlier into Ref). Splits
    as evenly-lethal as the controller decides; the AI uses a greedy lethal-first split."""

    def __init__(self, amount, targets):
        self.amount, self.targets = amount, targets

    def run(self, game, ctx):
        us = _uids(game, ctx, self.targets)
        amt = val(game, ctx, self.amount)
        if not us or not amt:
            return None
        game.do_deal_split(us, amt, ctx)
        return None


class Kill(Instr):
    def __init__(self, targets):
        self.targets = targets

    def run(self, game, ctx):
        us = _uids(game, ctx, self.targets)
        if us:
            game.do_kill(us, ctx)
        return None


class Buff(Instr):
    def __init__(self, targets):
        self.targets = targets

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.do_buff(u, ctx)
        return None


class SpendBuff(Instr):
    """Spend a buff from target(s); stores whether a buff was spent in ctx.vars[out]."""

    def __init__(self, targets, out="spent"):
        self.targets, self.out = targets, out

    def run(self, game, ctx):
        ok = False
        for u in _uids(game, ctx, self.targets):
            if game.do_spend_buff(u, ctx):
                ok = True
        ctx.vars[self.out] = ok
        return None


class Stun(Instr):
    def __init__(self, targets):
        self.targets = targets

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.do_stun(u, ctx)
        return None


class Ready(Instr):
    def __init__(self, targets):
        self.targets = targets

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.do_ready(u, ctx)
        return None


class Exhaust(Instr):
    def __init__(self, targets):
        self.targets = targets

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.do_exhaust(u, ctx)
        return None


class Heal(Instr):
    def __init__(self, targets):
        self.targets = targets

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.do_heal(u, ctx)
        return None


class Banish(Instr):
    def __init__(self, targets):
        self.targets = targets

    def run(self, game, ctx):
        us = _uids(game, ctx, self.targets)
        if us:
            game.do_banish(us, ctx)
        return None


class Discard(Instr):
    """Discard n cards chosen by the player (asks when there is a choice)."""

    def __init__(self, n=1, player=None, out="discarded"):
        self.n, self.player, self.out = n, player, out

    def run(self, game, ctx):
        p = _player(game, ctx, self.player)
        n = val(game, ctx, self.n)
        hand = game.players[p].hand
        if n >= len(hand):
            ctx.vars[self.out] = tuple(hand)
            game.do_discard(p, list(hand), ctx)
            return None
        opts = [tuple(c) for c in itertools.combinations(hand, n)]
        if len(opts) == 1:
            return self.resume(game, ctx, opts[0])
        return Decision(p, "discard", opts, out=self.out, labels=[", ".join(game.label(u) for u in o) for o in opts])

    def resume(self, game, ctx, choice):
        game.do_discard(_player(game, ctx, self.player), list(choice), ctx)
        return None


class DiscardChosen(Instr):
    def __init__(self, targets, player=None):
        self.targets, self.player = targets, player

    def run(self, game, ctx):
        us = _uids(game, ctx, self.targets)
        if us:
            game.do_discard(game.objects[us[0]].owner, us, ctx)
        return None


class Recycle(Instr):
    """Recycle chosen objects (Ref/list) or `n` cards from a zone chosen by the player."""

    def __init__(self, targets=None, n=None, zone="trash", player=None, out="recycled"):
        self.targets, self.n, self.zone, self.player, self.out = targets, n, zone, player, out

    def run(self, game, ctx):
        if self.targets is not None:
            us = _uids(game, ctx, self.targets)
            if us:
                game.do_recycle(us, ctx)
            return None
        p = _player(game, ctx, self.player)
        n = val(game, ctx, self.n)
        pool = [u for u, o in game.objects.items() if o.zone == self.zone and o.owner == p and not o.defn.is_token]
        if len(pool) <= n:
            game.do_recycle(pool, ctx)
            return None
        opts = [tuple(c) for c in itertools.combinations(pool, n)]
        if len(opts) > 60:   # keep branching sane: recycle the "least useful" automatically
            opts = opts[:60]
        return Decision(p, "recycle", opts, out=self.out, labels=[", ".join(game.label(u) for u in o) for o in opts])

    def resume(self, game, ctx, choice):
        game.do_recycle(list(choice), ctx)
        return None


class Burn(Instr):
    def __init__(self, n=1, player=None):
        self.n, self.player = n, player

    def run(self, game, ctx):
        game.do_burn(_player(game, ctx, self.player), val(game, ctx, self.n), ctx)
        return None


class Channel(Instr):
    def __init__(self, n=1, exhausted=False, player=None, out="channeled"):
        self.n, self.exhausted, self.player, self.out = n, exhausted, player, out

    def run(self, game, ctx):
        ctx.vars[self.out] = game.do_channel(_player(game, ctx, self.player), val(game, ctx, self.n), val(game, ctx, self.exhausted), ctx)
        return None


class Empower(Instr):
    def __init__(self, targets):
        self.targets = targets

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.do_empower(u, ctx)
        return None


class Disempower(Instr):
    def __init__(self, targets):
        self.targets = targets

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.do_disempower(u, ctx)
        return None


class Move(Instr):
    """Move units to `dest` (a location tuple, Ref, or 'base' meaning each unit's controller's base)."""

    def __init__(self, targets, dest, ready=False):
        self.targets, self.dest, self.ready = targets, dest, ready

    def run(self, game, ctx):
        us = _uids(game, ctx, self.targets)
        if not us:
            return None
        d = val(game, ctx, self.dest)
        if d is None:
            return None
        if d == "base":                      # each unit goes to its controller's base
            for u in us:
                game.do_move([u], ("base", game.objects[u].controller), ctx)
        else:
            game.do_move(us, d, ctx)
        if self.ready:
            for u in us:
                game.do_ready(u, ctx)
        return None


class Recall(Instr):
    def __init__(self, targets, exhausted=False):
        self.targets, self.exhausted = targets, exhausted

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.do_recall(u, ctx)
            if self.exhausted:
                game.do_exhaust(u, ctx)
        return None


class GainPoints(Instr):
    def __init__(self, n=1, player=None):
        self.n, self.player = n, player

    def run(self, game, ctx):
        game.gain_points(_player(game, ctx, self.player), val(game, ctx, self.n), "effect", ctx)
        return None


class LosePoints(Instr):
    def __init__(self, n=1, player=None):
        self.n, self.player = n, player

    def run(self, game, ctx):
        game.lose_points(_player(game, ctx, self.player), val(game, ctx, self.n), ctx)
        return None


class GainXP(Instr):
    def __init__(self, n=1, player=None):
        self.n, self.player = n, player

    def run(self, game, ctx):
        game.gain_xp(_player(game, ctx, self.player), val(game, ctx, self.n), ctx)
        return None


class PlayToken(Instr):
    """Play a token. loc: 'here' | 'base' | Ref/location | None (controller chooses from valid locations)."""

    def __init__(self, token, loc="base", ready=False, count=1, exhausted=False, grant=None, out="token"):
        self.token, self.loc, self.ready, self.count, self.exhausted, self.grant, self.out = token, loc, ready, count, exhausted, grant, out

    def run(self, game, ctx):
        loc = self.loc
        if loc == "here":
            loc = ctx.here
        elif loc == "base":
            loc = ("base", ctx.controller)
        else:
            loc = val(game, ctx, loc)
        if loc is None:
            return None
        made = []
        for _ in range(val(game, ctx, self.count)):
            u = game.play_token(ctx.controller, self.token, loc, ready=self.ready, exhausted_gear=self.exhausted, ctx=ctx)
            if u is not None:
                made.append(u)
                for kw, v in (self.grant or {}).items():
                    game.add_mod(u, "keyword", (kw, v), duration="permanent", source=ctx.source)
        ctx.vars[self.out] = made[-1] if made else None
        ctx.vars[self.out + "s"] = tuple(made)
        return None


class PlayCard(Instr):
    """Play a card (uid in Ref) from a non-hand zone as a limited action.
    ignore: 'all' | 'energy' | 'power' | None ; alt_cost: (energy, power_list) ; loc override."""

    def __init__(self, card, ignore=None, alt_cost=None, loc=None, may=True, out="played", player=None):
        self.card, self.ignore, self.alt_cost, self.loc, self.may, self.out, self.player = card, ignore, alt_cost, loc, may, out, player

    def run(self, game, ctx):
        u = val(game, ctx, self.card)
        if u is None or u not in game.objects:
            ctx.vars[self.out] = None
            return None
        loc = val(game, ctx, self.loc) if self.loc is not None else None
        ok = game.limited_play(_player(game, ctx, self.player), u, ctx, ignore=self.ignore, alt_cost=self.alt_cost, loc=loc)
        ctx.vars[self.out] = u if ok else None
        return None


class Add(Instr):
    """Add resources: energy int, power list of domains ('any' for [A])."""

    def __init__(self, energy=0, power=(), restriction=None):
        self.energy, self.power, self.restriction = energy, power, restriction

    def run(self, game, ctx):
        game.add_resources(ctx.controller, val(game, ctx, self.energy), [val(game, ctx, p) for p in self.power], restriction=self.restriction)
        return None


class CounterItem(Instr):
    def __init__(self, target):
        self.target = target

    def run(self, game, ctx):
        t = val(game, ctx, self.target)
        if t is not None:
            game.do_counter(t, ctx)
        return None


class Attach(Instr):
    def __init__(self, gear, unit):
        self.gear, self.unit = gear, unit

    def run(self, game, ctx):
        g, u = val(game, ctx, self.gear), val(game, ctx, self.unit)
        if g is not None and u is not None:
            game.do_attach(g, u, ctx)
        return None


class Detach(Instr):
    def __init__(self, gear):
        self.gear = gear

    def run(self, game, ctx):
        for g in _uids(game, ctx, self.gear):
            game.do_detach(g, ctx)
        return None


class GiveMight(Instr):
    """Give +/-N might for a duration ('turn' | 'combat' | 'permanent'). min_value snapshots (CR 479.4.b)."""

    def __init__(self, targets, amount, duration="turn", min_value=None):
        self.targets, self.amount, self.duration, self.min_value = targets, amount, duration, min_value

    def run(self, game, ctx):
        amt = val(game, ctx, self.amount)
        if amt is None:
            return None
        for u in _uids(game, ctx, self.targets):
            a = amt
            if self.min_value is not None and a < 0:
                cur = game.chars(u).might or 0
                a = -min(-a, max(cur - self.min_value, 0))
            game.add_mod(u, "might", a, duration=self.duration, source=ctx.source)
        return None


class SetMight(Instr):
    """Increase/set might to a value this turn (arithmetic layer, snapshotted)."""

    def __init__(self, targets, value, duration="turn", base=False):
        self.targets, self.value, self.duration, self.base = targets, value, duration, base

    def run(self, game, ctx):
        v = val(game, ctx, self.value)
        for u in _uids(game, ctx, self.targets):
            if self.base:
                game.add_mod(u, "base_might", v, duration=self.duration, source=ctx.source)
            else:
                cur = game.chars(u).might or 0
                if v > cur:
                    game.add_mod(u, "might", v - cur, duration=self.duration, source=ctx.source)
        return None


class DoubleMight(Instr):
    def __init__(self, targets, duration="turn"):
        self.targets, self.duration = targets, duration

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            cur = game.chars(u).might or 0
            if cur > 0:
                game.add_mod(u, "might", cur, duration=self.duration, source=ctx.source)
        return None


class GiveKeyword(Instr):
    def __init__(self, targets, keyword, value=True, duration="turn"):
        self.targets, self.keyword, self.value, self.duration = targets, keyword, value, duration

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.add_mod(u, "keyword", (self.keyword, val(game, ctx, self.value)), duration=self.duration, source=ctx.source)
        return None


class GiveAbility(Instr):
    def __init__(self, targets, ability, duration="turn"):
        self.targets, self.ability, self.duration = targets, ability, duration

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.add_mod(u, "ability", self.ability, duration=self.duration, source=ctx.source)
        return None


class GiveTag(Instr):
    def __init__(self, targets, tag, duration="turn"):
        self.targets, self.tag, self.duration = targets, tag, duration

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.add_mod(u, "tag", self.tag, duration=self.duration, source=ctx.source)
        return None


class Prevent(Instr):
    def __init__(self, targets, amount, duration="turn"):
        self.targets, self.amount, self.duration = targets, amount, duration

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.add_mod(u, "prevent", val(game, ctx, self.amount), duration=self.duration, source=ctx.source)
        return None


class Delayed(Instr):
    """Register a delayed trigger: when `event` matching `filt` happens before `expires`, run `effect`."""

    def __init__(self, event, effect, filt=None, expires="turn", once=True, player=None, label=""):
        self.event, self.effect, self.filt, self.expires, self.once, self.player, self.label = event, effect, filt, expires, once, player, label

    def run(self, game, ctx):
        game.add_delayed(ctx, self.event, self.effect, self.filt, self.expires, self.once, self.label)
        return None


class DelayedPassive(Instr):
    """Register a turn-scoped passive effect (e.g. 'the next spell you play this turn deals 1 bonus damage')."""

    def __init__(self, kind, data, expires="turn", uses=None):
        self.kind, self.data, self.expires, self.uses = kind, data, expires, uses

    def run(self, game, ctx):
        game.add_turn_effect(ctx, self.kind, {k: val(game, ctx, v) if not callable(v) else v for k, v in self.data.items()}, self.expires, self.uses)
        return None


class Reflexive(Instr):
    """'Do this:' -> put a new chain item (effect) on the chain, controlled by ctx.controller."""

    def __init__(self, effect, times=1, label="do this"):
        self.effect, self.times, self.label = effect, times, label

    def run(self, game, ctx):
        for _ in range(val(game, ctx, self.times)):
            game.add_reflexive(ctx, self.effect, self.label)
        return None


def _pay_decision(game, ctx, e, pw, purpose, decline=True, label=""):
    """Offer every distinct way to pay (CR 445.2: paying Energy/Power is always optional; declining negates
    the instruction). Returns a Decision, or applies the only possibility and returns None."""
    from .payment import plan_label
    p = ctx.controller
    plans = game.payment_plans(p, e, pw, purpose) if game.can_pay(p, e, pw, purpose=purpose) else []
    opts = list(plans) + (["decline"] if decline else [])
    if not plans:
        return "cannot"
    if len(opts) == 1:
        game.apply_payment(p, plans[0], ctx, purpose)
        return None
    labels = [plan_label(game, pl) for pl in plans] + (["don't pay" + (f" ({label})" if label else "")] if decline else [])
    return Decision(p, "pay", opts, labels=labels, info={"energy": e, "power": list(pw), "for": label})


class PayResources(Instr):
    """'You may pay X' / 'pay X' (not a cost of playing). Stores True in out if paid. energy int, power list of domains.
    CR 445.2: a player instructed to pay Energy or Power may always decline, which negates the instruction."""

    def __init__(self, energy=0, power=(), out="paid", optional=True):
        self.energy, self.power, self.out, self.optional = energy, power, out, optional

    def run(self, game, ctx):
        e = val(game, ctx, self.energy)
        pw = [val(game, ctx, p) for p in self.power]
        purpose = {"kind": "effect", "uid": ctx.source}
        r = _pay_decision(game, ctx, e, pw, purpose, decline=True, label=f"{e} energy {pw}" if pw else f"{e} energy")
        if r == "cannot":
            ctx.vars[self.out] = False
            return None
        if r is None:
            ctx.vars[self.out] = True
            return None
        return r

    def resume(self, game, ctx, choice):
        if choice == "decline":
            ctx.vars[self.out] = False
        else:
            game.apply_payment(ctx.controller, choice, ctx, {"kind": "effect", "uid": ctx.source})
            ctx.vars[self.out] = True
        return None


class PayAnyEnergy(Instr):
    """'Pay any amount of energy' -> chooses amount into out, then how to pay it."""

    def __init__(self, out="x", power=False):
        self.out, self.power = out, power

    def _cost(self, n):
        return (0, ["any"] * n) if self.power else (n, [])

    def run(self, game, ctx):
        purpose = {"kind": "effect", "uid": ctx.source}
        opts = [n for n in range(0, 40) if game.can_pay(ctx.controller, *self._cost(n), purpose=purpose)]
        ctx.vars.pop("__payany", None)
        if len(opts) == 1:
            ctx.vars[self.out] = 0
            return None
        return Decision(ctx.controller, "pay_amount", opts, out=self.out, labels=[str(o) for o in opts])

    def resume(self, game, ctx, choice):
        purpose = {"kind": "effect", "uid": ctx.source}
        if "__payany" in ctx.vars:              # second step: how to pay the chosen amount
            n = ctx.vars.pop("__payany")
            ctx.vars[self.out] = n
            game.apply_payment(ctx.controller, choice, ctx, purpose)
            return None
        if not choice:
            return None
        r = _pay_decision(game, ctx, *self._cost(choice), purpose, decline=False)
        if isinstance(r, Decision):
            ctx.vars["__payany"] = choice
            r.out = None
            return r
        return None


class PayEquip(Instr):
    """Weaponmaster (CR 829): 'you may pay the Equip cost of a gear' -> out True if paid."""

    def __init__(self, gear, out="__eq"):
        self.gear, self.out = gear, out

    def _cost(self, game, ctx):
        from .abilities import Activated
        gear = val(game, ctx, self.gear)
        if gear is None or gear not in game.objects:
            return None
        for ab in game.abilities(gear):
            if isinstance(ab, Activated) and ab.is_equip:
                d = game.objects[gear].base_defn()
                pw = ["any" if x == "C" and not d.domains else (d.domains[0] if x == "C" else x) for x in ab.cost.get("power", ())]
                return ab.cost.get("energy", 0), pw
        return None

    def run(self, game, ctx):
        c = self._cost(game, ctx)
        if c is None:
            ctx.vars[self.out] = False
            return None
        purpose = {"kind": "ability", "types": {"gear"}, "uid": val(game, ctx, self.gear)}
        r = _pay_decision(game, ctx, c[0], c[1], purpose, decline=False)
        if r == "cannot":
            ctx.vars[self.out] = False
            return None
        if r is None:
            ctx.vars[self.out] = True
            return None
        return r

    def resume(self, game, ctx, choice):
        purpose = {"kind": "ability", "types": {"gear"}, "uid": val(game, ctx, self.gear)}
        game.apply_payment(ctx.controller, choice, ctx, purpose)
        ctx.vars[self.out] = True
        return None


class SpendXP(Instr):
    def __init__(self, n, out="paid", optional=True):
        self.n, self.out, self.optional = n, out, optional

    def run(self, game, ctx):
        n = val(game, ctx, self.n)
        p = game.players[ctx.controller]
        if p.xp < n:
            ctx.vars[self.out] = False
            return None
        if not self.optional:
            p.xp -= n; ctx.vars[self.out] = True
            return None
        return Decision(ctx.controller, "yesno", [True, False], out=self.out, labels=[f"spend {n} XP", "don't"])

    def resume(self, game, ctx, choice):
        if choice:
            game.players[ctx.controller].xp -= val(game, ctx, self.n)
        return None


class Look(Instr):
    """Look at top n cards of your deck; stores list of uids in out (they stay in the deck)."""

    def __init__(self, n, out="looked", player=None, reveal=False):
        self.n, self.out, self.player, self.reveal = n, out, player, reveal

    def run(self, game, ctx):
        p = _player(game, ctx, self.player)
        n = val(game, ctx, self.n)
        cards = game.players[p].deck[:n]
        ctx.vars[self.out] = list(cards)
        if self.reveal:
            game.emit("reveal", player=p, cards=list(cards), ctx=ctx)
        return None


class Mill(Instr):
    """Put the top n cards of a player's main deck into their trash."""

    def __init__(self, n=1, player=None):
        self.n, self.player = n, player

    def run(self, game, ctx):
        p = _player(game, ctx, self.player)
        for _ in range(val(game, ctx, self.n)):
            ps = game.players[p]
            if not ps.deck:
                break
            u = ps.deck.pop(0) if isinstance(ps.deck, list) else game._draw_raw(p)
            game.put_in_trash(u, ctx)
        return None


class RevealTopRune(Instr):
    def __init__(self, out="rune", player=None):
        self.out, self.player = out, player

    def run(self, game, ctx):
        p = _player(game, ctx, self.player)
        rd = game.players[p].rune_deck
        ctx.vars[self.out] = rd[0] if rd else None
        return None


class ToHand(Instr):
    """Put cards (uids) into their owner's hand from wherever they are."""

    def __init__(self, targets):
        self.targets = targets

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.put_in_hand(u, ctx)
        return None


class ToTrash(Instr):
    def __init__(self, targets):
        self.targets = targets

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.put_in_trash(u, ctx)
        return None


class ToTop(Instr):
    """Put cards back on top of their owner's deck in the given order."""

    def __init__(self, targets):
        self.targets = targets

    def run(self, game, ctx):
        for u in reversed(_uids(game, ctx, self.targets)):
            game.put_on_top(u)
        return None


class Predict(Instr):
    def __init__(self, n=1, player=None):
        self.n, self.player = n, player

    def run(self, game, ctx):
        p = _player(game, ctx, self.player)
        n = val(game, ctx, self.n)
        cards = game.players[p].deck[:n]
        if not cards:
            return None
        opts = []
        for k in range(len(cards) + 1):
            opts += [tuple(c) for c in itertools.combinations(cards, k)]
        return Decision(p, "predict", opts, out="__predict", labels=["recycle: " + (", ".join(game.label(u) for u in o) or "nothing") for o in opts])

    def resume(self, game, ctx, choice):
        if choice:
            game.do_recycle(list(choice), ctx)
        return None


class TakeControl(Instr):
    def __init__(self, targets, duration="permanent"):
        self.targets, self.duration = targets, duration

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.take_control(u, ctx.controller, ctx, duration=self.duration)
        return None


class Hide(Instr):
    """Hide a card (uid) facedown at a battlefield you control."""

    def __init__(self, card, loc):
        self.card, self.loc = card, loc

    def run(self, game, ctx):
        u, loc = val(game, ctx, self.card), val(game, ctx, self.loc)
        if u is not None and loc is not None:
            game.do_hide(ctx.controller, u, loc, ctx)
        return None


class Emit(Instr):
    def __init__(self, kind, **data):
        self.kind, self.data = kind, data

    def run(self, game, ctx):
        game.emit(self.kind, **{k: val(game, ctx, v) for k, v in self.data.items()}, ctx=ctx)
        return None


class ActivateTriggers(Instr):
    """'Activate the conquer effects of units here' etc."""

    def __init__(self, targets, event):
        self.targets, self.event = targets, event

    def run(self, game, ctx):
        for u in _uids(game, ctx, self.targets):
            game.activate_named_triggers(u, self.event, ctx)
        return None


class ReplaceWithToken(Instr):
    def __init__(self, target, token):
        self.target, self.token = target, token

    def run(self, game, ctx):
        t = val(game, ctx, self.target)
        if t is not None:
            game.replace_with_token(t, self.token, ctx)
        return None


class ExtraTurn(Instr):
    def __init__(self, player=None):
        self.player = player

    def run(self, game, ctx):
        game.turn_queue.insert(0, _player(game, ctx, self.player))
        return None


class SwapLocations(Instr):
    def __init__(self, a, b):
        self.a, self.b = a, b

    def run(self, game, ctx):
        a, b = val(game, ctx, self.a), val(game, ctx, self.b)
        if a is None or b is None:
            return None
        la, lb = game.objects[a].location, game.objects[b].location
        if la is None or lb is None or la == lb:
            return None
        game.do_move([a], lb, ctx)
        game.do_move([b], la, ctx)
        return None


class CopyAs(Instr):
    def __init__(self, target, model):
        self.target, self.model = target, model

    def run(self, game, ctx):
        t, m = val(game, ctx, self.target), val(game, ctx, self.model)
        if t is not None and m is not None:
            game.objects[t].copy_of = game.objects[m].defn
            game.objects[t].chars_cache = None
            game.bump()
        return None


# ------------------------------------------------------------------ common value helpers
def count(sel):
    return lambda g, c: len(sel.candidates(g, c))


def might_of(ref):
    def f(g, c):
        u = val(g, c, ref)
        return (g.chars(u).might if u in g.objects else None)
    return f


def controller_of(ref):
    return lambda g, c: g.objects[val(g, c, ref)].controller if val(g, c, ref) in g.objects else None


def loc_of(ref):
    return lambda g, c: g.objects[val(g, c, ref)].place if val(g, c, ref) in g.objects else None


def opponent(g, c):
    return g.opponent(c.controller)


def hand_size(player=None):
    return lambda g, c: len(g.players[c.controller if player is None else val(g, c, player)].hand)


def is_my_turn(g, c):
    return g.turn_player == c.controller


def has_var(name):
    return lambda g, c: c.vars.get(name) not in (None, False, (), [])


def not_(f):
    return lambda g, c: not val(g, c, f)


def all_of(*fs):
    return lambda g, c: all(val(g, c, f) for f in fs)


def any_of(*fs):
    return lambda g, c: any(val(g, c, f) for f in fs)


def legion(g, c):
    return g.legion_active(c.controller, c.source)


def played_cost_additional(name="add"):
    return lambda g, c: bool(c.paid.get(name))


__all__ = [n for n in dir() if not n.startswith("_")]
