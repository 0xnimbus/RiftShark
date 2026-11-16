"""Paying Energy and Power exactly as the Core Rules describe (CR 162-168, 357, 430, 445).

A player's Rune Pool holds Energy and Power. Runes add to it with their two Reaction abilities
([E]: Add [1] and Recycle this: Add [C], CR 164.2); other permanents may have Reaction "Add" abilities
too (Kai'Sa's legend, Seals, Energy Conduit...). Paying removes resources from the pool (CR 445.1), and
while paying a player may activate any of those Add Reactions (CR 357.1.a, 430.3, 445.2.c).

The engine turns that freedom into one decision: every *distinct* way to pay a cost is offered as a
`plan` (which runes to exhaust, which to recycle and in what order, which other Add abilities to use, and
which pool resources to spend). Plans are deduplicated by the game state they lead to, so runes of the same
domain and state are interchangeable. A ready rune that is recycled is exhausted for [1] first, because the
extra Energy stays in the pool and can never hurt (the only strictly dominated choice left out). Adding
resources beyond what the cost needs ("floating") is done with separate rune actions whenever the player
could activate a Reaction (see FlowMixin.legal_actions).

Add restrictions ("Use only to play spells", "Spend this Energy only during showdowns") are kept on the
pool tokens and checked against the purpose of the payment.
"""
from __future__ import annotations

from collections import Counter
from itertools import permutations

from .abilities import Activated

CAP = 400   # safety bound on enumerated plans (far above anything a real board produces)


# ------------------------------------------------------------------ restrictions
def purpose_of_card(game, uid, kind="play"):
    o = game.objects.get(uid)
    types = set(o.base_defn().types) if o is not None else set()
    return {"kind": kind, "types": types, "uid": uid}


def restriction_ok(game, text, purpose):
    """Can a resource restricted by `text` (e.g. 'spells', 'units or gear', 'showdowns') pay for `purpose`?"""
    if text is None:
        return True
    if not purpose:
        return False
    t = text.lower()
    if "showdown" in t:
        return game.showdown is not None
    kind, types = purpose.get("kind"), purpose.get("types", ())
    ok = False
    if "spell" in t and kind == "play" and "spell" in types:
        ok = True
    for ty in ("unit", "gear"):
        if ty in t:
            if kind == "play" and ty in types:
                ok = True
            if "abilit" in t and kind == "ability" and ty in types:
                ok = True
    return ok


# ------------------------------------------------------------------ sources
def add_sources(game, p):
    """Other permanents' Reaction Add abilities usable while paying: [(uid, idx, energy, power, restriction)].
    Abilities whose cost is exhausting their source (and possibly killing it, Gold: "Kill this, [T]: [Add] [A]")
    and whose effect is a single Add qualify."""
    from .ops import Add
    from .vm import Context, val
    out = []
    for u, o in game.board_items():
        if o.zone != "board" or o.controller != p or o.exhausted or o.defn.type == "rune":
            continue
        for i, ab in enumerate(game.abilities(u)):
            if not (isinstance(ab, Activated) and ab.is_add and ab.timing == "reaction"):
                continue
            c = ab.cost
            if c.get("energy") or c.get("power") or not c.get("exhaust"):
                continue
            if any(c.get(k) for k in ("banish_self", "spend_buff", "xp", "discard", "sacrifice", "recycle")):
                continue
            if not ab.active(game, u):
                continue
            if ab.restriction is not None and not ab.restriction(game, u):
                continue
            if ab.once_per_turn and o.temp.get(("act", i)) == game.turn:
                continue
            code = [ins for ins in ab.code]
            if len(code) != 1 or not isinstance(code[0], Add):
                continue
            ctx = Context(p, u)
            e = val(game, ctx, code[0].energy) or 0
            pw = tuple(val(game, ctx, d) for d in code[0].power)
            out.append((u, i, e, pw, code[0].restriction))
    return out


def _pool_tokens(game, p, purpose):
    ps = game.players[p]
    tok = Counter()
    if ps.energy:
        tok[("E", None)] += ps.energy
    for d in ps.power:
        tok[(d, None)] += 1
    for res, txt in ps.pool_r:
        if restriction_ok(game, txt, purpose):
            tok[(res, txt)] += 1
    return tok


