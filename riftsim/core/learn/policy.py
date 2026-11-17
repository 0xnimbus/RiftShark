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
from .features import encode


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


def _fast_in_hand(g, p):
    """p holds a spell it could cast in the opponent's turn (Reaction or Action) with all its runes ready."""
    ps = g.players[p]
    runes = len(ps.runes)
    for u in ps.hand:
        d = g.objects[u].defn
        if d.type == "spell" and (d.keywords.get("reaction") or d.keywords.get("action")) and (d.energy or 0) <= runes:
            return True
    return False


def _reseed(pols, x):
    """Re-seed the random generators of these policies and the helper policies they hold."""
    seen, stack, k = set(), list(pols), 0
    while stack:
        p = stack.pop()
        if p is None or id(p) in seen:
            continue
        seen.add(id(p))
        if isinstance(getattr(p, "rng", None), random.Random):
            k += 1
            p.rng.seed(x * 1000003 + k)
        for a in ("helper", "opp_react", "window", "opp", "hold_opp"):
            stack.append(getattr(p, a, None))
        sub = getattr(p, "pnet", None)
        if isinstance(sub, list):
            stack.extend(sub)


class LearnedGreedy(GreedyPolicy):
    """deep=True ('learned-deep'): when the two best options of an action decision are within `margin` win
    probability of each other, they are compared again one turn deeper: play the option, end the turn, let the
    opponent play its whole turn with the same one-turn learned AI (on a copy determinised from our view, so its
    view of our hand is a sample too), and judge the start of our next turn. Only close calls pay for the deeper
    look, so a game costs a few times a plain one instead of a hundred times."""

    def __init__(self, net, seed=0, samples=3, deep=False, margin=0.04, deep_samples=2, react=False, window=None,
                 hold=False, hold_k=3, pnet=None, pk=3, blend=None, pstrong=0, crn=False, adapt=0, adapt_gap=15.0, **kw):
        super().__init__(seed, samples=samples, **kw)
        self.net = net
        # window ('learned:REF:rw', 'rwl' with the learned AI as the opponent): an action decision in the opponent's
        # turn (a reaction window) is not judged as if the opponent then ends its turn at once; the opponent plays the
        # rest of its turn (one-sample AI, on the determinised copy) and we may still answer its later plays, so
        # holding a counter for a bigger threat is weighed against spending it now. Judged at the start of our turn.
        self.window = None
        if window == "greedy":
            self.window = GreedyPolicy(seed + 211, samples=1)
        elif window == "learned":
            self.window = LearnedGreedy(net, seed=seed + 211, samples=1)
        self.window_calls = 0
        # hold ('learned:REF:hold'): on our own turn, while our hand has a fast spell (Reaction/Action) that our runes
        # could pay for, the best `hold_k` options (and ending the turn) are judged after the opponent's whole turn,
        # in which we may answer (one-sample AIs on both sides, determinised copies). Energy kept up for a counter
        # only has a value if the lookahead lets us spend it; the plain lookahead stops before the opponent acts.
        self.hold = hold
        self.hold_k = hold_k
        self.hold_opp = GreedyPolicy(seed + 307, samples=1) if hold else None
        self.hold_calls = 0
        # pnet ('learned:REF:p=POLICY[:kN]', AI v2 step 2): for our turn's decisions and reaction windows, the best `pk`
        # options by the one-turn judgement (and ending the turn / passing) are judged two turns deep: the rest of the
        # current turn and the opponent's whole turn are played with the fast policy net on both sides (its answers,
        # our counters), on determinised copies; judged at the start of our next turn.
        self.pnet = None
        self.pk = pk
        self.blend = blend          # None: the deep value decides among the candidates; x: shallow + x * (deep - shallow)
        self.p_calls = 0
        # crn ('crn'): every candidate is played out on the same determinised copies with the same random seeds
        # (common random numbers), so the comparison between candidates is not drowned by which hands were sampled
        self.crn = crn
        self.adapt, self.adapt_gap = adapt, adapt_gap      # 'aN[:gX]': adaptive sample count (needs crn)
        if pnet:
            from .policy_net import PolicyNet, PolicyNetPlayer
            pn = PolicyNet.load(pnet)
            if pstrong:
                # the opponent model inside the search: the one-sample learned AI judging only the policy net's
                # `pstrong` most likely options (about gen-14 strength at a fraction of its cost)
                self.pnet = [PrunedLearned(net, pn, pstrong, seed=seed + 613),
                             PrunedLearned(net, pn, pstrong, seed=seed + 617)]
            else:
                self.pnet = [PolicyNetPlayer(pn, seed=seed + 613), PolicyNetPlayer(pn, seed=seed + 617)]
        self.helper = GreedyPolicy(seed + 991, samples=1)
        # react=True ('learned-r'): in the lookahead the opponent may answer during our turn (to_turn_end opp)
        # react="learned" ('learned-rl'): the opponent's answers come from the one-sample learned AI instead
        self.opp_react = (LearnedGreedy(net, seed=seed + 433, samples=1) if react == "learned"
                          else GreedyPolicy(seed + 433, samples=1) if react else None)
        self.deep, self.margin, self.deep_samples = deep, margin, deep_samples
        self.opp = LearnedGreedy(net, seed=seed + 577, samples=1) if deep else None
        self.deep_calls = 0
        # recorder (tools/policy_data.py --values): a list that gets (features of each one-turn sample, two-turn win
        # probability) per searched candidate, to train a one-turn judge on the two-turn search's values
        self.recorder = None

    def evaluate(self, game, d, opts):
        vals = []
        window = (self.window is not None and d.kind == "action" and game.turn_player != d.player
                  and any(isinstance(x, tuple) and x[0] not in ("pass", "end_turn") for x in opts))
        if window:
            self.window_calls += 1
        rec = [] if self.recorder is not None else None
        for o in opts:
            v = 0.0
            if rec is not None:
                rec.append([])
            for _ in range(self.samples):
                g = determinize(game, d.player, self.rng)
                if g.pending is not None and o in g.pending.options:
                    g.choose(o)
                if window:
                    opponent_turn(g, d.player, self.window, respond=self.helper)
                else:
                    to_turn_end(g, d.player, self.helper, opp=self.opp_react)
                v += self.net.predict(g, d.player)
                if rec is not None and not g.over:
                    rec[-1].append(encode(g, d.player))
            v = 1000.0 * (v / self.samples - 0.5) + self.rng.random() * self.noise
            vals.append(v)
        if self.pnet is not None and d.kind == "action" and len(opts) >= 2:
            mine = game.turn_player == d.player
            real = any(isinstance(x, tuple) and x[0] not in ("pass", "end_turn") for x in opts)
            if mine or real:
                self.p_calls += 1
                order = sorted(range(len(opts)), key=lambda i: -vals[i])
                cand = order[:self.pk]
                for i, o in enumerate(opts):
                    if o in (("end_turn",), ("pass",)) and i not in cand:
                        cand.append(i)
                me, them = self.pnet
                if self.adapt:
                    return self._adaptive_deep(game, d, opts, vals, cand, mine, me, them)
                seeds = [self.rng.random() for _ in range(self.deep_samples)]
                for i in cand:
                    v = 0.0
                    for j in range(self.deep_samples):
                        if self.crn:
                            g = determinize(game, d.player, random.Random(seeds[j]))
                            _reseed((me, them, self.helper), seeds[j])
                        else:
                            g = determinize(game, d.player, self.rng)
                        if g.pending is not None and opts[i] in g.pending.options:
                            g.choose(opts[i])
                        if mine:
                            to_turn_end(g, d.player, self.helper, opp=them)
                        if not g.over:
                            opponent_turn(g, d.player, them, respond=me)
                        v += self.net.predict(g, d.player)
                    dv = 1000.0 * (v / self.deep_samples - 0.5)
                    if rec is not None and rec[i]:
                        self.recorder.append((rec[i], v / self.deep_samples))
                    vals[i] = 1e6 + dv if self.blend is None else vals[i] + self.blend * (dv - vals[i])
                return vals
        if (self.hold and d.kind == "action" and len(opts) >= 2 and game.turn_player == d.player
                and _fast_in_hand(game, d.player)):
            self.hold_calls += 1
            order = sorted(range(len(opts)), key=lambda i: -vals[i])
            cand = order[:self.hold_k]
            for i, o in enumerate(opts):
                if o == ("end_turn",) and i not in cand:
                    cand.append(i)
            for i in cand:
                v = 0.0
                for _ in range(self.deep_samples):
                    g = determinize(game, d.player, self.rng)
                    if g.pending is not None and opts[i] in g.pending.options:
                        g.choose(opts[i])
                    to_turn_end(g, d.player, self.helper)
                    if not g.over:
                        opponent_turn(g, d.player, self.hold_opp, respond=self.helper)
                    v += self.net.predict(g, d.player)
                vals[i] = 1e6 + 1000.0 * (v / self.deep_samples - 0.5)
            return vals
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


    def _sample_deep(self, game, d, o, mine, me, them, seed):
        g = determinize(game, d.player, random.Random(seed))
        _reseed((me, them, self.helper), seed)
        if g.pending is not None and o in g.pending.options:
            g.choose(o)
        if mine:
            to_turn_end(g, d.player, self.helper, opp=them)
        if not g.over:
            opponent_turn(g, d.player, them, respond=me)
        return self.net.predict(g, d.player)

    def _adaptive_deep(self, game, d, opts, vals, cand, mine, me, them):
        """`aN` (with crn): N shared samples per candidate first; while the best two blended values are within
        `adapt_gap` (in 1000 x win-probability units), two more shared samples each, up to `deep_samples`.
        Clear decisions stop early, close ones get the full count."""
        shallow = {i: vals[i] for i in cand}
        sums = {i: 0.0 for i in cand}
        seeds = []

        def blended(i):
            dv = 1000.0 * (sums[i] / len(seeds) - 0.5)
            return 1e6 + dv if self.blend is None else shallow[i] + self.blend * (dv - shallow[i])
        while len(seeds) < self.deep_samples:
            step = self.adapt if not seeds else 2
            for _ in range(min(step, self.deep_samples - len(seeds))):
                sd = self.rng.random()
                seeds.append(sd)
                for i in cand:
                    sums[i] += self._sample_deep(game, d, opts[i], mine, me, them, sd)
            b = sorted((blended(i) for i in cand), reverse=True)
            if len(b) < 2 or b[0] - b[1] >= self.adapt_gap:
                break
        self.p_samples = getattr(self, "p_samples", 0) + len(seeds)
        for i in cand:
            vals[i] = blended(i)
        return vals


