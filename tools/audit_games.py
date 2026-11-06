"""Play tournament-deck games and audit them: which mechanics each deck used, and rule invariants that every turn must
satisfy. Usage:
  python tools/audit_games.py --vs-random 5          # each deck vs randomly drawn opponents, 5 games per deck
  python tools/audit_games.py --round-robin 2        # every pair of decks, 2 games each (seats swapped)
  python tools/audit_games.py --adaptive 40          # every pair until its result is clear (6-40 games per pair)
Options: --policy greedy|mcts:N  --out out/audit  --workers N
Writes out/audit/report.md and out/audit/games.json."""
import argparse
import collections
import glob
import json
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_DB = None


def _db():
    global _DB
    if _DB is None:
        from riftsim.core.cards import CardDB
        from riftsim.core.scripts import script_all
        _DB = script_all(CardDB.load())
    return _DB


def speed_of(db, name, from_zone, loc):
    """'reaction' | 'action' | 'main' timing a card was played with."""
    d = db.card(name)
    kws = d.keywords
    if kws.get("reaction") or kws.get("quick_draw") or from_zone == "facedown":
        return "reaction"
    if d.is_unit and kws.get("ambush") and loc and loc[0] == "bf":
        return "reaction"
    if kws.get("action"):
        return "action"
    return "main"


