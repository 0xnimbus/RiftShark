"""Policies that judge positions with the trained value net instead of the hand-written heuristic.

Specs (policies.make_policy):
  learned               greedy lookahead (3 determinised samples, like expert) with the promoted generation
  learned:gen_002       the same with a named generation (models/gen_002.json) or a path to a model file
  learned-mcts:120      MCTS with 120 iterations and the promoted generation as leaf value
  learned-mcts:120:gen_002
Search still runs on determinised copies only (policies.determinize), and the features read only what the
deciding player may know.

The net is trained on positions at a turn boundary (the first decision of a new turn), and the greedy policy judges
every option at that same moment: it plays the option, then ends its turn without further plays (the opponent passes,
its own follow-up choices such as targets are made by the one-sample heuristic AI), and asks the net about the
position at the start of the next turn. Comparing every option at the same point in the turn matters: an earlier
version compared "attack now" (judged mid-turn) with "end turn" (judged at the opponent's Beginning phase, their
runes still exhausted) and learned never to attack.
"""
from __future__ import annotations

import os
import random

from ..policies import GreedyPolicy, MCTSPolicy, ai_options, determinize, mulligan_choice
from . import model as M


def _resolve(ref):
    if not ref:
        return M.best_path()      # may be "heuristic"
    if ref == "heuristic":
        return ref
    if os.path.sep in ref or ref.endswith(".json"):
        return ref
    return os.path.join(M.MODELS_DIR, ref + ".json")


def to_turn_end(g, p, helper, max_steps=400, opp=None):
    """Advance g (a determinised copy) to the first decision of the next turn: p ends its turn as soon as it may act
    freely, the opponent passes, payments use the standard plan, and p's other choices (targets, modes, damage
    assignment) come from `helper`. Returns when the turn number changes or the game ends.
    With `opp`, the opponent is not assumed to pass: whenever it gets priority during p's turn with something it
    could play (a combat trick, a counter, a hidden card), `opp` decides, so an attack is judged against the
    reactions the opponent's (sampled) hand allows ("playing around" Falling Star and the like)."""
    start = g.turn
    for _ in range(max_steps):
        d = g.run()
        if d is None or g.over or g.turn != start:
            return
        opts = ai_options(d, g)
        if d.kind == "pay":
            o = opts[0]
        elif d.kind == "mulligan":
            o = mulligan_choice(g, d)
        elif d.kind == "action":
            o = None
            if opp is not None and d.player != p and any(isinstance(x, tuple) and x[0] not in ("pass", "end_turn") for x in opts):
                o = opp.choose(g, d)
            if o is None:
                o = next((x for x in (("end_turn",), ("pass",)) if x in opts), None)
            if o is None:
                o = helper.choose(g, d) if d.player == p else opts[0]
        elif d.player == p:
            o = helper.choose(g, d)
        elif opp is not None:
            o = opp.choose(g, d)          # the opponent's targets, modes and damage for the reaction it chose
        else:
            o = random.Random(len(g.events) if hasattr(g, "events") else 0).choice(opts)
        g.choose(o)


def opponent_turn(g, p, helper, max_steps=600, respond=None):
    """From the start of the opponent's turn in g (a determinised copy from p's view), let the opponent play its whole
    turn with `helper` (payments use the standard plan, p's forced choices also come from `helper`). Whenever p gets
    priority with something it could play (a counter, a combat trick, a hidden card), `respond` (default `helper`)
    decides whether to use it: energy held up on p's own turn only has a value if p can spend it here.
    Returns at the start of p's next turn or when the game ends. Used to label what-if positions in self-play."""
    respond = respond or helper
    start = g.turn
    for _ in range(max_steps):
        d = g.run()
        if d is None or g.over or g.turn != start:
            return
        opts = ai_options(d, g)
        if d.kind == "pay":
            o = opts[0]
        elif d.kind == "mulligan":
            o = mulligan_choice(g, d)
        elif d.player != p:
            o = helper.choose(g, d)
        elif d.kind == "action":
            if any(x[0] not in ("pass", "end_turn") for x in opts if isinstance(x, tuple)):
                o = respond.choose(g, d)
            else:
                o = next((x for x in (("pass",), ("end_turn",)) if x in opts), None) or helper.choose(g, d)
        else:
            o = helper.choose(g, d)
        g.choose(o)


