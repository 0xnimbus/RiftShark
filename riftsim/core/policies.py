"""Decision policies for engine v2: random, greedy (one-ply heuristic) and MCTS with determinisation.

A policy answers `choose(game, decision) -> option`. Policies never mutate the game they are given;
search policies clone it.
"""
from __future__ import annotations

import math
import random

from .vm import Decision


def heuristic(g, p):
    """Static evaluation of the game from player p's point of view (higher is better)."""
    if g.over:
        if g.winner is None:
            return 0.0
        return 1000.0 if g.winner == p else -1000.0
    me, opp = g.players[p], g.players[g.opponent(p)]
    v = 60.0 * (me.points - opp.points)
    for b in g.battlefields:
        if b.controller == p:
            v += 25
        elif b.controller is not None:
            v -= 25
    for u, o in g.objects.items():
        if o.zone != "board":
            continue
        c = g.chars(u)
        if "unit" in c.types:
            w = (c.might or 0) + 1.5
            if o.location is not None and o.location[0] == "bf":
                w += 1.0
            v += w if o.controller == p else -w
        elif "gear" in c.types:
            v += 2.0 if o.controller == p else -2.0
    v += 1.5 * (len(me.hand) - len(opp.hand))
    v += 1.0 * (len(me.runes) - len(opp.runes))
    v += 0.5 * (me.xp - opp.xp)
    return v


class Policy:
    name = "policy"

    def choose(self, game, d: Decision):
        raise NotImplementedError


class RandomPolicy(Policy):
    name = "random"

    def __init__(self, seed=0, pass_bias=0.5):
        self.rng = random.Random(seed)
        self.pass_bias = pass_bias

    def choose(self, game, d):
        opts = d.options
        if d.kind == "action" and len(opts) > 1 and self.rng.random() < self.pass_bias:
            opts = [o for o in opts if o[0] not in ("pass", "end_turn")] or opts
        return self.rng.choice(opts)


def _advance_default(g, p, max_steps=400, rollout_rng=None):
    """Run the game until player p must decide again (or it ends). Other players' decisions are
    taken by a cheap default (random with pass bias) so the evaluation is a rough expectation."""
    rng = rollout_rng or random.Random(0)
    steps = 0
    while steps < max_steps:
        d = g.run()
        if d is None:
            return None
        if d.player == p:
            return d
        opts = d.options
        if d.kind == "action":
            opts = [o for o in opts if o[0] == "pass"] or opts
        g.choose(rng.choice(opts))
        steps += 1
    return g.pending


class GreedyPolicy(Policy):
    """One-ply lookahead: try each option on a clone, advance to the next own decision, evaluate."""
    name = "greedy"

    def __init__(self, seed=0, noise=0.01, max_options=60):
        self.rng = random.Random(seed)
        self.noise = noise
        self.max_options = max_options

    def choose(self, game, d):
        opts = list(d.options)
        if len(opts) == 1:
            return opts[0]
        if len(opts) > self.max_options:
            opts = self.rng.sample(opts, self.max_options)
        best, best_v = None, -1e18
        for o in opts:
            g = game.clone()
            g.choose(o)
            _advance_default(g, d.player, rollout_rng=random.Random(self.rng.random()))
            v = heuristic(g, d.player) + self.rng.random() * self.noise
            if d.kind == "action" and o[0] == "end_turn":
                v -= 0.01
            if v > best_v:
                best, best_v = o, v
        return best


# ---------------------------------------------------------------------------- MCTS
class _Node:
    __slots__ = ("option", "parent", "children", "visits", "value", "untried", "player")

    def __init__(self, option=None, parent=None, player=None):
        self.option, self.parent, self.player = option, parent, player
        self.children = []
        self.visits = 0
        self.value = 0.0
        self.untried = None


