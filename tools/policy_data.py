"""Record what the lookahead AI chooses, with every option it chose from (AI v2 step 1, docs/plans/ai_v2.md).

Per decision with two or more options (payments and mulligans excluded): the decider's position features
(features.encode, own seat only), the option features of every option (policy_net.encode_option), the index the AI
picked, the seat and the decision kind; per game the winner. tools/train_policy.py trains the policy net on it.

usage:
  python tools/policy_data.py --policy learned:gen_014 --games 1500 --out out/pol_g14.npz
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

KINDS = ("action", "choose", "assign_damage", "yesno", "order_triggers", "choose_location", "additional_cost", "other")


def _game(args):
    paths, seed, spec = args
    from riftsim.core.deck import Deck
    from riftsim.core.game import Game
    from riftsim.core.learn.features import encode
    from riftsim.core.learn.policy_net import encode_option
    from riftsim.core.policies import ai_options, make_policy, mulligan_choice
    db = T._db()
    decks = [Deck.load(p, db) for p in paths]
    pols = [make_policy(spec, seed=seed * 7 + i) for i in range(2)]
    g = Game(db, decks, seed=seed, log=False)
    g.max_turns = 60
    xs, phis, nopt, pick, seat, kind = [], [], [], [], [], []
    t = time.time()
    while True:
        d = g.run()
        if d is None:
            break
        opts = ai_options(d, g)
        if d.kind == "pay":
            g.choose(opts[0]); continue
        if d.kind == "mulligan":
            g.choose(mulligan_choice(g, d)); continue
        if len(opts) == 1:
            g.choose(opts[0]); continue
        o = pols[d.player].choose(g, d)
        if o in opts:
            xs.append(encode(g, d.player))
            phis += [encode_option(g, d.player, d, q) for q in opts]
            nopt.append(len(opts))
            pick.append(opts.index(o))
            seat.append(d.player)
            kind.append(KINDS.index(d.kind) if d.kind in KINDS else len(KINDS) - 1)
        g.choose(o)
    return {"x": xs, "phi": phis, "n": nopt, "pick": pick, "seat": seat, "kind": kind, "winner": g.winner,
            "secs": time.time() - t}


def _timed(args):
    return T._timed(_game, args, int(os.environ.get("RIFTSHARK_GAME_LIMIT", 3600)))


def main():
    import numpy as np
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="learned:gen_014")
    ap.add_argument("--games", type=int, default=1500)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7000000)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--max-minutes", type=float)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    jobs = []
    for i in range(a.games // 2):
        pair = rng.sample(T.DECKS, 2)
        jobs.append((pair, a.seed + 2 * i, a.policy))
        jobs.append((pair[::-1], a.seed + 2 * i + 1, a.policy))
    keys = ("x", "phi", "n", "pick", "seat", "kind", "game", "res")
    acc = {k: [] for k in keys}
    part = a.out + ".partial.npz"
    start = 0
    if os.path.exists(part):
        d = np.load(part)
        acc = {k: [d[k]] for k in keys}
        start = int(d["done"])
        print(f"resuming at game {start}", file=sys.stderr)

    def save(path, done=None):
        arrs = {k: (np.concatenate(acc[k]) if acc[k] else np.zeros((0,), np.float32)).astype(
            np.float32 if k in ("x", "phi", "res") else np.int32) for k in keys}
        if done is None:
            np.savez_compressed(path, **arrs)
        else:
            np.savez(path, done=done, **arrs)
    t = time.time()
    ex = ProcessPoolExecutor(max_workers=a.workers)
    try:
        for k, r in enumerate(ex.map(_timed, jobs[start:]), start):
            if a.max_minutes and time.time() - t > a.max_minutes * 60:
                print(f"time budget reached after {k} games", file=sys.stderr)
                break
            if not r.get("timeout") and r["n"]:
                for key in ("x", "phi"):
                    acc[key].append(np.array(r[key], dtype=np.float32))
                for key in ("n", "pick", "seat", "kind"):
                    acc[key].append(np.array(r[key], dtype=np.int32))
                acc["game"].append(np.full(len(r["n"]), k, dtype=np.int32))
                w = r["winner"]
                acc["res"].append(np.array([0.5 if w is None else (1.0 if s == w else 0.0) for s in r["seat"]],
                                           dtype=np.float32))
            if (k + 1) % 20 == 0:
                print(f"policy data {k + 1}/{len(jobs)} games, {sum(len(v) for v in acc['n'])} decisions ({time.time() - t:.0f}s)",
                      file=sys.stderr)
            if (k + 1) % 10 == 0:
                save(part, done=k + 1)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    save(a.out)
    if os.path.exists(part):
        os.remove(part)
    print(json.dumps({"decisions": sum(len(v) for v in acc["n"]), "options": sum(len(v) for v in acc["phi"]),
                      "secs": round(time.time() - t)}))


if __name__ == "__main__":
    main()
