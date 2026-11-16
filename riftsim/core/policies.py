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
    for u, o in g.board_items():
        c = g.chars(u)
        if "unit" in c.types:
            w = (c.might or 0) + 1.5
            if o.location is not None and o.location[0] == "bf":
                w += 1.0
            v += w if o.controller == p else -w
        elif "gear" in c.types:
            v += 2.0 if o.controller == p else -2.0
    v += 1.5 * (len(me.hand) - len(opp.hand))
    # runes are permanent resources: recycling one for a marginal gain is a real cost (was 1.0: the AI
    # recycled whole rune pools to move Equipment back and forth)
    v += RUNE_VALUE * (len(me.runes) - len(opp.runes))
    if g.turn_player == p and g.phase == "main":
        # unspent ready runes keep options open for reactions; tiny weight so real plays always win
        v += 0.15 * sum(1 for u in me.runes if not g.objects[u].exhausted)
    v += 0.5 * (me.xp - opp.xp)
    return v


RUNE_VALUE = 3.0


def _is_payment_source(game, o):
    if game is None or o[0] != "activate":
        return False
    try:
        ab = game.abilities(o[1])[o[2]]
    except (KeyError, IndexError):
        return False
    return bool(getattr(ab, "is_add", False)) and ab.timing == "reaction"


def _is_repeat_equip(game, o):
    """Equipping a gear that was already attached this turn: shuffling equipment back and forth only spends resources."""
    if game is None or o[0] != "activate":
        return False
    try:
        ab = game.abilities(o[1])[o[2]]
    except (KeyError, IndexError):
        return False
    at = game.objects[o[1]].temp.get("attached_turn")
    return bool(getattr(ab, "is_equip", False)) and at is not None and at[0] == game.turn


def ai_options(dec, game=None):
    """Options the built-in AIs consider. Floating resources with rune actions (CR 164.2) is legal at any
    Reaction window, but on its own it never improves the static evaluation and it hides the horizon from a
    one-ply search, so the AIs only spend runes through payment plans. This is an AI choice, not a rules
    restriction: the options stay legal for human players and the coach still grades them."""
    if dec.kind == "action":
        return [o for o in dec.options if o[0] != "rune" and not _is_payment_source(game, o)
                and not _is_repeat_equip(game, o)] or list(dec.options)
    return list(dec.options)


def prune_options(opts, cap, rng):
    """Cut a long option list down to `cap` for a search without losing whole kinds of play. Passing / ending the
    turn, every card play, ability, hide and payment stay; only Standard Move groups (which grow as 2^units per
    destination, CR 144.3) are thinned: single-unit moves and the all-units group for each destination are kept
    first, the remaining groups are sampled. Random sampling of the whole list used to drop 'end turn' or a play."""
    if len(opts) <= cap:
        return list(opts)
    moves = [o for o in opts if isinstance(o, tuple) and o and o[0] == "move"]
    if not moves:
        return list(opts)
    keep = [o for o in opts if not (isinstance(o, tuple) and o and o[0] == "move")]
    room = max(0, cap - len(keep))
    biggest = {}
    for o in moves:
        if len(o[1]) > len(biggest.get(o[2], ((), ()))[1]):
            biggest[o[2]] = o
    first = [o for o in moves if len(o[1]) == 1] + [o for o in biggest.values() if len(o[1]) > 1]
    rest = [o for o in moves if o not in first]
    if len(first) >= room:
        chosen = set(rng.sample(first, room)) if room else set()
    else:
        chosen = set(first) | set(rng.sample(rest, min(len(rest), room - len(first))))
    return keep + [o for o in moves if o in chosen]


