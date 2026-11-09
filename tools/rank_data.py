"""Option-ranking data: label the options of one decision by how the game actually goes after each of them.

The value judge is trained to predict who wins from a position, but the AI uses it to rank the options of one
decision, and those are different jobs (docs/results/training_2026-11-09_overnight.md: a model that predicts results
clearly better than gen 8 still loses to it). This collects data for the second job directly:

  For a few sampled action decisions per self-play game (reaction windows in the opponent's turn sampled more often,
  because that is where held interaction is decided), every option (up to --options) is played on a copy
  determinised from the decider's view, the turn is ended exactly the way the greedy lookahead does it
  (policy.to_turn_end), and that turn-end position is what the judge sees. Then the game is played out to the end
  --playouts times with the playout AI on both sides. Playout j uses the same determinisation and the same random
  seed for every option (common random numbers), so two options of one decision are compared in the same possible
  world and differ only by the option.

Saved per (decision, option, playout): the decider's turn-end features and the playout result. train_loop's
`train --linear --pairs FILE` turns every playout where two options ended differently into a pairwise row
(features of the better option minus the worse one) next to the usual value rows.

The AI never sees hidden information: every option and playout runs on policies.determinize copies (the opponent's
hand and both deck orders are resampled from the decider's view).

usage:
  python tools/rank_data.py --games 200 --out /mnt/project-files/riftshark/learn/rank_1.npz [--policy learned:gen_008]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_loop as T   # noqa: E402


def _playout(h, pols, max_steps=6000):
    from riftsim.core.policies import ai_options, mulligan_choice
    for _ in range(max_steps):
        d = h.run()
        if d is None or h.over:
            break
        opts = ai_options(d, h)
        if d.kind == "pay":
            o = opts[0]
        elif d.kind == "mulligan":
            o = mulligan_choice(h, d)
        else:
            o = pols[d.player].choose(h, d)
        h.choose(o)
    return h.winner


def _rank_game(args):
    paths, seed, ref, opts_cap, playouts, per_game, p_own, p_react = args
    from riftsim.core.deck import Deck
    from riftsim.core.game import Game
    from riftsim.core.learn import model as M
    from riftsim.core.learn.features import encode
    from riftsim.core.learn.policy import LearnedGreedy, _resolve, to_turn_end
    from riftsim.core.policies import GreedyPolicy, ai_options, determinize, prune_options
    db = T._db()
    decks = [Deck.load(p, db) for p in paths]
    net = M.load(_resolve(ref))
    # the trajectory and playout AI: the learned greedy with one sample (about 3x faster than the 3-sample gate AI)
    traj = [LearnedGreedy(net, seed=seed * 7 + i, samples=1) for i in range(2)]
    helper = GreedyPolicy(seed + 991, samples=1)
    rng = random.Random(seed * 13 + 5)
    g = Game(db, decks, seed=seed, log=False)
    g.max_turns = 60
    rows = {"x": [], "y": [], "dec": [], "opt": [], "po": [], "react": []}
    done = 0
    t = time.time()
    while True:
        d = g.run()
        if d is None:
            break
        choice = traj[d.player].choose(g, d)
        if d.kind == "action" and done < per_game:
            opts = ai_options(d, g)
            real = [o for o in opts if o[0] not in ("pass", "end_turn")]
            react = d.player != g.turn_player
            if real and rng.random() < (p_react if react else p_own):
                done += 1
                cand = prune_options(opts, 60, rng)
                keep = [choice] + [o for o in (("end_turn",), ("pass",)) if o in cand and o != choice]
                rest = [o for o in cand if o not in keep]
                rng.shuffle(rest)
                cand = (keep + rest)[:opts_cap]
                dec_id = seed * 100 + done
                for j in range(playouts):
                    s = rng.randrange(1 << 30)
                    for k, o in enumerate(cand):
                        h = determinize(g, d.player, random.Random(s))
                        if h.pending is None or o not in h.pending.options:
                            continue
                        h.choose(o)
                        to_turn_end(h, d.player, GreedyPolicy(s + 1, samples=1))
                        x = encode(h, d.player)
                        if h.over:
                            r = 1.0 if h.winner == d.player else 0.0
                        else:
                            random.seed(s + 2)
                            pols = [LearnedGreedy(net, seed=s + 3 + i, samples=1) for i in range(2)]
                            w = _playout(h, pols)
                            r = 0.5 if w is None else (1.0 if w == d.player else 0.0)
                        rows["x"].append(x); rows["y"].append(r); rows["dec"].append(dec_id)
                        rows["opt"].append(k); rows["po"].append(j); rows["react"].append(int(react))
        g.choose(choice)
    rows["secs"] = time.time() - t
    return rows


def _rank_timed(args):
    return T._timed(_rank_game, args, LIMIT)


LIMIT = 3600


def main():
    import numpy as np
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="gen_008", help="value model of the trajectory and playout AI")
    ap.add_argument("--options", type=int, default=5)
    ap.add_argument("--playouts", type=int, default=4)
    ap.add_argument("--per-game", type=int, default=3, help="decisions labelled per game")
    ap.add_argument("--p-own", type=float, default=0.08, help="chance to label an own-turn action decision")
    ap.add_argument("--p-react", type=float, default=0.5, help="chance to label a reaction window with a real option")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--seed", type=int, default=5000000)
    ap.add_argument("--max-minutes", type=float)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    jobs = []
    for i in range(a.games):
        pair = rng.sample(T.DECKS, 2)
        jobs.append((pair, a.seed + i, a.model, a.options, a.playouts, a.per_game, a.p_own, a.p_react))
    part = a.out + ".partial.npz"
    keys = ("x", "y", "dec", "opt", "po", "react")
    acc = {k: [] for k in keys}
    start = 0
    if os.path.exists(part):
        d = np.load(part)
        acc = {k: d[k].tolist() for k in keys}
        start = int(d["done"])
        print(f"resuming at game {start}", file=sys.stderr)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    t = time.time()

    def save(path, done=None):
        arrs = {k: np.array(acc[k], dtype=np.float32 if k in ("x", "y") else np.int64) for k in keys}
        if done is not None:
            np.savez(path, done=done, **arrs)
        else:
            np.savez_compressed(path, **arrs)
    ex = ProcessPoolExecutor(max_workers=a.workers)
    try:
        for k, r in enumerate(ex.map(_rank_timed, jobs[start:]), start):
            if a.max_minutes and time.time() - t > a.max_minutes * 60:
                print(f"time budget reached after {k} games", file=sys.stderr)
                break
            if r.get("timeout"):
                print(f"rank game {r['args']} ran out of time, dropped", file=sys.stderr)
            else:
                for key in keys:
                    acc[key] += r[key]
            decs = len(set(acc["dec"]))
            if (k + 1) % 5 == 0:
                print(f"rank {k + 1}/{len(jobs)} games, {decs} decisions, {len(acc['y'])} rows "
                      f"({time.time() - t:.0f}s)", file=sys.stderr)
                save(part, done=k + 1)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    save(a.out)
    if os.path.exists(part):
        os.remove(part)
    print(json.dumps({"decisions": len(set(acc["dec"])), "rows": len(acc["y"]), "secs": round(time.time() - t)}))


if __name__ == "__main__":
    main()
