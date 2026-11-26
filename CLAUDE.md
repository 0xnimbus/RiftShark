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
  2026-11-14 05:20: "When a combat that I was in ends" (Mournful Witness, Affectionate Poro) only saw units still at
  the battlefield, so attackers recalled after a tie never triggered; combat_end's survivors now include every unit
  designated in that combat that is still the same object on the board (CR 740.2.c). A trigger-fire count over 40
  greedy games (scratch script, every tournament card with a trigger) found no other dead triggers.
  10:20: Minotaur Reckoner ("Units can't move to base.") shared Vilemaw's Lair's "from here" rule, so it only stopped
  units at Reckoner's own location; the rule now carries "all" or "here" (game.valid_destination, rules_audit).
  15:20: Zhonya's Hourglass saved whichever friendly unit came first when two died together; its controller now picks
  (CR 373, decision `order_replacement`, `Replacement(single_use=True)`, game._ReplacementOrderStep). Checked OK:
  facedown Zhonya does nothing, Soraka's replacement sees units dying with her (CR 370.4), final point rule.
  20:20: Smite on a unit whose controller had Zhonya's Hourglass spent Zhonya's and still banished the unit: a death
  replaced by a recall/banish took more 'die' replacements. `replace_event` now stops once a death is replaced, and
  when several could replace one death its controller picks (CR 372, `Game.die_replacements`, game._ReplacementChoiceStep,
  decision `order_replacement` with index options). Guardian Angel vs Zhonya's is that player's pick too.
  2026-11-15 00:20: [Stun] exhausted the unit, so a ready unit stunned in the main phase couldn't move or pay exhaust
  costs; CR 424.1.b says stunned only stops its combat damage (Vex, Apathetic adds "They can't move it" for that). A
  stunned unit is no longer stunned again (424.1.a.1): no second "stun" event for Eclipse Herald-style triggers.
  Round-robins before this overrate stun decks (Vex, Kai'Sa's Stupefy, Riven, Broken Blade).
  05:20: two more pieces of the old stun model: `do_ready` refused to ready a stunned unit (no such rule); removed.
  "Heal it, exhaust it, and recall it" (Zhonya's, Guardian Angel, Soraka, Tactical Retreat) set the exhausted flag
  without the Exhaust action, so "When I become exhausted" (Reckless Innovator, Riven, Broken Blade) never triggered;
  `do_recall` now uses `do_exhaust`. rules_audit's move check now knows Vex's `cant_move_by`.
  10:20: a granted [Vision] (Forecaster: "Your Mechs have [Vision]", a Mech itself, 3 in Kai'Sa; Gemcraft Seer: "Other
  friendly units have [Vision]") was only a keyword, so it never predicted: Vision is a triggered ability (CR 817.1.b).
  `_apply_static` now adds the Vision trigger per grant (817.2: instances trigger separately). Checked OK: Brynhir's
  lock doesn't stop hiding (811.1.c.1), Temporal Breach on a token plays nothing, hidden cards at a lost battlefield
  are trashed in the cleanup (107.3.d).
  15:20: the same gap for [Disarm]/[Hunt]: Clanging Sentry's "Your Mechs have [Disarm]" never triggered, and printed
  Hunt/Disarm used the printed number only. Now one trigger per unit with the summed value (CR 823.2, 831.1.d.1:
  `scripts.hunt_ability/disarm_ability`, `game._grant_keyword_trigger` for statics and mods).
  20:20: Predict 2+ put the kept cards back in their old order; CR 437.1.a says "in any order": a `predict_order`
  decision (top to bottom) follows the recycle pick (ops.Predict). Checked OK: Legion counts only other cards
  finalized this turn (tokens aren't cards), Tianna/Otterpus replace gaining points (CR 470.2), Blitzcrank's hold.
  2026-11-16 00:20: an attached card's printed rules text stayed active (CR 135.4): an equipped Spinning Axe died to
  its own [Temporary] and attached gear could [Equip] again; `game._active_printed` drops printed abilities while
  attached (keywords stay visible, 135.4.a; abilities scripted from effect text, e.g. Guardian Angel, stay).
  05:20: that fix hid the Equip ability Weaponmaster reads (CR 821.1.c: "even if it's already attached"), so a
  Weaponmaster unit could no longer take an Equipment from another unit; `ops.PayEquip` now reads the printed Equip.
  Checked OK: Deathknell is skipped when Zhonya's/Guardian Angel replace the death (808.1.d.1), equipment Deathknell.
  10:20: multi-domain cards' split-colour power pips ([C], CR 135.2.e.6.c) took only the first domain (Defiant Dance
  needed Calm, never Chaos) or one of each (Tibbers: Fury + Chaos, never Fury + Fury). Now a requirement "fury|chaos"
  (`payment.own_power` / `req_ok`) used by card costs, [C] in ability costs and Accelerate. Cards checked against the
  images. Round-robins before this underrate Irelia, Akali, Azir, Master Yi, Riven (Blade of the Exile) and Sett.
  15:20: Repulse (Master Yi and Sett sideboards, the only unscripted card in any tournament list or sideboard) is
  hand-scripted in cards_manual.py: counters an enemy item that chooses the friendly unit and no other friendly unit.
  Checked OK: a Temporary unit killed before scoring loses the hold (CR 190.4.c), Sprite Fountain's Deathknell
  replays its Sprite when Temporary kills it, Defy reads printed costs (CR 356.1.c).
  20:20: a cost at the start of a non-"may" trigger ("Recycle me to ...", Ekko, Recurrent; "banish a card from any
  trash to ...", Gust Monk; "exhaust me to draw 1", Titanic Shrine) was paid on resolution; CR 383.3.b makes it the
  base cost, paid as the trigger is finalized: `targeting.TriggerBaseCost` in the finalize code. rules_audit no
  longer reports a staged combat waiting on choose_showdown as contested (CR 463.1).
  2026-11-17 00:20: Nocturne, Horrifying (errata: "As you look at or reveal me from the top of your deck, you may banish
  me ...", 3 in Kennen) was always played to base (or the looking effect's battlefield); now his owner picks base or a
  battlefield they control (CR 355.2.a). Reveals from the top (Dazzling Aurora, Mechanical Bandit, Blind Fury, Diana,
  Lunari) never offered him: `ops.SeeFromDeck` asks each card's owner; Aurora reveals on past a banished Nocturne.
  05:20: Riven, Broken Blade's "Spend my buff to [Stun] an enemy unit" chose the unit on resolution, after spending the
  buff; "[do X] to [do Y]" makes the unit a target (CR 355.10.c.1), now picked with the mode (auto_grammar lifts the
  choices of "spend a buff to" / "kill|exhaust|banish a ... to"; only Riven changed). Bedeviling Stranger's enemy unit
  is now chosen with the battlefield as the trigger goes on the chain (355.12). A scan of every card finds no other
  targeted choice left for resolution except Battle Preparations' runes.
  10:20: Fiora, Victorious ("While I'm [Mighty], I have [Deflect], [Ganking], and [Shield]", Sett deck) read her own
  Might from printed Might + buffs only, so Shield from elsewhere (Hunting Blind, 6 [M] defending) never made her
  Mighty. `Game.chars` now re-applies the layers until nothing changes when an object's effects read the object
  itself (CR 478.3; partial chars in `_partial`). Smoke games are unchanged and run at the same speed.
  15:20: "becomes [Mighty]" (CR 709) was only announced by mods and buffs, so a unit reaching 5 [M] through [Assault]
  as it attacks, [Shield] as it defends, a static (Sett, Kingpin) or a -[M] effect expiring never triggered Fiora,
  Worthy or the Grand Duelist legend. The cleanup now compares each unit with the last state seen
  (`Game._check_becomes_mighty`, temp `__mighty`; only while something can trigger on it).
  20:20: a Deflect target was allowed when the tax alone was payable, ignoring the cost of the spell or ability
  choosing it (and the tax of targets already chosen; `__deflect_cost` was never set): Hextech Ray with one Fury rune
  could choose Vex, Apathetic, then failed to pay and went to the trash. CR 355.16: `Game._unpaid_base_cost` adds the
  unpaid cost to the check (finalize: the item's cost; legal actions: `_spell_has_targets(cost=)`, activations), and
  rules_audit's missing-play check does the same. Skipped (tax only) while a later cost reduction could apply.
  2026-11-18 00:20: Bonus Damage (CR 712-715) was added to each part of a Split (Annie, Fiery + Scorched Earth's 5
  split three ways dealt 8); it now joins the amount to split once and raises the target cap (715.3, `ops.split_cap`,
  `Game.split_bonus`, parts dealt with `do_deal(bonus=False)`). A Deal of 0 (0-Might fight, "1 for each" with none) no
  longer gets Bonus Damage (715.4). Split targets were capped at 5 whatever the amount (Scorched Earth now its 5 + bonus).
  05:20: Fiora, Peerless checked "one on one" on resolution; it is the trigger condition (CR 383.2.a, 740.2.b), now a
  `filt` checked as she attacks/defends. Open: Lotus Trap's doubling and Ki Barrier's prevention on one unit are both
  replacement effects whose order its controller picks (CR 372, 433.1.b); `do_deal` always doubles first.
  10:20: a hidden card's targets must be at its battlefield unless the text makes that impossible (CR 811.1.d.2-3);
  any selector condition counted as making it impossible, so Facebreaker and Switcheroo played from facedown targeted
  anywhere when their battlefield had no legal pair (no valid target: can't be played). Only `Sel(elsewhere=True)`
  ("at another/a different location": Tideturner, Evelynn, Entrancing, Resonating Strike) chooses freely now.
  15:20: "When you choose or ready me" (Irelia, Fervent: Master Yi and Irelia decks) and "When you choose me with a
  spell" (Jae Medarda) triggered when an opponent chose the unit (an enemy Discipline gave Irelia +3); they now need its
  controller's spell/ability (the "target" event carries `item_kind`). Round-robins before this overrate Irelia, Fervent.
  20:20: "When you stun/buff/empower ..." read the affected unit's controller as "you": Eclipse Herald and Leona, Radiant
  Dawn never triggered on stunning enemies but did when an enemy stunned your unit. The stun/buff/empower events carry
  `by` (`abilities._by_me`); "one or more" stuns trigger once per Stun instruction (event `batch`), "enemy" is checked.
  No tournament card uses these triggers.
  2026-11-19 00:20: Akshan, Mischievous (Sett deck) took the gear for good when he left the board before his play
  trigger resolved; CR 359.3's example says the control effect is never generated. The gear is still moved and the
  cleanup recalls it to its controller's base (323.6). Checked OK: the "you ..." trigger table (draw, discard, recycle,
  channel, reveal, conquer/hold) reads the right player.
  05:20: a trigger's "it"/"me" followed the uid, so a unit returned to hand and played again with the trigger on the
  chain was still hit (Imperial Decree killed the replayed unit); CR 124 makes it a new object. Triggers remember the
  entry stamps of their event object and source while on the board (`Game._stamp_trigger_objects`, ctx `__ev_stamps`)
  and `ops._uids` drops a replaced one. Checked OK: Gust re-checks 3 [M] on resolution, Star-Crossed still returns the
  enemy when the friendly unit is gone, Traveling Merchant draws with an empty hand, "to a minimum of" snapshots.
  10:20: a play effect of a unit played from facedown still hit its battlefield target after the unit left the board
  (Kennen, Keeper of Balance killed in response still stunned); CR 811.1.d.3.a says it mistargets, since it reads
  where it was played from its source. `Game.hidden_source_gone` empties those choices at finalize and `_Recheck`
  drops them at resolution. Checked OK: Blood Rush follows its errata ("this turn"), Lingering Animus counts gear.
  15:20: attached gear kept its old location when its unit moved or was recalled (CR 719.3.a: attached cards move
  with the top-most card), so Orianna, Exquisite (Irelia deck) dealt no combat damage beside an equipped unit that had
  moved in, and a dead unit's Equipment detached in base instead of where the unit died (436.4.b, then recalled).
  `Game._sync_attachments` runs on every location change (move, recall, control change in base).
  20:20: "They deal damage equal to their Mights to each other" (Challenge, Rampage, Marching Orders ...) and "It deals
  damage equal to its Might" (Alpha Strike, Last Breath) are dealt by the units, not the spell (CR 418.6.b.3), but were
  treated as spell damage: Unyielding Spirit (Master Yi deck) prevented them and Annie/Ravenborn Tome/Void Gate Bonus
  Damage was added. `do_deal(source_uid=<unit>)` now marks the event `unit_source` (no spell/ability prevention or
  bonus, the unit's controller is responsible, 418.6.b.4). "Deal damage equal to my Might" (Yasuo, Graves, Caitlyn,
  Ezreal, Dashing) is ability damage and no longer passes the unit as the source.
  2026-11-20 00:20: delayed abilities matched "it" by uid, so a chosen unit returned to hand and played again was
  still hit (Noxian Guillotine killed the replayed unit on its next damage; Siphoning Strike / Deadly Flourish paid
  out when the new object died; Tornado Warrior disempowered it). CR 124: `Game.add_delayed` stores the entry stamps
  of the chosen board objects and the source (ctx `__dl_stamps`); events about a replaced object don't match and
  `ops._uids` drops it on resolution. Checked OK: Switcheroo follows CR 434 (increase/decrease, snapshotted),
  Akali, Silent's "unless I'm in combat" uses the combat battlefield (designations are set in each cleanup).
  05:20: Not So Fast and Repulse read an item's choices by uid, so a target that was returned to hand and played again
  still counted as chosen (Not So Fast could counter a Hextech Ray whose target had been replayed); CR 359.3.e.9.a
  counts mistargeted choices still on the board but not ones that changed to or from a non-board zone.
  `Game.current_targets(ctx)` drops choices whose entry stamp changed. Checked OK: no "give ... [keyword]/[M]" without
  "this turn" lasts only the turn (scan of every card; Blood Rush is errata), Shadow's Call's [Temporary] is
  permanent, Time Warp banishes itself, expert-policy rules_audit (8 games) clean.
  10:20: a unit with both Tank and Backline (or "assigned last") always took combat damage first; CR 467.2.c.8 lets
  the assigner fulfil either one (first or last, never in between), each such unit separately (467.2.c.9):
  `flow.DamageAssignmentsAny` unions the per-pick automata. Checked OK: hiding from the champion zone (Kennen,
  Keeper of Balance), Back Off draws only from hand, Edge of Night attaches at its play location.
  15:20: damage replacement effects on one unit (Lotus Trap's doubling, Counter Strike's prevent-next, Ki Barrier-style
  shields) always applied doubling, prevent-next, shields; CR 372 (example at 467.2.c.5) lets the unit's controller
  order them: `Game._damage_mod_orders` lists the distinct outcomes and `do_deal` asks (`game._DamageOrderStep`,
  decision `order_replacement`), then goes on with that target and the rest. Open: combat lethal need
  (`preview_damage`) still assumes the default order; replace_event replacements (Unyielding Spirit) always go first.
  No tournament list plays these cards.
  20:20: a card that went to a hand in public view (a unit returned by Gust/Rebuke/Star-Crossed/Retreat, a card
  taken from the trash, a card revealed from the deck and then drawn) became unknown to the opponent, so the AIs'
  `determinize` reshuffled it into a random card (no cheating, but public information lost). `Game._to_zone` /
  `_draw_raw` now record it in `Game.known` for the players who saw it (`Game._public_viewers`); drawn and facedown
  cards stay hidden. The play page shows such cards face up in the opponent's hand. Checked OK: Concert Poster's
  conquer trigger, The Empyrean's Predict amount, Bellows Breath's same-location choice.
  2026-11-21 00:20: "choose a battlefield" targets the battlefield (CR 170.7) and "units at a battlefield" restricts
  the units' targets, but `ChooseLocation` ignored the hidden restriction (811.1.d.2-3): Bedeviling Stranger (Riven,
  Kennen) played from facedown could pick another crowded battlefield, Fox-Fire, Ahri could kill units anywhere,
  Resonating Strike could pick any battlefield you control. `ChooseLocation(targeted=True)` (also the auto "split
  among ... at a single battlefield") now keeps the hidden battlefield; destinations stay free. This answers the
  2026-11-09 open question. Checked OK: hidden Temporal Breach whose unit moved off its battlefield does nothing
  (CR 359.3.e.2.a example), Seal of Discord pays as an Add source, En Garde, Shuriken Flip, Sabotage reveals.
  05:20: runes recycled together went to the bottom of the rune deck in a random order; CR 417.5.a gives their owner
  the order (main deck cards stay random, 417.5). `ops.Recycle` asks `recycle_order` (one domain per place, runes of
  a domain are interchangeable) and `do_recycle(rune_order=)` keeps it (Coalesced Energy). Checked OK: Pyke, Dockside
  Butcher from facedown offers its [Fury] additional cost, Trifarian Captain's Power limit, Weaponmaster's "[A] less"
  also reduces a domain Power cost (CR 356.4.f example; 821.1.c.3 reads as "no Power").
  10:20: every spell played from the trash was banished as it left the chain, but CR 829.1.b banishes only Flow
  plays (printed Flow or Kennen's granted Flow): Death from Below's "you may play this from your trash for [A]"
  copy was banished instead of going back to the trash, and a countered Forbidden Technique replay was banished.
  `_play` now marks Flow plays (ctx `__flow`, never effect plays); resolve, counter and fizzle read that flag.
  Checked OK: Lonely Poro's "alone" (CR 740.2.a, friendly units at its location), An Offer You Can't Refuse
  gives the Gold to the gear's controller, Kinkou Initiate counts only your other units.
  15:20: Battle Preparations' "If you showed off, ready up to 2 runes" chose the runes at resolution (the last
  targeted choice left there, see 2026-11-17 05:20); runes are public, so they are targets chosen as it is played
  (CR 355.5, 355.10), right after the Show Off pick. Hand-scripted in cards_manual.py (nothing to choose if nothing
  was shown off). Checked OK: Ember Monk triggers only on facedown plays, Gutter Guardian can't show off a
  facedown card (Radiance FAQ), Astral Heron's discount is "this turn" (errata) and used by effect plays (CR 420
  example), Evelynn, Entrancing needs your turn, Baron Nashor only enters the Pit when he adds it, Decree of Rage.
  20:20: a scan of every card for targeted choices left in resolution code found three hand scripts: Kha'Zix,
  Evolving Hunter ("you may spend 3 XP to deal ... to an enemy unit here") and Lady of Clockwork ("you may pay [1]
  to choose a friendly gear") now pay and choose as the trigger is finalized (CR 383.3.b, 355.10.c.1;
  `targeting._peel_costs` knows non-optional SpendXP). Teemo, Strategist follows his errata: defend trigger only,
  enemy unit chosen on the chain, one Deal of N (418.8), none for 0. Not in any tournament list. Checked OK:
  move destinations are chosen while playing (CR 355.4), Thrill of the Hunt's battlefield is picked by the play
  itself, Undertitan adds [2] as Void Burrower reveals it, Noxian Emissary's Empowered Deathknell.
  2026-11-22 00:20: reflexive triggers ("Then do this:", CR 388-389) made their choices and "you may" on resolution;
  `Game.add_reflexive` now splits them like a trigger (`split_trigger`: choices, a leading may and its cost are
  settled as the item is finalized, 388.4). Arise! and Guards! (Azir deck) did their errata's "Then do this:"
  inline; both now put a reflexive item on the chain (players can respond before the Soldiers are readied).
  Open: other errata "do this" cards ("If this kills it, do this: draw 1", Reflection copies, "Do this
  twice") are still inline. Checked OK: Hunker Down's move lock covers every mover, Abandon keeps a Flow spell
  banished, Alpha Strike gains XP per unit its damage kills.
  05:20: Disintegrate ("Deal 3 to a unit at a battlefield. If this kills it, do this: draw 1") never drew: the
  unit dies of lethal damage in the cleanup after the spell (CR 323), but the auto-script checked the trash while
  resolving. Hand-scripted as a delayed die trigger credited by `dmg_item` (like Alpha Strike; the only other
  "this kills" card). Dragon's Rage, Lee Sin's errata "Then do this: Choose another enemy unit at its
  destination" is now a reflexive item (target chosen at its finalize). Still inline: Rell, Magnetic's "then do
  this: Attach it to me"; Bone Skewer, Mirror Image, Keeper of Masks and LeBlanc, Deceiver are unscripted.
  10:20: "When you play a spell/card" triggers fired as the spell was finalized, above it on the chain, and even when
  it was countered; CR 420.4.a (Vendetta notes: in a trigger condition "play" means "resolve") makes them trigger on
  the spell's resolution, never if countered (Ravenbloom Student, Ember Monk with hidden spells, Astral Heron). The
  spell's "play" event is held in ctx `__play_ev` and emitted in `_resolved`; units/gear resolve on finalizing, so
  unchanged. "First/second card" triggers read the event's `nth` (finalize order), not the count at resolution.
  Open: Fizz, Trickster's errata "Then recycle it" and Rell, Magnetic's "If you do, then do this: Attach it to me"
  read literally act while the played card is still on the chain; kept as "after it resolves" until a ruling.
  15:20: three scripts still followed pre-errata text (Spiritforged). Rek'Sai, Swarm Queen and Void Rush: "You may
  banish one, then play it": the card is banished first and played from there (paying, or [2] less), so one that
  can't be played stays banished instead of being recycled/drawn (CR 420.3.c). Jax, Unmatched: "Your Equipment
  everywhere have [Quick-Draw]" (was hand only): Reaction timing and the attach trigger for Equipment played from
  the trash, face down or by effects. None is in a tournament list.
  20:20: Salvage (errata: "You may kill up to one gear. Draw 1."; Viktor, Rek'Sai and Sett lists) was auto-scripted as
  "choose exactly one gear", so it could not be played with no gear on the board and a gear had to be chosen;
  hand-scripted in cards_common.py (up to one target, CR 355.10). Dazzling Aurora follows its errata ("reveal ...
  until you reveal a unit and banish it. Play it"): a unit that can't be played stays banished. Checked OK: Clockwork
  Keeper's draw is a play trigger, Targon's Peak readies up to 2, Highlander heals/exhausts/recalls.
  2026-11-23 00:20: Sigil of the Storm (errata: "you must recycle one of your runes. (This doesn't choose anything.)")
  picked the rune as the trigger went on the chain; CR 355.10.f picks it as it resolves (hand-scripted, Choose
  `at_resolution`). Scans: every "up to N" / "any number of" choice in every script allows fewer (CR 355.13), and
  "must" instructions (Safety Inspector, Shard of Undoing, Angler Wyrm) choose nothing early. Open: "ready your
  legend" (Hall of Legends, 355.10.g) is still a target chosen at finalize; not in any tournament list.
  05:20: Hall of Legends hand-scripted: "ready your legend" is no longer a target (CR 355.10.g); with several legends
  it is picked as the ability resolves, the [1] is still decided and paid as the trigger is finalized (383.3.b).
  Checked OK: Azir equipment (Eye of the Herald, Hand Hammer, Brutalizer), Deathgrip errata targets, Thrill of the
  Hunt, Ambush locations/timing, Ganking, attachment control (CR 718.5.f).
  10:20: "... and draw it" (Lightning Rush, Trifarian Captain in Kennen; Apprentice Smith, Pakaa Protector, Raving
  Witness, Fate Weaver, Double Trouble, Ornn, Ivern, Diana, Lunari) put the card in hand without the Draw action, so it
  never counted for Frigid Jewel ("your second card each turn") or "when you draw" triggers; CR 414.1 makes it a draw:
  `Game.draw_card` / `ops.DrawCard`. Checked OK: Falling Star / Icathian Rain errata (separate Deals, the same unit can
  be chosen each time), Death from Below's replay, Thousand-Tailed Watcher only hits units there as it resolves.
  15:20: the auto-scripter's "reveal a <kind> from among them and draw it" / "draw it" lines also use `ops.DrawCard`
  (no current auto card hit them; Rift Herald and Command: Attack are unscripted). Checked OK: Decree of Focus (combat
  with a Fury unit or chosen by an enemy Fury spell), Life from Stone exhausts only a ready unit, Pit Rookie / First
  Mate choose another unit, Ruin Runner / Baron untargetable only for enemies, Challenge-style fights, Temporal Breach.
  20:20: auto "you may <targeted X>. If you do, Y" set "did" whether or not X happened: Adaptatron (Irelia deck: "you
  may kill a gear. If you do, buff me") and Pickpocket still got Y when the gear left before the trigger resolved
  (CR 359.3: an illegal target is not affected). `auto_grammar` now sets `__did` only while every targeted choice of
  X is still legal. Checked OK: scoring once per battlefield per turn and the final point (CR 471-473), Forgotten
  Monument, Accelerate on effect plays (CR 356.1.b.3), Blood Money, Imperial Decree, Shadow's Call, stun re-choice.
  2026-11-24 00:20: Emperor's Dais (Azir deck) followed its pre-errata text ("... hand. If you do, play ..."); the
  Vendetta errata reads "pay [1] and return a unit you control here to its owner's hand to play a ... Sand Soldier",
  so both are the base cost (CR 383.3.b): the unit is returned as the trigger is finalized (not a target; yes only
  while a friendly unit is there and [1] is payable) and the Soldier comes even if nothing is left there. The Diana,
  Lunari open question is answered by the same errata ("you may pay [1] to [Predict], then reveal ..."): no pay, no
  reveal, as scripted. Checked OK: hand scripts' "If you do" (Meditation, Call to Glory, Jayce, Crescent Guardian).
  05:20: a hidden card with printed [Reaction] (Consult the Past, Lotus Trap, Resonating Strike) could be played from
  facedown the turn it was hidden; CR 811.1.b gives the "you may play this" permission only "beginning on the next
  turn" (`flow` timing check needs `turn > facedown_turn` for every facedown play). Smoke games with these cards change.
  10:20: Mageseeker Warden ("opponents can only play units to their base") didn't stop enemy hidden units, which must be
  played to the battlefield they were hidden at (CR 811.1.d.1): with both, the unit has no legal location and can't be
  played from facedown (`flow._opp_warden`, rules_audit too). Last Caress ("even from face down ... any battlefield")
  and Arachnoid Horror's static are still unscripted. Smoke games unchanged.
  15:20: attackers recalled in step 3d of the combat cleanup (defenders still there) made the defender the combat's
  winner; CR 468.3.d calls that "No Result", so only a side whose opponent has no units left wins. "When I win a
  combat" (Nidalee, Cat Form, Sett deck), "When you win a combat" and Grim Resolve paid out for surviving
  (`flow._task_combat_result`). Checked OK: Weaponmaster's choice is made as the trigger is finalized (CR 821.1.c),
  Equip's choice is a target (818.1.b.1: Irelia, Fervent triggers), Mageseeker's ready lock, Charm/Ride the Wind moves.
  20:20: two Sett-deck battlefields still decided their cost on resolution: Valley of Idols ("they may pay [1] to [Buff]
  it", hand script in cards_common.py) and Monastery of Hirana ("you may spend a buff to draw 1", auto). Both costs are
  the trigger's base cost (CR 383.3.b): yes/no and payment as it is finalized (Monastery now in cards_manual.py; the
  buff's unit is picked as part of the cost, not a target). Checked OK: every battlefield in the 12 tournament decks
  (Star Spring, Rakelstake, Abandoned Hall, Sunken Temple, Forbidding Waste, Candlelit Sanctum), combat control task.
  2026-11-25 00:20: a scan of every "When ..., you may <cost> to ..." card found hand scripts that still asked and paid
  on resolution because the may sat under an "if I'm ready" If or was written as "pay; if paid": Ravenbloom Prefect
  (Irelia list: "banish me to banish it"), Fresh Beans, Solari Shrine, Altar of Memories, Battlefield Armorer, Fae
  Porter, Mistfall, Ripper's Bay, Diana's [1], Jayce's ready target. `targeting.split_trigger` now treats a leading
  If as a precondition for yes and "pay; if paid" as "you may pay", and "banish me" is a base cost (CR 383.3.b).
  A ChooseMode with `at_resolution` (Altar's top/bottom) is not hoisted; Deceiver pays discard + exhaust at finalize and
  picks the copied unit after the Reflection exists. Open: Rumble (recycle another unit), Jinx/Mordekaiser (discard 1),
  Bottled Constellation (kill 3) decide at finalize but still pay on resolution; none is in a tournament list.
  05:20: those four are now hand-scripted with the cost in the finalize code (CR 383.3.b): Super Mega Death Rocket!
  and Mordekaiser, Dominating discard as the trigger is finalized (Mordekaiser's target is picked then too), Rumble,
  Hotheaded recycles the other unit then (the Mech is picked on resolution), Bottled Constellation needs exactly 3
  picks (the old script let you pick fewer and then did nothing) and kills them together before the point is scored.
  10:20: a chosen player is a target (CR 355.7, 355.9.a) but `ops.ChoosePlayer` ran on resolution: Bewitching Spirit
  ("choose a player. They discard 1") and Blade Twirler picked late; `targeting.split_choices` now hoists it (every
  "choose an opponent" too, one option in 2 players). Miss Fortune, Captain ("The first time I move each turn, you may
  ready something else") asked on resolution and was a once-each-turn trigger, so a "no" let her second move trigger it
  (CR 383.3.e.2.b is only for "once each turn"); now may + choice at finalize, filter = her first move this turn.
  Checked OK: Lucian/Draven "first time" (no may), Twilight Shroud, Hush/Defy costs, Time Warp's turn queue, Stupefy's
  minimum on a 0-Might unit, Lightning Rush + Nocturne.
  15:20: [Weaponmaster] (CR 821.1.c "When you play me, you may choose a Card ... with the Equipment tag") chose the
  Equipment or "none" at finalize, so "no" still put the trigger on the chain; now a `_TriggerMay` (pre: you control an
  Equipment) then the choice, and no removes it (383.3.a.2); the Equip cost is still paid on resolution (821.1.c.5).
  Lucian and Akshan (Sett deck) are affected. Veiled Temple ("you may ready a friendly gear", same allow_none trick)
  and Sivir, Ambitious (a Do before the May) decided late too. Checked OK: Death from Below's replay (a trigger on
  its resolution with a leading may), Black Rose Sanctum / Star Spring / Rakelstake "first time" memos, rune pool
  emptying (CR 167), cleanup steps 4-8 (CR 323.5-323.10), effect plays to a given location, "once each turn" texts.
  20:20: a scan of every ability for targeted choices left in resolution code found Crumbling Sands ("Counter a spell
  if an opponent has played another spell this turn"): the auto-grammar read that condition as the caster's [Legion]
  (cards *you* played) and the If around the Choose kept the spell from being chosen as it was played. Hand-scripted
  (cards_manual.py: target at play, opponents' spells other than the chosen one checked on resolution); the grammar's
  "an opponent has played another X" no longer maps to Legion. Smoke games with it in a random deck change. Twisted
  Fate, Gambler's choices stay on resolution (they depend on the rune revealed then).
  2026-11-26 00:20: a read through the auto-grammar's conditions found "you have N+ units at that battlefield" (Garen,
  Might of Demacia legend and its Starter: "When you conquer, if you have 4+ units at that battlefield, draw 2") counting
  units at the trigger source's place, which a legend doesn't have: it never drew. "That battlefield" now reads the
  event's location ("here" still the source's). No other legend's auto text reads "here"/"that battlefield"; no auto
  trigger condition reads "it" (the intervening check has no targets yet). Checked OK: Revna / Forgotten Library's
  "if you spent [4] or more" (the spell's play event carries the energy), Akali, Silent's "unless I'm in combat".
  05:20: Tryndamere, Barbarian ("When I conquer after an attack, if you assigned 5 or more excess damage to enemy units,
  you score 1 point") summed the excess of every combat that turn (auto condition read a whole-turn memo), so 3 excess
  in one combat and 2 in a later one scored; it now reads that combat's excess like Sivir, Ambitious (`combat_excess`).
  Checked OK: Ahri, Confident's -[M] watch, Solari Shrine needs your kill, Storm Raptor, Blast Cone's move trigger.
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
- Engine speed (2026-11-16, Derrick picked the refactor): caches that only depend on zones, printed abilities, mods and
  attachments key on `Game.struct` (bumped by `Game.restruct()`, which also bumps `version`); board list, statics,
  trigger/rule/replacement/add-source indexes. Anything that changes an object's zone, defn, mods, attachments or copy_of
  must call `restruct()` (tests do after editing cards). `RIFTSHARK_CACHE_CHECK=1` compares every structure-keyed hit
  with a rebuild. Games are move-for-move identical to before; gen 14 1.35x, expert 1.48x, search-v2 1.42x faster.
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