def mulligan_choice(game, d):
    """Mulligan heuristic shared by the built-in AIs (CR 117): set aside the costliest cards (energy + power
    of 5 or more), up to two, keeping the cheapest early plays. Ties go to the card with the higher cost."""
    hand = sorted({u for o in d.options for u in o}, key=lambda u: -(game.objects[u].defn.energy + game.objects[u].defn.power))
    out = tuple(u for u in hand if game.objects[u].defn.energy + game.objects[u].defn.power >= 5)[:2]
    for o in d.options:
        if set(o) == set(out) and len(o) == len(out):
            return o
    return d.options[0]


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
        opts = ai_options(d, game)
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
        if d.player == p and d.kind != "pay":
            return d
        opts = ai_options(d, g)
        if d.kind == "action":
            opts = [o for o in opts if o[0] == "pass"] or opts
        elif d.kind == "mulligan":
            opts = [mulligan_choice(g, d)]
        elif d.kind == "pay":
            opts = opts[:1]           # standard payment plan
        g.choose(rng.choice(opts))
        steps += 1
    return g.pending


class GreedyPolicy(Policy):
    """One-ply lookahead: try each option on a clone, advance to the next own decision, evaluate."""
    name = "greedy"

    def __init__(self, seed=0, noise=0.01, max_options=60, temperature=0.0, miss_reactions=0.0, samples=1):
        self.rng = random.Random(seed)
        self.noise = noise
        self.max_options = max_options
        self.temperature = temperature          # 0: always the best option; >0: softmax over evaluations
        self.miss_reactions = miss_reactions    # chance to let an opponent's chain item resolve without looking
        self.samples = samples                  # determinised evaluations per option (hidden information)

    def value(self, g, p):
        """Position value for p (hand-written heuristic; LearnedPolicy uses the trained value net)."""
        return heuristic(g, p)

    def evaluate(self, game, d, opts):
        vals = []
        for o in opts:
            v = 0.0
            for k in range(self.samples):
                # never look ahead on the real game: the opponent's hand, facedown cards and both deck orders are
                # resampled from what this player cannot see (a real simulation, Derrick 2026-11-06)
                g = determinize(game, d.player, self.rng)
                if g.pending is None or o not in g.pending.options:
                    v += self.value(g, d.player)     # option depends on hidden cards: judge the position as it is
                    continue
                g.choose(o)
                _advance_default(g, d.player, rollout_rng=random.Random(self.rng.random()))
                v += self.value(g, d.player)
            v /= self.samples
            v += self.rng.random() * self.noise
            if d.kind == "action" and o[0] == "end_turn":
                v -= 0.01
            vals.append(v)
        return vals

    def choose(self, game, d):
        opts = ai_options(d, game)
        if d.kind == "mulligan":
            return mulligan_choice(game, d) if self.temperature < 8 else self.rng.choice(opts)
        if len(opts) == 1:
            return opts[0]
        if self.miss_reactions and d.kind == "action" and ("pass",) in opts and game.chain \
                and game.chain[-1].controller != d.player and self.rng.random() < self.miss_reactions:
            return ("pass",)
        opts = prune_options(opts, self.max_options, self.rng)
        vals = self.evaluate(game, d, opts)
        if self.temperature <= 0:
            return opts[max(range(len(opts)), key=lambda i: vals[i])]
        top = max(vals)
        ws = [math.exp(max(-50.0, (v - top) / self.temperature)) for v in vals]
        r = self.rng.random() * sum(ws)
        for o, w in zip(opts, ws):
            r -= w
            if r <= 0:
                return o
        return opts[-1]


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
    """Hidden information: shuffle what `player` cannot see (opponent hand + deck + facedown cards, own deck order,
    rune decks) on a clone and return it. Cards revealed to `player` (Scuttle Crab, reveals) are kept."""
    g = game.clone(copy_rng=False)                # g.rng is replaced below
    for q, ps in enumerate(g.players):
        # hidden orders/contents are sorted before shuffling, so the result depends only on what `player` knows
        if q == player:
            ps.deck = sorted(ps.deck, key=str)
            rng.shuffle(ps.deck)
            ps.rune_deck = sorted(ps.rune_deck, key=str)
            rng.shuffle(ps.rune_deck)
            continue
        # cards `player` knows stay where they are: revealed hand cards, facedown cards they may look at
        known_hand = [u for u in ps.hand if g.knows(player, u)]
        hidden_hand = [u for u in ps.hand if u not in known_hand]
        fd_slots = [(bf, k, u) for bf in g.battlefields for k, u in bf.facedown.items()
                    if g.objects[u].controller == q and not g.knows(player, u)]
        pool = sorted(hidden_hand + list(ps.deck) + [u for _, _, u in fd_slots], key=str)
        rng.shuffle(pool)
        # a facedown card is known to have [Hidden] (it was hidden with the keyword): fill those slots first
        hid = [u for u in pool if g.objects[u].base_defn().keywords.get("hidden")]
        new_fd = hid[:len(fd_slots)]
        if len(new_fd) < len(fd_slots):           # hidden by another effect: any card
            new_fd += [u for u in pool if u not in new_fd][:len(fd_slots) - len(new_fd)]
        rest = [u for u in pool if u not in set(new_fd)]
        nh = len(hidden_hand)
        new_hand, new_deck = rest[:nh], rest[nh:]
        olds = {u: (g.objects[u].location, g.objects[u].entered_stamp, getattr(g.objects[u], "hidden_at", None),
                    getattr(g.objects[u], "facedown_turn", None)) for _, _, u in fd_slots}
        for (bf, k, old), u in zip(fd_slots, new_fd):
            o = g.objects[u]
            o.zone, o.controller = "facedown", q
            o.location, o.entered_stamp, o.hidden_at, o.facedown_turn = olds[old]
            bf.facedown[k] = u
        ps.hand, ps.deck = known_hand + new_hand, new_deck
        for u in ps.hand:
            g.objects[u].zone, g.objects[u].location = "hand", None
        for u in ps.deck:
            g.objects[u].zone, g.objects[u].location = "deck", None
        ps.rune_deck = sorted(ps.rune_deck, key=str)
        rng.shuffle(ps.rune_deck)
    g.rng = random.Random(rng.random())      # future random events are unknown too
    g.restruct()
    return g


