"""Train the policy net (riftsim/core/learn/policy_net.py) to pick what the recorded AI picked (AI v2 step 1).

Data: tools/policy_data.py files. Model: h = tanh(W_x z(x) + W_o phi(option) + b1), score = w2 . h + b2, softmax over
the options of each decision, cross-entropy against the recorded pick. numpy, Adam, minibatches of decisions, the
validation split is by game. Reports top-1 agreement overall and per decision kind.

usage:
  python tools/train_policy.py out/pol_g14.npz --out models/policy_g14.json --hidden 64 --epochs 20
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KINDS = ("action", "choose", "assign_damage", "yesno", "order_triggers", "choose_location", "additional_cost", "other")


def load(files):
    X, P, N, K, PK, G = [], [], [], [], [], []
    off = 0
    for f in files:
        d = np.load(f)
        X.append(d["x"]); P.append(d["phi"]); N.append(d["n"]); K.append(d["pick"]); PK.append(d["kind"])
        G.append(d["game"] + off)
        off = int(G[-1].max()) + 1
    return (np.concatenate(X), np.concatenate(P), np.concatenate(N).astype(np.int64),
            np.concatenate(K).astype(np.int64), np.concatenate(PK), np.concatenate(G))


def forward(params, z, phi, seg, n):
    Wx, Wo, b1, w2, b2 = params
    hx = z @ Wx.T                                   # decisions x H
    pre = hx[seg] + phi @ Wo.T + b1                 # options x H
    h = np.tanh(pre)
    s = h @ w2 + b2                                 # options
    # softmax per decision
    starts = np.concatenate([[0], np.cumsum(n)[:-1]])
    mx = np.maximum.reduceat(s, starts)
    e = np.exp(s - mx[seg])
    tot = np.add.reduceat(e, starts)
    p = e / tot[seg]
    return h, s, p, starts


def run(a):
    X, PHI, N, PICK, KIND, G = load(a.files)
    W = a.width or X.shape[1]
    X = X[:, :W]
    rs = np.random.RandomState(a.seed)
    games = np.unique(G)
    val_games = set(rs.choice(games, size=max(1, len(games) // 10), replace=False).tolist())
    vmask = np.isin(G, np.array(sorted(val_games)))
    offs = np.concatenate([[0], np.cumsum(N)])
    A = PHI.shape[1]
    src = a.eval or a.init
    if src:   # an existing model: its normalisation and weights
        with open(src) as f:
            d = json.load(f)
        mean, std = np.array(d["mean"], np.float32), np.array(d["std"], np.float32)
        w1 = np.array(d["w1"], np.float32)
        H = w1.shape[0]
        params = [w1[:, :W].copy(), w1[:, W:].copy(), np.array(d["b1"], np.float32), np.array(d["w2"], np.float32),
                  np.float32(d["b2"])]
    else:
        mean = X[~vmask].mean(0)
        std = X[~vmask].std(0) + 1e-3
        H = a.hidden
        params = [rs.randn(H, W).astype(np.float32) * (0.5 / np.sqrt(W)), rs.randn(H, A).astype(np.float32) * (0.5 / np.sqrt(8)),
                  np.zeros(H, np.float32), rs.randn(H).astype(np.float32) * 0.1, np.float32(0.0)]
    Z = ((X - mean) / std).astype(np.float32)
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]
    tr_idx = np.where(~vmask)[0]
    va_idx = np.where(vmask)[0]

    def batch(idx):
        n = N[idx]
        rows = np.concatenate([np.arange(offs[i], offs[i + 1]) for i in idx])
        seg = np.repeat(np.arange(len(idx)), n)
        return Z[idx], PHI[rows], seg, n

    def evaluate(idx):
        correct, loss, cnt = 0, 0.0, 0
        per = {}
        for s0 in range(0, len(idx), 4096):
            b = idx[s0:s0 + 4096]
            z, phi, seg, n = batch(b)
            _, s, p, starts = forward(params, z, phi, seg, n)
            pk = PICK[b]
            loss -= np.log(p[starts + pk] + 1e-9).sum()
            am = np.array([int(np.argmax(s[st:st + k])) for st, k in zip(starts, n)])
            ok = am == pk
            correct += ok.sum(); cnt += len(b)
            for kk, o in zip(KIND[b], ok):
                c = per.setdefault(KINDS[kk], [0, 0]); c[0] += int(o); c[1] += 1
        return loss / cnt, correct / cnt, {k: round(c[0] / c[1], 3) for k, c in per.items() if c[1] >= 50}

    if a.eval:
        vl, va, per = evaluate(np.arange(len(N)))
        print(json.dumps({"model": a.eval, "val_loss": round(float(vl), 4), "val_agreement": round(float(va), 4),
                          "per_kind": per}))
        return
    step = 0
    lr = a.lr
    best = (float("inf"), None, 0)
    for ep in range(a.epochs):
        rs.shuffle(tr_idx)
        for s0 in range(0, len(tr_idx), a.batch):
            b = tr_idx[s0:s0 + a.batch]
            z, phi, seg, n = batch(b)
            h, s, p, starts = forward(params, z, phi, seg, n)
            ds = p.copy()
            ds[starts + PICK[b]] -= 1.0
            ds /= len(b)
            Wx, Wo, b1, w2, b2 = params
            gw2 = h.T @ ds
            gb2 = ds.sum()
            dh = np.outer(ds, w2) * (1 - h * h)
            gWo = dh.T @ phi
            gb1 = dh.sum(0)
            dhx = np.add.reduceat(dh, starts)
            gWx = dhx.T @ z
            grads = [gWx + a.l2 * Wx, gWo + a.l2 * Wo, gb1, gw2, np.float32(gb2)]
            step += 1
            for i, gr in enumerate(grads):
                m[i] = 0.9 * m[i] + 0.1 * gr
                v[i] = 0.999 * v[i] + 0.001 * gr * gr
                mh = m[i] / (1 - 0.9 ** step)
                vh = v[i] / (1 - 0.999 ** step)
                params[i] = (params[i] - lr * mh / (np.sqrt(vh) + 1e-8)).astype(np.float32)
        vl, va, per = evaluate(va_idx)
        print(f"epoch {ep + 1}: val loss {vl:.4f}, val agreement {va:.4f} {per}", file=sys.stderr)
        if vl < best[0]:
            best = (vl, [np.array(q, copy=True) for q in params], ep + 1)
        lr *= a.decay
    params = best[1]   # the epoch with the lowest validation loss
    print(f"keeping epoch {best[2]}", file=sys.stderr)
    tl, ta, _ = evaluate(tr_idx[:20000])
    vl, va, per = evaluate(va_idx)
    # chance level: picking uniformly at random
    chance = float(np.mean(1.0 / N[va_idx]))
    Wx, Wo, b1, w2, b2 = params
    out = {"mean": mean.astype(float).tolist(), "std": std.astype(float).tolist(),
           "w1": np.concatenate([Wx, Wo], axis=1).astype(float).tolist(), "b1": b1.astype(float).tolist(),
           "w2": w2.astype(float).tolist(), "b2": float(b2),
           "meta": {"files": [os.path.basename(f) for f in a.files], "decisions": int(len(N)), "hidden": H,
                    "train_agreement": round(float(ta), 4), "val_agreement": round(float(va), 4),
                    "val_loss": round(float(vl), 4), "epoch": best[2], "chance": round(chance, 4), "per_kind": per}}
    with open(a.out, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(json.dumps(out["meta"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--decay", type=float, default=0.9)
    ap.add_argument("--l2", type=float, default=1e-5)
    ap.add_argument("--width", type=int)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--init", help="start from this model (its normalisation too) and fine-tune")
    ap.add_argument("--eval", help="only report this model's loss/agreement on every decision of the files")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
