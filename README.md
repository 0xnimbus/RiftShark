# riftsim: Riftbound match simulator

Runs many Riftbound games in parallel between scripted players, records every game as a
replay, and reports win rates and which cards show up in winning lines.

```
pip install pytest            # only needed for the tests
python -m pytest -q tests

# 200 games, both seats greedy, alternate seats each game, save replays + full stats
python -m riftsim batch data/decks/fury_aggro.json data/decks/mind_control.json \
    --games 200 --policies greedy greedy --replays out/replays --json out/summary.json

# search player (MCTS) in seat 0 vs greedy in seat 1
python -m riftsim batch data/decks/fury_aggro.json data/decks/mind_control.json \
    --games 20 --policies mcts:iterations=200 greedy

# watch a game back, step by step, with every player's hand, runes, units and the events each action caused
python -m riftsim replay out/replays/game_00007.json

# re-simulate every saved game and check every action against the rules engine
python -m riftsim verify out/replays/
```

## Layout

| Path | What it is |
|---|---|
| `riftsim/cards.py` | Card / legend / deck definitions loaded from JSON, deck legality checks |
| `riftsim/state.py` | Game state with a fast `clone()` (search makes thousands of copies) |
| `riftsim/engine.py` | Rules: setup, turn structure, costs, combat, effects, `legal_actions()`, `apply()` |
| `riftsim/policies.py` | Players: `random`, `greedy` (1-ply + heuristic), `mcts` (tree search with hidden-info determinization) |
| `riftsim/runner.py` | Parallel batch runner and stats aggregation |
| `riftsim/replay.py` | Save / load / re-simulate / verify / print replays |
| `riftsim/cli.py` | Command line |
| `data/cards/*.json` | Card sets (placeholder set included) |
| `data/decks/*.json` | Decklists |
| `RULES.md` | Exactly which rules are modeled and which are not yet |

## How replays work

The engine is deterministic given the decks, a seed and the list of actions, so a replay is
just those four things (`out/replays/game_XXXXX.json`). `verify` replays the actions through a
fresh engine and checks each one against `legal_actions()` before applying it, and checks the
recorded winner matches. That catches both a policy cheating and an engine bug that let an
illegal action through. `replay` prints the full state after every action, so you can read a
game like a log.

## Adding cards

Add entries to a card set JSON. Supported fields: `type` (unit / spell / champion), `domains`,
`energy`, `power` (list of domains), `might`, `keywords` (`assault`, `shield`, `tank`,
`ganking`, `accelerate`), `effect` (`draw`, `damage`, `buff`, `kill_if_might_le`,
`ready_runes`, with optional `target` and, for units, `"trigger": "play"`). Anything the
engine does not support yet needs a new branch in `engine._resolve_effect`; see `RULES.md`.

## Policies

`--policies` takes one spec per deck (first spec plays the first deck). Seats alternate between games so first-player advantage is shared. `mcts` options: `iterations` (default 200),
`rollout_depth` (12), `c` (1.2), `rollout` (`greedy` or `random`). Greedy is roughly 1000
games/minute on 4 cores; MCTS at 100 iterations is around 2 games/minute per core, so use it
for targeted questions rather than big sweeps.
