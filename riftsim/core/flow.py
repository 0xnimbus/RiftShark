"""Turn structure, chain (HOT FEPR), cleanups, showdowns, combat and scoring (CR 300-474).

The game is driven by Game.run(): it advances until a player decision is needed and returns a
Decision; Game.choose(option) applies it. All flow state lives on the Game, so clones can be
resumed anywhere (search) and a replay is just the list of chosen options.
"""
from __future__ import annotations

import itertools

from .abilities import Activated, PlayPermission, Static
from .objects import ChainItem
from .vm import Context, Decision, Frame, Instr, compile_effect, run_vm, resume_vm, val
from .ops import Choose

PHASES = ["awaken", "beginning", "scoring", "channel", "draw", "main", "ending", "expiration"]


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
        ctx.vars.setdefault("__costs", {})
        opts = game._optional_costs(it, ctx)
        for name, (energy, power, label) in opts:
            if name in ctx.vars["__costs"]:
                continue
            total_e = energy + it.cost["energy"] + sum(e for (e, _) in ctx.vars["__costs"].values())
            total_p = list(power) + list(it.cost["power"]) + [d for (_, ps) in ctx.vars["__costs"].values() for d in ps]
            total_p += ["any"] * game._deflect_total(it, ctx)
            if not game.can_pay(ctx.controller, total_e, total_p):
                ctx.vars["__costs"][name] = (0, [])
                continue
            ctx.vars["__ask"] = name
            return Decision(ctx.controller, "additional_cost", [True, False], out="__ans",
                            labels=[f"pay {label}", f"don't pay {label}"], info={"item": it.id, "cost": name})
        return self._finish(game, ctx, it)

    def resume(self, game, ctx, choice):
        it = self._item(game)
        name = ctx.vars.pop("__ask")
        opts = dict(game._optional_costs(it, ctx))
        energy, power, _ = opts[name]
        if choice:
            ctx.vars["__costs"][name] = (energy, list(power))
            ctx.paid[name] = True
            if name == "repeat":
                ctx.repeat += 1
        else:
            ctx.vars["__costs"][name] = (0, [])
        return self.run(game, ctx)

    def _finish(self, game, ctx, it):
        e = it.cost["energy"] + sum(x for (x, _) in ctx.vars["__costs"].values())
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
        if not game.can_pay(ctx.controller, e, p):
            # cannot pay after all (e.g. deflect targets): the item leaves the chain (CR 355)
            game._fizzle_item(it, "cannot pay")
            return None
        game.pay(ctx.controller, e, p, ctx)
        it.cost["paid"] = (e, p)
        return None


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
                self.dirty = False
                self._cleanup()
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
        self.log("decision", player=d.player, kind=d.kind, choice=d.labels[d.options.index(choice)])
        if handler:
            self.pending = None
            getattr(self, handler)(choice, d)
        else:
            resume_vm(self, choice)

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
        if ph in ("start", "next_turn"):
            self._start_turn()
        elif ph == "awaken":
            self._awaken()
            self.phase = "beginning"
            self.dirty = True
        elif ph == "beginning":
            self.emit("beginning_phase", player=self.turn_player)
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
            if self.turn == 2 and self.cfg["players"] == 2:
                n = 3     # CR 487.7: player going second channels an extra rune on their first turn
            self.do_channel(self.turn_player, n)
            self.phase = "draw"
            self.dirty = True
        elif ph == "draw":
            self.do_draw(self.turn_player, 1)
            self.phase = "main"
            for p in self.players:
                p.energy, p.power = 0, []
            self.emit("main_phase", player=self.turn_player)
            self.priority = self.turn_player
            self.dirty = True
        elif ph == "main":
            if self.turn > self.max_turns:
                self._end_game(None, "turn limit")
                return
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
        for p in self.players:
            p.played_this_turn = []
            p.memo = {}
        self.log("turn", player=self.turn_player)
        self.phase = "awaken"
        self.priority, self.focus = None, None

    def _awaken(self):
        p = self.turn_player
        for u, o in list(self.objects.items()):
            if o.zone == "board" and o.controller == p and o.exhausted:
                if o.stunned:
                    continue
                o.exhausted = False
        self.bump()
        self.emit("awaken", player=p)

    def _expiration(self):
        # Ending special cleanup (CR 317.2): heal, expire 'this turn' effects, empty pools, un-stun.
        self.chain_activity = 0
        for o in self.objects.values():
            if o.zone == "board":
                o.damage = 0
                o.stunned = False
        self.expire_mods("turn")
        for o in self.objects.values():
            # temporary control changes
            keep = []
            for m in o.mods:
                if m.kind == "control":
                    o.controller = m.value
                else:
                    keep.append(m)
            o.mods = keep
        for p in self.players:
            p.energy, p.power = 0, []
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

    def _cleanup_once(self):
        v = self.cfg["victory"]
        # 1. victory
        for p in self.players:
            if p.points >= v and all(p.points > q.points for q in self.players if q is not p):
                self._end_game(p.idx, "victory")
                return
        # 2. designations
        if self.combat is not None:
            bfl = ("bf", self.combat["bf"])
            for u, o in self.objects.items():
                if o.zone != "board" or "unit" not in self.chars(u).types:
                    continue
                if o.location == bfl:
                    want = "attacker" if o.controller == self.combat["attacker"] else ("defender" if o.controller == self.combat["defender"] else None)
                    if o.designation != want:
                        o.designation = want
                        self.bump()
                        if want == "attacker":
                            self.emit("attack", uid=u, player=o.controller, loc=bfl)
                        elif want == "defender":
                            self.emit("defend", uid=u, player=o.controller, loc=bfl)
                elif o.designation is not None:
                    o.designation = None
                    self.bump()
        # 3a. lethal damage
        dead = [u for u, o in self.objects.items() if o.zone == "board" and "unit" in self.chars(u).types and self.lethal_damage(u)]
        if dead:
            self.do_kill(dead, None, by="damage")
        # 4. lose control of empty battlefields (open state, no showdown/combat there)
        if not self.closed:
            for bf in self.battlefields:
                if bf.controller is not None and not self.units_at(("bf", bf.idx), bf.controller):
                    if self._showdown_at(bf.idx):
                        continue
                    self.log("lose_control", bf=bf.idx, player=bf.controller)
                    bf.controller = None
                    self.dirty = True
        # 5. recalls
        for u, o in list(self.objects.items()):
            if o.zone != "board" or o.location is None:
                continue
            c = self.chars(u)
            if o.location[0] == "bf":
                if "gear" in c.types and "unit" not in c.types and o.attached_to is None and not c.keywords.get("deploy"):
                    self.do_recall(u)
            elif o.location[0] == "base" and o.location[1] != o.controller and o.attached_to is None:
                self.do_recall(u)
        for bf in self.battlefields:
            for p, u in list(bf.facedown.items()):
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
        bf.controller = p
        self.log("control", bf=i, player=p, prev=prev)
        self.bump()
        self._score(p, i, "conquer")

    # ------------------------------------------------------------------ scoring (CR 469-473)
    def _score(self, p, i, how):
        if (p, i) in self.scored:
            return
        self.scored.add((p, i))
        ps = self.players[p]
        v = self.cfg["victory"]
        loc = ("bf", i)
        units = tuple(self.units_at(loc, p))
        if how == "conquer" and ps.points >= v - 1:
            if all((p, b.idx) in self.scored for b in self.battlefields):
                self.gain_points(p, 1, "conquer")
            else:
                self.log("final_point_draw", player=p)
                self.do_draw(p, 1)
        else:
            self.gain_points(p, 1, how)
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
        a_total = sum((self.chars(u).might or 0) for u in att if not self.objects[u].stunned)
        d_total = sum((self.chars(u).might or 0) for u in dfn if not self.objects[u].stunned)
        self.combat["totals"] = (a_total, d_total)
        self.tasks.append(("combat_deal",))
        self.tasks.append(("assign", c["defender"], tuple(att), d_total))
        self.tasks.append(("assign", c["attacker"], tuple(dfn), a_total))

    def _task_assign(self, player, targets, total):
        targets = [u for u in targets if u in self.objects and self.objects[u].zone == "board"]
        if total <= 0 or not targets:
            return
        plans = self._damage_plans(targets, total)
        if len(plans) == 1:
            self.combat["assign"][player] = plans[0]
            return
        labels = [", ".join(f"{self.label(u)}:{a}" for u, a in zip(targets, pl) if a) for pl in plans]
        self.ask(player, "assign_damage", plans, labels, "_on_assign", targets=tuple(targets))

    def _on_assign(self, choice, d):
        self.combat["assign"][d.player] = choice
        self.combat["assign_targets_" + str(d.player)] = d.info["targets"]

    def _damage_plans(self, targets, total):
        """Enumerate legal combat damage assignments (CR 467.2.c): lethal first, Tank first, Backline last."""
        info = []
        for u in targets:
            c = self.chars(u)
            need = max(1, (c.might or 0) - self.objects[u].damage)
            prio = 0 if c.keywords.get("tank") else (2 if c.keywords.get("backline") else 1)
            info.append((u, need, prio))
        groups = [[t for t in info if t[2] == k] for k in (0, 1, 2)]
        plans = set()
        for perm0 in itertools.permutations(groups[0]):
            for perm1 in itertools.permutations(groups[1]):
                for perm2 in itertools.permutations(groups[2]):
                    order = list(perm0) + list(perm1) + list(perm2)
                    plan = {u: 0 for u in targets}
                    rem = total
                    for u, need, _ in order:
                        take = min(need, rem)
                        plan[u] = take
                        rem -= take
                    if rem > 0:
                        plan[order[-1][0]] += rem
                    plans.add(tuple(plan[u] for u in targets))
                    if len(plans) > 60:
                        break
        return sorted(plans, reverse=True)

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
        for ctx, u, amt in dealt:
            self.do_deal([u], amt, ctx, source_uid=None, combat=True)
        self.dirty = True

    def _task_combat_cleanup(self):
        c = self.combat
        loc = ("bf", c["bf"])
        self._cleanup()
        for o in self.objects.values():
            if o.zone == "board":
                o.damage = 0
        self.bump()
        dfn = self.units_at(loc, c["defender"])
        att = self.units_at(loc, c["attacker"])
        if dfn and att:
            for u in att:
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
            bf.controller = None
        bf.contested_by = None
        self.dirty = True

    def _task_combat_end(self):
        c = self.combat
        loc = ("bf", c["bf"])
        survivors = tuple(self.units_at(loc))
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
        code = list(it.target_code or []) + [_FinalizeCosts(it.id)]
        self.vm_frames.append(Frame(code, ctx, tag=("finalize", it.id)))

    def _finalized(self, item_id):
        it = next((x for x in self.chain if x.id == item_id), None)
        if it is None:
            return
        ctx = it.ctx
        it.finalized = True
        self.log("finalized", item=it.id, label=it.label, controller=it.controller)
        targets = [u for u in self._target_uids(ctx) if u is not None]
        if targets:
            self.emit("target", targets=tuple(targets), player=it.controller, item=it.id, ctx=ctx)
        if it.kind in ("spell", "unit", "gear"):
            self.players[it.controller].played_this_turn.append(it.uid)
            o = self.objects[it.uid]
            self.emit("play", uid=it.uid, player=it.controller, card_type=it.kind, loc=ctx.target_bf or ctx.vars.get("__loc"),
                      from_zone=ctx.played_from, item=it.id, ctx=ctx)
        self.priority = it.controller
        self.passes = 0
        self.dirty = True
        if it.resolves_now:
            self._resolve_item(it)
            return
        if it.kind == "spell" and self.showdown is not None:
            self.showdown["acted"] = True

    def _target_uids(self, ctx):
        out = []
        for name, sel in ctx.vars.get("__targets", []):
            v = ctx.vars.get(name)
            if isinstance(v, tuple):
                out.extend(v)
            else:
                out.append(v)
        return out

    def _deflect_total(self, it, ctx):
        total = 0
        for u in self._target_uids(ctx):
            o = self.objects.get(u)
            if o is None or o.zone != "board" or self.is_friendly(o.controller, ctx.controller):
                continue
            total += self.keyword_value(u, "deflect")
        return total

    def _optional_costs(self, it, ctx):
        """Optional additional costs for a chain item: [(name, (energy, power, label))]."""
        out = []
        if it.kind == "unit":
            c = self.chars(it.uid)
            if c.keywords.get("accelerate"):
                dom = [c.domains[0]] if len(c.domains) == 1 else (["any"] if not c.domains else [c.domains[0]])
                out.append(("accelerate", (1, dom, "Accelerate [1][C]")))
        rc = getattr(it.ability, "repeat_cost", None) if it.ability is not None else None
        if it.kind == "spell":
            rc = self.defn_of(it.uid).keywords.get("repeat_cost")
        if rc:
            out.append(("repeat", (rc[0], list(rc[1]), f"Repeat {rc}")))
        return out

    def _fizzle_item(self, it, why):
        it.removed = True
        if it in self.chain:
            self.chain.remove(it)
        if it.uid is not None and it.kind in ("spell", "unit", "gear"):
            o = self.objects[it.uid]
            if o.zone == "chain":
                self._to_zone(o, "trash")
        self.log("fizzle", item=it.id, label=it.label, why=why)
        self.dirty = True

    def _resolve_top(self):
        it = self.chain[-1]
        self._resolve_item(it)

    def _resolve_item(self, it):
        ctx = it.ctx
        # re-validate targets (CR 355.6 mistargeting): targets that no longer match are dropped
        for name, sel in ctx.vars.get("__targets", []):
            v = ctx.vars.get(name)
            if v is None:
                continue
            if isinstance(v, tuple):
                ctx.vars[name] = tuple(u for u in v if u in self.objects and self._still_valid(sel, ctx, u))
            elif not (v in self.objects and self._still_valid(sel, ctx, v)):
                ctx.vars[name] = None
        self.log("resolve", item=it.id, label=it.label, controller=it.controller)
        if it.kind in ("unit", "gear"):
            self._enter_board(it)
        self.vm_frames.append(Frame(it.code or [], ctx, tag=("resolve", it.id)))

    def _still_valid(self, sel, ctx, u):
        if sel is None or isinstance(sel, (list, tuple)):
            return True
        try:
            return sel.matches(self, ctx, u)
        except (KeyError, AttributeError):
            return False

    def _resolved(self, item_id):
        it = next((x for x in self.chain if x.id == item_id), None)
        if it is None:
            return
        self.chain.remove(it)
        it.removed = True
        if it.kind == "spell":
            o = self.objects[it.uid]
            if o.zone == "chain":
                if it.ctx.played_from == "trash" or it.ctx.vars.get("__banish_after"):
                    self._to_zone(o, "banish")
                else:
                    self._to_zone(o, "trash")
            self.emit("resolve", uid=it.uid, player=it.controller, card_type="spell", item=it.id)
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
            o.exhausted = not ctx.paid.get("accelerate", False)
            if ctx.paid.get("accelerate"):
                o.exhausted = False
            for d in self.consume_turn_effects("enter_ready", player=p):
                o.exhausted = False
        else:
            o.exhausted = False
        self.bump()
        self.log("enter", uid=it.uid, name=o.defn.name, loc=loc, player=p, ready=not o.exhausted)
        self.emit("enter", uid=it.uid, player=p, loc=loc, card_type="unit" if "unit" in c.types else "gear", token=False, ctx=ctx)
        if "unit" in c.types:
            self.emit("arrive", uid=it.uid, player=p, loc=loc, ctx=ctx)
            if loc[0] == "bf":
                self._apply_contested(loc, p)
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
            p = self.turn_player
            for u in a[1]:
                self.do_exhaust(u)
            self.do_move(list(a[1]), a[2], Context(p), standard=True)
            self.dirty = True
        elif k == "hide":
            p = self.turn_player
            self.pay(p, 0, ["any"])
            self.do_hide(p, a[1], ("bf", a[2]), Context(p))
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
    def card_cost(self, p, uid, from_zone):
        """(energy, power list) to play card uid from zone, after reductions."""
        o = self.objects[uid]
        d = o.base_defn()
        energy = d.energy or 0
        doms = list(d.domains)
        n = d.power or 0
        if n == 0:
            power = []
        elif len(doms) <= 1:
            power = (doms or ["any"]) * n
        else:
            power = list(doms[:n]) + [doms[0]] * max(0, n - len(doms))
        if from_zone == "facedown":
            energy, power = 0, []
        if from_zone == "trash":
            fl = d.keywords.get("flow_cost")
            if fl:
                energy, power = fl[0], list(fl[1])
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
        return max(0, energy), power

    def _play_timing_ok(self, p, uid, from_zone):
        """Can player p play this card now, timing-wise?"""
        o = self.objects[uid]
        c = o.base_defn()
        kws = c.keywords
        reaction = bool(kws.get("reaction")) or (from_zone == "facedown" and o.facedown_turn is not None and self.turn > o.facedown_turn) \
            or bool(kws.get("quick_draw"))
        action = bool(kws.get("action"))
        for ab in self._abilities_of(uid, o):
            if isinstance(ab, PlayPermission) and (ab.cond is None or ab.cond(self, uid)):
                if ab.perm == "reaction":
                    reaction = True
                elif ab.perm == "action":
                    action = True
        if from_zone == "facedown" and not reaction:
            return False
        if self.closed:
            return reaction and p == self.priority
        if self.showdown is not None or self.combat is not None:
            return (reaction or action) and p == self.focus
        return p == self.turn_player and self.phase == "main"

    def _play_locations(self, p, uid, from_zone):
        o = self.objects[uid]
        d = o.base_defn()
        if "spell" in d.types:
            return [None]
        if from_zone == "facedown":
            return [o.hidden_at]
        locs = [("base", p)]
        kws = d.keywords
        anywhere = False
        for t in self.turn_effects:
            if t["kind"] == "play_anywhere" and t["player"] == p and (t["data"].get("filter") is None or t["data"]["filter"](self, uid)):
                anywhere = True
        for ab in self._abilities_of(uid, o):
            if isinstance(ab, PlayPermission) and (ab.cond is None or ab.cond(self, uid)):
                if ab.perm in ("any_battlefield", "any_location"):
                    anywhere = True
        if "unit" in d.types:
            if kws.get("ambush") or anywhere:
                for bf in self.battlefields:
                    loc = ("bf", bf.idx)
                    if anywhere or self.units_at(loc, p):
                        players = {self.objects[u].controller for u in self.units_at(loc)}
                        if p in players or len(players) < 2:
                            locs.append(loc)
        elif "gear" in d.types:
            if kws.get("deploy") or anywhere:
                for bf in self.battlefields:
                    locs.append(("bf", bf.idx))
        return locs

    def legal_actions(self, p):
        """Discretionary actions available to player p right now."""
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
            u = bf.facedown.get(p)
            if u is not None:
                sources.append((u, "facedown"))
        for u in ps.trash:
            if self.objects[u].defn.keywords.get("flow_cost"):
                sources.append((u, "trash"))
        for u, z in sources:
            if not self._play_timing_ok(p, u, z):
                continue
            if not self._play_restrictions_ok(p, u, z):
                continue
            e, pw = self.card_cost(p, u, z)
            if not self.can_pay(p, e, pw):
                continue
            for loc in self._play_locations(p, u, z):
                if loc is None:
                    if not self._spell_has_targets(p, u, z):
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
        if main:
            acts.extend(self._move_actions(p))
            acts.extend(self._hide_actions(p))
        return acts

    def _play_restrictions_ok(self, p, uid, z):
        o = self.objects[uid]
        for ab in self._abilities_of(uid, o):
            if isinstance(ab, PlayPermission) and ab.perm == "restriction" and not ab.cond(self, uid):
                return False
        if z == "hand" and self.rules("cant_play_from_hand", player=p):
            return False
        if "spell" in o.base_defn().types:
            for src, v in self.rules("cant_play_spells"):
                if self.objects[src].controller != p and v is True:
                    return False
        return True

    def _spell_has_targets(self, p, uid, z):
        """Spells that require a target must have one (CR 355.6)."""
        d = self.objects[uid].base_defn()
        for ab in d.abilities:
            tc = getattr(ab, "target_code", None)
            if not tc:
                continue
            ctx = Context(p, uid, here=None)
            if z == "facedown":
                ctx.target_bf = self.objects[uid].hidden_at
            for ins in tc:
                if isinstance(ins, Choose) and not ins.up_to and not ins.allow_none:
                    if not self.choice_candidates(ctx, ins.sel, targeted=ins.targeted):
                        return False
                    break
        return True

    def _can_activate(self, p, uid, idx, ab):
        o = self.objects[uid]
        if not ab.active(self, uid):
            return False
        if ab.restriction is not None and not ab.restriction(self, uid):
            return False
        if ab.is_empower and o.empowered:
            return False
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
        if cost.get("discard", 0) > len(self.players[p].hand):
            return False
        if cost.get("sacrifice") is not None:
            ctx = Context(p, uid, here=o.location)
            if not cost["sacrifice"].candidates(self, ctx):
                return False
        if cost.get("kill_self") and o.zone != "board":
            return False
        e = cost.get("energy", 0)
        pw = list(cost.get("power", ()))
        pw = [o.base_defn().domains[0] if (d == "C" and o.base_defn().domains) else ("any" if d == "C" else d) for d in pw]
        if not self.can_pay(p, e, pw, extra_exhaust=()):
            return False
        if ab.targets:
            ctx = Context(p, uid, here=o.location)
            for ins in ab.target_code:
                if isinstance(ins, Choose) and not ins.up_to and not ins.allow_none:
                    if not self.choice_candidates(ctx, ins.sel, targeted=ins.targeted):
                        return False
                    break
        return True

    def _move_actions(self, p):
        acts = []
        by_loc = {}
        for u, o in self.objects.items():
            if o.zone == "board" and o.controller == p and not o.exhausted and not o.stunned and "unit" in self.chars(u).types:
                if any(True for _ in self.rules("cant_move", player=None) if False):
                    continue
                by_loc.setdefault(o.location, []).append(u)
        dests = [("bf", b.idx) for b in self.battlefields] + [("base", p)]
        for loc, units in by_loc.items():
            units = units[:8]
            for dest in dests:
                if dest == loc:
                    continue
                movable = [u for u in units if self.valid_destination(u, dest, standard=True)]
                if not movable:
                    continue
                for k in range(1, len(movable) + 1):
                    for combo in itertools.combinations(movable, k):
                        acts.append(("move", tuple(combo), dest))
        return acts

    def _hide_actions(self, p):
        acts = []
        ps = self.players[p]
        bfs = [b.idx for b in self.battlefields if b.controller == p and p not in b.facedown]
        if not bfs or not self.can_pay(p, 0, ["any"]):
            return acts
        cards = list(ps.hand) + ([ps.champion] if ps.champion else [])
        for u in cards:
            if self.objects[u].defn.keywords.get("hidden"):
                for b in bfs:
                    acts.append(("hide", u, b))
        return acts

    def _play(self, p, uid, loc):
        o = self.objects[uid]
        z = o.zone
        d = o.base_defn()
        kind = "spell" if "spell" in d.types else ("unit" if "unit" in d.types else "gear")
        e, pw = self.card_cost(p, uid, z)
        ctx = Context(p, uid, here=loc)
        ctx.played_from = z
        if z == "facedown":
            ctx.target_bf = o.hidden_at
        if loc is not None:
            ctx.vars["__loc"] = loc
        ctx.vars["self"] = uid
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
        self.log("play", uid=uid, name=d.name, player=p, loc=loc, from_zone=z)
        if self.showdown is not None:
            self.showdown["passes"] = 0
        self.passes = 0
        self.priority = p
        self.dirty = True
        return item

    def limited_play(self, p, uid, ctx, ignore=None, alt_cost=None, loc=None):
        """Play a card as part of an effect (CR 420). Cost may be ignored. Returns True if put on the chain."""
        o = self.objects.get(uid)
        if o is None or o.zone in ("board", "chain", None, "gone"):
            return False
        d = o.base_defn()
        z = o.zone
        e, pw = self.card_cost(p, uid, z)
        if ignore == "all":
            e, pw = 0, []
        elif ignore == "energy":
            e = 0
        elif ignore == "power":
            pw = []
        if alt_cost is not None:
            e, pw = alt_cost
        if not self.can_pay(p, e, pw):
            return False
        kind = "spell" if "spell" in d.types else ("unit" if "unit" in d.types else "gear")
        if loc is None and kind != "spell":
            loc = ctx.target_bf if (ctx.target_bf is not None and kind == "unit") else ("base", p)
        it = self._play(p, uid, loc)
        it.cost = {"energy": e, "power": pw}
        it.ctx.played_from = z
        return True

    def _activate(self, p, uid, idx):
        o = self.objects[uid]
        ab = self.abilities(uid)[idx]
        ctx = Context(p, uid, here=o.location)
        ctx.vars["self"] = uid
        cost = ab.cost
        pw = [o.base_defn().domains[0] if (d == "C" and o.base_defn().domains) else ("any" if d == "C" else d) for d in cost.get("power", ())]
        c = {"energy": cost.get("energy", 0), "power": pw}
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
        self.log("activate", uid=uid, name=o.defn.name, player=p, label=ab.label)
        if self.showdown is not None:
            self.showdown["passes"] = 0
            if not ab.is_add:
                self.showdown["acted"] = True
        self.passes = 0
        self.priority = p
        self.dirty = True

    def _cost_choices(self, ab, uid):
        """Costs that need a choice (discard N, sacrifice a unit, recycle N) become choose instructions."""
        from .ops import Choose as _C, Do
        out = []
        cost = ab.cost
        if cost.get("discard"):
            out.append(_C(Sel_hand(), out="__discard", n=cost["discard"], targeted=False))
            out.append(Do(lambda g, c: g.do_discard(c.controller, list(c.vars["__discard"]) if isinstance(c.vars["__discard"], tuple) else [c.vars["__discard"]], c)))
        if cost.get("sacrifice") is not None:
            out.append(_C(cost["sacrifice"], out="__sac", targeted=False))
            out.append(Do(lambda g, c: g.do_kill([c.vars["__sac"]], c, by="cost")))
        if cost.get("recycle"):
            from .ops import Recycle
            out.append(Recycle(n=cost["recycle"], zone=cost.get("recycle_zone", "trash")))
        return out


def Sel_hand():
    from .selectors import Sel
    return Sel("card", zone="hand", pred=lambda g, c, u: g.objects[u].owner == c.controller and u != c.source)
