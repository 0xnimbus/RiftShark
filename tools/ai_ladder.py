"""Measure AI strength levels against each other on the tournament decks.
Usage: python tools/ai_ladder.py novice intermediate --games 20 [--workers 4] [--seed 0]
Each game draws a random pair of tournament decks; seats and decks alternate so both levels play both sides."""
import argparse
import glob
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_DB = None


def _one(args):
    global _DB
    paths, seed, specs = args
    from riftsim.core.cards import CardDB
    from riftsim.core.deck import Deck
    from riftsim.core.policies import make_policy
    from riftsim.core.replay import play_game
    from riftsim.core.scripts import script_all
    if _DB is None:
        _DB = script_all(CardDB.load())
    decks = [Deck.load(p, _DB) for p in paths]
    pols = [make_policy(s, seed=seed * 11 + i) for i, s in enumerate(specs)]
    t = time.time()
    g, _ = play_game(_DB, decks, seed, pols, record=False)
    return {"specs": specs, "winner": g.winner, "reason": g.reason, "turns": g.turn, "secs": time.time() - t, "decks": [d.name for d in decks]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    paths = sorted(glob.glob(os.path.join(ROOT, "data/decks/tournament/*.json")))
    rng = random.Random(a.seed)
    jobs = []
    for i in range(a.games // 2):
        pair = rng.sample(paths, 2)
        seed = a.seed * 1000 + i
        jobs.append((pair, seed, [a.a, a.b]))
        jobs.append((pair, seed, [a.b, a.a]))       # same decks and shuffle, levels swap seats
    wins = {a.a: 0, a.b: 0}
    draws, unfinished, secs, turns = 0, 0, 0.0, 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for r in ex.map(_one, jobs):
            secs += r["secs"]
            turns += r["turns"]
            if r["reason"] == "turn limit":
                unfinished += 1
            elif r["winner"] is None:
                draws += 1
            else:
                wins[r["specs"][r["winner"]]] += 1
    n = len(jobs)
    print(f"{a.a} {wins[a.a]} - {wins[a.b]} {a.b}  (draws {draws}, unfinished at the turn cap {unfinished}, {n} games, {secs / n:.1f}s/game, {turns / n:.1f} turns)")
    print(f"{a.a} win rate {wins[a.a] / max(1, n - draws - unfinished):.2f}")


if __name__ == "__main__":
    main()
