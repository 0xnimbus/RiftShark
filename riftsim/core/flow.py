"""Turn structure, chain (HOT FEPR), cleanups, showdowns, combat and scoring (CR 300-474).

The game is driven by Game.run(): it advances until a player decision is needed and returns a
Decision; Game.choose(option) applies it. All flow state lives on the Game, so clones can be
resumed anywhere (search) and a replay is just the list of chosen options.
"""
from __future__ import annotations

import itertools

from .abilities import Activated, PlayPermission, Static
from .objects import ChainItem
from .vm import Context, Decision, Frame, Instr, Ref, compile_effect, relocate, run_vm, resume_vm, val, _copy_containers
from .ops import Choose, ChooseMode, May, SetVar, Do, PayResources, ChooseFromList, Exhaust, Recycle
from .selectors import Sel
from .payment import plan_label
from . import payment

PHASES = ["awaken", "beginning", "scoring", "channel", "draw", "main", "ending", "expiration"]


def _depends_on_choice(ins):
    """A choice restricted by an earlier choice (\"a unit there\") can't be checked before that choice is made."""
    if getattr(ins, "depends", False):
        return True
    w = getattr(ins.sel, "where", None) or ""
    return w.startswith("loc:")


def showoff_requirement(text):
    """Parse the object of '[Show Off] X.' (CR 832.1.b) into predicate(game, uid) -> bool, or None if unknown."""
    import re
    m = re.search(r"\[Show Off\]\s*([^.\n]*)", text or "")
    if not m:
        return None
    x = m.group(1).strip().lower()
    x = re.sub(r"^an? ", "", x)
    if x == "card":
        return lambda g, u: True
    if x in ("unit", "gear", "spell"):
        return lambda g, u, t=x: t in g.chars(u).types if g.objects[u].zone == "board" else t in g.objects[u].defn.types
    m = re.fullmatch(r"card with \[(\w+)\]", x)
    if m:
        kw = m.group(1).lower()
        return lambda g, u, kw=kw: bool((g.chars(u).keywords if g.objects[u].zone == "board" else g.objects[u].defn.keywords or {}).get(kw))
    m = re.fullmatch(r"card with energy cost \[(\d+)\] or more", x)
    if m:
        n = int(m.group(1))
        return lambda g, u, n=n: (g.objects[u].defn.energy or 0) >= n
    if re.fullmatch(r"[a-z'-]+", x):
        tag = x.capitalize()
        return lambda g, u, tag=tag: tag in (g.chars(u).tags if g.objects[u].zone == "board" else g.objects[u].defn.tags)
    return None


class _ShowOff(Instr):
    """CR 832.1.c: as you play this, you may reveal a matching card from hand or pick a matching friendly object on the
    board. Decided while finalizing (832.1.c.2). The shown-off object's information is locked in (832.1.d)."""

    def __init__(self, item_id, req):
        self.item_id, self.req = item_id, req

    def run(self, game, ctx):
        it = next((x for x in game.chain if x.id == self.item_id), None)
        if it is None:
            return None
        game.shown_off[it.uid] = None
        ctx.shown_off = None
        ps = game.players[ctx.controller]
        cands = [u for u in ps.hand if u != it.uid]
        cands += [u for u, o in game.board_items() if o.controller == ctx.controller
                  and u != it.uid and o.location is not None and o.location[0] in ("base", "bf", "legend", "runes")
                  and o.defn.type != "battlefield"]
        opts = [None]
        for u in cands:
            try:
                if self.req(game, u):
                    opts.append(u)
            except (KeyError, AttributeError, TypeError):
                pass
        if len(opts) == 1:
            return None
        labels = ["don't show off"] + [("reveal " if game.objects[u].zone == "hand" else "show off ") + game.label(u)
                                       for u in opts[1:]]
        return Decision(ctx.controller, "show_off", opts, labels=labels, out="__showoff_pick",
                        info={"item": it.id, "label": "Show Off"})

    def resume(self, game, ctx, choice):
        it = next((x for x in game.chain if x.id == self.item_id), None)
        if choice is None or it is None:
            return None
        o = game.objects[choice]
        c = game.chars(choice) if o.zone == "board" else None
        snap = {"uid": choice, "name": o.defn.name, "energy": o.defn.energy or 0, "power": o.defn.power or 0,
                "might": (c.might if c is not None else o.defn.might) or 0, "zone": o.zone}
        ctx.shown_off = snap
        game.shown_off[it.uid] = snap
        if o.zone == "hand":
            game.emit("reveal", player=ctx.controller, cards=[choice], ctx=ctx)
        game.emit("showoff", player=ctx.controller, uid=it.uid, shown=choice, ctx=ctx)
        game.log("showoff", player=ctx.controller, item=it.id, shown=o.defn.name)
        return None


class _SnapChoices(Instr):
    """Remember the choices made for execution k (Repeat, CR 820.2)."""

    def __init__(self, k):
        self.k = k

    def run(self, game, ctx):
        snaps = ctx.vars.setdefault("__rep_choices", {})
        snaps[self.k] = _copy_containers({n: v for n, v in ctx.vars.items() if not n.startswith("__rep") and n not in ("__costs", "__ask")})
        return None


class _SkipUnlessRepeat(Instr):
    def __init__(self, target):
        self.target = target

    def run(self, game, ctx):
        return None if ctx.repeat else self.target


class _RestoreChoices(Instr):
    def __init__(self, k):
        self.k = k

    def run(self, game, ctx):
        snap = (ctx.vars.get("__rep_choices") or {}).get(self.k)
        if snap:
            ctx.vars.update(_copy_containers(snap))
            # the earlier executions may have made these choices illegal (Hard Bargain countering the same spell
            # twice): instructions that can't be performed are ignored (CR 820.1.d.2)
            game._revalidate_targets(ctx)
        return None


class _FinalizeCosts(Instr):
    """Last instruction of a finalize program: Deflect costs, optional additional costs
    (Accelerate, Repeat), then the base cost."""

    def __init__(self, item_id):
        self.item_id = item_id

    def _item(self, game):
        for it in game.chain:
            if it.id == self.item_id:
                return it
        return None

    def run(self, game, ctx):
        it = self._item(game)
        if it is None:
            return None
        if it.cost is None:
            it.cost = {"energy": 0, "power": []}
        if ctx.vars.get("__ignore_cost"):          # "If you do, ignore this spell's cost" (Call to Glory, Wallop)
            it.cost = {"energy": 0, "power": []}
        ctx.vars.setdefault("__costs", {})
        if it.kind == "spell" and not ctx.vars.get("__chosen_reduce_done"):
            ctx.vars["__chosen_reduce_done"] = True
            chosen = set(u for u in game._target_uids(ctx) if u is not None)
            for src, n in game.rules("spells_choosing_me_cost_less", player=it.controller):    # Irelia, Graceful
                if src in chosen:
                    if it.cost["power"]:
                        it.cost = dict(it.cost, power=list(it.cost["power"])[1:])
                    else:
                        ctx.vars["__cost_reduce"] = ctx.vars.get("__cost_reduce", 0) + n
        opts = game._optional_costs(it, ctx)
        for name, (energy, power, label) in opts:
            if name in ctx.vars["__costs"]:
                continue
            payable = False
            for ve, vp in game.optional_cost_variants_for(it, ctx, name) or [(energy, power)]:
                total_e = ve + it.cost["energy"] + sum(e for (e, _) in ctx.vars["__costs"].values())
                total_p = list(vp) + list(it.cost["power"]) + [d for (_, ps) in ctx.vars["__costs"].values() for d in ps]
                total_p += ["any"] * game._deflect_total(it, ctx)
                payable = payable or game.can_pay(ctx.controller, total_e, total_p, purpose=game.item_purpose(it))
            if not payable:
                ctx.vars["__costs"][name] = (0, [])
                continue
            ctx.vars["__ask"] = name
            return Decision(ctx.controller, "additional_cost", [True, False], out="__ans",
                            labels=[f"pay {label}", f"don't pay {label}"], info={"item": it.id, "cost": name})
        return self._finish(game, ctx, it)

    def resume(self, game, ctx, choice):
        it = self._item(game)
        if ctx.vars.get("__ask") == "__pay__":
            ctx.vars.pop("__ask")
            e, p = ctx.vars.pop("__pay_total")
            e, p = ctx.vars.pop("__pay_totals", {}).get(choice, (e, p))
            game.apply_payment(ctx.controller, choice, ctx, game.item_purpose(it))
            it.cost["paid"] = (e, p)
            return None
        name = ctx.vars.pop("__ask")
        opts = dict(game._optional_costs(it, ctx))
        energy, power, _ = opts[name]
        if choice:
            if name == "add":                         # "pay [X] as an additional cost"
                ctx.paid["add"] = True
                for ab in game._abilities_of(it.uid, game.objects[it.uid]):
                    pr = game._resource_additional_cost(ab)
                    if pr is not None:
                        ctx.vars[pr.out] = True
            ctx.vars["__costs"][name] = (energy, list(power))
            ctx.vars.setdefault("__cost_variants", {})[name] = game.optional_cost_variants_for(it, ctx, name)
            ctx.paid[name] = True
            if name.startswith("repeat"):
                ctx.repeat += 1
        else:
            ctx.vars["__costs"][name] = (0, [])
        return self.run(game, ctx)

    def _finish(self, game, ctx, it):
        e = max(0, it.cost["energy"] - ctx.vars.get("__cost_reduce", 0)) + sum(x for (x, _) in ctx.vars["__costs"].values())
        p = list(it.cost["power"]) + [d for (_, ps) in ctx.vars["__costs"].values() for d in ps]
        p += ["any"] * game._deflect_total(it, ctx)
        if it.cost.get("exhaust"):
            game.do_exhaust(it.cost["exhaust"], ctx)
        for u in it.cost.get("kill", ()):
            game.do_kill([u], ctx, by="cost")
        for u in it.cost.get("banish", ()):
            game.do_banish([u], ctx)
        for u in it.cost.get("discard", ()):
            game.do_discard(ctx.controller, [u], ctx)
        for u in it.cost.get("recycle", ()):
            game.do_recycle([u], ctx)
        if it.cost.get("spend_buff"):
            game.do_spend_buff(it.cost["spend_buff"], ctx)
        if it.cost.get("xp"):
            game.players[ctx.controller].xp -= it.cost["xp"]
        purpose = game.item_purpose(it)
        # Ezreal, Prodigy: each paid optional cost is [1] or [A] less, the player's pick, so every combination's plans
        # are offered (the first is the standard one)
        totals = [(e, p)]
        for name, vs in ctx.vars.get("__cost_variants", {}).items():
            if len(vs) <= 1 or name not in ctx.vars["__costs"]:
                continue
            ce, cp = ctx.vars["__costs"][name]
            nxt = []
            for te, tp in totals:
                rest = list(tp)
                for d in cp:
                    rest.remove(d)
                for ve, vp in vs:
                    nxt.append((te - ce + ve, rest + list(vp)))
            totals = nxt
        plans, plan_total = [], {}
        for te, tp in totals:
            if not game.can_pay(ctx.controller, te, tp, purpose=purpose):
                continue
            for pl in game.payment_plans(ctx.controller, te, tp, purpose):
                if pl not in plan_total:
                    plan_total[pl] = (te, list(tp))
                    plans.append(pl)
        if plans:
            e, p = plan_total[plans[0]]
        if not plans:
            # cannot pay after all (e.g. deflect targets): the item leaves the chain (CR 355)
            game._fizzle_item(it, "cannot pay")
            return None
        if len(plans) == 1:
            game.apply_payment(ctx.controller, plans[0], ctx, purpose)
            it.cost["paid"] = (e, p)
            return None
        # CR 357.1.a / 445.2.c: the player chooses which runes and Add abilities pay the cost
        ctx.vars["__ask"] = "__pay__"
        ctx.vars["__pay_total"] = (e, list(p))
        if len(totals) > 1:
            ctx.vars["__pay_totals"] = plan_total
        return Decision(ctx.controller, "pay", plans, labels=[plan_label(game, pl) for pl in plans],
                        info={"item": it.id, "for": it.label, "energy": e, "power": list(p)})


class _RepeatDeflect(Instr):
    """Deflect is paid "for each time they choose [me]" (CR 809.1.c): the Repeat execution's choices are made after
    the other costs were paid, so their Deflect taxes are paid here. Can't pay: the item leaves the chain, as with the
    first execution's costs (_FinalizeCosts._finish)."""

    def __init__(self, item_id):
        self.item_id = item_id

    def _item(self, game):
        return next((it for it in game.chain if it.id == self.item_id), None)

    def run(self, game, ctx):
        it = self._item(game)
        if it is None:
            return None
        n = game._deflect_total(it, ctx)
        if n <= 0:
            return None
        p = ["any"] * n
        purpose = game.item_purpose(it)
        plans = game.payment_plans(ctx.controller, 0, p, purpose) if game.can_pay(ctx.controller, 0, p, purpose=purpose) else []
        if not plans:
            game._fizzle_item(it, "cannot pay Deflect")
            return None
        if len(plans) == 1:
            game.apply_payment(ctx.controller, plans[0], ctx, purpose)
            return None
        return Decision(ctx.controller, "pay", plans, labels=[plan_label(game, pl) for pl in plans],
                        info={"item": it.id, "for": it.label + " (Deflect, repeat)", "energy": 0, "power": list(p)})

    def resume(self, game, ctx, choice):
        it = self._item(game)
        game.apply_payment(ctx.controller, choice, ctx, game.item_purpose(it) if it is not None else None)
        return None