def audit_game(args):
    deck_paths, seed, policy = args
    from riftsim.core.deck import Deck
    from riftsim.core.policies import make_policy
    from riftsim.core.replay import play_game
    db = _db()
    decks = [Deck.load(p, db) for p in deck_paths]
    pols = [make_policy(policy, seed=seed * 7 + i) for i in range(2)]
    t = time.time()
    try:
        g, _ = play_game(db, decks, seed, pols, record=False, max_turns=60)
    except Exception as e:      # a crash is a finding, not a reason to stop the audit
        import traceback
        return {"decks": [d.name for d in decks], "paths": deck_paths, "seed": seed, "crash": traceback.format_exc()[-2000:]}
    ev = g.events
    names = [d.name for d in decks]
    use = [collections.Counter(), collections.Counter()]
    problems = []
    victory = g.victory_score() if hasattr(g, "victory_score") else g.cfg["victory"]

    # ---- per turn invariants: Channel 2 (3 for the second player's first turn), Draw 1
    turns = collections.defaultdict(list)
    for e in ev:
        turns[e.get("turn")].append(e)
    first_turn_of = {}
    for tnum in sorted(k for k in turns if k is not None):
        es = turns[tnum]
        tp = next((e["player"] for e in es if e["kind"] == "turn"), None)
        if tp is None:
            continue
        first_turn_of.setdefault(tp, tnum)
        # Channel phase = events between beginning_phase and main_phase of this turn
        try:
            b = next(i for i, e in enumerate(es) if e["kind"] == "event:beginning_phase")
            m = next(i for i, e in enumerate(es) if e["kind"] == "event:main_phase")
        except StopIteration:
            continue
        window = es[b:m]
        chans = [e for e in window if e["kind"] == "event:channel" and e.get("player") == tp]
        expected = 3 if (tnum == 2 and tp != g.first_player) else 2
        rune_deck_short = any(e["kind"] == "channel_short" for e in window)
        extra = sum(1 for e in window if e["kind"] == "trigger")       # beginning-phase triggers may channel too
        if len(chans) != expected and not rune_deck_short and not (extra and len(chans) > expected):
            problems.append(f"turn {tnum} P{tp}: channeled {len(chans)} runes in the Channel phase, expected {expected}")
        draws = [e for e in window if e["kind"] == "event:draw" and e.get("player") == tp]
        if len(draws) < 1 and not any(e["kind"] in ("event:burn_out", "burn_out") for e in window):
            problems.append(f"turn {tnum} P{tp}: no draw in the Draw phase")
        use[tp]["turns"] += 1
        use[tp]["runes_channeled"] += len(chans)

    # ---- plays and their timing
    for e in ev:
        k = e["kind"]
        p = e.get("player")
        if k == "play":
            sp = speed_of(db, e["name"], e.get("from_zone"), e.get("loc"))
            d = db.card(e["name"])
            kind = "unit" if d.is_unit else ("gear" if d.is_gear else "spell")
            use[p][f"play_{kind}"] += 1
            if e.get("from_zone") == "champion":
                use[p]["play_champion"] += 1
            if e.get("from_zone") == "facedown":
                use[p]["play_from_facedown"] += 1
            if d.is_unit and e.get("loc") and e["loc"][0] == "bf":
                use[p]["unit_played_to_battlefield"] += 1
                if d.keywords.get("ambush"):
                    use[p]["ambush"] += 1
            chain = e.get("chain", 0)
            state = e.get("state", "neutral")
            if e.get("by_effect"):
                use[p]["played_by_effect"] += 1
            elif chain > 0:
                use[p]["reaction_on_chain"] += 1
                if sp != "reaction":
                    problems.append(f"turn {e['turn']}: {e['name']} ({sp} speed) played onto a chain")
            elif state != "neutral":
                use[p][f"play_in_{state}"] += 1
                if sp == "main":
                    problems.append(f"turn {e['turn']}: {e['name']} (main speed) played during a {state}")
            elif p != e.get("turn_player") or e.get("phase") != "main":
                if sp == "main":
                    problems.append(f"turn {e['turn']}: {e['name']} (main speed) played outside its controller's main phase")
                else:
                    use[p]["play_on_opponents_turn"] += 1
        elif k == "activate":
            use[p]["activate"] += 1
            if e.get("label") == "Equip":
                use[p]["equip"] += 1
            if e.get("chain", 0) > 0 and e.get("timing") != "reaction" and e.get("label") not in ("Equip",):
                problems.append(f"turn {e['turn']}: {e['name']} ability ({e.get('timing')}) activated onto a chain")
        elif k == "event:hide":
            use[p]["hide"] += 1
        elif k == "move":
            pass
        elif k == "event:move":
            use[p]["move_standard" if e.get("standard") else "move_by_effect"] += 1
            if e.get("standard") and e.get("from") and e["from"][0] == "bf" and e["to"][0] == "bf":
                use[p]["ganking_move"] += 1
        elif k == "event:attack":
            use[p]["attacker"] += 1
        elif k == "event:defend":
            use[p]["defender"] += 1
        elif k == "event:combat_start":
            use[e["attacker"]]["combat"] += 1
        elif k == "event:showdown_start":
            use[g.turn_player]["showdown_any"] += 0
        elif k == "event:conquer":
            use[p]["conquer"] += 1
        elif k == "event:hold":
            use[p]["hold"] += 1
        elif k == "event:stun":
            use[e.get("by") if e.get("by") is not None else p]["stun"] += 1
        elif k == "event:xp":
            use[p]["xp_events"] += 1
        elif k == "event:counter":
            use[p]["counter"] += 1
        elif k == "event:target":
            use[p]["targeting"] += 1
        elif k == "event:recall":
            use[p]["recall"] += 1
        elif k == "event:empower":
            use[p]["empower"] += 1
        elif k == "event:draw":
            use[p]["draw"] += 1
        elif k == "trigger":
            c = e.get("controller")
            if c is not None:
                use[c]["triggers"] += 1
        elif k == "replace":
            use[g.objects[e["source"]].controller if e.get("source") in g.objects else 0]["replacements"] += 1
        elif k == "event:gain_points":
            pass
    if g.winner is None:
        problems.append(f"no winner ({g.reason}) after {g.turn} turns")
    max_chain = max([e.get("chain", 0) for e in ev if e["kind"] in ("play", "activate")] + [0]) + 1
    return {"decks": names, "paths": deck_paths, "seed": seed, "winner": g.winner, "reason": g.reason, "turns": g.turn,
            "points": [p.points for p in g.players], "first": g.first_player, "use": [dict(u) for u in use],
            "problems": problems, "max_chain": max_chain, "secs": round(time.time() - t, 2)}


