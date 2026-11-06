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
        return M.best_path()
    if os.path.sep in ref or ref.endswith(".json"):
        return ref
    return os.path.join(M.MODELS_DIR, ref + ".json")


def to_turn_end(g, p, helper, max_steps=400):
    """Advance g (a determinised copy) to the first decision of the next turn: p ends its turn as soon as it may act
    freely, the opponent passes, payments use the standard plan, and p's other choices (targets, modes, damage
    assignment) come from `helper`. Returns when the turn number changes or the game ends."""
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
            o = next((x for x in (("end_turn",), ("pass",)) if x in opts), None)
            if o is None:
                o = helper.choose(g, d) if d.player == p else opts[0]
        elif d.player == p:
            o = helper.choose(g, d)
        else:
            o = random.Random(len(g.events) if hasattr(g, "events") else 0).choice(opts)
        g.choose(o)


class LearnedGreedy(GreedyPolicy):
    def __init__(self, net, seed=0, samples=3, **kw):
        super().__init__(seed, samples=samples, **kw)
        self.net = net
        self.helper = GreedyPolicy(seed + 991, samples=1)

    def evaluate(self, game, d, opts):
        vals = []
        for o in opts:
            v = 0.0
            for _ in range(self.samples):
                g = determinize(game, d.player, self.rng)
                if g.pending is not None and o in g.pending.options:
                    g.choose(o)
                to_turn_end(g, d.player, self.helper)
                v += self.net.predict(g, d.player)
            v = 1000.0 * (v / self.samples - 0.5) + self.rng.random() * self.noise
            vals.append(v)
        return vals


class LearnedMCTS(MCTSPolicy):
    def __init__(self, net, iterations=120, seed=0, **kw):
        super().__init__(iterations=iterations, seed=seed, **kw)
        self.net = net

    def leaf(self, g, me):
        return 2.0 * self.net.predict(g, me) - 1.0


def make_learned(kind, arg, seed=0):
    if kind == "learned":
        path = _resolve(arg)
        pol = LearnedGreedy(M.load(path), seed=seed)
        pol.name = "learned:" + os.path.basename(path)[:-5]
        return pol
    it, _, ref = arg.partition(":")
    path = _resolve(ref)
    pol = LearnedMCTS(M.load(path), iterations=int(it or 120), seed=seed)
    pol.name = f"learned-mcts:{it or 120}:" + os.path.basename(path)[:-5]
    return pol
