"""Batch runner: many games in parallel, aggregated statistics, replays on disk."""
from __future__ import annotations

import collections
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor

from .cards import CardDB
from .deck import Deck
from .policies import make_policy
from .replay import play_game, save_replay

_DB = None


def _db():
    global _DB
    if _DB is None:
        from .scripts import script_all
        _DB = script_all(CardDB.load())
    return _DB


def _one(args):
    deck_dicts, seed, policy_specs, replay_dir, max_turns, snapshots = args
    db = _db()
    decks = [Deck.from_dict(d, db) for d in deck_dicts]
    pols = [make_policy(s, seed=seed * 7 + i) for i, s in enumerate(policy_specs)]
    t = time.time()
    g, rep = play_game(db, decks, seed, pols, record=True, snapshots=snapshots, max_turns=max_turns)
    path = None
    if replay_dir:
        os.makedirs(replay_dir, exist_ok=True)
        path = os.path.join(replay_dir, f"game_{seed}.json.gz")
        save_replay(rep, path)
    played = [[], []]
    for e in g.events:
        if e["kind"] == "play":
            played[e["player"]].append(e["name"])
    return {"seed": seed, "winner": g.winner, "reason": g.reason, "turns": g.turn, "points": [p.points for p in g.players],
            "first": g.first_player, "decisions": g.decision_count, "secs": round(time.time() - t, 3), "replay": path,
            "played": played, "decks": [d.name for d in decks]}


def run_batch(decks, games=100, policies=("greedy", "greedy"), workers=None, replay_dir=None, seed0=0, max_turns=60,
              mirror=True, snapshots=False, progress=None):
    """Play `games` games between decks[0] and decks[1]. With mirror=True, odd seeds swap seats so both decks
    play first equally. Returns (results list, summary dict)."""
    deck_dicts = [d.to_dict() if isinstance(d, Deck) else d for d in decks]
    jobs = []
    for i in range(games):
        seed = seed0 + i
        dd = deck_dicts if (not mirror or i % 2 == 0) else deck_dicts[::-1]
        pp = list(policies) if (not mirror or i % 2 == 0) else list(policies)[::-1]
        jobs.append((dd, seed, pp, replay_dir, max_turns, snapshots))
    results = []
    workers = workers or os.cpu_count() or 2
    if workers > 1 and games > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(_one, jobs, chunksize=max(1, games // (workers * 4))):
                results.append(r)
                if progress:
                    progress(len(results), games)
    else:
        for j in jobs:
            results.append(_one(j))
            if progress:
                progress(len(results), games)
    return results, summarize(results)


def summarize(results):
    by_deck = collections.defaultdict(lambda: {"games": 0, "wins": 0, "first_games": 0, "first_wins": 0, "points": 0})
    cards = collections.defaultdict(lambda: {"played": 0, "wins": 0, "games": 0})
    turns, draws = [], 0
    for r in results:
        turns.append(r["turns"])
        if r["winner"] is None:
            draws += 1
        for seat, name in enumerate(r["decks"]):
            s = by_deck[name]
            s["games"] += 1
            s["points"] += r["points"][seat]
            won = r["winner"] == seat
            s["wins"] += won
            if r["first"] == seat:
                s["first_games"] += 1
                s["first_wins"] += won
            seen = set()
            for cname in r["played"][seat]:
                cards[(name, cname)]["played"] += 1
                if cname not in seen:
                    seen.add(cname)
                    cards[(name, cname)]["games"] += 1
                    cards[(name, cname)]["wins"] += won
    decks = {}
    for name, s in by_deck.items():
        decks[name] = dict(s, win_rate=round(s["wins"] / max(1, s["games"]), 3),
                           first_win_rate=round(s["first_wins"] / max(1, s["first_games"]), 3),
                           avg_points=round(s["points"] / max(1, s["games"]), 2))
    card_stats = []
    for (deck, cname), s in cards.items():
        card_stats.append({"deck": deck, "card": cname, "played": s["played"], "games": s["games"],
                           "win_rate_when_played": round(s["wins"] / max(1, s["games"]), 3)})
    card_stats.sort(key=lambda x: (-x["games"], x["card"]))
    return {"games": len(results), "draws": draws, "avg_turns": round(sum(turns) / max(1, len(turns)), 2),
            "decks": decks, "cards": card_stats,
            "avg_secs": round(sum(r["secs"] for r in results) / max(1, len(results)), 3)}


def save_results(results, summary, path):
    with open(path, "w") as f:
        json.dump({"summary": summary, "games": results}, f, indent=1)