# ------------------------------------------------------------------ feasibility (fast)
def can_pay(game, p, energy, power, purpose=None, extra_exhaust=()):
    energy = energy or 0
    power = [d for d in power]
    if energy <= 0 and not power:
        return True
    ps = game.players[p]
    tok = _pool_tokens(game, p, purpose)
    for (u, i, e, pw, txt) in add_sources(game, p):
        if restriction_ok(game, txt, purpose):
            tok[("E", txt)] += e
            for d in pw:
                tok[(d, txt)] += 1
    runes = [game.objects[u] for u in ps.runes]
    ready = sum(1 for o in runes if not o.exhausted and o.uid not in extra_exhaust)
    e_tok = sum(n for (r, _), n in tok.items() if r == "E")
    if e_tok + ready < energy:
        return False
    # power: specific domains first from same-domain sources, then universal, then 'any' from leftovers
    spec = Counter(d for d in power if d != "any")
    n_any = sum(1 for d in power if d == "any")
    dom_src = Counter()
    for (r, _), n in tok.items():
        if r not in ("E", "any"):
            dom_src[r] += n
    for o in runes:
        dom_src[o.domain] += 1
    univ = sum(n for (r, _), n in tok.items() if r == "any")
    left = 0
    for d, n in spec.items():
        have = dom_src.get(d, 0)
        if have >= n:
            dom_src[d] = have - n
        else:
            univ -= n - have
            dom_src[d] = 0
            if univ < 0:
                return False
    left = univ + sum(dom_src.values())
    return left >= n_any


