"""Policy net (AI v2 step 1, docs/plans/ai_v2.md): scores the options of a decision straight from the position and a
description of each option, with no simulation, so a move costs milliseconds instead of the second or so the
lookahead AI spends. It is trained to pick what the lookahead AI picks (tools/train_policy.py) and is meant to play the
opponent, and our own answers, inside a deeper search.

Inputs per option: the deciding player's position features (features.encode, one seat only: no hidden information)
and the option's own features (encode_option: kind, the card it names with a hashed identity, cost, stats, where it
goes, how many units move). Model: one hidden tanh layer over [standardised position ; option], one score per option,
softmax over the options of the decision. Pure-Python forward pass, JSON weights, same conventions as model.py.
"""
from __future__ import annotations

import json
import math
import zlib

from .features import encode

OPT_KINDS = ("play", "pass", "end_turn", "move", "activate", "hide", "choose", "yes", "no", "choose_location",
             "assign_damage", "order_triggers", "other")
OPT_BUCKETS = 128
CARD_TYPES = ("unit", "spell", "gear", "rune", "legend", "battlefield", "token")
ZONES = ("hand", "board", "trash", "chain", "deck", "other")


def _bucket(card_id):
    return zlib.crc32(b"opt:" + card_id.encode()) % OPT_BUCKETS


def option_size():
    return len(OPT_KINDS) + OPT_BUCKETS + len(CARD_TYPES) + len(ZONES) + 14


def _kind(d, o):
    if d.kind == "action" and isinstance(o, tuple) and o and isinstance(o[0], str):
        return o[0] if o[0] in OPT_KINDS else "other"
    if d.kind in ("yesno", "additional_cost", "optional_replacement") and isinstance(o, bool):
        return "yes" if o else "no"
    if d.kind == "choose_location":
        return "choose_location"
    if d.kind == "assign_damage":
        return "assign_damage"
    if d.kind == "order_triggers":
        return "order_triggers"
    if isinstance(o, int) and not isinstance(o, bool):
        return "choose"
    return "other"


def _obj(g, d, o, kind):
    """The object an option names (the card played, the ability's source, the chosen object, the first mover)."""
    uid = None
    if kind in ("play", "activate", "hide") and len(o) > 1 and isinstance(o[1], int):
        uid = o[1]
    elif kind == "move" and len(o) > 1 and o[1]:
        uid = o[1][0]
    elif kind in ("choose", "order_triggers") and isinstance(o, int):
        uid = o
    if uid is None:
        return None
    return g.objects.get(uid)


def _dest(o, kind):
    if kind == "play" and len(o) > 2:
        return o[2]
    if kind == "move" and len(o) > 2:
        return o[2]
    if kind == "choose_location":
        return o
    return None


def encode_option(g, p, d, o):
    kind = _kind(d, o)
    out = [1.0 if kind == k else 0.0 for k in OPT_KINDS]
    cards = [0.0] * OPT_BUCKETS
    types = [0.0] * len(CARD_TYPES)
    zones = [0.0] * len(ZONES)
    ob = _obj(g, d, o, kind)
    extra = [0.0] * 14
    if ob is not None:
        df = ob.defn
        cards[_bucket(df.id)] = 1.0
        for i, t in enumerate(CARD_TYPES):
            if t in df.types or df.type == t:
                types[i] = 1.0
        z = ob.zone if ob.zone in ZONES else "other"
        zones[ZONES.index(z)] = 1.0
        try:
            c = g.chars(ob.uid) if ob.zone == "board" else None
        except Exception:
            c = None
        might = (c.might if c is not None else df.might) or 0
        extra[0] = (df.energy or 0) / 8
        extra[1] = (df.power or 0) / 3
        extra[2] = might / 8
        extra[3] = 1.0 if ob.controller == p else 0.0
        extra[4] = 1.0 if df.keywords.get("reaction") else 0.0
        extra[5] = 1.0 if df.keywords.get("action") else 0.0
        extra[6] = 1.0 if getattr(ob, "exhausted", False) else 0.0
    if kind == "move":
        extra[7] = len(o[1]) / 4
        tot = 0
        for u in o[1]:
            try:
                tot += g.chars(u).might or 0
            except Exception:
                pass
        extra[8] = tot / 8
    dest = _dest(o, kind)
    if isinstance(dest, tuple) and dest:
        if dest[0] == "base":
            extra[9] = 1.0
        elif dest[0] == "bf" and len(dest) > 1:
            bf = next((b for b in g.battlefields if b.idx == dest[1]), None)
            if bf is not None:
                extra[10] = 1.0 if bf.controller == p else 0.0
                extra[11] = 1.0 if bf.controller is not None and bf.controller != p else 0.0
                extra[12] = 1.0 if bf.controller is None else 0.0
    if kind == "activate" and len(o) > 2 and isinstance(o[2], int):
        extra[13] = min(o[2], 3) / 3
    if kind == "assign_damage" and isinstance(o, tuple):
        extra[13] = max(o) / 8 if o else 0.0
    return out + cards + types + zones + extra


class PolicyNet:
    def __init__(self, d):
        self.meta = d.get("meta", {})
        self.mean, self.std = d["mean"], d["std"]          # of the position features
        self.w1, self.b1, self.w2, self.b2 = d["w1"], d["b1"], d["w2"], d["b2"]
        self.ws = len(self.mean)

    @classmethod
    def load(cls, path):
        with open(path) as f:
            return cls(json.load(f))

    def scores(self, x, phis):
        z = [(v - m) / s for v, m, s in zip(x[:self.ws], self.mean, self.std)]
        # the position part of the hidden layer is shared by every option of the decision
        hs = []
        n = self.ws
        for row, b in zip(self.w1, self.b1):
            hs.append(b + sum(a * c for a, c in zip(row[:n], z)))
        out = []
        for phi in phis:
            s = self.b2
            for row, h0, w in zip(self.w1, hs, self.w2):
                h = h0
                for a, c in zip(row[n:], phi):
                    if c:
                        h += a * c
                s += w * math.tanh(h)
            out.append(s)
        return out

    def probs(self, g, d, opts):
        x = encode(g, d.player)
        sc = self.scores(x, [encode_option(g, d.player, d, o) for o in opts])
        top = max(sc)
        ws = [math.exp(s - top) for s in sc]
        t = sum(ws)
        return [w / t for w in ws]


class PolicyNetPlayer:
    """`policy:REF`: plays the arg-max option of the policy net (payments use the standard plan, mulligans the shared
    heuristic). Sees only what features.encode sees from its own seat."""

    def __init__(self, net, seed=0, temperature=0.0):
        import random
        self.net = net
        self.rng = random.Random(seed)
        self.temperature = temperature
        self.name = "policy"

    def choose(self, game, d):
        from ..policies import ai_options, mulligan_choice
        opts = ai_options(d, game)
        if d.kind == "mulligan":
            return mulligan_choice(game, d)
        if len(opts) == 1 or d.kind == "pay":
            return opts[0]
        pr = self.net.probs(game, d, opts)
        if self.temperature <= 0:
            return opts[max(range(len(opts)), key=lambda i: pr[i])]
        r = self.rng.random()
        for o, q in zip(opts, pr):
            r -= q
            if r <= 0:
                return o
        return opts[-1]
