"""Command line: python -m riftsim.core <command>

  batch   --decks A.json B.json --games 100 --policy greedy --policy mcts:200 --replays out/replays --out out/results.json
  replay  path.json.gz           print a transcript
  verify  path.json.gz           re-simulate and audit a replay
  coverage [--set RAD]           script coverage report
  deck    --legend "Blind Monk" --champion "Lee Sin" --out data/decks/lee_sin.json   (build a scripted-only sample deck)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time

from .cards import CardDB
from .deck import Deck


def _db():
    from .scripts import script_all
    return script_all(CardDB.load())


def cmd_batch(a):
    from .runner import run_batch, save_results
    db = _db()
    decks = [Deck.load(p, db) for p in a.decks]
    for d in decks:
        errs = d.validate(db)
        if errs:
            print(f"deck {d.name}: " + "; ".join(errs), file=sys.stderr)
            if not a.force:
                sys.exit(1)
    pols = a.policy or ["greedy", "greedy"]
    if len(pols) == 1:
        pols = pols * 2
    t = time.time()

    def prog(done, total):
        if done % max(1, total // 10) == 0 or done == total:
            print(f"  {done}/{total} games ({time.time() - t:.0f}s)", file=sys.stderr)

    results, summary = run_batch(decks, games=a.games, policies=pols, workers=a.workers, replay_dir=a.replays,
                                 seed0=a.seed, max_turns=a.max_turns, snapshots=a.snapshots, progress=prog)
    if a.out:
        save_results(results, summary, a.out, policies=pols)
    print(json.dumps({k: v for k, v in summary.items() if k != "cards"}, indent=1))
    print("top cards by games played:")
    for c in summary["cards"][:15]:
        print(f"  {c['deck'][:28]:28} {c['card'][:28]:28} games={c['games']:4} win%={c['win_rate_when_played']:.2f}")


def cmd_replay(a):
    from .replay import load_replay, transcript
    rep = load_replay(a.path)
    print(transcript(rep))


def cmd_verify(a):
    from .replay import load_replay, verify
    db = _db()
    rep = load_replay(a.path)
    ok, report = verify(db, rep)
    print("OK" if ok else "FAILED", json.dumps(report))
    sys.exit(0 if ok else 2)


def cmd_coverage(a):
    from .scripts import coverage
    db = _db()
    cards = [c for c in db if (not a.set or c.set == a.set)]
    counts, missing = coverage(db, cards)
    print(counts)
    if a.list:
        for c in missing:
            print(f"{c.id:10} {c.name[:30]:30} {c.script_status:9} | " + " || ".join(c.keywords.get("_unparsed", []))[:140])


def build_deck(db, legend, champion, rng, name=None, only_scripted=True):
    leg = db.card(legend)
    ch = db.card(champion)
    pool = [c for c in db if c.type in ("unit", "spell", "gear") and not c.is_token and c.domains
            and set(c.domains) <= set(leg.domains) and not c.data_incomplete and c.supertype != "champion"]
    if only_scripted:
        pool = [c for c in pool if c.script_status in ("auto", "manual", "vanilla", "keywords") and not c.keywords.get("_unparsed")]
    # prefer a curve: cheap units, a few spells and gear
    rng.shuffle(pool)
    pool.sort(key=lambda c: (c.energy or 0) + rng.random() * 3)
    main, counts = [], {}
    want = {"unit": 24, "spell": 12, "gear": 4}
    got = {"unit": 0, "spell": 0, "gear": 0}
    for c in pool:
        if len(main) >= 39:
            break
        if got[c.type] >= want[c.type]:
            continue
        if counts.get(c.name, 0) >= (1 if c.keywords.get("unique") else 2):
            continue
        main.append(c.id)
        counts[c.name] = counts.get(c.name, 0) + 1
        got[c.type] += 1
    for c in pool:
        if len(main) >= 39:
            break
        if counts.get(c.name, 0) < 3 and not c.keywords.get("unique"):
            main.append(c.id)
            counts[c.name] = counts.get(c.name, 0) + 1
    doms = list(leg.domains)
    runes = []
    for i in range(12):
        runes.append(doms[i % len(doms)])
    bfs = [b for b in db if b.type == "battlefield" and b.script_status in ("auto", "manual", "vanilla")]
    rng.shuffle(bfs)
    bfs = [b.id for b in bfs[:3]]
    return Deck(name or f"{leg.name} / {ch.name}", leg.id, ch.id, main, runes, bfs)


def cmd_deck(a):
    db = _db()
    d = build_deck(db, a.legend, a.champion, random.Random(a.seed), name=a.name)
    errs = d.validate(db)
    if errs:
        print("warning: " + "; ".join(errs), file=sys.stderr)
    with open(a.out, "w") as f:
        json.dump(d.to_dict(), f, indent=1)
    print(f"wrote {a.out}: {d.name}, {len(d.main)} cards")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="riftsim.core")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("batch")
    b.add_argument("--decks", nargs=2, required=True)
    b.add_argument("--games", type=int, default=50)
    b.add_argument("--policy", action="append")
    b.add_argument("--workers", type=int, default=None)
    b.add_argument("--replays", default=None)
    b.add_argument("--out", default=None)
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--max-turns", type=int, default=60)
    b.add_argument("--snapshots", action="store_true")
    b.add_argument("--force", action="store_true")
    b.set_defaults(fn=cmd_batch)
    r = sub.add_parser("replay")
    r.add_argument("path")
    r.set_defaults(fn=cmd_replay)
    v = sub.add_parser("verify")
    v.add_argument("path")
    v.set_defaults(fn=cmd_verify)
    c = sub.add_parser("coverage")
    c.add_argument("--set", default=None)
    c.add_argument("--list", action="store_true")
    c.set_defaults(fn=cmd_coverage)
    d = sub.add_parser("deck")
    d.add_argument("--legend", required=True)
    d.add_argument("--champion", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--name", default=None)
    d.add_argument("--seed", type=int, default=0)
    d.set_defaults(fn=cmd_deck)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
