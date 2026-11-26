"""Extend a linear judge with new features while keeping its own weights frozen.

    python tools/extend_judge.py models/gen_014.json DATA.npz [...] --out models/gen_014_d5.json

Judges retrained from scratch keep losing to gen 14 even on far more data (2026-11-20: 35% on 9377 games), so a new
feature is tested as a residual: the base judge's logit is a fixed offset and only the new features' weights (and a
bias) are fitted, by Newton steps on the logistic loss with an L2 penalty. Validation is split by game. The result is
the base model with its inputs padded to the new width (zero weight on features it never read) and the new weights
appended, so `learned:<out>` plays with base judgement + correction.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def base_logit(m, X):
    w = len(m["mean"])
    Z = (X[:, :w] - np.array(m["mean"])) / np.array(m["std"])
    out = np.full(len(X), m["b2"], dtype=np.float64)
    if m.get("h_index") is not None:
        out += m.get("h_scale", 0.0) * np.arctanh(np.clip(X[:, m["h_index"]], -0.999999, 0.999999))
    if m.get("lin"):
        out += Z @ np.array(m["lin"])
    if m.get("w1"):
        out += np.tanh(Z @ np.array(m["w1"]).T + np.array(m["b1"])) @ np.array(m["w2"])
    return out


def main():
    from riftsim.core.learn.features import size, size_v4
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=int, default=size_v4(), help="first new feature index (default: version 5)")
    ap.add_argument("--l2", type=float, default=1.0, help="L2 penalty on the new weights (summed loss scale)")
    ap.add_argument("--boundary-only", action="store_true", help="train on turn-boundary positions (kind 0) only")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    base = json.load(open(a.base))
    W = size()
    xs, ys, gs, off = [], [], [], 0
    for f in a.files:
        d = np.load(f)
        if d["x"].shape[1] < W:
            print(f"skipping {f}: {d['x'].shape[1]} features < {W}")
            continue
        keep = (d["kind"] == 0) if a.boundary_only and "kind" in d.files else slice(None)
        xs.append(d["x"][keep, :W].astype(np.float64)); ys.append(d["y"][keep]); gs.append(d["game"][keep] + off)
        off = int(gs[-1].max()) + 1 if len(gs[-1]) else off
    X, Y, G = np.concatenate(xs), np.concatenate(ys).astype(np.float64), np.concatenate(gs)
    O = base_logit(base, X)
    rs = np.random.RandomState(a.seed)
    games = np.unique(G)
    vm = np.isin(G, rs.choice(games, size=max(1, len(games) // 10), replace=False))
    N = X[:, a.start:W]
    mean, std = N[~vm].mean(0), N[~vm].std(0) + 1e-3
    A = np.hstack([(N - mean) / std, np.ones((len(N), 1))])
    w = np.zeros(A.shape[1])
    reg = np.full(A.shape[1], a.l2); reg[-1] = 0.0

    def loss(m, w):
        p = np.clip(1 / (1 + np.exp(-(O[m] + A[m] @ w))), 1e-9, 1 - 1e-9)
        return float(-np.mean(Y[m] * np.log(p) + (1 - Y[m]) * np.log(1 - p)))
    print(f"positions {len(Y)} ({vm.sum()} val), games {len(games)}; base val loss {loss(vm, w):.5f}")
    At, Ot, Yt = A[~vm], O[~vm], Y[~vm]
    for it in range(12):
        p = 1 / (1 + np.exp(-(Ot + At @ w)))
        g = At.T @ (p - Yt) + reg * w
        H = (At * (p * (1 - p))[:, None]).T @ At + np.diag(reg + 1e-9)
        w -= np.linalg.solve(H, g)
        print(f"  step {it + 1}: train {loss(~vm, w):.5f} val {loss(vm, w):.5f}")
    names = ["opp_reactions", "opp_counters", "opp_removal", "opp_bounce", "opp_fast_payable",
             "my_units", "my_removal", "my_reactions", "my_unit_might"]
    for k, v in enumerate(w[:-1]):
        print(f"  {names[k] if a.start == size_v4() and k < len(names) else a.start + k:18s} {v:+.4f}")
    out = dict(base)
    bw = len(base["mean"])
    pad = a.start - bw
    out["mean"] = list(base["mean"]) + [0.0] * pad + mean.tolist()
    out["std"] = list(base["std"]) + [1.0] * pad + std.tolist()
    out["lin"] = list(base.get("lin") or [0.0] * bw) + [0.0] * pad + w[:-1].tolist()
    if base.get("w1"):
        out["w1"] = [row + [0.0] * (W - bw) for row in base["w1"]]
    out["b2"] = base["b2"] + float(w[-1])
    out["meta"] = {"base": os.path.basename(a.base), "kind": "linear", "extended_from": a.start, "width": W,
                   "positions": int(len(Y)), "games": int(len(games)),
                   "val_loss_base": loss(vm, np.zeros_like(w)), "val_loss": loss(vm, w),
                   "note": "base judge frozen; only the features from extended_from on were fitted (tools/extend_judge.py)"}
    json.dump(out, open(a.out, "w"))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