class MCTSPolicy(Policy):
    """UCT over the decision tree with random rollouts (capped) and a heuristic leaf value.
    Each iteration re-determinises hidden information (PIMC-style)."""
    name = "mcts"

    def __init__(self, iterations=200, rollout_depth=40, c=1.4, seed=0, max_branch=40):
        self.iterations, self.rollout_depth, self.c = iterations, rollout_depth, c
        self.rng = random.Random(seed)
        self.max_branch = max_branch

    def leaf(self, g, me):
        """Leaf value in [-1, 1] for `me`."""
        return math.tanh(heuristic(g, me) / 150.0)

    def choose(self, game, d):
        opts = ai_options(d, game)
        if d.kind == "mulligan":
            return mulligan_choice(game, d)
        if len(opts) == 1:
            return opts[0]
        root = self.search(game, d, all_root_options=False)
        if not root.children:
            return self.rng.choice(opts)
        best = max(root.children, key=lambda ch: ch.visits)
        return best.option

    def search(self, game, d, iterations=None, all_root_options=True):
        """Run the search and return the root node (children carry visits and summed value for each option).
        all_root_options: evaluate every legal option at the root (the coach grades any move a human makes)."""
        opts = list(d.options) if all_root_options else ai_options(d, game)
        root = _Node(player=d.player)
        root.untried = prune_options(opts, self.max_branch, self.rng)
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
                    dopts = ai_options(dec, g)
                    node.untried = prune_options(dopts, self.max_branch, self.rng)
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
            # rollout: a cheap playout policy that develops the board (plays the costliest affordable card,
            # moves to battlefields) instead of uniform random moves, which mostly pass or waste resources
            steps = 0
            while not g.over and g.pending is not None and steps < self.rollout_depth:
                dec = g.pending
                o = rollout_choice(g, dec, self.rng)
                g.choose(o)
                g.run()
                steps += 1
            v = self.leaf(g, me)
            # backprop
            while node is not None:
                node.visits += 1
                node.value += v
                node = node.parent
        return root