class DamageAssignments:
    """Legal combat damage assignments (CR 467.2.c) for targets with (lethal need or None, priority) each, priority
    0 = Tank, 1 = normal, 2 = Backline / "assigned last". Units are dealt lethal in full in priority order (any order
    inside a priority, 467.2.c.3/6/7); the unit reached when damage runs out takes the rest; nobody gets more than
    lethal while another unit can still take damage (467.2.c.4); a unit no amount can kill may absorb any part and
    be passed; once every unit has lethal the excess may go anywhere. As a test on a plan a:
      - every killable unit has a >= lethal (then any split is fine), or
      - nobody gets more than lethal, at most one unit is partly damaged, and with p = the lowest priority of a
        killable unit short of lethal, no unit of a higher priority gets damage and the partly damaged one has p.
    The automaton walks the targets in order with state (damage left, lowest short priority, highest damaged
    priority, any over lethal, priority of the partial one), so counting and offering amounts never enumerates."""

    NONE = 3

    def __init__(self, info, total):
        self.info, self.total = list(info), total
        self._memo = {}

    def _step(self, i, st, a):
        s, low, high, over, part = st
        need, p = self.info[i]
        if a > 0:
            high = max(high, p)
        if need is not None:
            if a > need:
                over = True
            elif a < need:
                low = min(low, p)
                if a > 0:
                    if part != self.NONE:
                        return None
                    part = p
        return (s - a, low, high, over, part)

    def _accept(self, st):
        s, low, high, over, part = st
        if s:
            return False
        if low == self.NONE:
            return True
        return not over and high <= low and part in (self.NONE, low)

    def _count(self, i, st):
        key = (i, st)
        if key in self._memo:
            return self._memo[key]
        if i == len(self.info):
            n = 1 if self._accept(st) else 0
        else:
            n = 0
            for a in range(st[0] + 1):
                nx = self._step(i, st, a)
                if nx is not None:
                    n += self._count(i + 1, nx)
        self._memo[key] = n
        return n

    def _start(self):
        return (self.total, self.NONE, -1, False, self.NONE)

    def _state(self, prefix):
        st = self._start()
        for i, a in enumerate(prefix):
            st = self._step(i, st, a)
            if st is None or st[0] < 0:
                return None
        return st

    def count(self, prefix=()):
        st = self._state(prefix)
        return 0 if st is None else self._count(len(prefix), st)

    def amounts(self, prefix):
        """Amounts the next unit may get so that a legal assignment can still be completed."""
        st = self._state(prefix)
        i = len(prefix)
        return [a for a in range(st[0] + 1) if (nx := self._step(i, st, a)) is not None and self._count(i + 1, nx)]

    def plans(self):
        out = []

        def walk(prefix):
            if len(prefix) == len(self.info):
                out.append(tuple(prefix))
                return
            for a in self.amounts(prefix):
                walk(prefix + (a,))
        if self.count():
            walk(())
        return sorted(out, reverse=True)


class DamageAssignmentsAny:
    """CR 467.2.c.8-9: a unit with exclusionary requirements (Tank and Backline / "assigned last") follows the one
    its assigner picks, each such unit on its own. `variants` are DamageAssignments, one per combination of picks;
    an assignment is legal when it is legal under one of them. count() is an upper bound (a plan legal under two
    combinations counts twice) used only to pick flat vs one-unit-at-a-time; plans() has each plan once."""

    def __init__(self, variants):
        self.variants = variants
        self.info = variants[0].info
        self.total = variants[0].total

    def count(self, prefix=()):
        return sum(v.count(prefix) for v in self.variants)

    def amounts(self, prefix):
        out = set()
        for v in self.variants:
            if v.count(prefix):
                out.update(v.amounts(prefix))
        return sorted(out)

    def plans(self):
        return sorted({pl for v in self.variants for pl in v.plans()}, reverse=True)


