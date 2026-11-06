"""Command line interface.

  python -m riftsim batch  deckA.json deckB.json --games 200 --policies mcts greedy --replays out/replays
  python -m riftsim replay out/replays/game_00007.json          # print a transcript
  python -m riftsim verify out/replays/                          # re-check every replay against the rules
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import replay, runner
from .cards import Registry

DEFAULT_SET = str(Path(__file__).resolve().parent.parent / "data" / "cards" / "demo_set.json")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="riftsim")
    ap.add_argument("--cards", default=DEFAULT_SET, help="card set JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("batch", help="run many games in parallel")
    b.add_argument("decks", nargs=2)
    b.add_argument("--games", type=int, default=100)
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--policies", nargs=2, default=["greedy", "greedy"],
                   help="one policy per deck (first plays the first deck), e.g. mcts:iterations=300 greedy")
    b.add_argument("--workers", type=int, default=None)
    b.add_argument("--replays", default=None, help="directory to save one replay per game")
    b.add_argument("--json", default=None, help="write the full summary to this file")
    b.add_argument("--no-mirror", action="store_true", help="do not alternate seats between games")

    r = sub.add_parser("replay", help="print a transcript of a saved game")
    r.add_argument("file")
    r.add_argument("--hide-hands", action="store_true")

    v = sub.add_parser("verify", help="re-simulate replays and check every action was legal")
    v.add_argument("path", help="replay file or directory")

    args = ap.parse_args(argv)
    reg = Registry().load_set(args.cards)

    if args.cmd == "batch":
        summary = runner.run_batch(args.cards, args.decks, args.policies, games=args.games, seed0=args.seed,
                                   workers=args.workers, replay_dir=args.replays, mirror=not args.no_mirror)
        runner.print_summary(summary)
        if args.json:
            Path(args.json).write_text(json.dumps(summary, indent=1))
            print(f"\nfull summary written to {args.json}")
    elif args.cmd == "replay":
        rep = replay.load(args.file)
        print(replay.transcript(rep, reg, args.cards, show_hands=not args.hide_hands))
    elif args.cmd == "verify":
        p = Path(args.path)
        files = sorted(p.glob("*.json")) if p.is_dir() else [p]
        bad = 0
        for f in files:
            ok, msg = replay.verify(replay.load(f), reg, args.cards)
            if not ok:
                bad += 1
                print(f"FAIL {f}: {msg}")
        print(f"{len(files) - bad}/{len(files)} replays verified clean")
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
