"""Policies that judge positions with the trained value net instead of the hand-written heuristic.

Specs (policies.make_policy):
  learned               greedy lookahead (3 determinised samples, like expert) with the promoted generation
  learned:gen_002       the same with a named generation (models/gen_002.json) or a path to a model file
  learned-mcts:120      MCTS with 120 iterations and the promoted generation as leaf value
  learned-mcts:120:gen_002
Search still runs on determinised copies only (policies.determinize), and the features read only what the
deciding player may know.
"""
from __future__ import annotations

import os

from ..policies import GreedyPolicy, MCTSPolicy
from . import model as M


def _resolve(ref):
    if not ref:
        return M.best_path()
    if os.path.sep in ref or ref.endswith(".json"):
        return ref
    return os.path.join(M.MODELS_DIR, ref + ".json")


class LearnedGreedy(GreedyPolicy):
    def __init__(self, net, seed=0, samples=3, **kw):
        super().__init__(seed, samples=samples, **kw)
        self.net = net

    def value(self, g, p):
        return 1000.0 * (self.net.predict(g, p) - 0.5)


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
