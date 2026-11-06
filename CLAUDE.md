# RiftShark — status and handoff

Competitive-grade Riftbound (Riot TCG) match simulator: rules engine, card scripts, search/self-play AI,
replays, batch runner, web frontend. Owner: Derrick (GitHub `0xnimbus`).

## Usage checkpoints (Derrick's Claude plan, recorded every ~20 min)

| Time (UTC) | Session (5h window) | Week | Note |
|---|---|---|---|
| 2026-11-06 01:48 | 40% used, resets Fri 12:40 AM | 13% used, resets Mon 10:00 AM | Max plan; on track |
| 2026-11-06 02:03 | 56% used, resets Fri 12:40 AM | 15% used, resets Mon 10:00 AM | ~16%/20 min; session likely exhausted around 03:00 UTC |
| 2026-11-06 02:24 | 62% used, resets Fri 12:40 AM | 16% used, resets Mon 10:00 AM | +6% in 21 min (batch runs are cheap); continuing |
| 2026-11-06 02:45 | 72% used, resets Fri 12:40 AM | 17% used, resets Mon 10:00 AM | +10% in 21 min; one more block, then likely stop near 03:05 |
| 2026-11-06 03:08 | 85% used, resets Fri 12:40 AM | 19% used, resets Mon 10:00 AM | last block: Vercel setup + handoff, then stop until the session resets |
| 2026-11-06 03:30 | (switched to Opus by Derrick at 03:13) | | Derrick asked to stop after this commit: credits running low. Next: items 2-5 below, then re-run Kai'Sa vs Riven batches |
| 2026-11-06 05:55 | 6% used, resets 5:40 AM | 21% used, resets Mon 10:00 AM | new 5h window; Opus; decks + targeting work |
| 2026-11-06 06:11 | 10% used, resets 5:40 AM | 21% used, resets Mon 10:00 AM | +4% in 16 min; continuing |
| 2026-11-06 06:47 | 13% used, resets 5:40 AM | 22% used, resets Mon 10:00 AM | +3% in 36 min; continuing |
| 2026-11-06 07:05 | 18% used, resets 5:40 AM | 22% used, resets Mon 10:00 AM | +5% in 18 min; exact-rules items 2-4 done, round-robin done |
| 2026-11-06 13:09 | 2% used, resets 12:50 PM | 23% used, resets Mon 10:00 AM | thread was idle 07:21-13:07 (no wake scheduled); resuming item 5 (script remaining cards) |
| 2026-11-06 13:30 | 9% used, resets 12:50 PM | 24% used, resets Mon 10:00 AM | +7% in 21 min; Rek'Sai deck, 15 legends, coach fix, UI PR merged |
| 2026-11-06 13:53 | 12% used, resets 12:50 PM | 24% used, resets Mon 10:00 AM | +3% in 23 min; 5 hard legends + 11 champions scripted, 6 engine fixes |
| 2026-11-06 14:19 | 15% used, resets 12:50 PM | 25% used, resets Mon 10:00 AM | +3% in 26 min; ~70 champions scripted (none 314, partial 32); 20-per-pair round-robin running (out/rr20); browser coach depth 100 |
| 2026-11-06 14:43 | 18% used, resets 12:50 PM | 25% used, resets Mon 10:00 AM | +3% in 24 min; Repeat fix (CR 820), rr20 restarted 14:34 (180/900) |
| 2026-11-06 15:03 | 22% used, resets 12:50 PM | 26% used, resets Mon 10:00 AM | +4% in 20 min; 12 champions scripted, paid-additional-cost and [Calm]-cost fixes; rr20 restarted 14:58 |
| 2026-11-06 15:24 | 25% used, resets 12:50 PM | 26% used, resets Mon 10:00 AM | +3% in 21 min; 85 common cards scripted (none 306 -> 222), cards_common.py; rr20 at ~560/900 |
| 2026-11-06 15:45 | 30% used, resets 12:50 PM | 27% used, resets Mon 10:00 AM | +5% in 21 min; 84 RAD cards fixed from images, equipment keywords fix, batch triggers; rr20 written up, re-run on fixed engine in out/rr20b |
| 2026-11-06 16:11 | 33% used, resets 12:50 PM | 27% used, resets Mon 10:00 AM | +3% in 26 min; 55 more cards scripted (none 148 -> 93), Elder Dragon/Seraphic Wyvern/enter-ready-token engine support; rr20b at ~560/900 |
| 2026-11-06 16:39 | 38% used, resets 12:50 PM | 28% used, resets Mon 10:00 AM | +5% in 28 min; round-robins paused by Derrick (16:12) for a full rules audit: keyword data, damage assignment, moves, burn out fixed (report: RULES.md audit section) |
| 2026-11-06 17:00 | 44% used, resets 12:50 PM | 28% used, resets Mon 10:00 AM | +6% in 21 min; hidden-card targeting fix, AI never sees hidden info (determinize everywhere), engine ~25% faster |

