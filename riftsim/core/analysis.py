"""Move analysis ("coach"): rate every legal option at a decision and grade the one a player took,
chess-engine style. Scores are win probabilities estimated by MCTS (PIMC determinisation + rollouts).

Grades by win-probability loss against the best option:
  best <= 1pt, good <= 3, inaccuracy <= 7, mistake <= 15, blunder > 15 (percentage points)."""
from __future__ import annotations

import random

from .policies import MCTSPolicy, GreedyPolicy, _advance_default, heuristic

GRADES = [(1.0, "best"), (3.0, "good"), (7.0, "inaccuracy"), (15.0, "mistake"), (1e9, "blunder")]


def grade_for(loss_pct):
    for lim, name in GRADES:
        if loss_pct <= lim:
            return name
    return "blunder"


def analyze(game, d, iterations=300, seed=0, max_branch=40):
    """Return a dict with per-option win% and the recommended option.
    {'options': [{'index', 'label', 'option', 'win_pct', 'visits'} sorted best first], 'best': {...}}"""
    opts = list(d.options)
    out = []
    if len(opts) == 1:
        out.append({"index": 0, "label": d.labels[0], "option": opts[0], "win_pct": None, "visits": 0})
        return {"options": out, "best": out[0], "iterations": 0}
    pol = MCTSPolicy(iterations=iterations, seed=seed, max_branch=max_branch)
    root = pol.search(game, d)
    stats = {}
    for ch in root.children:
        if ch.visits:
            stats[ch.option] = (ch.visits, ch.value / ch.visits)
    # options the search never visited get a one-ply greedy estimate so every move has a number
    rng = random.Random(seed)
    for i, o in enumerate(opts):
        if o in stats:
            visits, v = stats[o]
        else:
            g = game.clone()
            g.choose(o)
            _advance_default(g, d.player, rollout_rng=rng)
            import math
            visits, v = 0, math.tanh(heuristic(g, d.player) / 150.0)
        out.append({"index": i, "label": d.labels[i], "option": o, "win_pct": round(50.0 * (v + 1.0), 1), "visits": visits})
    # rank by win% but break near-ties by visit count (more visits = more reliable)
    out.sort(key=lambda x: (-(x["win_pct"] or 0), -x["visits"]))
    return {"options": out, "best": out[0], "iterations": iterations}


def grade_choice(analysis, chosen_option):
    """Grade a chosen option against the analysis: returns dict(grade, loss_pct, win_pct, best_label, best_win_pct, rank)."""
    opts = analysis["options"]
    best = analysis["best"]
    mine = next((o for o in opts if o["option"] == chosen_option), None)
    if mine is None or mine["win_pct"] is None or best["win_pct"] is None:
        return {"grade": "only move", "loss_pct": 0.0, "win_pct": mine["win_pct"] if mine else None,
                "best_label": best["label"], "best_win_pct": best["win_pct"], "rank": 1, "of": len(opts)}
    loss = max(0.0, best["win_pct"] - mine["win_pct"])
    rank = opts.index(mine) + 1
    return {"grade": grade_for(loss), "loss_pct": round(loss, 1), "win_pct": mine["win_pct"], "best_label": best["label"],
            "best_win_pct": best["win_pct"], "rank": rank, "of": len(opts)}


def review_replay(db, rep, player, iterations=200, decks=None):
    """Grade every decision `player` made in a recorded replay. Yields dicts per decision."""
    from .deck import Deck
    from .game import Game
    from .replay import _unjson
    decks = decks or [Deck.from_dict(x, db) for x in rep["decks"]]
    g = Game(db, decks, seed=rep["seed"])
    choices = _unjson(rep["choices"])
    for i, ch in enumerate(choices):
        d = g.run()
        if d is None:
            break
        if d.player == player and len(d.options) > 1:
            an = analyze(g, d, iterations=iterations, seed=i)
            yield {"choice": i, "turn": g.turn, "kind": d.kind, "label": d.labels[d.options.index(ch)], **grade_choice(an, ch),
                   "alternatives": [{"label": o["label"], "win_pct": o["win_pct"]} for o in an["options"][:5]]}
        g.choose(ch)