def wilson(wins, n, z=1.96):
    """95% Wilson score interval for a win rate."""
    if n == 0:
        return 0.0, 1.0
    p = wins / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return mid - half, mid + half


def pair_done(wins, n, a):
    """A matchup is finished when it reached MAX games, or after --min-games when the 95% interval is narrow
    enough or clearly excludes 50% (one deck is favoured beyond doubt)."""
    if n >= a.adaptive:
        return True
    if n < a.min_games or n % 2:
        return False                  # seats stay balanced: always an even number of games
    lo, hi = wilson(wins, n)
    return (hi - lo) / 2 <= a.precision or lo > 0.5 or hi < 0.5


def adaptive_round_robin(paths, a):
    """Play every pair two games at a time (seats swapped) and keep the pool busy with the pairs still open.
    Games whose result is a timeout count as unfinished and are not counted (they are kept in the results)."""
    from concurrent.futures import FIRST_COMPLETED, wait
    pairs = [(p, q) for i, p in enumerate(paths) for q in paths[i + 1:]]
    state = {pq: {"n": 0, "wins": 0, "running": 0, "next": 0} for pq in pairs}
    results, seed = [], a.seed
    t = time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        live = {}

        def feed():
            nonlocal seed
            for pq in pairs:
                st = state[pq]
                while len(live) < a.workers * 2 and not pair_done(st["wins"], st["n"], a) \
                        and st["n"] + st["running"] < a.adaptive and st["running"] < 2 and st["next"] < 2 * a.adaptive:
                    k = st["next"]
                    st["next"] += 1
                    st["running"] += 1
                    order = list(pq) if k % 2 == 0 else [pq[1], pq[0]]
                    live[ex.submit(audit_game, (order, seed, a.policy))] = pq
                    seed += 1

        feed()
        while live:
            done, _ = wait(list(live), return_when=FIRST_COMPLETED)
            for f in done:
                pq = live.pop(f)
                r = f.result()
                results.append(r)
                st = state[pq]
                st["running"] -= 1
                if not r.get("crash") and r.get("winner") is not None:
                    st["n"] += 1
                    st["wins"] += r["paths"][r["winner"]] == pq[0]
            feed()
            closed = sum(1 for pq in pairs if pair_done(state[pq]["wins"], state[pq]["n"], a))
            print(f"{len(results)} games, {closed}/{len(pairs)} matchups settled ({time.time() - t:.0f}s)", file=sys.stderr)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vs-random", type=int, default=0)
    ap.add_argument("--round-robin", type=int, default=0)
    ap.add_argument("--decks", nargs="*")
    ap.add_argument("--policy", default="greedy")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--out", default="out/audit")
    ap.add_argument("--adaptive", type=int, default=0, metavar="MAX",
                    help="round-robin that stops each pair once its result is clear (up to MAX games per pair)")
    ap.add_argument("--min-games", type=int, default=6)
    ap.add_argument("--precision", type=float, default=0.15,
                    help="adaptive: stop a pair when its 95%% Wilson half-width is at most this")
    a = ap.parse_args()
    paths = a.decks or sorted(glob.glob(os.path.join(ROOT, "data/decks/tournament/*.json")))
    rng = random.Random(a.seed)
    jobs = []
    s = a.seed
    if a.vs_random:
        for p in paths:
            for i in range(a.vs_random):
                opp = rng.choice([q for q in paths if q != p])
                pair = [p, opp] if i % 2 == 0 else [opp, p]
                jobs.append((pair, s, a.policy)); s += 1
    if a.round_robin:
        for i, p in enumerate(paths):
            for q in paths[i + 1:]:
                for k in range(a.round_robin):
                    jobs.append(([p, q] if k % 2 == 0 else [q, p], s, a.policy)); s += 1
    os.makedirs(a.out, exist_ok=True)
    t = time.time()
    results = []
    if a.adaptive:
        results = adaptive_round_robin(paths, a)
        jobs = []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for r in ex.map(audit_game, jobs):
            results.append(r)
            if len(results) % 5 == 0:
                print(f"{len(results)}/{len(jobs)} games ({time.time() - t:.0f}s)", file=sys.stderr)
    json.dump(results, open(os.path.join(a.out, "games.json"), "w"), indent=1)
    write_report(results, os.path.join(a.out, "report.md"), a.policy)
    print(open(os.path.join(a.out, "report.md")).read())


