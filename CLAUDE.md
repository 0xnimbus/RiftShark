# RiftShark — status and handoff

Competitive-grade Riftbound (Riot TCG) match simulator: rules engine, card scripts, search/self-play AI,
replays, batch runner, web frontend. Owner: Derrick (GitHub `0xnimbus`).

## Usage checkpoints (Derrick's Claude plan, recorded every ~20 min)

| Time (UTC) | Session (5h window) | Week | Note |
|---|---|---|---|
| 2026-11-06 01:48 | 40% used, resets Fri 12:40 AM | 13% used, resets Mon 10:00 AM | Max plan; on track |

## Where things stand

- `data/cards/riftbound.json`: 1180 cards (OGN, OGS, SFD, UNL, VEN, RAD) from the official gallery + riftcodex promos.
  `data/cards/overrides.json` fixes gallery typos (9 RAD cards mistyped as units). 13 RAD cards still lack
  domains in the source data (`data_incomplete`), to be read from their images.
- `docs/rules/`: Core Rules 2026-10-09 (text + PDF), errata, patch notes, tournament rules.
- `riftsim/core/`: engine v2 (rules-accurate). `vm.py` bytecode VM + `Decision`; `ops.py` instruction set;
  `selectors.py`; `abilities.py` (+ `TRIGGERS` table); `objects.py`; `game.py` (actions, layers, events, costs);
  `flow.py` (turns, HOT FEPR chain, cleanups per CR 323, showdowns, combat per CR 466-468, scoring);
  `deck.py`; `scripts/` (keywords → auto-grammar → manual overrides).
- `tools/smoke_core.py N SEED`: random-play games; last run 40/40 games without crash, ~0.1 s per game.
- Script coverage (2026-11-06 01:48): auto 500, keywords-only 69, partial 77, none 527, vanilla 23.
- `riftsim/` top level still holds the v1 simplified engine (engine.py, policies.py, replay.py, runner.py, cli.py).
  It will be replaced by v2 equivalents.

## Known simplifications (must stay documented in RULES.md)

Rune payment is automatic (greedy heuristic), simultaneous triggers are ordered automatically (turn player
first), optional replacement effects are auto-applied, mulligan is skipped, "Add" restrictions (spend only on X)
are not enforced, `[Show Off]` is not implemented.

## Next steps

1. Keep raising auto-scripter coverage; hand-script legends/champions and competitive staples in
   `riftsim/core/scripts/cards_manual.py`.
2. Port policies (greedy, MCTS with determinisation), replay save/verify and the batch runner to v2.
3. GitHub Pages frontend (stats + visual replay viewer with card images) and Supabase upload.
4. Self-play training (policy/value net) on top of MCTS.

## Conventions

- Python 3.13, no third-party deps for the engine; tests with pytest under `tests/`.
- Commit messages end with the session attribution lines; never put model identifiers in code or commits.
