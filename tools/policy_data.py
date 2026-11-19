"""Record what the lookahead AI chooses, with every option it chose from (AI v2 step 1, docs/plans/ai_v2.md).

Per decision with two or more options (payments and mulligans excluded): the decider's position features
(features.encode, own seat only), the option features of every option (policy_net.encode_option), the index the AI
picked, the seat and the decision kind; per game the winner. tools/train_policy.py trains the policy net on it.
Also both seats' features at every turn boundary and at what-if boundaries (bkind 1: the decider ends the turn
here, one action decision in three) (bx, bseat, bkind, bgame, bres): the judge's training positions, unlike
the mid-turn decision positions in x (a judge trained on those plays far worse: 11% vs gen 14, 2026-11-19).

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
    bx, bseat, bkind, last_turn = [], [], [], None
    from riftsim.core.learn.policy import to_turn_end
    from riftsim.core.policies import GreedyPolicy, determinize
    helper = GreedyPolicy(seed + 991, samples=1)
    wrng = random.Random(seed * 13 + 5)          # own generator: the what-ifs never change the game itself
    t = time.time()
    while True:
        d = g.run()
        if d is None:
            break
        if g.turn != last_turn:             # a turn boundary, both seats: the positions the judge is trained on
            last_turn = g.turn
            for s in (0, 1):
                bx.append(encode(g, s))
                bseat.append(s)
                bkind.append(0)
        elif d.kind == "action" and wrng.random() < 1.0 / 3:
            # what-if boundary (as in train_loop self-play): the decider ends the turn here, on a copy where the
            # opponent's hidden cards are a sample from the decider's view; labelled with the game's result
            h = determinize(g, d.player, wrng)
            to_turn_end(h, d.player, helper)
            if not h.over:
                for s in (0, 1):
                    bx.append(encode(h, s))
                    bseat.append(s)
                    bkind.append(1)
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
    vx, vy, vdec, vopt, vpo = [], [], [], [], []
    for qs, q in enumerate(pols if values else ()):
        for rows, y, dec, opt in q.recorder:
            vx += rows
            vy += [y] * len(rows)
            vdec += [qs * 100000 + dec] * len(rows)     # one searched decision of one seat
            vopt += [opt] * len(rows)                     # its candidate
            vpo += list(range(len(rows)))                 # which one-turn sample
    return {"x": xs, "phi": phis, "n": nopt, "pick": pick, "seat": seat, "kind": kind, "winner": g.winner,
            "vx": vx, "vy": vy, "vdec": vdec, "vopt": vopt, "vpo": vpo, "bx": bx, "bseat": bseat, "bkind": bkind,
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
    ap.add_argument("--values", action="store_true",
                    help="also record the two-turn search's value of each searched candidate (vx: features of each "
                         "one-turn sample, vy: two-turn win probability, vgame; vdec/vopt/vpo: decision (per game), "
                         "candidate and sample ids, -1 for games recorded before them) to train a judge on")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    jobs = []
    for i in range(a.games // 2):
        pair = rng.sample(T.DECKS, 2)
        jobs.append((pair, a.seed + 2 * i, a.policy, a.values))
        jobs.append((pair[::-1], a.seed + 2 * i + 1, a.policy, a.values))
    keys = ("x", "phi", "n", "pick", "seat", "kind", "game", "res", "bx", "bseat", "bkind", "bgame", "bres") + (("vx", "vy", "vgame", "vdec", "vopt", "vpo") if a.values else ())
    acc = {k: [] for k in keys}
    part = a.out + ".partial.npz"
    done_idx = set()
    if os.path.exists(part):
        d = np.load(part)
        acc = {k: ([d[k]] if k in d and len(d[k]) else []) for k in keys}
        if a.values and "vdec" not in d and len(d["vy"]):    # recorded before decision ids: -1
            for key in ("vdec", "vopt", "vpo"):
                acc[key] = [np.full(len(d["vy"]), -1, np.int32)]
        done_idx = set(d["done_idx"].tolist()) if "done_idx" in d else set(range(int(d["done"])))
        print(f"resuming with {len(done_idx)} games done", file=sys.stderr)

    def save(path, partial=False):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        arrs = {k: (np.concatenate(acc[k]) if acc[k] else np.zeros((0,), np.float32)).astype(
            np.float32 if k in ("x", "phi", "res", "vx", "vy", "bx", "bres") else np.int32) for k in keys}
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
                    for key in ("vdec", "vopt", "vpo"):
                        acc[key].append(np.array(r[key], dtype=np.int32))
                w = r["winner"]
                acc["res"].append(np.array([0.5 if w is None else (1.0 if s == w else 0.0) for s in r["seat"]],
                                           dtype=np.float32))
                if r.get("bx"):
                    acc["bx"].append(np.array(r["bx"], dtype=np.float32))
                    acc["bseat"].append(np.array(r["bseat"], dtype=np.int32))
                    acc["bkind"].append(np.array(r["bkind"], dtype=np.int32))
                    acc["bgame"].append(np.full(len(r["bseat"]), k, dtype=np.int32))
                    acc["bres"].append(np.array([0.5 if w is None else (1.0 if s == w else 0.0) for s in r["bseat"]],
                                                dtype=np.float32))
            done_idx.add(k)
            if len(done_idx) % 20 == 0:
                print(f"policy data {len(done_idx)}/{len(jobs)} games, {sum(len(v) for v in acc['n'])} decisions ({time.time() - t:.0f}s)",
                      file=sys.stderr)
            save(part, partial=True)
            if a.max_minutes and time.time() - t > a.max_minutes * 60:
                print(f"time budget reached after {len(done_idx)} games", file=sys.stderr)
                break
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    save(a.out)
    if os.path.exists(part):
        os.remove(part)
    print(json.dumps({"decisions": sum(len(v) for v in acc["n"]), "options": sum(len(v) for v in acc["phi"]),
                      "secs": round(time.time() - t)}))
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)     # don't wait for games still running in the workers when the time budget ended the run


if __name__ == "__main__":
    main()
