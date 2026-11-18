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
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_loop as T   # noqa: E402

KINDS = ("action", "choose", "assign_damage", "yesno", "order_triggers", "choose_location", "additional_cost", "other")


def _game(args):
    paths, seed, spec = args[:3]
    values = len(args) > 3 and args[3]
    from riftsim.core.deck import Deck
    from riftsim.core.game import Game
    from riftsim.core.learn.features import encode
    from riftsim.core.learn.policy_net import encode_option
    from riftsim.core.policies import ai_options, make_policy, mulligan_choice
    db = T._db()
    decks = [Deck.load(p, db) for p in paths]
    pols = [make_policy(spec, seed=seed * 7 + i) for i in range(2)]
    if values:
        for q in pols:
            q.recorder = []
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
    vx, vy = [], []
    for q in (pols if values else ()):
        for rows, y in q.recorder:
            vx += rows
            vy += [y] * len(rows)
    return {"x": xs, "phi": phis, "n": nopt, "pick": pick, "seat": seat, "kind": kind, "winner": g.winner,
            "vx": vx, "vy": vy, "secs": time.time() - t}


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
    ap.add_argument("--values", action="store_true",
                    help="also record the two-turn search's value of each searched candidate (vx: features of each "
                         "one-turn sample, vy: two-turn win probability, vgame) to train a judge on")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    jobs = []
    for i in range(a.games // 2):
        pair = rng.sample(T.DECKS, 2)
        jobs.append((pair, a.seed + 2 * i, a.policy, a.values))
        jobs.append((pair[::-1], a.seed + 2 * i + 1, a.policy, a.values))
    keys = ("x", "phi", "n", "pick", "seat", "kind", "game", "res") + (("vx", "vy", "vgame") if a.values else ())
    acc = {k: [] for k in keys}
    part = a.out + ".partial.npz"
    done_idx = set()
    if os.path.exists(part):
        d = np.load(part)
        acc = {k: ([d[k]] if len(d[k]) else []) for k in keys}
        done_idx = set(d["done_idx"].tolist()) if "done_idx" in d else set(range(int(d["done"])))
        print(f"resuming with {len(done_idx)} games done", file=sys.stderr)

    def save(path, partial=False):
        arrs = {k: (np.concatenate(acc[k]) if acc[k] else np.zeros((0,), np.float32)).astype(
            np.float32 if k in ("x", "phi", "res", "vx", "vy") else np.int32) for k in keys}
        if not partial:
            np.savez_compressed(path, **arrs)
            return
        tmp = path + ".tmp.npz"            # a restart during the write must not destroy the last checkpoint
        np.savez(tmp, done=len(done_idx), done_idx=np.array(sorted(done_idx), np.int32), **arrs)
        os.replace(tmp, path)
    t = time.time()
    ex = ProcessPoolExecutor(max_workers=a.workers)
    # games finish in any order; each one is checkpointed as it finishes, so a container restart loses only the
    # games still running (in order, one long game held back every later result and a restart lost them all)
    futs = {ex.submit(_timed, jobs[k]): k for k in range(len(jobs)) if k not in done_idx}
    try:
        for f in as_completed(futs):
            k, r = futs[f], f.result()
            if a.max_minutes and time.time() - t > a.max_minutes * 60:
                print(f"time budget reached after {len(done_idx)} games", file=sys.stderr)
                break
            if not r.get("timeout") and r["n"]:
                for key in ("x", "phi"):
                    acc[key].append(np.array(r[key], dtype=np.float32))
                for key in ("n", "pick", "seat", "kind"):
                    acc[key].append(np.array(r[key], dtype=np.int32))
                acc["game"].append(np.full(len(r["n"]), k, dtype=np.int32))
                if a.values and r["vy"]:
                    acc["vx"].append(np.array(r["vx"], dtype=np.float32))
                    acc["vy"].append(np.array(r["vy"], dtype=np.float32))
                    acc["vgame"].append(np.full(len(r["vy"]), k, dtype=np.int32))
                w = r["winner"]
                acc["res"].append(np.array([0.5 if w is None else (1.0 if s == w else 0.0) for s in r["seat"]],
                                           dtype=np.float32))
            done_idx.add(k)
            if len(done_idx) % 20 == 0:
                print(f"policy data {len(done_idx)}/{len(jobs)} games, {sum(len(v) for v in acc['n'])} decisions ({time.time() - t:.0f}s)",
                      file=sys.stderr)
            save(part, partial=True)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    save(a.out)
    if os.path.exists(part):
        os.remove(part)
    print(json.dumps({"decisions": sum(len(v) for v in acc["n"]), "options": sum(len(v) for v in acc["phi"]),
                      "secs": round(time.time() - t)}))


if __name__ == "__main__":
    main()