def write_report(results, path, policy):
    by_deck = collections.defaultdict(lambda: {"games": 0, "wins": 0, "use": collections.Counter()})
    problems = collections.Counter()
    examples = {}
    crashes = [r for r in results if r.get("crash")]
    for r in results:
        if r.get("crash"):
            continue
        for seat, name in enumerate(r["decks"]):
            d = by_deck[name]
            d["games"] += 1
            d["wins"] += r["winner"] == seat
            d["use"].update(r["use"][seat])
        for pr in r["problems"]:
            key = pr.split(":", 1)[-1].strip()
            key = key if "turn" not in pr.split(":", 1)[0] else key
            problems[key] += 1
            examples.setdefault(key, f"seed {r['seed']} {r['decks'][0][:20]} vs {r['decks'][1][:20]}: {pr}")
    lines = [f"# Gameplay audit ({len(results)} games, policy {policy})", ""]
    if crashes:
        lines += [f"## Crashes: {len(crashes)}", ""]
        for c in crashes[:5]:
            lines += [f"- seed {c['seed']} {c['decks']}", "```", c["crash"], "```"]
    lines += ["## Rule invariant problems", ""]
    if not problems:
        lines.append("None found.")
    for k, n in problems.most_common(40):
        lines.append(f"- {n}x {k}  (e.g. {examples[k]})")
    keys = ["turns", "runes_channeled", "draw", "play_unit", "play_spell", "play_gear", "play_champion", "unit_played_to_battlefield",
            "ambush", "hide", "play_from_facedown", "reaction_on_chain", "play_in_showdown", "play_in_combat", "play_on_opponents_turn",
            "activate", "equip", "empower", "targeting", "triggers", "replacements", "move_standard", "ganking_move", "move_by_effect",
            "combat", "attacker", "defender", "conquer", "hold", "stun", "counter", "recall", "xp_events"]
    lines += ["", "## Mechanics used (per game average)", "", "| deck | games | win% | " + " | ".join(keys) + " |",
              "|---|---|---|" + "---|" * len(keys)]
    for name, d in sorted(by_deck.items()):
        n = max(1, d["games"])
        lines.append(f"| {name[:40]} | {d['games']} | {100 * d['wins'] / n:.0f} | " +
                     " | ".join(f"{d['use'].get(k, 0) / n:.1f}" for k in keys) + " |")
    ok = [r for r in results if not r.get("crash")]
    if ok:
        lines += ["", f"Average turns {sum(r['turns'] for r in ok) / len(ok):.1f}; longest chain {max(r['max_chain'] for r in ok)}; "
                  f"games without a winner {sum(1 for r in ok if r['winner'] is None)}; first player won "
                  f"{sum(1 for r in ok if r['winner'] == r['first'])}/{len(ok)}."]
        # matchups: row deck's win rate against the column deck, with games and 95% interval
        pair = collections.defaultdict(lambda: [0, 0])
        for r in ok:
            if r["winner"] is None:
                continue
            a_, b_ = r["decks"]
            w = r["decks"][r["winner"]]
            for me, opp in ((a_, b_), (b_, a_)):
                pair[(me, opp)][1] += 1
                pair[(me, opp)][0] += w == me
        lines += ["", "## Matchups (row vs column: win%, games, 95% interval)", "",
                  "| deck | opponent | win% | games | 95% interval |", "|---|---|---|---|---|"]
        for (me, opp), (w, n) in sorted(pair.items()):
            if me < opp:
                lo, hi = wilson(w, n)
                lines.append(f"| {me[:40]} | {opp[:40]} | {100 * w / n:.0f} | {n} | {100 * lo:.0f}-{100 * hi:.0f} |")
    open(path, "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