class FlowMixin:
    # ------------------------------------------------------------------ driver
    def run(self):
        """Advance until a decision is required (returns Decision) or the game ends (returns None)."""
        guard = 0
        while not self.over:
            guard += 1
            if guard > 200000:
                self._end_game(None, "step limit")
                break
            if self.pending is not None:
                return self.pending
            if self.vm_frames:
                d = run_vm(self)
                if d is not None:
                    return d
                continue
            if self.dirty:
                # CR 320.1 / 323.1: a pending cleanup (victory first) happens before the new pending
                # items are ordered and finalized
                self.dirty = False
                self._cleanup()
                continue
            if self.reorder_requests:
                d = self._ask_trigger_order()
                if d is not None:
                    return d
                continue
            if self.chain:
                self._advance_chain()
                continue
            if self.tasks:
                t = self.tasks.pop()
                self._task(*t)
                continue
            self._advance_phase()
        return None

    def choose(self, choice):
        """Answer the pending decision."""
        d = self.pending
        if d is None:
            raise RuntimeError("no pending decision")
        if choice not in d.options:
            raise ValueError(f"illegal choice {choice!r} for {d}")
        self.decision_count += 1
        self.history.append(choice)
        handler = d.info.get("handler")
        self.log("decision", player=d.player, dkind=d.kind, choice=d.labels[d.options.index(choice)])
        if handler:
            self.pending = None
            getattr(self, handler)(choice, d)
        else:
            resume_vm(self, choice)

    def _ask_trigger_order(self):
        """CR 383: the controller picks, one at a time, which of their simultaneous triggers resolves first."""
        req = self.reorder_requests[0]
        live = [i for i in req["items"] if any(it.id == i and not it.finalized for it in self.chain)]
        left = [i for i in live if i not in req["order"]]
        if len(left) <= 1:
            order = [i for i in req["order"] if i in live] + left
            self._apply_trigger_order(live, order)
            self.reorder_requests.pop(0)
            return None
        labels = []
        for i in left:
            it = next(x for x in self.chain if x.id == i)
            src = self.objects.get(it.uid)
            labels.append(f"{it.label}" + (f" ({src.defn.name})" if src is not None and src.defn.name not in it.label else ""))
        return self.ask(req["player"], "order_triggers", left, labels, "_on_trigger_order",
                        label="Choose which of your triggered abilities resolves first" if not req["order"] else "Which resolves next?")

    def _on_trigger_order(self, choice, d):
        self.reorder_requests[0]["order"].append(choice)

    def _apply_trigger_order(self, ids, order):
        """Put the group's items back into their chain slots so order[0] is on top (resolves first)."""
        slots = sorted(k for k, it in enumerate(self.chain) if it.id in ids)
        by_id = {it.id: it for it in self.chain if it.id in ids}
        for k, i in zip(reversed(slots), order):
            self.chain[k] = by_id[i]
        self.log("trigger_order", player=self.chain[slots[0]].controller if slots else None, order=list(order))

    def _ask_mulligan(self, p):
        """CR 117.1: choose up to two cards in hand. Options are every subset of size 0-2 (keep first)."""
        from itertools import combinations
        hand = list(self.players[p].hand)
        opts, seen = [], set()
        for o in [()] + [(u,) for u in hand] + list(combinations(hand, 2)):
            key = tuple(sorted(self.objects[u].defn.id for u in o))     # copies of a card give the same outcome
            if key not in seen:
                seen.add(key)
                opts.append(o)
        labels = ["Keep hand"] + ["Mulligan " + ", ".join(self.objects[u].defn.name for u in o) for o in opts[1:]]
        return self.ask(p, "mulligan", opts, labels, "_on_mulligan", label="Mulligan: set aside up to two cards")

    def _on_mulligan(self, choice, d):
        p = d.player
        ps = self.players[p]
        aside = [u for u in choice if u in ps.hand]
        for u in aside:                                   # CR 117.1: set aside
            ps.hand.remove(u)
            self.objects[u].zone = "aside"
            self.restruct()
        for _ in aside:                                   # CR 117.2: draw as many
            self._draw_raw(p)
        if aside:                                         # CR 117.3: recycle them (random order, CR 417.5)
            self.do_recycle(aside)
        self.log("mulligan", player=p, count=len(aside))
        self.mulligan_queue.pop(0)
        self.bump()

    def ask(self, player, kind, options, labels, handler, **info):
        info["handler"] = handler
        d = Decision(player, kind, options, labels=labels, info=info)
        self.pending = d
        return d

    def after_instruction(self):
        pass

    def on_frame_done(self, fr):
        tag = fr.tag
        if not tag:
            return
        if tag[0] == "finalize":
            self._finalized(tag[1])
        elif tag[0] == "resolve":
            self._resolved(tag[1])
        elif tag[0] == "cost":
            pass

    def _end_game(self, winner, reason):
        self.over = True
        self.winner = winner
        self.reason = reason
        self.log("game_over", winner=winner, reason=reason)

    # ------------------------------------------------------------------ state helpers
    @property
    def closed(self):
        return bool(self.chain)

    @property
    def neutral(self):
        return self.showdown is None and self.combat is None

    def legion_active(self, p, src):
        return any(u != src for u in self.players[p].played_this_turn)

    def _item_is_spell(self, item_id):
        for it in self.chain:
            if it.id == item_id:
                return it.kind == "spell"
        return False

    def next_player(self, p):
        return (p + 1) % len(self.players)

    # ------------------------------------------------------------------ phases (CR 314-317)
    def _advance_phase(self):
        ph = self.phase
        if ph == "mulligan":
            if self.mulligan_queue:
                self._ask_mulligan(self.mulligan_queue[0])
            else:
                self.phase = "start"
            return
        if ph in ("start", "next_turn"):
            self._start_turn()
        elif ph == "awaken":
            self._awaken()
            self.phase = "beginning"
            self.dirty = True
        elif ph == "beginning":
            # Beginning-phase triggers (e.g. Frozen Fortress) resolve before the phase ends (CR 315.2):
            # stay in "beginning" until the chain they opened is empty.
            if not self.turn_memo.get("beginning_emitted"):
                self.turn_memo["beginning_emitted"] = True
                self.emit("beginning_phase", player=self.turn_player)
            else:
                self.phase = "scoring"
            self.dirty = True
        elif ph == "scoring":
            for bf in self.battlefields:
                if bf.controller == self.turn_player:
                    self._score(self.turn_player, bf.idx, "hold")
            self.phase = "channel"
            self.dirty = True
        elif ph == "channel":
            n = 2
            if self.cfg["players"] == 2 and self.turn_player != self.first_player and self.turns_taken.get(self.turn_player) == 1:
                n = 3     # CR 487.7: the player going second channels an extra rune in their first Channel Phase
            if any(self.objects[src].location is not None and self.objects[src].location[0] == "bf"
                   for src, _ in self.rules("channel_only_one")):
                n = 1     # Sandstone Chimera: "players only channel 1 rune at the start of their Channel Phase"
            made = self.do_channel(self.turn_player, n)
            self.log("channel_phase", player=self.turn_player, n=n, made=len(made))
            self.phase = "draw"
            self.dirty = True
        elif ph == "draw":
            self.do_draw(self.turn_player, 1)
            self.phase = "main"
            self.empty_pools()
            self.emit("main_phase", player=self.turn_player)
            self.priority = self.turn_player
            self.dirty = True
        elif ph == "main":
            if self.turn > self.max_turns:
                # Not a rule of the game: a safety cap for simulations. Reported as unfinished, never as a draw.
                import sys
                print(f"WARNING: game stopped at the safety cap of {self.max_turns} turns (unfinished, not a draw)", file=sys.stderr)
                self._end_game(None, "turn limit")
                return
            if self.showdown is not None:
                self._showdown_decision()
            else:
                self._main_decision()
        elif ph == "ending":
            self.emit("ending_phase", player=self.turn_player)
            self.phase = "expiration"
            self.dirty = True
        elif ph == "expiration":
            self._expiration()
        else:
            raise RuntimeError(f"unknown phase {ph}")

    def _start_turn(self):
        if self.turn_queue:
            self.turn_player = self.turn_queue.pop(0)
        else:
            self.turn_player = self.next_player(self.turn_player)
        self.turn += 1
        self.scored = set()
        self.turn_memo = {}
        self.turns_taken[self.turn_player] = self.turns_taken.get(self.turn_player, 0) + 1
        for p in self.players:
            p.played_this_turn = []
            p.memo = {}
        self.log("turn", player=self.turn_player)
        self.phase = "awaken"
        self.priority, self.focus = None, None

    def _awaken(self):
        p = self.turn_player
        readied = []
        for u, o in list(self.objects.items()):
            if o.zone == "board" and o.controller == p and o.exhausted:
                if any(src == u for src, _ in self.rules("cant_ready")):
                    continue
                o.exhausted = False
                readied.append((u, o.location))
        self.bump()
        # CR 315.1.b / 416.3.a: this is the Ready action, so "When I become ready" (Jayce, Hammer in Hand; Fretful
        # Feline), "When you choose or ready me" (Irelia, Fervent) and "When you ready a friendly unit" (Pirate's
        # Haven) trigger for each object readied here
        for u, loc in readied:
            self.emit("ready", uid=u, player=p, loc=loc, ctx=None)
        self.emit("awaken", player=p)

    def _expiration(self):
        # Ending special cleanup (CR 317.2): heal, expire 'this turn' effects, empty pools, un-stun.
        self.chain_activity = 0
        for o in self.objects.values():
            if o.zone == "board":
                o.damage = 0
                o.temp = {k: v for k, v in o.temp.items() if not (isinstance(k, tuple) and k[0] == "damaged_by")}
                o.stunned = False
        for o in self.objects.values():
            # temporary control changes ("this turn"); before expire_mods drops the marker mods
            keep = []
            for m in o.mods:
                if m.kind == "control" and m.duration == "turn":
                    o.controller = m.value
                    if o.zone == "board" and o.location is not None and o.location[0] == "base":
                        o.location = ("base", o.controller)
                        self._sync_attachments(o)
                else:
                    keep.append(m)
            if len(keep) != len(o.mods):
                o.mods = keep
                self.restruct()
        self.expire_mods("turn")
        self.empty_pools()
        self.bump()
        self._cleanup()
        if self.chain:
            # triggers happened during expiration: FEPR them and repeat the expiration step
            return
        self.phase = "next_turn"

    # ------------------------------------------------------------------ cleanup (CR 323)
    def _cleanup(self):
        for _ in range(20):
            self.dirty = False
            self._cleanup_once()
            if not self.dirty or self.over or self.pending is not None:
                break
        self.dirty = False

    def _first_designation(self, u, want):
        """Record that unit u gained `want` in this combat; True only the first time (a unit that left the board
        and came back is a new object, CR 383.4.e.2.a)."""
        seen = self.combat.setdefault("designated", set())
        key = (u, self.objects[u].entered_stamp, want)
        if key in seen:
            return False
        seen.add(key)
        return True

    def _cleanup_once(self):
        v = self.victory_score()
        # 1. victory
        for p in self.players:
            if p.points >= v and all(p.points > q.points for q in self.players if q is not p):
                self._end_game(p.idx, "victory")
                return
        # 2. designations
        if self.combat is not None:
            bfl = ("bf", self.combat["bf"])
            for u, o in self.board_items():
                if o.zone != "board" or not self.is_unit(u):
                    continue
                if o.location == bfl:
                    want = "attacker" if o.controller == self.combat["attacker"] else ("defender" if o.controller == self.combat["defender"] else None)
                    if o.designation != want:
                        o.designation = want
                        self.bump()
                        # attack/defend triggers fire only the first time a unit gains the designation in a
                        # combat (CR 383.4.e.2.a / 383.4.f.2.a)
                        if want is not None and self._first_designation(u, want):
                            self.emit("attack" if want == "attacker" else "defend", uid=u, player=o.controller, loc=bfl)
                elif o.designation is not None:
                    o.designation = None
                    self.bump()
        # 3a. lethal damage
        dead = [u for u, o in self.board_items() if o.damage > 0 and self.is_unit(u) and self.lethal_damage(u)]
        if dead:
            self.do_kill(dead, None, by="damage")
        # 4. lose control of empty battlefields (open state, no showdown/combat there)
        if not self.closed:
            for bf in self.battlefields:
                if bf.controller is not None and not self.units_at(("bf", bf.idx), bf.controller):
                    if self._showdown_at(bf.idx):
                        continue
                    self.log("lose_control", bf=bf.idx, player=bf.controller)
                    self.set_bf_controller(bf.idx, None)
                    self.dirty = True
        self._check_static_might_reductions()
        self._check_becomes_mighty()
        self._end_control_durations()
        self._end_bound_legends()
        # 5. recalls
        for u, o in self.board_items():
            if o.zone != "board" or o.location is None:
                continue
            if o.location[0] == "bf":
                c = self.chars(u)
                if "gear" in c.types and "unit" not in c.types and o.attached_to is None and not c.keywords.get("deploy"):
                    self.do_recall(u)
            elif o.location[0] == "base" and o.location[1] != o.controller and o.attached_to is None:
                self.do_recall(u)
        for bf in self.battlefields:
            for k, u in list(bf.facedown.items()):
                p = k if isinstance(k, int) else k[0]
                if bf.controller != p:
                    self.log("hidden_lost", uid=u, bf=bf.idx)
                    self._to_zone(self.objects[u], "trash")
        # 6/7. stage showdowns and combats
        for bf in self.battlefields:
            loc = ("bf", bf.idx)
            if bf.contested_by is not None and not self._combat_at(bf.idx):
                players = {self.objects[u].controller for u in self.units_at(loc)}
                if bf.contested_by in players:
                    bf.staged_showdown = True
                    bf.staged_combat = len(players) >= 2
                else:
                    bf.staged_showdown = bf.staged_combat = False
            else:
                bf.staged_showdown = bf.staged_combat = False
            # 8. remove contested where the contester has no units and nothing ongoing
            if bf.contested_by is not None and not self.units_at(loc, bf.contested_by) and not self._showdown_at(bf.idx):
                bf.contested_by = None
                bf.staged_showdown = bf.staged_combat = False
                # 8a: units at an uncontrolled battlefield re-apply contested
                others = {self.objects[u].controller for u in self.units_at(loc)} - {bf.controller}
                if others and bf.controller is None:
                    bf.contested_by = sorted(others)[0]
                    self.dirty = True
        # 9/10. begin a showdown / combat when in a neutral open state
        if not self.closed and self.neutral and self.phase == "main":
            staged = [bf.idx for bf in self.battlefields if bf.staged_showdown or bf.staged_combat]
            if staged:
                if len(staged) == 1:
                    self._begin_showdown(staged[0])
                else:
                    self.ask(self.turn_player, "choose_showdown", staged, [self.loc_name(("bf", i)) for i in staged], "_on_choose_showdown")
        # 10a. a non-combat showdown becomes a combat showdown when combat gets staged there
        if self.showdown is not None and not self.showdown["combat"]:
            bf = self.battlefields[self.showdown["bf"]]
            players = {self.objects[u].controller for u in self.units_at(("bf", bf.idx))}
            if len(players) >= 2 and self.combat is None:
                self._open_combat(bf.idx, existing_showdown=True)

    def _on_choose_showdown(self, choice, d):
        self._begin_showdown(choice)

    def _showdown_at(self, i):
        return (self.showdown is not None and self.showdown["bf"] == i) or (self.combat is not None and self.combat["bf"] == i)

    def _combat_at(self, i):
        return self.combat is not None and self.combat["bf"] == i

    # ------------------------------------------------------------------ showdowns (CR 341-348)
    def _begin_showdown(self, i):
        bf = self.battlefields[i]
        bf.staged_showdown = False
        loc = ("bf", i)
        players = {self.objects[u].controller for u in self.units_at(loc)}
        opener = bf.contested_by if bf.contested_by is not None else self.turn_player
        self.showdown = {"bf": i, "combat": False, "opened_by": opener, "passes": 0, "trigger_chain": False, "acted": False}
        self.focus = opener
        self.priority = opener
        self.log("showdown", bf=i, player=opener)
        if len(players) >= 2:
            bf.staged_combat = False
            self._open_combat(i, existing_showdown=False)
        else:
            self.emit("showdown_start", loc=loc, player=opener, bf=i)
            if self.chain:
                self.showdown["trigger_chain"] = True
        self.dirty = True

    def _open_combat(self, i, existing_showdown):
        bf = self.battlefields[i]
        loc = ("bf", i)
        attacker = bf.contested_by if bf.contested_by is not None else self.turn_player
        players = {self.objects[u].controller for u in self.units_at(loc)}
        others = players - {attacker}
        defender = sorted(others)[0] if others else self.opponent(attacker)
        self.combat = {"bf": i, "attacker": attacker, "defender": defender, "step": "showdown"}
        self.showdown["combat"] = True
        bf.staged_combat = bf.staged_showdown = False
        self.log("combat", bf=i, attacker=attacker, defender=defender)
        if not existing_showdown:
            self.focus = attacker
            self.priority = attacker
            self.emit("showdown_start", loc=loc, player=attacker, bf=i)
        self.emit("combat_start", loc=loc, attacker=attacker, defender=defender, bf=i)
        for u in self.units_at(loc):
            o = self.objects[u]
            o.designation = "attacker" if o.controller == attacker else "defender"
            self._first_designation(u, o.designation)
        self.bump()
        # attack / defend triggers: attacker's first (CR 466.2.d.1)
        for u in self.units_at(loc, attacker):
            self.emit("attack", uid=u, player=attacker, loc=loc)
        for u in self.units_at(loc, defender):
            self.emit("defend", uid=u, player=defender, loc=loc)
        if self.chain:
            self.showdown["trigger_chain"] = True
        self.dirty = True

    def _showdown_decision(self):
        p = self.focus
        acts = self.legal_actions(p)
        self.priority = p
        self.ask(p, "action", acts, [self.action_label(a) for a in acts], "_on_action", showdown=True)

    def _close_showdown(self):
        sd = self.showdown
        i = sd["bf"]
        self.log("showdown_close", bf=i)
        if sd["combat"]:
            self.combat["step"] = "damage"
            self.tasks.append(("combat_end",))
            self.tasks.append(("combat_control",))
            self.tasks.append(("combat_result",))
            self.tasks.append(("combat_cleanup",))
            self.tasks.append(("combat_damage",))
            self.showdown = None
            self.focus = None
            self.priority = None
        else:
            bf = self.battlefields[i]
            players = {self.objects[u].controller for u in self.units_at(("bf", i))}
            self.showdown = None
            self.focus = None
            if len(players) == 1:
                p = players.pop()
                if bf.controller != p:
                    self._establish_control(i, p)
            bf.contested_by = None
            self.priority = self.turn_player
            self.dirty = True

    def _establish_control(self, i, p):
        bf = self.battlefields[i]
        prev = bf.controller
        self.conquered_from = prev           # read by "when I conquer an open battlefield" (Yone)
        self.set_bf_controller(i, p)
        self.log("control", bf=i, player=p, prev=prev)
        self.bump()
        self._score(p, i, "conquer")

    # ------------------------------------------------------------------ scoring (CR 469-473)
    def _score(self, p, i, how):
        if (p, i) in self.scored:
            return
        here = ("bf", i)
        for src, n in self.rules("no_score_before_turn"):
            if self.objects[src].place == here and self.turns_taken.get(p, 0) < n:
                self.log("cant_score", player=p, bf=i, why=self.objects[src].defn.name)
                return          # e.g. Forgotten Monument: no point and no conquer/hold event
        self.scored.add((p, i))
        ps = self.players[p]
        v = self.victory_score()
        loc = ("bf", i)
        units = tuple(self.units_at(loc, p))
        if how == "conquer":
            self.turn_memo.setdefault(("conquered_bfs", p), set()).add(i)     # "each battlefield you've conquered this turn"
            for u in units:
                self.objects[u].temp[("conquered", self.turn)] = True        # "if I didn't conquer this turn"
        if how == "conquer" and ps.points >= v - 1:
            if all((p, b.idx) in self.scored for b in self.battlefields):
                self.gain_points(p, 1, "conquer")
            else:
                self.log("final_point_draw", player=p)
                self.do_draw(p, 1)
        else:
            before = ps.points
            self.gain_points(p, 1, how)
            if how == "hold" and ps.points > before:     # Needlessly Large Yordle: "points you scored from holding"
                self.turn_memo[("hold_points", p)] = self.turn_memo.get(("hold_points", p), 0) + ps.points - before
        self.log("score", player=p, bf=i, how=how)
        self.emit(how, player=p, loc=loc, bf=i, units=units)
        self.emit("score", player=p, loc=loc, bf=i, units=units, how=how)
        self.dirty = True

    # ------------------------------------------------------------------ combat steps (CR 465-468)
    def _task(self, name, *args):
        getattr(self, "_task_" + name)(*args)

    def _task_combat_damage(self):
        c = self.combat
        loc = ("bf", c["bf"])
        att = [u for u in self.units_at(loc, c["attacker"]) if self.objects[u].designation == "attacker"]
        dfn = [u for u in self.units_at(loc, c["defender"]) if self.objects[u].designation == "defender"]
        if not att or not dfn:
            return
        self.combat["step"] = "damage"
        self.combat["assign"] = {}
        a_total = sum((self.chars(u).might or 0) for u in att if not self.objects[u].stunned and not self.no_combat_damage(u))
        d_total = sum((self.chars(u).might or 0) for u in dfn if not self.objects[u].stunned and not self.no_combat_damage(u))
        self.combat["totals"] = (a_total, d_total)
        self.tasks.append(("combat_deal",))
        self.tasks.append(("assign", c["defender"], tuple(att), d_total))
        self.tasks.append(("assign", c["attacker"], tuple(dfn), a_total))

    ASSIGN_FLAT_LIMIT = 64          # more legal assignments than this: ask one unit at a time instead of one flat list

    def _task_assign(self, player, targets, total):
        targets = [u for u in targets if u in self.objects and self.objects[u].zone == "board"]
        if total <= 0 or not targets:
            return
        self.combat["assign_targets_" + str(player)] = tuple(targets)
        dp = self._assign_dp(targets, total, player)
        if dp.count() > self.ASSIGN_FLAT_LIMIT:
            # Exact, but the flat list would be huge (a big Might total over many units splits its excess in
            # C(excess + units - 1, units - 1) ways): the player picks each unit's amount in turn, and every amount
            # offered still has a legal completion, so the reachable assignments are exactly the legal ones.
            self.tasks.append(("assign_step", player, tuple(targets), total, ()))
            return
        plans = dp.plans()
        if len(plans) == 1:
            self.combat["assign"][player] = plans[0]
            return
        labels = [", ".join(f"{self.label(u)}:{a}" for u, a in zip(targets, pl) if a) for pl in plans]
        self.ask(player, "assign_damage", plans, labels, "_on_assign", targets=tuple(targets))

    def _on_assign(self, choice, d):
        self.combat["assign"][d.player] = choice
        self.combat["assign_targets_" + str(d.player)] = d.info["targets"]

    def _task_assign_step(self, player, targets, total, prefix):
        targets = list(targets)
        dp = self._assign_dp(targets, total, player)
        prefix = tuple(prefix)
        while len(prefix) < len(targets):
            opts = dp.amounts(prefix)
            if len(opts) == 1:
                prefix += (opts[0],)
                continue
            u = targets[len(prefix)]
            need = dp.info[len(prefix)][0]
            left = total - sum(prefix)
            labels = [f"{self.label(u)}:{a}" + (" (lethal)" if need is not None and a >= need else "") for a in opts]
            self.ask(player, "assign_damage_step", opts, labels, "_on_assign_step", targets=tuple(targets), total=total,
                     prefix=prefix, unit=u, left=left,
                     label=f"Combat damage: how much of the {left} left goes to {self.label(u)}?",
                     done=[(self.label(x), a) for x, a in zip(targets, prefix)])
            return
        self.combat["assign"][player] = prefix
        self.combat["assign_targets_" + str(player)] = tuple(targets)

    def _on_assign_step(self, choice, d):
        self.tasks.append(("assign_step", d.player, d.info["targets"], d.info["total"], d.info["prefix"] + (choice,)))

    def _lethal_need(self, u, total, by):
        """CR 467.2.c.4.a / 467.2.c.5: the least assigned amount that would be lethal once replacement effects and
        prevention apply to it. None when no amount would be lethal (e.g. 'I don't take damage')."""
        o = self.objects[u]
        might = self.chars(u).might or 0
        prevent = sum(m.value for m in o.mods if m.kind == "prevent" and m.value > 0)
        bound = max(total, might - o.damage) + prevent + 1 + (1 if any(m.kind == "prevent_next" for m in o.mods) else 0)
        for a in range(1, bound + 1):
            dealt = self.preview_damage(u, a, by, combat=True)
            if dealt > 0 and (o.damage + dealt >= might or self._any_damage_kills(u, by)):
                return a
        return None

    def _any_damage_kills(self, u, by):
        o = self.objects[u]
        return any(not self.is_friendly(self.objects[src].controller, o.controller) and self.objects[src].controller == by
                   for src, _ in self.rules("any_damage_kills_enemies"))

    def _assign_dp(self, targets, total, player=None):
        """The legal combat damage assignments (CR 467.2.c) as a counting automaton over the targets in order."""
        last = {src for src, _ in self.rules("assigned_damage_last")}
        info = []
        for u in targets:
            c = self.chars(u)
            need = self._lethal_need(u, total, player)      # None: no amount is lethal (CR 467.2.c.6 "if able")
            tank = c.keywords.get("tank") and not any(
                self.objects[src].controller == player and self.objects[src].location == self.objects[u].location
                for src, _ in self.rules("ignore_tank_here"))          # Dune Surfer
            back = bool(c.keywords.get("backline") or u in last)
            # Tank and Backline both: the assigner fulfils one of them (CR 467.2.c.8), each unit separately (467.2.c.9)
            info.append((need, (0, 2) if tank and back else (0 if tank else (2 if back else 1))))
        if not any(isinstance(p, tuple) for _, p in info):
            return DamageAssignments(info, total)
        picks = itertools.product(*[p if isinstance(p, tuple) else (p,) for _, p in info])
        return DamageAssignmentsAny([DamageAssignments([(n, p) for (n, _), p in zip(info, pk)], total) for pk in picks])

    def _damage_plans(self, targets, total, player=None):
        """Every legal combat damage assignment, as plan tuples in target order (see DamageAssignments)."""
        return self._assign_dp(targets, total, player).plans()

    def _task_combat_deal(self):
        c = self.combat
        loc = ("bf", c["bf"])
        att = [u for u in self.units_at(loc, c["attacker"])]
        dfn = [u for u in self.units_at(loc, c["defender"])]
        a_plan = c["assign"].get(c["attacker"])
        d_plan = c["assign"].get(c["defender"])
        a_targets = c.get("assign_targets_" + str(c["attacker"])) or tuple(dfn)
        d_targets = c.get("assign_targets_" + str(c["defender"])) or tuple(att)
        dealt = []
        ctx_a = Context(c["attacker"], None, here=loc)
        ctx_d = Context(c["defender"], None, here=loc)
        if a_plan:
            for u, amt in zip(a_targets, a_plan):
                if amt:
                    dealt.append((ctx_a, u, amt))
        if d_plan:
            for u, amt in zip(d_targets, d_plan):
                if amt:
                    dealt.append((ctx_d, u, amt))
        self.log("combat_damage", bf=c["bf"], assignments=[(self.label(u), a) for _, u, a in dealt])
        for q in (c["attacker"], c["defender"]):
            self.turn_memo[("combat_excess", q)] = 0       # excess assigned in this combat (Sivir, Ambitious)
        for ctx, u, amt in dealt:
            hp = (self.chars(u).might or 0) - self.objects[u].damage
            excess = max(0, amt - max(0, hp))
            if excess:
                key = ("excess_damage", ctx.controller)
                self.turn_memo[key] = self.turn_memo.get(key, 0) + excess
                key = ("combat_excess", ctx.controller)
                self.turn_memo[key] = self.turn_memo.get(key, 0) + excess
            self.do_deal([u], amt, ctx, source_uid=None, combat=True)
        self.dirty = True

    def _task_combat_cleanup(self):
        c = self.combat
        loc = ("bf", c["bf"])
        self._cleanup()
        for o in self.objects.values():
            if o.zone == "board":
                o.damage = 0
                o.temp = {k: v for k, v in o.temp.items() if not (isinstance(k, tuple) and k[0] == "damaged_by")}
        self.bump()
        dfn = self.units_at(loc, c["defender"])
        att = self.units_at(loc, c["attacker"])
        if dfn and att:
            # Symbol of the Solari: "If a combat where you are the attacker ends in a tie, recall ALL units instead."
            everyone = bool(self.rules("attacker_tie_recall_all", player=c["attacker"]))
            for u in (att + dfn if everyone else att):
                self.do_recall(u)
            c["recalled"] = True
        self.dirty = True

    def _task_combat_result(self):
        c = self.combat
        loc = ("bf", c["bf"])
        att = self.units_at(loc, c["attacker"])
        dfn = self.units_at(loc, c["defender"])
        winner = loser = None
        if att and not dfn:
            winner, loser = c["attacker"], c["defender"]
        elif dfn and not att:
            winner, loser = c["defender"], c["attacker"]
        c["winner"], c["loser"] = winner, loser
        if c.get("recalled") or (att and dfn):
            self.log("combat_no_result", bf=c["bf"])
            if att and dfn:
                bf = self.battlefields[c["bf"]]
                bf.staged_showdown = bf.staged_combat = True
        else:
            self.log("combat_result", bf=c["bf"], winner=winner, loser=loser)
        self.emit("combat_result", loc=loc, winner=winner, loser=loser, bf=c["bf"],
                  winners=tuple(self.units_at(loc, winner)) if winner is not None else (),
                  losers=(), player=winner)
        self.dirty = True

    def _task_combat_control(self):
        c = self.combat
        i = c["bf"]
        bf = self.battlefields[i]
        loc = ("bf", i)
        if bf.staged_combat or bf.staged_showdown:
            return
        players = {self.objects[u].controller for u in self.units_at(loc)}
        if len(players) == 1:
            p = players.pop()
            if bf.controller != p:
                self._establish_control(i, p)
        elif not players:
            self.set_bf_controller(i, None)
        bf.contested_by = None
        self.dirty = True

    def _task_combat_end(self):
        c = self.combat
        loc = ("bf", c["bf"])
        # "When a combat that I was in ends" (Mournful Witness, Affectionate Poro): every unit that had a combat
        # designation in this combat and is still the same object on the board, wherever it is now (attackers
        # recalled after a tie were in the combat too, CR 740.2.c)
        was_in = {(u, stamp) for u, stamp, _ in c.get("designated", ())}
        survivors = tuple(u for u in self.units_at(loc)) + tuple(
            u for u, o in self.objects.items() if o.zone == "board" and o.location != loc and (u, o.entered_stamp) in was_in)
        for o in self.objects.values():
            o.designation = None
        self.expire_mods("combat")
        self.combat = None
        self.showdown = None
        self.focus = None
        self.priority = self.turn_player
        self.bump()
        self.log("combat_end", bf=loc[1])
        self.emit("combat_end", loc=loc, survivors=survivors, bf=loc[1], winner=c.get("winner"))
        self.dirty = True

    # ------------------------------------------------------------------ chain (CR 327-340)
    def _advance_chain(self):
        pend = [it for it in self.chain if not it.finalized]
        if pend:
            it = pend[0]
            self._finalize(it)
            return
        # all finalized: Execute / Pass
        if self.priority is None:
            self.priority = self.chain[-1].controller
            self.passes = 0
        if self.passes >= len(self.players):
            self.passes = 0
            self._resolve_top()
            return
        acts = self.legal_actions(self.priority)
        if len(acts) == 1:
            self._on_action(acts[0], None)
            return
        self.ask(self.priority, "action", acts, [self.action_label(a) for a in acts], "_on_action", chain=True)

    def _finalize(self, it):
        ctx = it.ctx
        pre = []
        show = []
        if it.kind in ("spell", "unit", "gear") and (self.objects[it.uid].defn.keywords or {}).get("show_off"):
            req = showoff_requirement(self.objects[it.uid].defn.text)
            if req is None:
                raise NotImplementedError("unparsed Show Off requirement: " + self.objects[it.uid].defn.name)
            show = [_ShowOff(it.id, req)]
        if it.kind in ("spell", "unit", "gear"):
            for ab in self._abilities_of(it.uid, self.objects[it.uid]):
                if isinstance(ab, PlayPermission) and ab.perm == "as_play":
                    show = show + relocate(compile_effect(ab.value), len(show))
                if isinstance(ab, PlayPermission) and ab.perm == "additional_cost" and (ab.cond is None or ab.cond(self, it.uid)):
                    req, ins, mandatory = ab.value
                    if self._resource_additional_cost(ab) is not None:
                        pass                      # paid with the rest of the cost in _FinalizeCosts (CR 357)
                    elif mandatory:
                        pre += list(ins) + [SetVar("__add", True), Do(lambda g, c: c.paid.__setitem__("add", True))]
                    else:
                        # non-resource costs (exhaust a unit, spend a buff) set __addok False when they could not be done
                        outs = [i.out for i in ins if isinstance(i, PayResources)]
                        pre.append(May([SetVar("__optional_cost", True)] + list(ins) + [SetVar("__optional_cost", False),
                                        Do(lambda g, c, outs=tuple(outs): c.paid.__setitem__(
                                            "add", all(c.vars.get(o) for o in outs) and c.vars.get("__addok", True)))],
                                       label="pay the additional cost", out="__addq"))
                if isinstance(ab, PlayPermission) and ab.perm == "variable_reduce":
                    pre += self._variable_reduce_code(it, ab)
                if isinstance(ab, PlayPermission) and ab.perm == "free_with_cost":
                    # "As you play this, you may <cost> as an additional cost. If you do, ignore this spell's cost."
                    can, ins = ab.value
                    if can(self, it.controller, it.uid):
                        body = list(ins) + [SetVar("__ignore_cost", True), Do(lambda g, c: c.paid.__setitem__("add", True))]
                        e0, pw0 = (it.cost or {}).get("energy", 0), (it.cost or {}).get("power", [])
                        if not self.can_pay(it.controller, e0, pw0, purpose=self.item_purpose(it)):
                            pre += body           # only playable this way (CR 357: the play must be legal)
                        else:
                            pre.append(May(body, label=ab.label or "pay the alternative cost", out="__freeq"))
        if it.kind == "spell":
            pre += self._exhaust_reducer_code(it)
        code = show + relocate(compile_effect(pre), len(show))      # compiled pieces: shift their jump targets
        tcode = list(it.target_code or [])
        code = code + relocate(tcode, len(code)) + [_FinalizeCosts(it.id)]
        if tcode and self._optional_costs_include_repeat(it):
            # CR 820.2: each additional execution gets its own choices (they may differ from the first)
            code = code + [_SnapChoices(0), _SkipUnlessRepeat(len(code) + 4 + len(tcode))]
            code = code + relocate(tcode, len(code)) + [_RepeatDeflect(it.id), _SnapChoices(1)]
        self.vm_frames.append(Frame(code, ctx, tag=("finalize", it.id)))

    # "As you play me, you may <do X> any number of times as an additional cost. Reduce my cost by [D] for each."
    # (Kraken Hunter, Commander Ledros). value = (candidates(g, p, uid) -> uids, domain, act(g, ctx, uid)).
    def _variable_reduce_perm(self, uid):
        for ab in self._abilities_of(uid, self.objects[uid]):
            if isinstance(ab, PlayPermission) and ab.perm == "variable_reduce":
                return ab
        return None

    @staticmethod
    def _reduce_power(pw, dom, k):
        pw = list(pw)
        for _ in range(k):
            if dom in pw:
                pw.remove(dom)
            else:
                m = next((x for x in pw if "|" in x and dom in x.split("|")), None)
                if m is not None:
                    pw.remove(m)
        return pw

    def _variable_reduce_min(self, p, uid, e, pw, purpose):
        """Fewest cost actions that make the play affordable (None if even all of them don't)."""
        ab = self._variable_reduce_perm(uid)
        if ab is None:
            return 0 if self.can_pay(p, e, pw, purpose=purpose) else None
        cands, dom, _ = ab.value
        n = len(cands(self, p, uid))
        for k in range(0, n + 1):
            if self.can_pay(p, e, self._reduce_power(pw, dom, k), purpose=purpose):
                return k
        return None

    def _variable_reduce_code(self, it, ab):
        cands, dom, act = ab.value
        p, uid = it.controller, it.uid
        opts = lambda g, c: list(cands(g, p, uid))

        def need(g, c):
            cost = it.cost or {"energy": 0, "power": []}
            k = g._variable_reduce_min(p, uid, cost["energy"], cost["power"], g.item_purpose(it))
            return k or 0

        def apply(g, c):
            chosen = [u for u in (c.vars.get("__vr") or ()) if u in g.objects]
            for u in chosen:
                act(g, c, u)
            if it.cost is not None and chosen:
                it.cost = dict(it.cost, power=g._reduce_power(it.cost["power"], dom, len(chosen)))
            if chosen:
                c.paid["add"] = True
        return [ChooseFromList(opts, out="__vr", n=lambda g, c: len(opts(g, c)), up_to=True, min_n=need,
                               label=ab.label or "additional cost"),
                Do(apply, label="pay the additional cost")]

    def _trash_play_perm(self, uid):
        """'You may play me from your trash for COST' (PlayPermission 'from_trash', alt_cost, cond)."""
        o = self.objects[uid]
        for ab in self._abilities_of(uid, o):
            if isinstance(ab, PlayPermission) and ab.perm == "from_trash" and (ab.cond is None or ab.cond(self, uid)):
                return ab
        return None

    def _free_with_cost(self, p, uid):
        for ab in self._abilities_of(uid, self.objects[uid]):
            if isinstance(ab, PlayPermission) and ab.perm == "free_with_cost" and ab.value[0](self, p, uid):
                return True
        return False

    def _exhaust_reducers(self, p):
        """Starry-Eyed Songstress: ready sources with rule 'spell_reduce_exhaust_units' (n units, energy) that p can use now."""
        out = []
        for src, v in self.rules("spell_reduce_exhaust_units", player=p):
            n, _ = v
            o = self.objects[src]
            ready_units = [u for u, x in self.board_items() if x.controller == p and not x.exhausted
                           and u != src and "unit" in self.chars(u).types]
            if not o.exhausted and len(ready_units) >= n:
                out.append((src, v))
        return out

    def _exhaust_reducer_code(self, it):
        """The optional cost is offered as a yes/no; when the spell was only affordable with it, it is paid without asking
        (declining would make the play illegal, CR 357)."""
        p = it.controller
        code = []
        e, pw = it.cost["energy"], it.cost["power"]
        must = not self.can_pay(p, e, pw, purpose=self.item_purpose(it))
        for src, (n, energy) in self._exhaust_reducers(p):
            sel = Sel("unit", side="friendly", pred=lambda g, c, u, src=src: u != src and not g.objects[u].exhausted)
            body = [Choose(sel, out=f"__exr{src}", n=n, targeted=False),
                    Do(lambda g, c, src=src: g.do_exhaust(src, c)),
                    Exhaust(Ref(f"__exr{src}")),
                    Do(lambda g, c, energy=energy: c.vars.__setitem__("__cost_reduce", c.vars.get("__cost_reduce", 0) + energy))]
            if must:
                code += body
                must = False
            else:
                code.append(May(body, out=f"__exq{src}",
                                label=f"exhaust {self.objects[src].defn.name} and {n} friendly units to reduce the cost by [{energy}]"))
        return code

    def _finalized(self, item_id):
        it = next((x for x in self.chain if x.id == item_id), None)
        if it is None:
            return
        ctx = it.ctx
        it.finalized = True
        self.log("finalized", item=it.id, label=it.label, controller=it.controller)
        targets = [u for u in self._target_uids(ctx) if u is not None]
        snaps = ctx.vars.get("__rep_choices") or {}
        if ctx.repeat and snaps:
            # Repeat (CR 820.2): every execution's choices were made while playing it; all of them are chosen
            targets = []
            for k in sorted(snaps):
                saved = ctx.vars
                ctx.vars = dict(saved, **snaps[k])
                targets += [u for u in self._target_uids(ctx) if u is not None]
                ctx.vars = saved
        if targets:
            # one event per chosen object: "When you choose a friendly unit" triggers once for each friendly unit a
            # spell chooses (only "the Nth time" triggers collapse simultaneous conditions, CR 383.1.b)
            for u in dict.fromkeys(targets):
                self.emit("target", targets=(u,), all_targets=tuple(targets), player=it.controller, item=it.id,
                          item_kind=it.kind, ctx=ctx)
            src = self.objects.get(it.uid) if it.uid is not None else None
            by_unit_ability = it.kind in ("ability", "trigger", "reflexive") and src is not None and \
                "unit" in (self.chars(it.uid).types if src.zone == "board" else src.defn.types)
            enemy = [u for u in targets if u in self.objects and self.objects[u].zone == "board"
                     and self.objects[u].controller is not None and not self.is_friendly(self.objects[u].controller, it.controller)
                     and ({"unit", "gear"} & set(self.chars(u).types))]
            if enemy and (it.kind == "spell" or by_unit_ability):      # Ezreal: "chosen enemy units and/or gear"
                k = ("chose_enemy", it.controller)
                self.turn_memo[k] = self.turn_memo.get(k, 0) + 1
        if it.kind == "spell" and self._energy_spent(it) >= 4:
            self.turn_memo[("spell_spent_4", it.controller)] = True      # Jhin, Meticulous Killer
        if it.kind in ("spell", "unit", "gear"):
            self.players[it.controller].played_this_turn.append(it.uid)
            pl = ctx.target_bf or ctx.vars.get("__loc")
            if it.kind in ("unit", "gear") and pl is not None and pl[0] == "bf":
                self.turn_memo[("played_to_bf", it.controller)] = True      # Hold 'Em
            o = self.objects[it.uid]
            if it.kind == "spell":
                # Ravenborn Tome: "The next spell you play this turn deals 1 Bonus Damage": used up by this spell even if
                # it deals nothing, and added to each of its Deal actions (CR 715)
                extra = sum(t.get("amount", 0) for t in self.consume_turn_effects("bonus_damage", player=it.controller))
                if extra:
                    ctx.vars["__spell_bonus"] = ctx.vars.get("__spell_bonus", 0) + extra
            ev = dict(uid=it.uid, player=it.controller, card_type=it.kind, loc=ctx.vars.get("__loc") or ctx.target_bf,
                      from_zone=ctx.played_from, item=it.id, energy=self._energy_spent(it), paid=dict(ctx.paid),
                      nth=len(self.players[it.controller].played_this_turn))
            if it.kind == "spell":
                # CR 420.4.a: "when you play" triggers trigger when the act of playing is completed by the card's
                # resolution; a countered spell never triggers them (420.4.a.1). Units and gear resolve on finalizing.
                ctx.vars["__play_ev"] = ev
            else:
                self.emit("play", ctx=ctx, **ev)
        elif it.kind == "ability":
            self.emit("activate", uid=it.uid, player=it.controller, energy=(it.cost or {}).get("energy", 0), item=it.id, ctx=ctx)
        self.priority = it.controller
        self.passes = 0
        self.dirty = True
        if it.kind in ("spell", "unit", "gear") and self.showdown is not None:
            self.showdown["acted"] = True      # CR 347.1.b / 340.2.a: playing any card passes Focus when the chain closes
        if it.resolves_now:
            self._resolve_item(it)            # CR 337.2: units, gear and Add abilities resolve on finalizing
            return

    def _target_uids(self, ctx):
        out = []
        for name, sel in ctx.vars.get("__targets", []):
            v = ctx.vars.get(name)
            if isinstance(v, tuple):
                out.extend(v)
            else:
                out.append(v)
        return out

    def current_targets(self, ctx):
        """The item's chosen targets that are still the same objects: a target that changed to or from a non-board
        zone is no longer counted as chosen (CR 359.3.e.4, 359.3.e.9.a); a mistargeted one still on the board is."""
        chosen = ctx.vars.get("__chosen") or {}
        out = []
        for name, sel in ctx.vars.get("__targets", []):
            v = ctx.vars.get(name)
            stamps = (chosen.get(name) or {}).get("stamps") or {}
            for u in (v if isinstance(v, tuple) else (v,)):
                if not isinstance(u, int) or u not in self.objects:
                    continue
                if u in stamps and self.objects[u].entered_stamp != stamps[u]:
                    continue
                out.append(u)
        return out

    def _deflect_total(self, it, ctx):
        total = 0
        if it.uid is not None and it.uid in self.objects and any(
                isinstance(ab, PlayPermission) and ab.perm == "ignore_deflect" for ab in self._abilities_of(it.uid, self.objects[it.uid])):
            return 0                 # Decree of Insight: "Ignore [Deflect] while paying this spell's cost"
        for u in self._target_uids(ctx):
            o = self.objects.get(u)
            if o is None or o.zone != "board" or self.is_friendly(o.controller, ctx.controller):
                continue
            total += self.keyword_value(u, "deflect")
        return total

    def _optional_costs_raw(self, it, ctx):
        """Optional additional costs for a chain item before Ezreal's reduction: [(name, (energy, power, label))]."""
        out = []
        if it.kind == "unit":
            c = self.chars(it.uid)
            granted = ctx.played_from not in ("hand", None) and \
                bool(self.rules("accelerate_if_not_from_hand", player=it.controller))      # Rek'Sai, Breacher
            if c.keywords.get("accelerate") or granted or ctx.vars.get("__granted_accel"):
                dom = [payment.own_power(c.domains)]          # CR 805.1.b.1-2
                out.append(("accelerate", (1, dom, "Accelerate [1][C]")))
        if it.kind in ("spell", "unit", "gear"):
            for ab in self._abilities_of(it.uid, self.objects[it.uid]):
                pr = self._resource_additional_cost(ab)
                if pr is not None and (ab.cond is None or ab.cond(self, it.uid)):
                    e, pw = val(self, ctx, pr.energy), [val(self, ctx, d) for d in pr.power]
                    lbl = (f"[{e}]" if e else "") + "".join(f"[{'/'.join(x.capitalize() for x in d.split('|')) if d != 'any' else 'A'}]" for d in pw)
                    out.append(("add", (e, pw, f"the additional cost {lbl}")))
                    break
        rc = getattr(it.ability, "repeat_cost", None) if it.ability is not None else None
        if it.kind == "spell":
            rc = self.defn_of(it.uid).keywords.get("repeat_cost")
        if rc:
            # Marai Spire: "friendly [Repeat] costs cost [1] less" (generic energy only)
            red = sum(int(v) for _, v in self.rules("repeat_cost_reduce", player=it.controller))
            out.append(("repeat", (max(0, rc[0] - red), list(rc[1]), f"Repeat {rc}")))
        gr = it.ctx.vars.get("__granted_repeat") if (it.kind == "spell" and it.ctx is not None) else None
        if gr:                                   # Temporal Portal: "[Repeat] equal to its cost"
            red = sum(int(v) for _, v in self.rules("repeat_cost_reduce", player=it.controller))
            out.append(("repeat_granted", (max(0, gr[0] - red), list(gr[1]), f"Repeat {gr}")))
        return out

    @staticmethod
    def _resource_additional_cost(ab):
        """The PayResources of an optional "pay [X] as an additional cost" (Crescent Guardian, Sea Monkey, Rampage),
        or None. Such a cost is added to the total cost and paid with it (CR 357), so it is only offered when the
        whole cost can be paid, and Ezreal, Prodigy reduces it."""
        if not (isinstance(ab, PlayPermission) and ab.perm == "additional_cost"):
            return None
        req, ins, mandatory = ab.value
        if mandatory or req is not None or len(ins) != 1 or not isinstance(ins[0], PayResources):
            return None
        return ins[0]

    def _optional_costs(self, it, ctx):
        """Optional additional costs for a chain item: [(name, (energy, power, label))], reduced (first variant)."""
        return [(n, (*self.reduce_optional_cost(it.controller, e, p), lbl)) for n, (e, p, lbl) in self._optional_costs_raw(it, ctx)]

    def reduce_optional_cost(self, p, energy, power):
        """Ezreal, Prodigy: "Optional additional costs you pay cost [1] or [A] less" (once per such source).
        The first of optional_cost_variants (a power symbol when there is one); the payer may pick any variant."""
        return self.optional_cost_variants(p, energy, power)[0]

    def optional_cost_variants(self, p, energy, power):
        """Every cost an optional additional cost can come to under Ezreal, Prodigy's "[1] or [A] less" (the player
        chooses per source, so a [1][C] Accelerate can cost [C] or [1]). First: power reduced when there is power."""
        out = [(energy, list(power))]
        for _ in self.rules("optional_cost_reduce", player=p):
            nxt = []
            for e, pw in out:
                cands = []
                for d in dict.fromkeys(reversed(pw)):          # [A] less: one power symbol (last one first)
                    q = list(pw)
                    del q[len(q) - 1 - q[::-1].index(d)]
                    cands.append((e, q))
                if e > 0:
                    cands.append((e - 1, list(pw)))            # [1] less
                nxt.extend(cands or [(e, list(pw))])
            out = []
            for e, pw in nxt:
                if (e, sorted(pw)) not in [(x, sorted(y)) for x, y in out]:
                    out.append((e, pw))
        return out

    def optional_cost_variants_for(self, it, ctx, name):
        """The variants of chain item `it`'s optional cost `name` (before reduction, then every Ezreal choice)."""
        raw = self._optional_costs_raw(it, ctx)
        for n, (e, p, _) in raw:
            if n == name:
                return self.optional_cost_variants(it.controller, e, p)
        return []

    def _optional_costs_include_repeat(self, it):
        rc = getattr(it.ability, "repeat_cost", None) if it.ability is not None else None
        if it.kind == "spell":
            rc = self.defn_of(it.uid).keywords.get("repeat_cost") or (it.ctx.vars.get("__granted_repeat") if it.ctx else None)
        return bool(rc)

    def _fizzle_item(self, it, why):
        it.removed = True
        if it in self.chain:
            self.chain.remove(it)
        if it.uid is not None and it.kind in ("spell", "unit", "gear"):
            o = self.objects[it.uid]
            if o.zone == "chain":
                flow = it.kind == "spell" and it.ctx is not None and it.ctx.vars.get("__flow")
                self._to_zone(o, "banish" if flow else "trash")      # Flow: banished on leaving the chain (CR 829.1.b.1)
        self.log("fizzle", item=it.id, label=it.label, why=why)
        self.dirty = True

    def _resolve_top(self):
        it = self.chain[-1]
        self._resolve_item(it)

    def _resolve_item(self, it):
        ctx = it.ctx
        self._revalidate_targets(ctx)
        self.log("resolve", item=it.id, label=it.label, controller=it.controller)
        if it.kind in ("unit", "gear"):
            self._enter_board(it)
        reps = ctx.repeat if it.kind in ("spell", "ability", "trigger", "reflexive") else 0
        snaps = ctx.vars.get("__rep_choices") or {}
        if reps:
            # CR 820.1.d: execute the instructions one additional time per Repeat paid, in order; the last run closes the item
            self.vm_frames.append(Frame(it.code or [], ctx, tag=("resolve", it.id)))
            for k in range(reps, 0, -1):
                if k in snaps:
                    self.vm_frames.append(Frame([_RestoreChoices(k)], ctx))
                if k > 1:
                    self.vm_frames.append(Frame(it.code or [], ctx))
            self.vm_frames.append(Frame(it.code or [], ctx))
            if 0 in snaps:
                self.vm_frames.append(Frame([_RestoreChoices(0)], ctx))
            return
        self.vm_frames.append(Frame(it.code or [], ctx, tag=("resolve", it.id)))

    def _revalidate_targets(self, ctx):
        """Re-validate targets (CR 355.6 mistargeting): targets that no longer match are dropped."""
        for name, sel in ctx.vars.get("__targets", []):
            v = ctx.vars.get(name)
            if v is None:
                continue
            if isinstance(v, tuple):
                ctx.vars[name] = tuple(u for u in v if u in self.objects and self._still_valid(sel, ctx, u))
            elif not (v in self.objects and self._still_valid(sel, ctx, v)):
                ctx.vars[name] = None

    def _still_valid(self, sel, ctx, u):
        if sel is None or isinstance(sel, (list, tuple)):
            return True
        try:
            return sel.matches(self, ctx, u)
        except (KeyError, AttributeError):
            return False

    def _energy_spent(self, it):
        """Energy actually paid for an item (base cost + additional costs), for "if you spent [N] or more"."""
        paid = (it.cost or {}).get("paid")
        return paid[0] if paid else 0

    def _resolved(self, item_id):
        it = next((x for x in self.chain if x.id == item_id), None)
        if it is None:
            return
        self.chain.remove(it)
        it.removed = True
        if it.kind == "spell":
            o = self.objects[it.uid]
            if o.zone == "chain":
                if it.ctx.vars.get("__recycle_after"):         # Fizz, Trickster
                    self.do_recycle([it.uid], it.ctx)
                elif it.ctx.vars.get("__flow") or it.ctx.vars.get("__banish_after"):     # Flow (CR 829.1.b)
                    self._to_zone(o, "banish")
                else:
                    self._to_zone(o, "trash")
            if it.ctx.vars.get("__play_ev"):
                self.emit("play", ctx=it.ctx, **it.ctx.vars.pop("__play_ev"))
            self.emit("resolve", uid=it.uid, player=it.controller, card_type="spell", item=it.id, energy=self._energy_spent(it),
                      may_replay=bool(it.ctx.vars.get("__may_replay")))     # "you may play this from your trash"
        if it.kind == "trigger" and it.ability is not None and getattr(it.ability, "keyword", None) == "deathknell":
            pass
        self.dirty = True
        self.passes = 0
        if self.chain:
            pend = [x for x in self.chain if not x.finalized]
            self.priority = self.chain[-1].controller if not pend else pend[0].controller
        else:
            # chain closed: open state again
            if self.showdown is not None:
                if not self.showdown.get("trigger_chain") and not it.is_add:
                    if self.showdown.get("acted"):
                        self.focus = self.next_player(self.focus)
                        self.showdown["passes"] = 0
                self.showdown["trigger_chain"] = False
                self.showdown["acted"] = False
                self.priority = self.focus
            else:
                self.priority = self.turn_player

    def _enter_board(self, it):
        o = self.objects[it.uid]
        ctx = it.ctx
        p = it.controller
        loc = ctx.vars.get("__loc") or ("base", p)
        self._to_zone(o, "board", location=loc, controller=p)
        o.played_from = ctx.played_from
        c = self.chars(it.uid)
        if "unit" in c.types:
            ready = bool(ctx.paid.get("accelerate", False))
            if self.consume_turn_effects("enter_ready", player=p):
                ready = True
            ev = self.replace_event({"kind": "enter_ready", "uid": it.uid, "player": p, "ready": ready, "loc": loc,
                                     "play_loc": ctx.vars.get("__play_loc") or loc,
                                     "add_paid": bool(ctx.paid.get("add")), "opt_ready": bool(ctx.vars.get("__opt_ready"))})
            if ev is not None:
                ready = bool(ev.get("ready"))
            o.exhausted = not ready
        else:
            ev = self.replace_event({"kind": "enter_ready", "uid": it.uid, "player": p, "ready": True, "loc": loc})
            o.exhausted = not (ev.get("ready", True) if ev else True)
        if ctx.paid.get("add"):
            o.temp["add_paid"] = True
        self.bump()
        self.log("enter", uid=it.uid, name=o.defn.name, loc=loc, player=p, ready=not o.exhausted)
        self.emit("enter", uid=it.uid, player=p, loc=loc, card_type="unit" if "unit" in c.types else "gear", token=False, ctx=ctx)
        if "unit" in c.types:
            self.emit("arrive", uid=it.uid, player=p, loc=loc, ctx=ctx)
            if loc[0] == "bf":
                self._apply_contested(loc, p)
        host = ctx.vars.get("__attach_to")          # "play an Equipment ... and attach it to me" (Rell, Magnetic)
        if host is not None and "gear" in c.types and self.objects.get(host) is not None \
                and self.objects[host].zone == "board":
            self.do_attach(it.uid, host, ctx)
        ctx.here = loc
        self.dirty = True

    # ------------------------------------------------------------------ actions
    def _main_decision(self):
        p = self.turn_player
        self.priority = p
        acts = self.legal_actions(p)
        self.ask(p, "action", acts, [self.action_label(a) for a in acts], "_on_action")

    def action_label(self, a):
        k = a[0]
        if k == "pass":
            return "pass"
        if k == "end_turn":
            return "end turn"
        if k == "play":
            loc = a[2] if len(a) > 2 else None
            return f"play {self.label(a[1])}" + (f" to {self.loc_name(loc)}" if loc else "")
        if k == "move":
            return "move " + ", ".join(self.label(u) for u in a[1]) + " to " + self.loc_name(a[2])
        if k == "move_select":
            return "move units to " + self.loc_name(a[1]) + " (choose which)"
        if k == "rune":
            d = (self.objects[a[2]].domain or "?").capitalize()
            return f"exhaust a {d} rune: add 1 energy" if a[1] == "exhaust" else f"recycle a {d} rune: add {d} power"
        if k == "hide":
            return f"hide {self.label(a[1])} at {self.loc_name(('bf', a[2]))}"
        if k == "activate":
            ab = self.abilities(a[1])[a[2]]
            return f"activate {self.label(a[1])}: {ab.label or ab.source_text[:30]}"
        return str(a)

    def _on_action(self, a, d):
        self.action_count += 1
        k = a[0]
        if k == "pass":
            self._pass()
        elif k == "end_turn":
            self.phase = "ending"
            self.priority = None
            self.dirty = True
        elif k == "play":
            self._play(self.priority if self.priority is not None else self.turn_player, a[1], a[2] if len(a) > 2 else None)
        elif k == "move":
            self._do_standard_move(self.turn_player, a[1], a[2])
        elif k == "move_select":
            self._move_select_step(self.turn_player, a[1], [])
        elif k == "hide":
            p = self.turn_player
            plans = []
            for e, pw in self._hide_costs(p):
                for pl in self.payment_plans(p, e, pw, {"kind": "hide"}):
                    if pl not in plans:
                        plans.append(pl)
            if len(plans) == 1:
                self._hide_paid(plans[0], None, hide=(a[1], a[2]), player=p)
            else:
                self.ask(p, "pay", plans, [plan_label(self, pl) for pl in plans], "_hide_paid", hide=(a[1], a[2]), hider=p,
                         **{"for": "hide " + self.objects[a[1]].defn.name})
        elif k == "rune":
            p = self.priority if self.priority is not None else self.turn_player
            u = a[2]
            o = self.objects[u]
            ctx = Context(p, u)
            if a[1] == "exhaust":
                self.do_exhaust(u, ctx)
                self.add_resources(p, 1, (), ctx=ctx)
            else:
                dom = o.domain
                self.do_recycle([u], ctx)
                self.add_resources(p, 0, (dom,), ctx=ctx)
            self.log("rune", player=p, uid=u, how=a[1])
            self.dirty = True
        elif k == "activate":
            self._activate(self.priority if self.priority is not None else self.turn_player, a[1], a[2])
        else:
            raise ValueError(a)

    def _pass(self):
        if self.chain:
            self.passes += 1
            self.priority = self.next_player(self.priority)
            return
        if self.showdown is not None:
            self.showdown["passes"] += 1
            if self.showdown["passes"] >= len(self.players):
                self._close_showdown()
            else:
                self.focus = self.next_player(self.focus)
                self.priority = self.focus
            return

    # ------------------------------------------------------------------ playing cards (CR 349-359)
    @staticmethod
    def _printed_power(d):
        doms, n = list(d.domains), d.power or 0
        if n == 0:
            return []
        if len(doms) <= 1:
            return (doms or ["any"]) * n
        return list(doms[:n]) + [doms[0]] * max(0, n - len(doms))

    def card_cost(self, p, uid, from_zone, loc=None):
        """(energy, power list) to play card uid from zone (to location loc, if known), after reductions."""
        o = self.objects[uid]
        d = o.base_defn()
        energy = d.energy or 0
        doms = list(d.domains)
        n = d.power or 0
        if n == 0:
            power = []
        else:
            power = [payment.own_power(doms)] * n      # multi-domain pips take any of its domains (CR 135.2.e.6.c)
        if from_zone == "facedown":
            energy, power = 0, []
        if from_zone == "trash":
            fl = d.keywords.get("flow_cost")
            if fl:
                energy, power = fl[0], list(fl[1])
            tp = self._trash_play_perm(uid)
            if tp is not None and tp.alt_cost is not None and not fl:
                energy, power = tp.alt_cost[0], list(tp.alt_cost[1])
        for ab in self._abilities_of(uid, o):
            if isinstance(ab, PlayPermission) and ab.cost_mod is not None and (ab.cond is None or ab.cond(self, uid)):
                energy, power = ab.cost_mod(self, uid, energy, power)
        for src, v in self.rules("cost_reduce", player=p):
            f = v if callable(v) else None
            if f is not None:
                energy, power = f(self, src, uid, energy, power)
        for t in self.turn_effects:
            if t["kind"] == "cost_reduce" and t["player"] == p:
                f = t["data"].get("filter")
                if f is None or f(self, uid):
                    energy = max(0, energy - t["data"].get("energy", 0))
                    if t["data"].get("power"):
                        power = power[t["data"]["power"]:]
        for src, v in self.rules("cost_reduce_once", player=p):   # Orianna: once each turn, a reduction for one card
            if not self.turn_memo.get(("once_reduce", src)) and v(self, src, uid, p):
                energy = max(0, energy - 1)
                power = power[1:]
        for src, v in self.rules("cost_mod_all"):            # Vex, Cheerless: affects every player's spells
            energy, power = v(self, src, uid, energy, power, p)
        if loc is not None:
            for src, v in self.rules("cost_reduce_at"):      # location-dependent reductions (Hunters' Circle)
                energy, power = v(self, src, uid, energy, power, p, loc)
        return max(0, energy), power

    def _play_timing_ok(self, p, uid, from_zone):
        """Can player p play this card now, timing-wise?"""
        o = self.objects[uid]
        c = o.base_defn()
        kws = c.keywords
        reaction = bool(kws.get("reaction")) or (from_zone == "facedown" and o.facedown_turn is not None and self.turn > o.facedown_turn) \
            or bool(kws.get("quick_draw"))
        if c.is_equipment and self.rules("hand_equipment_quick_draw", player=p):
            reaction = True                       # Jax, Unmatched (errata): "Your Equipment everywhere have [Quick-Draw]."
        action = bool(kws.get("action"))
        if c.type == "gear" and kws.get("deploy") and self.rules("deploy_gear_action", player=p):
            action = True                         # Jarvan IV, Martial Paragon: "Your gear with [Deploy] have [Action]."
        for ab in self._abilities_of(uid, o):
            if isinstance(ab, PlayPermission) and (ab.cond is None or ab.cond(self, uid)):
                if ab.perm == "reaction":
                    reaction = True
                elif ab.perm == "action":
                    action = True
        if from_zone == "facedown" and not (reaction and o.facedown_turn is not None and self.turn > o.facedown_turn):
            return False                          # CR 811.1.b: "Beginning on the next turn ... you may play this"
        if self.closed:
            return reaction and p == self.priority
        if self.showdown is not None or self.combat is not None:
            return (reaction or action) and p == self.focus
        return p == self.turn_player and self.phase == "main"

    def _opp_warden(self, p):
        """Mageseeker Warden: "While I'm at a battlefield, opponents can only play units to their base." """
        return any(self.objects[src].controller != p and (self.objects[src].location or ("",))[0] == "bf"
                   for src, _ in self.rules("opp_units_base_only"))

    def _play_locations(self, p, uid, from_zone):
        o = self.objects[uid]
        d = o.base_defn()
        if "spell" in d.types:
            return [None]
        if from_zone == "facedown":
            if "unit" in d.types and o.hidden_at in {self.objects[src].place for src, v in self.rules("cant_play_here")}:
                return []                    # a unit hidden at Rockfall Path can't be played there
            if "unit" in d.types and self._opp_warden(p):
                return []                    # CR 811.1.d.1 must go to that battlefield, Mageseeker Warden only to base
            return [o.hidden_at]
        locs = [("base", p)]
        if "unit" in d.types:
            # CR 355.2.a: a unit may be played to its controller's base or a battlefield that player controls
            locs += [("bf", bf.idx) for bf in self.battlefields if bf.controller == p]
        kws = d.keywords
        anywhere = False
        for t in self.turn_effects:
            if t["kind"] == "play_anywhere" and t["player"] == p and (t["data"].get("filter") is None or t["data"]["filter"](self, uid)):
                anywhere = True
        for ab in self._abilities_of(uid, o):
            if isinstance(ab, PlayPermission) and (ab.cond is None or ab.cond(self, uid)):
                if ab.perm in ("any_battlefield", "any_location"):
                    anywhere = True
        blocked = {self.objects[src].place for src, v in self.rules("cant_play_here")}
        if "unit" in d.types:
            if any(isinstance(ab, PlayPermission) and ab.perm == "to_enemy_bf" for ab in self._abilities_of(uid, o)):
                for bf in self.battlefields:          # "I can be played to a battlefield where there are enemy units"
                    loc = ("bf", bf.idx)
                    if any(self.objects[x].controller != p for x in self.units_at(loc)) and loc not in locs:
                        locs.append(loc)
            if kws.get("ambush") or anywhere:
                for bf in self.battlefields:
                    loc = ("bf", bf.idx)
                    if anywhere or self.units_at(loc, p):
                        players = {self.objects[u].controller for u in self.units_at(loc)}
                        if (p in players or len(players) < 2) and loc not in blocked and loc not in locs:
                            locs.append(loc)
        elif "gear" in d.types:
            if kws.get("deploy") or anywhere:
                for bf in self.battlefields:
                    locs.append(("bf", bf.idx))
            if kws.get("deploy"):
                locs = [l for l in locs if l[0] != "base"]     # CR 830.1.b: "Play or create this only to a battlefield"
        if "unit" in d.types:
            perms = {ab.perm for ab in self._abilities_of(uid, o) if isinstance(ab, PlayPermission)
                     and ab.perm in ("open_bf", "attacking_bf", "occupied_enemy_bf") and (ab.cond is None or ab.cond(self, uid))}
            for bf in self.battlefields if perms else ():
                loc = ("bf", bf.idx)
                units = self.units_at(loc)
                ok = ("open_bf" in perms and bf.controller is None and not units) \
                    or ("attacking_bf" in perms and self.combat is not None and self.combat["bf"] == bf.idx
                        and self.combat["attacker"] == p) \
                    or ("occupied_enemy_bf" in perms and bf.controller is not None
                        and not self.is_friendly(bf.controller, p) and bool(units))
                if ok and loc not in locs:
                    locs.append(loc)
        if self.rules("play_open_bf", player=p) and "unit" in d.types:
            for bf in self.battlefields:          # "Friendly units may be played to open battlefields"
                loc = ("bf", bf.idx)
                if bf.controller is None and not self.units_at(loc) and loc not in locs:
                    locs.append(loc)
        if "unit" in d.types and self._opp_warden(p):
            locs = [l for l in locs if l[0] == "base"]       # Mageseeker Warden
        for ab in self._abilities_of(uid, o):
            if isinstance(ab, PlayPermission) and ab.perm == "only_to" and ab.value is not None:
                locs = [l for l in locs if ab.value(self, p, l)]     # Perched Grimwyrm: "Play me only to ..."
        return [l for l in locs if l[0] == "base" or l not in blocked]

    def legal_actions(self, p):
        """Discretionary actions available to player p right now."""
        if self._canpay_memo is not None:
            return self._legal_actions(p)
        self._canpay_memo = {}
        try:
            return self._legal_actions(p)
        finally:
            self._canpay_memo = None

    def _legal_actions(self, p):
        acts = []
        main = (not self.closed) and self.neutral and self.phase == "main" and p == self.turn_player
        if self.closed or self.showdown is not None or self.combat is not None:
            acts.append(("pass",))
        elif main:
            acts.append(("end_turn",))
        ps = self.players[p]
        # play cards from hand / champion zone / facedown / trash (flow)
        sources = [(u, "hand") for u in ps.hand]
        if ps.champion is not None:
            sources.append((ps.champion, "champion"))
        for bf in self.battlefields:
            for u in self.facedown_cards(bf.idx, p):
                sources.append((u, "facedown"))
        for u in ps.trash:
            if self.objects[u].defn.keywords.get("flow_cost") or self._trash_play_perm(u):
                sources.append((u, "trash"))
        for t in self.turn_effects:          # "until ..., you may play that card" (Akali, Brash; Kennen's granted Flow)
            if t["kind"] == "may_play" and t["player"] == p and self.turn <= t["data"]["until_turn"]:
                u = t["data"]["uid"]
                if u in self.objects and self.objects[u].zone == t["data"]["zone"] and (u, t["data"]["zone"]) not in sources:
                    sources.append((u, t["data"]["zone"]))
        for u, z in sources:
            ambush_only = False
            if not self._play_timing_ok(p, u, z):
                # CR 822.1.b: Ambush = "I have [Reaction] as long as I'm being played to a battlefield where you control units"
                if z != "facedown" and self._ambush_locs(p, u) and self._reaction_window(p):
                    ambush_only = True
                else:
                    continue
            if not self._play_restrictions_ok(p, u, z):
                continue
            locs = self._play_locations(p, u, z)
            if ambush_only:
                amb = self._ambush_locs(p, u)
                locs = [l for l in locs if l in amb]
            purpose = payment.purpose_of_card(self, u)
            for loc in locs:
                e, pw = self.card_cost(p, u, z, loc)
                if not self.can_pay(p, e, pw, purpose=purpose):
                    if not (loc is None and self._exhaust_reducers(p) and self.can_pay(p, max(0, e - 2), pw, purpose=purpose)) \
                            and not self._free_with_cost(p, u) \
                            and self._variable_reduce_min(p, u, e, pw, purpose) is None:
                        continue
                if loc is None:
                    direct = self.can_pay(p, e, pw, purpose=purpose) and not self._variable_reduce_perm(u) \
                        and not self._exhaust_reducers(p)
                    if not self._spell_has_targets(p, u, z, cost=(e, list(pw), purpose) if direct else None):
                        continue
                    acts.append(("play", u))
                else:
                    acts.append(("play", u, loc))
        # activated abilities
        for u, o in self.objects.items():
            if o.zone != "board" or o.controller != p:
                continue
            for i, ab in enumerate(self.abilities(u)):
                if isinstance(ab, Activated) and self._can_activate(p, u, i, ab):
                    acts.append(("activate", u, i))
        acts.extend(self._rune_actions(p))
        if main:
            acts.extend(self._move_actions(p))
        if self._hide_window(p):
            acts.extend(self._hide_actions(p))
        return acts

    def _reaction_window(self, p):
        """Could p play a card with [Reaction] right now?"""
        if self.closed:
            return p == self.priority
        if self.showdown is not None or self.combat is not None:
            return p == self.focus
        return p == self.turn_player and self.phase == "main"

    def _ambush_locs(self, p, uid):
        """Battlefields a unit with Ambush may be played to with Reaction timing (CR 822; Rengar adds enemy-occupied ones)."""
        o = self.objects[uid]
        d = o.base_defn()
        if not d.is_unit or not self.chars(uid).keywords.get("ambush") and not d.keywords.get("ambush"):
            return []
        enemy_ok = any(isinstance(ab, PlayPermission) and ab.perm == "to_enemy_bf" for ab in self._abilities_of(uid, o))
        blocked = {self.objects[src].place for src, v in self.rules("cant_play_here")}
        out = []
        for bf in self.battlefields:
            loc = ("bf", bf.idx)
            if loc in blocked:
                continue
            units = self.units_at(loc)
            if any(self.objects[x].controller == p for x in units) or (enemy_ok and units):
                out.append(loc)
        return out

    def _can_react(self, p):
        """May p activate a Reaction ability right now (same windows as _can_activate for reactions)?"""
        if self.closed:
            return p == self.priority
        if self.showdown is not None or self.combat is not None:
            return p == self.focus
        return p == self.turn_player and self.phase == "main"

    def _rune_actions(self, p):
        """CR 164.2: every rune has '[Reaction] [E]: Add [1]' and '[Reaction] Recycle this: Add [C]'.
        Activating them outside a payment adds resources to the pool ('floating'). Runes of the same domain and
        state are interchangeable, so one action is offered per (domain, state)."""
        if not self._can_react(p):
            return []
        acts, seen = [], set()
        for u in sorted(self.players[p].runes):
            o = self.objects[u]
            key = (o.domain, o.exhausted)
            if key in seen:
                continue
            seen.add(key)
            if not o.exhausted:
                acts.append(("rune", "exhaust", u))
            acts.append(("rune", "recycle", u))
        return acts

    def _play_restrictions_ok(self, p, uid, z):
        o = self.objects[uid]
        for ab in self._abilities_of(uid, o):
            if isinstance(ab, PlayPermission) and ab.perm == "restriction" and not ab.cond(self, uid):
                return False
        if z == "hand" and self.rules("cant_play_from_hand", player=p):
            return False
        if not self._play_locks_ok(p, uid):
            return False
        for ab in self._abilities_of(uid, o):
            if isinstance(ab, PlayPermission) and ab.perm == "additional_cost":
                req, ins, mandatory = ab.value
                if mandatory and req is not None:
                    ctx = Context(p, uid, here=None)
                    if not req.candidates(self, ctx):
                        return False
        return True

    def _play_locks_ok(self, p, uid):
        """Effects that stop a player playing cards, which also apply to plays made by effects (CR 420.3.b)."""
        for t in self.turn_effects:
            if t["kind"] == "cant_play" and p in t["data"].get("players", ()):
                return False                 # Brynhir Thundersong: "opponents can't play cards this turn"
        if "spell" in self.objects[uid].base_defn().types:
            for src, v in self.rules("cant_play_spells"):
                if self.objects[src].controller != p and v is True:
                    return False
            for t in self.turn_effects:          # "Its controller can't play spells this turn" (Lilting Lullaby)
                if t["kind"] == "cant_play_spells" and p in t["data"].get("players", ()):
                    return False
        return True

    def _spell_has_targets(self, p, uid, z, cost=None):
        """Spells that require a target must have one (CR 355.6). cost: the play's cost, so a Deflect target whose
        tax can't be paid on top of it doesn't count (CR 355.16)."""
        d = self.objects[uid].base_defn()
        for ab in d.abilities:
            tc = getattr(ab, "target_code", None)
            if not tc:
                continue
            ctx = Context(p, uid, here=None)
            if cost is not None:
                ctx.vars["__base_cost"] = cost
            if z == "facedown":
                ctx.target_bf = self.objects[uid].hidden_at
            if not self._targets_possible(ctx, getattr(ab, "targets", None), tc):
                return False
        return True

    def _targets_possible(self, ctx, targets, code):
        """CR 355.8 / 403.3: every required target can be chosen. A modal item ("choose one") needs one mode whose
        targets can all be chosen (its other modes' choices are not required)."""
        if isinstance(targets, list):
            items = targets
        else:
            items = code or []
        for ins in items:
            if isinstance(ins, ChooseMode):
                if not any(self._targets_possible(ctx, body if isinstance(body, list) else [body], None)
                           for _, body in ins.modes):
                    return False
            elif isinstance(ins, Choose) and not ins.up_to and not ins.allow_none and not _depends_on_choice(ins):
                if not self.choice_candidates(ctx, ins.sel, targeted=ins.targeted):
                    return False
        return True

    def _can_activate(self, p, uid, idx, ab):
        o = self.objects[uid]
        if not ab.active(self, uid):
            return False
        if ab.restriction is not None and not ab.restriction(self, uid):
            return False
        if ab.is_empower and o.empowered and self.empower_cap(uid) == 1:
            return False        # objects that can be empowered several times ignore "only if not empowered" (Radiance patch)
        if ab.once_per_turn and o.temp.get(("act", idx)) == self.turn:
            return False
        timing = ab.timing
        if self.closed:
            if timing != "reaction" or p != self.priority:
                return False
        elif self.showdown is not None or self.combat is not None:
            if timing not in ("action", "reaction") or p != self.focus:
                return False
        else:
            if not (p == self.turn_player and self.phase == "main"):
                return False
        cost = ab.cost
        if cost.get("exhaust") and o.exhausted:
            return False
        if cost.get("ready_only") and o.exhausted:
            return False
        if cost.get("spend_buff") and o.buffs < 1:
            return False
        if cost.get("xp", 0) > self.players[p].xp:
            return False
        if cost.get("discard", 0) > len([h for h in self.players[p].hand if h != uid and (
                cost.get("discard_type") is None or cost["discard_type"] in self.chars(h).types)]):
            return False
        if cost.get("recycle", 0) > len(getattr(self.players[p], cost.get("recycle_zone", "trash"), ()) or ()):
            return False
        if cost.get("disempower_self") and not o.empowered:     # you can't disempower something that isn't empowered
            return False
        if cost.get("sacrifice") is not None:
            ctx = Context(p, uid, here=o.place)
            if not cost["sacrifice"].candidates(self, ctx):
                return False
        if cost.get("exhaust_unit") is not None:
            ctx = Context(p, uid, here=o.place)
            if not cost["exhaust_unit"].candidates(self, ctx):
                return False
        if cost.get("kill_self") and o.zone != "board":
            return False
        e = self.ability_energy(ab, uid)
        pw = list(cost.get("power", ()))
        pw = [payment.own_power(o.base_defn().domains) if d == "C" else d for d in pw]
        if not self.can_pay(p, e, pw, purpose={"kind": "ability", "types": set(self.chars(uid).types), "uid": uid}):
            return False
        if ab.targets:
            ctx = Context(p, uid, here=o.place)
            ctx.vars["__base_cost"] = (e, pw, {"kind": "ability", "types": set(self.chars(uid).types), "uid": uid})
            if not self._targets_possible(ctx, ab.targets, ab.target_code):
                return False
        return True

    MOVE_COMBO_LIMIT = 6          # up to this many movable units: one action per group; more: pick the group unit by unit

    def _move_actions(self, p):
        """CR 144: a Standard Move exhausts any number of the player's units and moves them to one destination; the
        origins need not be the same (144.3.b). Stunned units may move (stun only stops combat damage, CR 424.1.b)."""
        acts = []
        ready = [u for u, o in self.board_items() if o.controller == p and not o.exhausted
                 and o.location is not None and self.is_unit(u)]
        dests = [("bf", b.idx) for b in self.battlefields] + [("base", p)]
        for dest in dests:
            movable = [u for u in ready if self.valid_destination(u, dest, standard=True)]
            if not movable:
                continue
            if len(movable) <= self.MOVE_COMBO_LIMIT:
                for k in range(1, len(movable) + 1):
                    for combo in itertools.combinations(movable, k):
                        acts.append(("move", tuple(combo), dest))
            else:
                acts.append(("move_select", dest))
        return acts

    def _move_select_step(self, p, dest, chosen):
        movable = [u for u, o in self.board_items() if o.controller == p and not o.exhausted
                   and o.location is not None and self.is_unit(u) and u not in chosen
                   and self.valid_destination(u, dest, standard=True)]
        opts = movable + (["done"] if chosen else [])
        if not movable:
            self._do_standard_move(p, tuple(chosen), dest)
            return
        self.ask(p, "pick", opts, [self.label(u) for u in movable] + (["move them"] if chosen else []), "_move_select_pick",
                 dest=dest, chosen=tuple(chosen), label=f"Move which units to {self.loc_name(dest)}?")

    def _move_select_pick(self, choice, d):
        p, dest, chosen = d.player, d.info["dest"], list(d.info["chosen"])
        if choice == "done":
            self._do_standard_move(p, tuple(chosen), dest)
            return
        chosen.append(choice)
        self._move_select_step(p, dest, chosen)

    def _do_standard_move(self, p, units, dest):
        b = self.tick()
        for u in units:
            self.do_exhaust(u, batch=b)
        self.do_move(list(units), dest, Context(p), standard=True)
        self.dirty = True

    def _hide_window(self, p):
        """CR 811.1.b: hide 'on your turn during an Open State' (Neutral Open or Showdown Open, CR 307), with
        Priority (CR 312.1; in a showdown the player with Focus has it, 313.2)."""
        if self.closed or p != self.turn_player or self.phase != "main":
            return False
        if self.showdown is not None or self.combat is not None:
            return p == self.focus
        return True

    def _hide_actions(self, p):
        acts = []
        ps = self.players[p]
        bfs = [b.idx for b in self.battlefields if b.controller == p and self.can_hide_at(p, b.idx)]
        if not bfs or not self._hide_costs(p):
            return acts
        cards = list(ps.hand) + ([ps.champion] if ps.champion else [])
        for u in cards:
            if self.objects[u].defn.keywords.get("hidden"):
                for b in bfs:
                    acts.append(("hide", u, b))
        return acts

    def _hide_costs(self, p):
        """Payable costs to hide a card: [A], or [1] instead with Teemo, Swift Scout. -> list of (energy, power)."""
        costs = [(0, ["any"])]
        if self.rules("hide_for_1_energy", player=p):
            costs.append((1, []))
        return [c for c in costs if self.can_pay(p, c[0], c[1], purpose={"kind": "hide"})]

    def _hide_paid(self, plan, d, hide=None, player=None):
        if d is not None:
            hide, player = d.info["hide"], d.info["hider"]
        self.apply_payment(player, plan, Context(player), {"kind": "hide"})
        self.do_hide(player, hide[0], ("bf", hide[1]), Context(player))
        self.dirty = True

    def _state_name(self):
        """'combat' | 'showdown' | 'neutral' (open/closed is told by the chain depth)."""
        return "combat" if self.combat is not None else ("showdown" if self.showdown is not None else "neutral")

    def _play(self, p, uid, loc):
        o = self.objects[uid]
        z = o.zone
        d = o.base_defn()
        kind = "spell" if "spell" in d.types else ("unit" if "unit" in d.types else "gear")
        e, pw = self.card_cost(p, uid, z, loc)
        self._use_play_effects(p, uid)
        if loc is not None and kind in ("unit", "gear"):
            self.turn_memo.setdefault("played_at", []).append((p, loc))
        grant_repeat = self.consume_turn_effects("grant_repeat", player=p) if kind == "spell" else []
        grant_accel = kind == "unit" and bool(self.consume_turn_effects("grant_accelerate", player=p))   # Firelights' Hideout
        if kind == "gear" and not d.is_token:
            self.turn_memo[("gear_played", p)] = self.turn_memo.get(("gear_played", p), 0) + 1     # Ornn's Forge
        ctx = Context(p, uid, here=loc)
        ctx.played_from = z
        # Played from the trash for its Flow cost (or Kennen's granted Flow): banished as it leaves the chain
        # (CR 829.1.b). A spell an effect plays from the trash (Death from Below's replay, Fizz) is not.
        if z == "trash" and kind == "spell" and not getattr(self, "_limited_play", False) \
                and (d.keywords.get("flow_cost") or self._trash_play_perm(uid) is None):
            ctx.vars["__flow"] = True
        if z == "facedown":
            ctx.target_bf = o.hidden_at
        if loc is not None:
            ctx.vars["__loc"] = loc
        ctx.vars["self"] = uid
        if grant_repeat:
            if grant_repeat[0].get("base"):      # The Academy: "equal to its base cost" (printed)
                be, bpw = d.energy or 0, self._printed_power(d)
                ctx.vars["__granted_repeat"] = (be, tuple(bpw))
            else:                                 # Temporal Portal: "equal to its cost"
                ctx.vars["__granted_repeat"] = (e, tuple(pw))
        if grant_accel:
            ctx.vars["__granted_accel"] = True
        self._to_zone(o, "chain")
        o.controller = p
        # the card's own play abilities: spells have one 'effect' ability; permanents resolve by entering
        code, tcode = [], []
        for ab in d.abilities:
            if getattr(ab, "kind", "") == "spell":
                code = ab.code
                tcode = ab.target_code
        item = ChainItem(self.next_item_id, kind, p, uid, None, ctx, label=d.name, code=code, target_code=tcode,
                         cost={"energy": e, "power": pw})
        self.next_item_id += 1
        item.stamp = self.tick()
        self.chain.append(item)
        self.log("play", uid=uid, name=d.name, player=p, loc=loc, from_zone=z, chain=len(self.chain) - 1,
                 state=self._state_name(), phase=self.phase, turn_player=self.turn_player,
                 by_effect=bool(getattr(self, "_limited_play", False)))
        if self.showdown is not None:
            self.showdown["passes"] = 0
        self.passes = 0
        self.priority = p
        self.dirty = True
        return item

    def _use_play_effects(self, p, uid):
        """'The next <card> you play this turn costs less / gets X': playing a matching card uses the effect up."""
        for src, v in self.rules("cost_reduce_once", player=p):
            if not self.turn_memo.get(("once_reduce", src)) and v(self, src, uid, p):
                self.turn_memo[("once_reduce", src)] = True
        for t in list(self.turn_effects):
            if t["kind"] != "cost_reduce" or t["player"] != p or t["uses"] is None:
                continue
            f = t["data"].get("filter")
            if f is not None and not f(self, uid):
                continue
            on_play = t["data"].get("on_play")
            if on_play is not None:
                on_play(self, uid, t["ctx"])
            t["uses"] -= 1
            if t["uses"] <= 0:
                self.turn_effects.remove(t)

    def limited_play(self, p, uid, ctx, ignore=None, alt_cost=None, loc=None):
        """Play a card as part of an effect (CR 420). Cost may be ignored. Returns True if put on the chain."""
        o = self.objects.get(uid)
        if o is None or o.zone in ("board", "chain", None, "gone"):
            return False
        d = o.base_defn()
        z = o.zone
        kind = "spell" if "spell" in d.types else ("unit" if "unit" in d.types else "gear")
        if loc is None and kind != "spell":
            loc = ctx.target_bf if (ctx.target_bf is not None and kind == "unit") else ("base", p)
        e, pw = self.card_cost(p, uid, z, loc if kind != "spell" else None)
        if ignore == "all":
            e, pw = 0, []
        elif ignore == "energy":
            e = 0
        elif ignore == "power":
            pw = []
        if alt_cost is not None:
            e, pw = alt_cost
        if not self.can_pay(p, e, pw, purpose=payment.purpose_of_card(self, uid)):
            return False
        # CR 420.3.b: a limited play follows every normal step, so "can't play" locks (Brynhir Thundersong, spell
        # locks) and "Units can't be played here" (Rockfall Path) stop it; the card stays where it is (CR 420.3.c).
        if not self._play_locks_ok(p, uid):
            return False
        if kind == "unit" and loc is not None and loc[0] == "bf" \
                and loc in {self.objects[src].place for src, v in self.rules("cant_play_here")}:
            return False
        kind = "spell" if "spell" in d.types else ("unit" if "unit" in d.types else "gear")
        if loc is None and kind != "spell":
            loc = ctx.target_bf if (ctx.target_bf is not None and kind == "unit") else ("base", p)
        self._limited_play = True
        try:
            it = self._play(p, uid, loc)
        finally:
            self._limited_play = False
        it.cost = {"energy": e, "power": pw}
        it.ctx.played_from = z
        return True

    def _activate(self, p, uid, idx):
        o = self.objects[uid]
        ab = self.abilities(uid)[idx]
        ctx = Context(p, uid, here=o.place)
        ctx.vars["self"] = uid
        cost = ab.cost
        pw = [payment.own_power(o.base_defn().domains) if d == "C" else d for d in cost.get("power", ())]
        c = {"energy": self.ability_energy(ab, uid), "power": pw}
        if cost.get("exhaust"):
            c["exhaust"] = uid
        if cost.get("kill_self"):
            c["kill"] = [uid]
        if cost.get("banish_self"):
            c["banish"] = [uid]
        if cost.get("spend_buff"):
            c["spend_buff"] = uid
        if cost.get("xp"):
            c["xp"] = cost["xp"]
        if ab.once_per_turn:
            o.temp[("act", idx)] = self.turn
        kind = "add" if ab.is_add else "ability"
        item = ChainItem(self.next_item_id, kind, p, uid, ab, ctx, label=f"{o.defn.name}: {ab.label or ab.source_text[:30]}",
                         code=ab.code, target_code=list(ab.cost_code) + list(self._cost_choices(ab, uid)) + list(ab.target_code), cost=c)
        self.next_item_id += 1
        item.stamp = self.tick()
        self.chain.append(item)
        self.log("activate", uid=uid, name=o.defn.name, player=p, label=ab.label, chain=len(self.chain) - 1,
                 state=self._state_name(), timing=ab.timing, phase=self.phase, turn_player=self.turn_player)
        if self.showdown is not None:
            self.showdown["passes"] = 0
            if not ab.is_add:
                self.showdown["acted"] = True
        self.passes = 0
        self.priority = p
        self.dirty = True

    def ability_energy(self, ab, uid):
        """Energy cost of an activated ability, after the ability's own reduction ("costs [1] less for each ...")."""
        e = ab.cost.get("energy", 0)
        f = ab.cost.get("energy_reduction")
        if f is not None:
            e = max(0, e - f(self, uid))
        return e

    def _cost_choices(self, ab, uid):
        """Costs that need a choice (discard N, sacrifice a unit, recycle N) become choose instructions."""
        from .ops import Choose as _C, Do
        out = []
        cost = ab.cost
        if cost.get("discard"):
            out.append(_C(Sel_hand(cost.get("discard_type")), out="__discard", n=cost["discard"], targeted=False))
            out.append(Do(lambda g, c: g.do_discard(c.controller, list(c.vars["__discard"]) if isinstance(c.vars["__discard"], tuple) else [c.vars["__discard"]], c)))
        if cost.get("sacrifice") is not None:
            out.append(_C(cost["sacrifice"], out="__sac", targeted=False))
            out.append(Do(lambda g, c: g.do_kill([c.vars["__sac"]], c, by="cost")))
        if cost.get("exhaust_unit") is not None:      # "exhaust a friendly unit" (Blade of the Exile's Equip)
            out.append(_C(cost["exhaust_unit"], out="__exh", targeted=False))
            out.append(Do(lambda g, c: g.do_exhaust(c.vars["__exh"], c)))
        if cost.get("recycle"):
            out.append(Recycle(n=cost["recycle"], zone=cost.get("recycle_zone", "trash")))
        return out


def Sel_hand(card_type=None):
    return Sel("card", zone="hand", pred=lambda g, c, u: g.objects[u].owner == c.controller and u != c.source and (
        card_type is None or card_type in g.chars(u).types))
