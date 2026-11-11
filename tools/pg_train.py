"""Policy-gradient training of the learned judge: learn from the moves the AI actually chose and how those games ended.

Every result since gen 8 says the same thing (docs/results/training_2026-11-10.md): a judge that predicts results
better does not choose better, because predicting who wins and ranking the options of one decision are different
jobs. This trains the second job directly (REINFORCE on the linear judge):

  The AI judges every option of a decision exactly as `learned:REF` does (determinised copies, the turn ended by
  to_turn_end, the judge's logit at the start of the next turn, averaged over samples). Instead of always taking the
  best, it samples from softmax(logit / T). Saved per decision: grad = z(chosen) - sum_o pi(o) z(o) (the gradient of
  log pi(chosen) w.r.t. the judge's weights, times T; z = standardised features plus the hand-written score's atanh)
  and the value of the chosen option. At the end of the game, advantage = result - value, and the weights move by
  lr * mean(advantage * grad) / T. Moves that led to more wins than the judge expected get a higher score next time.

The AI never sees hidden information: every judged copy is a policies.determinize copy, as in the learned AI.

usage:
  python tools/pg_train.py collect --model gen_014 --games 600 --out out/pg_1.npz
  python tools/pg_train.py update out/pg_1.npz --model gen_014 --out models/cand_pg1.json --lr 0.5 --mask 106-233
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_loop as T   # noqa: E402


def _pg_game(args):
    paths, seed, ref, temp, samples = args
    from riftsim.core.deck import Deck
    from riftsim.core.game import Game
    from riftsim.core.learn import model as M
    from riftsim.core.learn.features import encode
    from riftsim.core.learn.policy import _resolve, to_turn_end
    from riftsim.core.policies import GreedyPolicy, ai_options, determinize, mulligan_choice, prune_options
    db = T._db()
    decks = [Deck.load(p, db) for p in paths]
    net = M.load(_resolve(ref))
    W = len(net.mean)
    hi = net.h_index
    rng = random.Random(seed * 17 + 3)
    helpers = [GreedyPolicy(seed * 7 + 991 + i, samples=1) for i in range(2)]
    g = Game(db, decks, seed=seed, log=False)
    g.max_turns = 60
    grads, vals, seats = [], [], []
    t = time.time()

    def judge(h, p):
        """(logit, z vector or None for a finished game) of position h from p's seat."""
        if h.over:
            r = 0.5 if h.winner is None else (1.0 if h.winner == p else 0.0)
            return (8.0 if r == 1.0 else -8.0 if r == 0.0 else 0.0), None
        x = encode(h, p)[:W]
        z = [(v - m) / s for v, m, s in zip(x, net.mean, net.std)]
        a = math.atanh(max(-0.999999, min(0.999999, x[hi])))
        lo = net.b2 + net.h_scale * a + sum(c * q for c, q in zip(net.lin, z))
        return lo, z + [a]

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
        opts = prune_options(opts, 24, rng)
        p = d.player
        los, zs = [], []
        for o in opts:
            lsum, zsum, zn = 0.0, [0.0] * (W + 1), 0
            for _ in range(samples):
                h = determinize(g, p, rng)
                if h.pending is not None and o in h.pending.options:
                    h.choose(o)
                to_turn_end(h, p, helpers[p])
                lo, z = judge(h, p)
                lsum += lo
                if z is not None:
                    zn += 1
                    for i, q in enumerate(z):
                        zsum[i] += q
            los.append(lsum / samples)
            # finished games are exact (no gradient): their share of the samples counts as a zero feature vector
            zs.append([q / samples for q in zsum])
        top = max(los)
        ws = [math.exp(max(-50.0, (lo - top) / temp)) for lo in los]
        tot = sum(ws)
        pi = [w / tot for w in ws]
        r = rng.random()
        k = len(opts) - 1
        for i, w in enumerate(pi):
            r -= w
            if r <= 0:
                k = i
                break
        mean_z = [sum(pi[i] * zs[i][j] for i in range(len(opts))) for j in range(W + 1)]
        grads.append([a - b for a, b in zip(zs[k], mean_z)])
        vals.append(1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, los[k])))))
        seats.append(p)
        g.choose(opts[k])
    if g.winner is None:
        return {"grad": [], "val": [], "res": [], "secs": time.time() - t}
    return {"grad": grads, "val": vals, "res": [1.0 if s == g.winner else 0.0 for s in seats],
            "secs": time.time() - t}


def _pg_timed(args):
    return T._timed(_pg_game, args, 3600)


