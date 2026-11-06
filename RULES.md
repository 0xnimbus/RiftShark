# Rules coverage (engine v2, `riftsim/core`)

Reference: Riftbound Core Rules 2026-10-09 (`docs/rules/`). The engine enumerates every legal option at every
decision, so a replay that re-simulates identically (`python -m riftsim.core verify`) contained only legal moves
under the rules as modelled here. Anything listed under *Simplifications* is where results can differ from paper play.

## Modelled

- 1v1 mode: 8 points to win, 2 battlefields (one picked at random from each deck's three), 12-rune rune deck,
  40-card main deck including the Chosen Champion (which starts in the Champion Zone), legend on the board.
- Turn structure: Awaken (ready everything; stun only stops combat damage and ends in the end-of-turn cleanup, CR 424.1), Beginning, Scoring (hold), Channel (2 runes; the
  second player channels 3 on their first turn), Draw, Main, Ending (end-of-turn cleanup, buffs/mods expire),
  Expiration. Extra turns via a turn queue (Time Warp).
- The chain with HOT FEPR ordering, priority vs focus, Neutral/Showdown × Open/Closed states, reactions and actions,
  cleanups per CR 323, simultaneous triggers ordered APNAP with each controller choosing the order of their own (CR 383), mulligan in turn order (CR 117), reflexive and delayed triggers, replacement
  effects, static layers (might, keywords, tags, types, granted abilities, rule flags).
- Showdowns (CR 345-348) and combat (CR 466-468): designations, attack/defend triggers, lethal-first damage assignment
  with Tank first and Backline last, combat cleanup, result, control and conquer; hold/conquer scoring, the final-point
  rule 473.1.b, the standard move (exhaust cost, base ↔ battlefield, Ganking battlefield → battlefield), hiding cards
  face down and playing them later as reactions.
- Costs: energy and power (domain) costs, Accelerate/Repeat/Flow alternative costs, Deflect, exhaust/kill/banish/
  discard/spend-buff/XP costs, "Add" resource abilities with pools emptying at the start of the main phase and end of
  turn.
- Keywords CR 805-832: Accelerate, Assault, Deathknell, Deflect, Ganking, Hidden, Legion, Shield, Tank, Temporary,
  Vision, Equip, Quick-Draw, Repeat, Weaponmaster, Ambush, Hunt, Level, Unique, Backline, Empower/Empowered, Flow,
  Deploy, Disarm, Mighty.
- Card text is compiled from the printed rules text by a grammar (`scripts/auto_grammar.py`), with hand-written
  scripts for cards the grammar cannot express (`scripts/cards_manual.py`). `python -m riftsim.core coverage` lists
  cards whose text is not fully scripted: such cards play with whatever part of their text was understood (keywords
  always work).

## Rune payment (exact since 2026-11-06)

Paying a cost is a player decision (`pay`): every distinct way to pay is offered, covering which runes to exhaust
for [1], which to recycle for [C] and in what order, other Reaction Add abilities (Kai'Sa's legend, Seals...) and
which pool resources to spend (`riftsim/core/payment.py`). Runes' two abilities can also be activated on their own
at any Reaction window to float resources. Add restrictions ("Use only to play spells", "only during showdowns")
are enforced. Paying Energy/Power in effects is always optional (CR 445.2). The one choice not offered is
recycling a ready rune without exhausting it first, which is strictly dominated (the extra [1] can never hurt).
The built-in AIs do not float resources outside payments; that is an AI limitation, not a rule.

## Show Off, alternative costs, battlefield tokens, information (exact since 2026-11-06)

- `[Show Off]` (CR 832): while finalizing, the controller may reveal a matching card from hand or pick a matching
  friendly object on the board (decision `show_off`). The shown-off card's characteristics are locked in
  (The Empyrean predicts its Power cost; Battle Preparations readies up to 2 runes).
- Blade of the Exile offers both Equip costs: [A], or exhaust a ready friendly unit (it may be the unit equipped).
  Weaponmaster reduces the [A] cost.
- Baron Nashor adds the Baron Pit battlefield token as he is played (if there is none) and enters there. Units can move
  to the Pit from any location without Ganking.
- Reveals are information: revealed hand cards stay known to the other player until they change zones, Scuttle Crab
  lets its controller look at facedown cards for the turn. The AIs' determinisation keeps what they know and shuffles
  only what they cannot see (including facedown cards); the play page shows the human what they know.

## Choices and targets (exact since 2026-11-06)

- Spells, triggered and activated abilities make their choices while being finalized on the chain (CR 355.3-355.5,
  355.12, 355.14.b): targets, "choose a battlefield", move destinations, and choices inside "you may ..." (the may itself
  is decided on resolution). Opponents see the targets before they react; Deflect costs and "when chosen" triggers use them.
- On resolution, a target that changed zones or no longer meets its requirements is unaffected; the rest of the spell
  still happens (CR 359.3.e). Hidden cards keep the "at this battlefield" restriction (CR 359.3.e.2.a).
- Groups of targets "at the same location" (Bellows Breath) are chosen together; if they split up, the controller picks
  one location's group (CR 355.11.b).
- Choices among hidden cards (hand, deck) and choices inside conditionals stay at resolution, as printed.
- `riftsim/core/targeting.py` does the split; `tests/test_targeting.py` covers it.

## Rules audit (2026-11-06)

`tools/rules_audit.py N SEED [policy]` plays games between the tournament decks and checks every action decision against
an independent reading of the rules (moves, play timing and locations, hiding, passing) and board invariants (zones,
runes, cleanups, scoring, Channel Phase counts). Fixed by the audit: card-level vs mentioned keywords and numbered
keywords (`cards._card_level_keyword`), multi-origin and stunned moves, the second player's first channel, victory
before trigger ordering, full combat damage assignment (CR 467.2.c, lethal counted after replacement and prevention),
untruncated discard/recycle choices, repeated burn out (CR 432), Focus passing after units in showdowns.
Interpretation: a unit no damage can kill may absorb any part of combat damage (CR 467.2.c.6 "if able").

## Simplifications (results can differ from paper play) — every item here is a bug to fix (owner rule: no simplifications)

- Optional ("you may ... instead") replacement effects are not built yet. The engine refuses to create one, so the four
  cards that need it (Mordekaiser, Twice Slain; Zilean, Time Mage; Heimerdinger, Academy Instructor; Sett, The Boss)
  stay unscripted and no deck containing them is legal; nothing is auto-applied.
- Card text the grammar could not parse is skipped for that card (see coverage); the long tail is being hand-scripted,
  competitive staples first. Since 2026-11-06 a deck containing such a card is illegal (`Deck.validate` rejects it when
  scripts are attached), so no simulated or coached game can use a simplified card without a loud error.
- A safety cap of 60 turns stops a simulated game. It is not a rule: such games are reported as unfinished with a
  warning and left out of win rates (never counted as draws). Play sessions use the same cap.