class PrunedLearned(LearnedGreedy):
    """One-sample learned AI that only judges the policy net's `top` most likely options (plus passing / ending the
    turn): an opponent model for the two-turn search close to the learned AI's strength at a fraction of its cost."""

    def __init__(self, net, pnet, top=3, seed=0):
        super().__init__(net, seed=seed, samples=1)
        self.pn, self.top = pnet, top

    def choose(self, game, d):
        opts = ai_options(d, game)
        if d.kind == "mulligan":
            return mulligan_choice(game, d)
        if len(opts) == 1 or d.kind == "pay":
            return opts[0]
        if len(opts) > self.top:
            pr = self.pn.probs(game, d, opts)
            order = sorted(range(len(opts)), key=lambda i: -pr[i])[:self.top]
            keep = [opts[i] for i in order]
            for o in (("pass",), ("end_turn",)):
                if o in opts and o not in keep:
                    keep.append(o)
            opts = keep
        vals = LearnedGreedy.evaluate(self, game, d, opts)
        return opts[max(range(len(opts)), key=lambda i: vals[i])]


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
            if f.startswith("p="):
                pr = f[2:]
                kw["pnet"] = pr if (pr.endswith(".json") or os.path.sep in pr) else os.path.join(M.MODELS_DIR, pr + ".json")
            elif f.startswith("ps") and f[2:].isdigit():
                kw["pstrong"] = int(f[2:])
            elif f.startswith("a") and f[1:].isdigit():
                kw["adapt"] = int(f[1:])
            elif f.startswith("g") and f[1:].replace(".", "", 1).isdigit():
                kw["adapt_gap"] = float(f[1:])
            elif f == "crn":
                kw["crn"] = True
            elif f.startswith("b=") :
                kw["blend"] = float(f[2:])
            elif f.startswith("d") and f[1:].isdigit():
                kw["deep_samples"] = int(f[1:])
            elif f.startswith("k") and f[1:].isdigit():
                kw["pk"] = int(f[1:])
            elif f == "hold" or f.startswith("hold") and f[4:].isdigit():
                kw["hold"] = True
                if f[4:]:
                    kw["hold_k"] = int(f[4:])
            elif f in ("rw", "rwl"):
                kw["window"] = "learned" if f == "rwl" else "greedy"
            elif f.startswith("s"):
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
