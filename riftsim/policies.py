"""AI players. Each policy is a callable: policy(state) -> action.

- RandomPolicy: uniform over legal actions (baseline / rollout policy).
- GreedyPolicy: one-ply lookahead with a hand-written evaluation.
- MCTSPolicy: Monte Carlo tree search over the active player's turn, with
  determinized hidden information (opponent hand / decks are reshuffled per simulation).
"""
from __future__ import annotations

import math
import random

from . import engine


def evaluate(s, pidx):
    """Heuristic value of the state for player pidx, in roughly [-1, 1]."""
    if s.done:
        if s.winner is None:
            return 0.0
        return 1.0 if s.winner == pidx else -1.0
    me, op = s.players[pidx], s.players[1 - pidx]
    v = 0.0
    v += 0.25 * (me.points - op.points)
    for bf in s.battlefields:
        if bf.controller == pidx:
            v += 0.15
        elif bf.controller is not None:
            v -= 0.15
        v += 0.02 * (sum(engine.might(s, u) for u in bf.units[pidx])
                     - sum(engine.might(s, u) for u in bf.units[1 - pidx]))
    v += 0.02 * (sum(engine.might(s, u) for u in me.base) - sum(engine.might(s, u) for u in op.base))
    v += 0.01 * (len(me.hand) - len(op.hand))
    v += 0.01 * (len(me.runes) - len(op.runes))
    return max(-1.0, min(1.0, v))


class RandomPolicy:
    name = "random"

    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def __call__(self, s):
        return self.rng.choice(engine.legal_actions(s))


class GreedyPolicy:
    name = "greedy"

    def __init__(self, seed=0, end_bias=-0.03):
        self.rng = random.Random(seed)
        self.end_bias = end_bias

    def __call__(self, s):
        best, best_v = None, -9
        acts = engine.legal_actions(s)
        self.rng.shuffle(acts)
        for a in acts:
            c = s.clone()
            engine.apply(c, a)
            v = evaluate(c, s.active) + (self.end_bias if a[0] == "end" else 0)
            if v > best_v:
                best, best_v = a, v
        return best


def _determinize(s, pidx, rng):
    """Hide information: reshuffle what pidx cannot see (opponent hand+deck, own deck order, rune decks)."""
    c = s.clone()
    c.rng = random.Random(rng.random())
    op = c.players[1 - pidx]
    pool = [cid for _, cid in op.hand] + op.deck
    c.rng.shuffle(pool)
    n = len(op.hand)
    op.hand = [(uid, pool[i]) for i, (uid, _) in enumerate(op.hand)]
    op.deck = pool[n:]
    c.rng.shuffle(c.players[pidx].deck)
    for p in c.players:
        c.rng.shuffle(p.rune_deck)
    return c


class _Node:
    __slots__ = ("children", "n", "w", "untried")

    def __init__(self, acts):
        self.children = {}
        self.n, self.w = 0, 0.0
        self.untried = list(acts)


class MCTSPolicy:
    name = "mcts"

    def __init__(self, seed=0, iterations=200, rollout_depth=12, c=1.2, rollout="greedy"):
        self.rng = random.Random(seed)
        self.iterations, self.depth, self.c = iterations, rollout_depth, c
        self.rollout = GreedyPolicy(seed) if rollout == "greedy" else RandomPolicy(seed)

    def __call__(self, s):
        acts = engine.legal_actions(s)
        if len(acts) == 1:
            return acts[0]
        me = s.active
        root = _Node(acts)
        for _ in range(self.iterations):
            st = _determinize(s, me, self.rng)
            node, path = root, []
            # Select / expand within the active player's turn.
            while not st.done and st.active == me:
                # Different determinizations can draw different cards, so an action that was
                # legal when the node was created may not be legal now. Only consider legal ones.
                legal = set(engine.legal_actions(st))
                untried = [a for a in node.untried if a in legal]
                if untried:
                    a = untried[self.rng.randrange(len(untried))]
                    node.untried.remove(a)
                    engine.apply(st, a)
                    child = _Node(engine.legal_actions(st) if st.active == me else [])
                    node.children[a] = child
                    path.append(child)
                    node = child
                    break
                children = [(a, n) for a, n in node.children.items() if a in legal]
                if not children:
                    break
                lnp = math.log(node.n + 1)
                a, node = max(children,
                              key=lambda kv: kv[1].w / (kv[1].n + 1e-9) + self.c * math.sqrt(lnp / (kv[1].n + 1e-9)))
                engine.apply(st, a)
                path.append(node)
            # Rollout.
            for _ in range(self.depth):
                if st.done:
                    break
                engine.apply(st, self.rollout(st))
            v = evaluate(st, me)
            root.n += 1
            root.w += v
            for n in path:
                n.n += 1
                n.w += v
        return max(root.children.items(), key=lambda kv: kv[1].n)[0]


POLICIES = {"random": RandomPolicy, "greedy": GreedyPolicy, "mcts": MCTSPolicy}


def make_policy(spec, seed=0):
    """'mcts' or 'mcts:iterations=400,rollout_depth=8'."""
    name, _, kw = spec.partition(":")
    kwargs = {}
    for part in filter(None, kw.split(",")):
        k, v = part.split("=")
        kwargs[k] = int(v) if v.lstrip("-").isdigit() else float(v) if v.replace(".", "", 1).isdigit() else v
    return POLICIES[name](seed=seed, **kwargs)