def collect(a):
    import numpy as np
    rng = random.Random(a.seed)
    jobs = []
    for i in range(a.games // 2):
        pair = rng.sample(T.DECKS, 2)
        jobs.append((pair, a.seed + 2 * i, a.model, a.temp, a.samples))
        jobs.append((pair[::-1], a.seed + 2 * i + 1, a.model, a.temp, a.samples))
    part = a.out + ".partial.npz"
    G, V, R, N = [], [], [], []
    start = 0
    if os.path.exists(part):
        d = np.load(part)
        G, V, R, N = d["grad"].tolist(), d["val"].tolist(), d["res"].tolist(), d["game"].tolist()
        start = int(d["done"])
        print(f"resuming at game {start}", file=sys.stderr)
    t = time.time()

    def save(path, done=None):
        arrs = dict(grad=np.array(G, dtype=np.float32), val=np.array(V, dtype=np.float32),
                    res=np.array(R, dtype=np.float32), game=np.array(N, dtype=np.int32))
        if done is None:
            np.savez_compressed(path, **arrs)
        else:
            np.savez(path, done=done, **arrs)
    ex = ProcessPoolExecutor(max_workers=a.workers)
    try:
        for k, r in enumerate(ex.map(_pg_timed, jobs[start:]), start):
            if a.max_minutes and time.time() - t > a.max_minutes * 60:
                print(f"time budget reached after {k} games", file=sys.stderr)
                break
            if not r.get("timeout"):
                G += r["grad"]; V += r["val"]; R += r["res"]; N += [k] * len(r["res"])
            if (k + 1) % 20 == 0:
                print(f"pg {k + 1}/{len(jobs)} games, {len(R)} decisions ({time.time() - t:.0f}s)", file=sys.stderr)
            if (k + 1) % 10 == 0:
                save(part, done=k + 1)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    save(a.out)
    if os.path.exists(part):
        os.remove(part)
    print(json.dumps({"games": len(set(N)), "decisions": len(R), "secs": round(time.time() - t)}))


def update(a):
    import numpy as np
    from riftsim.core.learn.policy import _resolve
    with open(_resolve(a.model)) as f:
        m = json.load(f)
    Gs, As = [], []
    for fn in a.files:
        d = np.load(fn)
        Gs.append(d["grad"].astype(np.float64))
        As.append(d["res"].astype(np.float64) - d["val"].astype(np.float64))
    G, A = np.concatenate(Gs), np.concatenate(As)
    W = len(m["lin"])
    mask = [i for r in (a.mask or "").split(",") if r for i in range(int(r.split("-")[0]), int(r.split("-")[-1]) + 1)]
    step = (A[:, None] * G).mean(0) / a.temp          # gradient of mean(advantage * log pi(chosen))
    # standard error per weight, to report how much of the step is signal
    se = (A[:, None] * G).std(0) / a.temp / math.sqrt(len(A))
    step[mask] = 0.0
    if a.min_snr:                                    # move only the weights whose step is clear of the noise
        step[np.abs(step) / (se + 1e-12) < a.min_snr] = 0.0
    lin = np.array(m["lin"], dtype=np.float64)
    norm = float(np.linalg.norm(step))
    scale = a.lr / norm if a.normalize and norm > 0 else a.lr
    lin += scale * step[:W]
    m["lin"] = lin.tolist()
    m["h_scale"] = float(m["h_scale"] + scale * step[W])
    snr = np.abs(step) / (se + 1e-12)
    m.setdefault("meta", {})
    m["meta"] = dict(m["meta"], pg={"files": [os.path.basename(f) for f in a.files], "decisions": int(len(A)),
                                    "lr": a.lr, "normalize": a.normalize, "temp": a.temp, "step_norm": norm,
                                    "weights_moved_2se": int((snr > 2).sum()), "base": a.model})
    with open(a.out, "w") as f:
        json.dump(m, f, separators=(",", ":"))
    top = np.argsort(-snr)[:10]
    print(json.dumps({"decisions": int(len(A)), "mean_adv": round(float(A.mean()), 4), "step_norm": round(norm, 4),
                      "applied": round(scale * norm, 4), "weights_moved_2se": int((snr > 2).sum()),
                      "top": [[int(i), round(float(step[i]), 4), round(float(snr[i]), 1)] for i in top]}))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--model", default="gen_014")
    c.add_argument("--games", type=int, default=600)
    c.add_argument("--out", required=True)
    c.add_argument("--temp", type=float, default=0.1, help="softmax temperature on the judge's logit")
    c.add_argument("--samples", type=int, default=2)
    c.add_argument("--seed", type=int, default=6000000)
    c.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    c.add_argument("--max-minutes", type=float)
    u = sub.add_parser("update")
    u.add_argument("files", nargs="+")
    u.add_argument("--model", default="gen_014")
    u.add_argument("--out", required=True)
    u.add_argument("--lr", type=float, default=0.3)
    u.add_argument("--normalize", action="store_true", help="lr is the length of the step (weights are standardised)")
    u.add_argument("--temp", type=float, default=0.1)
    u.add_argument("--mask", default="106-233")
    u.add_argument("--min-snr", type=float, default=0.0, help="zero the step of weights under this many std errors")
    a = ap.parse_args()
    collect(a) if a.cmd == "collect" else update(a)


if __name__ == "__main__":
    main()
