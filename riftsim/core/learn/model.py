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

    @classmethod
    def load(cls, path):
        with open(path) as f:
            return cls(json.load(f))

    def predict_x(self, x):
        z = [(v - m) / s for v, m, s in zip(x, self.mean, self.std)]
        out = self.b2
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


_CACHE = {}


def best_path():
    """The promoted generation (models/best.json points at it)."""
    with open(os.path.join(MODELS_DIR, "best.json")) as f:
        return os.path.join(MODELS_DIR, json.load(f)["model"])


def load(path=None):
    path = path or best_path()
    if path not in _CACHE:
        _CACHE[path] = ValueNet.load(path)
    return _CACHE[path]