## Where things stand

- `data/cards/riftbound.json`: 1180 cards (OGN, OGS, SFD, UNL, VEN, RAD) from the official gallery + riftcodex promos.
  `data/cards/overrides.json` fixes gallery typos; all RAD types/domains/tags were checked against the card images
  on 2026-11-06 (images at each card's `image` URL).
- `docs/rules/`: Core Rules 2026-10-09 (text + PDF), errata, patch notes, tournament rules.
- `riftsim/core/`: engine v2 (rules-accurate). `vm.py` bytecode VM + `Decision`; `ops.py` instruction set;
  `selectors.py`; `abilities.py` (+ `TRIGGERS` table); `objects.py`; `game.py` (actions, layers, events, costs);
  `flow.py` (turns, HOT FEPR chain, cleanups per CR 323, showdowns, combat per CR 466-468, scoring);
  `deck.py`; `scripts/` (keywords → auto-grammar → manual overrides).
- `tools/smoke_core.py N SEED`: random-play games; last run 40/40 games without crash, ~0.1 s per game.
- Script coverage (2026-11-06 16:11): auto 628, manual 401, keywords-only 28, partial 23, none 93, vanilla 23.
  RAD gallery data had wrong types/domains/tags on 84 cards: checked against the card images, fixed in data/cards/overrides.json.
  Common cards are hand-scripted in `riftsim/core/scripts/cards_common.py` (tests: tests/test_common_cards.py).
  Hand scripts for staples/legends/champions live in `riftsim/core/scripts/cards_staples.py` (tests: tests/test_legends.py, tests/test_champions.py).
- `data/decks/tournament/`: 10 decks (Rek'Sai added 2026-11-06 13:15; specs in tools/deckspecs/radiance_2026-11.json). Top Radiance lists (Riven 1st CoolStuffCon Orlando $25k; Kai'Sa 3rd Convergence IV) from
  riftdecks.com qualifying events (3 relevance stars, 256+ players). Derrick wants these refreshed daily and every
  relevant legend covered eventually; Kai'Sa vs Riven is the matchup he cares about now.
- First Kai'Sa vs Riven batch (200 greedy games): Kai'Sa 52.5%, Riven 47.5%; first player ~58%. Exported to web/data.
  An mcts:50 batch of 40 games is running in out/kr_mcts (background).
- Supabase: tables created from `supabase/schema.sql` (project ndobcpnialrdregjtqdd); `web/config.js` holds the
  publishable key; `tools/upload_supabase.py` needs env SUPABASE_URL + SUPABASE_SERVICE_KEY (Derrick adds the secret).
  Frontend reads the latest batch/replays from Supabase and falls back to `web/data`.
- `tests/test_core_v2.py` is the v2 regression suite (pytest -q tests/).
- Play & coach (Derrick's request 2026-11-06): `tools/play_server.py` + `web/play.html` + `riftsim/core/analysis.py`.
  Grades use MCTS win% loss vs best option; thresholds in analysis.GRADES. `riftsim/core/playsession.py` is shared by the
  server and the browser build: `tools/build_web_engine.py` copies the engine + cards + decks into `web/engine/`
  (gitignored, built by the Pages workflow) and `web/engine_worker.js` runs it with Pyodide 0.27 from jsdelivr when
  `/api/decks` does not answer. Measured in headless Chromium: ~6 s to start, 5-11 s per move at mcts:60/analysis 60.
  Derrick's PC has only Python 3.10 and Claude's auto-mode there refused to run the cloned server; the browser build is the
  way for him to play. Hosting: Vercel (`vercel.json`: build `python3 tools/build_web_engine.py`, output `web/`),
  imported from the GitHub repo through Derrick's Vercel account in Chrome on 2026-11-06; live at https://riftshark.vercel.app/play.html
  (auto-deploys on push to main; verified in Derrick's Chrome). The deck lists on the page only show decks that pass
  Deck.validate (fully scripted). GitHub Pages stays as a fallback.
- UI redesign (2026-11-06 03:30, branch claude/project-thread-awnl3n): playmat board in `web/board.js` (turn/phase bar, score pips,
  legend/champion/rune zones, battlefields with art, exhausted = rotated + dimmed + label, card preview tooltip with text and
  status help, "why can't I play this"), plain-language log and decision explanations (`RiftBoard.say/describe/explain`, already
  covers pay/order_triggers/mulligan), click a glowing hand card to play it. Play page no longer greys out: `PlaySession.apply` →
  `ai_step` (one AI decision per call, shown from a display queue while the opponent hand shows "thinking") → `grade`.
  2026-11-06 06:00: cards slide between zones (FLIP in `RiftBoard.render`, opponent cards fly out of their hand), phone layout
  (<=760px: smaller cards, decision panel fixed at the bottom), rune float options grouped as "Use runes now".
  Chain lane (06:10): the chain shows in the middle of the board, oldest left, "resolves next" right, with kind, controller,
  targets (PlaySession reads chosen uids from each item's ctx.vars) and trigger cause; who has priority; log lines indent by
  chain depth (`RiftBoard.chainStep`). The page sends a fresh random seed per game unless one is typed in, and shows it.
  Mulligan (06:50): hand view, click up to two cards then confirm (`decision.option_uids` from PlaySession); order_triggers
  explained one pick at a time. 07:00: Difficulty picker (novice..elite, default advanced), show_off decisions, any number of
  battlefields, facedown cards the human knows drawn face up (`facedown_known`), cards only slide when they change zone.
- Main deck = 39 cards + chosen champion (CR 103.3). `When you play me` triggers fire from the chain.
- `riftsim/` top level still holds the v1 simplified engine (engine.py, policies.py, replay.py, runner.py, cli.py).
  It will be replaced by v2 equivalents.

## HARD RULE (Derrick, 2026-11-06 03:07): no simplified cards or rules. Everything must run exactly as in the real game.

Every entry in the RULES.md "Simplifications" list is a bug to fix, in this order (each affects every game first):
1. DONE 2026-11-06 03:30: rune payment is a `pay` decision over distinct plans (`riftsim/core/payment.py`), rune
   float actions ("rune", exhaust|recycle, uid), Add restrictions enforced via payment purpose, effect payments always
   optional. AIs skip floats (`policies.ai_options`) and rollouts use the standard plan; one-ply lookahead pays
   before evaluating. Old replays no longer verify (new decisions): re-run batches and re-export web/data.
2. DONE 2026-11-06: simultaneous triggers ordered by their controller (CR 383), decision `order_triggers`.
3. DONE 2026-11-06: mulligan (CR 117, decision `mulligan`). Optional replacements: engine refuses them (4 unscripted
   cards need them; build a decision path before scripting those).
4. DONE 2026-11-06: Show Off (CR 832), Baron Pit, Blade of the Exile alt cost, Scuttle Crab information; the 60-turn cap
   is reported as unfinished with a warning (0 of 216 round-robin games hit it).
5. Script every card (`python -m riftsim.core coverage`: 425 none / 67 partial / 55 keywords-only on 2026-11-06), and
   make `Deck.validate` refuse (or the batch/coach warn loudly about) any card whose script_status is not auto/manual/
   vanilla, so nothing is simplified silently. Add per-card tests against printed text for the tournament decks first.
Until this is done, treat the published win rates and coach grades as provisional and say so in the UI.

Bugs Derrick reported 2026-11-06 03:35 (do first next session, before item 2):
- Playing as the first player (P0 seat in play.html), he does not start his first turn with 2 runes. Check the
  Channel phase on turn 1 (CR: 2 runes per turn, second player 3 on their first turn) and what the page shows.
- Battlefield effects seem not to apply in play. Check every battlefield in the two tournament decks (Void Gate,
  Frozen Fortress, Rockfall Path, Emperor's Dais, Rakelstake, Star Spring) fires/applies in real games, add tests.

- AI levels (2026-11-06, 20 games each): random 7-13 novice, novice 8-12 intermediate, intermediate 6-14 advanced,
  advanced 7-13 expert, advanced 2-10 elite (mcts:120, ~5 min per game). Round-robin of the 9 tournament decks:
  docs/results/round_robin_2026-11-06.md (Vex 75%, Riven 65%, Kai'Sa 62% ... Azir 25%).

## Next steps

1. Keep raising auto-scripter coverage; hand-script legends/champions and competitive staples in
   `riftsim/core/scripts/cards_manual.py`.
2. Port policies (greedy, MCTS with determinisation), replay save/verify and the batch runner to v2.
3. GitHub Pages frontend (stats + visual replay viewer with card images) and Supabase upload.
4. Self-play training (policy/value net) on top of MCTS.

## Conventions

- Python 3.13, no third-party deps for the engine; tests with pytest under `tests/`.
- Commit messages end with the session attribution lines; never put model identifiers in code or commits.