class LearnedGreedy(GreedyPolicy):
    """deep=True ('learned-deep'): when the two best options of an action decision are within `margin` win
    probability of each other, they are compared again one turn deeper: play the option, end the turn, let the
    opponent play its whole turn with the same one-turn learned AI (on a copy determinised from our view, so its
    view of our hand is a sample too), and judge the start of our next turn. Only close calls pay for the deeper
    look, so a game costs a few times a plain one instead of a hundred times."""

    def __init__(self, net, seed=0, samples=3, deep=False, margin=0.04, deep_samples=2, react=False, **kw):
        super().__init__(seed, samples=samples, **kw)
        self.net = net
        self.helper = GreedyPolicy(seed + 991, samples=1)
        # react=True ('learned-r'): in the lookahead the opponent may answer during our turn (to_turn_end opp)
        # react="learned" ('learned-rl'): the opponent's answers come from the one-sample learned AI instead
        self.opp_react = (LearnedGreedy(net, seed=seed + 433, samples=1) if react == "learned"
                          else GreedyPolicy(seed + 433, samples=1) if react else None)
        self.deep, self.margin, self.deep_samples = deep, margin, deep_samples
        self.opp = LearnedGreedy(net, seed=seed + 577, samples=1) if deep else None
        self.deep_calls = 0

    def evaluate(self, game, d, opts):
        vals = []
        for o in opts:
            v = 0.0
            for _ in range(self.samples):
                g = determinize(game, d.player, self.rng)
                if g.pending is not None and o in g.pending.options:
                    g.choose(o)
                to_turn_end(g, d.player, self.helper, opp=self.opp_react)
                v += self.net.predict(g, d.player)
            v = 1000.0 * (v / self.samples - 0.5) + self.rng.random() * self.noise
            vals.append(v)
        if self.deep and d.kind == "action" and len(opts) >= 2:
            order = sorted(range(len(opts)), key=lambda i: -vals[i])
            a, b = order[0], order[1]
            if vals[a] - vals[b] < 1000.0 * self.margin:
                self.deep_calls += 1
                deep = {}
                for i in (a, b):
                    v = 0.0
                    for _ in range(self.deep_samples):
                        g = determinize(game, d.player, self.rng)
                        if g.pending is not None and opts[i] in g.pending.options:
                            g.choose(opts[i])
                        to_turn_end(g, d.player, self.helper, opp=self.opp_react)
                        if not g.over:
                            opponent_turn(g, d.player, self.opp)
                        v += self.net.predict(g, d.player)
                    deep[i] = v
                win = a if deep[a] >= deep[b] else b
                vals[win] = vals[a] + 1.0
        return vals


class LearnedMCTS(MCTSPolicy):
    """turn_leaf=True ('learned-tmcts'): no random rollout; a leaf is played to the start of the next turn the same
    way the greedy lookahead does (the player whose turn it is ends it, the other passes) and judged there, at the
    point the net was trained on. The tree itself holds both players' choices, the opponent's answers during our
    turn included (sampled hands, UCT picks the replies that hurt us most), so interaction is searched, not assumed
    away."""

    def __init__(self, net, iterations=120, seed=0, turn_leaf=False, **kw):
        if turn_leaf:
            kw.setdefault("rollout_depth", 0)
        super().__init__(iterations=iterations, seed=seed, **kw)
        self.net = net
        self.turn_leaf = turn_leaf
        self.helper = GreedyPolicy(seed + 991, samples=1) if turn_leaf else None

    def leaf(self, g, me):
        if self.turn_leaf and not g.over:
            to_turn_end(g, g.turn_player, self.helper)
        return 2.0 * self.net.predict(g, me) - 1.0


def make_learned(kind, arg, seed=0):
    if kind in ("learned", "learned-deep", "learned-r", "learned-deep-r", "learned-rl"):
        # learned-deep:gen_008:0.1 -> close-call margin 0.1 (default 0.04): more decisions get the look through the
        # opponent's turn
        ref, _, rest = (arg or "").partition(":")
        # learned-deep:gen_008:0.15:3 -> margin 0.15, 3 deep samples; a field "s6" -> 6 determinised samples per option
        kw, nums = {}, []
        for f in (rest.split(":") if rest else []):
            if f.startswith("s"):
                kw["samples"] = int(f[1:])
            else:
                nums.append(f)
        if nums:
            kw["margin"] = float(nums[0])
        if len(nums) > 1:
            kw["deep_samples"] = int(nums[1])
        path = _resolve(ref)
        pol = LearnedGreedy(M.load(path), seed=seed, deep=kind.startswith("learned-deep"),
                            react="learned" if kind == "learned-rl" else kind.endswith("-r"), **kw)
        pol.name = kind + ":" + (path if path == "heuristic" else os.path.basename(path)[:-5]) + (":" + rest if rest else "")
        return pol
    it, _, ref = (arg or "").partition(":")
    path = _resolve(ref)
    pol = LearnedMCTS(M.load(path), iterations=int(it or 120), seed=seed, turn_leaf=kind == "learned-tmcts")
    pol.name = f"{kind}:{it or 120}:" + (path if path == "heuristic" else os.path.basename(path)[:-5])
    return pol
