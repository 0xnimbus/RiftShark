"""Value network: win probability of the player whose seat the features describe.

A one-hidden-layer MLP stored as JSON (inputs are standardised with the training set's mean and std). The forward pass
is pure Python so the engine keeps no third-party dependency and the model runs in the browser build; training
(tools/train_value.py) uses numpy.
"""
from __future__ import annotations

import json
import math
import os

from .features import encode

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                          "models")


class ValueNet:
    def __init__(self, d):
        self.meta = d.get("meta", {})
        self.mean, self.std = d["mean"], d["std"]
        self.w1, self.b1 = d["w1"], d["b1"]        # w1: hidden x inputs
        self.w2, self.b2 = d["w2"], d["b2"]        # w2: hidden
        # residual form: logit = h_scale * atanh(x[h_index]) + MLP(x), i.e. the hand-written score is the base and the
        # net learns a correction to it (models without these keys are a plain MLP)
        self.h_index, self.h_scale = d.get("h_index"), d.get("h_scale", 0.0)
        self.lin = d.get("lin")                    # optional linear term on the standardised inputs

    @classmethod
    def load(cls, path):
        with open(path) as f:
            return cls(json.load(f))

    def predict_x(self, x):
        z = [(v - m) / s for v, m, s in zip(x, self.mean, self.std)]
        out = self.b2
        if self.h_index is not None:
            out += self.h_scale * math.atanh(max(-0.999999, min(0.999999, x[self.h_index])))
        if self.lin:
            out += sum(a * c for a, c in zip(self.lin, z))
        for row, b, w in zip(self.w1, self.b1, self.w2):
            h = b
            for a, c in zip(row, z):
                h += a * c
            out += w * math.tanh(h)
        if out < -30:
            return 0.0
        if out > 30:
            return 1.0
        return 1.0 / (1.0 + math.exp(-out))

    def predict(self, g, p):
        """P(player p wins) from p's seat; finished games are exact."""
        if g.over:
            if g.winner is None:
                return 0.5
            return 1.0 if g.winner == p else 0.0
        return self.predict_x(encode(g, p))


class HeuristicNet:
    """Baseline with the same interface: the hand-written score squashed to a probability. `learned:heuristic` uses
    it, so the gain from the value net can be separated from the gain from judging options at the turn boundary."""
    meta = {"baseline": True}

    def predict(self, g, p):
        if g.over:
            return 0.5 if g.winner is None else (1.0 if g.winner == p else 0.0)
        from ..policies import heuristic
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, heuristic(g, p) / 150.0))))


class EnsembleNet:
    """Several value nets averaged in logit space (`learned:gen_008+gen_006`): their errors partly cancel, so the
    lookahead compares options with a less noisy judge. Features are encoded once and each net reads its prefix."""

    def __init__(self, nets):
        self.nets = nets
        self.meta = {"ensemble": [n.meta for n in nets]}

    def predict(self, g, p):
        if g.over:
            return 0.5 if g.winner is None else (1.0 if g.winner == p else 0.0)
        x = encode(g, p)
        z = 0.0
        for n in self.nets:
            q = min(1 - 1e-9, max(1e-9, n.predict_x(x)))
            z += math.log(q / (1 - q))
        z /= len(self.nets)
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


_CACHE = {}


def best_path():
    """The promoted generation (models/best.json points at it)."""
    with open(os.path.join(MODELS_DIR, "best.json")) as f:
        m = json.load(f).get("model")
    return os.path.join(MODELS_DIR, m) if m else "heuristic"     # no net has beaten the hand-written score yet


def load(path=None):
    if path == "heuristic":
        return HeuristicNet()
    if path and "+" in os.path.basename(path):
        d = os.path.dirname(path)
        names = os.path.basename(path)[:-5].split("+") if path.endswith(".json") else os.path.basename(path).split("+")
        return EnsembleNet([load(os.path.join(d, n if n.endswith(".json") else n + ".json")) for n in names])
    path = path or best_path()
    if path not in _CACHE:
        _CACHE[path] = ValueNet.load(path)
    return _CACHE[path]
