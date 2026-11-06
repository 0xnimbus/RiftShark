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
- Script coverage (2026-11-06 02:45): auto 613, manual 9, keywords-only 56, partial 66, none 429, vanilla 23.
- `data/decks/tournament/`: top Radiance lists (Riven 1st CoolStuffCon Orlando $25k; Kai'Sa 3rd Convergence IV) from
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
  Left to do: compact layout for small screens, animate cards moving between zones, check pay/order_triggers/mulligan labels once
  the engine thread lands them.
- Main deck = 39 cards + chosen champion (CR 103.3). `When you play me` triggers fire from the chain.
- `riftsim/` top level still holds the v1 simplified engine (engine.py, policies.py, replay.py, runner.py, cli.py).
  It will be replaced by v2 equivalents.

## HARD RULE (Derrick, 2026-11-06 03:07): no simplified cards or rules. Everything must run exactly as in the real game.

Every entry in the RULES.md "Simplifications" list is a bug to fix, in this order (each affects every game first):
1. DONE 2026-11-06 03:30: rune payment is a `pay` decision over distinct plans (`riftsim/core/payment.py`), rune
   float actions ("rune", exhaust|recycle, uid), Add restrictions enforced via payment purpose, effect payments always
   optional. AIs skip floats (`policies.ai_options`) and rollouts use the standard plan; one-ply lookahead pays
   before evaluating. Old replays no longer verify (new decisions): re-run batches and re-export web/data.
2. Simultaneous triggers ordered by their controller (CR 383) via a Decision, not automatically.
3. Mulligan at game start (CR 1v1 setup); optional replacement effects as a Decision; enforce "Add" restrictions.
4. `[Show Off]`, Baron Pit token, Blade of the Exile alternative Equip cost, Scuttle Crab reveal; remove the 60-turn cap
   once games are proven to end (or make it a loud error, never a silent draw).
5. Script every card (`python -m riftsim.core coverage`: 425 none / 67 partial / 55 keywords-only on 2026-11-06), and
   make `Deck.validate` refuse (or the batch/coach warn loudly about) any card whose script_status is not auto/manual/
   vanilla, so nothing is simplified silently. Add per-card tests against printed text for the tournament decks first.
Until this is done, treat the published win rates and coach grades as provisional and say so in the UI.

## Next steps

1. Keep raising auto-scripter coverage; hand-script legends/champions and competitive staples in
   `riftsim/core/scripts/cards_manual.py`.
2. Port policies (greedy, MCTS with determinisation), replay save/verify and the batch runner to v2.
3. GitHub Pages frontend (stats + visual replay viewer with card images) and Supabase upload.
4. Self-play training (policy/value net) on top of MCTS.

## Conventions

- Python 3.13, no third-party deps for the engine; tests with pytest under `tests/`.
- Commit messages end with the session attribution lines; never put model identifiers in code or commits.
