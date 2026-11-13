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
| 2026-11-06 17:21 | 47% used, resets 12:50 PM | 29% used, resets Mon 10:00 AM | +3% in 21 min; adaptive + sharded round-robin, mulligan coach UI, Emperor's Dais may-pay and Gold payment fixes; PR #2 (focus/damage UI) merged |
| 2026-11-06 17:42 | 50% used, resets 12:50 PM | 29% used, resets Mon 10:00 AM | +3% in 21 min; 14 cards scripted (none 85 -> 71): Hard Bargain, Kraken Hunter, Commander Ledros, Mageseeker Warden, Temporal Portal... |
| 2026-11-06 18:04 | 2% used, resets 5:50 PM | 30% used, resets Mon 10:00 AM | new 5h window; Derrick (17:44): scripting stopped, round-robin redone (out/rr_1745, adaptive max 20, expert; container restart killed the first try, runner now resumes from partial.jsonl); UI asks went to the UI thread |
| 2026-11-06 18:25 | 2% used, resets 5:50 PM | 30% used, resets Mon 10:00 AM | round-robin 871 games, 44/45 matchups settled |
| 2026-11-06 19:09 | 4% used, resets 5:50 PM | 30% used, resets Mon 10:00 AM | 18:30 round-robin written up; Derrick (18:41) asked for a Riven rules check: tools/deck_audit.py found Switcheroo + Not So Fast never castable and Heron counting tokens (fixed 9783ead); round-robin re-run in out/rr_1900 |
| 2026-11-06 19:31 | 6% used, resets 5:50 PM | 30% used, resets Mon 10:00 AM | round-robin re-run on the fixed engine (900 games): Vex 72%, Rek'Sai 66%, Riven 65%; Riven beats Kai'Sa 14-6 |
| 2026-11-06 19:51 | 6% used, resets 5:50 PM | 30% used, resets Mon 10:00 AM | Riven audit and re-run reported to Derrick; all asks done; card scripting paused by him, so the thread is idle (no further checkpoints) until his next message |

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
- Script coverage (2026-11-06 17:40): auto 628, manual 428, keywords-only 23, partial 23, none 71, vanilla 23.
  RAD gallery data had wrong types/domains/tags on 84 cards: checked against the card images, fixed in data/cards/overrides.json.
  Common cards are hand-scripted in `riftsim/core/scripts/cards_common.py` (tests: tests/test_common_cards.py).
  Hand scripts for staples/legends/champions live in `riftsim/core/scripts/cards_staples.py` (tests: tests/test_legends.py, tests/test_champions.py).
- `data/decks/tournament/`: 12 decks (Rek'Sai added 2026-11-06 13:15; Sett added 2026-11-11 from Nation Clash Saturday, which now has individual ranks; specs in tools/deckspecs/radiance_2026-11.json). Top Radiance lists (Riven 1st CoolStuffCon Orlando $25k; Kai'Sa 3rd Convergence IV) from
  riftdecks.com qualifying events (3 relevance stars, 256+ players). Derrick wants these refreshed daily and every
  relevant legend covered eventually; Kai'Sa vs Riven is the matchup he cares about now.
- First Kai'Sa vs Riven batch (200 greedy games): Kai'Sa 52.5%, Riven 47.5%; first player ~58%. Exported to web/data.
  An mcts:50 batch of 40 games is running in out/kr_mcts (background).
- Supabase: tables created from `supabase/schema.sql` (project ndobcpnialrdregjtqdd); `web/config.js` holds the
  publishable key; `tools/upload_supabase.py` needs env SUPABASE_URL + SUPABASE_SERVICE_KEY (Derrick adds the secret).
  Frontend reads the latest batch/replays from Supabase and falls back to `web/data`.
