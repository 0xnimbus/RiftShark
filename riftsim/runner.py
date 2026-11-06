"""Batch runner: play many games in parallel and aggregate stats."""
from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import engine, replay
from .cards import Registry
from .policies import make_policy


def play_one(card_set, deck_paths, seed, policy_specs, replay_dir=None, config=None):
    reg = Registry().load_set(card_set)
    decks = [reg.load_deck(p) for p in deck_paths]
    pols = [make_policy(spec, seed=seed * 2 + i) for i, spec in enumerate(policy_specs)]
    s = engine.new_game(reg, decks[0], decks[1], seed=seed, config=config)
    while not s.done:
        engine.apply(s, pols[s.active](s))
    cards_played = [Counter(), Counter()]
    for e in s.log:
        if e["kind"] == "action" and e["action"][0] in ("play", "champ"):
            cards_played[e["player"]][e["text"].split(" targeting")[0]] += 1
    result = {"seed": seed, "winner": s.winner, "turns": s.turn, "first": s.first,
              "points": [p.points for p in s.players],
              "decks": [d.name for d in decks], "policies": list(policy_specs),
              "cards_played": [dict(c) for c in cards_played]}
    if replay_dir:
        path = Path(replay_dir) / f"game_{seed:05d}.json"
        replay.save(path, s, deck_paths, seed, policy_specs, result)
        result["replay"] = str(path)
    return result


def run_batch(card_set, deck_paths, policy_specs, games=100, seed0=0, workers=None,
              replay_dir=None, config=None, mirror=True):
    """Play `games` games. With mirror=True, seeds alternate which deck sits in seat 0 so
    first-player advantage is shared evenly."""
    t0 = time.time()
    jobs = []
    for g in range(games):
        seed = seed0 + g
        if mirror and g % 2 == 1:
            jobs.append((card_set, deck_paths[::-1], seed, policy_specs[::-1], replay_dir, config))
        else:
            jobs.append((card_set, deck_paths, seed, policy_specs, replay_dir, config))
    with ProcessPoolExecutor(workers) as ex:
        results = list(ex.map(play_one, *zip(*jobs), chunksize=4))
    return summarize(results, time.time() - t0)


def summarize(results, elapsed=0.0):
    wins, games_by_deck, first_wins, turns = Counter(), Counter(), 0, []
    draws = 0
    played, played_in_wins = defaultdict(Counter), defaultdict(Counter)
    for r in results:
        turns.append(r["turns"])
        for i, d in enumerate(r["decks"]):
            games_by_deck[d] += 1
            for card, n in r["cards_played"][i].items():
                played[d][card] += n
                if r["winner"] == i:
                    played_in_wins[d][card] += n
        if r["winner"] is None:
            draws += 1
            continue
        wins[r["decks"][r["winner"]]] += 1
        if r["winner"] == r["first"]:
            first_wins += 1
    decided = len(results) - draws
    card_stats = {}
    for d in played:
        card_stats[d] = {c: {"played": n, "in_wins": played_in_wins[d][c],
                             "win_share": round(played_in_wins[d][c] / n, 3)}
                         for c, n in played[d].most_common()}
    return {
        "games": len(results), "draws": draws, "elapsed_s": round(elapsed, 1),
        "win_rate": {d: round(wins[d] / games_by_deck[d], 3) for d in games_by_deck},
        "first_player_win_rate": round(first_wins / decided, 3) if decided else None,
        "avg_turns": round(sum(turns) / len(turns), 1) if turns else None,
        "card_stats": card_stats,
        "results": results,
    }


def print_summary(summary, top_cards=8):
    print(f"Games: {summary['games']}  draws: {summary['draws']}  "
          f"avg half-turns: {summary['avg_turns']}  time: {summary['elapsed_s']}s")
    for d, wr in summary["win_rate"].items():
        print(f"  {d:<30} win rate {wr:.1%}")
    print(f"  first player win rate: {summary['first_player_win_rate']:.1%}")
    for d, cards in summary["card_stats"].items():
        print(f"\n  {d}: cards most often played in winning games")
        for c, st in sorted(cards.items(), key=lambda kv: -kv[1]["in_wins"])[:top_cards]:
            print(f"    {c:<40} played {st['played']:>4}  win share {st['win_share']:.0%}")
