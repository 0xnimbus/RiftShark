# RiftShark: Riftbound match simulator

Rules-accurate Riftbound (Riot's League of Legends TCG) engine, card scripts for every set including Radiance,
search-based AI players, verifiable replays, a parallel batch runner, and a web dashboard with a visual replay viewer.
See `RULES.md` for what the engine models and where it simplifies, and `CLAUDE.md` for status and handoff notes.

```
python -m pytest -q tests                      # regression suite (no third-party deps for the engine itself)

# 200 games between the two tournament lists, both seats greedy, seats alternate, replays with board snapshots
python -m riftsim.core batch --decks data/decks/tournament/kaisa_void.json data/decks/tournament/riven_exile.json \
    --games 200 --policy greedy --policy greedy --replays out/kr/replays --out out/kr/results.json --snapshots

# MCTS (50 iterations per decision) in both seats
python -m riftsim.core batch --decks A.json B.json --games 40 --policy mcts:50 --policy mcts:50 --out out/mcts.json

python -m riftsim.core replay out/kr/replays/game_0.json.gz      # transcript of one game
python -m riftsim.core verify out/kr/replays/game_0.json.gz      # re-simulate and check every recorded choice was legal
python -m riftsim.core coverage                                  # which cards' text is not fully scripted yet
python -m riftsim.core deck --legend "Blind Monk" --champion "Lee Sin"   # generate a sample legal deck

python tools/play_server.py                    # play a deck vs the AI at http://localhost:8765/play.html with move grading
python tools/build_web_engine.py               # bundle the engine into web/engine so play.html also runs server-less (Pyodide)
python tools/export_web.py out/kr/results.json out/kr/replays web/data --max-replays 10   # static data for web/
SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python tools/upload_supabase.py out/kr/results.json out/kr/replays
```

## Layout

| Path | What it is |
|---|---|
| `data/cards/riftbound.json` | 1180 cards from the official gallery (+ promos), with `overrides.json` corrections |
| `data/decks/tournament/` | Deck lists taken from riftdecks.com qualifying events (3 relevance stars, 256+ players) |
| `docs/rules/` | Core Rules 2026-10-09, errata, patch notes |
| `riftsim/core/` | Engine v2: `vm.py` (bytecode VM, decisions), `ops.py` (instructions), `game.py` (actions, layers, events), `flow.py` (turns, chain, showdowns, combat, scoring), `abilities.py`, `objects.py`, `deck.py`, `policies.py`, `replay.py`, `runner.py`, `cli.py` |
| `riftsim/core/scripts/` | Card scripting: keywords, the text grammar (`auto_grammar.py`), hand-written scripts (`cards_manual.py`) |
| `web/` | Static dashboard + replay viewer (GitHub Pages via `.github/workflows/pages.yml`); reads Supabase when configured |
| `supabase/schema.sql` | Tables for batches, games, deck/card stats and replays |
| `riftsim/core/analysis.py` | Move analysis: MCTS win% per option, chess-style grades (best/good/inaccuracy/mistake/blunder), replay review |
| `tools/` | `smoke_core.py` (random games), `export_web.py`, `upload_supabase.py`, `play_server.py` (play & coach, local), `build_web_engine.py` (browser bundle) |
| `tests/` | pytest suite |
| `riftsim/*.py` (top level) | The v1 simplified engine, kept until everything is ported |

## How a game is simulated

`Game.run()` advances the state until a player must decide and returns a `Decision` listing every legal option;
`Game.choose(option)` applies one. Policies (`random`, `greedy`, `mcts:N`) pick options. A replay is the deck lists,
the seed and the list of choices; `verify` replays it from scratch and confirms every choice was legal and the result
matches, which is the rules audit for every published game.