- `tests/test_core_v2.py` is the v2 regression suite (pytest -q tests/). `tests/test_rules_audit.py` covers the 2026-11-06 audit.
  `tests/test_deep_audit.py` covers niche interactions (deep rules audit routine, every 5 h): effect plays obey "can't play"
  locks and Rockfall Path (CR 420.3.b), Baron Nashor + The Exile enters the Pit ready.
  Combat damage: `flow.DamageAssignments` counts legal assignments without listing them; over `ASSIGN_FLAT_LIMIT` (64) the
  player assigns one unit at a time (`assign_damage_step`, every offered amount still completes legally).
  `tools/errata_check.py [--decks]` lists cards whose data text predates the published errata (2026-11-07: 14 in the
  tournament decks, 56 overall); scripts must follow the errata text. Fixed: Guards!, Tideturner, Arise! (00:20),
  Elnuk Herd, Dark Child Starter, Sona Harmonious, Janna Savior, Yone (double trigger), Karma Channeler, Portal Rescue (05:20).
  Open: Diana, Lunari (does the reveal still happen if you don't pay? errata wording is ambiguous); unscripted errata
  cards (The Boss, Unlicensed Armory, Kato, Relentless Pursuit, Ava Achiever) wait for scripting to resume.
  10:20 (Kai'Sa check): the auto-scripter dropped [Legion] on "I cost [2] less" (Noxus Hopeful, 3 in Kai'Sa: always cost [2])
  and on activated abilities (Darius legends, Sun Disc); fixed. Round-robins before 2026-11-07 10:40 overrate Kai'Sa.
  15:20: the same drop hit [Level N] lines (Bandle Soldier, Scorchclaw always entered ready); `script_line` now puts the
  lead-flag condition on every ability it parses (test sweeps every [Legion]/[Empowered]/[Level N] line).
  20:20: "play me to an open battlefield" (Sai Scout, Sneaky Deckhand, Ocean Drake, Miss Fortune), "a battlefield you're
  attacking" (Rengar, Pouncing) and "an occupied enemy battlefield" (Deadbloom Predator, Dauntless Vanguard) were all
  "any battlefield"; now exact perms in `flow._play_locations`. Effect plays (PlayCard) use `_play_locations` too, and
  tokens count for Hunters' Circle.
  2026-11-08 00:20: "When you play me/this" triggers go on the chain before the card is on the board, so their "here"
  was empty: Faithful Manufactor made no Recruit, Mischievous Marai dealt nothing, Blitzcrank/Hunting Blind moved nobody
  (28 cards; in 7 tournament decks). `_add_trigger` now uses the play location. Also: Vex stuns token units, Tornado
  Warrior hand-scripted, delayed triggers no longer re-check their creator's targets. Round-robins before this underrate
  Rek'Sai, Riven, Vex, Akali, Azir, Viktor, Irelia.
  05:20: a scan for selectors with tags no card has (test_no_selector_uses_a_tag_no_card_has) found 11 misparsed
  auto-scripts ("something else", "it instead", "an opponent" read as tags); hand-scripted in cards_manual.py: Ekko
  Recurrent, Miss Fortune Captain, Royal Entourage, Sudden Storm, Monster Harpoon, Blast Cone, Ravenbloom Prefect,
  Ocean Drake, Possession, Blade Twirler, Scuttle Crab. A scan of 60 games found no trigger resolving without "here".
  10:20: a scan for variables an ability reads but never sets found Lillia, Fae Fawn ("move from ... there" played the
  Sprite nowhere); auto triggers now store the event's player as __p and a move's origin as __tloc.
  20:20: attack/defend triggers re-fired when a unit left a combat and came back (CR 383.4.e.2.a: once per combat);
  `flow._first_designation` keys them by (uid, entered_stamp). Late arrivals still attack once (CR 466.2.c.3.a).
  2026-11-09 05:20: the "target" event is now one per chosen object ("When you choose a friendly unit" triggers per unit);
  Blade Dancer's auto-script fired (and readied "it") when you chose only enemies; now needs a friendly unit target.
  10:20: a countered spell played from the trash (Flow, Kennen's granted Flow) went back to the trash and could be
  played again; `do_counter` now banishes it (CR 829.1.b.1).
  20:20: spells could choose themselves while being played (Hard Bargain, any Sel zone="chain"); `Sel.matches` now needs a
  finalized chain item (CR 355.9.a.2). Repeat executions re-validate their own targets (CR 820.1.d.2), Hard Bargain asks
  nobody to pay when its spell is gone, and a fizzled trash-played spell is banished like a countered one.
  2026-11-10 00:20: Not So Fast countered the first chain item of the chosen source, not the one that chose your unit
  (one source, two abilities), could pick unfinalized items, and skipped token sources; fixed in auto_grammar.
  05:20: a Repeat execution's choices never paid Deflect (CR 809.1.c, "each time they choose"): `flow._RepeatDeflect`;
  the "target" events now cover every execution's choices (Irelia triggers for the repeat's unit too).
  10:20: a hidden spell's unspecified-location unit token (Guards!) went to base/any battlefield; PlayToken "choose" now
  uses the battlefield it was hidden at (CR 811.1.d.5). Open: is "choose a battlefield" in a hidden play effect restricted?
  15:20: Ezreal, Prodigy's "[1] or [A] less" always took [A]; the player now picks (`Game.optional_cost_variants`, every
  variant's payment plans are offered). "You may pay [X] as an additional cost" (Sea Monkey, Crescent Guardian, Blast
  Corps Cadet, 11 cards) was paid on its own before the cost, so it could be paid and the card then not afforded; now it
  is an `additional_cost` decision paid with the total cost (CR 357). 
  20:20: Vex, Apathetic's "They can't move it this turn" locked the unit for every player; now keyword `cant_move_by`
  (players) and `valid_destination(..., mover=)`: Vex's side can still move it (Charm, Temptation, Blitzcrank).
  2026-11-11 00:20: Rhasa the Sunderer played from the trash (Last Rites, Kennen) counted itself as a card in your trash
  (cost [1] too low): it is on the chain when its cost is set. An 80-game greedy rules_audit found no problems.
  10:20: Cull the Weak / Acceptable Losses ("Each player kills one of their units/gear") were chosen while playing, so
  they needed a unit of your own and locked the picks before responses; now picked at resolution (CR 355.10.e, the
  Choose's `at_resolution` flag keeps it out of `targeting.split_choices`), caster first, killed together.
  15:20: "The next spell you play this turn deals 1 Bonus Damage" (Ravenborn Tome) was spent by the first Deal of any
  source and given to one Deal only; now taken by the next spell played (ctx `__spell_bonus`), every Deal of it.
  20:20: "that battlefield" in auto triggers (Irresistible Faefolk, Vex, Mocking, Exemplar of Demacia) read `__bl`,
  which nothing set, so the move went nowhere; the trigger now stores the event's location as `__bl`. rules_audit no
  longer reports lethal damage on a unit waiting on an optional die replacement (Sett, The Boss).
  2026-11-12 00:20: "you may pay [N] to stun/move/give a unit ..." (Kennen, Keeper of Balance, Icevale Archer, Sinister
  Poro, Mask Mother, Portable Portal, Exemplar of Demacia) chose the unit at resolution after paying; it is a target
  chosen as the trigger goes on the chain, whatever the pay decision (CR 355.12): `auto_grammar._lift_choices`.
  05:20: "choose one" modes (Udyr, Wildman, Aphelios, Riven, Broken Blade, Royal Entourage, Jayce, Hammer in Hand,
  Reckless Innovator ...) were picked at resolution; the mode and its targets are now picked as the item goes on the
  chain (CR 355.3/355.5: `targeting.split_choices` hoists a top-level ChooseMode, `ops.ModeDispatch` runs the body),
  modes whose targets can't be chosen aren't offered, and `flow._targets_possible` needs one legal mode.
  10:20: "When ..., you may ..." was decided at resolution; it is decided as the trigger is finalized (CR 383.3.a,
  `targeting.split_trigger`): no removes it from the chain as if it never triggered (a once-each-turn one can fire
  again, 383.3.e.2.b), and a cost right after the "you may" ("you may pay [2] to ...") is paid then (383.3.b).
  15:20: "you may exhaust me [and pay [A]] to ..." is now that base cost too (`targeting._peel_costs`): Irelia, Rek'Sai,
  Vex (Gloomist) and Nasus (Curator) legends, Sivir, Renata, Exemplar ... exhaust as the trigger is finalized, and
  yes is only offered while the source is ready.
  20:20: "When X, if Y, ..." re-checked Y on resolution in 10 hand scripts (Tomb-Raider Barbara, Kha'Zix, Mutating
  Horror, both Shens, Swain, Poppy, Jarvan IV, Cosmic Vista, Poro Herder, Patched Porobot, Dropboarder); Y is part of
  the trigger condition only (CR 383.2.a.1). `Triggered(..., intervening=cond(g, ctx))` checks it when X happens.
  2026-11-13 00:20: units dying together saw each other die when the other came first in the batch (Viktor, Leader
  made a Recruit dying with another unit; CR 383.2.c.2 says no). `do_kill` now marks the whole batch as `_leaving` and
  `_collect_triggers` skips their triggers except for their own death/leave (383.2.c.3).
  05:20: Wraith of Echoes ("The first time a friendly unit dies each turn") was a once-each-turn trigger, so it fired on
  a later death when the first one happened before it was on the board; it now needs the turn's first batch of
  friendly deaths (turn_memo `first_unit_die_batch`, CR 383.1.b). Manual "Nth time" scripts already count per turn.
  10:20: "Its controller draws 2" (Hidden Blade) read the controller after the kill, when it had reset to the owner:
  killing a unit you had taken control of made its owner draw. `_to_zone` keeps the last known controller
  (temp `__lk_controller`) for `ops.controller_of`; "its owner channels" (Retreat) now uses `ops.owner_of`.
  15:20 (16:05): Transpositionist ("Return a friendly unit ... You may play a unit with less Might than that unit had")
  excluded the returned card, so a buffed unit could not be replayed; the card in hand is a new object with its printed
  Might. Checked OK: Deathgrip and Heedless Resurrection use the killed unit's last known Might/cost.
  20:20: the Awaken Phase readied objects without the Ready action's event (CR 315.1.b, 416.3.a), so "When I become
  ready" (Jayce, Hammer in Hand; Fretful Feline), Irelia, Fervent and Pirate's Haven never triggered at the start of
  the turn; `flow._awaken` now emits "ready" per readied object. Pirate's Haven no longer triggers on runes.
- Testing speed (2026-11-06): `tools/audit_games.py --adaptive 40` stops each matchup once its 95% Wilson interval is
  clear (min 6, even game counts) and prints a matchup table; `--shard I/N` + `--merge` split a round-robin; the
  `Round-robin (sharded)` GitHub Actions workflow (manual, repo is private so it uses Derrick's Actions minutes) runs
  N shards in parallel. Engine caches per state version (`_board_statics`, `_trigger_index`, rules) gave ~25%.
- Legal-action audit (2026-11-07, Derrick: every option for each player, incl. passing, Ganking, runes left up, gear):
  `tools/rules_audit.py N SEED [random|greedy|expert]` now also checks missing plays, rune actions, hides, Deploy
  locations, ability timing and who holds the decision; tests in tests/test_legal_actions.py. Fixed: Deploy gear could
  be played to base (CR 830.1.b), Quick-Draw gear could Equip at Reaction speed (Equip has no timing keyword, 818.1.c.2),
  hiding during your own showdown with Focus was missing (811.1.b 'Open State'), and the AIs' option cap sampled the
  list at random (could drop 'end turn' or a play); `policies.prune_options` now thins only move groups.
- AIs and the coach never see hidden information: every lookahead uses `policies.determinize` (see memory).
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
  16:50: showdown Focus strip on the battlefield (who has Focus, passes in a row), "◉ focus" on the seat, pass lines in the
  log; combat strip (attack vs defend Might), ATK/DEF badges, assigned damage on each unit (combat.assign), assign_damage
  options drawn as bars with "dies"; play.js serialises grade/apply so clicking during grading no longer stalls the page.
  17:55 (Derrick: feel like a digital TCG client): drag hand cards onto the board to play them and drag units (click several
  to pick them, then drag one) to move them; `PlaySession.decision_view` adds `meta` per action option ({k, uids, to: data-zone key})
  and `plans` per pay option (runes exhausted/recycled). Runes are drawn with their card art: on your turn a click offers
  exhaust/recycle, during a payment a click cycles tap -> recycle -> undo and "Pay" picks the matching plan (same-domain runes are
  interchangeable). Score is a big number plus a numbered 1..8 track; hand is a fan; round End turn / Pass button on the mat.
- Learning (Derrick 2026-11-06 20:55: "the main focus of this project", the AI must get stronger with practice):
  `riftsim/core/learn/` (features from one seat only, tested against determinize; value net with a pure-Python forward
  pass; `learned[:gen]` / `learned-mcts:N[:gen]` policies) and `tools/train_loop.py generation` (self-play with the best
  AI -> train -> gate head to head -> promote at 55%+). Models, `models/ladder.md`, history and control matches are in
  `models/`; self-play data goes to /mnt/project-files/riftshark/learn (not git). Key finding: judging every option at the
  start of the next turn (`learn.policy.to_turn_end`) is what makes the AI strong: with the hand-written score it beats
  expert 87-13 (`learned:heuristic`, the current best and the play page's "Learned" level). Plain nets lost to it;
  net v2 learns a correction on top of the score and tied it on expert data; gen 2 self-plays with the lookahead AI.
  2026-11-07 01:20 round-robin with that AI (Actions, 874 games): docs/results/round_robin_2026-11-07_learned.md (Kai'Sa 79%,
  Void Burrower 65%, Riven 61%, Viktor 61% ... Gloomist 44%, Irelia 16%; Kai'Sa beats Riven 11-3). The background container
  is reclaimed when the thread is idle with no Monitor attached: keep a Monitor on long local runs.
  The 5-hourly "RiftShark round-robin training" routine should run a generation and then a round-robin with `--policy learned`.
  2026-11-12 AI v2 (docs/plans/ai_v2.md, docs/results/ai_v2_2026-11-12.md): policy net `models/policy_g14.json`
  (`policy:REF`) + two-turn search `search-v2` (= `learned:gen_014:p=policy_g14:ps3:crn:b=0.3:d10`) beat gen 14 65-35
  and 60-37. ~15-20x slower per move; gates need `RIFTSHARK_GAME_LIMIT=4000`. Gen 14 stays the fast default.
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
3. DONE 2026-11-06: mulligan (CR 117, decision `mulligan`). Optional replacements: 2026-11-10 'die' ones work
   (`Replacement(optional=True, options=...)`, decision `optional_replacement`; do_kill keeps the unit on the board
   and pushes `game._OptionalReplacementStep`); Mordekaiser, Twice Slain scripted (tests/test_optional_replacement.py:
   kill him as Whirling Twirligig's cost, he eats the Recruit, the Mech still comes, CR 203.2). Zilean, Heimerdinger,
   Sett need other event kinds. Also fixed: "heal, exhaust and recall" on a unit already in base now heals/exhausts it.
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
  Latest (18:30, post-audit engine, expert, 880 games): docs/results/round_robin_2026-11-06_1830.md (Riven 71%, Vex 68%,
  Rek'Sai 64%, Kai'Sa 57% ... Azir 21%; Kai'Sa vs Riven 8-12). Card scripting paused by Derrick at 17:44.
  19:30 re-run after the Riven audit fixes: docs/results/round_robin_2026-11-06_1930.md (Vex 72%, Rek'Sai 66%, Riven 65%,
  Kai'Sa 56%; Riven 14-6 vs Kai'Sa). `tools/deck_audit.py GAMES.json KEY` replays one deck's games and counts every card use.

## Next steps

1. Keep raising auto-scripter coverage; hand-script legends/champions and competitive staples in
   `riftsim/core/scripts/cards_manual.py`.
2. Port policies (greedy, MCTS with determinisation), replay save/verify and the batch runner to v2.
3. GitHub Pages frontend (stats + visual replay viewer with card images) and Supabase upload.
4. Self-play training: value net in place (see Learning above); next a policy head / learned MCTS priors.

## Conventions

- Python 3.13, no third-party deps for the engine; tests with pytest under `tests/`.
- Commit messages end with the session attribution lines; never put model identifiers in code or commits.