def determinize(game, player, rng):
    """Hidden information: shuffle what `player` cannot see (opponent hand + deck, own deck order,
    rune decks, facedown cards) on a clone and return it."""
    g = game.clone()
    for q, ps in enumerate(g.players):
        if q == player:
            rng.shuffle(ps.deck)
            rng.shuffle(ps.rune_deck)
            continue
        pool = list(ps.hand) + list(ps.deck)
        rng.shuffle(pool)
        nh = len(ps.hand)
        ps.hand, ps.deck = pool[:nh], pool[nh:]
        for u in ps.hand:
            g.objects[u].zone = "hand"
        for u in ps.deck:
            g.objects[u].zone = "deck"
        rng.shuffle(ps.rune_deck)
    g.bump()
    return g


class MCTSPolicy(Policy):
    """UCT over the decision tree with random rollouts (capped) and a heuristic leaf value.
    Each iteration re-determinises hidden information (PIMC-style)."""
    name = "mcts"

    def __init__(self, iterations=200, rollout_depth=40, c=1.4, seed=0, max_branch=40):
        self.iterations, self.rollout_depth, self.c = iterations, rollout_depth, c
        self.rng = random.Random(seed)
        self.max_branch = max_branch

    def choose(self, game, d):
        opts = list(d.options)
        if len(opts) == 1:
            return opts[0]
        root = self.search(game, d)
        if not root.children:
            return self.rng.choice(opts)
        best = max(root.children, key=lambda ch: ch.visits)
        return best.option

    def search(self, game, d, iterations=None):
        """Run the search and return the root node (children carry visits and summed value for each option)."""
        opts = list(d.options)
        root = _Node(player=d.player)
        root.untried = list(opts) if len(opts) <= self.max_branch else self.rng.sample(opts, self.max_branch)
        me = d.player
        for _ in range(iterations or self.iterations):
            g = determinize(game, me, self.rng)
            node = root
            # selection / expansion
            depth = 0
            while True:
                dec = g.pending
                if dec is None or g.over:
                    break
                if node.untried is None:
                    node.untried = list(dec.options) if len(dec.options) <= self.max_branch else self.rng.sample(dec.options, self.max_branch)
                    node.player = dec.player
                if node.untried:
                    o = node.untried.pop(self.rng.randrange(len(node.untried)))
                    if o not in dec.options:
                        continue
                    child = _Node(o, node, dec.player)
                    node.children.append(child)
                    g.choose(o)
                    g.run()
                    node = child
                    break
                # UCT
                legal = [ch for ch in node.children if ch.option in dec.options]
                if not legal:
                    break
                lv = math.log(node.visits + 1)
                def uct(ch):
                    q = ch.value / ch.visits if ch.visits else 0.0
                    if dec.player != me:
                        q = -q
                    return q + self.c * math.sqrt(lv / (ch.visits + 1e-9))
                node = max(legal, key=uct)
                g.choose(node.option)
                g.run()
                depth += 1
                if depth > 60:
                    break
            # rollout
            steps = 0
            while not g.over and g.pending is not None and steps < self.rollout_depth:
                dec = g.pending
                o = self.rng.choice(dec.options)
                if dec.kind == "action" and len(dec.options) > 1 and self.rng.random() < 0.5:
                    o = self.rng.choice([x for x in dec.options if x[0] not in ("pass", "end_turn")] or dec.options)
                g.choose(o)
                g.run()
                steps += 1
            v = heuristic(g, me)
            v = math.tanh(v / 150.0)
            # backprop
            while node is not None:
                node.visits += 1
                node.value += v
                node = node.parent
        return root


def make_policy(spec, seed=0):
    """'random' | 'greedy' | 'mcts' | 'mcts:400' -> Policy"""
    if isinstance(spec, Policy):
        return spec
    name, _, arg = spec.partition(":")
    if name == "random":
        return RandomPolicy(seed)
    if name == "greedy":
        return GreedyPolicy(seed)
    if name == "mcts":
        return MCTSPolicy(iterations=int(arg) if arg else 200, seed=seed)
    raise ValueError(f"unknown policy {spec}")