# ------------------------------------------------------------------ plan enumeration
def _assign_power(reqs, tokens, groups):
    """Yield (spent tokens Counter, recycled rune groups Counter) covering every power requirement."""
    def cats(req):
        out = []
        for k, n in sorted(tokens.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
            r = k[0]
            if n > 0 and r != "E" and (req == "any" or r == req or r == "any"):
                out.append(("tok", k))
        for g, n in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            if n > 0 and (req == "any" or g[0] == req):
                out.append(("rune", g))
        return out

    spent, rec = Counter(), Counter()

    def rec_(i, last):
        if i == len(reqs):
            yield Counter(spent), Counter(rec)
            return
        cs = cats(reqs[i])
        start = 0
        if i > 0 and reqs[i] == reqs[i - 1] and last is not None and last in cs:
            start = cs.index(last)
        for c in cs[start:]:
            kind, k = c
            if kind == "tok":
                if spent[k] >= tokens[k]:
                    continue
                spent[k] += 1
                yield from rec_(i + 1, c)
                spent[k] -= 1
            else:
                if rec[k] >= groups[k]:
                    continue
                rec[k] += 1
                yield from rec_(i + 1, c)
                rec[k] -= 1

    yield from rec_(0, None)


def _assign_energy(n, e_tokens, ready):
    """Yield (spent E tokens Counter, exhausted ready runes Counter by domain) adding up to n."""
    cats = [("tok", k, c) for k, c in sorted(e_tokens.items(), key=lambda kv: str(kv[0][1])) if c > 0]
    cats += [("ex", d, c) for d, c in sorted(ready.items()) if c > 0]
    pick = [0] * len(cats)

    def rec_(i, left):
        if left == 0:
            sp, ex = Counter(), Counter()
            for (kind, k, _), m in zip(cats, pick):
                if m:
                    (sp if kind == "tok" else ex)[k] += m
            yield sp, ex
            return
        if i == len(cats):
            return
        for m in range(min(left, cats[i][2]), -1, -1):
            pick[i] = m
            yield from rec_(i + 1, left - m)
        pick[i] = 0

    yield from rec_(0, n)


def plans(game, p, energy, power, purpose=None):
    """Every distinct legal way for player p to pay `energy` and `power` (list of domains or 'any').
    Returns a list of plans (hashable tuples); the first is the engine's standard payment."""
    energy = energy or 0
    power = sorted(power, key=lambda d: (d == "any", d))
    if energy <= 0 and not power:
        return [((), ())]
    ps = game.players[p]
    base = _pool_tokens(game, p, purpose)
    by_group = {}
    for u in sorted(ps.runes):
        o = game.objects[u]
        by_group.setdefault((o.domain, o.exhausted), []).append(u)
    groups = Counter({g: len(us) for g, us in by_group.items()})
    srcs = [s for s in add_sources(game, p) if restriction_ok(game, s[4], purpose)]
    found = {}
    for mask in range(1 << len(srcs)):
        used = [srcs[i] for i in range(len(srcs)) if mask >> i & 1]
        tokens = Counter(base)
        for (_, _, e, pw, txt) in used:
            if e:
                tokens[("E", txt)] += e
            for d in pw:
                tokens[(d, txt)] += 1
        for spent_p, recycled in _assign_power(power, tokens, groups):
            surplus = sum(n for (d, ex), n in recycled.items() if not ex)
            left = tokens - spent_p
            e_tok = Counter({k: n for k, n in left.items() if k[0] == "E"})
            if surplus:
                e_tok[("E", None)] += surplus
            ready = Counter()
            for (d, ex), n in groups.items():
                if not ex:
                    ready[d] += n - recycled[(d, ex)]
            for spent_e, exhausted in _assign_energy(energy, e_tok, ready):
                # a ready rune that is recycled is exhausted first only when its [1] is actually spent
                surplus_used = min(surplus, max(0, spent_e[("E", None)] - left[("E", None)]))
                spent_e = Counter(spent_e)
                if surplus_used < spent_e[("E", None)] - left[("E", None)]:
                    continue
                spent = spent_p + spent_e
                # every Add ability used must pay for part of the cost (otherwise it is a separate float)
                if any(all(spent[k] <= tokens[k] - _outputs(s)[k] for k in _outputs(s)) for s in used):
                    continue
                for order in sorted(set(permutations(sorted(d for (d, ex), n in recycled.items() for _ in range(n))))):
                    plan = _build(by_group, used, recycled, exhausted, order, spent, surplus_used)
                    sig = _signature(groups, recycled, exhausted, order, used, tokens + Counter({("E", None): surplus_used}) - spent)
                    if sig not in found:
                        found[sig] = plan
                    if len(found) >= CAP:
                        break
    return sorted(found.values(), key=lambda pl: _score(game, pl))


def _outputs(src):
    _, _, e, pw, txt = src
    c = Counter()
    if e:
        c[("E", txt)] += e
    for d in pw:
        c[(d, txt)] += 1
    return c


def _build(by_group, used, recycled, exhausted, order, spent, surplus_used=None):
    acts = [("ab", u, i) for (u, i, _, _, _) in used]
    take = {g: list(us) for g, us in by_group.items()}
    rec_uids = {}
    for (d, ex), n in sorted(recycled.items()):
        for _ in range(n):
            rec_uids.setdefault(d, []).append((take[(d, ex)].pop(0), ex))
    for d, n in sorted(exhausted.items()):
        for _ in range(n):
            acts.append(("ex", take[(d, False)].pop(0)))
    rc = []
    pre_ex = 10 ** 6 if surplus_used is None else surplus_used
    for d in order:
        u, ex = rec_uids[d].pop(0)
        if not ex and pre_ex > 0:
            acts.append(("ex", u))      # exhaust for [1] before recycling: only when that Energy pays the cost
            pre_ex -= 1
        rc.append(("rc", u))
    acts += rc
    # resources generated by the activations are spent too: [1] per rune exhausted for Energy, [C] per rune recycled
    spent = Counter(spent)
    spent[("E", None)] += sum(exhausted.values())
    for d in order:
        spent[(d, None)] += 1
    sp = tuple(sorted(((k[0], k[1] or ""), n) for k, n in spent.items() if n > 0))
    return (tuple(acts), sp)


def _signature(groups, recycled, exhausted, order, used, pool_left):
    left = Counter(groups)
    left.subtract(recycled)
    for d, n in exhausted.items():
        left[(d, False)] -= n
        left[(d, True)] += n
    return (tuple(sorted((g, n) for g, n in left.items() if n > 0)), tuple(order),
            tuple(sorted((u, i) for (u, i, _, _, _) in used)),
            tuple(sorted(((k[0], k[1] or ""), n) for k, n in pool_left.items() if n > 0)))


def _score(game, plan):
    acts, spend = plan
    n_rc = sum(1 for a in acts if a[0] == "rc")
    n_ex = sum(1 for a in acts if a[0] == "ex")
    n_ab = sum(1 for a in acts if a[0] == "ab")
    # standard payment: spend the pool first, then use Add abilities, recycle exhausted runes before ready ones,
    # and keep the most domains available among the runes that stay ready
    return (n_rc, n_ex, -n_ab, -sum(n for _, n in spend), repr(plan))


# ------------------------------------------------------------------ labels and execution
def _rname(game, u):
    o = game.objects[u]
    return (o.domain or "?").capitalize()


def plan_label(game, plan):
    acts, spend = plan
    parts = []
    ex = Counter(_rname(game, a[1]) for a in acts if a[0] == "ex" and ("rc", a[1]) not in acts)
    if ex:
        parts.append("exhaust " + ", ".join(f"{n} {d}" if n > 1 else d for d, n in sorted(ex.items())) + " rune" + ("s" if sum(ex.values()) > 1 else ""))
    rc = [_rname(game, a[1]) for a in acts if a[0] == "rc"]
    if rc:
        parts.append("recycle " + " then ".join(rc) + " rune" + ("s" if len(rc) > 1 else ""))
    for a in acts:
        if a[0] == "ab":
            parts.append("use " + game.objects[a[1]].defn.name)
    pool = []
    for (r, txt), n in spend:
        name = "energy" if r == "E" else ("universal power" if r == "any" else r.capitalize() + " power")
        pool.append(f"{n} {name}" + (f" (only {txt})" if txt else ""))
    if pool:
        parts.append("spend " + ", ".join(pool))
    return "pay: " + "; ".join(parts)


def apply_plan(game, p, plan, ctx=None, purpose=None):
    """Carry out a payment plan: activate the Add abilities in order, then remove the resources from the pool."""
    acts, spend = plan
    ps = game.players[p]
    for a in acts:
        if a[0] == "ex":
            o = game.objects[a[1]]
            game.do_exhaust(a[1], ctx)
            game.add_resources(p, 1, (), ctx=ctx)
        elif a[0] == "rc":
            o = game.objects[a[1]]
            dom = o.domain
            game.do_recycle([a[1]], ctx)
            game.add_resources(p, 0, (dom,), ctx=ctx)
        elif a[0] == "ab":
            u, i = a[1], a[2]
            src = next(s for s in add_sources(game, p) if s[0] == u and s[1] == i)
            ab = game.abilities(u)[i]
            if ab.once_per_turn:
                game.objects[u].temp[("act", i)] = game.turn
            game.do_exhaust(u, ctx)
            if ab.cost.get("kill_self"):
                game.do_kill([u], ctx, by="cost")          # Gold: "Kill this, [T]: [Add] [A]"
            game.log("activate", uid=u, name=game.objects[u].defn.name, player=p, label=ab.label)
            game.add_resources(p, src[2], src[3], restriction=src[4], ctx=ctx)
    energy, power = 0, []
    for (r, txt), n in spend:
        txt = txt or None
        for _ in range(n):
            if txt is None:
                if r == "E":
                    if ps.energy < 1:
                        raise RuntimeError("payment plan: missing energy")
                    ps.energy -= 1
                else:
                    ps.power.remove(r)
            else:
                ps.pool_r.remove((r, txt))
            if r == "E":
                energy += 1
            else:
                power.append(r)
    tot = game.turn_memo.setdefault(("spent", p), [0, 0])      # energy, power spent this turn (Sivir, Mercenary)
    tot[0] += energy
    tot[1] += len(power)
    game.bump()
    game.log("pay", player=p, energy=energy, power=power)
    if energy or power:
        game.emit("pay", player=p, energy=energy, power=power, ctx=ctx)
    game.dirty = True
