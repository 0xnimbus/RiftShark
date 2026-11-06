"""Self-play learning loop for the value network.

One generation:
  1. self-play: the best AI plays games between random pairs of tournament decks; every few decisions the position is
     encoded from both seats (riftsim.core.learn.features, own-seat information only) and labelled with the final winner
  2. train: a fresh value net (warm-started from the best one) learns P(win | position) on this generation's data plus
     the replay buffer of earlier generations
  3. gate: the candidate plays the best AI head to head (same decks and shuffles, seats swapped); it is promoted only if
     it scores at least --promote (default 55%)
Models are saved in models/ (gen_NNN.json, best.json, history.json, ladder.md); training data goes to --data
(default /mnt/project-files/riftshark/learn when it exists, else out/learn), never to git.

usage:
  python tools/train_loop.py generation [--games 600] [--gate-games 200] [--workers 4]
  python tools/train_loop.py selfplay --games 600 --out FILE.npz [--policy SPEC]
  python tools/train_loop.py train DATA.npz ... --out models/gen_XXX.json
  python tools/train_loop.py gate CANDIDATE_SPEC BEST_SPEC --games 200
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import math
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MODELS = os.path.join(ROOT, "models")
DECKS = sorted(glob.glob(os.path.join(ROOT, "data/decks/tournament/*.json")))
_DB = None


def _db():
    global _DB
    if _DB is None:
        from riftsim.core.cards import CardDB
        from riftsim.core.scripts import script_all
        _DB = script_all(CardDB.load())
    return _DB


def default_data_dir():
    shared = "/mnt/project-files/riftshark/"
    return os.path.join(shared, "learn") if os.path.isdir(shared) else os.path.join(ROOT, "out", "learn")


def best_spec():
    p = os.path.join(MODELS, "best.json")
    if not os.path.exists(p):
        return "expert"
    with open(p) as f:
        return json.load(f)["spec"]


class GameTimeout(Exception):
    pass


def _timed(fn, args, limit):
    """Run one game with a wall-clock limit (SIGALRM in the worker). A game that runs out of time is dropped from the
    data and reported, never shortened: the engine is not changed to make it fit. Seen 2026-11-06: one combat
    enumerating millions of legal damage assignments (flow._damage_plans) stalled self-play for 15+ minutes."""
    import signal

    def _raise(*_):
        raise GameTimeout()
    old = signal.signal(signal.SIGALRM, _raise)
    signal.alarm(limit)
    try:
        return fn(args)
    except GameTimeout:
        return {"timeout": True, "args": [os.path.basename(x) for x in args[0]] + [args[1]]}
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _selfplay_timed(args):
    return _timed(_selfplay_game, args, GAME_LIMIT)


def _gate_timed(args):
    return _timed(_gate_game, args, GAME_LIMIT)


GAME_LIMIT = 300

# ------------------------------------------------------------------------------------------------ self-play
def _selfplay_game(args):
    paths, seed, spec, every, epsilon = args
    from riftsim.core.deck import Deck
    from riftsim.core.game import Game
    from riftsim.core.learn.features import encode
    from riftsim.core.learn.policy import to_turn_end
    from riftsim.core.policies import GreedyPolicy, ai_options, determinize, make_policy
    db = _db()
    decks = [Deck.load(p, db) for p in paths]
    pols = [make_policy(spec, seed=seed * 7 + i) for i in range(2)]
    rng = random.Random(seed * 13 + 5)
    g = Game(db, decks, seed=seed, log=False)
    g.max_turns = 60
    xs, seats = [], []
    last_turn = None
    helper = GreedyPolicy(seed + 991, samples=1)
    t = time.time()
    while True:
        d = g.run()
        if d is None:
            break
        if g.turn != last_turn:
            # a real turn boundary: the moment the learned greedy AI judges its options at
            last_turn = g.turn
            for s in (0, 1):
                xs.append(encode(g, s))
                seats.append(s)
        elif d.kind == "action" and rng.random() < 1.0 / every:
            # what-if boundary: the deciding player ends the turn here; teaches the net the positions it is asked about
            h = determinize(g, d.player, rng)
            to_turn_end(h, d.player, helper)
            if not h.over:
                for s in (0, 1):
                    xs.append(encode(h, s))
                    seats.append(s)
        if d.kind == "action" and epsilon and rng.random() < epsilon:
            choice = rng.choice(ai_options(d, g))       # exploration: positions the best line would never reach
        else:
            choice = pols[d.player].choose(g, d)
        g.choose(choice)
    if g.winner is None:
        return {"x": [], "y": [], "winner": None, "secs": time.time() - t}
    return {"x": xs, "y": [1.0 if s == g.winner else 0.0 for s in seats], "winner": g.winner, "turns": g.turn,
            "secs": time.time() - t}


def selfplay(games, spec, out, workers, seed, every=3, epsilon=0.03):
    import numpy as np
    rng = random.Random(seed)
    jobs = []
    for i in range(games // 2):
        pair = rng.sample(DECKS, 2)
        jobs.append((pair, seed + 2 * i, spec, every, epsilon))
        jobs.append((pair[::-1], seed + 2 * i + 1, spec, every, epsilon))
    X, Y, G = [], [], []
    timeouts = []
    part = out + ".partial.npz"          # container restarts kill runs: resume from the last checkpoint
    start = 0
    if os.path.exists(part):
        d = np.load(part, allow_pickle=True)
        X, Y, G = d["x"].tolist(), d["y"].tolist(), d["game"].tolist()
        start, timeouts = int(d["done"]), json.loads(str(d["timeouts"]))
        print(f"resuming self-play at game {start}", file=sys.stderr)
    t = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for k, r in enumerate(ex.map(_selfplay_timed, jobs[start:]), start):
            if r.get("timeout"):
                timeouts.append(r["args"])
                print(f"self-play game {r['args']} ran out of time, dropped", file=sys.stderr)
            else:
                X += r["x"]
                Y += r["y"]
                G += [k] * len(r["y"])
            if (k + 1) % 20 == 0:
                print(f"self-play {k + 1}/{len(jobs)} games, {len(Y)} positions ({time.time() - t:.0f}s)", file=sys.stderr)
            if (k + 1) % 50 == 0:
                np.savez(part, x=np.array(X, dtype=np.float32), y=np.array(Y, dtype=np.float32),
                         game=np.array(G, dtype=np.int32), done=k + 1, timeouts=json.dumps(timeouts))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    np.savez_compressed(out, x=np.array(X, dtype=np.float32), y=np.array(Y, dtype=np.float32),
                        game=np.array(G, dtype=np.int32))
    if os.path.exists(part):
        os.remove(part)
    return len(jobs), len(Y), timeouts


# ------------------------------------------------------------------------------------------------ training
def train(files, out, hidden=48, epochs=40, lr=2e-3, l2=1e-3, seed=0, warm=None, meta=None):
    import numpy as np
    xs, ys, gs = [], [], []
    off = 0
    for f in files:
        d = np.load(f)
        xs.append(d["x"])
        ys.append(d["y"])
        gs.append(d["game"] + off)
        off = int(gs[-1].max()) + 1 if len(gs[-1]) else off
    X, Y, G = np.concatenate(xs), np.concatenate(ys), np.concatenate(gs)
    rs = np.random.RandomState(seed)
    games = np.unique(G)
    val_games = set(rs.choice(games, size=max(1, len(games) // 10), replace=False).tolist())
    vmask = np.array([g in val_games for g in G])
    Xt, Yt, Xv, Yv = X[~vmask], Y[~vmask], X[vmask], Y[vmask]
    mean = Xt.mean(0)
    std = Xt.std(0) + 1e-3
    Zt, Zv = (Xt - mean) / std, (Xv - mean) / std
    n_in = X.shape[1]
    if warm and len(warm["mean"]) == n_in and len(warm["b1"]) == hidden:
        W1, b1 = np.array(warm["w1"]), np.array(warm["b1"])
        W2, b2 = np.array(warm["w2"]), float(warm["b2"])
        # the warm net expects the old standardisation: fold it into the first layer
        om, os_ = np.array(warm["mean"]), np.array(warm["std"])
        W1 = W1 * (std / os_)[None, :]
        b1 = b1 + W1 @ ((mean - om) / std)
    else:
        W1 = rs.randn(hidden, n_in) * math.sqrt(1.0 / n_in)
        b1 = np.zeros(hidden)
        W2 = rs.randn(hidden) * math.sqrt(1.0 / hidden)
        b2 = 0.0
    params = [W1, b1, W2, np.array(b2)]
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]

    def forward(Z, P):
        H = np.tanh(Z @ P[0].T + P[1])
        o = H @ P[2] + P[3]
        return H, 1 / (1 + np.exp(-np.clip(o, -30, 30)))

    def loss(Z, Yy, P):
        _, pr = forward(Z, P)
        pr = np.clip(pr, 1e-6, 1 - 1e-6)
        return float(-(Yy * np.log(pr) + (1 - Yy) * np.log(1 - pr)).mean()), float(((pr > 0.5) == (Yy > 0.5)).mean())

    best = (loss(Zv, Yv, params)[0], [p.copy() for p in params])
    step = 0
    bs = 512
    stale = 0
    for ep in range(epochs):
        idx = rs.permutation(len(Zt))
        for s in range(0, len(idx), bs):
            b = idx[s:s + bs]
            Z, Yy = Zt[b], Yt[b]
            H, pr = forward(Z, params)
            go = (pr - Yy) / len(b)                       # d loss / d logit
            gW2 = H.T @ go + l2 * params[2]
            gb2 = go.sum()
            gH = np.outer(go, params[2]) * (1 - H ** 2)
            gW1 = gH.T @ Z + l2 * params[0]
            gb1 = gH.sum(0)
            step += 1
            for i, gr in enumerate((gW1, gb1, gW2, np.array(gb2))):
                m[i] = 0.9 * m[i] + 0.1 * gr
                v[i] = 0.999 * v[i] + 0.001 * gr ** 2
                params[i] = params[i] - lr * (m[i] / (1 - 0.9 ** step)) / (np.sqrt(v[i] / (1 - 0.999 ** step)) + 1e-8)
        vl, va = loss(Zv, Yv, params)
        if vl < best[0] - 1e-4:
            best = (vl, [p.copy() for p in params])
            stale = 0
        else:
            stale += 1
            if stale >= 5:
                break
        print(f"epoch {ep + 1}: val loss {vl:.4f} acc {va:.3f}", file=sys.stderr)
    params = best[1]
    tl, ta = loss(Zt, Yt, params)
    vl, va = loss(Zv, Yv, params)
    base = float(Yv.mean())
    base_loss = float(-(Yv * math.log(max(base, 1e-6)) + (1 - Yv) * math.log(max(1 - base, 1e-6))).mean())
    info = {"positions": int(len(Y)), "games": int(len(games)), "train_loss": round(tl, 4), "val_loss": round(vl, 4),
            "val_acc": round(va, 4), "val_loss_constant": round(base_loss, 4), "hidden": hidden,
            "warm_start": bool(warm and len(warm["mean"]) == n_in)}
    d = {"meta": dict(meta or {}, **info), "mean": mean.tolist(), "std": std.tolist(), "w1": params[0].tolist(),
         "b1": params[1].tolist(), "w2": params[2].tolist(), "b2": float(params[3])}
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump(d, f, separators=(",", ":"))
    return info


# ------------------------------------------------------------------------------------------------ gating
def _gate_game(args):
    paths, seed, specs = args
    from riftsim.core.deck import Deck
    from riftsim.core.policies import make_policy
    from riftsim.core.replay import play_game
    db = _db()
    decks = [Deck.load(p, db) for p in paths]
    pols = [make_policy(s, seed=seed * 11 + i) for i, s in enumerate(specs)]
    g, _ = play_game(db, decks, seed, pols, record=False, max_turns=60, log=False)
    return {"specs": specs, "winner": g.winner, "decks": [os.path.basename(p) for p in paths]}


def gate(cand, best, games, workers, seed):
    rng = random.Random(seed)
    jobs = []
    for i in range(games // 2):
        pair = rng.sample(DECKS, 2)
        s = seed + i
        jobs.append((pair, s, [cand, best]))
        jobs.append((pair, s, [best, cand]))     # same decks and shuffle, the two AIs swap seats
    wins = draws = 0
    per_deck = {}
    timeouts = []
    t = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for k, r in enumerate(ex.map(_gate_timed, jobs)):
            if r.get("timeout"):
                timeouts.append(r["args"])      # dropped from the score (neither AI is credited)
                continue
            if r["winner"] is None:
                draws += 1
            else:
                cs = r["specs"].index(cand)
                won = r["winner"] == cs
                wins += won
                dk = r["decks"][cs]
                w, n = per_deck.get(dk, (0, 0))
                per_deck[dk] = (w + won, n + 1)
            if (k + 1) % 20 == 0:
                print(f"gate {k + 1}/{len(jobs)}: candidate {wins} wins ({time.time() - t:.0f}s)", file=sys.stderr)
    n = len(jobs) - len(timeouts)
    score = (wins + 0.5 * draws) / n
    z = 1.96
    p = score
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    return {"candidate": cand, "best": best, "games": n, "wins": wins, "draws": draws, "score": round(score, 4),
            "interval": [round(centre - half, 3), round(centre + half, 3)], "per_deck": per_deck,
            "timeouts": timeouts}


# ------------------------------------------------------------------------------------------------ one generation
def generation(a):
    os.makedirs(MODELS, exist_ok=True)
    hist_path = os.path.join(MODELS, "history.json")
    hist = json.load(open(hist_path)) if os.path.exists(hist_path) else []
    gen = 1 + max([h["generation"] for h in hist] or [0])
    name = f"gen_{gen:03d}"
    data_dir = a.data or default_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    best = best_spec()
    t0 = time.time()
    data_file = os.path.join(data_dir, f"{name}.npz")
    if not os.path.exists(data_file):
        print(f"{name}: self-play {a.games} games with {best}", file=sys.stderr)
        sp = selfplay(a.games, best, data_file, a.workers, seed=a.seed + 100000 * gen)
        json.dump({"games": sp[0], "positions": sp[1], "timeouts": sp[2]}, open(data_file + ".info.json", "w"))
    t1 = time.time()
    buffer = sorted(glob.glob(os.path.join(data_dir, "gen_*.npz")))[-a.buffer:]
    warm = None
    bp = os.path.join(MODELS, "best.json")
    if os.path.exists(bp):
        warm = json.load(open(os.path.join(MODELS, json.load(open(bp))["model"])))
    out = os.path.join(MODELS, f"{name}.json")
    info = train(buffer, out, warm=warm, seed=gen,
                 meta={"generation": gen, "selfplay_policy": best, "data": [os.path.basename(b) for b in buffer]})
    print(f"{name}: trained {info}", file=sys.stderr)
    t2 = time.time()
    cand = f"learned:{name}"
    res = gate(cand, best, a.gate_games, a.workers, seed=a.seed + 7000 + 1000 * gen)
    t3 = time.time()
    promoted = res["score"] >= a.promote
    entry = {"generation": gen, "model": f"{name}.json", "date": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
             "selfplay_policy": best, "selfplay_games": a.games, "train": info, "gate": res, "promoted": promoted,
             "minutes": {"selfplay": round((t1 - t0) / 60, 1), "train": round((t2 - t1) / 60, 1),
                         "gate": round((t3 - t2) / 60, 1)}}
    hist.append(entry)
    json.dump(hist, open(hist_path, "w"), indent=1)
    if promoted:
        json.dump({"model": f"{name}.json", "spec": cand, "generation": gen}, open(bp, "w"), indent=1)
    write_ladder(hist)
    print(json.dumps(entry, indent=1))
    return entry


def write_ladder(hist):
    lines = ["# Learned AI generations", "",
             "Each generation trains the value net on self-play of the best AI so far, then plays it head to head "
             "(same decks and shuffles, seats swapped). It replaces the best AI only with a score of 55% or more.",
             "Written by tools/train_loop.py; the `learned` policy and the play page's Learned difficulty use the generation in best.json.", "",
             "| gen | date | self-play by | positions | val loss (constant) | val acc | vs best: score (95% interval) | games | promoted |",
             "|---|---|---|---|---|---|---|---|---|"]
    for h in hist:
        t, g = h["train"], h["gate"]
        lines.append(f"| {h['generation']} | {h['date']} | {h['selfplay_policy']} | {t['positions']} | "
                     f"{t['val_loss']} ({t['val_loss_constant']}) | {t['val_acc']} | {100 * g['score']:.1f}% "
                     f"({100 * g['interval'][0]:.0f}-{100 * g['interval'][1]:.0f}) vs {g['best']} | {g['games']} | "
                     f"{'yes' if h['promoted'] else 'no'} |")
    with open(os.path.join(MODELS, "ladder.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generation")
    g.add_argument("--games", type=int, default=600)
    g.add_argument("--gate-games", type=int, default=200)
    g.add_argument("--promote", type=float, default=0.55)
    g.add_argument("--buffer", type=int, default=4, help="generations of self-play data to train on")
    g.add_argument("--data")
    s = sub.add_parser("selfplay")
    s.add_argument("--games", type=int, default=600)
    s.add_argument("--policy", default=None)
    s.add_argument("--out", required=True)
    t = sub.add_parser("train")
    t.add_argument("files", nargs="+")
    t.add_argument("--out", required=True)
    t.add_argument("--hidden", type=int, default=48)
    q = sub.add_parser("gate")
    q.add_argument("candidate")
    q.add_argument("best")
    q.add_argument("--games", type=int, default=200)
    for p in (g, s, q):
        p.add_argument("--workers", type=int, default=os.cpu_count() or 2)
        p.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    if a.cmd == "generation":
        generation(a)
    elif a.cmd == "selfplay":
        print(selfplay(a.games, a.policy or best_spec(), a.out, a.workers, a.seed))
    elif a.cmd == "train":
        print(train(a.files, a.out, hidden=a.hidden))
    elif a.cmd == "gate":
        print(json.dumps(gate(a.candidate, a.best, a.games, a.workers, a.seed), indent=1))


if __name__ == "__main__":
    main()
