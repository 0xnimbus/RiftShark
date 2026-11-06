# Rules coverage (engine v2, `riftsim/core`)

Reference: Riftbound Core Rules 2026-10-09 (`docs/rules/`). The engine enumerates every legal option at every
decision, so a replay that re-simulates identically (`python -m riftsim.core verify`) contained only legal moves
under the rules as modelled here. Anything listed under *Simplifications* is where results can differ from paper play.

## Modelled

- 1v1 mode: 8 points to win, 2 battlefields (one picked at random from each deck's three), 12-rune rune deck,
  40-card main deck including the Chosen Champion (which starts in the Champion Zone), legend on the board.
- Turn structure: Awaken (ready, stunned objects stay exhausted), Beginning, Scoring (hold), Channel (2 runes; the
  second player channels 3 on their first turn), Draw, Main, Ending (end-of-turn cleanup, buffs/mods expire),
  Expiration. Extra turns via a turn queue (Time Warp).
- The chain with HOT FEPR ordering, priority vs focus, Neutral/Showdown × Open/Closed states, reactions and actions,
  cleanups per CR 323, triggered abilities ordered turn player first, reflexive and delayed triggers, replacement
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

## Simplifications (results can differ from paper play) — every item here is a bug to fix (owner rule: no simplifications)

- Simultaneous triggers are ordered automatically (turn player first, then in object order), not by player choice.
- Optional replacement effects are auto-applied; mulligans are skipped.
- `[Show Off]` is not implemented: "if you showed off" clauses never fire (The Empyrean, Battle Preparations).
- Blade of the Exile's alternative Equip cost (exhaust a friendly unit) is not offered; only [A] is.
- Baron Nashor's Baron Pit battlefield token is not modelled: Baron plays like a normal unit (its other abilities work).
- Scuttle Crab's "look at their facedown cards" is a no-op (the AI already sees the full state).
- Card text the grammar could not parse is skipped for that card (see coverage); the long tail is being hand-scripted,
  competitive staples first. Since 2026-11-06 a deck containing such a card is illegal (`Deck.validate` rejects it when
  scripts are attached), so no simulated or coached game can use a simplified card without a loud error.
- A safety cap of 60 turns per game counts as a draw.