def rollout_choice(g, dec, rng):
    opts = ai_options(dec, g)
    if dec.kind == "pay":
        return opts[0]
    if dec.kind == "mulligan":
        return mulligan_choice(g, dec)
    if dec.kind != "action" or len(opts) == 1:
        return rng.choice(opts)
    plays = [o for o in opts if o[0] == "play"]
    moves = [o for o in opts if o[0] == "move" and o[2][0] == "bf"]
    r = rng.random()
    if plays and r < 0.75:
        def cost(o):
            d = g.objects[o[1]].base_defn()
            return (d.energy or 0) + 2 * (d.power or 0) + rng.random()
        return max(plays, key=cost)
    if moves and r < 0.9:
        return max(moves, key=lambda o: len(o[1]) + rng.random())
    for x in (("pass",), ("end_turn",)):
        if x in opts:
            return x
    return rng.choice(opts)


# Strength levels offered in the play page (Derrick, 2026-11-06). Each level is a real opponent: it plays at every
# timing it is allowed to (reactions, showdowns, hidden cards); lower levels decide with more noise and sometimes
# let an opponent's spell resolve without considering a response. Measured strength order: tools/ai_ladder.py.
LEVELS = {
    "novice": {"kind": "greedy", "temperature": 12.0, "miss_reactions": 0.6},
    "intermediate": {"kind": "greedy", "temperature": 4.0, "miss_reactions": 0.25},
    "advanced": {"kind": "greedy", "temperature": 0.8},
    "expert": {"kind": "greedy", "samples": 3},
    "elite": {"kind": "mcts", "iterations": 120},
}


def make_policy(spec, seed=0):
    """'random' | 'greedy' | 'mcts' | 'mcts:400' | a level name from LEVELS -> Policy"""
    if isinstance(spec, Policy):
        return spec
    if spec in LEVELS:
        cfg = dict(LEVELS[spec])
        kind = cfg.pop("kind")
        pol = GreedyPolicy(seed, **cfg) if kind == "greedy" else MCTSPolicy(seed=seed, **cfg)
        pol.name = spec
        return pol
    if spec == "search-v2":
        # AI v2 step 2 (2026-11-12): gen 14 + two-turn search with the policy-net-pruned learned opponent, 10 shared
        # samples, blend 0.3; beat gen 14 65-35 and 60-37 (docs/results/ai_v2_2026-11-12.md). ~15-20x slower per move.
        pol = make_policy("learned:gen_014:p=policy_g14:ps3:crn:b=0.3:d10", seed)
        pol.name = "search-v2"
        return pol
    name, _, arg = spec.partition(":")
    if name in ("learned", "learned-deep", "learned-mcts", "learned-r", "learned-deep-r", "learned-tmcts", "learned-rl"):
        from .learn.policy import make_learned
        return make_learned(name, arg, seed)
    if name == "policy":
        # policy:REF -> the policy net alone (no lookahead), AI v2 step 1
        import os
        from .learn.policy_net import PolicyNet, PolicyNetPlayer
        from .learn import model as _M
        path = arg if (arg.endswith(".json") or os.path.sep in arg) else os.path.join(_M.MODELS_DIR, arg + ".json")
        pol = PolicyNetPlayer(PolicyNet.load(path), seed=seed)
        pol.name = "policy:" + os.path.basename(path)[:-5]
        return pol
    if name == "random":
        return RandomPolicy(seed)
    if name == "greedy":
        return GreedyPolicy(seed)
    if name == "mcts":
        return MCTSPolicy(iterations=int(arg) if arg else 200, seed=seed)
    raise ValueError(f"unknown policy {spec}")
