"""One deck played by one AI against every other tournament deck played by another AI (seats alternate, each pair of
games shares a shuffle). Answers "does this AI play deck X better?" in the matchups that matter, e.g. whether a
search that models the opponent's answers helps an interactive deck like Kennen or Riven.

usage:
  python tools/deck_vs.py kennen_tempest learned-rl:gen_008 learned:gen_008 --games 10
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_loop as T   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("policy", help="AI that plays DECK")
    ap.add_argument("opponent", help="AI that plays every other deck")
    ap.add_argument("--games", type=int, default=10, help="games per matchup (even)")
    ap.add_argument("--seed", type=int, default=700000)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--out")
    a = ap.parse_args()
    me = next(p for p in T.DECKS if os.path.basename(p)[:-5] == a.deck)
    jobs = []
    for k, opp in enumerate(p for p in T.DECKS if p != me):
        for i in range(a.games // 2):
            s = a.seed + 1000 * k + i
            jobs.append(([me, opp], s, [a.policy, a.opponent]))
            jobs.append(([opp, me], s, [a.opponent, a.policy]))
    res, t = {}, time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for n, r in enumerate(ex.map(T._gate_timed, jobs), 1):
            if r.get("timeout"):
                continue
            seat = r["decks"].index(os.path.basename(me))
            opp = r["decks"][1 - seat][:-5]
            w, g = res.get(opp, (0, 0))
            res[opp] = (w + (r["winner"] == seat) + 0.5 * (r["winner"] is None), g + 1)
            if n % 20 == 0:
                tw = sum(v[0] for v in res.values()); tg = sum(v[1] for v in res.values())
                print(f"deck_vs {n}/{len(jobs)}: {tw}/{tg} ({time.time() - t:.0f}s)", file=sys.stderr)
    tw = sum(v[0] for v in res.values()); tg = sum(v[1] for v in res.values())
    p, z = tw / tg, 1.96
    half = z * math.sqrt(p * (1 - p) / tg + z * z / (4 * tg * tg)) / (1 + z * z / tg)
    c = (p + z * z / (2 * tg)) / (1 + z * z / tg)
    out = {"deck": a.deck, "policy": a.policy, "opponent": a.opponent, "wins": tw, "games": tg, "score": round(p, 4),
           "interval": [round(c - half, 3), round(c + half, 3)],
           "per_matchup": {k: [v[0], v[1]] for k, v in sorted(res.items(), key=lambda kv: -kv[1][0] / kv[1][1])}}
    print(json.dumps(out, indent=1))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
